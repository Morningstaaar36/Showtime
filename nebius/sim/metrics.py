"""Metrics and artifacts (section 10.4): density grid, hotspots, RSET, binary trajectories."""

from __future__ import annotations

import json
import math
from pathlib import Path
from typing import Any

import numpy as np
import shapely
from jps_build import free_space, to_poly
from scipy import ndimage
from shapely.geometry import Polygon, box

POS_SCALE = 0.02  # metres per int16 step in traj.bin
DENSITY_SCALE = 0.05  # people/m2 per uint8 step in density.bin
CELL_M = 1.0
SMOOTH_SIGMA = 0.8  # cells
GRID_MARGIN_M = 2


def _grid(venue: dict[str, Any]) -> tuple[float, float, int, int]:
    xs, ys = [], []
    for f in venue["floors"]:
        for x, y in f["walkable"]:
            xs.append(x)
            ys.append(y)
    # 2 m margin so people walking out through door passages stay on the grid
    x0, y0 = math.floor(min(xs)) - GRID_MARGIN_M, math.floor(min(ys)) - GRID_MARGIN_M
    nx = int(math.ceil(max(xs) + GRID_MARGIN_M - x0))
    ny = int(math.ceil(max(ys) + GRID_MARGIN_M - y0))
    return float(x0), float(y0), nx, ny


def _walkable_fraction(floor: dict[str, Any], x0: float, y0: float, nx: int, ny: int) -> np.ndarray:
    free = free_space(floor)
    cells = shapely.box(
        (x0 + np.arange(nx))[None, :].repeat(ny, 0),
        (y0 + np.arange(ny))[:, None].repeat(nx, 1),
        (x0 + np.arange(nx) + CELL_M)[None, :].repeat(ny, 0),
        (y0 + np.arange(ny) + CELL_M)[:, None].repeat(nx, 1),
    )
    return np.asarray(shapely.area(shapely.intersection(cells, free)), dtype=np.float64) / (
        CELL_M * CELL_M
    )


def _merge_frames(
    outputs: list[Any], floor_index: dict[str, int]
) -> tuple[list[float], list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]]:
    """Merge per-floor frames on the shared time grid."""
    by_t: dict[float, list[tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]]] = {}
    for out in outputs:
        fi = floor_index[out.floor_id]
        for t, (ids, xs, ys) in zip(out.frames_t, out.frames, strict=True):
            by_t.setdefault(round(t, 2), []).append(
                (ids, xs, ys, np.full(len(ids), fi, dtype=np.uint8))
            )
    times = sorted(by_t)
    frames = []
    for t in times:
        parts = by_t[t]
        frames.append(tuple(np.concatenate([p[i] for p in parts]) for i in range(4)))
    return times, frames  # type: ignore[return-value]


def write_trajectory(
    work: Path,
    times: list[float],
    frames: list[Any],
    x0: float,
    y0: float,
    floors: list[str],
    bounds: list[float],
) -> int:
    """traj.bin: per frame [u32 count][u16 ids][i16 x][i16 y][u8 floor][pad to 4 bytes]."""
    offsets: list[int] = []
    pos = 0
    with open(work / "traj.bin", "wb") as fh:
        for ids, xs, ys, fl in frames:
            n = len(ids)
            offsets.append(pos)
            xq = np.clip(np.round((xs - x0) / POS_SCALE), -32767, 32767).astype("<i2")
            yq = np.clip(np.round((ys - y0) / POS_SCALE), -32767, 32767).astype("<i2")
            buf = (
                np.asarray([n], dtype="<u4").tobytes()
                + ids.astype("<u2").tobytes()
                + xq.tobytes()
                + yq.tobytes()
                + fl.astype("u1").tobytes()
            )
            pad = (-len(buf)) % 4
            fh.write(buf + b"\0" * pad)
            pos += len(buf) + pad
    (work / "traj_index.json").write_text(
        json.dumps(
            {
                "format": "showtime-traj-v1",
                "times": times,
                "offsets": offsets,
                "bytes": pos,
                "origin": [x0, y0],
                "scale": POS_SCALE,
                "floors": floors,
                "bounds": bounds,
                "max_agents": int(max((len(f[0]) for f in frames), default=0)),
            }
        )
    )
    return pos


