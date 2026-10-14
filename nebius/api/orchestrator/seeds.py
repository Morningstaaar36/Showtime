"""Ranges across seeds (N05): the plan's key run again with a few more seeds.

One simulation is one sample of a random process (who walks how fast, who starts where). This
repeats the run Your plan's verdict rests on with more seeds: the confirmation run of the kept
fixes under the worst attack, or the baseline when nothing was kept. Venue, events and tier stay
the same; only the seed changes, and it is part of each run's identity, so every seed is a
normal run and repeating the check reuses them.

The range (min–max and median) covers evacuation time (95%), peak density and people still
inside, over the runs that finished. Runs that did not finish stay listed with their status and
are left out of the range, with a note that says so.
"""

from __future__ import annotations

import logging
import statistics
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from api.core.plan import PlanError
from api.core.venue_ops import PatchError
from api.db.models import UserSetting
from api.db.session import db_session
from api.models import Attack, RunResult, ScenarioEventIn, Venue

log = logging.getLogger("showtime.seeds")

MAX_EXTRA = 5
DEFAULT_LOCAL = 3
METRICS = ("evac_time_p95_s", "peak_density_ppm2", "agents_not_evacuated")
USABLE = ("ok", "partial")
PENDING = ("queued", "running")

Side = Literal["after", "baseline"]


class SeedCheckError(Exception):
    """The seed check can't start; the message says why in organizer words."""


@dataclass(frozen=True)
class KeyRun:
    """The run to repeat, and everything needed to rebuild it with another seed."""

    side: Side
    run_id: str
    venue: Venue
    tier: int
    seed: int
    attack: Attack | None
    extra: list[ScenarioEventIn]
    label: str
    venue_version: int

    def info(self) -> dict[str, Any]:
        """What the check repeats (for the UI)."""
        return {
            "side": self.side,
            "run_id": self.run_id,
            "label": self.label,
            "tier": self.tier,
            "seed": self.seed,
            "attack_title": self.attack.title if self.attack else None,
        }


def default_extra(settings: Any) -> int:
    """Extra seeds when the organizer doesn't choose: more where sandboxes run in parallel."""
    return MAX_EXTRA if getattr(settings, "sandbox_provider", "") == "nebius" else DEFAULT_LOCAL


def _key(session_id: str) -> str:
    return f"_seeds:{session_id}"


def _attempt(st: Any, run_id: str) -> Any:
    """The run row of a simulation attempt (an estimate shown in its place points to it)."""
    row = st.runs.get(run_id)
    failed = ((row.result or {}).get("extensions") or {}).get("fallback_for") if row else None
    return st.runs.get(str(failed)) if failed else row


def _seed_of(row: Any, default: int) -> int:
    seed = (row.request or {}).get("seed") if row is not None else None
    return int(seed) if isinstance(seed, int | float) else default


def key_run(st: Any, session: Any) -> KeyRun:
    """The plan's key confirmation run: after the kept fixes, or the baseline."""
    summary: dict[str, Any] = dict(session.summary or {})
    if session.status not in ("finished", "stopped") or not summary:
        raise SeedCheckError("This test hasn't finished yet, so there is no result to repeat.")
    default_seed = int((session.config or {}).get("seed", st.settings.default_seed))
    evaluation = summary.get("evaluation") or {}
    after_id = evaluation.get("after_run_id") or summary.get("final_run_id")
    worst = summary.get("worst_attack_id")
    if after_id and worst and summary.get("final_venue"):
        attack = next(
            (
                Attack.model_validate(a)
                for a in summary.get("attacks") or []
                if isinstance(a, dict) and a.get("attack_id") == worst
            ),
            None,
        )
        if attack is not None:
            row = _attempt(st, str(after_id))
            return KeyRun(
                side="after",
                run_id=row.id if row is not None else str(after_id),
                venue=Venue.model_validate(summary["final_venue"]),
                tier=row.tier if row is not None and row.tier in (2, 3) else 3,
                seed=_seed_of(row, default_seed),
                attack=attack,
                extra=[ScenarioEventIn.model_validate(e) for e in summary.get("measures") or []],
                label=(row.label if row is not None and row.label else "")
                or f"After fixes · {attack.title}",
                venue_version=session.venue_version,
            )
    base_id = summary.get("baseline_run_id")
    if base_id:
        row = _attempt(st, str(base_id))
        return KeyRun(
            side="baseline",
            run_id=row.id if row is not None else str(base_id),
            venue=st.projects.venue(session.project_id, session.venue_version),
            tier=row.tier if row is not None and row.tier in (2, 3) else 3,
            seed=_seed_of(row, default_seed),
            attack=None,
            extra=[],
            label=(row.label if row is not None and row.label else "") or "Baseline",
            venue_version=session.venue_version,
        )
    raise SeedCheckError("This test recorded no simulation to repeat.")


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


