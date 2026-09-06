"""Resolve follow-up questions into standalone questions for retrieval.

The retriever ranks assets per question, so "what about its key?" retrieves
nothing useful until it is resolved against the files the previous answer
discussed. When a model is configured, an LLM condenses the follow-up; the
deterministic heuristic (match file names mentioned in the last answer)
covers offline mode and acts as the LLM fallback.
"""

from __future__ import annotations

import logging
import re
from typing import Protocol

logger = logging.getLogger(__name__)

# Cap the conversation window so prompts stay small and the condense call cheap.
MAX_CONDENSE_TURNS = 8
MAX_STANDALONE_CHARS = 500

# Pronouns and demonstratives that usually point at the previous turn's subject.
REFERENCE_TOKENS = frozenset(
    {
        "it",
        "its",
        "it's",
        "that",
        "that's",
        "this",
        "these",
        "those",
        "they",
        "them",
        "their",
        "there",
        "one",
        "ones",
    }
)
FOLLOWUP_TRIGGERS = (
    "what about",
    "how about",
    "and the",
    "tell me more",
    "go on",
    "why",
    "compare it",
)

_WORD_RE = re.compile(r"[a-z0-9']+")


class _AssetLike(Protocol):
    file_name: str


def looks_like_followup(question: str, has_history: bool) -> bool:
    """Cheap gate so first questions never pay for reference resolution."""
    if not has_history:
        return False
    words = set(_WORD_RE.findall(question.lower()))
    if words & REFERENCE_TOKENS:
        return True
    if any(trigger in question.lower() for trigger in FOLLOWUP_TRIGGERS):
        return True
    return len(words) <= 3


# Stems shorter than this are too generic to anchor a follow-up ("mix",
# "new", "rev" match everywhere).
MIN_STEM_LENGTH = 4


def referenced_asset_names(
    answer_text: str,
    assets: list[_AssetLike],
    limit: int = 3,
) -> list[str]:
    """File names from the library that the previous answer talked about.

    Longer stems are checked first so "afterglow_rough_mix" wins over "mix".
    A stem matches when it appears contiguously, or when its distinctive first
    word plus at least half of its meaningful words do — enough for
    "Afterglow is the loudest" to find "afterglow_rough_mix.wav".
    """
    text = re.sub(r"[^a-z0-9]+", " ", answer_text.lower())
    ranked = sorted(assets, key=lambda asset: len(asset.file_name), reverse=True)
    found: list[str] = []
    for asset in ranked:
        stem = re.sub(r"\.[^.]+$", "", asset.file_name).lower()
        stem = re.sub(r"[^a-z0-9]+", " ", stem).strip()
        if len(stem.replace(" ", "")) < MIN_STEM_LENGTH:
            continue
        tokens = [token for token in stem.split() if len(token) >= 4]
        matched = re.search(rf"\b{re.escape(stem)}\b", text) is not None
        if not matched and tokens:
            present = [token for token in tokens if re.search(rf"\b{re.escape(token)}\b", text)]
            matched = bool(present) and present[0] == tokens[0] and len(present) >= max(
                1, (len(tokens) + 1) // 2
            )
        if matched and asset.file_name not in found:
            found.append(asset.file_name)
            if len(found) >= limit:
                break
    return found


def deterministic_standalone(
    question: str,
    history: list[dict],
    assets: list[_AssetLike],
) -> str:
    """Offline rewrite: append the files the last answer discussed."""
    last_answer = next(
        (turn["content"] for turn in reversed(history) if turn.get("role") == "assistant"),
        None,
    )
    if not last_answer:
        return question
    names = referenced_asset_names(last_answer, assets)
    if not names:
        return question
    return f"{question} ({', '.join(names)})"


CONDENSE_SYSTEM_PROMPT = (
    "Rewrite the user's follow-up question as one standalone question that can be "
    "understood without the conversation. Resolve references like 'it', 'that track', "
    "or 'the slow one' to the file, project, or value they point at. Keep the user's "
    "language and intent; do not answer the question. Output only the standalone "
    "question text."
)


def condense_with_llm(question: str, history: list[dict], model: str) -> str:
    """Ask the configured OpenAI-compatible endpoint to rewrite the follow-up.

    Raises on any failure so the caller can fall back to the deterministic
    heuristic instead of blocking the answer.
    """
    from openai import OpenAI

    client = OpenAI(api_key=_api_key(), timeout=30, max_retries=0)
    turns = [
        {"role": turn["role"], "content": str(turn.get("content", ""))[:600]}
        for turn in history[-MAX_CONDENSE_TURNS:]
    ]
    completion = client.chat.completions.create(
        model=model,
        temperature=0.0,
        messages=[
            {"role": "system", "content": CONDENSE_SYSTEM_PROMPT},
            *turns,
            {"role": "user", "content": question},
        ],
    )
    rewritten = (completion.choices[0].message.content or "").strip().strip('"').strip()
    if not rewritten or len(rewritten) > MAX_STANDALONE_CHARS:
        raise ValueError("Condensed question was empty or implausibly long.")
    return rewritten


def _api_key() -> str:
    import os

    return os.getenv("OPENAI_API_KEY") or "local"


def resolve_standalone(
    question: str,
    history: list[dict],
    assets: list[_AssetLike],
    llm_available: bool,
    model: str = "gpt-4.1-mini",
) -> tuple[str, str | None]:
    """Return ``(standalone_question, method)`` for retrieval.

    ``method`` is ``"llm"``, ``"heuristic"``, or ``None`` when the question
    passed through unchanged; it feeds the quality report so the UI can show
    exactly how a follow-up was interpreted.
    """
    if not looks_like_followup(question, bool(history)):
        return question, None
    if llm_available:
        try:
            return condense_with_llm(question, history, model), "llm"
        except Exception:
            logger.warning("LLM condensation failed; using offline heuristic.", exc_info=True)
    return deterministic_standalone(question, history, assets), "heuristic"
