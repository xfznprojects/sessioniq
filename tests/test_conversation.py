from __future__ import annotations

from sessioniq.conversation import (
    deterministic_standalone,
    looks_like_followup,
    referenced_asset_names,
    resolve_standalone,
)


class _FakeAsset:
    def __init__(self, file_name: str) -> None:
        self.file_name = file_name


ASSETS = [
    _FakeAsset("afterglow_rough_mix.wav"),
    _FakeAsset("midnight_drive.mp3"),
    _FakeAsset("mix.txt"),
]


def test_first_questions_are_not_treated_as_followups():
    assert not looks_like_followup("Which track is the fastest?", has_history=True)
    assert not looks_like_followup("What still needs work?", has_history=False)


def test_reference_words_and_short_questions_flag_followups():
    assert looks_like_followup("What about its key?", has_history=True)
    assert looks_like_followup("and the loudest?", has_history=True)
    assert looks_like_followup("why?", has_history=True)


def test_referenced_names_match_stems_and_tokens():
    names = referenced_asset_names(
        "afterglow_rough_mix.wav is the loudest at -9.0 dB RMS.", ASSETS
    )
    assert names == ["afterglow_rough_mix.wav"]

    # Token matching lets prose ("Afterglow is done") find the full file name.
    assert referenced_asset_names("Afterglow is done.", ASSETS) == ["afterglow_rough_mix.wav"]


def test_referenced_names_prefer_longer_stems():
    assets = [_FakeAsset("mix.wav"), _FakeAsset("afterglow_mix.wav")]
    names = referenced_asset_names("afterglow_mix.wav and mix.wav both peak hot.", assets)
    assert names[0] == "afterglow_mix.wav"


def test_deterministic_standalone_appends_referenced_files():
    history = [
        {"role": "user", "content": "Which track is the loudest?"},
        {"role": "assistant", "content": "afterglow_rough_mix.wav is the loudest."},
    ]
    rewritten = deterministic_standalone("What about its key?", history, ASSETS)
    assert "afterglow_rough_mix.wav" in rewritten
    assert rewritten.startswith("What about its key?")


def test_deterministic_standalone_without_matches_is_unchanged():
    history = [{"role": "assistant", "content": "I do not know."}]
    assert deterministic_standalone("what about it?", history, ASSETS) == "what about it?"


def test_resolve_standalone_passes_first_questions_through():
    question, method = resolve_standalone("Which track is fastest?", [], ASSETS, llm_available=True)
    assert question == "Which track is fastest?"
    assert method is None


def test_resolve_standalone_falls_back_to_heuristic_when_llm_fails(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("endpoint down")

    monkeypatch.setattr("sessioniq.conversation.condense_with_llm", boom)
    history = [{"role": "assistant", "content": "midnight_drive.mp3 is the slowest."}]
    question, method = resolve_standalone(
        "what about its bpm?", history, ASSETS, llm_available=True
    )
    assert method == "heuristic"
    assert "midnight_drive.mp3" in question
