"""Optional voice-memo transcription via local Whisper.

Enabled by installing the ``voice`` extra (``pip install -e ".[voice]"``).
Everything runs locally: the model downloads to the user cache on first use
and is never committed. Missing dependencies degrade to a clear status hint
instead of an error, mirroring the vector-search extra.
"""

from __future__ import annotations

import logging
import os
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_WHISPER_MODEL = "base.en"


def transcription_status() -> dict:
    """Whether local transcription is usable, plus a setup hint when it is not."""
    available = _faster_whisper() is not None
    status = {
        "available": available,
        "model": os.getenv("SESSIONIQ_WHISPER_MODEL", DEFAULT_WHISPER_MODEL),
    }
    if not available:
        status["hint"] = (
            "Voice memo transcription is off. Install the voice extra "
            '(pip install -e ".[voice]") to transcribe recordings into notes '
            "with a local Whisper model."
        )
    return status


def transcribe_audio(path: str | Path) -> str:
    """Transcribe an audio file to plain text; raises when the extra is missing."""
    whisper = _faster_whisper()
    if whisper is None:
        raise RuntimeError(
            "Transcription requires the optional voice extra: pip install -e \".[voice]\""
        )
    model_name = os.getenv("SESSIONIQ_WHISPER_MODEL", DEFAULT_WHISPER_MODEL)
    model = whisper.WhisperModel(model_name, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(path), vad_filter=True)
    text = "\n".join(segment.text.strip() for segment in segments if segment.text.strip())
    logger.info("Transcribed %s with %s", Path(path).name, model_name)
    return text.strip()


def _faster_whisper():
    try:
        import faster_whisper

        return faster_whisper
    except Exception:  # Not installed, or a broken install.
        return None
