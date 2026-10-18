"""Crowd pressure and Fruin level of service from trajectory frames (numpy and scipy only).

Crowd pressure (Helbing, Johansson & Al-Abideen 2007, "Dynamics of crowd disasters: an
empirical study", Phys. Rev. E 75, 046109, arXiv:physics/0701203) is the local density times
the local velocity variance,

    P(r, t) = rho(r, t) * Var_{r,t}(v),

with Gaussian weights f(z) = exp(-|z|^2 / R^2) / (pi R^2) and R = 1 m (their local scale).
Written with weighted sums S0 = sum_j f_j, S1 = sum_j f_j v_j and S2 = sum_j f_j |v_j|^2 it is
P = S0 * (S2/S0 - |S1/S0|^2) = S2 - |S1|^2 / S0 (units 1/s^2). On the 1 m grid the sums are
cloud-in-cell deposits blurred with a Gaussian of sigma = R / sqrt(2), which is the same kernel.
Var_{r,t} also averages over time: stored frames are the mean of P over each 1 s window.

Turbulent crowd motion set in at the 2006 Hajj when P exceeded 0.02/s^2 (paper, Fig. 3c and
text); Yu & Johansson (2007, arXiv:0708.3282) use the same value in simulation. Both measured it
at local densities of about 5.5-10 people/m^2, so pressure is only reported (and a cell only
counts as turbulent) where the density is at least `min_density` (the warning density by
default; see docs/ASSUMPTIONS.md).

Fruin (1971), "Pedestrian Planning and Design", walkway level of service by area per person:
A >= 3.25 m^2, B 2.32-3.25, C 1.39-2.32, D 0.93-1.39, E 0.46-0.93, F < 0.46 m^2 per person.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np
from scipy import ndimage

PRESSURE_R_M = 1.0
TURBULENCE_P = 0.02  # 1/s^2, Helbing et al. (2007)
PRESSURE_SCALE = 0.001  # 1/s^2 per uint8 step in pressure.bin (saturates at 0.255/s^2)
MAX_SPEED = 3.0  # m/s; faster frame-to-frame moves are model sidesteps, not walking
MAX_FRAME_GAP_S = 1.0
LOS_BANDS = ("A", "B", "C", "D", "E", "F")
# Fruin walkway LoS: area per person (m^2) -> density upper bounds of A..E in people/m^2
FRUIN_AREA_M2 = (3.25, 2.32, 1.39, 0.93, 0.46)
FRUIN_EDGES_PPM2 = tuple(1.0 / a for a in FRUIN_AREA_M2)


def frame_velocities(
    prev: tuple[Any, ...], cur: tuple[Any, ...], dt: float
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Velocities of people seen in both frames on the same floor.

    Frames are (ids, xs, ys, floor_index). Returns (x, y, vx, vy, floor) of the current
    positions; people who appear, change floor, jump (model sidestep) or after a long gap are left
    out.
    """
    empty = np.zeros(0)
    if dt <= 0 or dt > MAX_FRAME_GAP_S or len(prev[0]) == 0 or len(cur[0]) == 0:
        return empty, empty, empty, empty, np.zeros(0, dtype=np.uint8)
    kp = np.asarray(prev[0], dtype=np.int64) * 256 + np.asarray(prev[3], dtype=np.int64)
    kc = np.asarray(cur[0], dtype=np.int64) * 256 + np.asarray(cur[3], dtype=np.int64)
    _, ip, ic = np.intersect1d(kp, kc, assume_unique=False, return_indices=True)
    xs, ys = np.asarray(cur[1], dtype=np.float64)[ic], np.asarray(cur[2], dtype=np.float64)[ic]
    vx = (xs - np.asarray(prev[1], dtype=np.float64)[ip]) / dt
    vy = (ys - np.asarray(prev[2], dtype=np.float64)[ip]) / dt
    ok = np.hypot(vx, vy) <= MAX_SPEED
    fl = np.asarray(cur[3])[ic]
    return xs[ok], ys[ok], vx[ok], vy[ok], fl[ok].astype(np.uint8)


