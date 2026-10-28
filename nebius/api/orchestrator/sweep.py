"""Scenario sweep: the same plan under several what-ifs, each simulated in its own sandbox.

Locally the Docker sandbox runs them one after another; with Nebius Sandboxes every scenario is
a branch of the plan's run and they run in parallel (SANDBOX_MAX_PARALLEL). Results feed the
scenario matrix in Simulate and the Copilot's review.
"""

from __future__ import annotations

import logging
from typing import Any

from api.adapters.llm import LLMError
from api.agents.base import AgentEnv, AgentUnavailable
from api.agents.what_if import design_what_ifs
from api.core.estimates import scale_people
from api.core.scenarios import (
    BY_ID,
    CATALOGUE,
    LEGACY_SWEEP,
    Resolved,
    catalogue_for,
    resolve,
    venue_facts,
)
from api.db.models import UserSetting
from api.db.session import db_session
from api.models import RunResult, Venue

log = logging.getLogger("showtime.sweep")


DEFAULT_SCENARIOS = LEGACY_SWEEP  # as planned, +20%, main exit closed, rain, both, late surge
MAX_SCENARIOS = 18


class UnknownScenario(ValueError):
    """A scenario id that is not in the catalogue."""


def _resolve(
    st: Any, venue: Venue, scenario_ids: list[str] | tuple[str, ...] | None
) -> list[Resolved]:
    ids = list(dict.fromkeys(scenario_ids or DEFAULT_SCENARIOS))
    unknown = [i for i in ids if i not in BY_ID]
    if unknown:
        raise UnknownScenario(
            f"Unknown scenario '{unknown[0]}'. Known: {', '.join(s.id for s in CATALOGUE)}."
        )
    if len(ids) > MAX_SCENARIOS:
        raise UnknownScenario(f"At most {MAX_SCENARIOS} scenarios per sweep.")
    baseline = st.runs.estimate(venue)
    facts = venue_facts(venue, baseline)
    return [resolve(BY_ID[i], facts) for i in ids]


async def design(st: Any, project_id: str) -> tuple[list[Resolved], str]:
    """The what-ifs for a project, chosen and composed by the AI from the scenario library and
    the scenario events; the standard six only when no model answers. Returns them and who
    chose them ("ai" or "standard")."""
    venue: Venue = st.projects.venue(project_id)
    library = catalogue_for(venue, st.runs.estimate(venue))
    env = AgentEnv(llm=st.llm, project_id=project_id, on_usage=st.usage.add)
    try:
        plan = await design_what_ifs(env, st.registry, venue, library)
    except (AgentUnavailable, LLMError) as exc:
        log.warning("what-if designer unavailable (%s); running the standard six", exc)
        return _resolve(st, venue, None), "standard"
    if not plan.scenarios:
        return _resolve(st, venue, None), "standard"
    return plan.scenarios, "ai"


def _item(r: Resolved, **kw: Any) -> dict[str, Any]:
    """A sweep row: the original fields (key, label, run_id, skipped, closed_exit) plus the
    catalogue's title, icon, category and targets."""
    return {
        "key": r.spec.id,
        "label": r.label,
        "title": r.spec.title,
        "icon": r.spec.icon,
        "category": r.spec.category,
        "targets": r.built.targets if r.built else [],
        **kw,
    }


def _key(project_id: str) -> str:
    return f"_sweep:{project_id}"


def sweep_tier(st: Any) -> int:
    """Full runs when the sandbox runs several at once; quick (3-minute) runs one at a time."""
    return 3 if int(getattr(st.runner, "parallel", 1)) > 1 else 2


