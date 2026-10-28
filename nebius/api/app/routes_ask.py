"""One box "Ask or change anything".

The router agent sorts the organizer's sentence; the existing agents and formulas answer it.
An edit is only proposed (the organizer applies it with POST /projects/{id}/patch), a question
goes to the number-checked explainer, and what-if numbers are instant estimates computed in
code, never written by a model. An "analyse" question is answered by the analyst: code it
writes runs in a sandbox on the run's artifacts (also POST /projects/{id}/analyse).
"""

from __future__ import annotations

from math import isfinite
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from starlette.concurrency import run_in_threadpool

from api.adapters.llm import LLMError, LLMReplayMiss
from api.agents.analyst import analyse, run_facts, run_inputs
from api.agents.base import AgentEnv, AgentUnavailable
from api.agents.router import (
    WEATHER_SPEED,
    Route,
    clamp_scale,
    exit_names,
    resolve_exits,
    route_message,
)
from api.app.errors import ApiException, llm_unavailable
from api.app.routes_agents import EditIn, ask_context, edit_by_text, explain_or_503, run_sources
from api.app.routes_core import get_state
from api.app.routes_projects import WhatIfIn, what_if
from api.app.state import AppState
from api.core.evidence import describe_run, fallback_for
from api.core.plan import PlanError, saved_events
from api.db.models import Run
from api.models import RunResult, Venue

router = APIRouter(prefix="/api/v1")


class AskAnythingIn(BaseModel):
    """One sentence from the organizer, and the screen it was typed on."""

    text: str = Field(min_length=2, max_length=500)
    context: Literal["check", "plan"] = "check"
    session_id: str | None = Field(default=None, description="the tested plan being read")


