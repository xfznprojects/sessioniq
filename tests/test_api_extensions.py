from __future__ import annotations

import math
import os
import struct
import tempfile
import time
import wave
from pathlib import Path

# Same isolation pattern as test_api.py: the app resolves upload root and the
# vector switch at import time. setdefault keeps the suite sharing test_api's
# library while protecting standalone runs from touching a real library.
os.environ.setdefault("SESSIONIQ_DISABLE_VECTOR", "1")
os.environ.setdefault(
    "SESSIONIQ_UPLOAD_ROOT", str(Path(tempfile.mkdtemp(prefix="sessioniq-ext-")) / "uploads")
)

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


def _upload_wav(client: TestClient, project: str, name: str) -> dict:
    sample_rate = 8_000
    frames = []
    for index in range(sample_rate):  # 1s of 220 Hz
        value = int(0.4 * 32767 * math.sin(2 * math.pi * 220 * index / sample_rate))
        frames.append(struct.pack("<h", value))
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as handle:
        with wave.open(handle, "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(sample_rate)
            wav.writeframes(b"".join(frames))
        handle.flush()
        response = client.post(
            "/api/upload",
            files={"files": (name, Path(handle.name).read_bytes(), "audio/wav")},
            data={"project_name": project},
        )
    os.unlink(handle.name)
    assert response.status_code == 200, response.text
    return response.json()


def test_chat_history_resolves_followups_with_heuristic(client: TestClient):
    _upload_note(client, "History Flow", b"TODO tighten the kick before export.")

    first = client.post(
        "/api/chat",
        json={"question": "What tasks are open?", "project_name": "History Flow"},
    )
    assert first.status_code == 200
    first_answer = first.json()["answer"]["answer"]
    assert "tighten the kick" in first_answer
    assert first.json()["standalone_question"] is None

    followup = client.post(
        "/api/chat",
        json={
            "question": "what about its tempo?",
            "project_name": "History Flow",
            "history": [
                {"role": "user", "content": "What tasks are open?"},
                {"role": "assistant", "content": first_answer},
            ],
        },
    )
    assert followup.status_code == 200
    payload = followup.json()
    assert payload["rewrite_method"] == "heuristic"
    assert payload["standalone_question"] is not None
    assert "mix_notes.txt" in payload["standalone_question"]
    # The note stays a cited source for the follow-up.
    assert any(source["file_name"] == "mix_notes.txt" for source in payload["sources"])


def test_decisions_roundtrip_and_answer(client: TestClient):
    _upload_note(client, "Decision Flow", b"TODO print the stems.")
    created = client.post(
        "/api/decisions",
        json={"text": "Lock 96 BPM and cut the bridge.", "project_name": "Decision Flow"},
    )
    assert created.status_code == 200, created.text
    decision = created.json()["decision"]
    assert decision["text"].startswith("Lock 96 BPM")

    listed = client.get("/api/decisions", params={"project": "Decision Flow"})
    assert [item["id"] for item in listed.json()["decisions"]] == [decision["id"]]
    assert client.get("/api/decisions").json()["decisions"]

    answer = client.post(
        "/api/chat",
        json={"question": "What did we decide?", "project_name": "Decision Flow"},
    )
    assert answer.status_code == 200
    assert "Lock 96 BPM" in answer.json()["answer"]["answer"]

    deleted = client.delete(f"/api/decisions/{decision['id']}")
    assert deleted.status_code == 200
    assert client.delete(f"/api/decisions/{decision['id']}").status_code == 404


def test_decisions_reject_empty_text(client: TestClient):
    assert client.post("/api/decisions", json={"text": "   "}).status_code == 422


def test_project_report_renders_markdown(client: TestClient):
    _upload_note(client, "Report Flow", b"TODO finalize the artwork colors.")
    response = client.get("/api/projects/report", params={"project": "Report Flow"})
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/markdown")
    assert "# SessionIQ report — Report Flow" in response.text
    assert "mix_notes.txt" in response.text
    assert "Open tasks" in response.text

    whole_library = client.get("/api/projects/report", params={"project": "All Projects"})
    assert whole_library.status_code == 200
    assert "# SessionIQ report — All Projects" in whole_library.text


def test_transcribe_creates_note_asset_from_audio(client: TestClient, monkeypatch):
    payload = _upload_wav(client, "Voice Flow", "memo.wav")
    asset_id = payload["assets"][0]["id"]

    monkeypatch.setattr(
        "sessioniq.api.transcription_status",
        lambda: {"available": True, "model": "test"},
    )
    monkeypatch.setattr(
        "sessioniq.api.transcribe_audio",
        lambda path: "TODO try a warmer vocal chain. Maybe double the chorus.",
    )

    response = client.post(f"/api/assets/{asset_id}/transcribe")
    assert response.status_code == 200, response.text
    created = response.json()["asset"]
    assert created["file_name"].startswith("memo-transcript")
    assert created["display_type"] == "Notes"
    assert "warmer vocal chain" in created["text"]["text"]
    # Action extraction ran on the transcript, exactly like an uploaded note.
    assert created["text"]["action_items"]


def test_transcribe_reports_missing_extra(client: TestClient, monkeypatch):
    payload = _upload_wav(client, "Voice Flow", "memo2.wav")
    monkeypatch.setattr(
        "sessioniq.api.transcription_status",
        lambda: {"available": False, "hint": "Install the voice extra."},
    )
    response = client.post(f"/api/assets/{payload['assets'][0]['id']}/transcribe")
    assert response.status_code == 409
    assert "voice extra" in response.json()["detail"]


def test_transcribe_rejects_notes(client: TestClient):
    library = _upload_note(client, "Voice Flow", b"Just text.")
    asset_id = library["assets"][0]["id"]
    response = client.post(f"/api/assets/{asset_id}/transcribe")
    assert response.status_code == 400


def test_ai_status_reports_transcription_state(client: TestClient):
    status = client.get("/api/ai-status").json()
    assert "transcription" in status
    assert "available" in status["transcription"]


def test_asset_payload_exposes_derived_timecodes(client: TestClient):
    payload = _upload_wav(client, "Peak Flow", "peaks.wav")
    asset = payload["assets"][0]
    assert "energy_peak_seconds" in asset
    assert "first_beat_seconds" in asset


def test_chat_quality_report_includes_tool_calls_field(client: TestClient):
    _upload_note(client, "Quality Flow", b"TODO check the outro fade.")
    response = client.post("/api/chat", json={"question": "How many files are there?"})
    assert response.status_code == 200
    assert "tool_calls" in response.json()["quality"]


def test_index_persists_decisions(client: TestClient):
    client.post(
        "/api/decisions", json={"text": "Persistence check.", "project_name": "Decision Flow"}
    )
    index_path = Path(os.environ["SESSIONIQ_UPLOAD_ROOT"]).parent / "library-index.json"
    raw = index_path.read_text(encoding="utf-8")
    assert "Persistence check." in raw
    import json as jsonlib

    assert jsonlib.loads(raw)["decisions"][0]["text"] == "Persistence check."


def test_decision_numbers_no_longer_flagged_as_ungrounded(client: TestClient):
    _upload_note(client, "Decision QA", b"TODO check the outro fade.")
    client.post(
        "/api/decisions",
        json={
            "text": "Lock the tempo at 96 BPM and cut the bridge.",
            "project_name": "Decision QA",
        },
    )
    response = client.post(
        "/api/chat", json={"question": "What did we decide?", "project_name": "Decision QA"}
    )
    payload = response.json()
    assert "Lock the tempo at 96 BPM" in payload["answer"]["answer"]
    assert payload["validation"] == []


def test_chat_logs_query_with_feedback_roundtrip(client: TestClient):
    _upload_note(client, "Query Log Flow", b"TODO tighten the kick.")
    response = client.post(
        "/api/chat", json={"question": "What tasks are open?", "project_name": "Query Log Flow"}
    )
    query_id = response.json()["query_id"]
    assert query_id

    log = client.get("/api/queries").json()
    assert log["stats"]["total"] >= 1
    assert any(entry["id"] == query_id for entry in log["entries"])

    rated = client.post(f"/api/queries/{query_id}/feedback", json={"feedback": "up"})
    assert rated.status_code == 200
    assert rated.json()["stats"]["feedback_up"] >= 1
    entry = next(e for e in client.get("/api/queries").json()["entries"] if e["id"] == query_id)
    assert entry["feedback"] == "up"

    cleared = client.post(f"/api/queries/{query_id}/feedback", json={"feedback": None})
    assert cleared.status_code == 200
    assert client.get("/api/queries").json()["stats"]["feedback_up"] == 0

    assert client.post("/api/queries/missing/feedback", json={"feedback": "up"}).status_code == 404


def test_streaming_chat_emits_events_and_final_payload(client: TestClient):
    _upload_note(client, "Stream Flow", b"TODO tidy the outro.")
    frames: list[tuple[str, dict]] = []
    with client.stream(
        "POST", "/api/chat/stream", json={"question": "What tasks are open?"}
    ) as response:
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/event-stream")
        import json as jsonlib

        buffer = ""
        for chunk in response.iter_text():
            buffer += chunk
            while "\n\n" in buffer:
                frame, buffer = buffer.split("\n\n", 1)
                kind, data_text = "message", ""
                for line in frame.split("\n"):
                    if line.startswith("event: "):
                        kind = line[len("event: "):].strip()
                    elif line.startswith("data: "):
                        data_text += line[len("data: "):]
                if data_text:
                    frames.append((kind, jsonlib.loads(data_text)))

    kinds = [kind for kind, _ in frames]
    assert "delta" in kinds
    assert kinds[-1] == "done"
    done = frames[-1][1]
    assert "tighten" in done["answer"]["answer"] or done["answer"]["answer"]
    assert done["query_id"]
    assert done["sources"]
    assert "validation" in done and "quality" in done


def test_reanalyze_upgrades_metadata_and_preserves_curation(client: TestClient):
    payload = _upload_wav(client, "Reanalyze Flow", "legacy.wav")
    asset = payload["assets"][0]
    client.patch(f"/api/assets/{asset['id']}", json={
        "status": "Ready",
        "tags": [{"label": "keep-me", "ai_suggested": False, "color": "blue"}],
        "note": "curated note",
    })

    response = client.post(f"/api/assets/{asset['id']}/reanalyze")

    assert response.status_code == 200, response.text
    refreshed = response.json()["asset"]
    assert refreshed["id"] == asset["id"]
    assert refreshed["status"] == "Ready"
    assert refreshed["note"] == "curated note"
    assert any(tag["label"] == "keep-me" for tag in refreshed["tags"])
    assert refreshed["last_analyzed"]
    assert refreshed["mode"] in {"major", "minor"}  # populated by re-analysis


def test_reanalyze_rejects_missing_file(client: TestClient):
    library = _upload_note(client, "Reanalyze Flow", b"plain note")
    asset_id = library["assets"][0]["id"]
    response = client.post(f"/api/assets/{asset_id}/reanalyze")
    assert response.status_code == 200  # note files re-parse fine


def test_reference_nextup_digest_and_scan_endpoints(client: TestClient, tmp_path):
    _upload_note(client, "Advisor Flow", b"TODO finalize the chain.")

    assert client.get("/api/reference", params={"project": "Advisor Flow"}).json() == {
        "reference": None,
        "comparisons": [],
    }
    assert client.get("/api/reference", params={"project": "All Projects"}).status_code == 400

    ranking = client.get("/api/next-up").json()["ranking"]
    assert any(item["project_name"] == "Advisor Flow" for item in ranking)

    digest = client.get("/api/digest").json()
    assert digest["open_tasks"] >= 1
    assert "generated_at" in digest

    scan_dir = tmp_path / "bounces"
    scan_dir.mkdir()
    (scan_dir / "idea.txt").write_text("Scanned TODO: try a wider stereo image.", encoding="utf-8")
    scanned = client.post("/api/library/scan", json={"path": str(scan_dir), "note": "from scan"})
    assert scanned.status_code == 200, scanned.text
    names = [asset["file_name"] for asset in scanned.json()["assets"]]
    assert "idea.txt" in names
    # The source folder is copied, not emptied.
    assert (scan_dir / "idea.txt").exists()

    missing = client.post("/api/library/scan", json={"path": str(tmp_path / "missing")})
    assert missing.status_code == 400
    empty = tmp_path / "empty"
    empty.mkdir()
    assert client.post("/api/library/scan", json={"path": str(empty)}).status_code == 400


def test_next_up_chat_answer_ranks_projects(client: TestClient):
    _upload_note(client, "Rank Flow", b"TODO widen the stereo image.")
    response = client.post(
        "/api/chat", json={"question": "What should I finish next?"}
    )
    payload = response.json()
    answer_lines = payload["answer"]["answer"].splitlines()
    assert answer_lines[0] == "Finish these next:"
    # A ranked, numbered list of projects with at least one citation.
    assert len(answer_lines) >= 2 and answer_lines[1].startswith("1. ")
    assert payload["answer"]["citations"]


def test_chat_receives_summaries_for_ranking(client: TestClient, monkeypatch):
    captured = {}

    class FakeToolbox:
        assets = []
        touched = {}

        def execute(self, *args, **kwargs):
            return "{}"

    import sessioniq.api as api_module

    original = api_module.GroundedAssistant

    class SpyAssistant(original):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, **kwargs)
            captured["summaries"] = kwargs.get("summaries")

    monkeypatch.setattr(api_module, "GroundedAssistant", SpyAssistant)
    _upload_note(client, "Summary Flow", b"TODO check levels.")
    client.post("/api/chat", json={"question": "overview of the project"})
    assert captured["summaries"], "assistant should receive project summaries"


