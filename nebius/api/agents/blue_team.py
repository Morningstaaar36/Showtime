"""Blue team: fixes for an attack, as a validated venue patch and/or operational measures."""

from __future__ import annotations

import json
from types import GenericAlias
from typing import Any, Literal, cast

from pydantic import BaseModel, Field, create_model

from api.agents.base import AgentDef, AgentEnv, audit_decision, call_agent
from api.agents.context import event_union, events_doc, ids_line, op_union, ops_doc, venue_summary
from api.core.extensions import Registry
from api.core.plan import PlanError, apply_fix_bundle
from api.core.venue_ops import PatchError
from api.models import Attack, Fix, RunResult, Venue
from api.models.plan import ObjectConstraint, PlanAction

FIX_OPS = {"add_exit", "resize", "add_barrier_line", "move", "remove_obstacle"}
FIX_EVENTS = {"staggered_release", "marshal_redirect", "one_way"}


class BlueTeamBase(BaseModel):
    """Static stand-in for the dynamic output model."""

    fixes: list[dict[str, Any]] = Field(default_factory=list)


BLUE_TEAM_AGENT = AgentDef(
    name="blue_team",
    role="main",
    prompt_file="blue_team.md",
    output_model=BlueTeamBase,
    temperature=0.2,
    max_tokens=2800,
    description="Proposes fixes that are re-simulated.",
)


def _model(registry: Registry, n: int) -> type[BaseModel]:
    events = FIX_EVENTS & set(registry.keys("ScenarioEvent"))
    draft = create_model(
        "FixDraft",
        title=(str, Field(max_length=90)),
        ops=(
            GenericAlias(list, op_union(registry, FIX_OPS)),
            Field(default_factory=list, max_length=3),
        ),
        operational=(
            GenericAlias(list, event_union(registry, events)),
            Field(default_factory=list, max_length=3),
        ),
        actions=(list[PlanAction], Field(default_factory=list, max_length=3)),
        replace_actions=(list[PlanAction], Field(default_factory=list, max_length=3)),
        remove_action_ids=(list[str], Field(default_factory=list, max_length=3)),
        new_objects=(dict[str, ObjectConstraint], Field(default_factory=dict)),
        cost_label=(Literal["low", "medium", "high"], "medium"),
        rationale=(str, Field(default="", max_length=260)),
    )
    return create_model(
        "BlueTeamOut", fixes=(GenericAlias(list, draft), Field(min_length=0, max_length=n))
    )


def check_fix(
    registry: Registry,
    venue: Venue,
    ops: list[dict[str, Any]],
    operational: list[dict[str, Any]],
    *,
    actions: list[dict[str, Any]] | None = None,
    replace_actions: list[dict[str, Any]] | None = None,
    remove_action_ids: list[str] | None = None,
    new_objects: dict[str, Any] | None = None,
) -> list[str]:
    """A fix must apply cleanly, keep the stage and every exit at least as wide, keep people."""
    problems: list[str] = []
    if not (ops or operational or actions or replace_actions or remove_action_ids):
        return ["a fix needs at least one edit or one operational measure"]
    widths = {e.id: e.width_m for f in venue.floors for e in f.exits}
    for o in ops:
        if (
            o.get("op") == "resize"
            and o.get("target") in widths
            and (o.get("width_m") or 0) < widths[o["target"]]
        ):
            problems.append(f"resize must not make exit {o['target']} narrower")
        if o.get("op") == "resize" and o.get("target") not in widths:
            problems.append("only exits may be resized by a fix")
    try:
        fix = Fix.model_validate(
            {
                "fix_id": "validation",
                "for_attack": "validation",
                "title": "Candidate",
                "patch": {"ops": ops},
                "operational": operational,
                "actions": actions or [],
                "replace_actions": replace_actions or [],
                "remove_action_ids": remove_action_ids or [],
                "new_objects": new_objects or {},
            }
        )
        for action in [*fix.actions, *fix.replace_actions]:
            if action.event is not None and action.event.type not in FIX_EVENTS:
                problems.append(f"unsupported fix action {action.event.type}")
        target = apply_fix_bundle(venue, fix, registry)
        if target.total_people() != venue.total_people():
            problems.append("a fix must preserve the number of people")
        stages = {o.id for f in venue.floors for o in f.obstacles if o.kind == "stage"}
        if not stages <= set(target.all_ids()):
            problems.append("a fix must preserve the stage")
    except (PatchError, PlanError, ValueError) as exc:
        problems.extend(getattr(exc, "problems", [str(exc)]))
    return problems


