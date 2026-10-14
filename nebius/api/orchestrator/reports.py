"""Report bundles: everything an exporter needs, assembled from stored results only."""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlmodel import col, select

from api.core.assumptions import assumptions
from api.core.estimates import compute_estimates
from api.core.evidence import describe_run
from api.core.extensions import ReportBundle
from api.core.extensions.geometry import display_names
from api.core.plan import plan_hash
from api.core.settings import ROOT_DIR
from api.db.models import Run, SessionEventRow
from api.db.session import db_session
from api.models import Attack, Countdown, Fix, RunResult, Venue


def _result(row: Run | None) -> RunResult | None:
    if row is None or not row.result:
        return None
    try:
        return RunResult.model_validate(row.result)
    except ValueError:
        return None


def _calibration(template_id: str | None) -> dict[str, Any]:
    path = ROOT_DIR / "api" / "data" / "calibration.json"
    if not template_id or not path.exists():
        return {}
    data = json.loads(path.read_text())
    return dict(data.get(template_id, {}))


def humanizer(*venues: Venue | None) -> Callable[[str], str]:
    """Replace machine ids ("street_w", "door_e1") in model-written text with readable names.

    Only ids with "_" or a digit are replaced, so ordinary words that double as ids stay.
    """
    names = {k: v for k, v in display_names(*venues).items() if re.search(r"[_\d]", k)}
    if not names:
        return lambda text: text
    pattern = re.compile(
        r"\b(" + "|".join(map(re.escape, sorted(names, key=len, reverse=True))) + r")\b"
    )
    return lambda text: pattern.sub(lambda m: names[m.group(0)], text)


