"""Screening wind check for a ballasted temporary stage roof (section 10.7).

A Pynite 3D frame (legs + roof beams + bracing) is loaded with
  - lateral wind on vertical surfaces: F = q·G·Cf·A_vertical
  - uplift on the roof:                U = q·G·C_uplift·A_roof
with the ASCE 7 velocity pressure q = 0.613·Kz·Kzt·Kd·V² (N/m², V in m/s).
Because the model is linear, reactions scale with V², so the gust speed at which
uplift, sliding or overturning demand equals the ballast capacity is solved exactly.
This is a screening estimate, not a structural design.
"""

from __future__ import annotations

import math
from typing import Any

from pydantic import BaseModel

from api.models import StageParams

G_ACC = 9.81


class WindAssumptions(BaseModel):
    """Coefficients used by the check (all shown to the user)."""

    kz: float = 1.0  # exposure C, ~10-12 m height
    kzt: float = 1.0  # flat site
    kd: float = 0.85  # directionality (ASCE 7)
    gust_factor: float = 0.85  # rigid structure
    uplift_coeff: float = 0.8  # net roof uplift coefficient
    roof_dead_kn_m2: float = 0.25  # roof self-weight
    roof_edge_depth_m: float = 1.0  # vertical face of the roof edge


class StageCheckResult(BaseModel):
    """Wind limit and the check that governs it."""

    v_limit_ms: float
    governing: str  # uplift | sliding | overturning
    limits_ms: dict[str, float]
    wind_direction: str
    assumptions: list[str]
    label: str = "screening estimate"
    formula: str = "q = 0.613·Kz·Kzt·Kd·V²"


