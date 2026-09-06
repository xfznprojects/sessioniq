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


def test_tempo_similarity_treats_double_time_as_same_groove():
    from sessioniq.insights import tempo_similarity

    assert tempo_similarity(90.0, 180.0) == 1.0
    assert tempo_similarity(180.0, 90.0) == 1.0
    assert tempo_similarity(90.0, 175.0) > 0.7  # near half-time
    # Genuinely different tempi stay dissimilar.
    assert tempo_similarity(90.0, 150.0) < 0.05


def test_similarity_scores_half_time_tracks_as_close():
    target = _audio("half", 90, 3000, -12, "C")
    double = _audio("double", 180, 3050, -12, "C")

    dims = similar_assets(target, [double])[0]["dimensions"]

    assert dims["tempo"] > 0.9


def test_key_compatibility_relative_minor_and_neighbors():
    from sessioniq.insights import key_compatibility

    assert key_compatibility("C", "major", "A", "minor") == 0.95  # relative minor
    assert key_compatibility("C", "major", "C", "major") == 1.0
    assert key_compatibility("C", None, "G", None) == 0.85  # perfect fifth
    assert key_compatibility("C", None, "F#", None) == 0.0


def test_similarity_reports_compatible_key_highlight():
    target = _audio("root", 120, 2500, -12, "C")
    neighbor = _audio("fifth", 121, 2510, -12, "G")

    match = similar_assets(target, [neighbor])[0]

    assert "compatible key" in match["highlights"]
    assert "same key" not in match["highlights"]
