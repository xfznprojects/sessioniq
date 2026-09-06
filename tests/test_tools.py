from __future__ import annotations

import json

from sessioniq.models import (
    AssetKind,
    AssetTag,
    AudioMetadata,
    FileStatus,
    ProjectAsset,
    ProjectTask,
    TaskStatus,
)
from sessioniq.tools import LibraryToolbox


def _audio(
    asset_id: str,
    bpm: float,
    status: FileStatus = FileStatus.IN_PROGRESS,
    key: str | None = None,
    rms_db: float = -12.0,
    tags: list[str] | None = None,
    project: str = "Album/Song A",
) -> ProjectAsset:
    return ProjectAsset(
        id=asset_id,
        file_name=f"{asset_id}.wav",
        kind=AssetKind.AUDIO,
        project_name=project,
        status=status,
        audio=AudioMetadata(
            duration_seconds=120.0,
            bpm_estimate=bpm,
            rms_amplitude=0.2,
            rms_db=rms_db,
            key_estimate=key,
        ),
        tags=[AssetTag(label=label) for label in tags or []],
    )


def _tasks_for(*assets: ProjectAsset) -> list[ProjectTask]:
    return [
        ProjectTask(
            id=f"task-{asset.id}",
            asset_id=asset.id,
            project_name=asset.project_name,
            description=f"Polish {asset.file_name}",
            source_file=asset.file_name,
            status=TaskStatus.TODO,
        )
        for asset in assets
    ]


def _toolbox(assets: list[ProjectAsset], **kwargs) -> LibraryToolbox:
    return LibraryToolbox(assets, tasks=_tasks_for(*assets), **kwargs)


def _run(toolbox: LibraryToolbox, name: str, arguments: dict) -> dict:
    return json.loads(toolbox.execute(name, arguments))


def test_filter_assets_by_status_and_kind():
    ready = _audio("ready", 120.0, status=FileStatus.READY)
    draft = _audio("draft", 100.0)
    toolbox = _toolbox([ready, draft])

    result = _run(toolbox, "filter_assets", {"status": "Ready"})

    assert result["total_matches"] == 1
    assert result["assets"][0]["file_name"] == "ready.wav"
    assert ready.id in toolbox.touched


def test_filter_assets_respects_default_project_scope():
    in_scope = _audio("inside", 120.0, project="Album/Song A")
    outside = _audio("outside", 120.0, project="Other Project")
    toolbox = _toolbox([in_scope, outside], default_project="Album")

    result = _run(toolbox, "filter_assets", {})

    assert result["total_matches"] == 1
    assert result["assets"][0]["file_name"] == "inside.wav"


def test_filter_assets_by_bpm_range_and_key():
    fast = _audio("fast", 150.0, key="C")
    slow = _audio("slow", 90.0, key="A")
    toolbox = _toolbox([fast, slow])

    result = _run(toolbox, "filter_assets", {"bpm_min": 100, "key": "C"})

    assert result["total_matches"] == 1
    assert result["assets"][0]["file_name"] == "fast.wav"


def test_compute_stat_max_includes_winning_asset():
    quiet = _audio("quiet", 120.0, rms_db=-24.0)
    hot = _audio("hot", 120.0, rms_db=-9.0)
    toolbox = _toolbox([quiet, hot])

    result = _run(toolbox, "compute_stat", {"field": "rms_db", "op": "max"})

    assert result["max"] == -9.0
    assert result["asset"]["file_name"] == "hot.wav"
    assert hot.id in toolbox.touched


def test_compute_stat_avg_and_count():
    toolbox = _toolbox([_audio("a", 100.0), _audio("b", 140.0)])

    assert _run(toolbox, "compute_stat", {"field": "bpm", "op": "avg"})["avg"] == 120.0
    assert _run(toolbox, "compute_stat", {"field": "bpm", "op": "count"})["count"] == 2


def test_compute_stat_reports_missing_field_gracefully():
    toolbox = _toolbox([_audio("a", 100.0)])

    result = _run(toolbox, "compute_stat", {"field": "brightness", "op": "max"})

    assert "error" in result


def test_asset_details_includes_tasks_and_metadata():
    asset = _audio("detail", 120.0)
    toolbox = _toolbox([asset])

    result = _run(toolbox, "asset_details", {"asset_id": asset.id})

    assert result["asset"]["file_name"] == "detail.wav"
    assert "bpm=120" in result["metadata"]
    assert result["tasks"][0]["description"] == "Polish detail.wav"


def test_asset_details_rejects_unknown_id():
    result = _run(_toolbox([]), "asset_details", {"asset_id": "nope"})
    assert "error" in result


def test_search_library_delegates_and_records_touched():
    from sessioniq.models import RetrievedSource

    asset = _audio("found", 120.0)

    def fake_search(query, limit=4, project_name=None):
        assert query == "needs mastering"
        return [RetrievedSource(asset=asset, score=1.5)]

    toolbox = _toolbox([asset], search=fake_search)
    result = _run(toolbox, "search_library", {"query": "needs mastering"})

    assert result["matches"][0]["file_name"] == "found.wav"
    assert asset.id in toolbox.touched


def test_list_projects_counts_files_and_open_tasks():
    first = _audio("a", 120.0, project="Album/Song A")
    second = _audio("b", 120.0, project="Album/Song B")
    toolbox = _toolbox([first, second])

    result = _run(toolbox, "list_projects", {})

    projects = {item["project"]: item for item in result["projects"]}
    assert projects["Album/Song A"]["files"] == 1
    assert projects["Album/Song A"]["open_tasks"] == 1


def test_unknown_tool_and_bad_arguments_return_errors():
    toolbox = _toolbox([_audio("a", 120.0)])

    assert "error" in _run(toolbox, "does_not_exist", {})
    # Non-serializable filter values must not raise out of execute().
    assert "error" in _run(toolbox, "compute_stat", {"field": "bpm", "op": "explode"})
