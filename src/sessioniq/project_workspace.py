from __future__ import annotations

import hashlib
import os
import re
from collections import defaultdict
from pathlib import Path

from sessioniq.models import (
    AssetKind,
    FileStatus,
    HealthCheck,
    ProjectAsset,
    ProjectHealth,
    ProjectSummary,
    ProjectTask,
    TaskStatus,
)
from sessioniq.note_analysis import extract_action_items

UPLOAD_ROOT = Path(os.getenv("SESSIONIQ_UPLOAD_ROOT", ".sessioniq-data/uploads"))

STATUS_WEIGHTS = {
    TaskStatus.TODO: 0.0,
    TaskStatus.IN_PROGRESS: 0.35,
    TaskStatus.ALMOST_DONE: 0.75,
    TaskStatus.DONE: 1.0,
}


def project_slug(project_name: str) -> str:
    """Slug a project path. '/' separates album → song folders and is preserved,
    so "Summer EP/Song One" maps to the nested folder "summer-ep/song-one"."""
    segments = []
    for segment in project_name.strip().split("/"):
        cleaned = segment.strip().lower()
        slug = re.sub(r"[^a-z0-9._-]+", "-", cleaned).strip("-._")
        if slug:
            segments.append(slug)
    return "/".join(segments) or "unassigned"


def safe_upload_path(project_name: str, file_name: str, root: Path = UPLOAD_ROOT) -> Path:
    # Keep existing stored paths valid, but isolate new uploads even when display
    # names slug to the same spelling (including on case-insensitive filesystems).
    name = "/".join(part.strip() for part in project_name.split("/") if part.strip())
    identity = hashlib.sha256((name or "Unassigned").encode()).hexdigest()[:16]
    project_dir = root / f"{project_slug(project_name)}--{identity}"
    project_dir.mkdir(parents=True, exist_ok=True)
    basename = Path(file_name.replace("\\", "/")).name
    if basename in {"", ".", ".."} or ":" in basename:
        raise ValueError("Invalid upload filename.")
    file_path = project_dir / basename
    file_path.resolve().relative_to(root.resolve())
    if not file_path.exists():
        return file_path

    stem = file_path.stem
    suffix = file_path.suffix
    counter = 2
    while True:
        candidate = project_dir / f"{stem}-{counter}{suffix}"
        if not candidate.exists():
            return candidate
        counter += 1


def move_stored_file(
    stored_path: str | None,
    new_project_name: str,
    root: Path = UPLOAD_ROOT,
) -> str | None:
    """Move an asset's file into another project's folder, avoiding name clashes.

    Returns the new stored path, or the original value when there is nothing on
    disk to move. Never raises for a missing source file - the caller may be
    working from a persisted index whose upload was cleaned up.
    """
    if not stored_path:
        return stored_path
    source = Path(stored_path)
    source.resolve().relative_to(root.resolve())
    destination = safe_upload_path(new_project_name, source.name, root=root)
    if source.resolve() == destination.resolve():
        return str(source)
    if source.exists():
        source.replace(destination)
        _cleanup_empty_dir(source.parent, root)
        return str(destination)
    return stored_path


def rename_project_files(
    stored_paths: list[str | None],
    new_project_name: str,
    root: Path = UPLOAD_ROOT,
) -> list[str | None]:
    """Relocate every file of a project into the renamed project's folder."""
    return [move_stored_file(path, new_project_name, root=root) for path in stored_paths]


def _cleanup_empty_dir(directory: Path, root: Path) -> None:
    try:
        if directory.resolve() == root.resolve():
            return
        if directory.is_dir() and not any(directory.iterdir()):
            directory.rmdir()
    except OSError:
        pass


def summarize_projects(
    assets: list[ProjectAsset],
    status_overrides: dict[str, str] | None = None,
) -> list[ProjectSummary]:
    overrides = status_overrides if status_overrides is not None else {}
    grouped: dict[str, list[ProjectAsset]] = defaultdict(list)
    for asset in assets:
        grouped[asset.project_name].append(asset)

    summaries: list[ProjectSummary] = []
    for project_name, project_assets in sorted(grouped.items()):
        tasks = _project_tasks(project_name, project_assets, overrides)
        summaries.append(
            ProjectSummary(
                project_name=project_name,
                asset_count=len(project_assets),
                audio_count=sum(asset.kind == AssetKind.AUDIO for asset in project_assets),
                midi_count=sum(asset.kind == AssetKind.MIDI for asset in project_assets),
                note_count=sum(asset.kind == AssetKind.NOTE for asset in project_assets),
                tasks=tasks,
                progress=_progress(tasks),
                health=project_health(project_assets, tasks),
            )
        )
    return summaries


