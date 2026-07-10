from __future__ import annotations

from sessioniq.note_analysis import analyze_note, extract_action_items


def test_extract_action_items_from_production_notes():
    text = """
    Kick feels fine.
    - TODO tighten kick and bass.
    * Try shorter reverb on vocal.
    [ ] Check export loudness target.
    """

    items = extract_action_items(text)

    assert items == [
        "TODO tighten kick and bass.",
        "Try shorter reverb on vocal.",
        "Check export loudness target.",
    ]


def test_analyze_note_includes_action_items(tmp_path):
    path = tmp_path / "mix_notes.md"
    path.write_text("Need wider pads.\nArrangement feels good.", encoding="utf-8")

    metadata = analyze_note(path)

    assert metadata.word_count == 6
    assert metadata.action_items == ["Need wider pads."]
