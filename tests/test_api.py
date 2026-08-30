from __future__ import annotations

import json
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
def client(monkeypatch) -> TestClient:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
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
    for field in (
        "confidence",
        "grounded",
        "sources_retrieved",
        "model",
        "prompt_version",
        "processing_ms",
        "checks",
        "hallucination_risk",
    ):
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


def test_rename_and_move_preserve_task_completion(client):
    lib = _upload_note(client, "Stable Task", b"TODO tighten kick.")
    task = _project(lib, "Stable Task")["tasks"][0]
    client.patch(f"/api/tasks/{task['id']}", json={"status": "Done"})
    response = client.post(
        "/api/projects/rename", json={"old_name": "Stable Task", "new_name": "Renamed Task"}
    )
    renamed = _project(response.json()["library"], "Renamed Task")
    assert renamed["tasks"][0]["id"] == task["id"]
    assert renamed["tasks"][0]["status"] == "Done"
    asset = next(a for a in lib["assets"] if a["project_name"] == "Stable Task")
    response = client.patch(f"/api/assets/{asset['id']}", json={"project_name": "Moved Task"})
    assert _project(response.json()["library"], "Moved Task")["tasks"][0]["status"] == "Done"


def test_delete_legacy_shared_folder_keeps_other_projects(client):
    from sessioniq import api

    _upload_note(client, "Collision A", b"first")
    _upload_note(client, "Collision-A", b"second")
    first = next(a for a in api.ASSETS if a.project_name == "Collision A")
    second = next(a for a in api.ASSETS if a.project_name == "Collision-A")
    assert Path(first.stored_path).parent != Path(second.stored_path).parent
    # Reproduce a pre-update library whose distinct projects share a folder.
    shared = Path(first.stored_path).parent / "second.txt"
    Path(second.stored_path).replace(shared)
    second.stored_path = str(shared)
    response = client.post("/api/projects/delete", json={"name": "Collision A"})
    assert response.status_code == 200
    assert shared.read_bytes() == b"second"
    assert not Path(first.stored_path).exists()
    assert _project(response.json()["library"], "Collision-A")


def test_failed_delete_commit_restores_files_and_library(client, monkeypatch):
    from sessioniq import api

    lib = _upload_note(client, "Rollback Delete", b"keep me")
    asset = next(a for a in lib["assets"] if a["project_name"] == "Rollback Delete")

    def fail_save():
        raise OSError("Disk full")

    monkeypatch.setattr(api, "_save_library_index", fail_save)
    with pytest.raises(OSError, match="Disk full"):
        client.delete(f"/api/assets/{asset['id']}")
    assert Path(asset["stored_path"]).read_bytes() == b"keep me"
    assert any(a.id == asset["id"] for a in api.ASSETS)


def test_failed_rename_commit_restores_original_paths(client, monkeypatch):
    from sessioniq import api

    lib = _upload_note(client, "Rollback Rename", b"keep this path")
    asset = next(a for a in lib["assets"] if a["project_name"] == "Rollback Rename")

    def fail_save():
        raise OSError("Disk full")

    monkeypatch.setattr(api, "_save_library_index", fail_save)
    with pytest.raises(OSError, match="Disk full"):
        client.post(
            "/api/projects/rename",
            json={"old_name": "Rollback Rename", "new_name": "Never Committed"},
        )
    assert Path(asset["stored_path"]).read_bytes() == b"keep this path"
    restored = next(a for a in api.ASSETS if a.id == asset["id"])
    assert restored.project_name == "Rollback Rename"
    assert restored.stored_path == asset["stored_path"]


def test_failed_file_rollback_keeps_original_error_and_restores_other_state(client, monkeypatch):
    from sessioniq import api

    _upload_note(client, "Partial Rollback", b"first file")
    lib = _upload_note(client, "Partial Rollback", b"second file")
    originals = {
        a["id"]: Path(a["stored_path"])
        for a in lib["assets"]
        if a["project_name"] == "Partial Rollback"
    }
    failed_id = list(originals)[-1]  # First attempted restore in the reverse journal.
    moved = {}
    original_error = OSError("Simulated index commit failure")
    committed_index = api.LIBRARY_INDEX_PATH.read_bytes()
    real_replace = Path.replace

    def fail_save():
        moved.update({a.id: Path(a.stored_path) for a in api.ASSETS if a.id in originals})
        raise original_error

    def fail_one_restore(path, target):
        if path == moved.get(failed_id):
            raise PermissionError("Simulated locked file during rollback")
        return real_replace(path, target)

    monkeypatch.setattr(api, "_save_library_index", fail_save)
    monkeypatch.setattr(Path, "replace", fail_one_restore)
    with pytest.raises(OSError) as caught:
        client.post(
            "/api/projects/rename",
            json={
                "old_name": "Partial Rollback",
                "new_name": "Uncommitted Rename",
            },
        )

    assert caught.value is original_error
    assert any(str(moved[failed_id]) in note for note in caught.value.__notes__)
    assert api.LIBRARY_INDEX_PATH.read_bytes() == committed_index
    assert api.FILE_MOVES == []
    assert api.RETRIEVER._collection is None
    for asset_id, original in originals.items():
        restored = next(a for a in api.ASSETS if a.id == asset_id)
        assert restored.project_name == "Partial Rollback"
        assert restored.stored_path == str(original)
        assert any(a is restored for a in api.RETRIEVER.assets)
        if asset_id == failed_id:
            assert moved[asset_id].read_bytes() == b"second file"
            assert not original.exists()  # Requires manual recovery; no false success.
        else:
            assert original.read_bytes() == b"first file"
            assert not moved[asset_id].exists()


