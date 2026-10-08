"""Template venues shipped with the app (api/data/templates/*.json)."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from api.models import Venue

TEMPLATE_DIR = Path(__file__).resolve().parents[1] / "data" / "templates"


@lru_cache(maxsize=1)
def _load_all() -> dict[str, Venue]:
    out: dict[str, Venue] = {}
    for path in sorted(TEMPLATE_DIR.glob("*.json")):
        v = Venue.model_validate(json.loads(path.read_text()))
        out[v.venue_id] = v
    return out


def list_templates() -> list[Venue]:
    """All templates, in a stable order."""
    order = ["festival_field", "conference_hall_2f", "school_wing", "t_alley"]
    items = _load_all()
    return [items[k] for k in order if k in items] + [v for k, v in items.items() if k not in order]


def get_template(template_id: str) -> Venue:
    """A deep copy of one template; KeyError if unknown."""
    return _load_all()[template_id].model_copy(deep=True)