def build_bundle(st: Any, project_id: str, session_id: str | None = None) -> ReportBundle:
    """Bundle for a project: a red-team session if given (or the latest), else the stress test."""
    p = st.projects.get(project_id)
    s = st.settings
    session = (
        st.sessions.get(session_id)
        if session_id
        else next(
            (
                x
                for x in st.sessions.list_sessions(project_id)
                if x.status in ("finished", "stopped")
            ),
            None,
        )
    )
    summary: dict[str, Any] = dict(session.summary or {}) if session else {}
    version = session.venue_version if session else p.current_version
    venue = st.projects.venue(project_id, version)

    with db_session() as db:
        runs = list(
            db.exec(
                select(Run).where(Run.project_id == project_id).order_by(col(Run.created_at).desc())
            )
        )
    by_id = {r.id: r for r in runs}
    baseline = _result(by_id.get(summary.get("baseline_run_id", "")))
    if baseline is None:
        stress = next(
            (
                r
                for r in runs
                if r.tier == 3
                and r.venue_version == version
                and r.status in ("ok", "partial")
                and not r.attack_id
            ),
            None,
        )
        baseline = _result(stress)
    final = _result(by_id.get(summary.get("final_run_id") or ""))
    # runs of this session come from its event log (cached runs may belong to an earlier session)
    run_info: dict[str, dict[str, Any]] = {}
    nodes: dict[str, dict[str, Any]] = {}
    if session is not None:
        with db_session() as db:
            for ev in db.exec(
                select(SessionEventRow)
                .where(
                    SessionEventRow.session_id == session.id,
                    col(SessionEventRow.type).in_(["run_finished", "branch_node"]),
                )
                .order_by(col(SessionEventRow.seq))
            ):
                if ev.type == "run_finished":
                    run_info[str(ev.payload.get("run_id"))] = ev.payload
                else:  # a node's later events update it, as in the live view
                    nid = str(ev.payload.get("node_id"))
                    nodes[nid] = {**nodes.get(nid, {}), **ev.payload}
    with db_session() as db:
        rows = {rid: db.get(Run, rid) for rid in run_info}
    results = {rid: res for rid, r in rows.items() if (res := _result(r)) is not None}
    final_raw = summary.get("final_venue")
    human = humanizer(venue, Venue.model_validate(final_raw) if final_raw else None)
    attacks = [Attack.model_validate(a) for a in summary.get("attacks", [])]
    attacks = [a.model_copy(update={"title": human(a.title)}) for a in attacks]
    fixes = [Fix.model_validate(f) for f in summary.get("fixes", [])]
    fixes = [f.model_copy(update={"title": human(f.title)}) for f in fixes]
    countdown = Countdown.model_validate(summary["countdown"]) if summary.get("countdown") else None
    if countdown is not None and countdown.rset_source.startswith("run "):
        # sessions saved before the label existed: their countdown used the worst attack;
        # say what that run actually is instead of assuming it was a finished simulation
        used = _result(by_id.get(countdown.rset_source[4:].strip()))
        what = describe_run(used) if used is not None else countdown.rset_source
        countdown.rset_source = f"the worst red-team attack ({what})"
    fixed_venue = (
        Venue.model_validate(summary["final_venue"]) if summary.get("final_venue") else None
    )

    plan_venue = fixed_venue or venue
    t1 = st.runs.estimate(plan_venue)
    plan = t1.extensions.get("plan", {})
    sources: list[dict[str, str]] = []
    seen: set[str] = set()
    for a in attacks:
        url = str(a.inspired_by.source_url)
        if url not in seen:
            seen.add(url)
            sources.append(
                {"label": f"{a.inspired_by.incident} ({a.inspired_by.year or 'n.d.'})", "url": url}
            )
    for src in (venue.extensions or {}).get("sources", []):
        if src.get("url") not in seen:
            sources.append({"label": src.get("label", ""), "url": src.get("url", "")})
    sources.extend(
        [
            {"label": "JuPedSim crowd simulation", "url": "https://www.jupedsim.org"},
            {
                "label": "Crowd accidents 1900–2024 dataset (Feliciani et al.)",
                "url": "https://doi.org/10.5281/zenodo.19483010",
            },
            {"label": "Weather: Open-Meteo (CC BY 4.0)", "url": "https://open-meteo.com"},
        ]
    )
    summary_text = human(summary.get("judge_text") or _stress_summary(baseline))
    return ReportBundle(
        project_name=p.name,
        venue=venue,
        venue_version=version,
        baseline=baseline,
        final=final,
        attacks=attacks,
        fixes=fixes,
        results=results,
        accepted_fix_ids=list(summary.get("accepted_fixes", [])),
        countdown=countdown,
        assumptions=assumptions(s),
        sources=sources,
        exit_assignment=plan.get("groups", {}),
        stair_assignment=plan.get("stairs", {}),
        summary_text=summary_text,
        generated_at=datetime.now().isoformat(timespec="minutes"),
        session_id=session.id if session else None,
        density_danger_ppm2=s.density_danger_ppm2,
        density_warn_ppm2=s.density_warn_ppm2,
        provider_label=s.llm_label,
        tokens_total=session.tokens if session else 0,
        cost_usd=session.cost_usd if session else 0.0,
        scoreboard=list(summary.get("scoreboard", [])),
        recommendations=[human(r) for r in summary.get("recommendations", [])],
        worst_attack_id=summary.get("worst_attack_id"),
        before=summary.get("before") or {},
        after=summary.get("after") or {},
        fixed_venue=fixed_venue,
        calibration=_calibration(p.template_id),
        extras={
            "estimates": compute_estimates(
                plan_venue, st.registry, s, s.unit_costs or None
            ).model_dump(mode="json"),
            "tier1_plan_venue": "fixed" if fixed_venue else "current",
            "run_info": run_info,
            "measures": summary.get("measures", []),
            # typed evidence: evaluation status and the cost record (absent in old sessions)
            "evaluation": summary.get("evaluation"),
            "cost": summary.get("cost"),
            # before/after results of each kept fix, and the plan selected for handover
            "fix_evidence": fix_evidence(summary, nodes),
            "handover": _handover(st, project_id, session, summary, venue, plan_venue, plan),
        },
    )


