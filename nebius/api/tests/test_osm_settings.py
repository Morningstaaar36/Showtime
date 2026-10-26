"""The map services are configured, not written into the adapter: the largest area to load,
the Overpass servers (main, fallbacks, slow last resorts) and the vector tiles come from
settings, and the "zoom in" message states the configured size."""

from __future__ import annotations

from pathlib import Path

import pytest

from api.adapters.osm import OsmUnavailable
from api.app.state import build_osm
from api.core.settings import Settings


def _osm(tmp_path: Path, **kw: object):
    return build_osm(Settings(_env_file=None, cache_dir=tmp_path, offline=True, **kw))


async def test_the_largest_area_and_its_message_come_from_settings(tmp_path: Path) -> None:
    osm = _osm(tmp_path, osm_max_span_km=0.5)
    # about 0.9 km north-south: over a 0.5 km limit
    with pytest.raises(OsmUnavailable, match=r"0\.5 km"):
        await osm.features(23.7200, 90.3900, 23.7281, 90.3950)


def test_the_overpass_servers_come_from_settings(tmp_path: Path) -> None:
    osm = _osm(
        tmp_path,
        overpass_url="https://main.example/api",
        overpass_fallback_urls="https://a.example/api, https://main.example/api",
        overpass_late_urls="https://slow.example/api",
    )
    assert osm.overpass_urls == ["https://main.example/api", "https://a.example/api"]
    assert osm.late_urls == ["https://slow.example/api"]


def test_the_app_gets_its_map_config_from_the_server(tmp_path: Path, monkeypatch: object) -> None:
    from fastapi.testclient import TestClient

    from api.adapters.llm import FakeLLM
    from api.adapters.sandbox import FakeRunner
    from api.app.main import create_app
    from api.app.state import build_state
    from api.tests.evidence_fakes import reset_engine, use_test_settings

    s = use_test_settings(tmp_path, monkeypatch)  # type: ignore[arg-type]
    s = s.model_copy(
        update={"map_start": "23.73,90.39,13", "map_style_url": "https://style.example/s.json"}
    )
    st = build_state(s, llm=FakeLLM({}, s), runner=FakeRunner(s.runs_dir))
    try:
        with TestClient(create_app(state=st, settings=s)) as c:
            m = c.get("/api/v1/health").json()["client"]["map"]
        assert m["style_url"] == "https://style.example/s.json"
        assert m["raster_tiles_url"] == s.map_raster_tiles_url
        assert m["start"] == {"lat": 23.73, "lon": 90.39, "zoom": 13.0}
    finally:
        reset_engine()


def test_a_bad_map_start_fails_at_startup_naming_the_variable(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="MAP_START"):
        Settings(_env_file=None, cache_dir=tmp_path, map_start="somewhere nice")
