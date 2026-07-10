from __future__ import annotations

import json
import logging
import os
import re

from sessioniq.models import AssistantAnswer, Citation, ProjectAsset, RetrievedSource
from sessioniq.validation import validate_grounded_answer

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """You are SessionIQ, a source-grounded assistant for music production sessions.
Answer only from the provided project sources; never invent files, values, or advice
that the sources cannot support.
Numbers (BPM, dB, durations, note counts) must be quoted exactly as they appear in the
source metadata.
If the sources do not support an answer, say you do not know.
Every answer must cite the file names used as evidence, with a short evidence string
naming the metadata field or note text the claim came from.
Keep answers concise and practical for a producer reviewing their session."""

# Bump when SYSTEM_PROMPT or the grounding contract changes, so the UI can show
# exactly which prompt produced each answer (LLMOps prompt versioning).
PROMPT_VERSION = "v1.2.0"
DEFAULT_TEMPERATURE = 0.2
KNOWLEDGE_SOURCE = "Project files"

# Sources sent to the LLM are capped so prompts stay inside the small context
# windows local models default to (Ollama commonly runs with 2k-8k tokens).
LLM_MAX_SOURCES = 12
LLM_MAX_SOURCE_CHARS = 1200


def llm_status() -> dict[str, str]:
    """Which answer engine will handle the next question, for status displays."""
    base_url = os.getenv("OPENAI_BASE_URL", "")
    if base_url:
        return {
            "mode": "local-llm",
            "model": os.getenv("SESSIONIQ_MODEL", "gpt-4.1-mini"),
            "endpoint": base_url,
        }
    if os.getenv("OPENAI_API_KEY"):
        return {
            "mode": "openai",
            "model": os.getenv("SESSIONIQ_MODEL", "gpt-4.1-mini"),
            "endpoint": "api.openai.com",
        }
    return {"mode": "rules", "model": "deterministic metadata engine", "endpoint": "offline"}


