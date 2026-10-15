"""Simulator validation (T-N10-1, T-N10-3): the shipped JSON, the venue, the batch script."""

from __future__ import annotations

import json
import os
import shutil
import statistics
import subprocess
from pathlib import Path

import pytest
from shapely.geometry import Polygon

from api.core.geometry import validate_venue
from api.core.settings import ROOT_DIR
from api.core.validation import (
    VALIDATION_PATH,
    bottleneck_venue,
    error_pct,
    holding_depth,
    load_validation,
    summarize,
)
from api.models.validation import SimulatorValidation

DATA = ROOT_DIR / "data" / "validation" / "bottleneck2006"


def test_shipped_validation_json_validates_with_three_seeds_per_width() -> None:
    data = load_validation()
    assert data is not None, "api/data/validation.json is missing: run make validate"
    assert len(data.widths) >= 5
    for w in data.widths:
        seeds = [r.seed for r in w.simulated_flow_ps.runs]
        assert len(seeds) >= 3 and len(set(seeds)) == len(seeds), w.run_name
        flows = [r.flow_ps for r in w.simulated_flow_ps.runs]
        assert w.simulated_flow_ps.median == pytest.approx(statistics.median(flows))
        assert w.error_pct == error_pct(w.simulated_flow_ps.median, w.measured_flow_ps)
        assert w.measured_specific_flow == pytest.approx(w.measured_flow_ps / w.b_m, abs=1e-3)
    assert (data.median_abs_error_pct, data.mean_error_pct) == summarize(
        [w.error_pct for w in data.widths]
    )
    assert data.meta.dataset_doi == "10.34735/ped.2006.2"
    assert data.meta.app_defaults and data.meta.assumptions


def test_model_rejects_inconsistent_ranges() -> None:
    raw = json.loads(VALIDATION_PATH.read_text())
    raw["widths"][0]["simulated_flow_ps"]["min"] = 99.0
    with pytest.raises(ValueError):
        SimulatorValidation.model_validate(raw)


def test_bottleneck_venue_matches_the_experiment_geometry() -> None:
    v = bottleneck_venue("b120", 1.2, 4.0, 178, corridor_w=7.0, distance_m=4.0)
    assert validate_venue(v).ok
    f = v.floors[0]
    walk = Polygon(f.walkable)
    # bottleneck b x l between y = 0 and y = l, centred on x = 0
    assert walk.intersection(Polygon([(-5, 0.5), (5, 0.5), (5, 3.5), (-5, 3.5)])).area == (
        pytest.approx(1.2 * 3.0)
    )
    zone = Polygon(f.zones[0].polygon)
    assert zone.bounds[3] == pytest.approx(-4.0)  # ends 4 m before the entrance
    assert f.zones[0].people / zone.area == pytest.approx(3.3, rel=0.01)
    assert holding_depth(178, 7.0) == pytest.approx(7.71, abs=0.01)


def test_load_validation_missing_file(tmp_path: Path) -> None:
    assert load_validation(tmp_path / "nope.json") is None


def _image_ok(image: str) -> bool:
    if shutil.which("docker") is None:
        return False
    r = subprocess.run(["docker", "image", "inspect", image], capture_output=True, check=False)
    return r.returncode == 0


@pytest.mark.slow
def test_validate_script_one_width_end_to_end(tmp_path: Path) -> None:
    """T-N10-3: the batch script on one width with a small headcount, in the sim image."""
    image = os.environ.get("SIM_IMAGE", "showtime-sim:latest")
    if not _image_ok(image):
        pytest.skip(f"docker or {image} not available")
    if not (DATA / "txt" / "b120.txt").exists():
        pytest.skip("validation data missing: run scripts/get_data.sh")
    out = tmp_path / "validation.json"
    env = {**os.environ, "DB_URL": f"sqlite:///{tmp_path / 'val.sqlite'}", "SIM_IMAGE": image}
    proc = subprocess.run(
        [
            "uv",
            "run",
            "python",
            str(ROOT_DIR / "scripts" / "validate_bottleneck.py"),
            "--runs",
            "b120",
            "--people",
            "40",
            "--out",
            str(out),
        ],
        cwd=ROOT_DIR / "api",
        env=env,
        capture_output=True,
        text=True,
        timeout=600,
        check=False,
    )
    assert proc.returncode == 0, proc.stdout[-2000:] + proc.stderr[-2000:]
    data = SimulatorValidation.model_validate_json(out.read_text())
    (w,) = data.widths
    assert w.run_name == "b120" and w.n_people == 40
    assert len(w.simulated_flow_ps.runs) == 3
    assert all(r.crossings == 40 for r in w.simulated_flow_ps.runs)
    assert 2.0 < w.measured_flow_ps < 3.0  # the experiment itself does not depend on --people
