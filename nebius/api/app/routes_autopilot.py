"""Autopilot: one request to a tested plan. Start it, follow it (SSE), stop it, and find a
project's latest run."""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any

from fastapi import APIRouter, Depends
from sse_starlette.sse import EventSourceResponse

from api.app.errors import ApiException
from api.app.routes_core import get_state
from api.app.state import AppState
from api.models.autopilot import AutopilotRequest, AutopilotRun
from api.orchestrator.autopilot import AutopilotManager, manager_for

router = APIRouter(prefix="/api/v1")


def _run(mgr: AutopilotManager, run_id: str) -> AutopilotRun:
    run = mgr.get(run_id)
    if run is None:
        raise ApiException(404, "not_found", f"Autopilot run {run_id} does not exist.")
    return run


@router.post("/autopilot", status_code=202, response_model=AutopilotRun)
async def start_autopilot(
    body: AutopilotRequest, st: AppState = Depends(get_state)
) -> AutopilotRun:
    """Plan an event from one sentence, or test an existing project, in the background.

    Quick: one red-team round of 3 attacks, 2 fixes each for the 2 worst. Thorough: up to 3
    rounds of 5 attacks plus the six-scenario sweep. Fixes are tested, never applied."""
    return manager_for(st).start(body)


@router.get("/autopilot/{run_id}", response_model=AutopilotRun)
async def get_autopilot(run_id: str, st: AppState = Depends(get_state)) -> AutopilotRun:
    """The run: its eight steps, and when done the project, session, report and cost."""
    return _run(manager_for(st), run_id)


@router.get("/autopilot/{run_id}/events")
async def autopilot_events(
    run_id: str, after: int = 0, st: AppState = Depends(get_state)
) -> EventSourceResponse:
    """Server-sent events: replay from `after`, then live until the run ends (`event: end`)."""
    mgr = manager_for(st)
    _run(mgr, run_id)

    async def gen() -> AsyncIterator[dict[str, Any]]:
        async for ev in mgr.stream(run_id, after):
            yield {"id": str(ev.seq), "event": "message", "data": json.dumps(ev.model_dump())}
        yield {"event": "end", "data": "{}"}

    return EventSourceResponse(gen(), ping=15)


@router.post("/autopilot/{run_id}/stop", response_model=AutopilotRun)
async def stop_autopilot(run_id: str, st: AppState = Depends(get_state)) -> AutopilotRun:
    """Stop gracefully: the plan keeps what was finished (the red-team session stops too)."""
    mgr = manager_for(st)
    _run(mgr, run_id)
    mgr.stop(run_id)
    return _run(mgr, run_id)


@router.get("/projects/{project_id}/autopilot", response_model=AutopilotRun | None)
async def project_autopilot(
    project_id: str, st: AppState = Depends(get_state)
) -> AutopilotRun | None:
    """The project's latest Autopilot run (null when it never had one)."""
    st.projects.get(project_id)  # unknown project: 404
    return manager_for(st).latest_for_project(project_id)
