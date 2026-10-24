"""Agent routes: text edits (Venue agent). Sessions, reports and Ask are added alongside."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from api.adapters.llm import BudgetExceeded, LLMError
from api.agents.base import AgentEnv, AgentUnavailable
from api.agents.venue import propose_edit
from api.app.errors import ApiException
from api.app.routes_core import get_state
from api.app.routes_projects import _after_edit
from api.app.state import AppState
from api.core.venue_ops import PatchError
from api.models import RunResult, ScenarioEventIn, Venue
from api.orchestrator import together
from api.orchestrator.session import (
    FixConflict,
    FixSelectionError,
    SessionConfigError,
    StalePlan,
)

router = APIRouter(prefix="/api/v1")
log = logging.getLogger("showtime.api")


class EditIn(BaseModel):
    """A typed change request."""

    text: str = Field(min_length=2, max_length=500)
    apply: bool = True


TOOL_LABELS: dict[str, str] = {
    "simulator": "Crowd simulator (JuPedSim) in a sealed sandbox",
    "instant_estimate": "Instant estimate (network flow, milliseconds)",
    "solver": "Layout solver (a design becomes exact geometry)",
    "map": "OpenStreetMap sites",
    "incidents": "388 real crowd accidents, 1900–2024",
    "edit_ops": "Validated venue edits",
    "scenario_events": "Scenario events (blocked exit, surge, smoke, …)",
    "number_check": "Number check (only numbers the tools produced)",
}


@router.get("/agents")
async def list_agents(st: AppState = Depends(get_state)) -> dict[str, Any]:
    """The AI team: every Nemotron agent, the model it runs on now, what it decides and the
    tools it may use; and the sandbox every simulation runs in."""
    from api.agents.team import TEAM

    sandbox = await st.runner.health()
    return {
        "provider": st.settings.llm_label,
        "agents": [
            {
                "name": m.agent.name,
                "label": m.label,
                "stage": m.stage,
                "decides": m.decides,
                "role": m.agent.role,
                "model": st.llm.model_for(m.agent.role),
                "prompt_version": m.agent.prompt_version,
                "tools": list(m.tools),
            }
            for m in TEAM
        ],
        "tools": TOOL_LABELS,
        "sandbox": {
            "provider": st.settings.sandbox_provider,
            "ok": bool(sandbox.get("ok")),
            "detail": str(sandbox.get("detail", "")),
            "isolation": "no network, memory and CPU limits, one container per scenario",
        },
    }


@router.post("/projects/{project_id}/edit")
async def edit_by_text(
    project_id: str, body: EditIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Venue agent: plain language → validated patch (applied unless apply=false)."""
    venue = st.projects.venue(project_id)
    env = AgentEnv(llm=st.llm, project_id=project_id)
    try:
        out = await propose_edit(env, st.registry, venue, body.text)
    except BudgetExceeded as exc:
        raise ApiException(429, "budget", str(exc), "Raise the token budget in Settings.") from exc
    except (LLMError, AgentUnavailable) as exc:
        raise ApiException(
            503,
            "llm_unavailable",
            "The language model isn't answering.",
            "Start the local model with: make llm-up",
        ) from exc
    call = out.call
    agent = {
        "model": call.model if call else "",
        "prompt_version": "venue",
        "tokens": (call.usage.prompt_tokens + call.usage.completion_tokens)
        if call and call.usage
        else 0,
        "cost_usd": call.usage.cost_usd if call and call.usage else 0.0,
    }
    resp: dict[str, Any] = {
        "status": out.status,
        "patch": None,
        "questions": out.questions,
        "explanation": out.explanation,
        "version": None,
        "validation": None,
        "agent": agent,
        "problems": out.problems,
    }
    if out.patch is not None:
        resp["patch"] = out.patch.model_dump(mode="json")
    if out.status == "proposed" and out.patch is not None and body.apply:
        try:
            row, _ = st.projects.apply(project_id, out.patch, out.explanation, author="agent")
        except PatchError as exc:
            resp.update(status="failed", explanation=exc.problems[0])
            return resp
        resp.update(_after_edit(st, project_id, row))
        resp["status"] = "applied"
    return resp


# --- Red Team Night sessions --------------------------------------------------------------


