"""Real cases: documented crowd disasters, rebuilt by the Designer agent and tested."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends

from api.adapters.llm import BudgetExceeded, LLMError
from api.agents.base import AgentUnavailable
from api.app.errors import ApiException, llm_unavailable
from api.app.routes_core import get_state
from api.app.state import AppState
from api.core.real_cases import get_case, list_cases
from api.orchestrator.real_cases import CaseBuildFailed, case_projects, open_case

router = APIRouter(prefix="/api/v1")


@router.get("/real_cases")
async def real_cases(st: AppState = Depends(get_state)) -> list[dict[str, Any]]:
    """Every case with its facts and sources, and the project built from it (if any)."""
    built = case_projects(st)  # one pass over the projects for every case
    return [{**c.model_dump(mode="json"), "project_id": built.get(c.id)} for c in list_cases()]


@router.post("/real_cases/{case_id}/open")
async def open_real_case(case_id: str, st: AppState = Depends(get_state)) -> dict[str, Any]:
    """Build the case's venue from its description (Designer agent) and start its test; a case
    built before opens its existing project."""
    try:
        get_case(case_id)
    except KeyError as exc:
        raise ApiException(404, "not_found", f"There is no real case '{case_id}'.") from exc
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
