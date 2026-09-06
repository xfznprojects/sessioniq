from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sessioniq.advisor import rank_next, reference_comparison, weekly_digest
from sessioniq.models import (
    AssetKind,
    AudioMetadata,
    FileStatus,
    ProjectAsset,
    ProjectSummary,
)


def _audio(asset_id: str, name: str, project: str, status=FileStatus.IN_PROGRESS, **audio_kwargs):
    defaults = dict(
        duration_seconds=180.0,
        bpm_estimate=124.0,
        rms_amplitude=0.2,
        rms_db=-14.0,
        peak_amplitude=0.9,
        peak_db=-1.0,
        integrated_lufs=-14.0,
        spectral_centroid_mean=2500.0,
    )
    defaults.update(audio_kwargs)
    return ProjectAsset(
        id=asset_id,
        file_name=name,
        kind=AssetKind.AUDIO,
        project_name=project,
        status=status,
        audio=AudioMetadata(**defaults),
    )


def test_reference_comparison_reports_signed_deltas():
    reference = _audio(
        "ref", "ref master.wav", "EP/Song", status=FileStatus.REFERENCE, rms_db=-10.0
    )
    mix = _audio("mix", "rough mix.wav", "EP/Song", rms_db=-16.0, integrated_lufs=-20.0)

    result = reference_comparison([reference, mix], "EP/Song")

    assert result["reference"]["file_name"] == "ref master.wav"
    deltas = result["comparisons"][0]["deltas"]
    assert deltas["rms_db"] == -6.0
    assert deltas["integrated_lufs"] == -6.0
    assert deltas["peak_db"] == 0.0


def test_reference_comparison_without_reference_returns_none():
    mix = _audio("mix", "rough mix.wav", "EP/Song")
    assert reference_comparison([mix], "EP/Song") is None


def test_reference_comparison_scopes_to_project_tree():
    reference = _audio("ref", "ref.wav", "EP/One", status=FileStatus.REFERENCE)
    other = _audio("mix", "mix.wav", "EP/Two")

    result = reference_comparison([reference, other], "EP/One")

    assert [item["file_name"] for item in result["comparisons"]] == []


def test_rank_next_favors_progress_and_readiness():
    from sessioniq.models import ProjectHealth

    def summary(name: str, progress: float, health: float) -> ProjectSummary:
        return ProjectSummary(
            project_name=name,
            asset_count=1,
            audio_count=1,
            midi_count=0,
            note_count=0,
            tasks=[],
            progress=progress,
            health=ProjectHealth(score=health),
        )

    fresh = datetime.now(UTC) - timedelta(days=2)
    stale = datetime.now(UTC) - timedelta(days=60)
    assets = [
        ProjectAsset(
            id="a",
            file_name="a.wav",
            kind=AssetKind.AUDIO,
            project_name="Almost There",
            date_added=fresh.isoformat(),
        ),
        ProjectAsset(
            id="b",
            file_name="b.wav",
            kind=AssetKind.AUDIO,
            project_name="Early Idea",
            date_added=stale.isoformat(),
        ),
    ]
    ranking = rank_next(
        assets,
        [summary("Almost There", 0.8, 1.0), summary("Early Idea", 0.1, 0.2)],
    )

    assert ranking[0]["project_name"] == "Almost There"
    assert "80% through its tasks" in ranking[0]["reasons"]
    assert ranking[1]["project_name"] == "Early Idea"


def test_weekly_digest_flags_stalled_and_ready():
    old = (datetime.now(UTC) - timedelta(days=30)).isoformat()
    new = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assets = [
        _audio("stalled", "stalled.wav", "Old Song", status=FileStatus.NEEDS_WORK),
        _audio("ready", "final.wav", "Done Song", status=FileStatus.READY),
        ProjectAsset(
            id="stalled-id",
            file_name="stalled.wav",
            kind=AssetKind.AUDIO,
            project_name="Old Song",
            status=FileStatus.NEEDS_WORK,
            date_added=old,
        ),
        ProjectAsset(
            id="ready-id",
            file_name="final.wav",
            kind=AssetKind.AUDIO,
            project_name="Done Song",
            status=FileStatus.READY,
            date_added=new,
        ),
    ]
    # The _audio helper has no dates; use the dated bare assets only.
    assets = [
        ProjectAsset(
            id="stalled-id",
            file_name="stalled.wav",
            kind=AssetKind.AUDIO,
            project_name="Old Song",
            status=FileStatus.NEEDS_WORK,
            date_added=old,
            audio=AudioMetadata(duration_seconds=60.0, bpm_estimate=120.0),
        ),
        ProjectAsset(
            id="ready-id",
            file_name="final.wav",
            kind=AssetKind.AUDIO,
            project_name="Done Song",
            status=FileStatus.READY,
            date_added=new,
            audio=AudioMetadata(duration_seconds=60.0, bpm_estimate=120.0),
        ),
    ]

    digest = weekly_digest(assets, [])

    assert digest["stalled"][0]["file_name"] == "stalled.wav"
    assert digest["stalled"][0]["days_idle"] >= 29
    assert digest["ready_to_ship"][0]["file_name"] == "final.wav"
    assert digest["added_this_week"]["count"] == 1