def project_health(assets: list[ProjectAsset], tasks: list[ProjectTask]) -> ProjectHealth:
    """Score a project's completeness from what a finished release usually needs."""
    has_audio = any(asset.kind == AssetKind.AUDIO for asset in assets)
    has_notes = any(asset.note or asset.text for asset in assets)
    has_reference = any(
        asset.kind == AssetKind.AUDIO and asset.status == FileStatus.REFERENCE for asset in assets
    )
    has_master = any(
        asset.kind == AssetKind.AUDIO and asset.status == FileStatus.READY for asset in assets
    )
    open_tasks = [task for task in tasks if task.status != TaskStatus.DONE]
    tasks_clear = not open_tasks

    checks = [
        HealthCheck(label="Audio imported", ok=has_audio),
        HealthCheck(label="Mix notes", ok=has_notes),
        HealthCheck(label="Reference track", ok=has_reference),
        HealthCheck(label="Master / export", ok=has_master),
        HealthCheck(label="Tasks cleared", ok=tasks_clear),
    ]
    score = sum(check.ok for check in checks) / len(checks)

    suggestions: list[str] = []
    if not has_audio:
        suggestions.append("Import at least one audio file.")
    if not has_notes:
        suggestions.append("Add mix notes so the assistant has context.")
    if not has_reference:
        suggestions.append("Add a reference track to compare against.")
    if not has_master:
        suggestions.append("Export a master / final version.")
    if open_tasks:
        suggestions.append(f"Finish {len(open_tasks)} open task(s).")

    return ProjectHealth(score=score, checks=checks, suggestions=suggestions)


def smart_collections(assets: list[ProjectAsset]) -> dict[str, list[ProjectAsset]]:
    unfinished_statuses = {FileStatus.IDEA, FileStatus.IN_PROGRESS, FileStatus.NEEDS_WORK}
    collections: dict[str, list[ProjectAsset]] = {
        "Needs Work": [
            asset
            for asset in assets
            if asset.status == FileStatus.NEEDS_WORK
            or any(tag.label.lower() == "needs work" for tag in asset.tags)
        ],
        "Needs Mixing": [
            asset
            for asset in assets
            if asset.kind == AssetKind.AUDIO and asset.status == FileStatus.IN_PROGRESS
        ],
        "Needs Mastering": [
            asset
            for asset in assets
            if asset.kind == AssetKind.AUDIO
            and asset.status not in {FileStatus.READY, FileStatus.REFERENCE, FileStatus.ARCHIVED}
            and not any(word in asset.file_name.lower() for word in ("master", "final", "export"))
        ],
        "Unfinished": [asset for asset in assets if asset.status in unfinished_statuses],
        "Ready to Export": [asset for asset in assets if asset.status == FileStatus.READY],
        "High BPM (140+)": [asset for asset in assets if (bpm := _asset_bpm(asset)) and bpm >= 140],
        "Missing Notes": [asset for asset in assets if not asset.note and not asset.text],
        "Recently Analyzed": sorted(
            [asset for asset in assets if asset.last_analyzed],
            key=lambda asset: asset.last_analyzed or "",
            reverse=True,
        )[:12],
    }
    collections.update(_similar_bpm_collections(assets))
    collections.update(_same_key_collections(assets))
    return {name: items for name, items in collections.items() if items}


def _project_tasks(
    project_name: str,
    assets: list[ProjectAsset],
    status_overrides: dict[str, str],
) -> list[ProjectTask]:
    tasks: list[ProjectTask] = []
    for asset in assets:
        descriptions: list[str] = []
        if asset.note:
            descriptions.extend(extract_action_items(asset.note))
        if asset.text:
            descriptions.extend(asset.text.action_items)

        for description in dict.fromkeys(descriptions):
            task_id = hashlib.sha256(f"{asset.id}|{description}".encode()).hexdigest()[:20]
            legacy_id = _task_id(project_name, asset.file_name, description)
            if task_id not in status_overrides and legacy_id in status_overrides:
                status_overrides[task_id] = status_overrides[legacy_id]
            status = TaskStatus(status_overrides.get(task_id, TaskStatus.TODO.value))
            tasks.append(
                ProjectTask(
                    id=task_id,
                    asset_id=asset.id,
                    project_name=project_name,
                    description=description,
                    source_file=asset.file_name,
                    status=status,
                )
            )
    return tasks


def _task_id(project_name: str, file_name: str, description: str) -> str:
    digest = hashlib.sha1(
        f"{project_name}|{file_name}|{description}".encode(),
        usedforsecurity=False,
    ).hexdigest()
    return digest[:12]


def _progress(tasks: list[ProjectTask]) -> float:
    if not tasks:
        return 0.0
    total = sum(STATUS_WEIGHTS[task.status] for task in tasks)
    return total / len(tasks)


def _similar_bpm_collections(assets: list[ProjectAsset]) -> dict[str, list[ProjectAsset]]:
    buckets: dict[int, list[ProjectAsset]] = defaultdict(list)
    for asset in assets:
        bpm = _asset_bpm(asset)
        if bpm:
            bucket = round(bpm / 5) * 5
            buckets[bucket].append(asset)
    return {
        f"Similar BPM: {bucket}": bucket_assets
        for bucket, bucket_assets in sorted(buckets.items())
        if len(bucket_assets) > 1
    }


def _same_key_collections(assets: list[ProjectAsset]) -> dict[str, list[ProjectAsset]]:
    groups: dict[str, list[ProjectAsset]] = defaultdict(list)
    for asset in assets:
        key = _asset_key(asset)
        if key:
            groups[key].append(asset)
    return {
        f"Same Key: {key}": key_assets
        for key, key_assets in sorted(groups.items())
        if len(key_assets) > 1
    }


def _asset_bpm(asset: ProjectAsset) -> float | None:
    if asset.audio:
        return asset.audio.bpm_estimate
    if asset.midi:
        return asset.midi.tempo_bpm
    return None


def _asset_key(asset: ProjectAsset) -> str | None:
    if asset.audio:
        return asset.audio.key_estimate
    if asset.midi:
        return asset.midi.key_estimate
    return None