class GroundedAssistant:
    def __init__(self, model: str | None = None) -> None:
        self.model = model or os.getenv("SESSIONIQ_MODEL", "gpt-4.1-mini")
        # Populated on every answer() call so callers (the API) can build an
        # LLMOps-style quality report: which engine, prompt, and tokens ran.
        self.last_meta: dict[str, object] = self._base_meta("rules")

    def _base_meta(self, engine: str) -> dict[str, object]:
        status = llm_status()
        return {
            "engine": engine,
            "mode": status["mode"],
            "model": status["model"] if engine != "rules" else "deterministic metadata engine",
            "prompt_version": PROMPT_VERSION,
            "temperature": DEFAULT_TEMPERATURE if engine == "llm" else None,
            "knowledge_source": KNOWLEDGE_SOURCE,
            "token_usage": None,
        }

    def answer(self, question: str, sources: list[RetrievedSource]) -> AssistantAnswer:
        if not sources:
            self.last_meta = self._base_meta("rules")
            return AssistantAnswer(
                answer="I do not know yet because no relevant project source data was found.",
                citations=[],
                confidence="low",
            )

        if os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_BASE_URL"):
            try:
                answer = self._llm_answer(question, sources)
                return answer
            except Exception:
                logger.warning(
                    "LLM answer failed; falling back to the deterministic engine.",
                    exc_info=True,
                )

        self.last_meta = self._base_meta("rules")
        return self._deterministic_answer(question, sources)

    def _llm_answer(self, question: str, sources: list[RetrievedSource]) -> AssistantAnswer:
        """Ask an OpenAI-compatible endpoint: OpenAI cloud, or a local server such
        as Ollama when OPENAI_BASE_URL points at it (e.g. http://localhost:11434/v1)."""
        from openai import OpenAI

        self.last_meta = self._base_meta("llm")
        client = OpenAI(api_key=os.getenv("OPENAI_API_KEY") or "local")
        context = [
            {
                "file_name": source.asset.file_name,
                "summary": source.asset.search_text()[:LLM_MAX_SOURCE_CHARS],
            }
            for source in sources[:LLM_MAX_SOURCES]
        ]
        completion = client.chat.completions.parse(
            model=self.model,
            temperature=DEFAULT_TEMPERATURE,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {
                    "role": "user",
                    "content": json.dumps(
                        {"question": question, "sources": context},
                        indent=2,
                    ),
                },
            ],
            response_format=AssistantAnswer,
        )
        usage = getattr(completion, "usage", None)
        if usage is not None:
            self.last_meta["token_usage"] = {
                "prompt": getattr(usage, "prompt_tokens", None),
                "completion": getattr(usage, "completion_tokens", None),
                "total": getattr(usage, "total_tokens", None),
            }
        answer = completion.choices[0].message.parsed
        if answer is None:
            raise ValueError("LLM returned no parsed answer.")
        errors = validate_grounded_answer(answer, sources)
        if errors:
            return AssistantAnswer(
                answer="I do not know. The generated answer failed source-grounding checks.",
                citations=[],
                confidence="low",
            )
        return answer

    def _deterministic_answer(
        self,
        question: str,
        sources: list[RetrievedSource],
    ) -> AssistantAnswer:
        assets = [source.asset for source in sources]
        lowered = question.lower()

        handlers = (
            self._superlative_answer,
            self._task_answer,
            self._status_answer,
            self._count_answer,
            self._key_answer,
            self._summary_answer,
            self._tempo_answer,
            self._loudness_answer,
            self._duration_answer,
            self._midi_answer,
            self._note_answer,
        )
        for handler in handlers:
            result = handler(lowered, assets)
            if result is not None:
                return result

        return self._fallback_answer(lowered, assets)

    # --- Intent handlers -------------------------------------------------

    def _superlative_answer(
        self, lowered: str, assets: list[ProjectAsset]
    ) -> AssistantAnswer | None:
        checks = (
            (("fastest", "highest bpm", "quickest"), _bpm, max, "the fastest", "BPM"),
            (("slowest", "lowest bpm"), _bpm, min, "the slowest", "BPM"),
            (("loudest", "hottest"), _rms_db, max, "the loudest", "dB RMS"),
            (("quietest", "softest"), _rms_db, min, "the quietest", "dB RMS"),
            (("longest",), _duration, max, "the longest", "seconds"),
            (("shortest",), _duration, min, "the shortest", "seconds"),
        )
        for keywords, accessor, pick, label, unit in checks:
            if not any(keyword in lowered for keyword in keywords):
                continue
            values = [(asset, accessor(asset)) for asset in assets]
            values = [(asset, value) for asset, value in values if value is not None]
            if not values:
                return None
            winner, value = pick(values, key=lambda pair: pair[1])
            others = ", ".join(
                f"{asset.file_name} ({other_value:.1f})"
                for asset, other_value in sorted(values, key=lambda p: p[1], reverse=True)
                if asset.id != winner.id
            )
            answer = f"{winner.file_name} is {label} at {value:.1f} {unit}."
            if others:
                answer += f" Others: {others}."
            citations = [
                Citation(file_name=asset.file_name, evidence=f"{unit}={other_value:.1f}")
                for asset, other_value in values
            ]
            return AssistantAnswer(answer=answer, citations=citations, confidence="high")
        return None

    def _task_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        triggers = ("task", "todo", "to do", "action item", "work on", "unfinished", "next step")
        if not any(trigger in lowered for trigger in triggers):
            return None
        lines: list[str] = []
        citations: list[Citation] = []
        for asset in assets:
            items = list(asset.text.action_items) if asset.text else []
            if not items and asset.note:
                items = [asset.note] if _looks_actionable(asset.note) else []
            if items:
                for item in items:
                    lines.append(f"- {item} (from {asset.file_name})")
                citations.append(
                    Citation(file_name=asset.file_name, evidence="; ".join(items)[:180])
                )
        if not lines:
            return None
        header = f"Open items across {len(citations)} file(s):"
        return AssistantAnswer(
            answer="\n".join([header, *lines]),
            citations=citations,
            confidence="high",
        )

    def _status_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        words = _words(lowered)
        wanted = [
            status
            for status in ("ready", "needs work", "in progress", "idea", "reference", "archived")
            if (status in lowered if " " in status else status in words)
        ]
        if not wanted and "status" not in words:
            return None
        lines: list[str] = []
        citations: list[Citation] = []
        for asset in assets:
            status = asset.status.value.lower()
            if wanted and status not in wanted:
                continue
            lines.append(f"- {asset.file_name}: {asset.status.value}")
            citations.append(
                Citation(file_name=asset.file_name, evidence=f"status={asset.status.value}")
            )
        if not lines:
            described = " or ".join(wanted) if wanted else "that status"
            return AssistantAnswer(
                answer=f"No files are currently marked {described}.",
                citations=[
                    Citation(
                        file_name=asset.file_name, evidence=f"status={asset.status.value}"
                    )
                    for asset in assets[:4]
                ],
                confidence="medium",
            )
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="high")

    def _count_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        words = _words(lowered)
        phrase_hit = any(t in lowered for t in ("how many", "what files", "which files"))
        if not phrase_hit and not words & {"count", "list", "inventory"}:
            return None
        by_kind: dict[str, list[ProjectAsset]] = {}
        for asset in assets:
            by_kind.setdefault(asset.kind.value, []).append(asset)
        parts = [f"{len(group)} {kind}" for kind, group in sorted(by_kind.items())]
        lines = [f"{len(assets)} file(s) in scope ({', '.join(parts)}):"]
        citations: list[Citation] = []
        for asset in assets:
            details = _asset_brief(asset)
            lines.append(f"- {asset.file_name} ({details})")
            citations.append(Citation(file_name=asset.file_name, evidence=details))
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="high")

    def _key_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        if "key" not in _words(lowered):
            return None
        keyed = [(asset, _key(asset)) for asset in assets]
        keyed = [(asset, key) for asset, key in keyed if key]
        if not keyed:
            return None
        lines = [f"- {asset.file_name}: {key}" for asset, key in keyed]
        groups: dict[str, list[str]] = {}
        for asset, key in keyed:
            groups.setdefault(key, []).append(asset.file_name)
        shared = [
            f"{key}: {', '.join(names)}" for key, names in groups.items() if len(names) > 1
        ]
        if shared:
            lines.append("Files sharing a key - " + "; ".join(shared))
        citations = [
            Citation(file_name=asset.file_name, evidence=f"key_estimate={key}")
            for asset, key in keyed
        ]
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="high")

    def _summary_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        if not any(t in lowered for t in ("summar", "overview", "describe", "about the project")):
            return None
        by_kind: dict[str, int] = {}
        for asset in assets:
            by_kind[asset.kind.value] = by_kind.get(asset.kind.value, 0) + 1
        bpms = [value for value in (_bpm(asset) for asset in assets) if value]
        keys = sorted({key for key in (_key(asset) for asset in assets) if key})
        open_items = sum(len(asset.text.action_items) for asset in assets if asset.text)
        parts = [f"{count} {kind}" for kind, count in sorted(by_kind.items())]
        lines = [f"Scope: {len(assets)} file(s) ({', '.join(parts)})."]
        if bpms:
            lines.append(f"Tempo range: {min(bpms):.0f}-{max(bpms):.0f} BPM.")
        if keys:
            lines.append(f"Detected keys: {', '.join(keys)}.")
        if open_items:
            lines.append(f"Open action items in notes: {open_items}.")
        citations = [
            Citation(file_name=asset.file_name, evidence=_asset_brief(asset))
            for asset in assets[:8]
        ]
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="medium")

    def _tempo_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        if "bpm" not in lowered and "tempo" not in lowered:
            return None
        lines: list[str] = []
        citations: list[Citation] = []
        for asset in assets:
            bpm = _bpm(asset)
            if bpm is None and not asset.audio and not asset.midi:
                continue
            bpm_text = f"{bpm:.1f} BPM" if bpm else "no BPM estimate available"
            lines.append(f"{asset.file_name} has an estimated tempo of {bpm_text}.")
            citations.append(Citation(file_name=asset.file_name, evidence=f"bpm_estimate={bpm}"))
        if not lines:
            return None
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="high")

    def _loudness_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        if not any(t in lowered for t in ("loud", "level", "rms", "peak", "volume", "db")):
            return None
        lines: list[str] = []
        citations: list[Citation] = []
        for asset in assets:
            if not asset.audio or asset.audio.peak_amplitude is None:
                continue
            peak_db = f"{asset.audio.peak_db:.1f} dB" if asset.audio.peak_db else "n/a"
            rms_db = f"{asset.audio.rms_db:.1f} dB" if asset.audio.rms_db else "n/a"
            lines.append(f"{asset.file_name} peaks at {peak_db} with RMS {rms_db}.")
            citations.append(
                Citation(
                    file_name=asset.file_name,
                    evidence=f"peak_db={asset.audio.peak_db}, rms_db={asset.audio.rms_db}",
                )
            )
        if not lines:
            return None
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="high")

    def _duration_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        if not any(t in lowered for t in ("duration", "how long", "length")):
            return None
        lines: list[str] = []
        citations: list[Citation] = []
        for asset in assets:
            duration = _duration(asset)
            if duration is None:
                continue
            minutes, seconds = divmod(int(round(duration)), 60)
            lines.append(f"{asset.file_name} runs {minutes}:{seconds:02d} ({duration:.1f}s).")
            citations.append(
                Citation(file_name=asset.file_name, evidence=f"duration_seconds={duration:.1f}")
            )
        if not lines:
            return None
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="high")

    def _midi_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        if not any(t in lowered for t in ("midi", "note", "chord", "velocity", "instrument")):
            return None
        lines: list[str] = []
        citations: list[Citation] = []
        for asset in assets:
            if not asset.midi:
                continue
            summary = asset.midi.musical_summary or (
                f"{asset.midi.note_count} MIDI notes"
            )
            lines.append(f"{asset.file_name}: {summary}")
            citations.append(
                Citation(
                    file_name=asset.file_name,
                    evidence=f"note_count={asset.midi.note_count}",
                )
            )
        if not lines:
            return None
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="high")

    def _note_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer | None:
        lines: list[str] = []
        citations: list[Citation] = []
        query_words = {word for word in re.findall(r"[a-z0-9']+", lowered) if len(word) > 3}
        for asset in assets:
            text = asset.text.text if asset.text else asset.note
            if not text:
                continue
            matched = [
                line.strip()
                for line in text.splitlines()
                if line.strip() and query_words & set(re.findall(r"[a-z0-9']+", line.lower()))
            ]
            snippet = " / ".join(matched[:3]) if matched else text.strip().replace("\n", " ")[:180]
            lines.append(f"{asset.file_name}: {snippet}")
            citations.append(Citation(file_name=asset.file_name, evidence=snippet[:180]))
        if not lines:
            return None
        return AssistantAnswer(answer="\n".join(lines), citations=citations, confidence="medium")

    def _fallback_answer(self, lowered: str, assets: list[ProjectAsset]) -> AssistantAnswer:
        lines: list[str] = []
        citations: list[Citation] = []
        for asset in assets[:4]:
            details = _asset_brief(asset)
            lines.append(f"- {asset.file_name}: {details}")
            citations.append(Citation(file_name=asset.file_name, evidence=details))
        header = (
            "Here is what the closest matching project sources contain; "
            "ask about tempo, key, loudness, duration, tasks, or notes for more detail:"
        )
        return AssistantAnswer(
            answer="\n".join([header, *lines]),
            citations=citations,
            confidence="low",
        )