def session_out(row: Any) -> dict[str, Any]:
    """Session row as JSON."""
    summary = dict(row.summary or {})
    summary.pop("final_venue", None)  # large; fetched via /apply or the bundle
    return {
        "id": row.id,
        "project_id": row.project_id,
        "venue_version": row.venue_version,
        "status": row.status,
        "config": row.config,
        "summary": summary or None,
        "tokens": row.tokens,
        "cost_usd": row.cost_usd,
        "created_at": row.created_at.isoformat(),
        "finished_at": row.finished_at.isoformat() if row.finished_at else None,
        "error": row.error,
    }


class SessionIn(BaseModel):
    """Start Red Team Night."""

    project_id: str
    config: dict[str, Any] = Field(default_factory=dict)


@router.post("/sessions", status_code=201)
async def start_session(body: SessionIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Start a red-team session on the project's current venue."""
    from api.core.geometry import validate_venue

    venue = st.projects.venue(body.project_id)
    rep = validate_venue(venue)
    if not rep.ok:
        raise ApiException(
            422,
            "venue_invalid",
            f"Red team can't start: {rep.errors[0].message}",
            rep.errors[0].hint,
        )
    running = [
        s
        for s in st.sessions.list_sessions(body.project_id)
        if s.status == "running"
        and s.id in st.sessions.live
        and not st.sessions.live[s.id].finished
    ]
    if running:
        return session_out(running[0])
    try:
        return session_out(st.sessions.start(body.project_id, body.config))
    except SessionConfigError as exc:
        raise ApiException(
            422,
            "invalid_config",
            f"Red team can't start: {exc}",
            "Use whole numbers in range for rounds, attacks, fixes and budgets.",
            {"errors": exc.errors},
        ) from exc


def _live_status(st: AppState, row: Any) -> Any:
    """A session stored as running that this server is not running stopped with a restart."""
    live = st.sessions.live.get(row.id)
    if row.status == "running" and (live is None or live.finished):
        row.status = "stopped"  # server restarted mid-session
    return row


@router.get("/sessions/{session_id}")
def get_session(session_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    row = st.sessions.get(session_id)
    if row is None:
        raise ApiException(404, "not_found", f"Session {session_id} does not exist.")
    return session_out(_live_status(st, row))


@router.get("/projects/{project_id}/sessions")
def list_sessions(project_id: str, st: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    return [session_out(_live_status(st, s)) for s in st.sessions.list_sessions(project_id)]


@router.get("/sessions/{session_id}/events")
async def session_events(session_id: str, after: int = 0, st: AppState = Depends(get_state)) -> Any:
    """Server-sent events: replay from `after`, then live until the session ends."""
    import json as _json

    from sse_starlette.sse import EventSourceResponse

    if st.sessions.get(session_id) is None:
        raise ApiException(404, "not_found", f"Session {session_id} does not exist.")

    async def gen() -> Any:
        async for ev in st.sessions.stream(session_id, after):
            yield {"id": str(ev.seq), "event": "message", "data": _json.dumps(ev.model_dump())}
        yield {"event": "end", "data": "{}"}

    return EventSourceResponse(gen(), ping=15)


@router.get("/sessions/{session_id}/archive")
def session_archive(session_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """The red team's failure map (quality-diversity archive): hazard kind × where, with the
    strongest simulated attacks per cell, coverage and QD-score (docs/RAINBOW.md). Live while
    the session runs, from the summary once it has finished."""
    row = st.sessions.get(session_id)
    if row is None:
        raise ApiException(404, "not_found", f"Session {session_id} does not exist.")
    live = st.sessions.live.get(session_id)
    snap = live.archive if live is not None else None
    if snap is None and row.summary:
        snap = row.summary.get("archive")
    if snap is None:
        stored = [e for e in st.sessions.stored_events(session_id) if e.type == "archive"]
        snap = stored[-1].payload.get("archive") if stored else None
    if snap is None:
        raise ApiException(
            404,
            "no_archive",
            "This session has no failure map yet.",
            "Sessions started before the failure map existed have none: run the red team again.",
        )
    return {"session_id": session_id, "status": row.status, **snap}


@router.post("/sessions/{session_id}/stop")
def stop_session(session_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    st.sessions.stop(session_id)
    return get_session(session_id, st)


class ApplyIn(BaseModel):
    """Which kept fixes to accept; every kept fix when `fix_ids` is left out."""

    fix_ids: list[str] | None = Field(default=None, max_length=100)


@router.post("/sessions/{session_id}/apply")
async def apply_session(
    session_id: str, body: ApplyIn | None = None, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Save the session's fixed plan, or only the chosen kept fixes, as a new version.

    The response's `applied` says which fixes the new version contains and whether they
    were tested together. A subset was not, so this starts simulating it together under the
    worst attack (`applied.together`; follow it at GET /sessions/{id}/together).

    Async on purpose: that run starts as a task on the server's event loop.
    """
    try:
        row = st.sessions.apply_final(session_id, body.fix_ids if body else None)
    except StalePlan as exc:
        raise ApiException(409, "stale_plan", str(exc)) from exc
    except FixConflict as exc:
        raise ApiException(
            409, "fixes_conflict", str(exc), "Choose the changes together, or accept all of them."
        ) from exc
    except FixSelectionError as exc:
        raise ApiException(422, "invalid_fix_selection", str(exc)) from exc
    except ValueError as exc:
        raise ApiException(409, "no_plan", str(exc)) from exc
    srow = st.sessions.get(session_id)
    records = ((srow.summary or {}) if srow else {}).get("applied") or [None]
    if records[-1] and not records[-1].get("tested_together"):
        try:
            records[-1] = together.start_together_check(st, srow)["record"]
        except together.TogetherCheckError as exc:
            log.info("together check for %s not started: %s", session_id, exc)
    return _after_edit(st, row.project_id, row, {"applied": records[-1]})


# --- Reports and exports -----------------------------------------------------------------


def _export(st: AppState, project_id: str, exporter_id: str, session_id: str | None) -> Any:
    from fastapi.responses import Response

    from api.orchestrator.reports import build_bundle

    if not st.registry.has("Exporter", exporter_id):
        raise ApiException(
            503, "feature_off", "This export is turned off.", "Enable it in Settings › Plugins."
        )
    bundle = build_bundle(st, project_id, session_id)
    if exporter_id == "export_html_report" and st.registry.has("Exporter", "export_svg_map"):
        bundle.extras["map_svg"] = (
            st.registry.get("Exporter", "export_svg_map").render(bundle).decode()
        )
    if exporter_id == "export_checklist" and st.registry.has("Exporter", "export_svg_map"):
        bundle.extras["map_svg"] = _selected_map(st, bundle)
    exp = st.registry.get("Exporter", exporter_id)
    data = exp.render(bundle)
    name = "".join(c if c.isalnum() else "-" for c in bundle.project_name)[:50]
    disposition = "inline" if exp.media_type in ("text/html", "image/svg+xml") else "attachment"
    return Response(
        data,
        media_type=exp.media_type,
        headers={
            "Content-Disposition": f'{disposition}; filename="{name}-{exporter_id}.{exp.file_ext}"'
        },
    )


def _selected_map(st: AppState, bundle: Any) -> str:
    """Map of the plan selected for handover (the current version), without session hotspots."""
    h = bundle.extras.get("handover") or {}
    if not h.get("venue"):
        return ""
    selected = bundle.model_copy(
        update={
            "venue": Venue.model_validate(h["venue"]),
            "venue_version": h.get("version", bundle.venue_version),
            "fixed_venue": None,
            "final": None,
            "baseline": None,
            "exit_assignment": h.get("exit_assignment") or {},
            "stair_assignment": h.get("stair_assignment") or {},
        }
    )
    try:
        return str(st.registry.get("Exporter", "export_svg_map").render(selected).decode())
    except Exception:  # the checklist is still useful without its map
        return ""


@router.get("/projects/{project_id}/checklist")
def project_checklist(
    project_id: str, session: str | None = None, st: AppState = Depends(get_state)
) -> Any:
    """Printable handover checklist of the selected plan (the current version), in English."""
    return _export(st, project_id, "export_checklist", session)


@router.get("/sessions/{session_id}/checklist")
def session_checklist(session_id: str, st: AppState = Depends(get_state)) -> Any:
    """Handover checklist of the selected plan, with this session's evidence."""
    row = st.sessions.get(session_id)
    if row is None:
        raise ApiException(404, "not_found", f"Session {session_id} does not exist.")
    return _export(st, row.project_id, "export_checklist", session_id)


@router.get("/projects/{project_id}/report")
def project_report(
    project_id: str, session: str | None = None, st: AppState = Depends(get_state)
) -> Any:
    """Printable HTML report (latest red-team session, else the latest stress test)."""
    return _export(st, project_id, "export_html_report", session)


@router.get("/projects/{project_id}/map.svg")
def project_map(
    project_id: str, session: str | None = None, st: AppState = Depends(get_state)
) -> Any:
    """Evacuation map (SVG)."""
    return _export(st, project_id, "export_svg_map", session)


@router.get("/projects/{project_id}/bundle.json")
def project_bundle(
    project_id: str, session: str | None = None, st: AppState = Depends(get_state)
) -> Any:
    """Everything behind the report as JSON."""
    return _export(st, project_id, "export_json_bundle", session)


@router.get("/sessions/{session_id}/report")
def session_report(session_id: str, st: AppState = Depends(get_state)) -> Any:
    row = st.sessions.get(session_id)
    if row is None:
        raise ApiException(404, "not_found", f"Session {session_id} does not exist.")
    return _export(st, row.project_id, "export_html_report", session_id)


@router.get("/sessions/{session_id}/map.svg")
def session_map(session_id: str, st: AppState = Depends(get_state)) -> Any:
    row = st.sessions.get(session_id)
    if row is None:
        raise ApiException(404, "not_found", f"Session {session_id} does not exist.")
    return _export(st, row.project_id, "export_svg_map", session_id)


@router.get("/sessions/{session_id}/bundle.json")
def session_bundle(session_id: str, st: AppState = Depends(get_state)) -> Any:
    row = st.sessions.get(session_id)
    if row is None:
        raise ApiException(404, "not_found", f"Session {session_id} does not exist.")
    return _export(st, row.project_id, "export_json_bundle", session_id)


# --- Ask the venue -----------------------------------------------------------------------


class HotspotIn(BaseModel):
    floor_id: str
    x: float
    y: float
    t_s: float | None = None


class AskIn(BaseModel):
    project_id: str
    run_id: str | None = None
    question: str = Field(min_length=2, max_length=300)
    hotspot: HotspotIn | None = None


def ask_context(
    st: AppState,
    venue: Venue,
    res: RunResult,
    events: list[Any],
    hs: HotspotIn | None = None,
    *,
    every_exit: bool = False,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Explainer data about one hotspot of a run, and where to point the camera.

    `every_exit` adds each exit's totals, so general questions ("which exit is the busiest?")
    are answered from the same run.
    """
    import math

    from api.core.extensions import geometry as geo

    spot = None
    if hs is not None:
        spot = min(
            res.hotspots,
            key=lambda h: (h.floor_id != hs.floor_id, math.hypot(h.x - hs.x, h.y - hs.y)),
            default=None,
        )
    elif res.hotspots:
        spot = res.hotspots[0]
    fx, fy, fid = (
        (spot.x, spot.y, spot.floor_id)
        if spot
        else (hs.x, hs.y, hs.floor_id)
        if hs
        else (0, 0, "F0")
    )
    per_exit = {p.exit_id: p for p in res.metrics.per_exit}
    exits = []
    for f in venue.floors:
        for ex in f.exits:
            cx, cy = geo.centroid(ex.polygon)
            d = math.hypot(cx - fx, cy - fy)
            if f.floor_id == fid and d <= 30:
                p = per_exit.get(ex.id)
                exits.append(
                    {
                        "exit": ex.label or ex.id,
                        "width_m": ex.width_m,
                        "distance_m": round(d, 1),
                        "blocked": ex.blocked,
                        "people_used_it": p.people if p else 0,
                        "mean_flow_people_per_s": p.mean_flow_pps if p else 0,
                        "last_person_at_s": p.last_s if p else None,
                    }
                )
    context: dict[str, Any] = {
        "hotspot": {
            "floor": fid,
            "peak_density_people_per_m2": spot.peak_density_ppm2 if spot else None,
            "time_of_peak_s": spot.t_s if spot else None,
            "level": spot.level if spot else None,
            "nearest_object": spot.near if spot else None,
        },
        "nearby_exits": sorted(exits, key=lambda x: x["distance_m"])[:4],
        "run": {
            "people": res.metrics.agents_total,
            "evacuation_time_95_s": res.metrics.evac_time_p95_s,
            "peak_density_people_per_m2": res.metrics.peak_density_ppm2,
            "time_above_danger_s": res.metrics.time_above_danger_s,
            "kind": "simulation" if res.tier >= 2 else "instant estimate",
        },
        "scenario_events": events,
        "thresholds_people_per_m2": {
            "warning": st.settings.density_warn_ppm2,
            "danger": st.settings.density_danger_ppm2,
        },
    }
    if every_exit:
        context["exits"] = [
            {
                "exit": ex.label or ex.id,
                "floor": f.floor_id,
                "width_m": ex.width_m,
                "blocked": ex.blocked,
                "people_used_it": per_exit[ex.id].people if ex.id in per_exit else 0,
                "last_person_at_s": per_exit[ex.id].last_s if ex.id in per_exit else None,
            }
            for f in venue.floors
            for ex in f.exits
        ][:16]
    return context, {"floor_id": fid, "x": fx, "y": fy}


async def explain_or_503(
    st: AppState, project_id: str, question: str, context: dict[str, Any]
) -> tuple[str, bool]:
    """The explainer's number-checked answer; a designed 503 when the model isn't answering."""
    from api.agents.judge import explain

    try:
        return await explain(
            AgentEnv(llm=st.llm, project_id=project_id),
            question,
            context,
        )
    except LLMError as exc:
        raise ApiException(
            503,
            "llm_unavailable",
            "The language model isn't answering.",
            "Start the local model with: make llm-up",
        ) from exc
    except Exception as exc:  # AgentUnavailable
        raise ApiException(
            503, "llm_unavailable", str(exc)[:200], "Start the local model with: make llm-up"
        ) from exc


def run_sources(st: AppState, row: Any) -> list[dict[str, str]]:
    """The real incident behind the attack a run tested, cited under an answer about it."""
    sources = []
    if row.attack_id and row.session_id:
        srow = st.sessions.get(row.session_id)
        for a in (srow.summary or {}).get("attacks", []) if srow else []:
            if a.get("attack_id") == row.attack_id:
                sources.append(
                    {"title": a["inspired_by"]["incident"], "url": a["inspired_by"]["source_url"]}
                )
    return sources


@router.post("/ask")
async def ask_venue(body: AskIn, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Explainer agent: answers about a hotspot using only the run's data."""
    venue = st.projects.venue(body.project_id)
    row = st.runs.get(body.run_id) if body.run_id else None
    if row is None or not row.result:
        raise ApiException(409, "no_run", "Run a stress test first, then ask about a hotspot.")
    res = RunResult.model_validate(row.result)
    events = (row.request or {}).get("extensions", {}).get("events", [])
    context, camera = ask_context(st, venue, res, events, body.hotspot)
    answer, checked = await explain_or_503(st, body.project_id, body.question, context)
    return {
        "answer": answer,
        "camera_target": camera,
        "sources": run_sources(st, row),
        "numbers_checked": checked,
        "context": context,
    }


# --- Rewind the worst moment (SANDBOX_SCOPE idea 3) --------------------------------------------


class RewindResponseIn(BaseModel):
    """One response to try from the rewind moment: a label and its scenario events."""

    label: str = Field(min_length=1, max_length=120)
    events: list[ScenarioEventIn] = Field(min_length=1, max_length=8)


class RewindIn(BaseModel):
    """`at_s` defaults to the moment of peak danger; `responses` to the kept changes' staff
    measures plus a few quick actions."""

    at_s: float | None = Field(default=None, gt=0, le=3600)
    responses: list[RewindResponseIn] | None = Field(default=None, max_length=6)


@router.post("/sessions/{session_id}/rewind", status_code=202)
async def rewind_session(
    session_id: str, body: RewindIn | None = None, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Rewind the worst attack to one second and try every response from there in parallel.

    Returns the rewind record at once (`id`, `status`); poll `GET /rewind/{id}`.
    """
    from api.orchestrator.rewind import RewindError, start_rewind

    body = body or RewindIn()
    try:
        return start_rewind(
            st,
            session_id,
            body.at_s,
            [r.model_dump() for r in body.responses] if body.responses else None,
        )
    except LookupError as exc:
        raise ApiException(404, "not_found", str(exc)) from exc
    except RewindError as exc:
        raise ApiException(409, "cannot_rewind", str(exc)) from exc


@router.get("/rewind/{rewind_id}")
def get_rewind(rewind_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """A rewind's status, its moment, the checkpoint run and every branch against "do nothing"."""
    from api.orchestrator.rewind import get_rewind as load

    rec = load(st, rewind_id)
    if rec is None:
        raise ApiException(404, "not_found", f"Rewind {rewind_id} does not exist.")
    return rec


@router.get("/sessions/{session_id}/rewind")
def latest_session_rewind(session_id: str, st: AppState = Depends(get_state)) -> Any:
    """The session's latest rewind, or null."""
    from api.orchestrator.rewind import latest_rewind

    return latest_rewind(st, session_id)
