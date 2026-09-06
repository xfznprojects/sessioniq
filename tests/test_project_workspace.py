from __future__ import annotations

import os
from pathlib import Path

from sessioniq.models import (
    AssetKind,
    AudioMetadata,
    NoteMetadata,
    ProjectAsset,
    TaskStatus,
)
from sessioniq.project_workspace import (
    UPLOAD_ROOT,
    move_stored_file,
    project_slug,
    rename_project_files,
    safe_upload_path,
    summarize_projects,
)


def test_default_upload_root_is_local_ignored_app_data():
    # Respects SESSIONIQ_UPLOAD_ROOT when set, otherwise the git-ignored default.
    expected = Path(os.getenv("SESSIONIQ_UPLOAD_ROOT", ".sessioniq-data/uploads"))
    assert expected == UPLOAD_ROOT


def test_safe_upload_path_uses_project_folder_and_avoids_collisions(tmp_path):
    first = safe_upload_path("Vivien Remix", "../track.wav", root=tmp_path)
    first.write_bytes(b"audio")

    second = safe_upload_path("Vivien Remix", "../track.wav", root=tmp_path)

    assert first.parent.name.startswith("vivien-remix--")
    assert first.name == "track.wav"
    assert second.name == "track-2.wav"


def test_project_slug_preserves_album_song_hierarchy():
    assert project_slug("Summer EP/Song One") == "summer-ep/song-one"
    assert project_slug("  Album X / Track 2  ") == "album-x/track-2"
    assert project_slug("//weird///path//") == "weird/path"


def test_nested_upload_path_creates_song_folder(tmp_path):
    from sessioniq.project_workspace import safe_upload_path as sup

    path = sup("Summer EP/Intro", "loop.wav", root=tmp_path)
    assert path.parent.parent == tmp_path / "summer-ep"
    assert path.parent.name.startswith("intro--")
    assert path.name == "loop.wav"


def test_move_stored_file_relocates_and_cleans_empty_source(tmp_path):
    source = safe_upload_path("Old Project", "loop.wav", root=tmp_path)
    source.write_bytes(b"audio")

    moved = move_stored_file(str(source), "New Project", root=tmp_path)

    assert moved is not None
    moved_path = Path(moved)
    assert moved_path.exists()
    assert not source.exists()
    assert not source.parent.exists()  # empty old folder is removed


def test_move_stored_file_avoids_overwriting_existing_name(tmp_path):
    existing = safe_upload_path("New Project", "loop.wav", root=tmp_path)
    existing.write_bytes(b"first")
    source = safe_upload_path("Old Project", "loop.wav", root=tmp_path)
    source.write_bytes(b"second")

    moved = move_stored_file(str(source), "New Project", root=tmp_path)

    assert Path(moved).parent == existing.parent
    assert Path(moved).name == "loop-2.wav"
    assert existing.read_bytes() == b"first"


def test_move_stored_file_is_noop_for_missing_source(tmp_path):
    ghost = str(tmp_path / "old" / "gone.wav")

    assert move_stored_file(ghost, "New Project", root=tmp_path) == ghost


def test_rename_project_files_moves_every_asset(tmp_path):
    paths = []
    for name in ("kick.wav", "snare.wav"):
        path = safe_upload_path("Draft", name, root=tmp_path)
        path.write_bytes(b"x")
        paths.append(str(path))

    moved = rename_project_files(paths, "Final Mix", root=tmp_path)

    assert all(Path(path).exists() for path in moved)
    assert all(Path(path).parent.name.startswith("final-mix--") for path in moved)


def test_summarize_projects_counts_assets_and_progress():
    asset = ProjectAsset(
        id="notes",
        file_name="mix_notes.txt",
        kind=AssetKind.NOTE,
        project_name="Vivien Remix",
        text=NoteMetadata(
            text="TODO tighten kick.\nTry shorter reverb.",
            word_count=5,
            action_items=["TODO tighten kick.", "Try shorter reverb."],
        ),
    )
    first_summary = summarize_projects([asset])[0]
    overrides = {first_summary.tasks[0].id: TaskStatus.DONE.value}

    summary = summarize_projects([asset], overrides)[0]

    assert summary.asset_count == 1
    assert summary.note_count == 1
    assert len(summary.tasks) == 2
    assert summary.tasks[0].status == TaskStatus.DONE
    assert summary.progress == 0.5


def test_duplicate_collection_flags_same_bounce_only():
    from sessioniq.project_workspace import smart_collections

    def dup(name, rms=-12.0):
        return ProjectAsset(
            id=name,
            file_name=f"{name}.wav",
            kind=AssetKind.AUDIO,
            project_name="Dupes",
            audio=AudioMetadata(
                duration_seconds=180.0,
                bpm_estimate=124.0,
                rms_amplitude=0.2,
                rms_db=rms,
                spectral_centroid_mean=2500.0,
            ),
        )

    rough = dup("afterglow rough mix")
    final = dup("afterglow final master")
    stranger = ProjectAsset(
        id="stranger",
        file_name="stranger.wav",
        kind=AssetKind.AUDIO,
        project_name="Dupes",
        audio=AudioMetadata(
            duration_seconds=180.0,  # Same grid, different song.
            bpm_estimate=124.0,
            rms_amplitude=0.2,
            rms_db=-20.0,
            spectral_centroid_mean=900.0,
        ),
    )

    collections = smart_collections([rough, final, stranger])

    flagged = collections.get("Possible Duplicates", [])
    names = {asset.file_name for asset in flagged}
    assert names == {"afterglow rough mix.wav", "afterglow final master.wav"}


def test_no_duplicates_collection_for_distinct_files():
    from sessioniq.project_workspace import smart_collections

    one = ProjectAsset(
        id="one",
        file_name="one.wav",
        kind=AssetKind.AUDIO,
        audio=AudioMetadata(duration_seconds=60.0, bpm_estimate=90.0),
    )
    two = ProjectAsset(
        id="two",
        file_name="two.wav",
        kind=AssetKind.AUDIO,
        audio=AudioMetadata(duration_seconds=61.0, bpm_estimate=128.0),
    )

    assert "Possible Duplicates" not in smart_collections([one, two])
