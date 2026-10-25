"""Red team: attack scenarios grounded in real crowd incidents.

The model chooses which incident inspires each attack and which events to stage; the
source URL and evidence come from the incident record itself (never from the model).
"""

from __future__ import annotations

import hashlib
import json
import re
from types import GenericAlias
from typing import Any, cast

from pydantic import BaseModel, Field, create_model

from api.agents.base import AgentDef, AgentEnv, audit_decision, call_agent
from api.agents.context import event_union, events_doc, ids_line, venue_summary
from api.agents.numbers import allowed_numbers, check_numbers
from api.core.extensions import IncidentRecord, Registry
from api.core.scripts import MAX_SCRIPT_CHARS, check_script
from api.models import Attack, RunResult, Venue

# marshal_redirect as an attack is misdirection: wrong signs or a marshal sending people the
# wrong way (the "wrong route" row of the failure map)
ATTACK_EVENTS = {"block_exit", "surge", "slowdown", "counterflow", "marshal_redirect"}
DOI = "https://doi.org/10.5281/zenodo.19483010"
SCRIPT_EVENT = "script"
MAX_SCRIPT_ATTACKS = 1  # per round, on top of the menu attacks


class RedTeamBase(BaseModel):
    """Static stand-in for the dynamic output model."""

    attacks: list[dict[str, Any]] = Field(default_factory=list)
    scripts: list[dict[str, Any]] = Field(default_factory=list)


RED_TEAM_AGENT = AgentDef(
    name="red_team",
    role="fast",
    prompt_file="red_team.md",
    output_model=RedTeamBase,
    temperature=0.3,
    max_tokens=2600,
    description="Designs attack scenarios from real incidents.",
)


def _model(registry: Registry, n: int) -> type[BaseModel]:
    draft = create_model(
        "AttackDraft",
        title=(str, Field(max_length=90)),
        incident_row=(int, ...),
        events=(
            GenericAlias(list, event_union(registry, ATTACK_EVENTS)),
            Field(min_length=1, max_length=3),
        ),
        rationale=(str, Field(default="", max_length=260)),
    )
    # code is checked after parsing (check_script), so one bad script never sinks the reply
    script = create_model(
        "ScriptAttackDraft",
        title=(str, Field(max_length=90)),
        incident_row=(int, ...),
        code=(str, ...),
        every_s=(float, Field(default=1.0, ge=0.25, le=600)),
        rationale=(str, Field(default="", max_length=260)),
    )
    return create_model(
        "RedTeamOut",
        attacks=(GenericAlias(list, draft), Field(min_length=1, max_length=n)),
        scripts=(
            GenericAlias(list, script),
            Field(default_factory=list, max_length=MAX_SCRIPT_ATTACKS),
        ),
    )


def is_script_attack(attack: Attack) -> bool:
    """An attack written as code (a `script` event) rather than picked from the menu."""
    return any(e.type == SCRIPT_EVENT for e in attack.events)


def script_problems(code: str) -> list[str]:
    """Static problems with a scenario script (it is never run outside the sandbox)."""
    if len(code) > MAX_SCRIPT_CHARS:
        return [f"code is longer than {MAX_SCRIPT_CHARS} characters"]
    return check_script(code)


def script_attack(
    title: str,
    code: str,
    record: IncidentRecord,
    attack_id: str,
    rationale: str = "",
    every_s: float = 1.0,
    generated_by: str = "ai",
) -> Attack:
    """An attack made of one scenario script; provenance comes from the incident record."""
    return Attack.model_validate(
        {
            "attack_id": attack_id,
            "title": title.strip()[:90],
            "events": [
                {
                    "type": SCRIPT_EVENT,
                    "title": title.strip()[:90],
                    "code": code,
                    "every_s": every_s,
                    "at_s": 0.0,
                }
            ],
            "inspired_by": inspired_by(record),
            "rationale": rationale.strip(),
            "extensions": {"kind": "script", "generated_by": generated_by},
        }
    )


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
        facts = [str(x) for x in (r.year, r.country) if x]
        if r.deaths is not None:  # a web page that gives no count is not "0 deaths"
            facts.append(f"{r.deaths} deaths")
        where = "[web search result] " if r.origin == "tavily" else ""
        out.append(f"row {r.row_id}: {where}{name} ({'; '.join(facts) or 'no details'}). {desc}")
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


def inspired_by(r: IncidentRecord) -> dict[str, Any]:
    """The evidence on an attack, from the record it is grounded in: its name, year, source URL
    (the dataset row or the web hit, never one the model wrote) and where it came from."""
    name = getattr(r, "name", "") or f"{r.event_type} crowd accident, {r.country}"
    web = r.origin == "tavily"
    return {
        "incident": name,
        "year": r.year,
        "source_url": _source_url(r),
        "evidence": _evidence(r),
        "dataset_row": None if web else r.row_id,
        "origin": "tavily" if web else "dataset",
    }


# web hits are listed for the red team after the dataset rows, from this row number on
WEB_ROW_BASE = 100_000


