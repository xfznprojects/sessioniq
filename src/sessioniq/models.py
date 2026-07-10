from __future__ import annotations

from enum import StrEnum
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


class AssetKind(StrEnum):
    AUDIO = "audio"
    MIDI = "midi"
    NOTE = "note"
    IMAGE = "image"
    REFERENCE = "reference"
    EXPORT = "export"


class FileStatus(StrEnum):
    IDEA = "Idea"
    IN_PROGRESS = "In Progress"
    NEEDS_WORK = "Needs Work"
    READY = "Ready"
    REFERENCE = "Reference"
    ARCHIVED = "Archived"


class AssetTag(BaseModel):
    label: str
    ai_suggested: bool = False
    # Optional pill color: one of the named palette colors (blue, green, amber,
    # red, violet, teal, neutral). None falls back to a default style.
    color: str | None = None


class Citation(BaseModel):
    file_name: str
    evidence: str


class AudioMetadata(BaseModel):
    duration_seconds: float = Field(ge=0)
    bpm_estimate: float | None = Field(default=None, ge=0)
    sample_rate: int | None = Field(default=None, ge=0)
    peak_amplitude: float | None = Field(default=None, ge=0)
    peak_db: float | None = None
    rms_amplitude: float | None = Field(default=None, ge=0)
    rms_db: float | None = None
    spectral_centroid_mean: float | None = Field(default=None, ge=0)
    energy_series: list[float] = Field(default_factory=list)
    spectral_centroid_series: list[float] = Field(default_factory=list)
    beat_positions: list[float] = Field(default_factory=list)
    codec: str | None = None
    bitrate: int | None = Field(default=None, ge=0)
    key_estimate: str | None = None


class MidiNote(BaseModel):
    note_number: int = Field(ge=0, le=127)
    note_name: str
    velocity: int = Field(ge=0, le=127)
    start_seconds: float = Field(ge=0)
    duration_seconds: float = Field(ge=0)
    track_name: str | None = None


class MidiMetadata(BaseModel):
    duration_seconds: float = Field(ge=0)
    track_names: list[str] = Field(default_factory=list)
    note_count: int = Field(ge=0)
    notes: list[MidiNote] = Field(default_factory=list)
    tempo_bpm: float | None = Field(default=None, ge=0)
    pitch_min: int | None = Field(default=None, ge=0, le=127)
    pitch_max: int | None = Field(default=None, ge=0, le=127)
    velocity_min: int | None = Field(default=None, ge=0, le=127)
    velocity_max: int | None = Field(default=None, ge=0, le=127)
    instrument_names: list[str] = Field(default_factory=list)
    pitch_distribution: dict[str, int] = Field(default_factory=dict)
    musical_summary: str = ""
    key_estimate: str | None = None


class NoteMetadata(BaseModel):
    text: str
    word_count: int = Field(ge=0)
    action_items: list[str] = Field(default_factory=list)


class TaskStatus(StrEnum):
    TODO = "To do"
    IN_PROGRESS = "In progress"
    ALMOST_DONE = "Almost done"
    DONE = "Done"


class ProjectTask(BaseModel):
    id: str
    project_name: str
    description: str
    source_file: str
    status: TaskStatus = TaskStatus.TODO


class HealthCheck(BaseModel):
    label: str
    ok: bool


class ProjectHealth(BaseModel):
    score: float = Field(ge=0, le=1)
    checks: list[HealthCheck] = Field(default_factory=list)
    suggestions: list[str] = Field(default_factory=list)


class ProjectSummary(BaseModel):
    project_name: str
    asset_count: int = Field(ge=0)
    audio_count: int = Field(ge=0)
    midi_count: int = Field(ge=0)
    note_count: int = Field(ge=0)
    tasks: list[ProjectTask] = Field(default_factory=list)
    progress: float = Field(ge=0, le=1)
    health: ProjectHealth = Field(default_factory=lambda: ProjectHealth(score=0.0))