def _side(node: dict[str, Any] | None) -> dict[str, Any] | None:
    """One side of a fix comparison: the run a branch node shows and what it is based on."""
    if not node or not node.get("run_id"):
        return None
    return {
        "run_id": node["run_id"],
        "basis": node.get("basis"),
        "tier": node.get("tier"),
        "fallback_for": node.get("fallback_for"),
        "metrics": node.get("metrics") or {},
    }


def fix_evidence(
    summary: dict[str, Any], nodes: dict[str, dict[str, Any]]
) -> dict[str, dict[str, Any]]:
    """Each kept fix's own test: its attack on the venue with the fixes kept before it
    (re-run when an earlier fix of the round was kept), then the same attack with the fix.
    Both are usually quick simulations; the combined plan is judged by `evaluation`."""
    fixes = {str(f.get("fix_id")): f for f in summary.get("fixes") or [] if isinstance(f, dict)}
    out: dict[str, dict[str, Any]] = {}
    for i, fid in enumerate(summary.get("accepted_fixes") or []):
        fx = fixes.get(str(fid))
        if fx is None:
            continue
        attack = fx.get("for_attack")
        before = nodes.get(f"atk:{attack}:current:{i}") or nodes.get(f"atk:{attack}")
        after = nodes.get(f"fix:{fid}")
        out[str(fid)] = {
            "attack_id": attack,
            "before": _side(before),
            "after": _side(after),
            "gain": (after or {}).get("gain"),
        }
    return out


def plan_state(
    current_hash: str, tested_hash: str | None, kept: int, applied: list[Any]
) -> tuple[str, dict[str, Any] | None]:
    """Where the selected plan (the current version) stands against a session's test.

    `untested` (no session), `pending` (tested; kept fixes not accepted yet), `tested`
    (tested; nothing to accept), `accepted` (the kept fixes, tested together),
    `accepted_subset` (some kept fixes, not tested together) or `stale` (changed since).
    """
    if tested_hash is None:
        return "untested", None
    if current_hash == tested_hash:
        return ("pending" if kept else "tested"), None
    for rec in reversed(applied):
        if isinstance(rec, dict) and rec.get("plan_hash") == current_hash:
            return ("accepted" if rec.get("tested_together") else "accepted_subset"), rec
    return "stale", None


def _handover(
    st: Any,
    project_id: str,
    session: Any,
    summary: dict[str, Any],
    tested: Venue,
    plan_venue: Venue,
    plan: dict[str, Any],
) -> dict[str, Any]:
    """The selected plan for the handover checklist: the project's current version, and how
    the session's evidence relates to it."""
    current = st.projects.version(project_id)
    selected = Venue.model_validate(current.venue)
    digest = plan_hash(selected)
    kept = [str(f) for f in summary.get("accepted_fixes") or []]
    state, record = plan_state(
        digest,
        plan_hash(tested) if session is not None else None,
        len(kept),
        list(summary.get("applied") or []),
    )
    if digest != plan_hash(plan_venue):
        try:  # the exit plan of the selected venue, for its map
            plan = st.runs.estimate(selected).extensions.get("plan", {})
        except Exception:
            plan = {}
    return {
        "version": current.version,
        "plan_hash": digest,
        "venue": selected.model_dump(mode="json"),
        "tested_version": session.venue_version if session is not None else None,
        "state": state,
        "applied": record,
        # kept fixes that are part of the selected plan, and the ones still waiting
        "fix_ids": list(record.get("fix_ids") or []) if record else [],
        "suggested_fix_ids": kept if state == "pending" else [],
        "exit_assignment": plan.get("groups", {}),
        "stair_assignment": plan.get("stairs", {}),
    }


def _stress_summary(r: RunResult | None) -> str:
    if r is None:
        return "No simulation has been run for this version yet. Run a stress test first."
    m = r.metrics
    parts = [f"Stress test of {m.agents_total:,} people."]
    if m.evac_time_p95_s is not None:
        parts.append(f"95% are out in {m.evac_time_p95_s:.0f} s.")
    parts.append(
        f"Peak density {m.peak_density_ppm2:.1f} people per m², above the danger level "
        f"for {m.time_above_danger_s:.0f} s."
    )
    return " ".join(parts)
