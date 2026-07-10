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