class ProjectAsset(BaseModel):
    id: str
    file_name: str
    kind: AssetKind
    project_name: str = "Unassigned"
    stored_path: str | None = None
    status: FileStatus = FileStatus.IDEA
    tags: list[AssetTag] = Field(default_factory=list)
    date_added: str | None = None
    last_analyzed: str | None = None
    note: str = ""
    audio: AudioMetadata | None = None
    midi: MidiMetadata | None = None
    text: NoteMetadata | None = None

    @field_validator("file_name")
    @classmethod
    def file_name_only(cls, value: str) -> str:
        return Path(value).name

    @field_validator("project_name")
    @classmethod
    def normalized_project_name(cls, value: str) -> str:
        # Collapse whitespace/slashes so album/song paths stay tidy.
        segments = [segment.strip() for segment in value.split("/") if segment.strip()]
        return "/".join(segments) if segments else "Unassigned"

    def search_text(self) -> str:
        sections: list[str] = [
            f"file: {self.file_name}",
            f"type: {self.kind.value}",
            f"project: {self.project_name}",
        ]
        if self.stored_path:
            sections.append(f"stored path: {self.stored_path}")
        if self.status:
            sections.append(f"status: {self.status.value}")
        if self.tags:
            tag_text = ", ".join(tag.label for tag in self.tags)
            sections.append(f"tags: {tag_text}")
        if self.note:
            sections.append(f"user note: {self.note}")
        if self.audio:
            sections.append(
                "audio metadata: "
                f"duration={self.audio.duration_seconds:.2f}s "
                f"bpm={self.audio.bpm_estimate} "
                f"sample_rate={self.audio.sample_rate} "
                f"peak={self.audio.peak_amplitude} "
                f"peak_db={self.audio.peak_db} "
                f"rms={self.audio.rms_amplitude} "
                f"rms_db={self.audio.rms_db} "
                f"brightness={self.audio.spectral_centroid_mean}"
            )
        if self.midi:
            note_names = ", ".join(note.note_name for note in self.midi.notes[:32])
            sections.append(
                "midi metadata: "
                f"duration={self.midi.duration_seconds:.2f}s "
                f"tracks={', '.join(self.midi.track_names)} "
                f"note_count={self.midi.note_count} "
                f"tempo_bpm={self.midi.tempo_bpm} "
                f"pitch_range={self.midi.pitch_min}-{self.midi.pitch_max} "
                f"velocity_range={self.midi.velocity_min}-{self.midi.velocity_max} "
                f"instruments={', '.join(self.midi.instrument_names)} "
                f"notes={note_names}"
            )
            if self.midi.musical_summary:
                sections.append(f"midi summary: {self.midi.musical_summary}")
        if self.text:
            sections.append(f"production note text: {self.text.text}")
            if self.text.action_items:
                sections.append(f"action items: {'; '.join(self.text.action_items)}")
        return "\n".join(sections)

    def compact_metadata(self, include_series: bool = True) -> dict[str, Any]:
        data: dict[str, Any] = {
            "id": self.id,
            "file_name": self.file_name,
            "kind": self.kind.value,
            "project_name": self.project_name,
            "stored_path": self.stored_path,
            "status": self.status.value,
            "tags": [tag.model_dump() for tag in self.tags],
            "date_added": self.date_added,
            "last_analyzed": self.last_analyzed,
            "note": self.note,
        }
        if self.audio:
            series_fields = {"energy_series", "spectral_centroid_series", "beat_positions"}
            data["audio"] = self.audio.model_dump(
                exclude=None if include_series else series_fields
            )
        if self.midi:
            data["midi"] = {
                **self.midi.model_dump(exclude={"notes"}),
                "notes": [note.model_dump() for note in self.midi.notes[:32]],
            }
        if self.text:
            data["text"] = self.text.model_dump()
        return data


class RetrievedSource(BaseModel):
    asset: ProjectAsset
    score: float


class AssistantAnswer(BaseModel):
    answer: str
    citations: list[Citation] = Field(default_factory=list)
    confidence: Literal["low", "medium", "high"] = "medium"
