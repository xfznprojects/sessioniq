"""Questions that must be computed rather than retrieved.

"Which track is the loudest" is not a similarity question: every audio file
matches the words *loud* and *track* about equally well, so ranking by text
overlap cannot pick a winner. These questions are answered by the tool layer
(``compute_stat``), which compares real numbers.

Each case names the tool call the assistant is expected to make and the asset
that call must return. The two tie cases accept any member of the tied set,
because which one wins depends on snapshot order rather than on the comparison.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class ToolCase:
    question: str
    tool: str
    arguments: dict
    expected_any: tuple[str, ...]
    field: str
    op: str


# Detected extremes in the demo corpus, for reference:
#   rms_db   max -14.89 (Client Cue 03/reference.wav)   min -24.57 (afterglow_reference.wav)
#   bpm      max 117.5 (four tied)                      min  76.0 (lofi_sketch.wav)
#   centroid max 1218.1 (midnight_drive.wav)            min 813.6 (lofi_sketch.wav)
#   duration max 8.0s (four tied)

TOOL_SET: tuple[ToolCase, ...] = (
    ToolCase(
        "which track is the loudest?",
        "compute_stat",
        {"field": "rms_db", "op": "max"},
        ("Client Cue 03/reference.wav",),
        "rms_db",
        "max",
    ),
    ToolCase(
        "which track is the quietest?",
        "compute_stat",
        {"field": "rms_db", "op": "min"},
        ("Neon Horizon/Afterglow/afterglow_reference.wav",),
        "rms_db",
        "min",
    ),
    ToolCase(
        "which track is the slowest?",
        "compute_stat",
        {"field": "bpm", "op": "min"},
        ("Lo-Fi Study/lofi_sketch.wav",),
        "bpm",
        "min",
    ),
    ToolCase(
        "which tracks are the fastest?",
        "compute_stat",
        {"field": "bpm", "op": "max"},
        (
            "Neon Horizon/Midnight Drive/midnight_drive.wav",
            "Neon Horizon/Afterglow/afterglow.wav",
            "Neon Horizon/Afterglow/afterglow_master.wav",
            "Neon Horizon/Afterglow/afterglow_reference.wav",
        ),
        "bpm",
        "max",
    ),
    ToolCase(
        "which track is the brightest?",
        "compute_stat",
        {"field": "brightness", "op": "max"},
        ("Neon Horizon/Midnight Drive/midnight_drive.wav",),
        "brightness",
        "max",
    ),
    ToolCase(
        "which track is the darkest?",
        "compute_stat",
        {"field": "brightness", "op": "min"},
        ("Lo-Fi Study/lofi_sketch.wav",),
        "brightness",
        "min",
    ),
    ToolCase(
        "which track is the longest?",
        "compute_stat",
        {"field": "duration", "op": "max"},
        (
            "Neon Horizon/Midnight Drive/midnight_drive.wav",
            "Neon Horizon/Afterglow/afterglow.wav",
            "Neon Horizon/Afterglow/afterglow_master.wav",
            "Neon Horizon/Afterglow/afterglow_reference.wav",
        ),
        "duration",
        "max",
    ),
)
