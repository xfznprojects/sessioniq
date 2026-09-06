from __future__ import annotations

from sessioniq.assistant import GroundedAssistant
from sessioniq.models import (
    AssetKind,
    AssistantAnswer,
    Citation,
    NoteMetadata,
    ProjectAsset,
    RetrievedSource,
)
from sessioniq.validation import validate_grounded_answer


def test_validation_rejects_uncited_source_answer():
    source = _source("notes.md")
    answer = AssistantAnswer(answer="The chorus needs work.", citations=[])

    errors = validate_grounded_answer(answer, [source])

    assert "at least one citation" in errors[0]


def test_validation_rejects_unknown_citation():
    source = _source("notes.md")
    answer = AssistantAnswer(
        answer="The chorus needs work.",
        citations=[Citation(file_name="other.md", evidence="chorus")],
    )

    errors = validate_grounded_answer(answer, [source])

    assert "was not present" in errors[0]


def test_no_source_answer_must_say_do_not_know():
    answer = AssistantAnswer(answer="Try adding compression.", citations=[])

    errors = validate_grounded_answer(answer, [])

    assert errors == ["Answer should say it does not know when no source data is available."]


def test_assistant_without_sources_says_do_not_know():
    answer = GroundedAssistant().answer("What is the BPM?", [])

    assert "do not know" in answer.answer.lower()
    assert answer.citations == []


def test_assistant_deterministic_answer_cites_sources(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
    source = _source("notes.md")

    answer = GroundedAssistant().answer("What does the note say?", [source])

    assert answer.citations[0].file_name == "notes.md"
    assert "chorus" in answer.answer


def _source(file_name: str) -> RetrievedSource:
    asset = ProjectAsset(
        id=file_name,
        file_name=file_name,
        kind=AssetKind.NOTE,
        text=NoteMetadata(text="The chorus needs a wider harmony stack.", word_count=8),
    )
    return RetrievedSource(asset=asset, score=1.0)


def _decision(text: str):
    from sessioniq.models import Decision

    return Decision(
        id="d1",
        text=text,
        project_name="Unassigned",
        created_at="2026-09-06T00:00:00",
    )


def test_decision_numbers_count_as_grounded_claims():
    source = _source("notes.md")
    answer = AssistantAnswer(
        answer="Recorded decisions:\n- Lock Afterglow at 96 BPM, cut the bridge.",
        citations=[Citation(asset_id="notes.md", file_name="notes.md", evidence="project context")],
    )

    errors = validate_grounded_answer(answer, [source], decisions=[_decision("Lock 96 BPM.")])

    assert errors == []


def test_note_text_numbers_count_as_grounded_claims():
    source = _source_with_note("Target the master at 110 BPM before Friday.")
    answer = AssistantAnswer(
        answer="The note targets the master at 110 BPM before Friday.",
        citations=[
            Citation(
                asset_id="notes.md", file_name="notes.md", evidence="production note text"
            )
        ],
    )

    errors = validate_grounded_answer(answer, [source])

    assert errors == []


def test_unsupported_numbers_still_flagged():
    source = _source("notes.md")
    answer = AssistantAnswer(
        answer="The track runs at 96 BPM.",
        citations=[Citation(asset_id="notes.md", file_name="notes.md", evidence="project context")],
    )

    errors = validate_grounded_answer(
        answer, [source], decisions=[_decision("Lock 88 BPM.")]
    )

    assert any("bpm=96" in error for error in errors)


def _source_with_note(text: str) -> RetrievedSource:
    asset = ProjectAsset(
        id="notes.md",
        file_name="notes.md",
        kind=AssetKind.NOTE,
        text=NoteMetadata(text=text, word_count=8, action_items=[]),
    )
    return RetrievedSource(asset=asset, score=1.0)
