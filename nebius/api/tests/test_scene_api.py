"""Scene endpoint acceptance, using the existing isolated fake-provider API fixture."""

from __future__ import annotations

from fastapi.testclient import TestClient

from api.models.scene import SceneFacts, SceneSnapshot
from api.tests.test_api import client as client
from api.tests.test_scene import room


def create(client: TestClient) -> str:
    response = client.post("/api/v1/projects", json={"venue": room().model_dump(mode="json")})
    assert response.status_code == 201, response.text
    return str(response.json()["id"])


def test_scene_endpoints(client: TestClient) -> None:
    pid = create(client)
    snapshot = client.get(f"/api/v1/projects/{pid}/scene")
    assert snapshot.status_code == 200, snapshot.text
    scene = SceneSnapshot.model_validate(snapshot.json())
    response = client.get(f"/api/v1/projects/{pid}/scene-facts")
    assert response.status_code == 200, response.text
    facts = SceneFacts.model_validate(response.json())
    assert facts.identity == scene.identity
    assert facts.identity.project_id == pid
    assert facts.identity.venue_version == 1
    assert facts.zones[0].reachability == "reachable"


def test_edit_and_historical_version(client: TestClient) -> None:
    pid = create(client)
    before = client.get(f"/api/v1/projects/{pid}/scene-facts").json()
    patch = client.post(
        f"/api/v1/projects/{pid}/patch",
        json={
            "patch": {"ops": [{"op": "block_exit", "exit_id": "E1"}]},
            "allow_new_errors": True,
        },
    )
    assert patch.status_code == 200, patch.text
    after = client.get(f"/api/v1/projects/{pid}/scene-facts").json()
    assert after["identity"]["venue_version"] == 2
    assert after["identity"]["scene_hash"] != before["identity"]["scene_hash"]
    assert after["zones"][0]["reachability"] == "unreachable"
    historical = client.get(f"/api/v1/projects/{pid}/scene-facts?version=1").json()
    assert historical == before
    undo = client.post(f"/api/v1/projects/{pid}/undo")
    assert undo.status_code == 200
    restored = client.get(f"/api/v1/projects/{pid}/scene-facts").json()
    assert restored["identity"]["venue_version"] == 3
    assert restored["identity"]["scene_hash"] == before["identity"]["scene_hash"]
    assert restored["zones"] == before["zones"]


def test_scene_unknown_project_version_and_invalid_query(client: TestClient) -> None:
    for suffix in ("scene", "scene-facts"):
        assert client.get(f"/api/v1/projects/unknown/{suffix}").status_code == 404
        pid = create(client)
        assert client.get(f"/api/v1/projects/{pid}/{suffix}?version=99").status_code == 404
        assert client.get(f"/api/v1/projects/{pid}/{suffix}?version=0").status_code == 422


def test_invalid_polygon_is_not_repaired_by_scene_endpoint(client: TestClient) -> None:
    venue = room()
    venue.floors[0].walkable = [(0, 0), (10, 8), (0, 8), (10, 0)]
    created = client.post("/api/v1/projects", json={"venue": venue.model_dump(mode="json")})
    assert created.status_code == 201, created.text
    pid = created.json()["id"]
    for suffix in ("scene", "scene-facts"):
        response = client.get(f"/api/v1/projects/{pid}/{suffix}")
        assert response.status_code == 422, response.text
        assert response.json()["code"] == "invalid_scene"
        assert response.json()["details"]["issues"][0]["code"] == "invalid_polygon"


def test_no_routes_and_response_schemas(client: TestClient) -> None:
    pid = create(client)
    response = client.get(f"/api/v1/projects/{pid}/scene-facts?include_routes=false")
    assert response.status_code == 200
    assert response.json()["route_budget_reason"] == "routes_disabled"
    assert response.json()["zones"][0]["reachability"] == "reachable"
    schema = client.get("/api/openapi.json").json()
    assert "SceneSnapshot" in schema["components"]["schemas"]
    assert "SceneFacts" in schema["components"]["schemas"]