def _deposit(
    xs: np.ndarray,
    ys: np.ndarray,
    w: np.ndarray,
    x0: float,
    y0: float,
    nx: int,
    ny: int,
    cell: float,
) -> np.ndarray:
    """Cloud-in-cell deposit of weights w at (x, y) on cell centres, per m^2."""
    out = np.zeros((ny, nx), dtype=np.float64)
    if len(xs) == 0:
        return out
    gx = (xs - x0) / cell - 0.5
    gy = (ys - y0) / cell - 0.5
    ix, iy = np.floor(gx).astype(int), np.floor(gy).astype(int)
    fx, fy = gx - ix, gy - iy
    for dx, dy, wt in (
        (0, 0, (1 - fx) * (1 - fy)),
        (1, 0, fx * (1 - fy)),
        (0, 1, (1 - fx) * fy),
        (1, 1, fx * fy),
    ):
        jx, jy = ix + dx, iy + dy
        ok = (jx >= 0) & (jx < nx) & (jy >= 0) & (jy < ny)
        np.add.at(out, (jy[ok], jx[ok]), (w * wt)[ok])
    return out / (cell * cell)


def weighted_sums(
    xs: np.ndarray,
    ys: np.ndarray,
    vx: np.ndarray,
    vy: np.ndarray,
    x0: float,
    y0: float,
    nx: int,
    ny: int,
    cell: float = 1.0,
    r_m: float = PRESSURE_R_M,
) -> np.ndarray:
    """Gaussian-weighted sums [S0, S1x, S1y, S2] per cell (S0 is people per m^2)."""
    sigma = r_m / math.sqrt(2.0) / cell
    weights = (np.ones(len(xs)), vx, vy, vx * vx + vy * vy)
    return np.stack(
        [
            ndimage.gaussian_filter(
                _deposit(xs, ys, w, x0, y0, nx, ny, cell), sigma, mode="constant"
            )
            for w in weights
        ]
    )


def pressure_from_sums(
    sums: np.ndarray, frames: int = 1, walkable: np.ndarray | None = None
) -> tuple[np.ndarray, np.ndarray]:
    """(density, pressure) from sums pooled over `frames` instants.

    P = (S2 - |S1|^2 / S0) / frames: the weighted variance of every velocity seen near the cell
    during the window, times the mean density. `walkable` (cell walkable fraction smoothed with
    the same kernel) corrects the Gaussian for walls, as the density grid does.
    """
    s0, s1x, s1y, s2 = sums
    with np.errstate(invalid="ignore", divide="ignore"):
        p = np.where(s0 > 1e-9, s2 - (s1x * s1x + s1y * s1y) / np.maximum(s0, 1e-12), 0.0)
    p = np.clip(p, 0.0, None) / max(frames, 1)
    d = s0 / max(frames, 1)
    if walkable is not None:
        norm = np.maximum(walkable, 0.25)
        d, p = d / norm, p / norm
    return d, p


def pressure_field(
    xs: np.ndarray,
    ys: np.ndarray,
    vx: np.ndarray,
    vy: np.ndarray,
    x0: float,
    y0: float,
    nx: int,
    ny: int,
    cell: float = 1.0,
    r_m: float = PRESSURE_R_M,
    walkable: np.ndarray | None = None,
) -> tuple[np.ndarray, np.ndarray]:
    """(density people/m^2, crowd pressure 1/s^2) on the grid for one floor at one instant."""
    sums = weighted_sums(xs, ys, vx, vy, x0, y0, nx, ny, cell, r_m)
    return pressure_from_sums(sums, 1, walkable)


def los_band(density: np.ndarray) -> np.ndarray:
    """Fruin walkway level of service as 0 (A) .. 5 (F) for densities in people/m^2."""
    return np.digitize(np.asarray(density, dtype=np.float64), FRUIN_EDGES_PPM2, right=True)


def los_shares(seconds: np.ndarray) -> dict[str, float]:
    """Share of person-seconds in each band: {"los_share_A": ..., ..., "los_share_F": ...}."""
    total = float(np.sum(seconds))
    return {
        f"los_share_{b}": (round(float(seconds[i]) / total, 4) if total > 0 else 0.0)
        for i, b in enumerate(LOS_BANDS)
    }


