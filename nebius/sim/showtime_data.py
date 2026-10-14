"""Read one run's data inside a code sandbox (`import showtime_data as sd`).

Analysis scripts (AI- or user-written) use these helpers instead of opening files:

- `load_trajectories(every_s=None)` -> DataFrame [t, id, x, y, floor]: every person's position
  (metres) at every stored time `t` (seconds); `every_s` keeps one frame per that many seconds
- `load_density()` -> (array [time, floor, ny, nx] in people per m2, index dict with `times`,
  `origin`, `cell_m`, `floors`, `warn`, `danger`)
- `exits()` -> DataFrame [id, name, floor, x, y, width_m, blocked]
- `zones()` -> DataFrame [id, name, floor, x, y, area_m2, people]
- `people_near(exit_id, radius_m=3.0)` -> DataFrame [t, people]: people within that distance
  of an exit's centre at each time (a simple queue measure)
- `result()` -> dict: the run's result.json (metrics, per-exit totals, hotspots)
- `venue()` -> dict: the venue as simulated

The files are the run's artifacts (formats in sim/metrics.py), read-only in `SHOWTIME_WORK`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


class DataMissing(Exception):
    """The run does not have this kind of data (e.g. an instant estimate has no trajectories)."""


def _work() -> Path:
    return Path(os.environ.get("SHOWTIME_WORK", "/work"))


def _file(name: str, what: str) -> Path:
    p = _work() / name
    if not p.is_file():
        raise DataMissing(f"This run has no {what} ({name} is missing).")
    return p


def _json(name: str, what: str) -> Any:
    return json.loads(_file(name, what).read_text())


def result() -> dict[str, Any]:
    """The run's result.json."""
    return dict(_json("result.json", "result"))


def venue() -> dict[str, Any]:
    """The venue as simulated (venue.json)."""
    return dict(_json("venue.json", "venue"))


def _centre(polygon: list[list[float]]) -> tuple[float, float, float]:
    """(x, y, area) of a polygon (area-weighted centroid; vertex mean if degenerate)."""
    pts = np.asarray(polygon, dtype=float)
    if len(pts) < 3:
        m = pts.mean(axis=0) if len(pts) else np.zeros(2)
        return float(m[0]), float(m[1]), 0.0
    x, y = pts[:, 0], pts[:, 1]
    xn, yn = np.roll(x, -1), np.roll(y, -1)
    cross = x * yn - xn * y
    a = cross.sum() / 2
    if abs(a) < 1e-9:
        return float(x.mean()), float(y.mean()), 0.0
    cx = ((x + xn) * cross).sum() / (6 * a)
    cy = ((y + yn) * cross).sum() / (6 * a)
    return float(cx), float(cy), float(abs(a))


def exits() -> pd.DataFrame:
    """One row per exit: id, name (its label, else the id), floor, centre x/y, width, blocked."""
    rows = []
    for f in venue().get("floors", []):
        for e in f.get("exits", []):
            x, y, _ = _centre(e["polygon"])
            rows.append(
                {
                    "id": e["id"],
                    "name": e.get("label") or e["id"],
                    "floor": f["floor_id"],
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "width_m": e.get("width_m"),
                    "blocked": bool(e.get("blocked", False)),
                }
            )
    return pd.DataFrame(rows, columns=["id", "name", "floor", "x", "y", "width_m", "blocked"])


def zones() -> pd.DataFrame:
    """One row per crowd zone: id, name, floor, centre x/y, area in m2, people at the start."""
    rows = []
    for f in venue().get("floors", []):
        for z in f.get("zones", []):
            x, y, area = _centre(z["polygon"])
            rows.append(
                {
                    "id": z["id"],
                    "name": z.get("label") or z["id"],
                    "floor": f["floor_id"],
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "area_m2": round(area, 1),
                    "people": int(z.get("people", 0)),
                }
            )
    return pd.DataFrame(rows, columns=["id", "name", "floor", "x", "y", "area_m2", "people"])


