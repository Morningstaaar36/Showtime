"""Rewind the worst moment: branch many responses from one second.

A finished red-team session names its worst attack. Rewind reruns that attack on the tested
plan with a checkpoint at the moment of peak danger, then starts every branch from that
checkpoint: "do nothing" plus each response (the kept changes' staff measures and a few
quick actions). Locally the runner copies the checkpoint into each branch's folder; on Nebius
every branch is a snapshot child of the checkpoint run. All branches run in parallel (the
runner bounds how many) and each is compared with "do nothing" from the same second.

Records are kept as internal user settings (`_rewind:<id>`), so no table changes.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from datetime import UTC, datetime
from typing import Any

from api.adapters.sandbox import SimJob
from api.core.evidence import comparable
from api.core.extensions.breaks import evac_estimate
from api.core.plan import PlanError
from api.db.models import UserSetting
from api.db.session import db_session
from api.models import Attack, Fix, RunResult, ScenarioEventIn, Venue
from api.orchestrator.session import severity

log = logging.getLogger("showtime.rewind")

MAX_QUICK_ACTIONS = 3
MAX_RESPONSES = 6
_TASKS: dict[str, asyncio.Task[None]] = {}


# --- stored records (shared with the stress test) ---------------------------------------------
def save_record(st: Any, key: str, record: dict[str, Any]) -> None:
    """Store a JSON record under an internal settings key (never shown as a setting)."""
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, key) or UserSetting(key=key)
        row.value = record
        row.updated_at = datetime.now(UTC)
        s.add(row)
        s.commit()


def load_record(st: Any, key: str) -> dict[str, Any] | None:
    with db_session(st.projects.db_url) as s:
        row = s.get(UserSetting, key)
        return dict(row.value) if row and isinstance(row.value, dict) else None


def live_or_interrupted(record: dict[str, Any] | None, tasks: dict[str, Any]) -> Any:
    """A record still marked running whose task is gone was cut off by a restart."""
    if record and record.get("status") == "running" and record.get("id") not in tasks:
        record = {**record, "status": "interrupted", "message": "The server restarted first."}
    return record


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


# --- choosing the moment and the responses -----------------------------------------------------
def peak_moment(run: RunResult) -> dict[str, Any]:
    """The moment of peak danger in a run: its densest hotspot (danger ones first)."""
    hot = [h for h in run.hotspots if h.level == "danger"] or list(run.hotspots)
    if hot:
        h = max(hot, key=lambda x: (x.peak_density_ppm2, -x.t_s))
        near = f" near {h.near}" if h.near else ""
        return {
            "at_s": round(max(1.0, h.t_s), 1),
            "why": f"peak density {h.peak_density_ppm2:.1f} people per m²{near} at {h.t_s:.0f} s",
            "source": "hotspot",
        }
    est = evac_estimate(run)
    if est:
        return {
            "at_s": round(max(1.0, est / 2), 1),
            "why": "no crowding hotspot was recorded, so halfway through the evacuation",
            "source": "evacuation_time",
        }
    return {"at_s": 60.0, "why": "no crowding was recorded, so one minute in", "source": "default"}


def _shift(events: list[ScenarioEventIn], at_s: float) -> list[ScenarioEventIn]:
    """Events that start no earlier than the rewind moment."""
    out = []
    for ev in events:
        data = ev.model_dump()
        data["at_s"] = max(float(data.get("at_s") or 0.0), at_s)
        out.append(ScenarioEventIn.model_validate(data))
    return out


def suggest_responses(
    venue: Venue, attack: Attack, kept: list[Fix], run: RunResult | None, at_s: float
) -> tuple[list[dict[str, Any]], list[str]]:
    """The kept changes' staff measures, then a few quick actions. Returns (responses, notes)."""
    responses: list[dict[str, Any]] = []
    notes: list[str] = []
    for fx in kept:
        if not fx.operational:
            notes.append(
                f"“{fx.title}” changes the building, which can't start in the middle of the "
                "event, so it is not a branch."
            )
            continue
        responses.append(
            {
                "key": f"fix:{fx.fix_id}",
                "label": f"Kept change: {fx.title}",
                "kind": "kept_fix",
                "events": [e.model_dump() for e in _shift(fx.operational, at_s)],
            }
        )
    exits = {e.id: e for f in venue.floors for e in f.exits}
    name = {i: (e.label or i) for i, e in exits.items()}
    quick: list[dict[str, Any]] = []
    closed = [
        str(e.model_dump().get("exit_id"))
        for e in attack.events
        if e.type == "block_exit" and e.model_dump().get("exit_id") in exits
    ]
    closed += [i for i, e in exits.items() if e.blocked and i not in closed]
    for ex in closed[:1]:
        quick.append(
            {
                "key": f"open:{ex}",
                "label": f"Open {name[ex]} again",
                "kind": "quick_action",
                "events": [{"type": "unblock_exit", "exit_id": ex, "at_s": at_s}],
            }
        )
    open_ids = [i for i, e in exits.items() if not e.blocked and i not in closed]
    loads = {p.exit_id: p.people for p in (run.metrics.per_exit if run else [])}
    hot_exit = next(
        (
            h.near
            for h in sorted(run.hotspots if run else [], key=lambda h: -h.peak_density_ppm2)
            if h.near in open_ids
        ),
        None,
    )
    busiest = hot_exit or (max(open_ids, key=lambda i: loads.get(i, 0)) if open_ids else None)
    others = [i for i in open_ids if i != busiest]
    if busiest and others:
        calm = min(others, key=lambda i: loads.get(i, 0))
        quick.append(
            {
                "key": f"stewards:{busiest}:{calm}",
                "label": f"Send stewards to move people from {name[busiest]} to {name[calm]}",
                "kind": "quick_action",
                "events": [
                    {
                        "type": "marshal_redirect",
                        "from_exit_id": busiest,
                        "to_exit_id": calm,
                        "fraction": 0.4,
                        "at_s": at_s,
                        "speech": f"This way to {name[calm]}!",
                    }
                ],
            }
        )
    zones = sorted((z for f in venue.floors for z in f.zones), key=lambda z: -z.people)
    if zones:
        z = zones[0]
        quick.append(
            {
                "key": f"hold:{z.id}",
                "label": f"Hold {z.label or z.id} back for one minute",
                "kind": "quick_action",
                "events": [
                    {"type": "staggered_release", "zone_id": z.id, "delay_s": 60, "at_s": at_s}
                ],
            }
        )
    return (responses + quick[:MAX_QUICK_ACTIONS])[:MAX_RESPONSES], notes