class PressureAccumulator:
    """Pressure over 1 s space-time windows, peaks, turbulent time and hotspots.

    Each window pools the weighted sums of all its frames before taking the variance, so the
    variance is over space (Gaussian, R = 1 m) and time (the window), as in Var_{r,t}. Cells whose
    window density is below `min_density` are set to 0: the indicator and its threshold were
    measured in dense crowds, and in a thin crowd different free walking speeds alone would
    exceed it.
    """

    def __init__(
        self,
        n_floors: int,
        nx: int,
        ny: int,
        x0: float,
        y0: float,
        walkable: list[np.ndarray],
        masks: list[np.ndarray],
        threshold: float = TURBULENCE_P,
        min_density: float = 0.0,
        window_s: float = 1.0,
        cell: float = 1.0,
    ) -> None:
        self.n, self.nx, self.ny, self.x0, self.y0, self.cell = n_floors, nx, ny, x0, y0, cell
        sigma = PRESSURE_R_M / math.sqrt(2.0) / cell
        self.walk = [ndimage.gaussian_filter(w, sigma, mode="constant") for w in walkable]
        self.masks = masks
        self.threshold, self.min_density, self.window_s = threshold, min_density, window_s
        shape = (n_floors, ny, nx)
        self._sums = np.zeros((n_floors, 4, ny, nx))
        self._n = 0
        self._next = window_s
        self._last_t: float | None = None
        self.stored: list[np.ndarray] = []
        self.stored_t: list[float] = []
        self.series: list[float] = []
        self.peak_map = np.zeros(shape, dtype=np.float32)
        self.peak_t = np.zeros(shape, dtype=np.float32)
        self.turbulent_s = 0.0

    def add(
        self, t: float, x: np.ndarray, y: np.ndarray, vx: np.ndarray, vy: np.ndarray, fl: np.ndarray
    ) -> None:
        """Add one frame of velocities (from `frame_velocities`)."""
        for fi in range(self.n):
            sel = fl == fi
            if not np.any(sel):
                continue
            self._sums[fi] += weighted_sums(
                x[sel], y[sel], vx[sel], vy[sel], self.x0, self.y0, self.nx, self.ny, self.cell
            )
        self._n += 1
        if t + 1e-6 >= self._next:
            self._flush(t)

    def _flush(self, t: float) -> None:
        if self._n == 0:
            return
        p = np.zeros((self.n, self.ny, self.nx))
        d = np.zeros_like(p)
        for fi in range(self.n):
            df, pf = pressure_from_sums(self._sums[fi], self._n, self.walk[fi])
            d[fi] = np.where(self.masks[fi], df, 0.0)
            p[fi] = np.where(self.masks[fi] & (df >= self.min_density), pf, 0.0)
        span = t - (self._last_t if self._last_t is not None else t - self.window_s)
        if np.any(p >= self.threshold):
            self.turbulent_s += span
        p32 = p.astype(np.float32)
        upd = p32 > self.peak_map
        self.peak_map = np.where(upd, p32, self.peak_map)
        self.peak_t = np.where(upd, np.float32(t), self.peak_t)
        self.stored.append(np.clip(np.round(p / PRESSURE_SCALE), 0, 255).astype(np.uint8))
        self.stored_t.append(round(t, 2))
        self.series.append(round(float(p.max()), 4))
        self._sums[:] = 0.0
        self._n = 0
        self._last_t = t
        while self._next <= t + 1e-6:
            self._next += self.window_s

    def finish(self, t_end: float) -> None:
        """Flush a last partial window."""
        if self._n:
            self._flush(t_end)

    def hotspots(self, floor_ids: list[str], limit: int = 10) -> list[dict[str, Any]]:
        """Connected turbulent cells (1 s pressure at or over the threshold), strongest first."""
        out: list[dict[str, Any]] = []
        for fi, fid in enumerate(floor_ids):
            labels, n = ndimage.label(self.peak_map[fi] >= self.threshold)
            for lab in range(1, n + 1):
                cells = labels == lab
                vals = np.where(cells, self.peak_map[fi], 0)
                iy, ix = np.unravel_index(int(np.argmax(vals)), vals.shape)
                out.append(
                    {
                        "floor_id": fid,
                        "x": round(self.x0 + (ix + 0.5) * self.cell, 2),
                        "y": round(self.y0 + (iy + 0.5) * self.cell, 2),
                        "peak_pressure_per_s2": round(float(vals[iy, ix]), 4),
                        "t_s": round(float(self.peak_t[fi, iy, ix]), 1),
                        "cells": int(cells.sum()),
                    }
                )
        out.sort(key=lambda h: -h["peak_pressure_per_s2"])
        return out[:limit]
