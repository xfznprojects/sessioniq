"""Content-based similarity between assets, from the analysis features SessionIQ
already extracts. Works without embeddings (numeric feature vectors); the vector
store, when present, sharpens retrieval separately in the retriever.
"""

from __future__ import annotations

import re
from collections import Counter

from sessioniq.models import AssetKind, ProjectAsset

# Per-dimension "just noticeable" scale: an absolute difference of this size maps
# to zero similarity. Fixed scales give stable, set-independent scores (so "92%
# similar" means the same thing whether the library holds 2 tracks or 200).
DIMENSION_SCALE: dict[str, float] = {
    "tempo": 60.0,  # BPM
    "brightness": 3000.0,  # spectral centroid Hz
    "loudness": 24.0,  # dB
    "duration": 240.0,  # seconds
}
NUMERIC_DIMENSIONS = tuple(DIMENSION_SCALE)

# Tempos at these ratios share a grid (double-time, half-time, triplets), so
# 90 vs 180 BPM is the same groove family, not zero similarity.
METRIC_RATIOS = (1 / 3, 0.5, 2.0, 3.0)
# Deviation tolerated around an exact multiple: a tight window, because being
# "near double-time" is a much weaker claim than being near the same tempo.
MULTIPLE_WINDOW_BPM = 12.0


def tempo_similarity(bpm_a: float, bpm_b: float) -> float:
    """Similarity by tempo, folding metrical multiples onto one grid.

    Direct comparison uses the full 60 BPM scale; near-exact multiples
    (double-time, half-time, triplets) score high so a 90 BPM groove can
    match its 180 BPM bounce.
    """
    best = max(0.0, 1.0 - abs(bpm_a - bpm_b) / DIMENSION_SCALE["tempo"])
    for ratio in METRIC_RATIOS:
        scaled = bpm_b * ratio
        candidate = max(0.0, 1.0 - abs(bpm_a - scaled) / MULTIPLE_WINDOW_BPM)
        best = max(best, candidate)
    return best

PITCH_CLASSES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")
_FLAT_TO_SHARP = {"DB": "C#", "EB": "D#", "GB": "F#", "AB": "G#", "BB": "A#"}
# Compatibility by distance on the circle of fifths (Camelot-style): neighbors
# (perfect fourth/fifth) and the relative major/minor mix well; distant keys
# do not. Same-letter entries here mean "identical position on the wheel".
_SAME_MODE_COMPAT = {0: 1.0, 1: 0.85, 2: 0.6}
_CROSS_MODE_COMPAT = {0: 0.95, 1: 0.75}


def _parse_key(key: str | None) -> int | None:
    """Pitch class (0-11) from analyzer output like 'C', 'F#', or 'Bb'."""
    if not key:
        return None
    tokens = re.findall(r"[A-G][#b]?", key.strip().upper())
    if not tokens:
        return None
    name = _FLAT_TO_SHARP.get(tokens[0], tokens[0])
    return PITCH_CLASSES.index(name) if name in PITCH_CLASSES else None


def _circle_distance(a: int, b: int) -> int:
    return min(abs(a - b), 12 - abs(a - b))


def key_compatibility(
    key_a: str | None,
    mode_a: str | None,
    key_b: str | None,
    mode_b: str | None,
) -> float | None:
    """Harmonic compatibility in [0, 1]: 1.0 is the same key, ~0.85 a fourth/fifth
    or same wheel position, 0.95 the relative major/minor. None when a key is
    missing. Without mode estimates both keys are compared as majors, so older
    libraries still get graded compatibility instead of a same/different bit.
    """
    pitch_a, pitch_b = _parse_key(key_a), _parse_key(key_b)
    if pitch_a is None or pitch_b is None:
        return None

    def fifths(pitch: int, mode: str | None) -> int:
        # Minor keys map to their relative major's slot on the wheel.
        root = pitch + 3 if mode == "minor" else pitch
        return (root * 7) % 12

    distance = _circle_distance(fifths(pitch_a, mode_a), fifths(pitch_b, mode_b))
    if mode_a and mode_b and mode_a != mode_b:
        return _CROSS_MODE_COMPAT.get(distance, 0.0)
    return _SAME_MODE_COMPAT.get(distance, 0.0)


def _numeric_features(asset: ProjectAsset) -> dict[str, float]:
    features: dict[str, float] = {}
    if asset.audio:
        if asset.audio.bpm_estimate:
            features["tempo"] = float(asset.audio.bpm_estimate)
        if asset.audio.spectral_centroid_mean:
            features["brightness"] = float(asset.audio.spectral_centroid_mean)
        if asset.audio.rms_db is not None:
            features["loudness"] = float(asset.audio.rms_db)
        if asset.audio.duration_seconds:
            features["duration"] = float(asset.audio.duration_seconds)
    elif asset.midi:
        if asset.midi.tempo_bpm:
            features["tempo"] = float(asset.midi.tempo_bpm)
        if asset.midi.duration_seconds:
            features["duration"] = float(asset.midi.duration_seconds)
    return features


