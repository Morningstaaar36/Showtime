"""Open a real case: the Designer agent builds the venue from the case's sourced description
(one model call, replayed from the LLM cache in record_replay mode), the project keeps the
case's facts and sources, and a test starts at once.

The test needs no further model calls: rule-based what-ifs and fixes (`agents: "rules"`) and
the computed summary instead of the judge (`judge: false`). Its baseline is the case as it
happened; the rest is what Showtime would have suggested.
"""

from __future__ import annotations

from typing import Any

from api.agents.base import AgentEnv
from api.agents.venue_designer import design_venue
from api.core.real_cases import EXTENSION_KEY, RealCase, case_of, get_case

# one round, two what-ifs, two fixes for the worst; tier 2 for the what-ifs keeps a crowd
# that cannot get out (Hillsborough) inside the session's wall-clock budget
CASE_TEST: dict[str, Any] = {
    "max_rounds": 1,
    "attacks_per_round": 2,
    "fixes_per_attack": 2,
    "fix_targets": 1,
    "agents": "rules",
    "judge": False,
    "confirm_tier3": False,
}


class CaseBuildFailed(Exception):
    """The designer could not build a venue from the description."""

    def __init__(self, problems: list[str]) -> None:
        super().__init__("; ".join(problems) or "The model did not return a layout.")
        self.problems = problems


def existing_project(st: Any, case_id: str) -> str | None:
    """A project already built from this case (newest first), so a case is built once."""
    for p in st.projects.list_projects():
        try:
            ext = st.projects.venue(p.id).extensions
        except Exception:  # a broken project must not hide the others
            continue
        if case_of(ext) == case_id:
            return str(p.id)
    return None


def _latest_session(st: Any, project_id: str) -> str | None:
    rows = st.sessions.list_sessions(project_id)
    return str(rows[0].id) if rows else None


async def open_case(st: Any, case_id: str) -> dict[str, Any]:
    """The case's project (built now, or the one built before) and its test session.

    Raises KeyError for an unknown case and CaseBuildFailed when no venue came back.
    """
    case = get_case(case_id)
    pid = existing_project(st, case_id)
    if pid is not None:
        return {"project_id": pid, "session_id": _latest_session(st, pid), "status": "existing"}
    env = AgentEnv(llm=st.llm, project_id=None, on_usage=st.usage.add)
    out = await design_venue(env, case.description)
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
    row = st.sessions.start(p.id, CASE_TEST)
    return {"project_id": p.id, "session_id": row.id, "status": "testing"}


def _project_text(case: RealCase) -> str:
    return f"{case.incident}, {case.place}, {case.date}. {case.toll} {case.lesson}"
