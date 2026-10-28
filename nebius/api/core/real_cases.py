"""Real cases: well-documented crowd disasters as sourced descriptions (api/data/real_cases.json).

The description is the input to the Designer agent, exactly like an organizer's sentence; the
venue is built from it, never drawn by hand. What a project needs to show the case (what
happened, the sources) travels in the venue's `extensions["real_case"]`.
"""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, StringConstraints

from api.models import EventKind, Location

CASES_FILE = Path(__file__).resolve().parents[1] / "data" / "real_cases.json"
EXTENSION_KEY = "real_case"


Line = Annotated[str, StringConstraints(strip_whitespace=True, min_length=2, max_length=400)]


class CaseSource(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=3, max_length=240)
    url: HttpUrl


class CaseFacts(BaseModel):
    """One incident: what the site was, what happened, and where every number comes from. What
    an organizer writes to save a case of their own; the id is made from the title."""

    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    title: str = Field(min_length=3, max_length=60)
    incident: str = Field(min_length=3, max_length=160)
    date: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}$")
    place: str = Field(min_length=2, max_length=160)
    deaths: int = Field(ge=0)
    people: int = Field(gt=0)  # the crowd the description models (it states the number)
    toll: str = Field(min_length=1, max_length=200)
    event_kind: EventKind
    location: Location
    description: str = Field(min_length=40, max_length=2000)
    what_happened: str = Field(min_length=10, max_length=300)
    lesson: str = Field(min_length=5, max_length=160)
    sources: list[CaseSource] = Field(min_length=1, max_length=12)
    dimensions: list[Line] = Field(min_length=1, max_length=30)
    approximations: list[Line] = Field(min_length=1, max_length=30)


class RealCase(CaseFacts):
    """A case with its id: shipped in api/data/real_cases.json or saved by an organizer."""

    id: str = Field(pattern=r"^[a-z0-9_]+$", max_length=64)

    def card(self) -> dict[str, Any]:
        """What a project built from this case keeps (venue.extensions.real_case)."""
        return {
            "id": self.id,
            "title": self.title,
            "incident": self.incident,
            "date": self.date,
            "place": self.place,
            "deaths": self.deaths,
            "toll": self.toll,
            "what_happened": self.what_happened,
            "lesson": self.lesson,
            "sources": [s.model_dump(mode="json") for s in self.sources],
            "approximations": list(self.approximations),
        }


@lru_cache(maxsize=1)
def _load() -> dict[str, RealCase]:
    raw = json.loads(CASES_FILE.read_text())
    cases = [RealCase.model_validate(c) for c in raw["cases"]]
    return {c.id: c for c in cases}


def list_cases() -> list[RealCase]:
    """Every case, in the file's order."""
    return list(_load().values())


def get_case(case_id: str) -> RealCase:
    """One case; KeyError if unknown."""
    return _load()[case_id]


def case_id_for(title: str, taken: set[str]) -> str:
    """An id from a title ("Astroworld 2021 · Houston" → astroworld_2021_houston), made unique."""
    base = re.sub(r"[^a-z0-9]+", "_", title.lower()).strip("_")[:56] or "case"
    out, n = base, 2
    while out in taken:
        out, n = f"{base}_{n}", n + 1
    return out


def case_of(venue_extensions: dict[str, Any]) -> str | None:
    """The id of the real case a venue was built from, if any."""
    card = venue_extensions.get(EXTENSION_KEY)
    return str(card["id"]) if isinstance(card, dict) and card.get("id") else None
