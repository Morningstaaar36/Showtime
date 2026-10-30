"""Redesign a venue with the organizer's own words.

"Not right yet: put the kitchen on the east side, make it eight storeys." The designer takes its
own earlier layout (stored on the venue by the design rounds) and the request, and goes through
the same rounds (check, critique, revise); the result is saved as a new version, so it can be
undone. One redesign per project at a time; its progress is polled by the page.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import asdict, dataclass, field
from typing import Any

from api.adapters.llm import BudgetExceeded, LLMError
from api.agents.base import AgentEnv, AgentUnavailable
from api.models import Venue
from api.models.venue_spec import VenueSpec
from api.orchestrator.designing import design_from_text

log = logging.getLogger("showtime.redesign")
MAX_REQUEST_CHARS = 600


class RedesignError(ValueError):
    """The venue cannot be redesigned (not designed from words, or a redesign is running)."""


@dataclass
class Redesign:
    project_id: str
    request: str
    status: str = "designing"  # designing | done | failed
    stage: dict[str, Any] = field(default_factory=dict)  # round, of, stage
    version: int | None = None  # the version it saved
    problems: list[str] = field(default_factory=list)
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


_jobs: dict[str, Redesign] = {}
_tasks: dict[str, asyncio.Task[None]] = {}


def redesign_status(project_id: str) -> Redesign | None:
    return _jobs.get(project_id)


def start_redesign(st: Any, project_id: str, request: str) -> Redesign:
    """Start redesigning the project's current venue with `request` (in the background)."""
    request = request.strip()
    if len(request) < 3:
        raise RedesignError("Say what to change, e.g. “put the kitchen on the east side”.")
    if len(request) > MAX_REQUEST_CHARS:
        raise RedesignError(f"Keep the request under {MAX_REQUEST_CHARS} characters.")
    running = _jobs.get(project_id)
    if running is not None and running.status == "designing":
        raise RedesignError("A redesign is already running for this plan.")
    venue = st.projects.venue(project_id)
    generated = venue.extensions.get("generated") or {}
    if not generated.get("spec") or not generated.get("description"):
        raise RedesignError(
            "This venue was not designed from a description, so there is no design to revise: "
            "change it with “Ask or change anything” or in Expert view."
        )
    job = _jobs[project_id] = Redesign(project_id=project_id, request=request)
    _tasks[project_id] = asyncio.create_task(_run(st, job, venue, generated))
    return job


async def _run(st: Any, job: Redesign, venue: Venue, generated: dict[str, Any]) -> None:
    env = AgentEnv(llm=st.llm, project_id=job.project_id, on_usage=st.usage.add)
    try:
        start = VenueSpec.model_validate(generated["spec"])
        out = await design_from_text(
            st,
            env,
            str(generated["description"]),
            None,
            location=venue.location,
            progress=lambda e: setattr(job, "stage", dict(e)),
            start=start,
            request=job.request,
        )
        if out.venue is None:
            job.status, job.problems = "failed", out.problems
            job.error = out.problems[0] if out.problems else "The designer gave no layout."
            return
        new = out.venue.model_copy(
            update={
                "name": venue.name,
                "description": venue.description,
                "location": venue.location,
                "event_kind": venue.event_kind or out.venue.event_kind,
                "extensions": {
                    **{k: v for k, v in venue.extensions.items() if k not in ("generated", "site")},
                    **out.venue.extensions,
                    "generated": {
                        **(out.venue.extensions.get("generated") or {}),
                        "redesigns": [
                            *((venue.extensions.get("generated") or {}).get("redesigns") or []),
                            job.request,
                        ],
                    },
                },
            }
        )
        row = st.projects.replace_venue(
            job.project_id, new, f"Redesigned: {job.request[:80]}", author="designer"
        )
        job.version, job.problems = row.version, out.problems
        job.status = "done"
    except (AgentUnavailable, LLMError, BudgetExceeded) as exc:
        job.status, job.error = "failed", f"The model isn't answering: {exc}"
    except Exception as exc:  # report, never leave the page waiting
        log.exception("redesign of %s failed", job.project_id)
        job.status, job.error = "failed", str(exc)
