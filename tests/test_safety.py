from __future__ import annotations

import json

import pytest

from sessioniq.models import (
    AssetKind,
    AssistantAnswer,
    AudioMetadata,
    Citation,
    FileStatus,
    NoteMetadata,
    ProjectAsset,
    RetrievedSource,
)
from sessioniq.persistence import save_index
from sessioniq.project_workspace import _task_id, project_health, summarize_projects
from sessioniq.validation import validate_grounded_answer


def test_old_task_status_migrates_before_rename():
    asset = ProjectAsset(
        id="stable-id",
        file_name="notes.txt",
        kind=AssetKind.NOTE,
        project_name="Old",
        text=NoteMetadata(text="TODO mix", word_count=2, action_items=["TODO mix"]),
    )
    statuses = {_task_id("Old", "notes.txt", "TODO mix"): "Done"}
    first = summarize_projects([asset], statuses)[0].tasks[0]
    asset.project_name = "New"
    second = summarize_projects([asset], statuses)[0].tasks[0]
    assert second.id == first.id
    assert second.status == "Done"


def test_artwork_and_final_notes_are_not_audio_deliverables():
    assets = [
        ProjectAsset(
            id="cover", file_name="cover.png", kind=AssetKind.IMAGE, status=FileStatus.REFERENCE
        ),
        ProjectAsset(
            id="final", file_name="final.txt", kind=AssetKind.NOTE, status=FileStatus.READY
        ),
    ]
    checks = {check.label: check.ok for check in project_health(assets, []).checks}
    assert not checks["Reference track"]
    assert not checks["Master / export"]


def test_invented_tempo_fails_even_with_valid_citation():
    asset = ProjectAsset(
        id="mix",
        file_name="mix.wav",
        kind=AssetKind.AUDIO,
        audio=AudioMetadata(duration_seconds=30, bpm_estimate=120),
    )
    answer = AssistantAnswer(
        answer="mix.wav is 999 BPM.",
        citations=[Citation(asset_id="mix", file_name="mix.wav", evidence="bpm=999")],
    )
    assert validate_grounded_answer(answer, [RetrievedSource(asset=asset, score=1)])
    answer.answer = "mix.wav is 120 BPM."
    answer.citations[0].evidence = "bpm=120"
    assert not validate_grounded_answer(answer, [RetrievedSource(asset=asset, score=1)])


def test_atomic_save_failure_preserves_original_and_backup(tmp_path, monkeypatch):
    from sessioniq import persistence

    path = tmp_path / "library-index.json"
    save_index(path, {"assets": ["original"]})
    replace = persistence.os.replace

    def fail_index(source, target):
        if target == path:
            raise OSError("Disk full")
        return replace(source, target)

    monkeypatch.setattr(persistence.os, "replace", fail_index)
    with pytest.raises(OSError):
        save_index(path, {"assets": ["new"]})
    assert json.loads(path.read_text()) == {"assets": ["original"]}
    assert json.loads(path.with_suffix(".json.bak").read_text()) == {"assets": ["original"]}


def test_known_good_index_skips_reparse(tmp_path, monkeypatch):
    from sessioniq import persistence

    path = tmp_path / "library-index.json"
    persistence.save_index(path, {"assets": ["first"]})
    calls = []
    real_loads = persistence.json.loads

    def counting_loads(raw):
        calls.append(raw)
        return real_loads(raw)

    monkeypatch.setattr(persistence.json, "loads", counting_loads)
    persistence.save_index(path, {"assets": ["second"]})  # previous bytes known good
    assert calls == []

    path.write_text(json.dumps({"assets": [" externally edited"]}))  # differs from cache
    persistence.save_index(path, {"assets": ["third"]})
    assert len(calls) == 1  # externally modified content is still verified once
    assert json.loads(path.read_text()) == {"assets": ["third"]}
