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
from api.core.extensions import ReportBundle
from api.core.extensions.geometry import display_names
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
    if session is not None:
        with db_session() as db:
            for ev in db.exec(
                select(SessionEventRow).where(
                    SessionEventRow.session_id == session.id, SessionEventRow.type == "run_finished"
                )
            ):
                run_info[str(ev.payload.get("run_id"))] = ev.payload
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
        # sessions saved before the label existed; their countdown always used the worst attack
        countdown.rset_source = (
            f"the worst red-team attack, confirmed by simulation ({countdown.rset_source})"
        )
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
        },
    )


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
