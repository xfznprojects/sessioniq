from __future__ import annotations

import os
import tempfile
from pathlib import Path

# Isolate the app from the developer's real library and the optional vector
# stack before importing it (both are resolved at module import time).
os.environ["SESSIONIQ_DISABLE_VECTOR"] = "1"
_UPLOAD_ROOT = Path(tempfile.mkdtemp(prefix="sessioniq-api-")) / "uploads"
os.environ["SESSIONIQ_UPLOAD_ROOT"] = str(_UPLOAD_ROOT)

import pytest  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from sessioniq.api import app  # noqa: E402


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


def _upload_note(client: TestClient, project: str, body: bytes) -> dict:
    response = client.post(
        "/api/upload",
        files={"files": ("mix_notes.txt", body, "text/plain")},
        data={"project_name": project},
    )
    assert response.status_code == 200, response.text
    return response.json()["library"]


def _project(library: dict, name: str) -> dict:
    return next(p for p in library["projects"] if p["project_name"] == name)


def test_task_status_update_drives_progress(client: TestClient):
    library = _upload_note(client, "Task Flow", b"TODO tighten the kick before export.")
    project = _project(library, "Task Flow")
    assert project["tasks"], "note action items should surface as tasks"
    assert project["progress"] == 0.0
    task_id = project["tasks"][0]["id"]

    response = client.patch(f"/api/tasks/{task_id}", json={"status": "Done"})
    assert response.status_code == 200
    project = _project(response.json()["library"], "Task Flow")
    assert project["tasks"][0]["status"] == "Done"
    assert project["progress"] == 1.0


def test_unknown_task_returns_404(client: TestClient):
    assert client.patch("/api/tasks/does-not-exist", json={"status": "Done"}).status_code == 404


def test_chat_returns_quality_report(client: TestClient):
    _upload_note(client, "QA Flow", b"Bounce a final master before Friday.")
    response = client.post("/api/chat", json={"question": "what needs work?"})
    assert response.status_code == 200
    quality = response.json()["quality"]
    for field in ("confidence", "grounded", "sources_retrieved", "model", "prompt_version",
                  "processing_ms", "checks", "hallucination_risk"):
        assert field in quality, f"quality report missing {field}"
    assert quality["prompt_version"].startswith("v")
    assert isinstance(quality["checks"], list) and quality["checks"]


def test_pipeline_reports_stages(client: TestClient):
    response = client.get("/api/pipeline")
    assert response.status_code == 200
    body = response.json()
    stage_ids = [stage["id"] for stage in body["stages"]]
    assert stage_ids[0] == "upload" and stage_ids[-1] == "answer"
    assert {"embeddings", "retriever", "llm", "validation"}.issubset(set(stage_ids))


def test_project_health_flags_missing_pieces(client: TestClient):
    library = _upload_note(client, "Health Check", b"Try a brighter hat.")
    project = _project(library, "Health Check")
    health = project["health"]
    assert 0.0 <= health["score"] <= 1.0
    labels = {check["label"]: check["ok"] for check in health["checks"]}
    assert labels["Reference track"] is False
    assert labels["Master / export"] is False
    assert health["suggestions"], "missing pieces should produce suggestions"


def test_semantic_search_ranks_by_content(client: TestClient):
    _upload_note(client, "Search Flow", b"TODO master the low end before release.")
    response = client.post("/api/search", json={"query": "what still needs mastering?"})
    assert response.status_code == 200
    results = response.json()["results"]
    assert results, "semantic search should return content matches"
    assert all("score" in r for r in results)


def test_similar_endpoint_returns_matches(client: TestClient):
    lib = _upload_note(client, "Sim Flow", b"first note")
    # Need at least two assets; upload a second note.
    client.post(
        "/api/upload",
        files={"files": ("second.txt", b"second note", "text/plain")},
        data={"project_name": "Sim Flow"},
    )
    lib = client.get("/api/library").json()
    asset_id = next(a["id"] for a in lib["assets"] if a["project_name"] == "Sim Flow")
    response = client.get(f"/api/assets/{asset_id}/similar")
    assert response.status_code == 200
    assert "matches" in response.json()


