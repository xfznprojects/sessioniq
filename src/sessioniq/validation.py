from __future__ import annotations

from sessioniq.models import AssistantAnswer, RetrievedSource


def validate_grounded_answer(answer: AssistantAnswer, sources: list[RetrievedSource]) -> list[str]:
    errors: list[str] = []
    source_names = {source.asset.file_name for source in sources}

    if sources and not answer.citations:
        errors.append("Answer must include at least one citation when sources are available.")

    for citation in answer.citations:
        if citation.file_name not in source_names:
            errors.append(f"Citation '{citation.file_name}' was not present in retrieved sources.")
        if not citation.evidence.strip():
            errors.append(f"Citation '{citation.file_name}' is missing evidence text.")

    no_source_unknown = (
        not sources
        and "do not know" not in answer.answer.lower()
        and "don't know" not in answer.answer.lower()
    )
    if no_source_unknown:
        errors.append("Answer should say it does not know when no source data is available.")

    return errors
