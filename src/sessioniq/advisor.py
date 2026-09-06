"""Library-level advice from already-extracted metadata.

Reference A/B comparison, a what-to-finish-next ranking, and a weekly digest —
all pure functions over the analyzed library, so every number shown can be
traced back to the same facts the assistant cites.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sessioniq.models import AssetKind, FileStatus, ProjectAsset, ProjectSummary, TaskStatus

# A mix is "stalled" when nothing in its project moved for this long.
STALLED_AFTER_DAYS = 14
FRESH_WITHIN_DAYS = 30
ACTIVE_WITHIN_DAYS = 90


def _age_days(timestamp: str | None) -> float | None:
    if not timestamp:
        return None
    try:
        moment = datetime.fromisoformat(timestamp)
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=UTC)
    return (datetime.now(UTC) - moment).total_seconds() / 86400


def _in_scope(project_name: str, scope: str) -> bool:
    return project_name == scope or project_name.startswith(scope.rstrip("/") + "/")


def reference_comparison(assets: list[ProjectAsset], scope: str) -> dict | None:
    """Compare every mix in a project against its reference track.

    Deltas are signed (mix minus reference): "-6.0 dB" means the mix is 6 dB
    quieter than the reference. Only fields measured on both files are
    reported; None means "not analyzed on this pair".
    """
    scoped = [asset for asset in assets if _in_scope(asset.project_name, scope)]
    references = [
        asset
        for asset in scoped
        if asset.audio and asset.status == FileStatus.REFERENCE
    ]
    if not references:
        return None
    references.sort(key=lambda asset: asset.date_added or "")
    reference = references[0]
    mixes = [
        asset
        for asset in scoped
        if asset.audio
        and asset.status not in {FileStatus.REFERENCE, FileStatus.ARCHIVED}
        and asset.kind == AssetKind.AUDIO
    ]
    comparisons = []
    for mix in mixes:
        deltas: dict[str, float | None] = {}
        for field in ("rms_db", "peak_db", "integrated_lufs", "spectral_centroid_mean"):
            mix_value = getattr(mix.audio, field, None)
            ref_value = getattr(reference.audio, field, None)
            if mix_value is not None and ref_value is not None:
                deltas[field] = round(mix_value - ref_value, 2)
        if mix.audio.duration_seconds and reference.audio.duration_seconds:
            deltas["duration_seconds"] = round(
                mix.audio.duration_seconds - reference.audio.duration_seconds, 1
            )
        comparisons.append({"asset_id": mix.id, "file_name": mix.file_name, "deltas": deltas})
    return {
        "reference": {"asset_id": reference.id, "file_name": reference.file_name},
        "comparisons": comparisons,
    }


def rank_next(assets: list[ProjectAsset], summaries: list[ProjectSummary]) -> list[dict]:
    """Rank projects by how finishable they are right now.

    45% readiness (health checks), 35% task progress, 20% freshness so the
    ranking favors work that is close to done and still warm — and surfaces
    near-finished stale projects as "stalled" instead of burying them.
    """
    latest_by_project: dict[str, str] = {}
    for asset in assets:
        if asset.date_added and (
            asset.project_name not in latest_by_project
            or asset.date_added > latest_by_project[asset.project_name]
        ):
            latest_by_project[asset.project_name] = asset.date_added

    ranked = []
    for summary in summaries:
        latest = _age_days(latest_by_project.get(summary.project_name))
        if latest is None:
            freshness = 0.2
        elif latest <= FRESH_WITHIN_DAYS:
            freshness = 1.0
        elif latest <= ACTIVE_WITHIN_DAYS:
            freshness = 0.6
        else:
            freshness = 0.2
        score = 0.45 * summary.health.score + 0.35 * summary.progress + 0.20 * freshness
        reasons = []
        if summary.progress >= 0.99:
            reasons.append("all tasks done")
        elif summary.progress > 0:
            reasons.append(f"{round(summary.progress * 100)}% through its tasks")
        missing = [check.label for check in summary.health.checks if not check.ok]
        if missing:
            reasons.append(f"missing: {', '.join(missing[:2]).lower()}")
        stalled = (
            summary.progress < 0.99
            and latest is not None
            and latest > STALLED_AFTER_DAYS
        )
        if stalled:
            reasons.append(f"untouched for ~{int(latest)} days")
        ranked.append(
            {
                "project_name": summary.project_name,
                "score": round(score, 3),
                "progress": round(summary.progress, 2),
                "readiness": round(summary.health.score, 2),
                "stalled": stalled,
                "open_tasks": sum(1 for task in summary.tasks if task.status != TaskStatus.DONE),
                "reasons": reasons,
            }
        )
    ranked.sort(key=lambda item: item["score"], reverse=True)
    return ranked


def weekly_digest(
    assets: list[ProjectAsset], summaries: list[ProjectSummary]
) -> dict:
    """A one-glance state of the catalog: stalled work, wins, and gaps."""
    open_statuses = {FileStatus.IN_PROGRESS, FileStatus.NEEDS_WORK}
    stalled = []
    for asset in assets:
        if asset.status not in open_statuses:
            continue
        age = _age_days(asset.date_added)
        if age is not None and age > STALLED_AFTER_DAYS:
            stalled.append(
                {
                    "asset_id": asset.id,
                    "file_name": asset.file_name,
                    "project_name": asset.project_name,
                    "days_idle": int(age),
                    "status": asset.status.value,
                }
            )
    stalled.sort(key=lambda item: item["days_idle"], reverse=True)

    ready = [
        {"asset_id": asset.id, "file_name": asset.file_name, "project_name": asset.project_name}
        for asset in assets
        if asset.audio and asset.status == FileStatus.READY
    ]

    added = []
    for asset in assets:
        age = _age_days(asset.date_added)
        if age is not None and age <= 7:
            added.append(asset.file_name)

    projects_without_reference = [
        summary.project_name
        for summary in summaries
        if not any(
            check.ok for check in summary.health.checks if "reference" in check.label.lower()
        )
    ]

    open_tasks = sum(
        1 for summary in summaries for task in summary.tasks if task.status != TaskStatus.DONE
    )

    return {
        "stalled": stalled[:10],
        "stalled_count": len(stalled),
        "ready_to_ship": ready[:10],
        "ready_count": len(ready),
        "added_this_week": {"count": len(added), "files": added[:8]},
        "open_tasks": open_tasks,
        "projects_without_reference": projects_without_reference,
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
    }
