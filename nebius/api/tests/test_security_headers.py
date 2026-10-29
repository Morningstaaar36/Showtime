"""Every API response carries the standard browser security headers (OWASP secure headers):
no MIME sniffing, framed only by the app itself (the report preview), no full referrer to other
sites, and no camera, microphone or location."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from api.tests.http import api_client

EXPECTED = {
    "x-content-type-options": "nosniff",
    "x-frame-options": "SAMEORIGIN",
    "referrer-policy": "strict-origin-when-cross-origin",
    "permissions-policy": "camera=(), microphone=(), geolocation=()",
}


def test_responses_carry_the_security_headers(tmp_path: Path, monkeypatch: Any) -> None:
    from api.adapters.llm import FakeLLM
    from api.adapters.sandbox import FakeRunner
    from api.app.main import create_app
    from api.app.state import build_state
    from api.tests.evidence_fakes import reset_engine, use_test_settings

    s = use_test_settings(tmp_path, monkeypatch)
    st = build_state(s, llm=FakeLLM({}, s), runner=FakeRunner(s.runs_dir))
    try:
        with api_client(create_app(state=st, settings=s)) as c:
            for path in ("/api/v1/health", "/api/v1/projects", "/api/v1/nope"):
                r = c.get(path)
                for name, value in EXPECTED.items():
                    assert r.headers.get(name) == value, (path, name, r.headers.get(name))
    finally:
        reset_engine()
