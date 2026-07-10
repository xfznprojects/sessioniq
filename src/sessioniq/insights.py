"""Content-based similarity between assets, from the analysis features SessionIQ
already extracts. Works without embeddings (numeric feature vectors); the vector
store, when present, sharpens retrieval separately in the retriever.
"""

from __future__ import annotations

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
                diff = abs(target_features[dimension] - features[dimension])
                dimensions[dimension] = max(0.0, 1.0 - diff / DIMENSION_SCALE[dimension])

        asset_key = _asset_key(asset)
        if target_key and asset_key:
            dimensions["key"] = 1.0 if target_key == asset_key else 0.0

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
    strong = sorted(
        (item for item in dimensions.items() if item[1] >= 0.8),
        key=lambda item: item[1],
        reverse=True,
    )
    return [phrases[name] for name, _ in strong if name in phrases]
