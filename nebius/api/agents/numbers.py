"""Number check (hard rule 3): every number in agent prose must match a computed value."""

from __future__ import annotations

import math
import re
from typing import Any

NUM_RE = re.compile(r"(?<![\w.:/#-])(\d{1,3}(?:,\d{3})+|\d+)(?:\.(\d+))?(?![\w:/])")
TIME_RE = re.compile(r"\b([01]?\d|2[0-3]):([0-5]\d)\b")
SMALL_INT_MAX = 10  # counts in prose ("two exits", "3 fixes") are allowed


def _walk(obj: Any, out: set[float], key: str = "") -> None:
    if isinstance(obj, bool) or obj is None:
        return
    if isinstance(obj, int | float):
        v = float(obj)
        if math.isfinite(v):
            out.add(v)
            out.add(round(v))
            out.add(round(v, 1))
            out.add(round(v, 2))
            if key.endswith("_s") and abs(v) >= 60:  # seconds also quoted as minutes
                out.add(round(v / 60, 1))
                out.add(float(round(v / 60)))
        return
    if isinstance(obj, dict):
        for k, v in obj.items():
            _walk(v, out, str(k))
    elif isinstance(obj, list | tuple):
        for v in obj:
            _walk(v, out, key)
    elif isinstance(obj, str):
        for m in NUM_RE.finditer(obj):
            out.add(_to_float(m))


def _to_float(m: re.Match[str]) -> float:
    whole = m.group(1).replace(",", "")
    frac = m.group(2)
    return float(f"{whole}.{frac}") if frac else float(whole)


def allowed_numbers(data: Any) -> set[float]:
    """Every number in `data` (nested), with common rounding variants."""
    out: set[float] = set()
    _walk(data, out)
    return out


def allowed_times(data: Any) -> set[str]:
    """HH:MM strings found in `data` (e.g. countdown times)."""
    found: set[str] = set()

    def walk(o: Any) -> None:
        if isinstance(o, str):
            for m in TIME_RE.finditer(o):
                found.add(f"{int(m.group(1)):02d}:{m.group(2)}")
        elif isinstance(o, dict):
            for v in o.values():
                walk(v)
        elif isinstance(o, list | tuple):
            for v in o:
                walk(v)

    walk(data)
    return found


def check_numbers(text: str, allowed: set[float], times: set[str] | None = None) -> list[str]:
    """Numbers in `text` that do not match any allowed value (empty list = pass)."""
    bad: list[str] = []
    times = times or set()
    stripped = text
    for m in TIME_RE.finditer(text):
        hhmm = f"{int(m.group(1)):02d}:{m.group(2)}"
        if hhmm not in times:
            bad.append(m.group(0))
        stripped = stripped.replace(m.group(0), " ")
    for m in NUM_RE.finditer(stripped):
        v = _to_float(m)
        if v.is_integer() and v <= SMALL_INT_MAX:
            continue
        if any(abs(v - a) <= max(0.051, 0.006 * abs(a)) for a in allowed):
            continue
        bad.append(m.group(0))
    return bad