# --- comparing branches ------------------------------------------------------------------------
def numbers(r: RunResult | None) -> dict[str, Any]:
    """The four compared numbers of one branch, as the simulation reported them."""
    if r is None:
        return {}
    m = r.metrics
    est = evac_estimate(r)
    return {
        "evac_time_95_s": round(est, 1) if est is not None else None,
        "evac_is_estimate": m.evac_time_p95_s is None and est is not None,
        "people_inside": m.agents_not_evacuated,
        "peak_density_ppm2": m.peak_density_ppm2,
        "time_above_danger_s": m.time_above_danger_s,
    }


def _delta(a: Any, b: Any) -> float | None:
    if isinstance(a, int | float) and isinstance(b, int | float):
        return round(float(a) - float(b), 1)
    return None


def compare(base: RunResult | None, branches: list[dict[str, Any]], warn_ppm2: float) -> str | None:
    """Fill each branch's change against "do nothing"; returns the key of the best response.

    Only a finished branch whose evidence is comparable with "do nothing" can be best, and
    only when it is better by the session's severity measure.
    """
    base_n = numbers(base)
    best: tuple[float, str] | None = None
    for b in branches:
        r: RunResult | None = b.pop("_result", None)
        if r is None:
            continue
        n = numbers(r)
        b["metrics"] = n
        b["basis"] = r.basis
        b["status"] = r.status
        b["error"] = r.error
        if b["key"] == "nothing" or base is None:
            continue
        b["vs_nothing"] = {
            k: _delta(n.get(k), base_n.get(k)) for k in base_n if k != "evac_is_estimate"
        }
        b["comparable"] = comparable(base, r)
        usable = r.status in ("ok", "partial") and b["comparable"]
        if usable and severity(r, warn_ppm2) < severity(base, warn_ppm2):
            b["better"] = True
            if best is None or severity(r, warn_ppm2) < best[0]:
                best = (severity(r, warn_ppm2), b["key"])
        else:
            b["better"] = False
    return best[1] if best else None


# --- the rewind itself -----------------------------------------------------------------------
class RewindError(ValueError):
    """The session can't be rewound (no worst attack, still running...)."""


def _nodes(st: Any, session_id: str) -> dict[str, str]:
    """Tree node id -> run id of a session (branches it skipped are left out)."""
    nodes: dict[str, str] = {}
    for ev in st.sessions.stored_events(session_id):
        p = ev.payload
        if ev.type == "branch_node" and p.get("run_id") and not p.get("skipped"):
            nodes[str(p.get("node_id"))] = str(p["run_id"])
    return nodes