def _frame(stage: StageParams, a: WindAssumptions, direction: str) -> dict[str, Any]:
    from Pynite import FEModel3D  # imported lazily: heavy

    n_per_row = max(2, stage.legs // 2)
    w, d, h = stage.width_m, stage.depth_m, stage.roof_height_m
    m = FEModel3D()
    m.add_material("steel", 200e9, 77e9, 0.3, 7850)
    m.add_section("leg", 4.0e-3, 2.0e-5, 2.0e-5, 4.0e-5)
    m.add_section("beam", 3.0e-3, 1.5e-5, 1.5e-5, 3.0e-5)
    m.add_section("brace", 1.0e-3, 1.0e-6, 1.0e-6, 2.0e-6)
    bases: list[str] = []
    tops: list[str] = []
    xs = [w * i / (n_per_row - 1) for i in range(n_per_row)]
    for row, y in enumerate((0.0, d)):
        for i, x in enumerate(xs):
            b, t = f"B{row}{i}", f"T{row}{i}"
            m.add_node(b, x, y, 0.0)
            m.add_node(t, x, y, h)
            m.def_support(b, True, True, True, False, False, False)
            m.add_member(f"L{row}{i}", b, t, "steel", "leg")
            bases.append(b)
            tops.append(t)
            if i > 0:
                m.add_member(f"RB{row}{i}", f"T{row}{i - 1}", t, "steel", "beam")
                m.add_member(
                    f"XB{row}{i}", f"B{row}{i - 1}", t, "steel", "brace", tension_only=False
                )
    for i in range(n_per_row):
        m.add_member(f"CB{i}", f"T0{i}", f"T1{i}", "steel", "beam")
        m.add_member(f"XS{i}", f"B0{i}", f"T1{i}", "steel", "brace")

    q1 = 0.613 * a.kz * a.kzt * a.kd  # N/m² per (m/s)²
    if direction == "front":
        area_lat = stage.banner_area_m2 + stage.width_m * a.roof_edge_depth_m
        axis = "FY"
    else:
        area_lat = (
            stage.banner_area_m2 * (stage.depth_m / stage.width_m)
            + stage.depth_m * a.roof_edge_depth_m
        )
        axis = "FX"
    f_lat = q1 * a.gust_factor * stage.force_coeff * area_lat
    f_up = q1 * a.gust_factor * a.uplift_coeff * stage.roof_area_m2
    dead = a.roof_dead_kn_m2 * 1000.0 * stage.roof_area_m2
    for t in tops:
        m.add_node_load(t, axis, f_lat / len(tops), case="W")
        m.add_node_load(t, "FZ", f_up / len(tops), case="W")
        m.add_node_load(t, "FZ", -dead / len(tops), case="D")
    m.add_load_combo("W", {"W": 1.0})
    m.add_load_combo("D", {"D": 1.0})
    m.analyze_linear(check_stability=True)
    rz_w = [m.nodes[b].RxnFZ["W"] for b in bases]
    rz_d = [m.nodes[b].RxnFZ["D"] for b in bases]
    rh_w = [math.hypot(m.nodes[b].RxnFX["W"], m.nodes[b].RxnFY["W"]) for b in bases]
    return {
        "rz_w": rz_w,
        "rz_d": rz_d,
        "rh_w": rh_w,
        "f_lat": f_lat,
        "f_up": f_up,
        "dead": dead,
        "lever": d if direction == "front" else w,
        "h": h,
    }


def _limits(stage: StageParams, r: dict[str, Any]) -> dict[str, float]:
    wb = stage.ballast_kg_per_leg * G_ACC
    mu = stage.friction_coeff
    out: dict[str, float] = {}
    # uplift: each leg's tension must stay below its ballast weight
    v2 = [(wb + rd) / -rw for rw, rd in zip(r["rz_w"], r["rz_d"], strict=True) if rw < -1e-9]
    if v2:
        out["uplift"] = math.sqrt(max(min(v2), 0.0))
    # sliding: total horizontal force vs friction on total normal force
    total_n = stage.legs * wb + sum(r["rz_d"])
    denom = sum(r["rh_w"]) - mu * sum(r["rz_w"])
    if denom > 1e-9:
        out["sliding"] = math.sqrt(max(mu * total_n / denom, 0.0))
    # overturning about the leeward base line
    m_res = (stage.legs * wb + r["dead"]) * r["lever"] / 2.0
    m_ot = r["f_lat"] * r["h"] + r["f_up"] * r["lever"] / 2.0
    if m_ot > 1e-9:
        out["overturning"] = math.sqrt(m_res / m_ot)
    return out


def check_stage(stage: StageParams, a: WindAssumptions | None = None) -> StageCheckResult:
    """Gust speed (m/s at 10 m) at which the ballasted stage roof first fails a check."""
    a = a or WindAssumptions()
    best: tuple[float, str, str, dict[str, float]] | None = None
    for direction in ("front", "side"):
        lim = _limits(stage, _frame(stage, a, direction))
        if not lim:
            continue
        gov = min(lim, key=lambda k: lim[k])
        if best is None or lim[gov] < best[0]:
            best = (lim[gov], gov, direction, lim)
    assert best is not None, "no wind check produced a limit"
    v, gov, direction, lim = best
    assumptions = [
        f"Velocity pressure q = 0.613·Kz·Kzt·Kd·V² with Kz={a.kz}, Kzt={a.kzt}, Kd={a.kd} "
        "(ASCE 7 form).",
        f"Gust factor G={a.gust_factor}; lateral force coefficient Cf={stage.force_coeff}; "
        f"net roof uplift coefficient {a.uplift_coeff}.",
        f"Vertical area: banners {stage.banner_area_m2:.0f} m² + roof edge "
        f"{a.roof_edge_depth_m:.1f} m deep; roof area {stage.roof_area_m2:.0f} m².",
        f"Ballast {stage.ballast_kg_per_leg:,.0f} kg on each of {stage.legs} legs; base friction "
        f"μ={stage.friction_coeff}; roof self-weight {a.roof_dead_kn_m2} kN/m².",
        "Linear frame with pinned, unanchored bases; wind from the front and the side.",
    ]
    return StageCheckResult(
        v_limit_ms=round(v, 2),
        governing=gov,
        limits_ms={k: round(x, 2) for k, x in lim.items()},
        wind_direction=direction,
        assumptions=assumptions,
    )