def density_and_hotspots(
    work: Path,
    venue: dict[str, Any],
    times: list[float],
    frames: list[Any],
    x0: float,
    y0: float,
    nx: int,
    ny: int,
    warn: float,
    danger: float,
    store_every_s: float = 1.0,
) -> dict[str, Any]:
    """Smoothed density per frame (normalised by walkable area), hotspots and threshold times."""
    floors = venue["floors"]
    frac = [_walkable_fraction(f, x0, y0, nx, ny) for f in floors]
    frac_s = [ndimage.gaussian_filter(fr, SMOOTH_SIGMA, mode="constant") for fr in frac]
    masks = [fr > 0.2 for fr in frac]
    peak_map = np.zeros((len(floors), ny, nx), dtype=np.float32)
    peak_t = np.zeros((len(floors), ny, nx), dtype=np.float32)
    stored: list[np.ndarray] = []
    stored_t: list[float] = []
    next_store = 0.0
    above_danger = above_warn = 0.0
    dts = np.diff(times, append=times[-1] + (times[-1] - times[-2] if len(times) > 1 else 0.25))
    series_peak: list[float] = []
    for k, (_, xs, ys, fl) in enumerate(frames):
        dens = np.zeros((len(floors), ny, nx), dtype=np.float32)
        for fi in range(len(floors)):
            sel = fl == fi
            if not np.any(sel):
                continue
            ix = np.floor((xs[sel] - x0) / CELL_M).astype(int)
            iy = np.floor((ys[sel] - y0) / CELL_M).astype(int)
            ok = (ix >= 0) & (ix < nx) & (iy >= 0) & (iy < ny)
            ix, iy = ix[ok], iy[ok]
            counts = np.zeros((ny, nx), dtype=np.float64)
            np.add.at(counts, (iy, ix), 1.0)
            sm = ndimage.gaussian_filter(counts, SMOOTH_SIGMA, mode="constant")
            d = np.where(masks[fi], sm / np.maximum(frac_s[fi], 0.25), 0.0)
            dens[fi] = d
        fmax = float(dens.max()) if dens.size else 0.0
        series_peak.append(round(fmax, 3))
        if fmax >= danger:
            above_danger += float(dts[k])
        if fmax >= warn:
            above_warn += float(dts[k])
        upd = dens > peak_map
        peak_map = np.where(upd, dens, peak_map)
        peak_t = np.where(upd, times[k], peak_t)
        if times[k] + 1e-6 >= next_store:
            stored.append(np.clip(np.round(dens / DENSITY_SCALE), 0, 255).astype(np.uint8))
            stored_t.append(times[k])
            next_store += store_every_s
    arr = np.stack(stored) if stored else np.zeros((0, len(floors), ny, nx), dtype=np.uint8)
    (work / "density.bin").write_bytes(arr.tobytes())
    (work / "density_index.json").write_text(
        json.dumps(
            {
                "format": "showtime-density-v1",
                "times": stored_t,
                "origin": [x0, y0],
                "cell_m": CELL_M,
                "nx": nx,
                "ny": ny,
                "floors": [f["floor_id"] for f in floors],
                "scale": DENSITY_SCALE,
                "dtype": "uint8",
                "shape": list(arr.shape),
                "warn": warn,
                "danger": danger,
                "peak_series": series_peak[:: max(1, len(series_peak) // 600)],
                "peak_map": [np.round(peak_map[i], 2).tolist() for i in range(len(floors))],
            }
        )
    )

    hotspots: list[dict[str, Any]] = []
    for fi, f in enumerate(floors):
        labels, n = ndimage.label(peak_map[fi] >= warn)
        for lab in range(1, n + 1):
            cells = labels == lab
            vals = np.where(cells, peak_map[fi], 0)
            iy, ix = np.unravel_index(int(np.argmax(vals)), vals.shape)
            pk = float(vals[iy, ix])
            x, y = x0 + ix + 0.5, y0 + iy + 0.5
            hotspots.append(
                {
                    "floor_id": f["floor_id"],
                    "x": round(x, 2),
                    "y": round(y, 2),
                    "peak_density_ppm2": round(pk, 2),
                    "t_s": round(float(peak_t[fi, iy, ix]), 1),
                    "level": "danger" if pk >= danger else "warning",
                    "near": _nearest(f, x, y),
                    "cells": int(cells.sum()),
                }
            )
    hotspots.sort(key=lambda h: -h["peak_density_ppm2"])
    return {
        "peak": float(peak_map.max()) if peak_map.size else 0.0,
        "above_danger_s": above_danger,
        "above_warn_s": above_warn,
        "hotspots": hotspots[:10],
    }


def _nearest(floor: dict[str, Any], x: float, y: float) -> str | None:
    best, best_d = None, math.inf
    pt = shapely.Point(x, y)
    for coll in ("exits", "obstacles"):
        for item in floor.get(coll, []):
            d = to_poly(item["polygon"]).distance(pt)
            if d < best_d:
                best, best_d = item["id"], d
    return best if best_d < 12 else None


def exit_area_density(
    venue: dict[str, Any], times: list[float], frames: list[Any], frame_hz: float
) -> dict[str, float]:
    """PedPy classic density in a 2 m band in front of each exit; returns peak per exit."""
    import pandas as pd
    import pedpy

    out: dict[str, float] = {}
    for fi, f in enumerate(venue["floors"]):
        for e in f.get("exits", []):
            # PedPy needs a convex measurement area: 2 m band in front of the exit
            area = (
                to_poly(e["polygon"])
                .buffer(2.0, join_style="mitre")
                .intersection(to_poly(f["walkable"]))
                .convex_hull
            )
            if area.is_empty or not isinstance(area, Polygon) or area.area < 1.0:
                continue
            rows = []
            for k, (ids, xs, ys, fl) in enumerate(frames):
                sel = (fl == fi) & shapely.contains_xy(area, xs, ys)
                if np.any(sel):
                    rows.append(
                        pd.DataFrame(
                            {"id": ids[sel].astype(int), "frame": k, "x": xs[sel], "y": ys[sel]}
                        )
                    )
            if not rows:
                out[e["id"]] = 0.0
                continue
            traj = pedpy.TrajectoryData(
                data=pd.concat(rows, ignore_index=True), frame_rate=frame_hz
            )
            dens = pedpy.compute_classic_density(
                traj_data=traj, measurement_area=pedpy.MeasurementArea(area)
            )
            out[e["id"]] = round(float(dens["density"].max()), 3)
    return out


def evacuation_metrics(
    outputs: list[Any], people_total: int, venue: dict[str, Any], max_sim_s: float
) -> dict[str, Any]:
    """RSET (p95, max), per-exit flows, evacuated fraction, extrapolated RSET when partial."""
    exits = sorted((t, gid, e) for out in outputs for (t, gid, e) in out.exit_times)
    times = np.asarray([t for t, _, _ in exits], dtype=float)
    evacuated = len(exits)
    not_evac = max(people_total - evacuated, 0)
    p95 = tmax = None
    if people_total > 0 and evacuated >= math.ceil(0.95 * people_total):
        p95 = float(np.sort(times)[math.ceil(0.95 * people_total) - 1])
    if people_total > 0 and evacuated == people_total:
        tmax = float(times.max())
    per_exit: dict[str, list[float]] = {}
    for t, _, e in exits:
        per_exit.setdefault(e, []).append(t)
    rows = []
    for f in venue["floors"]:
        for e in f.get("exits", []):
            ts = per_exit.get(e["id"], [])
            flow = (len(ts) - 1) / (ts[-1] - ts[0]) if len(ts) >= 2 and ts[-1] > ts[0] else 0.0
            rows.append(
                {
                    "exit_id": e["id"],
                    "people": len(ts),
                    "mean_flow_pps": round(flow, 3),
                    "first_s": round(ts[0], 1) if ts else None,
                    "last_s": round(ts[-1], 1) if ts else None,
                }
            )
    extra: dict[str, float] = {
        "evacuated_fraction": round(evacuated / people_total, 4) if people_total else 1.0
    }
    if p95 is None and evacuated and people_total:
        # extrapolate: current total exit flow over the last 30 s of the run
        recent = times[times > times.max() - 30]
        rate = len(recent) / 30.0 if len(recent) > 1 else 0.0
        need = math.ceil(0.95 * people_total) - evacuated
        if rate > 0:
            extra["rset_extrapolated_s"] = round(float(times.max() + need / rate), 1)
    return {
        "p95": p95,
        "max": tmax,
        "evacuated": evacuated,
        "not_evacuated": not_evac,
        "per_exit": rows,
        "extra": extra,
    }


def grid_for(venue: dict[str, Any]) -> tuple[float, float, int, int]:
    """Public wrapper for the shared grid."""
    return _grid(venue)


def bounds_for(venue: dict[str, Any]) -> list[float]:
    """[minx, miny, maxx, maxy] over all floors."""
    b = shapely.union_all([box(*to_poly(f["walkable"]).bounds) for f in venue["floors"]]).bounds
    return [round(v, 3) for v in b]


merge_frames = _merge_frames
