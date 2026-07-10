from __future__ import annotations

import pytest

from sessioniq.assistant import GroundedAssistant, llm_status
from sessioniq.models import (
    AssetKind,
    AudioMetadata,
    FileStatus,
    NoteMetadata,
    ProjectAsset,
    RetrievedSource,
)


@pytest.fixture(autouse=True)
def no_llm(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)


def _audio_asset(
    asset_id: str,
    bpm: float,
    rms_db: float = -18.0,
    duration: float = 120.0,
    key: str | None = None,
    status: FileStatus = FileStatus.IDEA,
) -> ProjectAsset:
    return ProjectAsset(
        id=asset_id,
        file_name=f"{asset_id}.wav",
        kind=AssetKind.AUDIO,
        status=status,
        audio=AudioMetadata(
            duration_seconds=duration,
            bpm_estimate=bpm,
            rms_amplitude=0.1,
            rms_db=rms_db,
            peak_amplitude=0.9,
            peak_db=-1.0,
            key_estimate=key,
        ),
    )


def _sources(*assets: ProjectAsset) -> list[RetrievedSource]:
    return [RetrievedSource(asset=asset, score=1.0) for asset in assets]


def test_superlative_fastest_picks_max_bpm():
    sources = _sources(_audio_asset("slow", 90.0), _audio_asset("fast", 150.0))

    answer = GroundedAssistant().answer("Which track is the fastest?", sources)

    assert "fast.wav" in answer.answer.splitlines()[0]
    assert "150.0" in answer.answer
    assert answer.confidence == "high"
    assert {citation.file_name for citation in answer.citations} == {"slow.wav", "fast.wav"}


def test_superlative_loudest_uses_rms_db():
    sources = _sources(
        _audio_asset("quiet", 120.0, rms_db=-24.0),
        _audio_asset("hot", 120.0, rms_db=-9.0),
    )

    answer = GroundedAssistant().answer("which one is the loudest?", sources)

    assert answer.answer.startswith("hot.wav")


def test_task_answer_lists_action_items():
    note = ProjectAsset(
        id="mix-notes",
        file_name="mix_notes.txt",
        kind=AssetKind.NOTE,
        text=NoteMetadata(
            text="TODO tighten kick.\nTry shorter reverb.",
            word_count=7,
            action_items=["TODO tighten kick.", "Try shorter reverb."],
        ),
    )

    answer = GroundedAssistant().answer("What tasks are still open?", _sources(note))

    assert "tighten kick" in answer.answer
    assert answer.citations[0].file_name == "mix_notes.txt"


def test_count_answer_lists_all_files():
    sources = _sources(_audio_asset("one", 100.0), _audio_asset("two", 110.0))

    answer = GroundedAssistant().answer("How many files do I have?", sources)

    assert "2 file(s)" in answer.answer
    assert "one.wav" in answer.answer
    assert "two.wav" in answer.answer


def test_key_answer_groups_shared_keys():
    sources = _sources(
        _audio_asset("first", 100.0, key="A"),
        _audio_asset("second", 110.0, key="A"),
    )

    answer = GroundedAssistant().answer("What key are these in?", sources)

    assert "A" in answer.answer
    assert "first.wav" in answer.answer
    assert "second.wav" in answer.answer


def test_status_answer_filters_ready_files():
    sources = _sources(
        _audio_asset("done", 100.0, status=FileStatus.READY),
        _audio_asset("wip", 110.0, status=FileStatus.IN_PROGRESS),
    )

    answer = GroundedAssistant().answer("Which files are ready?", sources)

    assert "done.wav" in answer.answer
    assert "wip.wav" not in answer.answer


def test_fallback_still_cites_sources():
    sources = _sources(_audio_asset("mystery", 100.0))

    answer = GroundedAssistant().answer("zzz unrelated question", sources)

    assert answer.citations
    assert answer.citations[0].file_name == "mystery.wav"


def test_llm_status_reports_rules_mode():
    assert llm_status()["mode"] == "rules"


def test_llm_status_reports_local_llm(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://localhost:11434/v1")
    monkeypatch.setenv("SESSIONIQ_MODEL", "llama3.2")

    status = llm_status()

    assert status["mode"] == "local-llm"
    assert status["model"] == "llama3.2"


def test_unreachable_local_llm_falls_back_to_rules(monkeypatch):
    monkeypatch.setenv("OPENAI_BASE_URL", "http://127.0.0.1:9")  # nothing listens here
    monkeypatch.setenv("SESSIONIQ_MODEL", "llama3.2")
    sources = _sources(_audio_asset("slow", 90.0), _audio_asset("fast", 150.0))

    answer = GroundedAssistant().answer("Which track is the fastest?", sources)

    assert "fast.wav" in answer.answer
    assert answer.citations