def _result_brief(r: RunResult) -> str:
    m = r.metrics
    per = ", ".join(f"{p.exit_id}: {p.people} people" for p in m.per_exit)
    hs = "; ".join(
        f"{h.peak_density_ppm2} people/m2 near {h.near or 'open floor'} at {h.t_s:.0f} s"
        for h in r.hotspots[:3]
    )
    return (
        f"evacuation time 95%: {m.evac_time_p95_s} s; peak density {m.peak_density_ppm2} "
        f"people/m2; time above danger {m.time_above_danger_s} s; still inside "
        f"{m.agents_not_evacuated}. Exit use: {per}. Hotspots: {hs or 'none'}."
    )


async def blue_team(
    env: AgentEnv,
    registry: Registry,
    venue: Venue,
    attack: Attack,
    result: RunResult,
    n: int,
    id_prefix: str,
) -> list[Fix]:
    """Ask for up to n fixes for one attack; invalid fixes are discarded."""
    model = _model(registry, n)
    events = FIX_EVENTS & set(registry.keys("ScenarioEvent"))

    def problems_of(d: Any) -> list[str]:
        return check_fix(
            registry,
            venue,
            [o.model_dump(exclude_none=True) for o in d.ops],
            [e.model_dump(exclude_none=True) for e in d.operational],
            actions=[a.model_dump(mode="json") for a in d.actions],
            replace_actions=[a.model_dump(mode="json") for a in d.replace_actions],
            remove_action_ids=d.remove_action_ids,
            new_objects={k: v.model_dump(mode="json") for k, v in d.new_objects.items()},
        )

    def validate(out: Any) -> list[str]:
        probs: list[str] = []
        for i, d in enumerate(out.fixes):
            probs.extend(f"fix {i + 1}: {x}" for x in problems_of(d))
        return probs

    values = {
        "venue": venue_summary(venue),
        "ids": ids_line(venue),
        "attack": json.dumps(
            {"title": attack.title, "events": [e.model_dump() for e in attack.events]}
        ),
        "result": _result_brief(result),
        "ops": ops_doc(registry, FIX_OPS),
        "events": events_doc(registry, events),
        "n": str(n),
    }
    call = await call_agent(
        env,
        BLUE_TEAM_AGENT,
        values,
        f"Propose {n} different fixes for this attack.",
        output_model=model,
        validate=validate,
        summarize=lambda o: "; ".join(f.title for f in cast(Any, o).fixes)[:300],
    )
    fixes: list[Fix] = []
    for d in cast(Any, call.output).fixes if call.output else []:
        probs = problems_of(d)
        if probs:
            audit_decision(env, "blue_team", "discarded fix", {"title": d.title, "problems": probs})
            continue
        ops: list[dict[str, Any]] = []
        for o in d.ops:
            od = o.model_dump(exclude_none=True)
            if od not in ops:
                ops.append(od)
        fixes.append(
            Fix.model_validate(
                {
                    "fix_id": f"{id_prefix}{len(fixes) + 1}",
                    "for_attack": attack.attack_id,
                    "title": d.title.strip()[:90],
                    "patch": {"ops": ops},
                    "operational": [e.model_dump(exclude_none=True) for e in d.operational],
                    "actions": [a.model_dump(mode="json") for a in d.actions],
                    "replace_actions": [a.model_dump(mode="json") for a in d.replace_actions],
                    "remove_action_ids": d.remove_action_ids,
                    "new_objects": {k: v.model_dump(mode="json") for k, v in d.new_objects.items()},
                    "rationale": d.rationale.strip(),
                    "cost_label": d.cost_label,
                }
            )
        )
    return fixes
