"""The real cases an organizer can open: the shipped examples (api/data/real_cases.json) and
the ones organizers wrote and saved (table `saved_case`). Saved cases are data like the shipped
ones; nothing about an incident is written in code. Shipped examples are read-only.
"""

from __future__ import annotations

import logging
from typing import Any, Literal

from pydantic import ValidationError
from sqlmodel import col, select

from api.core.real_cases import CaseFacts, RealCase, case_id_for, list_cases
from api.db.models import SavedCase, utcnow
from api.db.session import db_session

log = logging.getLogger("showtime.case_library")

Origin = Literal["example", "saved"]


class ShippedCase(Exception):
    """A shipped example cannot be changed or deleted."""


def _saved(st: Any) -> list[RealCase]:
    out: list[RealCase] = []
    with db_session(st.projects.db_url) as s:
        rows = s.exec(select(SavedCase).order_by(col(SavedCase.created_at))).all()
    for row in rows:
        try:
            out.append(RealCase.model_validate({**row.data, "id": row.id}))
        except ValidationError:  # a row from an older schema must not hide the others
            log.warning("saved case %s does not validate and is skipped", row.id, exc_info=True)
    return out


def all_cases(st: Any) -> list[tuple[RealCase, Origin]]:
    """Every case: the shipped examples first, then the saved ones, oldest first."""
    shipped: list[tuple[RealCase, Origin]] = [(c, "example") for c in list_cases()]
    return [*shipped, *((c, "saved") for c in _saved(st))]


def find_case(st: Any, case_id: str) -> tuple[RealCase, Origin]:
    """One case and where it comes from; KeyError if there is none."""
    for case, origin in all_cases(st):
        if case.id == case_id:
            return case, origin
    raise KeyError(case_id)


def save_case(st: Any, facts: CaseFacts, case_id: str | None = None) -> RealCase:
    """Save a new case (id from its title) or replace a saved one."""
    shipped = {c.id for c in list_cases()}
    if case_id is not None and case_id in shipped:
        raise ShippedCase(case_id)
    with db_session(st.projects.db_url) as s:
        if case_id is None:
            taken = shipped | set(s.exec(select(SavedCase.id)).all())
            row = SavedCase(id=case_id_for(facts.title, taken))
        else:
            found = s.get(SavedCase, case_id)
            if found is None:
                raise KeyError(case_id)
            row = found
            row.updated_at = utcnow()
        row.data = facts.model_dump(mode="json")
        s.add(row)
        s.commit()
        return RealCase.model_validate({**row.data, "id": row.id})


def delete_case(st: Any, case_id: str) -> None:
    """Delete a saved case; projects built from it keep their copy of its facts."""
    if case_id in {c.id for c in list_cases()}:
        raise ShippedCase(case_id)
    with db_session(st.projects.db_url) as s:
        row = s.get(SavedCase, case_id)
        if row is None:
            raise KeyError(case_id)
        s.delete(row)
        s.commit()