def load_trajectories(every_s: float | None = None) -> pd.DataFrame:
    """Positions of everyone over time: columns t (s), id, x, y (m), floor (floor id)."""
    index = _json("traj_index.json", "trajectories")
    data = _file("traj.bin", "trajectories").read_bytes()
    ox, oy = index["origin"]
    scale = float(index["scale"])
    floors = list(index.get("floors") or ["F0"])
    parts: list[pd.DataFrame] = []
    next_t = -1e9
    for t, off in zip(index["times"], index["offsets"], strict=False):
        if every_s and t + 1e-6 < next_t:
            continue
        next_t = t + every_s if every_s else next_t
        n = int(np.frombuffer(data, dtype="<u4", count=1, offset=off)[0])
        if n == 0:
            continue
        ids = np.frombuffer(data, dtype="<u2", count=n, offset=off + 4)
        xs = np.frombuffer(data, dtype="<i2", count=n, offset=off + 4 + 2 * n)
        ys = np.frombuffer(data, dtype="<i2", count=n, offset=off + 4 + 4 * n)
        fl = np.frombuffer(data, dtype="u1", count=n, offset=off + 4 + 6 * n)
        parts.append(
            pd.DataFrame(
                {
                    "t": np.full(n, float(t)),
                    "id": ids.astype(np.int32),
                    "x": np.round(ox + xs.astype(np.float64) * scale, 2),
                    "y": np.round(oy + ys.astype(np.float64) * scale, 2),
                    "floor": [floors[i] if i < len(floors) else str(i) for i in fl],
                }
            )
        )
    if not parts:
        return pd.DataFrame(columns=["t", "id", "x", "y", "floor"])
    return pd.concat(parts, ignore_index=True)


def load_density() -> tuple[np.ndarray, dict[str, Any]]:
    """Density grid over time in people per m2: array [time, floor, ny, nx] and its index."""
    index = dict(_json("density_index.json", "density grid"))
    raw = np.frombuffer(_file("density.bin", "density grid").read_bytes(), dtype=np.uint8)
    shape = tuple(int(v) for v in index.get("shape") or [0, 0, 0, 0])
    arr = raw.reshape(shape).astype(np.float32) * float(index.get("scale", 0.05))
    index.pop("peak_map", None)  # large; the array holds the same information
    return arr, index


def leaving_times(every_s: float | None = 1.0) -> pd.DataFrame:
    """When each person was last seen: [id, t_left] in seconds (sorted by time).

    Someone still inside when the run ended is last seen at the end of the run.
    """
    traj = load_trajectories(every_s)
    if traj.empty:
        return pd.DataFrame(columns=["id", "t_left"])
    last = traj.groupby("id", as_index=False)["t"].max().rename(columns={"t": "t_left"})
    return last.sort_values("t_left", ignore_index=True)


def people_near(exit_id: str, radius_m: float = 3.0, every_s: float | None = 1.0) -> pd.DataFrame:
    """How many people are within `radius_m` of an exit's centre at each time: [t, people]."""
    ex = exits()
    row = ex[(ex["id"] == exit_id) | (ex["name"] == exit_id)]
    if row.empty:
        raise DataMissing(f"There is no exit called {exit_id!r}. Exits: {', '.join(ex['id'])}.")
    e = row.iloc[0]
    traj = load_trajectories(every_s)
    if traj.empty:
        return pd.DataFrame(columns=["t", "people"])
    near = traj[
        (traj["floor"] == e["floor"])
        & (np.hypot(traj["x"] - e["x"], traj["y"] - e["y"]) <= radius_m)
    ]
    counts = near.groupby("t").size()
    times = pd.Index(sorted(traj["t"].unique()), name="t")
    out = counts.reindex(times, fill_value=0).rename("people").reset_index()
    out["people"] = out["people"].astype(int)
    return out
