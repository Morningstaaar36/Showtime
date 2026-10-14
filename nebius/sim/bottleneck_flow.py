"""Flow through a measurement line with PedPy: one method for real and simulated trajectories.

Used by `scripts/validate_bottleneck.py` through code jobs in the sim image, so the experiment's
trajectories and the simulator's are measured by exactly the same code and PedPy version.

Method (Seyfried et al. 2009, eq. 3; Liddle et al. 2009 use "the first 150 people"):
PedPy finds the frame at which each person crosses the line; the crossings are sorted in time
and the flow over the steady window from the `first`-th to the `last`-th crossing is
J = (last - first) / (t_last - t_first) persons/s, i.e. 1 / mean time gap. Specific flow = J / b.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
import pedpy

STEADY_FIRST = 10  # skip the start-up: the first people walk into an empty bottleneck
STEADY_LAST = 150  # Liddle et al. (2009) compute the flow from the first 150 people


def load_juelich_txt(path: str | Path) -> tuple[pd.DataFrame, float]:
    """Jülich archive trajectory txt (id, frame, x cm, y cm at 25 fps) -> metres."""
    raw = np.loadtxt(path, comments="#", usecols=(0, 1, 2, 3))
    df = pd.DataFrame(
        {
            "id": raw[:, 0].astype(int),
            "frame": raw[:, 1].astype(int),
            "x": raw[:, 2] / 100.0,
            "y": raw[:, 3] / 100.0,
        }
    )
    return df, 25.0


def from_showtime(traj: pd.DataFrame, frame_hz: float) -> tuple[pd.DataFrame, float]:
    """showtime_data.load_trajectories() [t, id, x, y, floor] -> PedPy columns."""
    df = pd.DataFrame(
        {
            "id": traj["id"].astype(int),
            "frame": np.round(traj["t"].to_numpy() * frame_hz).astype(int),
            "x": traj["x"].astype(float),
            "y": traj["y"].astype(float),
        }
    )
    return df.drop_duplicates(["id", "frame"]), frame_hz


def line_flow(
    df: pd.DataFrame,
    frame_rate: float,
    line: tuple[tuple[float, float], tuple[float, float]],
    width_m: float,
    first: int = STEADY_FIRST,
    last: int = STEADY_LAST,
) -> dict[str, Any]:
    """Crossings of `line` and the steady-window flow (persons/s and persons/(m·s))."""
    traj = pedpy.TrajectoryData(data=df, frame_rate=frame_rate)
    mline = pedpy.MeasurementLine(list(line))
    _nt, crossing = pedpy.compute_n_t(traj_data=traj, measurement_line=mline)
    frames = np.sort(crossing["frame"].to_numpy(dtype=float))
    times = frames / frame_rate
    n = len(times)
    hi = min(last, n)
    lo = min(first, max(hi - 1, 1))
    flow = None
    if hi - lo >= 1 and times[hi - 1] > times[lo - 1]:
        flow = (hi - lo) / float(times[hi - 1] - times[lo - 1])
    return {
        "people": int(df["id"].nunique()),
        "crossings": n,
        "window": [lo, hi],
        "window_s": [round(float(times[lo - 1]), 2), round(float(times[hi - 1]), 2)]
        if n
        else [],
        "flow_ps": round(flow, 4) if flow is not None else None,
        "specific_flow": round(flow / width_m, 4) if flow is not None else None,
        "crossing_times_s": [round(float(t), 2) for t in times],
        "pedpy": pedpy.__version__,
    }