def test_job_lifecycle_transcribe(client: TestClient, monkeypatch):
    payload = _upload_wav(client, "Job Flow", "voice_memo.wav")
    asset_id = payload["assets"][0]["id"]
    monkeypatch.setattr(
        "sessioniq.api.transcription_status", lambda: {"available": True, "model": "test"}
    )
    monkeypatch.setattr(
        "sessioniq.api.transcribe_audio", lambda path: "TODO re-record the second verse louder."
    )

    started = client.post("/api/jobs/transcribe", json={"asset_id": asset_id})
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]

    for _ in range(80):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert "updated" not in job  # result is the transcript commit payload
    library = client.get("/api/library").json()
    assert any(
        a["file_name"].startswith("voice_memo-transcript") for a in library["assets"]
    )
    assert client.get("/api/jobs/missing").status_code == 404
    assert client.get("/api/jobs").json()["jobs"]


def test_batch_reanalyze_job_upgrades_and_reports(client: TestClient):
    payload = _upload_wav(client, "Batch Flow", "old_analysis.wav")
    asset_id = payload["assets"][0]["id"]

    started = client.post("/api/jobs/reanalyze", json={"scope": "Batch Flow"})
    assert started.status_code == 200, started.text
    job_id = started.json()["job_id"]

    for _ in range(120):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "done", job
    assert job["progress"]["total"] == 1
    assert job["result"]["updated"] == 1
    library = client.get("/api/library").json()
    refreshed = next(a for a in library["assets"] if a["id"] == asset_id)
    assert refreshed["last_analyzed"]
    assert refreshed["mode"] in {"major", "minor", None}

    assert client.post("/api/jobs/reanalyze", json={"scope": "No Such Project"}).status_code == 400
    cancel = client.post("/api/jobs/missing/cancel")
    assert cancel.status_code == 404 or cancel.status_code == 409