def _finished(st: Any, rid: str | None) -> RunResult | None:
    row = st.runs.get(rid) if rid else None
    if row is None or not row.result or row.status not in ("ok", "partial"):
        return None
    return RunResult.model_validate(row.result)


def _source_run(st: Any, session_id: str, worst_id: str) -> tuple[str | None, RunResult | None]:
    """The run that showed the worst attack: its confirmation before fixes, else its test."""
    nodes = _nodes(st, session_id)
    for node in ("final:before", f"atk:{worst_id}"):
        res = _finished(st, nodes.get(node))
        if res is not None:
            return node, res
    return None, None


def _hardest_attack(st: Any, session_id: str) -> str | None:
    """When no attack broke the plan: the attack whose test run came out worst."""
    best: tuple[float, str] | None = None
    warn_ppm2 = st.settings.density_warn_ppm2
    for node, rid in _nodes(st, session_id).items():
        if not node.startswith("atk:") or node.count(":") != 1:
            continue
        res = _finished(st, rid)
        if res is not None and (best is None or severity(res, warn_ppm2) > best[0]):
            best = (severity(res, warn_ppm2), node.split(":", 1)[1])
    return best[1] if best else None


def start_rewind(
    st: Any,
    session_id: str,
    at_s: float | None = None,
    responses: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Create the rewind record and start it in the background; returns the record."""
    row = st.sessions.get(session_id)
    if row is None:
        raise LookupError(f"Session {session_id} does not exist.")
    summary = row.summary or {}
    if row.status not in ("finished", "stopped") or not summary:
        raise RewindError("Rewind needs a finished test.")
    worst_id = summary.get("worst_attack_id")
    hardest = False
    if not worst_id:
        worst_id, hardest = _hardest_attack(st, session_id), True
    attack = next(
        (
            Attack.model_validate(a)
            for a in summary.get("attacks") or []
            if a.get("attack_id") == worst_id
        ),
        None,
    )
    if attack is None:
        raise RewindError("This test has no finished attack run, so there is no moment to rewind.")
    venue: Venue = st.projects.venue(row.project_id, row.venue_version)
    rid = f"rw_{uuid.uuid4().hex[:10]}"
    record: dict[str, Any] = {
        "id": rid,
        "session_id": session_id,
        "project_id": row.project_id,
        "venue_version": row.venue_version,
        "attack": {"attack_id": attack.attack_id, "title": attack.title},
        "status": "running",
        "message": None,
        "created_at": now_iso(),
        "finished_at": None,
        "moment": None,
        "source_run_id": None,
        "checkpoint_run_id": None,
        "tier": None,
        "done": 0,
        "total": 0,
        "branches": [],
        "best": None,
        "notes": [],
        "hardest_not_breaking": hardest,
    }
    if len(venue.floors) > 1:
        record.update(
            status="unsupported",
            finished_at=now_iso(),
            message=f"Rewind needs a single-floor venue: this one has {len(venue.floors)} "
            "floors, and saving the crowd mid-run works on one floor only for now.",
        )
        _save(st, record)
        return record
    _save(st, record)
    _TASKS[rid] = asyncio.create_task(
        _run(
            st,
            record,
            venue,
            attack,
            summary,
            int(row.config.get("seed", st.settings.default_seed)),
            at_s,
            responses,
        )
    )
    return record


def _save(st: Any, record: dict[str, Any]) -> None:
    save_record(st, f"_rewind:{record['id']}", record)
    save_record(st, f"_rewind_latest:{record['session_id']}", {"id": record["id"]})


def get_rewind(st: Any, rewind_id: str) -> dict[str, Any] | None:
    rec = load_record(st, f"_rewind:{rewind_id}")
    return live_or_interrupted(rec, _TASKS)  # type: ignore[no-any-return]


def latest_rewind(st: Any, session_id: str) -> dict[str, Any] | None:
    ref = load_record(st, f"_rewind_latest:{session_id}")
    return get_rewind(st, str(ref["id"])) if ref else None


async def _run(
    st: Any,
    record: dict[str, Any],
    venue: Venue,
    attack: Attack,
    summary: dict[str, Any],
    seed: int,
    at_s: float | None,
    chosen: list[dict[str, Any]] | None,
) -> None:
    try:
        await _rewind(st, record, venue, attack, summary, seed, at_s, chosen)
    except asyncio.CancelledError:
        record.update(status="cancelled", message="Cancelled.")
        raise
    except Exception as exc:  # a rewind must always end with a readable record
        log.exception("rewind %s failed", record["id"])
        record.update(status="failed", message=f"The rewind couldn't finish: {exc}")
    finally:
        record["finished_at"] = now_iso()
        _save(st, record)
        _TASKS.pop(record["id"], None)


async def _rewind(
    st: Any,
    record: dict[str, Any],
    venue: Venue,
    attack: Attack,
    summary: dict[str, Any],
    seed: int,
    at_s: float | None,
    chosen: list[dict[str, Any]] | None,
) -> None:
    sid, pid, version = record["session_id"], record["project_id"], record["venue_version"]
    _node, source = _source_run(st, sid, attack.attack_id)
    moment: dict[str, Any]
    if at_s is not None:
        moment = {"at_s": round(float(at_s), 1), "why": "the moment you chose", "source": "user"}
    elif source is not None:
        moment = peak_moment(source)
    else:
        raise RewindError("The worst attack has no finished run to find its worst moment in.")
    t = float(moment["at_s"])
    if source is not None:
        moment["run_id"] = source.run_id
    # full simulations, so every branch reports evacuation time and people still inside
    tier = 3
    record.update(moment=moment, source_run_id=source.run_id if source else None, tier=tier)

    fixes = {f["fix_id"]: Fix.model_validate(f) for f in summary.get("fixes") or []}
    kept = [fixes[f] for f in summary.get("accepted_fixes") or [] if f in fixes]
    if chosen:
        responses = [
            {
                "key": f"custom:{i + 1}",
                "label": str(c.get("label") or f"Response {i + 1}"),
                "kind": "custom",
                "events": [
                    e.model_dump()
                    for e in _shift(
                        [ScenarioEventIn.model_validate(e) for e in c.get("events") or []], t
                    )
                ],
            }
            for i, c in enumerate(chosen[:MAX_RESPONSES])
        ]
        notes: list[str] = []
    else:
        responses, notes = suggest_responses(venue, attack, kept, source, t)
    if record.get("hardest_not_breaking"):
        notes.insert(0, "No attack broke the plan, so this rewinds the attack that came out worst.")
    record["notes"] = notes
    _save(st, record)

    # 1. the checkpoint: the worst attack again, saving the crowd at the chosen second
    ckpt_job = st.runs.build_job(
        venue,
        tier=tier,
        seed=seed,
        attack=attack,
        checkpoint_at_s=t,
        parent_run_id=source.run_id if source else None,
    )
    ckpt_job.request.extensions["rewind_id"] = record["id"]
    ckpt_label = f"Rewind · checkpoint at {t:.0f} s · {attack.title}"
    ckpt = await st.runs.run(ckpt_job, pid, version, sid, ckpt_label)
    record["checkpoint_run_id"] = ckpt.run_id
    if ckpt.status not in ("ok", "partial"):
        record.update(
            status="failed",
            message=f"The checkpoint run didn't finish ({ckpt.status}): {ckpt.error or ''}".strip(),
        )
        return

    # 2. every branch from that second, all at once
    branches: list[dict[str, Any]] = [
        {"key": "nothing", "label": "Do nothing", "kind": "nothing", "events": []},
        *responses,
    ]
    jobs: list[tuple[SimJob, str]] = []
    runnable: list[dict[str, Any]] = []
    for b in branches:
        try:
            job = st.runs.build_job(
                venue,
                tier=tier,
                seed=seed,
                attack=attack,
                extra=[ScenarioEventIn.model_validate(e) for e in b["events"]],
                resume_from=ckpt.run_id,
                parent_run_id=ckpt.run_id,
            )
        except (PlanError, ValueError) as exc:
            problems = getattr(exc, "problems", None) or [str(exc)]
            b.update(status="not_possible", error=str(problems[0]))
            continue
        job.request.extensions.update({"rewind_id": record["id"], "rewind_at_s": t})
        b.update(run_id=job.request.run_id, status="queued")
        jobs.append((job, f"Rewind · {b['label']} (from {t:.0f} s)"))
        runnable.append(b)
    record.update(branches=branches, total=len(jobs), done=0)
    _save(st, record)

    def on_done(i: int, res: RunResult) -> None:
        runnable[i]["status"] = res.status
        record["done"] = int(record["done"]) + 1
        _save(st, record)

    results = await st.runs.run_many(jobs, pid, version, sid, on_done=on_done)
    for b, r in zip(runnable, results, strict=True):
        b["_result"] = r
    base = next((r for b, r in zip(runnable, results, strict=True) if b["key"] == "nothing"), None)
    record["best"] = compare(base, branches, st.settings.density_warn_ppm2)
    record["status"] = "done"
    if base is None or base.status not in ("ok", "partial"):
        record["message"] = "The “do nothing” branch didn't finish, so nothing can be compared."
