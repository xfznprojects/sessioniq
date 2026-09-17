"""Labeled questions over the generated demo library.

Ground truth is keyed on ``<project>/<file name>`` because the demo corpus
contains several files that share a name (four ``cover.png`` artwork files).

Every expected value here was read off a real ingestion run of
``scripts/seed_demo.py`` — the detected tempo, key, loudness and centroid in the
labels are what the analyzers actually produce, not the values the synthesizer
was asked for. Those two differ: ``cue_draft.wav`` is synthesized on D and
detected in A, for example. Labels follow the analyzers, because the analyzers
are what retrieval indexes.

Re-generate the corpus after changing ``seed_demo.py`` and re-check the labels;
``tests/test_evals.py`` asserts that every label still names a real file.
"""

from __future__ import annotations

from dataclasses import dataclass

# Every asset scripts/seed_demo.py produces, project-qualified.
DEMO_CORPUS: tuple[str, ...] = (
    "Neon Horizon/Intro/intro.wav",
    "Neon Horizon/Intro/cover.png",
    "Neon Horizon/Midnight Drive/midnight_drive.wav",
    "Neon Horizon/Midnight Drive/mix_notes.txt",
    "Neon Horizon/Midnight Drive/cover.png",
    "Neon Horizon/Afterglow/afterglow.wav",
    "Neon Horizon/Afterglow/afterglow_master.wav",
    "Neon Horizon/Afterglow/afterglow_reference.wav",
    "Neon Horizon/Afterglow/notes.txt",
    "Neon Horizon/Afterglow/cover.png",
    "Lo-Fi Study/lofi_sketch.wav",
    "Lo-Fi Study/chords.mid",
    "Lo-Fi Study/ideas.txt",
    "Lo-Fi Study/cover.png",
    "Client Cue 03/cue_draft.wav",
    "Client Cue 03/reference.wav",
    "Client Cue 03/brief.txt",
)

# Detected values, for readers of this file.
#   intro.wav                89.1 bpm  key G  centroid  837.8  -18.8 LUFS
#   midnight_drive.wav      117.5 bpm  key E  centroid 1218.1  -18.3 LUFS
#   afterglow.wav           117.5 bpm  key E  centroid 1202.1  -18.4 LUFS
#   afterglow_master.wav    117.5 bpm  key E  centroid 1208.0  -18.4 LUFS
#   afterglow_reference.wav 117.5 bpm  key E  centroid 1190.4  -25.0 LUFS  (quiet bounce)
#   lofi_sketch.wav          76.0 bpm  key C  centroid  813.6  -18.9 LUFS
#   cue_draft.wav            99.4 bpm  key A  centroid  871.0  -19.9 LUFS
#   reference.wav            99.4 bpm  key A  centroid  858.2  -15.5 LUFS  (loudest)

FASTEST_TRACKS = (
    "Neon Horizon/Midnight Drive/midnight_drive.wav",
    "Neon Horizon/Afterglow/afterglow.wav",
    "Neon Horizon/Afterglow/afterglow_master.wav",
    "Neon Horizon/Afterglow/afterglow_reference.wav",
)

KEY_OF_E = FASTEST_TRACKS

ARTWORK = (
    "Neon Horizon/Intro/cover.png",
    "Neon Horizon/Midnight Drive/cover.png",
    "Neon Horizon/Afterglow/cover.png",
    "Lo-Fi Study/cover.png",
)

# Notes whose text literally contains a TODO marker.
TODO_NOTES = (
    "Neon Horizon/Midnight Drive/mix_notes.txt",
    "Lo-Fi Study/ideas.txt",
    "Client Cue 03/brief.txt",
)


@dataclass(frozen=True)
class GoldenCase:
    question: str
    expected: tuple[str, ...]
    category: str
    project: str | None = None


