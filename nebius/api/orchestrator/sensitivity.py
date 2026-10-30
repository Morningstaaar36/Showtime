"""Sensitivity: Your plan's key run again with fewer or more people, slower or faster.

Headcounts and walking speeds are planning assumptions, not measurements. This repeats the run
Your plan's numbers rest on (the chosen changes under the worst attack, or the baseline) four
more times, changing one assumption at a time and keeping the seed, venue, events and tier:

- every zone's headcount × 0.8 and × 1.2 (`scale_people`; surges and counterflows in the attack
  keep their own numbers),
- every free walking speed (level mean and spread, stairs) × 0.85 and × 1.15, from the start;
  exit and stair flow capacities stay as set.

The range (min–max and median) covers evacuation time (95%), peak density and people still
inside over the runs that finished, the plan as tested included. Each run also says whether it
breaks the plan by the same rules as the red team. Runs that did not finish stay listed with
their status and are left out of the range, with a note that says so. Every variant is a normal
run with its inputs in its identity, so repeating the check reuses them.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from api.core.estimates import scale_people
from api.core.extensions.breaks import BreakRule, break_reasons
from api.core.plan import PlanError
from api.core.venue_ops import PatchError
from api.db.models import UserSetting
from api.db.session import db_session
from api.models import RunResult
from api.orchestrator.seeds import METRICS, PENDING, USABLE, KeyRun, SeedCheckError, spread
from api.orchestrator.together import plan_key

log = logging.getLogger("showtime.sensitivity")


class SensitivityError(Exception):
    """The check can't start; the message says why in organizer words."""


@dataclass(frozen=True)
class Variant:
    """One changed assumption."""

    key: str
    label: str
    people: float = 1.0
    speed: float = 1.0


def variants(settings: Any) -> tuple[Variant, ...]:
    """The plan as tested, then each assumption changed by the configured share."""
    pp = float(settings.sensitivity_people_pct)
    sp = float(settings.sensitivity_speed_pct)
    return (
        Variant("as_tested", "As tested"),
        Variant(f"people_minus_{pp:g}", f"{pp:g}% fewer people", people=1 - pp / 100),
        Variant(f"people_plus_{pp:g}", f"{pp:g}% more people", people=1 + pp / 100),
        Variant(f"speed_minus_{sp:g}", f"Walking {sp:g}% slower", speed=1 - sp / 100),
        Variant(f"speed_plus_{sp:g}", f"Walking {sp:g}% faster", speed=1 + sp / 100),
    )


def _key(session_id: str) -> str:
    return f"_sensitivity:{session_id}"


def _load(st: Any, session_id: str) -> dict[str, Any] | None:
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, _key(session_id))
        return dict(row.value) if row is not None and isinstance(row.value, dict) else None


def _save(st: Any, session_id: str, record: dict[str, Any]) -> None:
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, _key(session_id)) or UserSetting(key=_key(session_id))
        row.value = record
        row.updated_at = datetime.now(UTC)
        s.add(row)
        s.commit()


def _target(st: Any, key: KeyRun) -> float:
    s = st.settings
    indoor = key.venue.mode == "indoor"
    return float(s.target_evac_indoor_s if indoor else s.target_evac_outdoor_s)


def _plan_key(st: Any, session: Any) -> KeyRun:
    try:
        return plan_key(st, session)
    except SeedCheckError as exc:
        raise SensitivityError(str(exc)) from exc