# --- Metadata accessors -------------------------------------------------


def _words(lowered: str) -> set[str]:
    return set(re.findall(r"[a-z0-9']+", lowered))


def _bpm(asset: ProjectAsset) -> float | None:
    if asset.audio and asset.audio.bpm_estimate:
        return asset.audio.bpm_estimate
    if asset.midi and asset.midi.tempo_bpm:
        return asset.midi.tempo_bpm
    return None


def _key(asset: ProjectAsset) -> str | None:
    if asset.audio and asset.audio.key_estimate:
        return asset.audio.key_estimate
    if asset.midi and asset.midi.key_estimate:
        return asset.midi.key_estimate
    return None


def _duration(asset: ProjectAsset) -> float | None:
    if asset.audio:
        return asset.audio.duration_seconds
    if asset.midi:
        return asset.midi.duration_seconds
    return None


def _rms_db(asset: ProjectAsset) -> float | None:
    if asset.audio and asset.audio.rms_db is not None:
        return asset.audio.rms_db
    return None


def _asset_brief(asset: ProjectAsset) -> str:
    parts = [asset.kind.value, f"status={asset.status.value}"]
    bpm = _bpm(asset)
    if bpm:
        parts.append(f"bpm={bpm:.1f}")
    key = _key(asset)
    if key:
        parts.append(f"key={key}")
    duration = _duration(asset)
    if duration:
        parts.append(f"duration={duration:.1f}s")
    if asset.text and asset.text.action_items:
        parts.append(f"open_items={len(asset.text.action_items)}")
    return ", ".join(parts)


def _looks_actionable(text: str) -> bool:
    lowered = text.lower()
    return any(word in lowered for word in ("todo", "need", "fix", "try", "finish", "tighten"))