@router.post("/projects/{project_id}/ask-anything")
async def ask_anything(
    project_id: str, body: AskAnythingIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Sort the text (model, else keywords), then propose an edit, answer, try a what-if or
    name the screen to open. `result` has the response shape of the route that answered."""
    venue = st.projects.venue(project_id)
    env = AgentEnv(llm=st.llm, project_id=project_id)
    route = await route_message(env, venue, body.text, body.context)
    if route.intent == "analyse" and not analysis_run(st, project_id, venue, None, body.session_id):
        route.intent = "question"  # nothing simulated to analyse yet: answer from the numbers
    try:
        result = await _answer(st, project_id, venue, route, body)
    except ApiException as exc:  # say how the text was understood, also when it fails
        exc.details = {**exc.details, "intent": route.intent, "routed_by": route.routed_by}
        raise
    return {"intent": route.intent, "routed_by": route.routed_by, "result": result}


async def _answer(
    st: AppState, project_id: str, venue: Venue, route: Route, body: AskAnythingIn
) -> dict[str, Any]:
    if route.intent == "edit":
        # the venue agent's proposal only: nothing is saved until the organizer applies it
        return await edit_by_text(project_id, EditIn(text=body.text, apply=False), st)
    if route.intent == "question":
        return await _question(st, project_id, venue, body.text, body.session_id)
    if route.intent == "what_if":
        return await _what_if(st, project_id, venue, route)
    if route.intent == "analyse":
        row = analysis_run(st, project_id, venue, None, body.session_id)
        assert row is not None  # checked before answering
        return await analyse_or_503(st, project_id, venue, row, body.text)
    if route.intent == "navigate" and route.target is not None:
        return {"target": route.target}
    return _help(venue, body.context)


# --- question --------------------------------------------------------------------------------


def _usable(row: Run | None) -> bool:
    return row is not None and bool(row.result) and row.status in ("ok", "partial")


def question_run(
    st: AppState, project_id: str, session_id: str | None, venue: Venue, version: int
) -> Run | None:
    """The run a question is about: the session's final (else baseline) run; without a session
    the newest plain test of the current venue version (no attack, fix or extra scenario)."""
    srow = st.sessions.get(session_id) if session_id else None
    if srow is not None and srow.project_id == project_id:
        summary = srow.summary or {}
        for rid in (summary.get("final_run_id"), summary.get("baseline_run_id")):
            row = st.runs.get(rid) if isinstance(rid, str) else None
            if _usable(row):
                return row
    try:  # every run also carries the organizer's saved staff plan: that alone is still plain
        saved = [e.model_dump(mode="json") for e in saved_events(venue, st.registry)]
    except PlanError:
        saved = []
    for row in st.runs.list(project_id, limit=30):
        plain = not (row.attack_id or row.fix_id) and _events(row) == saved
        if _usable(row) and row.venue_version == version and plain:
            return row
    return None


def _events(row: Run) -> list[Any]:
    events = (row.request or {}).get("extensions", {}).get("events", [])
    return events if isinstance(events, list) else []


def _tested_venue(st: AppState, row: Run, current: Venue) -> Venue:
    """The venue the run simulated (a fix run includes the fix), else the current one."""
    path = st.settings.runs_dir / row.id / "venue.json"
    try:
        return Venue.model_validate_json(path.read_text()) if path.is_file() else current
    except (OSError, ValueError):
        return current


def basis_of(res: RunResult) -> str:
    """Where the numbers of an answer come from, in plain words (from the result basis)."""
    if res.tier == 1 and not fallback_for(res):
        return "Instant estimate (formula)"
    return describe_run(res).capitalize()


async def _question(
    st: AppState, project_id: str, venue: Venue, text: str, session_id: str | None
) -> dict[str, Any]:
    version = st.projects.get(project_id).current_version
    row = question_run(st, project_id, session_id, venue, version)
    if row is not None:
        res = RunResult.model_validate(row.result)
        context, camera = ask_context(
            st, _tested_venue(st, row, venue), res, _events(row), every_exit=True
        )
    else:  # nothing tested yet: answer from the instant estimate of the venue as it is
        res = await run_in_threadpool(st.runs.estimate, venue)
        context, camera = ask_context(st, venue, res, [], every_exit=True)
    answer, checked = await explain_or_503(st, project_id, text, context)
    return {
        "answer": answer,
        "camera_target": camera,
        "sources": run_sources(st, row) if row is not None else [],
        "numbers_checked": checked,
        "context": context,
        "run_id": row.id if row is not None else None,
        "basis": basis_of(res),
    }


# --- analyse (the analyst writes code that runs in a sandbox) ---------------------------------


class AnalyseIn(BaseModel):
    """A question for the analyst about one run (default: the run a question would use)."""

    question: str = Field(min_length=2, max_length=500)
    run_id: str | None = None
    session_id: str | None = None


def _has_artifacts(st: AppState, row: Run | None) -> bool:
    if row is None or not _usable(row):
        return False
    return (st.settings.runs_dir / row.id / "result.json").is_file()


def analysis_run(
    st: AppState, project_id: str, venue: Venue, run_id: str | None, session_id: str | None
) -> Run | None:
    """The simulated run to analyse: the one asked for, else the run a question would use,
    else the newest simulated run of the project. Only runs with artifacts on disk qualify."""
    if run_id is not None:
        row = st.runs.get(run_id)
        ok = row is not None and row.project_id == project_id and _has_artifacts(st, row)
        return row if ok else None
    version = st.projects.get(project_id).current_version
    row = question_run(st, project_id, session_id, venue, version)
    if _has_artifacts(st, row):
        return row
    for candidate in st.runs.list(project_id, limit=30):
        if _has_artifacts(st, candidate):
            return candidate
    return None


async def analyse_or_503(
    st: AppState, project_id: str, venue: Venue, row: Run, question: str
) -> dict[str, Any]:
    """Run the analyst on a run; a designed 503 when the model isn't answering."""
    res = RunResult.model_validate(row.result)
    run_dir = st.settings.runs_dir / row.id
    inputs = await run_in_threadpool(run_inputs, run_dir)
    tested = _tested_venue(st, row, venue)
    facts = run_facts(res.model_dump(mode="json"), exit_names(tested), sorted(inputs))
    env = AgentEnv(llm=st.llm, project_id=project_id)
    try:
        out = await analyse(env, st.runner, question, facts, inputs)
    except (AgentUnavailable, LLMError, LLMReplayMiss) as exc:
        raise llm_unavailable(
            st.llm, "The AI isn't answering, so I can't write an analysis right now."
        ) from exc
    return {
        **out.to_dict(),
        "run_id": row.id,
        "basis": basis_of(res),
        "sandbox": st.runner.provider,
    }


@router.post("/projects/{project_id}/analyse")
async def analyse_question(
    project_id: str, body: AnalyseIn, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """The analyst's answer: code it wrote, run in a sandbox, and a number-checked summary."""
    venue = st.projects.venue(project_id)
    row = analysis_run(st, project_id, venue, body.run_id, body.session_id)
    if row is None:
        raise ApiException(
            409,
            "no_run",
            "There is no simulated run to analyse yet.",
            "Run a stress test first; the analysis reads its crowd movements.",
        )
    return await analyse_or_503(st, project_id, venue, row, body.question)


# --- what-if ---------------------------------------------------------------------------------


def _quoted(names: list[str]) -> str:
    q = [f"“{n}”" for n in names]
    return q[0] if len(q) == 1 else ", ".join(q[:-1]) + " or " + q[-1]


async def _what_if(st: AppState, project_id: str, venue: Venue, route: Route) -> dict[str, Any]:
    """The existing what-if with checked parameters, next to the plan as it is (both formula)."""
    names = exit_names(venue)
    ids, unknown = resolve_exits(route.closed_exits, venue)
    if unknown:
        valid = list(names.values())
        raise ApiException(
            422,
            "unknown_exit",
            f"There is no exit called {_quoted(unknown)} in this venue.",
            f"Exits here: {', '.join(valid)}." if valid else "This venue has no exits yet.",
            {"unknown": unknown, "valid": valid},
        )
    scale, capped = clamp_scale(route.crowd_scale)
    weather = route.weather or "none"
    changed = WhatIfIn(people_scale=scale, speed_factor=WEATHER_SPEED[weather], blocked_exits=ids)
    after = await run_in_threadpool(what_if, project_id, changed, st)
    before = await run_in_threadpool(what_if, project_id, WhatIfIn(), st)
    asked = (
        route.crowd_scale if route.crowd_scale is not None and isfinite(route.crowd_scale) else None
    )
    return {
        **after,
        "before": before,
        "params": {
            "crowd_scale": scale,
            "crowd_scale_asked": round(asked, 3) if asked is not None else None,
            "capped": capped,
            "weather": weather,
            "speed_factor": WEATHER_SPEED[weather],
            "closed_exits": [{"id": i, "name": names[i]} for i in ids],
            "changed": scale != 1.0 or weather != "none" or bool(ids),
        },
    }


# --- other -----------------------------------------------------------------------------------


def _help(venue: Venue, screen: str) -> dict[str, Any]:
    """What the box can do, with three examples that fit this venue."""
    doors = list(exit_names(venue).values())
    has_stage = any(o.kind == "stage" for f in venue.floors for o in f.obstacles)
    edit = f"make {doors[0]} 3 m wide" if doors else "add a 2 m door on the east wall"
    what = f"what if {doors[-1]} is closed and it rains?" if doors else "what if it rains?"
    question = (
        "why is it crowded near the stage?" if has_stage else "where does it get most crowded?"
    )
    return {
        "message": "I can change the venue, answer questions about the results or try a "
        "what-if. Try one of these:",
        "examples": [edit, what, question] if screen == "check" else [question, what, edit],
    }