@pytest.mark.parametrize("move_file", [False, True])
def test_nested_mutation_rejected_and_outer_state_restored(client, move_file):
    from sessioniq import api

    project = f"Nested Mutation {move_file}"
    lib = _upload_note(client, project, b"keep original bytes")
    asset = next(a for a in lib["assets"] if a["project_name"] == project)
    original_path = Path(asset["stored_path"])
    committed_index = api.LIBRARY_INDEX_PATH.read_bytes()
    inner_calls = []

    @api.mutation
    def inner():
        inner_calls.append(True)

    @api.mutation
    def outer():
        current = next(a for a in api.ASSETS if a.id == asset["id"])
        if move_file:
            api._move_asset(current, f"Moved {project}")
        else:
            current.project_name = f"Changed {project}"
        inner()

    with pytest.raises(RuntimeError, match="Nested mutations are not supported"):
        outer()

    assert inner_calls == []
    assert api.LIBRARY_INDEX_PATH.read_bytes() == committed_index
    restored = next(a for a in api.ASSETS if a.id == asset["id"])
    assert restored.project_name == project
    assert restored.stored_path == str(original_path)
    assert original_path.read_bytes() == b"keep original bytes"
    assert api.FILE_MOVES == []

    # The guard must reset after failure and permit a subsequent normal mutation.
    response = client.post(
        "/api/projects/rename",
        json={"old_name": project, "new_name": f"Recovered {project}"},
    )
    assert response.status_code == 200
    assert _project(response.json()["library"], f"Recovered {project}")


def test_batch_upload_failure_does_not_commit_partial_library(client):
    response = client.post(
        "/api/upload",
        data={"project_name": "Failed Batch"},
        files=[
            ("files", ("good.txt", b"TODO keep", "text/plain")),
            ("files", ("bad.exe", b"bad", "application/octet-stream")),
        ],
    )
    assert response.status_code == 400
    assert not any(
        a["project_name"] == "Failed Batch" for a in client.get("/api/library").json()["assets"]
    )


def test_chat_receives_preferences_and_current_task_status(client, monkeypatch):
    from sessioniq import api
    from sessioniq.assistant import GroundedAssistant

    lib = _upload_note(client, "Remembered Tasks", b"TODO tighten kick.")
    task = _project(lib, "Remembered Tasks")["tasks"][0]
    client.patch(f"/api/tasks/{task['id']}", json={"status": "Done"})
    client.put("/api/memory", json={"preferences": ["Concise mix notes"]})
    captured = {}

    class InspectAssistant(GroundedAssistant):
        def __init__(self, **kwargs):
            captured.update(kwargs)
            super().__init__(**kwargs)

    monkeypatch.setattr(api, "GroundedAssistant", InspectAssistant)
    response = client.post(
        "/api/chat", json={"question": "What tasks are open?", "project_name": "Remembered Tasks"}
    )
    assert response.status_code == 200
    assert captured["preferences"] == ["Concise mix notes"]
    assert "No open tasks" in response.json()["answer"]["answer"]
    assert response.json()["quality"]["hallucination_risk"] == "not assessed"


def test_startup_reconciliation_relinks_renamed_file(client):
    from sessioniq import api

    # A unique name matters: an earlier rollback test deliberately leaves an
    # orphaned mix_notes.txt behind, which would make recovery ambiguous.
    response = client.post(
        "/api/upload",
        files={"files": ("crash-song.txt", b"survived a crash", "text/plain")},
        data={"project_name": "Crash Sim"},
    )
    assert response.status_code == 200, response.text
    asset = next(a for a in api.ASSETS if a.project_name == "Crash Sim")
    # Simulate a process killed mid-rename: files already moved, index not saved.
    moved = api.safe_upload_path("Renamed Sim", Path(asset.stored_path).name)
    Path(asset.stored_path).replace(moved)
    # Earlier tests may leave their own crash leftovers; only our asset matters
    # here (reconciliation recovering those too is the intended behavior).
    api._reconcile_missing_files(api.ASSETS)
    assert Path(asset.stored_path) == moved
    assert asset.project_name == "Crash Sim"  # grouping kept; only the file is relinked
    assert api._asset_payload(asset)["file_missing"] is False


