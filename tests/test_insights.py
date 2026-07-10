from __future__ import annotations

from sessioniq.insights import similar_assets
from sessioniq.models import AssetKind, AudioMetadata, ProjectAsset


def _audio(asset_id: str, bpm: float, centroid: float, rms_db: float, key: str) -> ProjectAsset:
    return ProjectAsset(
        id=asset_id,
        file_name=f"{asset_id}.wav",
        kind=AssetKind.AUDIO,
        audio=AudioMetadata(
            duration_seconds=120,
            bpm_estimate=bpm,
            spectral_centroid_mean=centroid,
            rms_amplitude=0.2,
            rms_db=rms_db,
            peak_amplitude=0.9,
            key_estimate=key,
        ),
    )


def test_similarity_ranks_closest_track_first():
    target = _audio("target", 128, 3000, -10, "A")
    near = _audio("near", 126, 3100, -11, "A")
    far = _audio("far", 90, 1200, -22, "F")

    matches = similar_assets(target, [near, far])

    assert matches[0]["id"] == "near"
    assert matches[0]["score"] > matches[1]["score"]
    assert "same key" in matches[0]["highlights"]


def test_similarity_reports_per_dimension_breakdown():
    target = _audio("a", 120, 2500, -12, "C")
    other = _audio("b", 121, 2510, -12, "C")

    dims = similar_assets(target, [other])[0]["dimensions"]

    assert {"tempo", "brightness", "loudness", "key"}.issubset(dims)
    assert dims["tempo"] > 0.9


def test_similarity_handles_missing_features_gracefully():
    target = _audio("a", 120, 2500, -12, "C")
    bare = ProjectAsset(
        id="bare",
        file_name="bare.wav",
        kind=AssetKind.AUDIO,
        audio=AudioMetadata(duration_seconds=0),
    )
    # No overlapping numeric features -> excluded rather than crashing.
    assert similar_assets(target, [bare]) == []
