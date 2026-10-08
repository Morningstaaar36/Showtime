"""Shared queries across services."""

from __future__ import annotations

from sqlalchemy import or_
from sqlmodel import Session, col, select

from api.db.models import RedTeamSession, Run, SessionEventRow


def project_runs(s: Session, project_id: str, limit: int | None = None) -> list[Run]:
    """Runs of a project, newest first: runs it owns plus runs its red-team sessions finished.

    Run ids are content-addressed, so a session may reuse a cached run that another project
    (or an earlier import of the same pack) created first.
    """
    sids = list(s.exec(select(RedTeamSession.id).where(RedTeamSession.project_id == project_id)))
    ids: set[str] = set()
    if sids:
        for ev in s.exec(
            select(SessionEventRow).where(
                col(SessionEventRow.session_id).in_(sids), SessionEventRow.type == "run_finished"
            )
        ):
            rid = (ev.payload or {}).get("run_id")
            if isinstance(rid, str):
                ids.add(rid)
    q = select(Run).where(or_(col(Run.project_id) == project_id, col(Run.id).in_(ids)))
    q = q.order_by(col(Run.created_at).desc())
    if limit is not None:
        q = q.limit(limit)
    return list(s.exec(q))
