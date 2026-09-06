from __future__ import annotations

import re

from sessioniq.models import AssistantAnswer, Decision, RetrievedSource

NUMBER = r"(-?\d+(?:\.\d+)?)"
CLAIMS = {
    "bpm": rf"\b(?:bpm(?:_estimate)?|tempo_bpm)\s*[=:]\s*{NUMBER}|{NUMBER}\s*BPM\b",
    "peak_db": rf"\bpeak_db\s*[=:]\s*{NUMBER}",
    "rms_db": rf"\brms_db\s*[=:]\s*{NUMBER}",
    "duration_seconds": rf"\bduration(?:_seconds)?\s*[=:]\s*{NUMBER}",
    "note_count": rf"\bnote_count\s*[=:]\s*{NUMBER}",
}


def _harvest_claim_values(text: str) -> dict[str, list[float]]:
    """Numeric claims that appear verbatim in a piece of trusted source text.

    Decisions and note text are extracted content the same way metadata is:
    a number the producer wrote down ("locked 96 BPM") is grounded even when
    the cited file's analyzer fields disagree or are absent.
    """
    harvested: dict[str, list[float]] = {}
    for field, pattern in CLAIMS.items():
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw = next(group for group in match.groups() if group is not None)
            harvested.setdefault(field, []).append(float(raw))
    return harvested


def _numeric_errors(
    text: str,
    sources: list[RetrievedSource],
    decisions: list[Decision] | None = None,
) -> list[str]:
    errors = []

    # Allowed values per field: analyzer metadata plus numbers written in the
    # sources' own extracted text and in recorded decisions.
    allowed: dict[str, list[float]] = {}
    for source in sources:
        metadata = source.asset.audio or source.asset.midi
        if metadata:
            for field in CLAIMS:
                key = (
                    ("bpm_estimate" if source.asset.audio else "tempo_bpm")
                    if field == "bpm"
                    else field
                )
                value = getattr(metadata, key, None)
                if value is not None:
                    allowed.setdefault(field, []).append(value)
        for field, harvested in _harvest_claim_values(source.asset.cached_search_text()).items():
            allowed.setdefault(field, []).extend(harvested)
    for decision in decisions or []:
        for field, harvested in _harvest_claim_values(decision.text).items():
            allowed.setdefault(field, []).extend(harvested)

    for field, pattern in CLAIMS.items():
        values = allowed.get(field, [])
        for match in re.finditer(pattern, text, re.IGNORECASE):
            raw = next(value for value in match.groups() if value is not None)
            decimals = len(raw.split(".")[1]) if "." in raw else 0
            if not any(abs(round(value, decimals) - float(raw)) < 1e-8 for value in values):
                errors.append(f"Unsupported numeric claim: {field}={raw}.")
    return errors


def validate_grounded_answer(
    answer: AssistantAnswer,
    sources: list[RetrievedSource],
    decisions: list[Decision] | None = None,
) -> list[str]:
    errors: list[str] = []
    source_names = {source.asset.file_name for source in sources}

    if sources and not answer.citations:
        errors.append("Answer must include at least one citation when sources are available.")

    for citation in answer.citations:
        if citation.file_name not in source_names:
            errors.append(f"Citation '{citation.file_name}' was not present in retrieved sources.")
        if not citation.evidence.strip():
            errors.append(f"Citation '{citation.file_name}' is missing evidence text.")
        matched = [source for source in sources if source.asset.file_name == citation.file_name]
        if citation.asset_id:
            matched = [source for source in matched if source.asset.id == citation.asset_id]
        if len(matched) != 1:
            errors.append(f"Citation '{citation.file_name}' must identify one retrieved asset.")
        else:
            # Evidence strings name metadata fields, so they stay strictly
            # metadata-checked; recorded decisions only cover the answer body.
            errors.extend(_numeric_errors(citation.evidence, matched))

    cited = [
        source
        for source in sources
        if any(
            citation.file_name == source.asset.file_name
            and (not citation.asset_id or citation.asset_id == source.asset.id)
            for citation in answer.citations
        )
    ]
    errors.extend(_numeric_errors(answer.answer, cited, decisions))

    no_source_unknown = (
        not sources
        and "do not know" not in answer.answer.lower()
        and "don't know" not in answer.answer.lower()
    )
    if no_source_unknown:
        errors.append("Answer should say it does not know when no source data is available.")

    return errors
