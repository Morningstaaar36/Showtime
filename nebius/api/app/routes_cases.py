"""Real cases: documented crowd disasters, rebuilt by the Designer agent and tested."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.adapters.llm import BudgetExceeded, LLMError
from api.agents.base import AgentUnavailable
from api.app.errors import ApiException, llm_unavailable
from api.app.routes_core import get_state
from api.app.state import AppState
from api.core.real_cases import CaseFacts, RealCase
from api.orchestrator.case_library import (
    ShippedCase,
    all_cases,
    delete_case,
    find_case,
    save_case,
)
from api.orchestrator.real_cases import (
    CaseBuildFailed,
    case_projects,
    current_project,
    open_case,
)

router = APIRouter(prefix="/api/v1")
# The routes that read every case and project (or write case files) are plain functions:
# FastAPI runs them in its thread pool, so they never hold up the event loop.


def _out(st: AppState, case: RealCase, origin: str, built: dict[str, str]) -> dict[str, Any]:
    pid = built.get(case.id)
    if pid is not None and current_project(st, pid, case) is None:
        pid = None  # built from an earlier text of the case: opening builds the new one
    return {**case.model_dump(mode="json"), "origin": origin, "project_id": pid}


def _not_found(case_id: str) -> ApiException:
    return ApiException(404, "not_found", f"There is no real case '{case_id}'.")


def _read_only(case_id: str) -> ApiException:
    return ApiException(
        409,
        "read_only",
        f"'{case_id}' is a built-in example and cannot be changed.",
        "Save a copy as a new case and change that.",
    )


@router.get("/real_cases")
def real_cases(st: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    """Every case (the shipped examples, then the saved ones) with its facts and sources, and
    the project built from it (if any)."""
    built = case_projects(st)  # one pass over the projects for every case
    return [_out(st, c, origin, built) for c, origin in all_cases(st)]


@router.post("/real_cases", status_code=201)
def create_real_case(body: CaseFacts, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Save a new real case; it opens like the examples (the designer builds it from its text)."""
    return _out(st, save_case(st, body), "saved", {})


@router.put("/real_cases/{case_id}")
def update_real_case(
    case_id: str, body: CaseFacts, st: AppState = Depends(get_state)
) -> dict[str, Any]:
    """Change a saved case; the next open builds it from the new text."""
    try:
        case = save_case(st, body, case_id)
    except ShippedCase as exc:
        raise _read_only(case_id) from exc
    except KeyError as exc:
        raise _not_found(case_id) from exc
    return _out(st, case, "saved", case_projects(st))


@router.delete("/real_cases/{case_id}", status_code=204)
def delete_real_case(case_id: str, st: AppState = Depends(get_state)) -> None:
    """Delete a saved case; projects built from it stay, with their copy of its facts."""
    try:
        delete_case(st, case_id)
    except ShippedCase as exc:
        raise _read_only(case_id) from exc
    except KeyError as exc:
        raise _not_found(case_id) from exc


@router.post("/real_cases/{case_id}/open")
async def open_real_case(case_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Build the case's venue from its description (Designer agent) and start its test; a case
    built before opens its existing project."""
    try:
        find_case(st, case_id)
    except KeyError as exc:
        raise _not_found(case_id) from exc
    try:
        return await open_case(st, case_id)
    except CaseBuildFailed as exc:
        raise ApiException(
            422,
            "design_failed",
            "The venue could not be built from the case description.",
            exc.problems[0] if exc.problems else None,
            {"problems": exc.problems},
        ) from exc
    except BudgetExceeded as exc:
        raise ApiException(429, "budget", str(exc), "Raise the token budget in Settings.") from exc
    except (LLMError, AgentUnavailable) as exc:
        raise llm_unavailable(
            st.llm, "The language model isn't answering, so the venue can't be built."
        ) from exc
