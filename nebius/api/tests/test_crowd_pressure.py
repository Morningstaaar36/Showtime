"""Crowd pressure (Helbing et al. 2007) and Fruin level of service on synthetic frames.

`sim/crowd_pressure.py` needs only numpy and scipy, so it is tested here without JuPedSim.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path
from types import ModuleType

import numpy as np
import pytest

SIM = Path(__file__).resolve().parents[2] / "sim"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("sim_crowd_pressure", SIM / "crowd_pressure.py")
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


cp = _load()
NX = NY = 20


def _lattice(spacing: float) -> tuple[np.ndarray, np.ndarray]:
    g = np.arange(5.0, 15.0, spacing)
    xs, ys = np.meshgrid(g, g)
    return xs.ravel(), ys.ravel()


def test_uniform_flow_has_no_pressure() -> None:
    xs, ys = _lattice(0.5)  # 4 people per m^2
    v = np.full(len(xs), 0.8)
    d, p = cp.pressure_field(xs, ys, v, np.zeros_like(v), 0.0, 0.0, NX, NY)
    assert d[10, 10] == pytest.approx(4.0, rel=0.05)
    assert float(p.max()) < 1e-9


def test_counterflow_pressure_is_density_times_variance() -> None:
    xs, ys = _lattice(0.5)
    # alternate columns walk +0.5 and -0.5 m/s: variance 0.25 m^2/s^2 everywhere inside
    col = np.round((xs - 5.0) / 0.5).astype(int)
    vx = np.where(col % 2 == 0, 0.5, -0.5)
    d, p = cp.pressure_field(xs, ys, vx, np.zeros_like(vx), 0.0, 0.0, NX, NY)
    assert p[10, 10] == pytest.approx(d[10, 10] * 0.25, rel=0.05)
    assert p[10, 10] > cp.TURBULENCE_P
    assert float(p.min()) >= 0.0


def test_pressure_grows_with_density_at_equal_variance() -> None:
    rng = np.random.default_rng(1)
    out = []
    for spacing in (1.0, 0.5):
        xs, ys = _lattice(spacing)
        vx, vy = rng.normal(0, 0.2, len(xs)), rng.normal(0, 0.2, len(xs))
        out.append(cp.pressure_field(xs, ys, vx, vy, 0.0, 0.0, NX, NY)[1][8:12, 8:12].mean())
    assert out[1] > 2.5 * out[0]


def test_frame_velocities_match_ids_and_drop_jumps_and_floor_changes() -> None:
    ids = np.array([1, 2, 3, 4])
    prev = (ids, np.array([0.0, 1.0, 2.0, 3.0]), np.zeros(4), np.zeros(4, dtype=np.uint8))
    cur = (
        np.array([4, 2, 1, 3, 9]),  # reordered; 9 is new
        np.array([3.1, 1.0, 0.25, 9.0, 5.0]),  # 3 jumps 7 m (a model sidestep)
        np.zeros(5),
        np.array([1, 0, 0, 0, 0], dtype=np.uint8),  # 4 moved to another floor
    )
    x, _, vx, vy, fl = cp.frame_velocities(prev, cur, 0.25)
    assert sorted(vx.tolist()) == pytest.approx([0.0, 1.0])
    assert sorted(x.tolist()) == pytest.approx([0.25, 1.0])
    assert np.all(vy == 0) and np.all(fl == 0)
    assert len(cp.frame_velocities(prev, cur, 5.0)[0]) == 0  # too long a gap


def test_fruin_levels_of_service() -> None:
    # Fruin (1971) walkway: A >= 3.25 m^2/person ... F < 0.46 m^2/person
    dens = [0.2, 1 / 3.0, 1 / 2.0, 1 / 1.2, 1 / 0.7, 3.0, 5.0]
    assert cp.los_band(np.array(dens)).tolist() == [0, 1, 2, 3, 4, 5, 5]
    shares = cp.los_shares(np.array([1.0, 0, 0, 0, 1.0, 2.0]))
    assert shares == {
        "los_share_A": 0.25,
        "los_share_B": 0.0,
        "los_share_C": 0.0,
        "los_share_D": 0.0,
        "los_share_E": 0.25,
        "los_share_F": 0.5,
    }
    assert sum(cp.los_shares(np.array([3.0, 1, 1, 1, 1, 4])).values()) == pytest.approx(
        1.0, abs=1e-3
    )


def _run(acc: object, spacing: float, speed_sd: float, seconds: float = 4.0) -> None:
    rng = np.random.default_rng(3)
    xs, ys = _lattice(spacing)
    for k in range(1, int(seconds * 4) + 1):
        vx, vy = rng.normal(0, speed_sd, len(xs)), rng.normal(0, speed_sd, len(xs))
        acc.add(k * 0.25, xs, ys, vx, vy, np.zeros(len(xs), dtype=np.uint8))  # type: ignore[attr-defined]
    acc.finish(seconds)  # type: ignore[attr-defined]


def test_accumulator_counts_turbulent_time_only_in_dense_crowds() -> None:
    walk = [np.ones((NY, NX))]
    masks = [np.ones((NY, NX), dtype=bool)]
    dense = cp.PressureAccumulator(1, NX, NY, 0.0, 0.0, walk, masks, min_density=3.5)
    _run(dense, 0.5, 0.3)  # 4 people/m^2, irregular motion
    assert dense.turbulent_s == pytest.approx(4.0)
    assert len(dense.stored) == 4 and dense.stored[0].dtype == np.uint8
    hot = dense.hotspots(["F0"])
    assert hot and hot[0]["peak_pressure_per_s2"] >= cp.TURBULENCE_P
    sparse = cp.PressureAccumulator(1, NX, NY, 0.0, 0.0, walk, masks, min_density=3.5)
    _run(sparse, 1.0, 0.3)  # 1 person/m^2: same motion, below the density floor
    assert sparse.turbulent_s == 0.0 and sparse.hotspots(["F0"]) == []
    calm = cp.PressureAccumulator(1, NX, NY, 0.0, 0.0, walk, masks, min_density=3.5)
    _run(calm, 0.5, 0.01)  # dense but orderly
    assert calm.turbulent_s == 0.0
