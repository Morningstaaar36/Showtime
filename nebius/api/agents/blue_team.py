"""Blue team: fixes for an attack, as a validated venue patch and/or operational measures."""

from __future__ import annotations

import json
from typing import Any, Literal

from pydantic import BaseModel, Field, create_model

from api.agents.base import AgentDef, AgentEnv, audit_decision, call_agent
from api.agents.context import event_union, events_doc, ids_line, op_union, ops_doc, venue_summary
from api.core.extensions import Registry
from api.core.venue_ops import PatchError, apply_patch
from api.models import Attack, Fix, RunResult, Venue, VenuePatch

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
    max_tokens=1400,
    description="Proposes fixes that are re-simulated.",
)


def _model(registry: Registry, n: int) -> type[BaseModel]:
    events = FIX_EVENTS & set(registry.keys("ScenarioEvent"))
    draft = create_model(
        "FixDraft",
        title=(str, Field(max_length=90)),
        ops=(list[op_union(registry, FIX_OPS)], Field(default_factory=list, max_length=3)),  # type: ignore[valid-type]
        operational=(
            list[event_union(registry, events)],
            Field(default_factory=list, max_length=3),
        ),  # type: ignore[valid-type]
        cost_label=(Literal["low", "medium", "high"], "medium"),
        rationale=(str, Field(default="", max_length=260)),
    )
    return create_model("BlueTeamOut", fixes=(list[draft], Field(min_length=1, max_length=n)))  # type: ignore[valid-type]


def check_fix(
    registry: Registry, venue: Venue, ops: list[dict[str, Any]], operational: list[dict[str, Any]]
) -> list[str]:
    """A fix must apply cleanly, keep the stage and every exit at least as wide, keep people."""
    problems: list[str] = []
    if not ops and not operational:
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
    target = venue
    if ops:
        try:
            target = apply_patch(venue, VenuePatch.model_validate({"ops": ops}), registry).venue
            if target.total_people() < venue.total_people():
                problems.append("a fix must not reduce the number of people")
        except PatchError as exc:
            problems.extend(exc.problems)
    # measures may refer to exits the same fix adds, so check them on the patched venue
    for e in operational:
        if not registry.has("ScenarioEvent", e.get("type", "")):
            problems.append(f"unknown measure {e.get('type')}")
            continue
        spec = registry.event(e["type"])
        problems.extend(spec.validate_refs(target, spec.params_model.model_validate(e)))
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
        summarize=lambda o: "; ".join(f.title for f in o.fixes)[:300],
    )
    fixes: list[Fix] = []
    for d in call.output.fixes if call.output else []:
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
                    "rationale": d.rationale.strip(),
                    "cost_label": d.cost_label,
                }
            )
        )
    return fixes
