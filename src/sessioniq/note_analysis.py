from __future__ import annotations

import re
from pathlib import Path

from sessioniq.models import NoteMetadata

ACTION_PATTERNS = (
    "todo",
    "to do",
    "needs",
    "need",
    "try",
    "fix",
    "add",
    "reduce",
    "tighten",
    "check",
    "review",
    "export",
    "finish",
    "improve",
)


def analyze_note(path: str | Path) -> NoteMetadata:
    text = Path(path).read_text(encoding="utf-8")
    return NoteMetadata(
        text=text,
        word_count=len(text.split()),
        action_items=extract_action_items(text),
    )


def extract_action_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in text.splitlines():
        line = _clean_note_line(raw_line)
        if not line:
            continue
        lowered = line.lower()
        if any(pattern in lowered for pattern in ACTION_PATTERNS):
            items.append(line)
    return items


def _clean_note_line(line: str) -> str:
    cleaned = re.sub(r"^\s*(?:[-*]|\d+[.)]|\[[ xX]\])\s*", "", line).strip()
    return re.sub(r"\s+", " ", cleaned)
