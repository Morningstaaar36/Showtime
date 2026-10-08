"""Pack coding of trajectories: delta coding is exact; coarsening keeps positions within a step."""

from __future__ import annotations

import struct

import numpy as np

from api.core import trajpack


def _traj(frames: list[list[tuple[int, int, int]]]) -> tuple[bytes, dict[str, object]]:
    buf = bytearray()
    offsets = []
    for f in frames:
        offsets.append(len(buf))
        n = len(f)
        buf += struct.pack("<I", n)
        buf += np.array([p[0] for p in f], "<u2").tobytes()
        buf += np.array([p[1] for p in f], "<i2").tobytes()
        buf += np.array([p[2] for p in f], "<i2").tobytes()
        buf += bytes(n)
        buf += bytes((4 - len(buf) % 4) % 4)
    return bytes(buf), {
        "offsets": offsets,
        "scale": 0.02,
        "times": [0.5 * i for i in range(len(frames))],
    }


def test_delta_roundtrip_is_exact_with_reordering_and_exits() -> None:
    raw, ix = _traj(
        [
            [(1, 100, -50), (2, 32000, -32000)],
            [(2, -32000, 32000), (1, 101, -49), (3, 5, 5)],
            [(3, 7, 4)],
            [],
        ]
    )
    enc = trajpack.encode(raw, ix)
    assert len(enc) == len(raw) and enc != raw
    assert trajpack.decode(enc, ix) == raw


def test_coarsen_scales_index_and_stays_within_half_a_step() -> None:
    raw, ix = _traj([[(1, 100, -50), (2, 301, 7)]])
    out, ix2 = trajpack.coarsen(raw, ix, 3)
    assert ix2["scale"] == ix["scale"] * 3
    xs = np.frombuffer(out, "<i2", 2, 4 + 4)
    orig = np.frombuffer(raw, "<i2", 2, 4 + 4)
    assert np.all(np.abs(xs * 3 - orig) <= 1.5)
