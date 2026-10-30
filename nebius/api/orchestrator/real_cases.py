"""Open a real case: the Designer agent builds the venue from the case's sourced description
(one model call, replayed from the LLM cache in record_replay mode), the project keeps the
case's facts and sources, and a test starts at once.

The test is the normal AI-designed one: the red team attacks the case as it was, the blue team
proposes fixes, the simulator confirms them and the judge writes the verdict (the rules stand in
only when no model answers). Its baseline is the case as it happened; the rest is what Showtime
would have suggested.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from api.agents.base import AgentEnv
from api.core.real_cases import EXTENSION_KEY, RealCase, case_of
from api.core.session_modes import session_modes
from api.orchestrator.case_library import find_case
from api.orchestrator.designing import design_from_text

log = logging.getLogger("showtime.real_cases")

# one build of a case at a time (a double click must not build it twice); the designer has a
# deadline (CASE_BUILD_TIMEOUT_S) so a model that never answers cannot leave the tile spinning
_building: dict[str, asyncio.Lock] = {}
# (project id, version) -> the case it was built from, or None: venues are read once
_case_of_version: dict[tuple[str, int], str | None] = {}
# case id -> where its build is ({round, of, stage}), while it is being built
_progress: dict[str, dict[str, Any]] = {}


def build_progress(case_id: str) -> dict[str, Any] | None:
    """Where the case's build is (design round and stage), or None when it isn't building."""
    return _progress.get(case_id)


class CaseBuildFailed(Exception):
    """The designer could not build a venue from the description."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems) or "The model did not return a layout.")
        self.problems = problems


def case_projects(st: Any) -> dict[str, str]:
    """Each case's project (the newest built from it), reading every venue once in one pass and
    never again until the project gets a new version."""
    out: dict[str, str] = {}
    for p in st.projects.list_projects():
        key = (str(p.id), int(p.current_version))
        if key not in _case_of_version:
            try:
                _case_of_version[key] = case_of(st.projects.venue(p.id).extensions)
            except Exception:  # a broken project must not hide the others
                log.warning("project %s could not be read for its real case", p.id, exc_info=True)
                continue
        case_id = _case_of_version[key]
        if case_id is not None:
            out.setdefault(case_id, str(p.id))
    return out


def existing_project(st: Any, case_id: str) -> str | None:
    """A project already built from this case (newest first), so a case is built once."""
    return case_projects(st).get(case_id)


def current_project(st: Any, project_id: str | None, case: RealCase) -> str | None:
    """The project if it was built from the case as it reads now; None once the case was
    edited after the build (the project stays, with the text it was built from)."""
    if project_id is None:
        return None
    venue = st.projects.venue(project_id)
    same = venue.extensions.get(EXTENSION_KEY) == case.card() and venue.location == case.location
    return project_id if same else None


def _latest_session(st: Any, project_id: str) -> str | None:
    rows = st.sessions.list_sessions(project_id)
    return str(rows[0].id) if rows else None


async def open_case(st: Any, case_id: str) -> dict[str, Any]:
    """The case's project (built now, or the one built before) and its test session.

    Raises KeyError for an unknown case and CaseBuildFailed when no venue came back.
    A second call while the case is being built waits for that build and opens its project.
    """
    find_case(st, case_id)
    lock = _building.setdefault(case_id, asyncio.Lock())
    async with lock:
        return await _open_case(st, case_id)


async def _open_case(st: Any, case_id: str) -> dict[str, Any]:
    case, _ = find_case(st, case_id)
    pid = current_project(st, existing_project(st, case_id), case)
    if pid is not None:
        sid = _latest_session(st, pid)
        if sid is not None:
            return {"project_id": pid, "session_id": sid, "status": "existing"}
        # built before but never tested: its layout needed a fix. Edited since (a new version):
        # test it if it is valid now, else leave it to whoever is fixing it. Untouched: build
        # it again (a model's second answer, or a better solver, may get it right)
        from api.core.geometry import validate_venue

        if st.projects.get(pid).current_version > 1:
            if validate_venue(st.projects.venue(pid)).ok:
                row = st.sessions.start(pid, session_modes().real_case)
                return {"project_id": pid, "session_id": row.id, "status": "testing"}
            return {"project_id": pid, "session_id": None, "status": "needs_fixes", "problems": []}
        st.projects.delete(pid)  # untouched and still broken: design it again
    env = AgentEnv(llm=st.llm, project_id=None, on_usage=st.usage.add)
    deadline = float(st.settings.case_build_timeout_s)
    try:
        # the case's crowd is data: a layout that holds another number goes back to the model
        out = await asyncio.wait_for(
            design_from_text(
                st,
                env,
                case.description,
                case.people,
                location=case.location,
                progress=lambda e: _progress.__setitem__(case_id, e),
            ),
            deadline,
        )
    except TimeoutError as exc:
        raise CaseBuildFailed(
            [f"The designer took longer than {deadline:g} s; try again."]
        ) from exc
    finally:
        _progress.pop(case_id, None)
    if out.venue is None:
        raise CaseBuildFailed(out.problems)
    venue = out.venue.model_copy(
        update={
            "name": case.title,
            "description": case.what_happened,
            "event_kind": case.event_kind,
            "location": case.location,
            "extensions": {**out.venue.extensions, EXTENSION_KEY: case.card()},
        }
    )
    p = st.projects.create(case.title, venue=venue, description=_project_text(case))
    if out.status != "built":  # the layout needs a fix first: open it in the editor
        return {
            "project_id": p.id,
            "session_id": None,
            "status": out.status,
            "problems": out.problems,
        }
    row = st.sessions.start(p.id, session_modes().real_case)
    return {"project_id": p.id, "session_id": row.id, "status": "testing"}


def _project_text(case: RealCase) -> str:
    return f"{case.incident}, {case.place}, {case.date}. {case.toll} {case.lesson}"
