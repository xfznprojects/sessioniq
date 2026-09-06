from __future__ import annotations

from types import SimpleNamespace

import pytest

from sessioniq.assistant import GroundedAssistant
from sessioniq.models import (
    AssetKind,
    AssistantAnswer,
    AudioMetadata,
    Citation,
    FileStatus,
    ProjectAsset,
    RetrievedSource,
)
from sessioniq.tools import LibraryToolbox


@pytest.fixture(autouse=True)
def llm_enabled(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")


def _audio(asset_id: str, bpm: float, status: FileStatus = FileStatus.READY) -> ProjectAsset:
    return ProjectAsset(
        id=asset_id,
        file_name=f"{asset_id}.wav",
        kind=AssetKind.AUDIO,
        status=status,
        audio=AudioMetadata(duration_seconds=120.0, bpm_estimate=bpm, rms_db=-12.0),
    )


def _tool_call(name: str, arguments: dict) -> SimpleNamespace:
    return SimpleNamespace(
        id=f"call-{name}",
        function=SimpleNamespace(name=name, arguments=__import__("json").dumps(arguments)),
    )


def _tool_round(*calls: SimpleNamespace) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=list(calls)))]
    )


def _no_tool_round() -> SimpleNamespace:
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=None))]
    )


def _final_round(answer: AssistantAnswer) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(message=SimpleNamespace(content=None, tool_calls=None, parsed=answer))
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )


class _FakeChat:
    def __init__(self, responses: list[SimpleNamespace]) -> None:
        self.responses = list(responses)
        self.create_calls: list[dict] = []
        self.parse_calls: list[dict] = []

    def create(self, **kwargs):
        self.create_calls.append(kwargs)
        return self.responses.pop(0)

    def parse(self, **kwargs):
        self.parse_calls.append(kwargs)
        return self.responses.pop(0)


def _install_client(monkeypatch, responses: list[SimpleNamespace]) -> _FakeChat:
    chat = _FakeChat(responses)
    client = SimpleNamespace(chat=SimpleNamespace(completions=chat))
    monkeypatch.setattr(GroundedAssistant, "_client", lambda self: client)
    return chat


def test_agentic_answer_validates_tool_found_citations(monkeypatch):
    """A citation for an asset found by a tool (not retrieval) must pass
    validation because tool sources are appended before checking."""
    ready = _audio("ready", 128.0)
    draft = _audio("draft", 96.0, status=FileStatus.IN_PROGRESS)
    sources = [RetrievedSource(asset=draft, score=1.0)]  # Retrieval only saw the draft.
    toolbox = LibraryToolbox([ready, draft])
    final = AssistantAnswer(
        answer="ready.wav is the fastest at 128.0 BPM.",
        citations=[Citation(asset_id=ready.id, file_name=ready.file_name, evidence="bpm=128.0")],
        confidence="high",
    )
    chat = _install_client(
        monkeypatch,
        [
            _tool_round(_tool_call("filter_assets", {"status": "Ready"})),
            _no_tool_round(),
            _final_round(final),
        ],
    )

    assistant = GroundedAssistant(toolbox=toolbox)
    answer = assistant.answer("Which ready track is fastest?", sources)

    assert answer.answer.startswith("ready.wav")
    expected_calls = [{"name": "filter_assets", "arguments": {"status": "Ready"}}]
    assert assistant.last_meta["tool_calls"] == expected_calls
    assert ready.id in toolbox.touched
    # The tool loop ran with schemas, and the final call asked for the answer.
    assert chat.create_calls[0]["tools"]
    assert "Answer the user's question now" in chat.create_calls[-1]["messages"][-1]["content"]


def test_agentic_failure_falls_back_to_rules_engine(monkeypatch):
    draft = _audio("draft", 96.0, status=FileStatus.IN_PROGRESS)
    sources = [RetrievedSource(asset=draft, score=1.0)]

    def boom(self):
        raise RuntimeError("no endpoint")

    monkeypatch.setattr(GroundedAssistant, "_client", boom)
    assistant = GroundedAssistant(toolbox=LibraryToolbox([draft]))

    answer = assistant.answer("What BPM is this track?", sources)

    assert "96.0 BPM" in answer.answer
    assert assistant.last_meta["engine"] == "rules"


