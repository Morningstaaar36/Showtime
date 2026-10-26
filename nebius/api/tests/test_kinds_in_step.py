"""The web app's fallback list of event kinds, and its strings, stay in step with the API's."""

from __future__ import annotations

import json
import re
from typing import get_args

from api.core.event_profiles import event_kinds
from api.core.settings import ROOT_DIR
from api.models.venue import EventKind


def test_the_web_event_kinds_match_the_api() -> None:
    ts = (ROOT_DIR / "web" / "src" / "lib" / "venueOps.ts").read_text()
    block = re.search(r"export const EVENT_KINDS: EventKindId\[\] = \[(.*?)\];", ts, re.S)
    assert block, "EVENT_KINDS not found in venueOps.ts"
    web = re.findall(r'"([a-z_]+)"', block.group(1))
    assert web == list(get_args(EventKind))
    strings = json.loads((ROOT_DIR / "web" / "src" / "i18n" / "en.json").read_text())
    assert set(strings["editor"]["event"]) >= set(web)


def test_every_event_kind_has_its_copy() -> None:
    assert [k["id"] for k in event_kinds()] == list(get_args(EventKind))
