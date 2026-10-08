"""Scenario sweep: the same plan under several what-ifs, each simulated in its own sandbox.

Locally the Docker sandbox runs them one after another; with Nebius Sandboxes every scenario is
a branch of the plan's run and they run in parallel (SANDBOX_MAX_PARALLEL). Results feed the
scenario matrix in Simulate and the Copilot's review.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

from api.core.estimates import scale_people
from api.db.models import UserSetting
from api.db.session import db_session
from api.models import RunResult, ScenarioEventIn, Venue

log = logging.getLogger("showtime.sweep")


@dataclass(frozen=True)
class Scenario:
    """One what-if of the sweep."""

    key: str
    label: str
    scale: float = 1.0
    speed: float = 1.0
    close_main: bool = False


SCENARIOS = (
    Scenario("plan", "As planned"),
    Scenario("plus20", "20% more people", scale=1.2),
    Scenario("gate", "Main exit closed", close_main=True),
    Scenario("rain", "Rain: 85% walking speed", speed=0.85),
    Scenario("rain_gate", "Rain and main exit closed", speed=0.85, close_main=True),
    Scenario("surge", "Late surge in the dark: 30% more, 70% speed", scale=1.3, speed=0.7),
)


def _key(project_id: str) -> str:
    return f"_sweep:{project_id}"


def sweep_tier(settings: Any) -> int:
    """Full runs when sandboxes run in parallel (Nebius); 3-minute runs on one local Docker."""
    return 3 if settings.sandbox_provider == "nebius" else 2


def start_sweep(st: Any, project_id: str, parent_run_id: str | None = None) -> dict[str, Any]:
    """Submit every scenario; returns the sweep record (scenario → run id)."""
    p = st.projects.get(project_id)
    version = p.current_version
    venue: Venue = st.projects.venue(project_id, version)
    exits = [e for f in venue.floors for e in f.exits if not e.blocked]
    main = max(exits, key=lambda e: e.width_m) if len(exits) > 1 else None
    tier = sweep_tier(st.settings)
    items: list[dict[str, Any]] = []
    for sc in SCENARIOS:
        v = scale_people(venue, sc.scale)
        extra: list[ScenarioEventIn] = []
        if sc.close_main:
            if main is None:
                items.append(
                    {
                        "key": sc.key,
                        "label": sc.label,
                        "run_id": None,
                        "skipped": "Only one exit: closing it would trap everyone.",
                    }
                )
                continue
            extra.append(ScenarioEventIn(type="block_exit", exit_id=main.id, at_s=0))
        if sc.speed < 1:
            extra.append(ScenarioEventIn(type="slowdown", factor=sc.speed, at_s=0))
        if v.total_people() > st.settings.max_people:
            items.append(
                {
                    "key": sc.key,
                    "label": sc.label,
                    "run_id": None,
                    "skipped": f"{v.total_people():,} people is above the simulation limit.",
                }
            )
            continue
        try:
            job = st.runs.build_job(v, tier=tier, seed=42, extra=extra, parent_run_id=parent_run_id)
            rid = st.runs.submit(
                job, project_id=project_id, venue_version=version, label=f"Sweep · {sc.label}"
            )
        except Exception as exc:  # one bad scenario must not stop the sweep
            log.exception("sweep scenario %s failed to start", sc.key)
            items.append(
                {"key": sc.key, "label": sc.label, "run_id": None, "skipped": str(exc)[:160]}
            )
            continue
        items.append(
            {
                "key": sc.key,
                "label": sc.label,
                "run_id": rid,
                "closed_exit": main.label or main.id if sc.close_main and main else None,
            }
        )
    record = {"version": version, "tier": tier, "items": items}
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
        else:
            item["status"] = "skipped" if it.get("skipped") else "missing"
        out.append(item)
    return {**record, "items": out}


def instant_matrix(st: Any, venue: Venue) -> list[dict[str, Any]]:
    """Instant estimate of every scenario (milliseconds): what the sweep will test."""
    exits = [e for f in venue.floors for e in f.exits if not e.blocked]
    main = max(exits, key=lambda e: e.width_m) if len(exits) > 1 else None
    out: list[dict[str, Any]] = []
    for sc in SCENARIOS:
        v = scale_people(venue, sc.scale)
        extra: list[ScenarioEventIn] = []
        if sc.close_main and main is not None:
            extra.append(ScenarioEventIn(type="block_exit", exit_id=main.id, at_s=0))
        elif sc.close_main:
            continue
        if sc.speed < 1:
            extra.append(ScenarioEventIn(type="slowdown", factor=sc.speed, at_s=0))
        m = st.runs.estimate(v, None, None, extra).metrics
        out.append(
            {
                "scenario": sc.label,
                "people": v.total_people(),
                "evacuation_95_percent_s": round(m.evac_time_p95_s) if m.evac_time_p95_s else None,
                "peak_people_per_m2": round(m.peak_density_ppm2, 1),
                "closed_exit": (main.label or main.id) if sc.close_main and main else None,
            }
        )
    return out
