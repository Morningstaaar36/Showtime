"""Red team: attack scenarios grounded in real crowd incidents.

The model chooses which incident inspires each attack and which events to stage; the
source URL and evidence come from the incident record itself (never from the model).
"""

from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, create_model

from api.agents.base import AgentDef, AgentEnv, audit_decision, call_agent
from api.agents.context import event_union, events_doc, ids_line, venue_summary
from api.core.extensions import IncidentRecord, Registry
from api.models import Attack, RunResult, Venue

ATTACK_EVENTS = {"block_exit", "surge", "slowdown", "counterflow"}
DOI = "https://doi.org/10.5281/zenodo.19483010"


class RedTeamBase(BaseModel):
    """Static stand-in for the dynamic output model."""

    attacks: list[dict[str, Any]] = Field(default_factory=list)


RED_TEAM_AGENT = AgentDef(
    name="red_team",
    role="fast",
    prompt_file="red_team.md",
    output_model=RedTeamBase,
    temperature=0.3,
    max_tokens=1400,
    description="Designs attack scenarios from real incidents.",
)


def _model(registry: Registry, n: int) -> type[BaseModel]:
    draft = create_model(
        "AttackDraft",
        title=(str, Field(max_length=90)),
        incident_row=(int, ...),
        events=(list[event_union(registry, ATTACK_EVENTS)], Field(min_length=1, max_length=3)),  # type: ignore[valid-type]
        rationale=(str, Field(default="", max_length=260)),
    )
    return create_model("RedTeamOut", attacks=(list[draft], Field(min_length=1, max_length=n)))  # type: ignore[valid-type]


def venue_features(venue: Venue, baseline: RunResult | None) -> dict[str, Any]:
    """Facts the red team reasons about (all computed)."""
    people = venue.total_people()
    exits = [e for f in venue.floors for e in f.exits if not e.blocked]
    width = sum(e.width_m for e in exits)
    feats: dict[str, Any] = {
        "mode": venue.mode,
        "people": people,
        "open_exits": len(exits),
        "exit_width_m": round(width, 1),
        "people_per_m_exit": round(people / width) if width else None,
        "narrowest_exit_m": round(min((e.width_m for e in exits), default=0), 1),
        "stairs": len(venue.stairs),
        "floors": len(venue.floors),
        "has_stage": any(o.kind == "stage" for f in venue.floors for o in f.obstacles),
    }
    if baseline is not None and baseline.metrics:
        m = baseline.metrics
        feats["baseline"] = {
            "evac_time_p95_s": m.evac_time_p95_s,
            "peak_density_ppm2": m.peak_density_ppm2,
            "busiest_exit": max(m.per_exit, key=lambda p: p.people).exit_id if m.per_exit else None,
            "hotspot_near": baseline.hotspots[0].near if baseline.hotspots else None,
        }
    return feats


def incident_query(venue: Venue, feats: dict[str, Any]) -> dict[str, Any]:
    """Keywords and settings for searching the incident dataset."""
    kw: dict[str, float] = {"exit": 1.0, "crush": 1.0, "panic": 0.6, "density": 0.6}
    if feats["stairs"]:
        kw["stairs"] = 1.6
    if feats.get("narrowest_exit_m", 9) < 3.5:
        kw.update({"narrow": 1.4, "bottleneck": 1.2, "alley": 1.0})
    if feats["has_stage"]:
        kw.update({"stage": 1.2, "wind": 1.0, "storm": 0.8, "barrier": 0.8, "surge": 1.0})
    if venue.mode == "indoor":
        kw.update({"fire": 1.0, "locked": 1.0, "false_alarm": 0.8, "power": 0.6})
        settings = ["nightclub", "concert", "religious", "school", "indoor", "sports"]
    else:
        kw.update({"gate": 1.2, "counterflow": 1.2, "slope": 0.6, "festival": 1.0})
        settings = ["festival", "street", "concert", "stadium", "sports", "religious"]
    return {"keywords": kw, "settings": settings}


def _incident_lines(rows: list[IncidentRecord]) -> str:
    out = []
    for r in rows:
        name = getattr(r, "name", "") or f"{r.event_type} crowd accident, {r.country}"
        desc = (r.description or "").replace("\n", " ")[:260]
        out.append(
            f"row {r.row_id}: {name} ({r.year}, {r.country}; {r.deaths or 0} deaths). {desc}"
        )
    return "\n".join(out)


def _source_url(r: IncidentRecord) -> str:
    url = (r.source_url or "").strip()
    if url.startswith("http"):
        return url
    return f"{DOI}#row={r.row_id}"


def _evidence(r: IncidentRecord) -> str:
    text = (r.description or "").strip().replace("\n", " ")
    first = text.split(". ")[0]
    return (first if len(first) > 30 else text)[:220]