def start_sweep(
    st: Any,
    project_id: str,
    parent_run_id: str | None = None,
    scenario_ids: list[str] | None = None,
    resolved: list[Resolved] | None = None,
    chosen_by: str = "standard",
) -> dict[str, Any]:
    """Submit every scenario (`resolved`, e.g. designed by the AI, else `scenario_ids`, else
    the original six); returns the sweep record (scenario → run id). Raises UnknownScenario
    for ids outside the catalogue."""
    p = st.projects.get(project_id)
    version = p.current_version
    venue: Venue = st.projects.venue(project_id, version)
    tier = sweep_tier(st)
    items: list[dict[str, Any]] = []
    for r in resolved if resolved is not None else _resolve(st, venue, scenario_ids):
        if r.built is None:
            items.append(_item(r, run_id=None, skipped=r.reason))
            continue
        v = scale_people(venue, r.built.scale)
        total = v.total_people() + sum(
            int(e.model_dump().get("extra_people", 0) or e.model_dump().get("people", 0) or 0)
            for e in r.built.events
            if e.type in ("surge", "counterflow")
        )
        if total > st.settings.max_people:
            items.append(
                _item(
                    r,
                    run_id=None,
                    skipped=f"{total:,} people is above the simulation limit.",
                )
            )
            continue
        try:
            job = st.runs.build_job(
                v,
                tier=tier,
                seed=st.settings.default_seed,
                extra=list(r.built.events),
                parent_run_id=parent_run_id,
            )
            job.request.extensions["events"] = job.events
            job.request.extensions["scenario_id"] = r.spec.id
            rid = st.runs.submit(
                job, project_id=project_id, venue_version=version, label=f"Sweep · {r.label}"
            )
        except Exception as exc:  # one bad scenario must not stop the sweep
            log.exception("sweep scenario %s failed to start", r.spec.id)
            items.append(_item(r, run_id=None, skipped=str(exc)[:160]))
            continue
        items.append(_item(r, run_id=rid, closed_exit=r.built.closed_exit))
    record = {
        "version": version,
        "tier": tier,
        "scenarios": [it["key"] for it in items],
        "items": items,
        "chosen_by": chosen_by if resolved is not None else "you" if scenario_ids else "standard",
    }
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, _key(project_id)) or UserSetting(key=_key(project_id))
        row.value = record
        s.add(row)
        s.commit()
    return record


def sweep_status(st: Any, project_id: str) -> dict[str, Any] | None:
    """The latest sweep of a project with each run's status and headline metrics."""
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, _key(project_id))
        record = dict(row.value) if row and isinstance(row.value, dict) else None
    if record is None:
        return None
    out = []
    for it in record.get("items", []):
        item = dict(it)
        rid = it.get("run_id")
        r = st.runs.get(rid) if rid else None
        if r is not None:
            # a run waiting for a free sandbox has no progress yet
            item["status"] = "queued" if r.status == "running" and not r.progress else r.status
            item["progress"] = r.progress
            item["tier"] = r.tier
            if r.result and r.status in ("ok", "partial"):
                m = RunResult.model_validate(r.result).metrics
                item["metrics"] = {
                    "evac_time_p95_s": m.evac_time_p95_s,
                    "peak_density_ppm2": m.peak_density_ppm2,
                    "time_above_danger_s": m.time_above_danger_s,
                    "agents_not_evacuated": m.agents_not_evacuated,
                    "agents_total": m.agents_total,
                }
                for k in ("time_turbulent_s", "peak_pressure"):
                    if k in m.extra:
                        item["metrics"][k] = m.extra[k]
        else:
            item["status"] = "skipped" if it.get("skipped") else "missing"
        out.append(item)
    return {**record, "items": out}


def instant_matrix(
    st: Any, venue: Venue, scenario_ids: list[str] | None = None
) -> list[dict[str, Any]]:
    """Instant estimate of every scenario (milliseconds): what the sweep will test."""
    out: list[dict[str, Any]] = []
    for r in _resolve(st, venue, scenario_ids):
        if r.built is None:
            continue
        v = scale_people(venue, r.built.scale)
        m = st.runs.estimate(v, None, None, list(r.built.events)).metrics
        out.append(
            {
                "scenario": r.label,
                "people": m.agents_total or v.total_people(),
                "evacuation_95_percent_s": round(m.evac_time_p95_s) if m.evac_time_p95_s else None,
                "peak_people_per_m2": round(m.peak_density_ppm2, 1),
                "closed_exit": r.built.closed_exit,
            }
        )
    return out