def start_sensitivity(st: Any, session: Any) -> dict[str, Any]:
    """Submit the key run under each changed assumption (needs a running event loop).

    When the key run can no longer be rebuilt exactly (a setting changed since the test), the
    plan as tested is simulated again too, so every run shares the current settings.
    """
    key = _plan_key(st, session)

    def build(v: Variant) -> Any:
        try:
            job = st.runs.build_job(
                scale_people(key.venue, v.people),
                tier=key.tier,
                seed=key.seed,
                attack=key.attack,
                extra=key.extra,
                parent_run_id=key.run_id,
                speed_factor=v.speed,
            )
        except (PlanError, PatchError, ValueError) as exc:
            problems = getattr(exc, "problems", None) or getattr(exc, "issues", None) or [exc]
            first = problems[0]
            raise SensitivityError(
                "The tested plan can't be simulated again: " + str(getattr(first, "message", first))
            ) from exc
        job.request.extensions["events"] = job.events
        return job

    items: list[dict[str, Any]] = []
    for v in variants(st.settings):
        job = build(v)
        if v.key == "as_tested" and job.request.run_id == key.run_id:
            items.append({"variant": v.key, "run_id": key.run_id, "original": True})
            continue
        rid = st.runs.submit(
            job,
            project_id=session.project_id,
            venue_version=key.venue_version,
            session_id=session.id,
            label=f"{key.label} · {v.label}"[:120],
        )
        item: dict[str, Any] = {"variant": v.key, "run_id": str(rid), "original": False}
        if v.key == "as_tested":
            item["rerun_of"] = key.run_id
        items.append(item)
    record = {
        "session_id": session.id,
        "key": key.info(),
        "target_s": _target(st, key),
        "items": items,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _save(st, session.id, record)
    log.info("sensitivity %s: %s under %d assumptions", session.id, key.run_id, len(items))
    return sensitivity_status(st, session)


def _item(st: Any, it: dict[str, Any], target_s: float) -> dict[str, Any]:
    v = next((x for x in variants(st.settings) if x.key == it.get("variant")), None)
    out: dict[str, Any] = {
        "variant": it.get("variant"),
        "label": v.label if v else str(it.get("variant")),
        "people_factor": v.people if v else None,
        "speed_factor": v.speed if v else None,
        "run_id": it.get("run_id"),
        "original": bool(it.get("original")),
        "status": "missing",
        "basis": "unknown",
        "tier": None,
        "progress": None,
        "metrics": None,
        "error": None,
        "included": False,
        "breaks": [],
    }
    row = st.runs.get(str(it["run_id"])) if it.get("run_id") else None
    if row is None:
        return out
    out["tier"] = row.tier
    out["status"] = "queued" if row.status == "running" and not row.progress else row.status
    out["progress"] = row.progress
    out["error"] = row.error
    if row.result:
        try:
            res = RunResult.model_validate(row.result)
        except ValueError:
            return out
        out["basis"] = res.basis
        m = res.metrics
        out["metrics"] = {
            "evac_time_p95_s": m.evac_time_p95_s,
            "peak_density_ppm2": m.peak_density_ppm2,
            "agents_not_evacuated": m.agents_not_evacuated,
            "agents_total": m.agents_total,
            "time_above_danger_s": m.time_above_danger_s,
        }
        out["included"] = row.status in USABLE and res.basis != "unknown"
        if out["included"]:
            s = st.settings
            out["breaks"] = break_reasons(res, BreakRule.of(s, target_s))
    return out


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def sensitivity_status(st: Any, session: Any) -> dict[str, Any]:
    """The latest sensitivity check of a session: each run and the range over finished ones."""
    try:
        key: dict[str, Any] | None = _plan_key(st, session).info()
        reason = None
    except SensitivityError as exc:
        key, reason = None, str(exc)
    base: dict[str, Any] = {
        "session_id": session.id,
        "available": key is not None,
        "reason": reason,
        "key": key,
        "variants": [
            {"variant": v.key, "label": v.label, "people_factor": v.people, "speed_factor": v.speed}
            for v in variants(st.settings)
        ],
    }
    record = _load(st, session.id)
    if record is None:
        return {
            **base,
            "status": "none",
            "items": [],
            "done": 0,
            "total": 0,
            "range": None,
            "holds_in_all": None,
            "breaks_in": [],
            "notes": [],
        }
    target_s = float(record.get("target_s") or st.settings.target_evac_indoor_s)
    items = [_item(st, it, target_s) for it in record.get("items") or [] if isinstance(it, dict)]
    pending = [i for i in items if i["status"] in PENDING]
    included = [i for i in items if i["included"]]
    left_out = [i for i in items if i["status"] not in PENDING and not i["included"]]
    rng: dict[str, Any] = {}
    for name in METRICS:
        values = [float(i["metrics"][name]) for i in included if i["metrics"][name] is not None]
        rng[name] = spread(values)
    breaks_in = [i["label"] for i in included if i["breaks"]]
    notes: list[str] = []
    if left_out:
        k = len(left_out)
        notes.append(
            f"{k} {_plural(k, 'run', 'runs')} did not finish and "
            f"{_plural(k, 'is', 'are')} left out of the range."
        )
    no_p95 = sum(1 for i in included if i["metrics"]["evac_time_p95_s"] is None)
    if no_p95:
        notes.append(
            f"In {no_p95} {_plural(no_p95, 'run', 'runs')} fewer than 95% of people got out "
            f"before the run stopped, so {_plural(no_p95, 'its', 'their')} evacuation time is "
            "left out."
        )
    if any(it.get("rerun_of") for it in record.get("items") or []):
        notes.append(
            "A setting changed after this test, so the plan as tested was simulated again "
            "with the current settings."
        )
    finished = not pending and not left_out and bool(included)
    return {
        **base,
        "key": record.get("key") or key,
        "status": "running" if pending else "done",
        "started_at": record.get("started_at"),
        "target_s": target_s,
        "items": items,
        "done": len(items) - len(pending),
        "total": len(items),
        "range": rng if included else None,
        "holds_in_all": (not breaks_in) if finished else None,
        "breaks_in": breaks_in,
        "notes": notes,
    }
