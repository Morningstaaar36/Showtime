"""Importing plans: a DXF drawn to the JuPedSim layers, a venue JSON and a .showtime.zip all come
in through POST /projects/import, and what can be imported is never listed by hand: the API names
the registered importer plugins (GET /importers), and so does the error for any other file."""

from __future__ import annotations

import io
import json
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path: Path, monkeypatch: Any) -> Any:
    from api.adapters.llm import FakeLLM
    from api.adapters.sandbox import FakeRunner
    from api.app.main import create_app
    from api.app.state import build_state
    from api.tests.evidence_fakes import reset_engine, use_test_settings

    s = use_test_settings(tmp_path, monkeypatch)
    st = build_state(s, llm=FakeLLM({}, s), runner=FakeRunner(s.runs_dir))
    with TestClient(create_app(state=st, settings=s)) as c:
        yield c
    reset_engine()


def _dxf() -> bytes:
    import ezdxf

    from plugins.import_dxf import LAYERS  # the plugin's own layer names

    doc = ezdxf.new()
    msp = doc.modelspace()
    msp.add_lwpolyline(
        [(0, 0), (30, 0), (30, 20), (0, 20)], close=True, dxfattribs={"layer": LAYERS["walk"]}
    )
    msp.add_lwpolyline(
        [(14, 0), (16, 0), (16, 0.4), (14, 0.4)], close=True, dxfattribs={"layer": LAYERS["exit"]}
    )
    msp.add_lwpolyline(
        [(5, 5), (25, 5), (25, 15), (5, 15)], close=True, dxfattribs={"layer": LAYERS["zone"]}
    )
    buf = io.StringIO()
    doc.write(buf)
    return buf.getvalue().encode()


def test_a_dxf_drawing_becomes_a_plan(client: Any) -> None:
    r = client.post(
        "/api/v1/projects/import", files={"file": ("hall.dxf", _dxf(), "application/dxf")}
    )
    assert r.status_code == 201, r.text
    v = client.get(f"/api/v1/projects/{r.json()['id']}").json()["version"]["venue"]
    assert len(v["floors"][0]["exits"]) == 1 and v["floors"][0]["zones"][0]["people"] > 0


def test_a_venue_json_becomes_a_plan(client: Any) -> None:
    t = client.get("/api/v1/templates").json()
    venue = (t if isinstance(t, list) else t["templates"])[0]["venue"]
    r = client.post(
        "/api/v1/projects/import",
        files={"file": ("venue.json", json.dumps(venue).encode(), "application/json")},
    )
    assert r.status_code == 201, r.text


def test_what_can_be_imported_comes_from_the_importers(client: Any) -> None:
    kinds = client.get("/api/v1/importers").json()["importers"]
    exts = {e for k in kinds for e in k["extensions"]}
    assert {".showtime.zip", ".json", ".dxf"} <= exts
    r = client.post(
        "/api/v1/projects/import", files={"file": ("notes.txt", b"hello", "text/plain")}
    )
    assert r.status_code == 415
    for e in exts:
        assert e in r.json()["hint"]
