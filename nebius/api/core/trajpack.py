"""Lossless delta coding of `traj.bin` for project packs.

Same frame layout as `traj.bin` ([u32 n][u16 ids][i16 x][i16 y][u8 floor][pad]), but x and y
hold each person's movement since their previous frame (int16, wrapping). Steps are small, so
LZMA compresses packs several times better; `decode` restores the original bytes exactly.
"""

from __future__ import annotations

from typing import Any

import numpy as np

DELTA_NAME = "traj.delta.bin"


def _code(data: bytes, index: dict[str, Any], decode: bool) -> bytes:
    out = bytearray(data)
    prev_x = np.zeros(65536, dtype=np.int16)
    prev_y = np.zeros(65536, dtype=np.int16)
    for off in index["offsets"]:
        n = int(np.frombuffer(data, dtype="<u4", count=1, offset=off)[0])
        if n == 0:
            continue
        ids = np.frombuffer(data, dtype="<u2", count=n, offset=off + 4)
        xs = np.frombuffer(data, dtype="<i2", count=n, offset=off + 4 + 2 * n)
        ys = np.frombuffer(data, dtype="<i2", count=n, offset=off + 4 + 4 * n)
        with np.errstate(over="ignore"):
            if decode:
                nx = (prev_x[ids] + xs).astype(np.int16)
                ny = (prev_y[ids] + ys).astype(np.int16)
                prev_x[ids], prev_y[ids] = nx, ny
            else:
                nx = (xs - prev_x[ids]).astype(np.int16)
                ny = (ys - prev_y[ids]).astype(np.int16)
                prev_x[ids], prev_y[ids] = xs, ys
        out[off + 4 + 2 * n : off + 4 + 4 * n] = nx.astype("<i2").tobytes()
        out[off + 4 + 4 * n : off + 4 + 6 * n] = ny.astype("<i2").tobytes()
    return bytes(out)


def encode(traj: bytes, index: dict[str, Any]) -> bytes:
    """`traj.bin` → delta-coded bytes (same length)."""
    return _code(traj, index, decode=False)


def decode(delta: bytes, index: dict[str, Any]) -> bytes:
    """Delta-coded bytes → the original `traj.bin`."""
    return _code(delta, index, decode=True)


def coarsen(traj: bytes, index: dict[str, Any], factor: int) -> tuple[bytes, dict[str, Any]]:
    """Store positions in steps of `factor × scale` (packs only; 6 cm is invisible on screen)."""
    if factor <= 1:
        return traj, index
    out = bytearray(traj)
    for off in index["offsets"]:
        n = int(np.frombuffer(traj, dtype="<u4", count=1, offset=off)[0])
        for k in (1, 2):
            a = np.frombuffer(traj, dtype="<i2", count=n, offset=off + 4 + 2 * k * n)
            q = np.round(a.astype(np.int32) / factor).astype("<i2")
            out[off + 4 + 2 * k * n : off + 4 + 2 * (k + 1) * n] = q.tobytes()
    return bytes(out), {**index, "scale": index["scale"] * factor}
