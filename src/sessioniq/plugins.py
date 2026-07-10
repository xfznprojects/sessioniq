"""Declarative registry of SessionIQ's analysis + AI capabilities.

This is the single source of truth for the "Plugins" view: which analyzers run
today, and which integrations are planned. Keeping it declarative makes the
platform look (and stay) extensible.
"""

from __future__ import annotations

ANALYSIS_PLUGINS: list[dict] = [
    {
        "name": "BPM Detector",
        "category": "Audio",
        "engine": "librosa",
        "status": "active",
        "formats": ["wav", "mp3", "flac", "aiff", "ogg", "m4a"],
        "detail": "Tempo estimation from onset envelope.",
    },
    {
        "name": "Key Estimator",
        "category": "Audio",
        "engine": "librosa (chroma)",
        "status": "active",
        "formats": ["wav", "mp3", "flac"],
        "detail": "Pitch-class profile → key estimate.",
    },
    {
        "name": "Loudness & Dynamics",
        "category": "Audio",
        "engine": "numpy",
        "status": "active",
        "formats": ["wav", "mp3", "flac"],
        "detail": "Peak / RMS levels in dB.",
    },
    {
        "name": "Brightness (Spectral Centroid)",
        "category": "Audio",
        "engine": "librosa",
        "status": "active",
        "formats": ["wav", "mp3", "flac"],
        "detail": "Timbral brightness over time.",
    },
    {
        "name": "Beat Tracker",
        "category": "Audio",
        "engine": "librosa",
        "status": "active",
        "formats": ["wav", "mp3"],
        "detail": "Beat positions for the waveform.",
    },
    {
        "name": "MIDI Parser",
        "category": "MIDI",
        "engine": "pretty_midi / mido",
        "status": "active",
        "formats": ["mid", "midi"],
        "detail": "Notes, pitch range, tempo, instruments.",
    },
    {
        "name": "Note & Task Extractor",
        "category": "Text",
        "engine": "SessionIQ",
        "status": "active",
        "formats": ["txt", "md"],
        "detail": "Action items, tags, and statuses from notes.",
    },
    {
        "name": "Embeddings",
        "category": "Retrieval",
        "engine": "ChromaDB (all-MiniLM-L6-v2)",
        "status": "optional",
        "formats": ["*"],
        "detail": "Local semantic vectors; degrades to lexical if absent.",
    },
    {
        "name": "Grounded Answering",
        "category": "AI",
        "engine": "Ollama / OpenAI / rules",
        "status": "active",
        "formats": ["*"],
        "detail": "Source-grounded answers with a quality report.",
    },
    {
        "name": "Validation",
        "category": "AI",
        "engine": "SessionIQ",
        "status": "active",
        "formats": ["*"],
        "detail": "Citation + grounding + hallucination checks.",
    },
]

PLANNED_INTEGRATIONS: list[dict] = [
    {"name": "Ableton Live", "category": "DAW"},
    {"name": "FL Studio", "category": "DAW"},
    {"name": "Reaper", "category": "DAW"},
    {"name": "Spotify", "category": "Reference"},
    {"name": "Chord Detector", "category": "Audio"},
    {"name": "LUFS Metering", "category": "Audio"},
]


def plugin_registry(vector_enabled: bool) -> dict:
    plugins = []
    for plugin in ANALYSIS_PLUGINS:
        resolved = dict(plugin)
        if plugin["name"] == "Embeddings":
            resolved["status"] = "active" if vector_enabled else "inactive"
        plugins.append(resolved)
    return {"plugins": plugins, "planned": PLANNED_INTEGRATIONS}
