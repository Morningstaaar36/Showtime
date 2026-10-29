"""The test client every API test uses: it talks to the API as the web app does."""

from __future__ import annotations

from typing import Any

from fastapi.testclient import TestClient

from api.app.main import WRITE_HEADER


def api_client(app: Any, **kwargs: Any) -> TestClient:
    """A TestClient on a host the API trusts (`localhost`) that sends the header every change
    needs, as the web app's client does (web/src/api/client.ts)."""
    kwargs.setdefault("base_url", "http://localhost")
    headers = {WRITE_HEADER: "1", **kwargs.pop("headers", {})}
    return TestClient(app, headers=headers, **kwargs)
