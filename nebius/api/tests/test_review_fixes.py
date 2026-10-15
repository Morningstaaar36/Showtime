"""Regression tests for defects found in the pre-release review."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.tests.test_api import client  # noqa: F401 - shared fixture


def _shape(body: dict[str, object]) -> None:
    assert set(body) == {"code", "message", "hint", "details"}


def test_unknown_route_and_method_use_the_error_shape(client: TestClient) -> None:  # noqa: F811
    r = client.get("/api/v1/no-such-thing")
    assert r.status_code == 404
    _shape(r.json())
    assert r.json()["code"] == "not_found"
    r = client.delete("/api/v1/health")
    assert r.status_code == 405
    _shape(r.json())
    assert r.json()["code"] == "method_not_allowed"


def test_unhandled_exception_is_a_designed_500(client: TestClient) -> None:  # noqa: F811
    app = client.app

    @app.get("/api/v1/_boom")  # type: ignore[attr-defined]
    def boom() -> None:
        raise RuntimeError("secret internals /home/x")

    r = TestClient(app, raise_server_exceptions=False).get("/api/v1/_boom")
    assert r.status_code == 500
    _shape(r.json())
    assert r.json()["code"] == "internal_error" and "internals" not in r.text