def test_reconciliation_never_adopts_ambiguous_or_owned_files(client):
    from sessioniq import api

    _upload_note(client, "Owner", b"owned")  # mix_notes.txt, still referenced
    _upload_note(client, "Victim", b"lost")  # mix_notes.txt in another folder
    victim = next(a for a in api.ASSETS if a.project_name == "Victim")
    original_path = victim.stored_path
    Path(victim.stored_path).unlink()  # the file is gone, nothing to relink to
    api._reconcile_missing_files(api.ASSETS)
    assert victim.stored_path == original_path  # not adopted the Owner's file

    # Two same-named orphans remain ambiguous: no guessing.
    orphan_dir = api.UPLOAD_ROOT / "orphan"
    orphan_dir.mkdir()
    (orphan_dir / "mix_notes.txt").write_bytes(b"one")
    (orphan_dir.parent / "orphan2" / "mix_notes.txt").parent.mkdir(parents=True)
    (api.UPLOAD_ROOT / "orphan2" / "mix_notes.txt").write_bytes(b"two")
    api._reconcile_missing_files(api.ASSETS)
    assert victim.stored_path == original_path


def test_stale_staging_cleanup_removes_only_old_directories(tmp_path):
    import os
    import time as time_module

    from sessioniq import api

    fresh = api.STAGING_ROOT / "fresh-upload"
    stale = api.STAGING_ROOT / "dead-upload"
    fresh.mkdir(parents=True)
    stale.mkdir(parents=True)
    (fresh / "part.bin").write_bytes(b"x")
    (stale / "part.bin").write_bytes(b"x")
    old = time_module.time() - 48 * 3600
    os.utime(stale, (old, old))
    api._clean_stale_staging()
    assert not stale.exists()
    assert fresh.exists()


def test_asset_payload_flags_missing_file(client):
    from sessioniq import api

    _upload_note(client, "Flag Test", b"note")
    asset = next(a for a in api.ASSETS if a.project_name == "Flag Test")
    assert api._asset_payload(asset)["file_missing"] is False
    Path(asset.stored_path).unlink()
    assert api._asset_payload(asset)["file_missing"] is True


def test_failed_update_restores_asset_fields(client, monkeypatch):
    from sessioniq import api

    _upload_note(client, "Field Rollback", b"TODO keep.")
    asset = next(a for a in api.ASSETS if a.project_name == "Field Rollback")
    response = client.patch(f"/api/assets/{asset.id}", json={"note": "original note"})
    assert response.status_code == 200
    original_tags = list(asset.tags)

    def fail_save():
        raise OSError("Disk full")

    monkeypatch.setattr(api, "_save_library_index", fail_save)
    with pytest.raises(OSError, match="Disk full"):
        client.patch(
            f"/api/assets/{asset.id}",
            json={"status": "Ready", "note": "changed", "tags": [{"label": "x"}]},
        )
    restored = next(a for a in api.ASSETS if a.id == asset.id)
    assert restored.status.value == "Idea"
    assert restored.note == "original note"
    assert restored.tags == original_tags
    assert Path(restored.stored_path).read_bytes() == b"TODO keep."


def test_saved_index_truncates_midi_notes_but_keeps_counts(client):
    from sessioniq import api
    from sessioniq.models import AssetKind, MidiMetadata, MidiNote, ProjectAsset

    notes = [
        MidiNote(
            note_number=60,
            note_name="C4",
            velocity=100,
            start_seconds=i * 0.25,
            duration_seconds=0.2,
        )
        for i in range(600)
    ]
    asset = ProjectAsset(
        id="big-midi",
        file_name="part.mid",
        kind=AssetKind.MIDI,
        project_name="Truncation",
        stored_path=None,
        midi=MidiMetadata(duration_seconds=150.0, note_count=600, notes=notes, tempo_bpm=120.0),
    )
    api.ASSETS.append(asset)
    try:
        api._save_library_index()
        raw = json.loads(api.LIBRARY_INDEX_PATH.read_text(encoding="utf-8"))
    finally:
        api.ASSETS.remove(asset)
        api._save_library_index()
    stored = next(a for a in raw["assets"] if a["id"] == "big-midi")
    assert len(stored["midi"]["notes"]) == 32  # payload/search cap applied to storage too
    assert stored["midi"]["note_count"] == 600  # aggregates survive for search/insights
