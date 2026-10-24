"""Reusable conformance suites: any plugin implementing an extension point must pass.

Usage from a plugin test:

    from api.tests.conformance.suites import check_patch_op
    check_patch_op(registry, venue, {"op": "my_op", ...})
"""

from __future__ import annotations

from typing import Any

from api.core.extensions import (
    API_VERSION,
    Exporter,
    HazardContext,
    HazardResult,
    HazardSource,
    Registry,
    ReportBundle,
    ScenarioEvent,
    T1Exit,
    T1Group,
    Tier1State,
)
from api.core.venue_ops import apply_patch, venue_hash
from api.models import Venue, VenuePatch


def check_patch_op(registry: Registry, venue: Venue, params: dict[str, Any]) -> Venue:
    """A PatchOp must validate, apply without mutating its input, and undo exactly."""
    assert API_VERSION == "1"
    before_hash = venue_hash(venue)
    snapshot = venue.model_dump_json()
    organizer = getattr(registry.patch_op(params["op"]), "user_only", False)
    result = apply_patch(
        venue, VenuePatch.model_validate({"ops": [params]}), registry, organizer_edit=organizer
    )
    assert venue.model_dump_json() == snapshot, "op mutated its input venue"
    # the hash covers what a simulation sees; metadata ops (event details) change extensions
    changed = venue_hash(result.venue) != before_hash or result.venue.extensions != venue.extensions
    assert changed, "op had no effect"
    undone = apply_patch(
        result.venue, result.inverse, registry, allow_new_errors=True, organizer_edit=True
    )
    assert venue_hash(undone.venue) == before_hash, "inverse did not restore the venue"
    assert undone.venue.extensions == venue.extensions, "inverse did not restore extensions"
    return result.venue


def check_scenario_event(registry: Registry, venue: Venue, params: dict[str, Any]) -> None:
    """A ScenarioEvent must validate its params, check refs and apply a Tier 1 effect."""
    ev: ScenarioEvent = registry.event(params["type"])
    p = ev.params_model.model_validate(params)
    assert ev.validate_refs(venue, p) == [], "valid sample rejected"
    state = Tier1State(
        exits={
            e.id: T1Exit(
                id=e.id,
                floor_id=f.floor_id,
                x=0,
                y=0,
                width_m=e.width_m,
                capacity_pps=1.3 * e.width_m,
            )
            for f in venue.floors
            for e in f.exits
        },
        groups={
            z.id: T1Group(id=z.id, floor_id=f.floor_id, x=0, y=0, people=z.people)
            for f in venue.floors
            for z in f.zones
        },
        walk_speed_mps=1.3,
    )
    ev.tier1_effect(state, p)
    bad = dict(params)
    for key in ("exit_id", "zone_id", "to_exit_id", "floor_id"):
        if key in bad:
            bad[key] = "does_not_exist"
            assert ev.validate_refs(venue, ev.params_model.model_validate(bad)), (
                f"unknown {key} accepted"
            )
            break
    assert ev.label and ev.description


async def check_hazard_source(source: HazardSource, ctx: HazardContext) -> HazardResult | None:
    """A HazardSource returns None or a result with an explanation and a non-negative time."""
    res = await source.evaluate(ctx)
    if res is not None:
        assert res.explanation, "hazard needs an explanation"
        assert res.t_hazard_s is None or res.t_hazard_s >= 0
    return res


def check_exporter(exporter: Exporter, bundle: ReportBundle) -> bytes:
    """An Exporter renders non-empty bytes that carry the disclaimer when textual."""
    out = exporter.render(bundle)
    assert out, "empty export"
    if exporter.media_type.startswith(("text/", "image/svg")):
        assert bundle.disclaimer.encode() in out, "disclaimer missing"
    return out