def test_history_flows_into_the_llm_payload(monkeypatch):
    draft = _audio("draft", 96.0)
    sources = [RetrievedSource(asset=draft, score=1.0)]
    final = AssistantAnswer(
        answer="draft.wav runs at 96.0 BPM.",
        citations=[Citation(asset_id=draft.id, file_name=draft.file_name, evidence="bpm=96.0")],
        confidence="high",
    )
    chat = _install_client(monkeypatch, [_final_round(final)])
    history = [
        {"role": "user", "content": "Which track is slowest?"},
        {"role": "assistant", "content": "draft.wav is the slowest."},
    ]

    GroundedAssistant().answer("what about its bpm?", sources, history=history)

    payload = chat.parse_calls[0]["messages"][1]["content"]
    assert '"conversation"' in payload
    assert "draft.wav is the slowest." in payload


def test_decision_answer_lists_recorded_decisions():
    from sessioniq.models import Decision

    draft = _audio("draft", 96.0, status=FileStatus.IN_PROGRESS)
    sources = [RetrievedSource(asset=draft, score=1.0)]
    decisions = [
        Decision(
            id="d1",
            text="Lock the tempo at 96 BPM and cut the bridge.",
            project_name="Unassigned",
            created_at="2026-09-01T10:00:00",
        )
    ]

    answer = GroundedAssistant(decisions=decisions).answer(
        "What did we decide?", sources
    )

    assert "Lock the tempo at 96 BPM" in answer.answer
    assert answer.citations


def _stream_chunk(text: str) -> SimpleNamespace:
    return SimpleNamespace(choices=[SimpleNamespace(delta=SimpleNamespace(content=text))])


def test_streamed_final_emits_deltas_and_parses_citations(monkeypatch):
    draft = _audio("draft", 96.0)
    sources = [RetrievedSource(asset=draft, score=1.0)]
    expected = AssistantAnswer(
        answer="draft.wav runs at 96.0 BPM.",
        citations=[Citation(asset_id=draft.id, file_name=draft.file_name, evidence="bpm=96.0")],
        confidence="medium",
    )

    streamed = [
        _stream_chunk("draft.wav runs at "),
        _stream_chunk("96.0 BPM.\n%%CITATIONS%%\n"),
        _stream_chunk(
            '[{"asset_id": "draft", "file_name": "draft.wav", "evidence": "bpm=96.0"}]'
        ),
    ]

    class _StreamChat:
        def __init__(self) -> None:
            self.create_calls: list[dict] = []

        def create(self, **kwargs):
            self.create_calls.append(kwargs)
            return iter(streamed)

    chat = _StreamChat()
    client = SimpleNamespace(chat=SimpleNamespace(completions=chat))
    monkeypatch.setattr(GroundedAssistant, "_client", lambda self: client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    events: list[tuple[str, dict]] = []
    assistant = GroundedAssistant()
    answer = assistant.answer(
        "what bpm is this?", sources, on_event=lambda kind, data: events.append((kind, data))
    )

    streamed_text = "".join(data["text"] for kind, data in events if kind == "delta")
    assert streamed_text == "draft.wav runs at 96.0 BPM.\n"
    assert answer.answer == expected.answer
    assert answer.citations[0].asset_id == "draft"
    assert chat.create_calls[0].get("stream") is True


def test_streamed_final_without_marker_fails_validation_gracefully(monkeypatch):
    draft = _audio("draft", 96.0)
    sources = [RetrievedSource(asset=draft, score=1.0)]

    class _StreamChat:
        def create(self, **kwargs):
            return iter([_stream_chunk("Some answer with no citation trailer at all.")])

    fake_client = SimpleNamespace(chat=SimpleNamespace(completions=_StreamChat()))
    monkeypatch.setattr(GroundedAssistant, "_client", lambda self: fake_client)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    answer = GroundedAssistant().answer("what bpm is this?", sources, on_event=lambda *a: None)

    # No citations in the trailer -> grounding failed -> refused answer.
    assert answer.answer.startswith("I do not know.")
    assert answer.citations == []