def start_seed_check(st: Any, session: Any, n: int | None = None) -> dict[str, Any]:
    """Submit the key run with `n` more seeds (default 3 locally, at most 5).

    Seeds are the key run's seed + 1 … + n. When the key run can no longer be rebuilt exactly
    (a setting changed since the test), its seed is run again too, so all seeds share inputs.
    """
    key = key_run(st, session)
    count = max(1, min(MAX_EXTRA, n or default_extra(st.settings)))

    def build(seed: int) -> Any:
        try:
            job = st.runs.build_job(
                key.venue,
                tier=key.tier,
                seed=seed,
                attack=key.attack,
                extra=key.extra,
                parent_run_id=key.run_id,
            )
        except (PlanError, PatchError, ValueError) as exc:
            problems = getattr(exc, "problems", None) or getattr(exc, "issues", None) or [exc]
            first = problems[0]
            raise SeedCheckError(
                "The tested plan can't be simulated again: " + str(getattr(first, "message", first))
            ) from exc
        job.request.extensions["events"] = job.events
        return job

    def submit(job: Any, seed: int) -> str:
        return str(
            st.runs.submit(
                job,
                project_id=session.project_id,
                venue_version=key.venue_version,
                session_id=session.id,
                label=f"{key.label} · seed {seed}"[:120],
            )
        )

    probe = build(key.seed)
    items: list[dict[str, Any]] = []
    if probe.request.run_id == key.run_id:
        items.append({"seed": key.seed, "run_id": key.run_id, "original": True})
    else:  # same seed, current settings: run it again so the range compares like with like
        items.append(
            {
                "seed": key.seed,
                "run_id": submit(probe, key.seed),
                "original": False,
                "rerun_of": key.run_id,
            }
        )
    for i in range(1, count + 1):
        seed = key.seed + i
        items.append({"seed": seed, "run_id": submit(build(seed), seed), "original": False})
    record = {
        "session_id": session.id,
        "key": key.info(),
        "n_extra": count,
        "items": items,
        "started_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
    _save(st, session.id, record)
    log.info("seed check %s: %s with %d more seeds", session.id, key.run_id, count)
    return seed_check_status(st, session)


def spread(values: list[float]) -> dict[str, float | int] | None:
    """Min, max and median of the values (None when there are none)."""
    if not values:
        return None
    return {
        "min": min(values),
        "max": max(values),
        "median": float(statistics.median(values)),
        "n": len(values),
    }


def _plural(n: int, one: str, many: str) -> str:
    return one if n == 1 else many


def _item(st: Any, it: dict[str, Any]) -> dict[str, Any]:
    out: dict[str, Any] = {
        "seed": it.get("seed"),
        "run_id": it.get("run_id"),
        "original": bool(it.get("original")),
        "status": "missing",
        "basis": "unknown",
        "tier": None,
        "progress": None,
        "metrics": None,
        "error": None,
        "included": False,
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
    return out


def seed_check_status(st: Any, session: Any) -> dict[str, Any]:
    """The latest seed check of a session: each run and the range over the finished ones."""
    try:
        key: dict[str, Any] | None = key_run(st, session).info()
        reason = None
    except SeedCheckError as exc:
        key, reason = None, str(exc)
    base: dict[str, Any] = {
        "session_id": session.id,
        "available": key is not None,
        "reason": reason,
        "key": key,
        "default_extra": default_extra(st.settings),
        "max_extra": MAX_EXTRA,
    }
    record = _load(st, session.id)
    if record is None:
        return {
            **base,
            "status": "none",
            "n_extra": 0,
            "items": [],
            "done": 0,
            "total": 0,
            "range": None,
            "bases": {},
            "notes": [],
        }
    items = [_item(st, it) for it in record.get("items") or [] if isinstance(it, dict)]
    pending = [i for i in items if i["status"] in PENDING]
    included = [i for i in items if i["included"]]
    left_out = [i for i in items if i["status"] not in PENDING and not i["included"]]
    rng: dict[str, Any] = {}
    for name in METRICS:
        values = [float(i["metrics"][name]) for i in included if i["metrics"][name] is not None]
        rng[name] = spread(values)
    bases: dict[str, int] = {}
    for i in included:
        bases[i["basis"]] = bases.get(i["basis"], 0) + 1
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
    rerun = next((it for it in record.get("items") or [] if it.get("rerun_of")), None)
    if rerun is not None:
        notes.append(
            f"A setting changed after this test, so seed {rerun['seed']} was simulated again "
            "with the current settings."
        )
    return {
        **base,
        "key": record.get("key") or key,
        "status": "running" if pending else "done",
        "n_extra": int(record.get("n_extra") or 0),
        "started_at": record.get("started_at"),
        "items": items,
        "done": len(items) - len(pending),
        "total": len(items),
        "range": rng if included else None,
        "bases": bases,
        "notes": notes,
    }
