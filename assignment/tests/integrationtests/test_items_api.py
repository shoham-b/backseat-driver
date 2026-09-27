"""Integration tests for /items routes.

Demonstrates how domain errors map to HTTP status codes without any
try/except in the route handlers.
"""
import json
from http import HTTPStatus

import pytest
from fastapi.testclient import TestClient

from vlm_scene_description.api.app import app
from vlm_scene_description.db.memory import MemoryRepository


@pytest.fixture(autouse=True)
def _clear_item_store(client: TestClient) -> None:
    """Reset the shared item store between tests so they are independent."""
    repo = app.state.repository
    if isinstance(repo, MemoryRepository):
        repo.clear()


def test_list_items_returns_empty_page(client: TestClient) -> None:
    response = client.get("/items/")

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["items"] == []
    assert data["total"] == 0
    assert data["page"] == 1
    assert data["page_size"] == 20


def test_list_items_pagination_params(client: TestClient) -> None:
    response = client.get("/items/", params={"page": 2, "page_size": 5})

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["page"] == 2
    assert data["page_size"] == 5


def test_get_missing_item_returns_404(client: TestClient) -> None:
    response = client.get("/items/nonexistent")

    assert response.status_code == HTTPStatus.NOT_FOUND
    error = response.json()["error"]
    assert error["code"] == HTTPStatus.NOT_FOUND
    assert "message" in error


def test_create_item(client: TestClient) -> None:
    payload = {"id": "widget-1", "name": "Widget", "description": "A test widget"}

    response = client.post("/items/", json=payload)

    assert response.status_code == HTTPStatus.CREATED
    data = response.json()
    assert data["id"] == "widget-1"
    assert data["name"] == "Widget"


def test_create_then_retrieve(client: TestClient) -> None:
    client.post("/items/", json={"id": "abc", "name": "Alpha"})

    response = client.get("/items/abc")

    assert response.status_code == HTTPStatus.OK
    assert response.json()["name"] == "Alpha"


def test_create_duplicate_returns_409(client: TestClient) -> None:
    payload = {"id": "dup", "name": "Dupe"}
    client.post("/items/", json=payload)

    response = client.post("/items/", json=payload)

    assert response.status_code == HTTPStatus.CONFLICT
    assert "message" in response.json()["error"]


def test_update_item_changes_only_supplied_fields(client: TestClient) -> None:
    client.post(
        "/items/",
        json={"id": "upd", "name": "Original", "description": "Keep this"},
    )

    response = client.patch("/items/upd", json={"name": "Updated"})

    assert response.status_code == HTTPStatus.OK
    data = response.json()
    assert data["name"] == "Updated"
    assert data["description"] == "Keep this"
    assert data["id"] == "upd"


def test_update_missing_item_returns_404(client: TestClient) -> None:
    response = client.patch("/items/ghost", json={"name": "Updated"})

    assert response.status_code == HTTPStatus.NOT_FOUND


def test_delete_item(client: TestClient) -> None:
    client.post("/items/", json={"id": "del1", "name": "DeleteMe"})

    response = client.delete("/items/del1")

    assert response.status_code == HTTPStatus.NO_CONTENT
    assert client.get("/items/del1").status_code == HTTPStatus.NOT_FOUND


def test_delete_missing_item_returns_404(client: TestClient) -> None:
    response = client.delete("/items/ghost")

    assert response.status_code == HTTPStatus.NOT_FOUND


# ── NDJSON streaming ─────────────────────────────────────────────────────────

def test_stream_empty_yields_no_lines(client: TestClient) -> None:
    response = client.get("/items/stream")

    assert response.status_code == HTTPStatus.OK
    assert response.headers["content-type"] == "application/x-ndjson"
    assert response.text == ""


def test_stream_yields_one_line_per_item(client: TestClient) -> None:
    client.post("/items/", json={"id": "s1", "name": "Alpha"})
    client.post("/items/", json={"id": "s2", "name": "Beta"})

    response = client.get("/items/stream")

    lines = [ln for ln in response.text.splitlines() if ln]
    assert len(lines) == 2
    ids = {json.loads(ln)["id"] for ln in lines}
    assert ids == {"s1", "s2"}


def test_stream_each_line_is_valid_json(client: TestClient) -> None:
    client.post("/items/", json={"id": "j1", "name": "One", "description": "desc"})

    response = client.get("/items/stream")

    for line in response.text.splitlines():
        item = json.loads(line)
        assert "id" in item
        assert "name" in item