def web_records(hits: list[Any]) -> list[IncidentRecord]:
    """Web search hits as incident rows the red team may cite (origin "tavily")."""
    out = []
    for i, h in enumerate(hits):
        year = int(h.published[:4]) if h.published and h.published[:4].isdigit() else None
        out.append(
            IncidentRecord(
                row_id=WEB_ROW_BASE + i,
                year=year,
                name=h.title[:120],
                description=h.snippet,
                source_url=h.url,
                date=h.published,
                origin="tavily",
            )
        )
    return out


def web_queries(venue: Venue, feats: dict[str, Any], n: int) -> list[str]:
    """Up to n web searches for real incidents and near-misses like this venue's, from the same
    weighted keywords the dataset search uses and the kind of event."""
    q = incident_query(venue, feats)
    words = [w for w, _ in sorted(q["keywords"].items(), key=lambda kv: -kv[1])]
    event = (venue.event_kind or "").replace("_", " ") or q["settings"][0]
    picks = [
        f"crowd crush {event} {words[0]} {words[1]}",
        f"crowd near-miss {event} evacuation {' '.join(words[2:4])}",
        f"{event} crowd disaster inquiry report {words[0]}",
    ]
    return [p.strip() for p in picks[: max(0, n)]]


def to_attack(draft: Any, rows: dict[int, IncidentRecord], attack_id: str) -> Attack:
    """Build the Attack contract; provenance comes from the incident record."""
    r = rows[draft.incident_row]
    return Attack.model_validate(
        {
            "attack_id": attack_id,
            "title": draft.title.strip()[:90],
            "events": [e.model_dump(exclude_none=True) for e in draft.events],
            "inspired_by": inspired_by(r),
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


# a title that repeats the failure-map target it was aimed at ("Adaptive scenario (code) · West
# side: exits …") says nothing about what happens; the model is asked to name the failure instead
_AIM_COPY = re.compile(r"\(code\)|:\s*(?:exits|zones)\s", re.IGNORECASE)


def prose_numbers(title: str, rationale: str, facts: Any) -> list[str]:
    """Numbers an attack's title or rationale quotes that are not in `facts` (the venue, its
    features, the attack's own events or code, the incident it cites): hard rule 3, no number
    from the model shown as a fact."""
    return check_numbers(f"{title}. {rationale}", allowed_numbers(facts))


def strip_numbers(text: str, bad: list[str]) -> str:
    """The text without the numbers that failed the check."""
    for tok in bad:
        text = re.sub(rf"(?<![\w.]){re.escape(tok)}(?![\w])\s*", "", text)
    return re.sub(r"\s{2,}", " ", text).strip(" ,;")


def copies_aim(title: str) -> bool:
    """Whether a title is the target description the attack was aimed at, not a name for it."""
    return bool(_AIM_COPY.search(title))


def title_from_rationale(rationale: str, fallback: str) -> str:
    """A readable title from the model's own rationale (its first clause), when the title it
    wrote only repeats its target."""
    first = re.split(r"(?<=[.;:!?])\s|,\s", rationale.strip(), maxsplit=1)[0].rstrip(".;:!?")
    if len(first) < 8:
        return fallback
    words, out = first.split(), ""
    for w in words:
        if len(out) + len(w) + 1 > 60:
            break
        out = f"{out} {w}".strip()
    return out[:1].upper() + out[1:]


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
    names = {e.id: e.label or e.id for f in venue.floors for e in f.exits}
    names.update({z.id: z.label or z.id for f in venue.floors for z in f.zones})
    where = f" at {names.get(ref, ref)}" if ref else ""
    return f"{' and '.join(labels)}{where}"


def signature(events: list[dict[str, Any]]) -> str:
    """Identity of an attack for de-duplication (ignores timing details)."""
    keys = []
    for e in events:
        # every place the event names: two redirects between different exits are different
        ref = "/".join(
            str(e[k])
            for k in (
                "exit_id",
                "zone_id",
                "from_exit_id",
                "to_exit_id",
                "target_zone_id",
                "floor_id",
            )
            if e.get(k)
        )
        if e.get("type") == SCRIPT_EVENT:
            ref = hashlib.sha256(str(e.get("code", "")).encode()).hexdigest()[:12]
        keys.append(f"{e.get('type')}:{ref}")
    return "|".join(sorted(keys))


def _checked_prose(env: AgentEnv, a: Attack, facts: Any) -> Attack:
    """An attack whose title and rationale quote only checked numbers: what still fails after the
    repair round is removed (the rationale, or the number in the title), and the audit says so."""
    bad = prose_numbers(a.title, a.rationale or "", facts)
    if not bad:
        return a
    title = strip_numbers(a.title, bad) or a.title
    audit_decision(env, "red_team", "removed unchecked numbers", {"title": a.title, "numbers": bad})
    return a.model_copy(update={"title": title, "rationale": ""})


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
    aim: list[str] | None = None,
    aim_script: str | None = None,
) -> list[Attack]:
    """Ask the model for up to n attacks; invalid or duplicate ones are discarded.

    `aim` names the failure-map cells (hazard kind · where) the attacks should fill, one
    line per attack, and `aim_script` the cell for the scenario script (quality-diversity
    search, docs/RAINBOW.md). Which cell an attack really lands in is decided from its
    events afterwards, never from the model's claim."""
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

    def script_problems_of(d: Any) -> list[str]:
        p: list[str] = []
        if d.incident_row not in rows:
            p.append(f"incident_row {d.incident_row} is not in the incident list")
        if not d.title.strip():
            p.append("title is empty")
        p.extend(script_problems(d.code))
        return p

    def facts_of(d: Any) -> dict[str, Any]:
        rec = rows.get(d.incident_row)
        return {
            "venue": venue.model_dump(mode="json"),
            "features": feats,
            "events": [e.model_dump() for e in getattr(d, "events", [])],
            "code": getattr(d, "code", ""),
            "every_s": getattr(d, "every_s", None),
            "incident": rec.model_dump(mode="json") if rec is not None else {},
        }

    def validate(out: Any) -> list[str]:
        probs: list[str] = []
        for i, d in enumerate(out.attacks):
            probs.extend(f"attack {i + 1}: {x}" for x in problems_of(d))
        for i, d in enumerate(getattr(out, "scripts", [])):
            probs.extend(f"script {i + 1}: {x}" for x in script_problems_of(d))
        named = [("attack", i, d) for i, d in enumerate(out.attacks)]
        named += [("script", i, d) for i, d in enumerate(getattr(out, "scripts", []))]
        for kind, i, d in named:
            bad = prose_numbers(d.title, d.rationale, facts_of(d))
            if bad:
                probs.append(
                    f"{kind} {i + 1}: the title or rationale quotes {', '.join(bad)}, which is not "
                    "in the venue, its events or the incident; quote only those numbers, or none"
                )
        probs.extend(
            f"{kind} {i + 1}: the title repeats the target; name what happens to the crowd "
            "there in a few words, using the exit, zone or floor names of this venue"
            for kind, i, d in named
            if copies_aim(d.title)
        )
        return probs

    values = {
        "venue": venue_summary(venue),
        "ids": ids_line(venue),
        "features": json.dumps(feats),
        "incidents": _incident_lines(incidents),
        "events": events_doc(registry, ATTACK_EVENTS),
        "n": str(n),
        "tested": "\n".join(f"- {t}" for t in (tested or [])) or "- nothing yet",
        "aim": "\n".join(f"{i + 1}. {line}" for i, line in enumerate(aim or []))
        or "- any new weakness",
        "aim_script": aim_script or "any part of the venue",
    }
    call = await call_agent(
        env,
        RED_TEAM_AGENT,
        values,
        f"Design {n} different attacks on this plan.",
        output_model=model,
        validate=validate,
        summarize=lambda o: "; ".join(
            [a.title for a in cast(Any, o).attacks]
            + [f"script: {d.title}" for d in getattr(o, "scripts", [])]
        )[:300],
    )
    attacks: list[Attack] = []
    for d in cast(Any, call.output).attacks if call.output else []:
        if problems_of(d):
            audit_decision(
                env, "red_team", "discarded attack", {"title": d.title, "problems": problems_of(d)}
            )
            continue
        a = to_attack(d, rows, f"A{id_offset + len(attacks) + 1}")
        a = _checked_prose(env, a, facts_of(d))
        title = grounded_title(a.title, venue, a, registry)
        if copies_aim(title):
            title = title_from_rationale(a.rationale or "", title)
        if title != a.title:
            audit_decision(env, "red_team", "retitled attack", {"was": a.title, "now": title})
            a = a.model_copy(update={"title": title})
        sig = signature([e.model_dump() for e in a.events])
        if sig in seen:
            audit_decision(env, "red_team", "discarded duplicate", {"title": a.title})
            continue
        seen.add(sig)
        attacks.append(a)
    for d in getattr(call.output, "scripts", []) if call.output else []:
        probs = script_problems_of(d)
        if probs:
            # the reason is kept in the audit log; the code itself never ran
            audit_decision(
                env, "red_team", "discarded script attack", {"title": d.title, "problems": probs}
            )
            continue
        title = d.title
        if copies_aim(title):
            title = title_from_rationale(d.rationale, "AI-written scenario")
            audit_decision(env, "red_team", "retitled attack", {"was": d.title, "now": title})
        a = script_attack(
            title,
            d.code,
            rows[d.incident_row],
            f"A{id_offset + len(attacks) + 1}",
            d.rationale,
            d.every_s,
        )
        a = _checked_prose(env, a, facts_of(d))
        sig = signature([e.model_dump() for e in a.events])
        if sig in seen:
            audit_decision(env, "red_team", "discarded duplicate", {"title": a.title})
            continue
        seen.add(sig)
        audit_decision(env, "red_team", "script attack accepted", {"title": a.title})
        attacks.append(a)
    return attacks