def to_attack(draft: Any, rows: dict[int, IncidentRecord], attack_id: str) -> Attack:
    """Build the Attack contract; provenance comes from the incident record."""
    r = rows[draft.incident_row]
    name = getattr(r, "name", "") or f"{r.event_type} crowd accident, {r.country}"
    return Attack.model_validate(
        {
            "attack_id": attack_id,
            "title": draft.title.strip()[:90],
            "events": [e.model_dump(exclude_none=True) for e in draft.events],
            "inspired_by": {
                "incident": name,
                "year": r.year,
                "source_url": _source_url(r),
                "evidence": _evidence(r),
                "dataset_row": r.row_id,
            },
            "rationale": draft.rationale.strip(),
        }
    )


# Words a 9B model sometimes borrows from the incident text; each needs the feature in the venue.
_FEATURE_WORDS: dict[str, Any] = {
    "stair": lambda v: bool(v.stairs),
    "escalator": lambda v: False,
    "mezzanine": lambda v: len(v.floors) > 1,
    "balcony": lambda v: len(v.floors) > 1,
    "upper floor": lambda v: len(v.floors) > 1,
    "stage": lambda v: (
        v.stage is not None or any(o.kind == "stage" for f in v.floors for o in f.obstacles)
    ),
    "tunnel": lambda v: False,
    "bridge": lambda v: False,
}


def grounded_title(title: str, venue: Venue, attack: Attack, registry: Registry) -> str:
    """Keep the model's title unless it names something this venue does not have."""
    low = title.lower()
    if not any(w in low and not has(venue) for w, has in _FEATURE_WORDS.items()):
        return title
    labels: list[str] = []
    refs: list[str] = []
    for e in attack.events:
        try:
            label = registry.event(e.type).label
        except KeyError:
            label = e.type.replace("_", " ").capitalize()
        label = label if not labels else label[:1].lower() + label[1:]
        if label.lower() not in (x.lower() for x in labels):
            labels.append(label)
        d = e.model_dump()
        refs += [r for r in (d.get("exit_id"), d.get("zone_id")) if isinstance(r, str)]
    ref = refs[0] if refs else None
    names = {x.id: x.label or x.id for f in venue.floors for x in [*f.exits, *f.zones]}
    where = f" at {names.get(ref, ref)}" if ref else ""
    return f"{' and '.join(labels)}{where}"


def signature(events: list[dict[str, Any]]) -> str:
    """Identity of an attack for de-duplication (ignores timing details)."""
    keys = []
    for e in events:
        ref = e.get("exit_id") or e.get("zone_id") or ""
        keys.append(f"{e.get('type')}:{ref}")
    return "|".join(sorted(keys))


async def red_team(
    env: AgentEnv,
    registry: Registry,
    venue: Venue,
    baseline: RunResult | None,
    incidents: list[IncidentRecord],
    n: int,
    seen: set[str],
    id_offset: int = 0,
    tested: list[str] | None = None,
) -> list[Attack]:
    """Ask the model for up to n attacks; invalid or duplicate ones are discarded."""
    feats = venue_features(venue, baseline)
    rows = {r.row_id: r for r in incidents}
    total = venue.total_people()
    model = _model(registry, n)

    def problems_of(d: Any) -> list[str]:
        p: list[str] = []
        if d.incident_row not in rows:
            p.append(f"incident_row {d.incident_row} is not in the incident list")
        for e in d.events:
            spec = registry.event(e.type)
            p.extend(spec.validate_refs(venue, spec.params_model.model_validate(e.model_dump())))
            if e.type == "surge" and e.extra_people > max(50, total // 2):
                p.append(f"surge of {e.extra_people} is more than half the crowd")
            if e.type == "counterflow" and e.people > max(50, total // 3):
                p.append(f"counterflow of {e.people} is more than a third of the crowd")
            if e.at_s > 600:
                p.append("events must start within the first 10 minutes")
        return p

    def validate(out: Any) -> list[str]:
        probs: list[str] = []
        for i, d in enumerate(out.attacks):
            probs.extend(f"attack {i + 1}: {x}" for x in problems_of(d))
        return probs

    values = {
        "venue": venue_summary(venue),
        "ids": ids_line(venue),
        "features": json.dumps(feats),
        "incidents": _incident_lines(incidents),
        "events": events_doc(registry, ATTACK_EVENTS),
        "n": str(n),
        "tested": "\n".join(f"- {t}" for t in (tested or [])) or "- nothing yet",
    }
    call = await call_agent(
        env,
        RED_TEAM_AGENT,
        values,
        f"Design {n} different attacks on this plan.",
        output_model=model,
        validate=validate,
        summarize=lambda o: "; ".join(a.title for a in o.attacks)[:300],
    )
    attacks: list[Attack] = []
    for d in call.output.attacks if call.output else []:
        if problems_of(d):
            audit_decision(
                env, "red_team", "discarded attack", {"title": d.title, "problems": problems_of(d)}
            )
            continue
        a = to_attack(d, rows, f"A{id_offset + len(attacks) + 1}")
        title = grounded_title(a.title, venue, a, registry)
        if title != a.title:
            audit_decision(env, "red_team", "retitled attack", {"was": a.title, "now": title})
            a = a.model_copy(update={"title": title})
        sig = signature([e.model_dump() for e in a.events])
        if sig in seen:
            audit_decision(env, "red_team", "discarded duplicate", {"title": a.title})
            continue
        seen.add(sig)
        attacks.append(a)
    return attacks