def test_cancelled_batch_job_preserves_library(client: TestClient, monkeypatch):
    import sessioniq.jobs as jobs_module

    _upload_wav(client, "Cancel Flow", "cancel_me.wav")
    _upload_wav(client, "Cancel Flow", "second.wav")

    original_ingest = __import__("sessioniq.api", fromlist=["ingest_file"]).ingest_file

    def slow_ingest(path, *args, **kwargs):
        # Cancel whatever reanalyze job is running; the runner thread may
        # start before the POST response carries the id back to the test.
        with jobs_module.JOB_LOCK:
            running = [
                job_id for job_id, job in jobs_module.JOBS.items() if job["status"] == "running"
            ]
        for job_id in running:
            jobs_module.request_cancel(job_id)
        return original_ingest(path, *args, **kwargs)

    monkeypatch.setattr("sessioniq.api.ingest_file", slow_ingest)
    started = client.post("/api/jobs/reanalyze", json={"scope": "Cancel Flow"})
    job_id = started.json()["job_id"]
    for _ in range(120):
        job = client.get(f"/api/jobs/{job_id}").json()
        if job["status"] != "running":
            break
        time.sleep(0.05)
    assert job["status"] == "cancelled"
    # The first file's analysis is discarded; the library still lists both files.
    library = client.get("/api/library").json()
    names = {a["file_name"] for a in library["assets"] if a["project_name"] == "Cancel Flow"}
    assert {"cancel_me.wav", "second.wav"} <= names
