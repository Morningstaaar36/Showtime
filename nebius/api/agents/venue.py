"""Venue agent: plain-language edits → VenuePatch (or clarifying questions)."""

from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field, create_model

from api.agents.base import AgentCall, AgentDef, AgentEnv, call_agent
from api.agents.context import explain_patch, ids_line, op_union, ops_doc, venue_summary
from api.core.extensions import Registry
from api.core.extensions import geometry as geo
from api.core.plan import PlanError
from api.core.venue_ops import PatchError, apply_patch
from api.models import Venue, VenuePatch


class VenueEditBase(BaseModel):
    """Static stand-in for the dynamic output model (used for the AgentSpec registry)."""

    ops: list[dict[str, Any]] = Field(default_factory=list)
    questions: list[str] = Field(default_factory=list)


@lru_cache(maxsize=8)
def _output_model(union: Any) -> type[BaseModel]:
    # `intent` comes first: a one-sentence plan written before the ops guides a small model
    return create_model(
        "VenueEdit",
        intent=(str, Field(default="", max_length=240)),
        ops=(list[union], Field(default_factory=list, max_length=6)),  # type: ignore[valid-type]
        questions=(list[str], Field(default_factory=list, max_length=3)),
    )


VENUE_AGENT = AgentDef(
    name="venue",
    role="main",
    prompt_file="venue.md",
    output_model=VenueEditBase,
    temperature=0.1,
    max_tokens=900,
    description="Turns typed requests into venue edits.",
)


@dataclass
class EditOutcome:
    """Result of an edit request."""

    status: str  # proposed | questions | failed
    patch: VenuePatch | None = None
    questions: list[str] = field(default_factory=list)
    explanation: str = ""
    problems: list[str] = field(default_factory=list)
    call: AgentCall[Any] | None = None


def out_of_bounds(before: Venue, after: Venue) -> list[str]:
    """Changed objects that would stick out of the floor outline by more than 5 %."""
    old = {o.id: o.polygon for f in before.floors for o in f.obstacles}
    old.update({z.id: z.polygon for f in before.floors for z in f.zones})
    problems = []
    for f in after.floors:
        outline = geo.to_polygon(f.walkable)
        # a wall drawn on the outline straddles it by half its thickness: that is not "outside"
        wall_outline = outline.buffer(0.2, join_style="mitre")
        for item in [*f.obstacles, *f.zones]:
            if old.get(item.id) == item.polygon:
                continue
            poly = geo.to_polygon(item.polygon)
            edge = wall_outline if getattr(item, "kind", None) == "wall" else outline
            outside = poly.difference(edge).area
            if poly.area > 0 and outside / poly.area > 0.05:
                problems.append(
                    f"'{item.id}' would extend {outside:.0f} m² beyond the edge of "
                    f"floor {f.floor_id}. Choose a smaller move or another direction, "
                    "or ask the user."
                )
    return problems


def _to_patch(out: Any) -> VenuePatch:
    ops: list[dict[str, Any]] = []
    for o in getattr(out, "ops", []):
        d = o.model_dump(exclude_none=True)
        if d not in ops:  # small models sometimes repeat an op; keep one of each
            ops.append(d)
    return VenuePatch.model_validate({"ops": ops})


async def propose_edit(env: AgentEnv, registry: Registry, venue: Venue, text: str) -> EditOutcome:
    """Ask the venue agent for a patch; validated by a dry run before it is returned."""
    model = _output_model(op_union(registry))
    values = {"venue": venue_summary(venue), "ids": ids_line(venue), "ops": ops_doc(registry)}

    def validate(out: Any) -> list[str]:
        if not out.ops:
            return []
        try:
            res = apply_patch(venue, _to_patch(out), registry)
        except (PatchError, PlanError) as exc:
            return exc.problems
        return out_of_bounds(venue, res.venue)

    def summarize(out: Any) -> str:
        if out.ops:
            return f"{len(out.ops)} edit(s): " + ", ".join(o.op for o in out.ops)
        return "questions: " + " / ".join(out.questions)[:200]

    call = await call_agent(
        env,
        VENUE_AGENT,
        values,
        f'Request: "{text.strip()}"',
        output_model=model,
        validate=validate,
        summarize=summarize,
    )
    out = call.output
    if out is None:
        return EditOutcome(
            status="failed",
            call=call,
            explanation="I couldn't turn that into an edit. Try rephrasing it "
            "with an object id, a direction and a distance.",
            problems=[call.error or "invalid output"],
        )
    if not out.ops:
        qs = list(out.questions) or ["Which object do you mean, and what should change?"]
        return EditOutcome(
            status="questions",
            questions=qs,
            call=call,
            explanation="I need a bit more detail before editing the plan.",
        )
    if call.problems:
        return EditOutcome(
            status="failed",
            call=call,
            problems=call.problems,
            explanation="That edit would break the plan: " + call.problems[0],
        )
    patch = _to_patch(out)
    return EditOutcome(
        status="proposed",
        patch=patch,
        questions=list(out.questions),
        explanation=explain_patch(venue, patch),
        call=call,
    )