def test_inline_note_update(client: TestClient):
    lib = _upload_note(client, "Notes Flow", b"initial")
    asset_id = next(a["id"] for a in lib["assets"] if a["project_name"] == "Notes Flow")
    response = client.patch(f"/api/assets/{asset_id}", json={"note": "  tighten the low end  "})
    assert response.status_code == 200
    asset = next(a for a in response.json()["library"]["assets"] if a["id"] == asset_id)
    assert asset["note"] == "tighten the low end"


def test_delete_asset_removes_file_and_index(client: TestClient, tmp_path):
    from sessioniq.api import UPLOAD_ROOT

    lib = _upload_note(client, "Delete Flow", b"bye")
    asset = next(a for a in lib["assets"] if a["project_name"] == "Delete Flow")
    stored = Path(asset["stored_path"])
    assert stored.exists()

    response = client.delete(f"/api/assets/{asset['id']}")
    assert response.status_code == 200
    remaining = [a["id"] for a in response.json()["library"]["assets"]]
    assert asset["id"] not in remaining
    assert not stored.exists()
    assert UPLOAD_ROOT  # imported for clarity


def test_image_upload_becomes_project_artwork(client: TestClient):
    # 1x1 transparent PNG
    png = bytes.fromhex(
        "89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c4"
        "890000000a49444154789c6360000002000154a24f9f0000000049454e44ae426082"
    )
    response = client.post(
        "/api/upload",
        files={"files": ("cover.png", png, "image/png")},
        data={"project_name": "Art Flow"},
    )
    assert response.status_code == 200
    lib = response.json()["library"]
    project = _project(lib, "Art Flow")
    assert project["artwork"], "image should become the project's cover artwork"
    image_asset = next(a for a in lib["assets"] if a["display_type"] == "Image")
    assert image_asset["media_url"]


def test_memory_persists_preferences(client: TestClient):
    response = client.put("/api/memory", json={"preferences": ["darker kicks", "Techno", "  "]})
    assert response.status_code == 200
    body = response.json()
    assert body["preferences"] == ["darker kicks", "Techno"]  # blanks dropped
    assert "stats" in body and "derived" in body
    # survives a fresh GET
    assert client.get("/api/memory").json()["preferences"] == ["darker kicks", "Techno"]


def test_plugins_registry_lists_active_analyzers(client: TestClient):
    body = client.get("/api/plugins").json()
    names = [p["name"] for p in body["plugins"]]
    assert "BPM Detector" in names and "MIDI Parser" in names
    assert body["planned"], "planned integrations should be advertised"


def test_delete_project_removes_all_songs_and_files(client: TestClient):
    _upload_note(client, "Doomed Album/Song A", b"a")
    lib = _upload_note(client, "Doomed Album/Song B", b"b")
    stored = [
        Path(a["stored_path"])
        for a in lib["assets"]
        if a["project_name"].startswith("Doomed Album")
    ]
    assert all(p.exists() for p in stored)

    response = client.post("/api/projects/delete", json={"name": "Doomed Album"})
    assert response.status_code == 200
    names = [p["project_name"] for p in response.json()["library"]["projects"]]
    assert not any(n.startswith("Doomed Album") for n in names)
    assert all(not p.exists() for p in stored)

    assert client.post("/api/projects/delete", json={"name": "ghost"}).status_code == 404


def test_album_rename_renames_all_songs_under_it(client: TestClient):
    _upload_note(client, "Old Album/Song A", b"a")
    _upload_note(client, "Old Album/Song B", b"b")
    response = client.post(
        "/api/projects/rename",
        json={"old_name": "Old Album", "new_name": "New Album"},
    )
    assert response.status_code == 200
    names = [p["project_name"] for p in response.json()["library"]["projects"]]
    assert "New Album/Song A" in names
    assert "New Album/Song B" in names
    assert not any(n.startswith("Old Album") for n in names)


def test_project_rename_moves_assets(client: TestClient):
    _upload_note(client, "Working Title", b"Try a wider chorus.")
    response = client.post(
        "/api/projects/rename",
        json={"old_name": "Working Title", "new_name": "Final Title"},
    )
    assert response.status_code == 200
    names = [p["project_name"] for p in response.json()["library"]["projects"]]
    assert "Final Title" in names
    assert "Working Title" not in names
