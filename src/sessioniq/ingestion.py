from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from sessioniq.audio_analysis import analyze_audio
from sessioniq.midi_analysis import analyze_midi
from sessioniq.models import AssetKind, AssetTag, FileStatus, ProjectAsset
from sessioniq.note_analysis import analyze_note

AudioExtensions = frozenset[str]

AUDIO_EXTENSIONS: AudioExtensions = frozenset(
    {
        ".aac",
        ".aif",
        ".aiff",
        ".flac",
        ".m4a",
        ".mp3",
        ".ogg",
        ".wav",
        ".wave",
    }
)
MIDI_EXTENSIONS = {".mid", ".midi"}
NOTE_EXTENSIONS = {".txt", ".md"}
IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp", ".gif"}


def ingest_file(
    path: str | Path,
    note: str = "",
    project_name: str = "Unassigned",
    stored_path: str | None = None,
) -> ProjectAsset:
    path = Path(path)
    suffix = path.suffix.lower()
    asset_id = f"{path.stem}-{uuid4().hex[:8]}"
    analyzed_at = datetime.now(UTC).isoformat()

    if suffix in AUDIO_EXTENSIONS:
        asset = ProjectAsset(
            id=asset_id,
            file_name=path.name,
            kind=AssetKind.AUDIO,
            project_name=project_name,
            stored_path=stored_path,
            status=_default_status(path.name),
            note=note,
            audio=analyze_audio(path),
            date_added=analyzed_at,
            last_analyzed=analyzed_at,
        )
        asset.tags = _suggest_tags(asset)
        return asset
    if suffix in MIDI_EXTENSIONS:
        asset = ProjectAsset(
            id=asset_id,
            file_name=path.name,
            kind=AssetKind.MIDI,
            project_name=project_name,
            stored_path=stored_path,
            status=_default_status(path.name),
            note=note,
            midi=analyze_midi(path),
            date_added=analyzed_at,
            last_analyzed=analyzed_at,
        )
        asset.tags = _suggest_tags(asset)
        return asset
    if suffix in NOTE_EXTENSIONS:
        asset = ProjectAsset(
            id=asset_id,
            file_name=path.name,
            kind=AssetKind.NOTE,
            project_name=project_name,
            stored_path=stored_path,
            status=_default_status(path.name),
            note=note,
            text=analyze_note(path),
            date_added=analyzed_at,
            last_analyzed=analyzed_at,
        )
        asset.tags = _suggest_tags(asset)
        return asset
    if suffix in IMAGE_EXTENSIONS:
        # Artwork / references: stored and served, but not analyzed.
        asset = ProjectAsset(
            id=asset_id,
            file_name=path.name,
            kind=AssetKind.IMAGE,
            project_name=project_name,
            stored_path=stored_path,
            status=FileStatus.REFERENCE,
            note=note,
            date_added=analyzed_at,
            last_analyzed=analyzed_at,
        )
        asset.tags = [AssetTag(label="artwork", ai_suggested=True)]
        return asset

    supported = sorted(
        AUDIO_EXTENSIONS | MIDI_EXTENSIONS | NOTE_EXTENSIONS | IMAGE_EXTENSIONS
    )
    raise ValueError(f"Unsupported file type '{suffix}'. Supported types: {', '.join(supported)}")


def supported_extensions() -> list[str]:
    return sorted(AUDIO_EXTENSIONS | MIDI_EXTENSIONS | NOTE_EXTENSIONS | IMAGE_EXTENSIONS)


def supported_upload_types() -> list[str]:
    return [extension.removeprefix(".") for extension in supported_extensions()]


def _default_status(file_name: str) -> FileStatus:
    lowered = file_name.lower()
    if "reference" in lowered or "ref" in lowered:
        return FileStatus.REFERENCE
    if "export" in lowered or "final" in lowered or "master" in lowered:
        return FileStatus.READY
    if "archive" in lowered:
        return FileStatus.ARCHIVED
    return FileStatus.IDEA


def _suggest_tags(asset: ProjectAsset) -> list[AssetTag]:
    tags: list[AssetTag] = [AssetTag(label=asset.kind.value, ai_suggested=True)]
    if asset.audio:
        if asset.audio.bpm_estimate:
            tags.append(AssetTag(label=f"{round(asset.audio.bpm_estimate)} bpm", ai_suggested=True))
        if asset.audio.key_estimate:
            tags.append(AssetTag(label=f"key {asset.audio.key_estimate}", ai_suggested=True))
        if asset.audio.spectral_centroid_mean and asset.audio.spectral_centroid_mean > 2500:
            tags.append(AssetTag(label="bright", ai_suggested=True))
    if asset.midi:
        if asset.midi.key_estimate:
            tags.append(AssetTag(label=f"key {asset.midi.key_estimate}", ai_suggested=True))
        if asset.midi.instrument_names:
            tags.append(AssetTag(label=asset.midi.instrument_names[0].lower(), ai_suggested=True))
    if asset.text and asset.text.action_items:
        tags.append(AssetTag(label="needs work", ai_suggested=True))
    return tags
