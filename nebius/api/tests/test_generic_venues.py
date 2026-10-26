"""Venue knowledge comes from data and is the same for any kind of venue (step 5e)."""

from __future__ import annotations

import json
from typing import Any

from api.agents.red_team import _incident_kinds, grounded_title, incident_query
from api.core.settings import ROOT_DIR
from api.core.templates import TEMPLATE_DIR, list_templates
from api.models import Attack, Venue


def _venue(mode: str, kind: str | None) -> Venue:
    from api.core.templates import get_template

    v = get_template("school_wing" if mode == "indoor" else "festival_field")
    return v.model_copy(update={"event_kind": kind})


def _feats(stairs: bool = False) -> dict[str, Any]:
    return {"stairs": stairs, "has_stage": False, "narrowest_exit_m": 5}


def test_the_incident_search_follows_the_kind_of_venue() -> None:
    q = incident_query(_venue("indoor", "transit"), _feats())
    assert q["settings"][0] == "transport" and q["keywords"]["station"] > 1
    q = incident_query(_venue("indoor", "religious"), _feats())
    assert q["settings"][0] == "religious"
    q = incident_query(_venue("outdoor", None), _feats())
    assert q["settings"][0] == "outdoor"  # no kind: the mode's defaults


def test_every_setting_and_keyword_in_the_table_exists_in_the_dataset() -> None:
    from api.core.plugins import load_plugins

    src = load_plugins(ROOT_DIR).registry.all("IncidentSource")[0]
    rows = src._load()
    if not rows:  # the dataset is not downloaded here
        return
    settings = {r.setting for r in rows}
    keywords = {k for r in rows for k in r.keywords}
    table = _incident_kinds()
    for entry in [*table["defaults"].values(), *table["kinds"].values()]:
        assert set(entry["settings"]) <= settings, entry["settings"]
        assert set(entry["keywords"]) <= keywords, set(entry["keywords"]) - keywords


def test_a_title_naming_something_the_venue_has_is_kept() -> None:
    from api.core.extensions import Registry  # noqa: F401  (registry from plugins below)
    from api.core.plugins import load_plugins

    reg = load_plugins(ROOT_DIR).registry
    v = _venue("outdoor", "festival")
    v.floors[0].exits[0].label = "West tunnel end"
    a = Attack.model_validate(
        {
            "attack_id": "A1",
            "title": "Tunnel crush at the west end",
            "events": [{"type": "block_exit", "exit_id": v.floors[0].exits[0].id, "at_s": 30}],
            "inspired_by": {"incident": "x", "source_url": "https://e.org/x"},
        }
    )
    assert grounded_title(a.title, v, a, reg) == "Tunnel crush at the west end"


def test_the_template_order_comes_from_the_templates_index() -> None:
    order = json.loads((TEMPLATE_DIR / "index.json").read_text())["order"]
    assert [t.venue_id for t in list_templates()][: len(order)] == order