GOLDEN_SET: tuple[GoldenCase, ...] = (
    # --- acoustic superlatives ------------------------------------------------
    GoldenCase("which track is the loudest?", ("Client Cue 03/reference.wav",), "superlative"),
    GoldenCase(
        "which track is the quietest?",
        ("Neon Horizon/Afterglow/afterglow_reference.wav",),
        "superlative",
    ),
    GoldenCase("which track is the slowest?", ("Lo-Fi Study/lofi_sketch.wav",), "superlative"),
    GoldenCase("which tracks are the fastest?", FASTEST_TRACKS, "superlative"),
    GoldenCase(
        "which track is the brightest?",
        ("Neon Horizon/Midnight Drive/midnight_drive.wav",),
        "superlative",
    ),
    GoldenCase("which track is the darkest?", ("Lo-Fi Study/lofi_sketch.wav",), "superlative"),
    # Same intent, natural wording that has to reach the metadata vocabulary
    # through the synonym map rather than by literal token overlap.
    GoldenCase("which song is the loudest?", ("Client Cue 03/reference.wav",), "synonym"),
    GoldenCase("show me the fastest tune", FASTEST_TRACKS, "synonym"),
    GoldenCase("which track has the highest volume?", ("Client Cue 03/reference.wav",), "synonym"),
    # --- key ------------------------------------------------------------------
    GoldenCase("which track is in the key of G?", ("Neon Horizon/Intro/intro.wav",), "key"),
    GoldenCase(
        "which tracks are in the key of C?",
        ("Lo-Fi Study/lofi_sketch.wav", "Lo-Fi Study/chords.mid"),
        "key",
    ),
    GoldenCase("which audio files are in the key of E?", KEY_OF_E, "key"),
    # --- note content ---------------------------------------------------------
    GoldenCase("which notes mention a dusty piano loop?", ("Lo-Fi Study/ideas.txt",), "content"),
    GoldenCase("which notes still have todo items?", TODO_NOTES, "content"),
    GoldenCase(
        "which notes mention sidechaining the pads?",
        ("Neon Horizon/Midnight Drive/mix_notes.txt",),
        "content",
    ),
    GoldenCase("what did the client ask for?", ("Client Cue 03/brief.txt",), "content"),
    GoldenCase("which notes mention tape saturation?", ("Lo-Fi Study/ideas.txt",), "content"),
    GoldenCase(
        "where is the note about checking the low end on headphones?",
        ("Neon Horizon/Afterglow/notes.txt",),
        "content",
    ),
    # --- status ---------------------------------------------------------------
    GoldenCase("what still needs work?", ("Client Cue 03/cue_draft.wav",), "status"),
    GoldenCase(
        "which files are ready?",
        ("Neon Horizon/Afterglow/afterglow_master.wav",),
        "status",
    ),
    GoldenCase(
        "what is in progress?",
        ("Neon Horizon/Midnight Drive/midnight_drive.wav",),
        "status",
    ),
    # --- tags -----------------------------------------------------------------
    GoldenCase(
        "which track is tagged synthwave?",
        ("Neon Horizon/Midnight Drive/midnight_drive.wav",),
        "tag",
    ),
    GoldenCase("which track is my favorite?", ("Neon Horizon/Afterglow/afterglow.wav",), "tag"),
    GoldenCase("which track is chill?", ("Lo-Fi Study/lofi_sketch.wav",), "tag"),
    GoldenCase(
        "which track is marked as a single?",
        ("Neon Horizon/Midnight Drive/midnight_drive.wav",),
        "tag",
    ),
    # --- format ---------------------------------------------------------------
    GoldenCase("which project has a midi file?", ("Lo-Fi Study/chords.mid",), "format"),
    GoldenCase("where is the artwork?", ARTWORK, "format"),
    # --- project-scoped -------------------------------------------------------
    GoldenCase(
        "what files are in this project?",
        (
            "Lo-Fi Study/lofi_sketch.wav",
            "Lo-Fi Study/chords.mid",
            "Lo-Fi Study/ideas.txt",
            "Lo-Fi Study/cover.png",
        ),
        "project",
        project="Lo-Fi Study",
    ),
    GoldenCase(
        "which file is the reference?",
        ("Client Cue 03/reference.wav",),
        "project",
        project="Client Cue 03",
    ),
    # --- aggregate ------------------------------------------------------------
    GoldenCase(
        "list all the audio tracks",
        (
            "Neon Horizon/Intro/intro.wav",
            "Neon Horizon/Midnight Drive/midnight_drive.wav",
            "Neon Horizon/Afterglow/afterglow.wav",
            "Neon Horizon/Afterglow/afterglow_master.wav",
            "Neon Horizon/Afterglow/afterglow_reference.wav",
            "Lo-Fi Study/lofi_sketch.wav",
            "Client Cue 03/cue_draft.wav",
            "Client Cue 03/reference.wav",
        ),
        "aggregate",
    ),
)

CATEGORIES: tuple[str, ...] = tuple(sorted({case.category for case in GOLDEN_SET}))
