"""Simulator validation: the bottleneck venue, the summary statistics and the shipped exhibit.

`scripts/validate_bottleneck.py` builds one venue per experiment run with `bottleneck_venue`,
simulates it, and writes `api/data/validation.json`; the API serves it with `load_validation`.
"""

from __future__ import annotations

import statistics
from functools import lru_cache
from pathlib import Path

from api.core.settings import ROOT_DIR
from api.models import Exit, Floor, Venue, Zone
from api.models.validation import SimulatorValidation

VALIDATION_PATH = ROOT_DIR / "api" / "data" / "validation.json"

# Assumed initial density in the holding area (persons/m2). The 2006 papers do not state it;
# 3.3 /m2 is the value the same group used for its 2005 bottleneck series (Seyfried et al. 2009).
HOLDING_DENSITY_PPM2 = 3.3
OUTFLOW_DEPTH_M = 1.0  # open area after the bottleneck before the exit (metadata box: y up to l+1)
OUTFLOW_WIDTH_M = 8.0  # metadata bounding box is 8 m wide (x from -4 to 4)


def holding_depth(n_people: int, corridor_w: float, density: float = HOLDING_DENSITY_PPM2) -> float:
    """Depth of the holding area that gives `density` over the corridor width."""
    return round(n_people / (density * corridor_w), 2)


def bottleneck_venue(
    run_name: str,
    b: float,
    length: float,
    n_people: int,
    corridor_w: float,
    distance_m: float,
    density: float = HOLDING_DENSITY_PPM2,
) -> Venue:
    """The experiment in the archive's frame: bottleneck entrance on y = 0, centred on x = 0.

    Corridor `corridor_w` wide in front of the bottleneck; the holding area spans the corridor
    and ends `distance_m` before the entrance; the bottleneck is b x length; behind it an open
    area 8 m x 1 m whose far edge is the exit (so the exit never limits the flow).
    """
    hw, hb = corridor_w / 2, b / 2
    depth = holding_depth(n_people, corridor_w, density)
    y_hold = -(distance_m + depth)
    y_back = y_hold - 0.5
    y_out = length + OUTFLOW_DEPTH_M
    ow = OUTFLOW_WIDTH_M / 2
    walkable = [
        (-hw, y_back),
        (hw, y_back),
        (hw, 0.0),
        (hb, 0.0),
        (hb, length),
        (ow, length),
        (ow, y_out),
        (-ow, y_out),
        (-ow, length),
        (-hb, length),
        (-hb, 0.0),
        (-hw, 0.0),
    ]
    exit_poly = [
        (-ow + 0.2, y_out - 0.4),
        (ow - 0.2, y_out - 0.4),
        (ow - 0.2, y_out - 0.02),
        (-ow + 0.2, y_out - 0.02),
    ]
    zone = [(-hw, y_hold), (hw, y_hold), (hw, -distance_m), (-hw, -distance_m)]
    floor = Floor(
        floor_id="F0",
        name="Bottleneck",
        walkable=walkable,
        exits=[Exit(id="out", polygon=exit_poly, width_m=OUTFLOW_WIDTH_M - 0.4, label="Out")],
        zones=[Zone(id="holding", polygon=zone, people=n_people, label="Holding area")],
    )
    return Venue(
        venue_id=f"validation_{run_name}",
        name=f"Jülich bottleneck 2006 {run_name} (b = {b:g} m)",
        description="Validation venue built from the Jülich archive metadata (DOI 10.34735/ped.2006.2).",
        mode="indoor",
        floors=[floor],
    )


def error_pct(simulated: float, measured: float) -> float:
    """Signed relative error in percent (> 0: the simulator lets people through faster)."""
    return round((simulated - measured) / measured * 100.0, 1)


def summarize(errors: list[float]) -> tuple[float, float]:
    """(median of |error|, mean signed error) in percent."""
    if not errors:
        return 0.0, 0.0
    return (
        round(statistics.median(abs(e) for e in errors), 1),
        round(statistics.fmean(errors), 1),
    )


@lru_cache(maxsize=2)
def _load(path: Path, mtime: float) -> SimulatorValidation:
    return SimulatorValidation.model_validate_json(path.read_text())


def load_validation(path: Path = VALIDATION_PATH) -> SimulatorValidation | None:
    """The shipped exhibit, or None when it has not been generated."""
    if not path.exists():
        return None
    return _load(path, path.stat().st_mtime)