def _asset_key(asset: ProjectAsset) -> str | None:
    if asset.audio:
        return asset.audio.key_estimate
    if asset.midi:
        return asset.midi.key_estimate
    return None


def _asset_mode(asset: ProjectAsset) -> str | None:
    return asset.audio.mode_estimate if asset.audio else None


def similar_assets(
    target: ProjectAsset,
    others: list[ProjectAsset],
    limit: int = 5,
) -> list[dict]:
    """Rank ``others`` by feature similarity to ``target`` with a per-dimension breakdown."""
    target_features = _numeric_features(target)
    target_key = _asset_key(target)

    scored: list[dict] = []
    for asset in others:
        features = _numeric_features(asset)
        dimensions: dict[str, float] = {}
        for dimension in NUMERIC_DIMENSIONS:
            if dimension in target_features and dimension in features:
                if dimension == "tempo":
                    dimensions[dimension] = tempo_similarity(
                        target_features[dimension], features[dimension]
                    )
                else:
                    diff = abs(target_features[dimension] - features[dimension])
                    dimensions[dimension] = max(0.0, 1.0 - diff / DIMENSION_SCALE[dimension])

        asset_key = _asset_key(asset)
        if target_key and asset_key:
            compatibility = key_compatibility(
                target_key, _asset_mode(target), asset_key, _asset_mode(asset)
            )
            if compatibility is not None:
                dimensions["key"] = compatibility

        if not dimensions:
            continue
        overall = sum(dimensions.values()) / len(dimensions)
        scored.append(
            {
                "id": asset.id,
                "file_name": asset.file_name,
                "project_name": asset.project_name,
                "score": round(overall, 4),
                "dimensions": {key: round(value, 3) for key, value in dimensions.items()},
                "highlights": _highlights(dimensions),
            }
        )

    scored.sort(key=lambda item: item["score"], reverse=True)
    return scored[:limit]


def producer_profile(assets: list[ProjectAsset], preferences: list[str]) -> dict:
    """A 'creative fingerprint' derived from the library, plus the producer's own
    stated preferences. This is the AI-memory the assistant carries session to session.
    """
    bpms = [
        value
        for asset in assets
        if (value := (asset.audio.bpm_estimate if asset.audio else None))
    ]
    bpms += [
        asset.midi.tempo_bpm for asset in assets if asset.midi and asset.midi.tempo_bpm
    ]
    keys = Counter(
        key
        for asset in assets
        if (key := (_asset_key(asset)))
    )
    loudness = [
        asset.audio.rms_db
        for asset in assets
        if asset.audio and asset.audio.rms_db is not None
    ]
    brightness = [
        asset.audio.spectral_centroid_mean
        for asset in assets
        if asset.audio and asset.audio.spectral_centroid_mean
    ]
    projects = Counter(asset.project_name for asset in assets)

    derived: list[str] = []
    if bpms:
        derived.append(f"Typically works around {round(sum(bpms) / len(bpms))} BPM "
                       f"(range {round(min(bpms))}-{round(max(bpms))}).")
    if keys:
        top = ", ".join(key for key, _ in keys.most_common(3))
        derived.append(f"Most-used keys: {top}.")
    if loudness:
        derived.append(f"Average mix loudness around {sum(loudness) / len(loudness):.1f} dB RMS.")
    if brightness:
        avg = sum(brightness) / len(brightness)
        tone = "bright" if avg > 2500 else "warm"
        derived.append(f"Leans {tone} (avg brightness {round(avg)} Hz).")
    if projects:
        busiest, count = projects.most_common(1)[0]
        derived.append(f"Most active project: {busiest} ({count} files).")

    return {
        "stats": {
            "files": len(assets),
            "projects": len(projects),
            "audio": sum(1 for a in assets if a.kind == AssetKind.AUDIO),
            "midi": sum(1 for a in assets if a.kind == AssetKind.MIDI),
            "notes": sum(1 for a in assets if a.kind == AssetKind.NOTE),
            "avg_bpm": round(sum(bpms) / len(bpms)) if bpms else None,
            "top_keys": [key for key, _ in keys.most_common(3)],
        },
        "derived": derived,
        "preferences": preferences,
    }


def _highlights(dimensions: dict[str, float]) -> list[str]:
    """Short phrases for the strongest shared traits ('similar tempo', 'same key')."""
    phrases = {
        "tempo": "similar tempo",
        "brightness": "similar brightness",
        "loudness": "similar loudness",
        "duration": "similar length",
        "key": "same key",
    }
    # "same key" is reserved for an exact match; graded compatibility gets its
    # own label so a fifth-up neighbor never reads as the same key.
    strong = sorted(
        (item for item in dimensions.items() if item[1] >= 0.8 and item[0] != "key"),
        key=lambda item: item[1],
        reverse=True,
    )
    highlights = [phrases[name] for name, _ in strong if name in phrases]
    key_score = dimensions.get("key", 0.0)
    if key_score >= 0.99:
        highlights.append("same key")
    elif key_score >= 0.55:
        highlights.append("compatible key")
    return highlights
