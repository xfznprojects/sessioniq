from __future__ import annotations

import contextlib
import copy
import json
import logging
import os
import queue
import re
import shutil
import threading
import time
from collections import defaultdict
from datetime import UTC, datetime
from functools import wraps
from pathlib import Path
from threading import RLock
from typing import Annotated, Literal
from uuid import uuid4

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, Response, UploadFile
from fastapi.concurrency import run_in_threadpool
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, ValidationError

from sessioniq import jobs
from sessioniq.advisor import rank_next, reference_comparison, weekly_digest
from sessioniq.assistant import PROMPT_VERSION, GroundedAssistant, llm_status
from sessioniq.conversation import (
    condense_with_llm,
    deterministic_standalone,
    looks_like_followup,
)
from sessioniq.ingestion import ingest_file, supported_extensions, supported_upload_types
from sessioniq.insights import producer_profile, similar_assets
from sessioniq.models import (
    AssetKind,
    AssetTag,
    Decision,
    FileStatus,
    ProjectAsset,
    RetrievedSource,
    TaskStatus,
)
from sessioniq.persistence import atomic_write, mark_known_good, save_index
from sessioniq.plugins import plugin_registry
from sessioniq.project_workspace import (
    UPLOAD_ROOT,
    build_session_report,
    move_stored_file,
    safe_upload_path,
    smart_collections,
    summarize_projects,
)
from sessioniq.retrieval import HybridRetriever
from sessioniq.tools import LibraryToolbox
from sessioniq.transcription import transcribe_audio, transcription_status
from sessioniq.validation import validate_grounded_answer

load_dotenv()

app = FastAPI(title="SessionIQ API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=str(UPLOAD_ROOT)), name="uploads")

LIBRARY_INDEX_PATH = UPLOAD_ROOT.parent / "library-index.json"

ASSETS: list[ProjectAsset] = []
TASK_STATUSES: dict[str, str] = {}
PROJECT_ORDER: list[str] = []
PREFERENCES: list[str] = []
DECISIONS: list[Decision] = []
LAST_ANSWER_SOURCES: list = []
LAST_ANSWER_DECISIONS: list[Decision] = []
LAST_ANSWER = None
# Answer log for the LLMOps loop: every question with its quality report and
# the user's thumbs up/down. Capped in memory; JSON on disk next to the index.
QUERY_LOG: list[dict] = []
QUERY_LOG_MAX = 500
QUERY_LOG_PATH = UPLOAD_ROOT.parent / "query-log.json"
RETRIEVER = HybridRetriever(persist_directory=UPLOAD_ROOT.parent / "chroma")
STATE_LOCK = RLock()
FILE_MOVES: list[tuple[Path, Path]] = []
ASSET_UNDO: dict[str, dict] = {}
_MUTATION_ACTIVE = False  # Read and written only while holding STATE_LOCK.
STAGING_ROOT = UPLOAD_ROOT.parent / "staging"
STAGING_MAX_AGE_SECONDS = 24 * 3600
# Matches the note cap in ProjectAsset.compact_metadata; the index is storage,
# not an analysis cache, so long MIDI note lists are truncated on save.
MAX_STORED_NOTES = 32
logger = logging.getLogger(__name__)


def synchronized(function):
    @wraps(function)
    def wrapped(*args, **kwargs):
        with STATE_LOCK:
            return function(*args, **kwargs)

    return wrapped


def _asset_field_snapshot(asset: ProjectAsset) -> dict:
    """Flat snapshot of the fields endpoints may mutate in place.

    Nested analysis models (audio/midi/text) are written once at ingest and
    only swapped whole (re-analysis), so reference snapshots are enough and
    deep-copying them for every mutation — the previous whole-library
    snapshot — was pure overhead at scale.
    """
    return {
        "status": asset.status,
        "tags": list(asset.tags),
        "note": asset.note,
        "stored_path": asset.stored_path,
        "project_name": asset.project_name,
        "file_name": asset.file_name,
        "kind": asset.kind,
        "audio": asset.audio,
        "midi": asset.midi,
        "text": asset.text,
        "last_analyzed": asset.last_analyzed,
    }


def _restore_assets(original_assets: list[ProjectAsset]) -> None:
    """Undo list membership plus field changes from a failed mutation."""
    ASSETS[:] = original_assets
    for asset in original_assets:
        undo = ASSET_UNDO.get(asset.id)
        if undo:
            asset.status = undo["status"]
            asset.tags = undo["tags"]
            asset.note = undo["note"]
            asset.stored_path = undo["stored_path"]
            asset.project_name = undo["project_name"]
            asset.file_name = undo["file_name"]
            asset.kind = undo["kind"]
            asset.audio = undo["audio"]
            asset.midi = undo["midi"]
            asset.text = undo["text"]
            asset.last_analyzed = undo["last_analyzed"]


def mutation(function):
    """Serialize mutations and roll back files/state if the index cannot commit."""

    @wraps(function)
    def wrapped(*args, **kwargs):
        global _MUTATION_ACTIVE

        with STATE_LOCK:
            if _MUTATION_ACTIVE:
                # RLock permits re-entry, but nested commits would discard the
                # outer mutation's recovery journal and commit partial state.
                raise RuntimeError("Nested mutations are not supported")
            # Cheap snapshots: flat per-asset field records instead of
            # deep-copying the whole library (see _asset_field_snapshot).
            original_assets = list(ASSETS)
            ASSET_UNDO.clear()
            ASSET_UNDO.update(
                {asset.id: _asset_field_snapshot(asset) for asset in original_assets}
            )
            original_statuses = dict(TASK_STATUSES)
            original_order = list(PROJECT_ORDER)
            original_preferences = list(PREFERENCES)
            original_decisions = list(DECISIONS)
            FILE_MOVES.clear()
            _MUTATION_ACTIVE = True
            try:
                result = function(*args, **kwargs)
                _save_library_index()
                return result
            except Exception as original_error:
                try:
                    for source, destination in reversed(FILE_MOVES):
                        try:
                            if destination.exists():
                                source.parent.mkdir(parents=True, exist_ok=True)
                                destination.replace(source)
                        except OSError as rollback_error:
                            # A locked file must not block other restores or mask
                            # the original failure. Leave its bytes for recovery.
                            detail = (
                                f"Manual recovery required: could not restore "
                                f"'{destination}' to '{source}': {rollback_error}"
                            )
                            original_error.add_note(detail)
                            logger.error(detail, exc_info=True)
                finally:
                    _restore_assets(original_assets)
                    TASK_STATUSES.clear()
                    TASK_STATUSES.update(original_statuses)
                    PROJECT_ORDER[:] = original_order
                    PREFERENCES[:] = original_preferences
                    DECISIONS[:] = original_decisions
                    RETRIEVER.assets = list(ASSETS)
                    # A failed mutation may have updated optional vectors. Use lexical
                    # retrieval until restart rebuilds them from the committed index.
                    RETRIEVER._collection = None
                raise
            finally:
                FILE_MOVES.clear()
                ASSET_UNDO.clear()
                _MUTATION_ACTIVE = False

    return wrapped


def _move_asset(asset: ProjectAsset, target: str) -> None:
    original = Path(asset.stored_path) if asset.stored_path else None
    moved = move_stored_file(asset.stored_path, target)
    if original and moved and original != Path(moved) and Path(moved).exists():
        FILE_MOVES.append((original, Path(moved)))
    asset.stored_path = moved
    asset.project_name = target


def _trash_assets(assets: list[ProjectAsset]) -> None:
    """Remove only owned files; legacy projects may share a physical folder.

    Quarantine files outside the served uploads directory so failed commits can
    restore them and accidental deletes remain manually recoverable.
    """
    paths = []
    for asset in assets:
        if asset.stored_path:
            source = Path(asset.stored_path)
            try:
                source.resolve().relative_to(UPLOAD_ROOT.resolve())
            except ValueError as exc:
                raise HTTPException(400, "Stored file is outside the library.") from exc
            if any(
                other not in assets
                and other.stored_path
                and Path(other.stored_path).resolve() == source.resolve()
                for other in ASSETS
            ):
                continue
            if source.exists() and source not in paths:
                paths.append(source)
    if not paths:
        return
    trash = UPLOAD_ROOT.parent / "trash" / uuid4().hex
    trash.mkdir(parents=True)
    manifest = []
    for index, source in enumerate(paths):
        destination = trash / f"{index}-{source.name}"
        source.replace(destination)
        FILE_MOVES.append((source, destination))
        manifest.append({"original": str(source), "trashed": destination.name})
    recovery = {
        "files": manifest,
        "assets": [asset.model_dump() for asset in assets],
        "task_statuses": dict(TASK_STATUSES),
    }
    (trash / "manifest.json").write_text(json.dumps(recovery), encoding="utf-8")


def _reconcile_missing_files(assets: list[ProjectAsset], root: Path = UPLOAD_ROOT) -> int:
    """Relink assets whose file was moved by an interrupted mutation.

    A process killed between file moves and the index save leaves the index
    pointing at old paths while the bytes live in the renamed project folder
    (the trash for deletions is outside ``root`` and never reconciled). Relink
    only when exactly one unreferenced file with the same name exists under
    ``root``, so a file owned by another asset is never adopted and ambiguous
    names stay missing for manual recovery instead of guessing. The asset keeps
    its original project grouping; the next move/rename tidies the folder.
    """
    missing = [
        asset for asset in assets if asset.stored_path and not Path(asset.stored_path).exists()
    ]
    if not missing:
        return 0
    referenced = {Path(asset.stored_path).resolve() for asset in assets if asset.stored_path}
    orphans_by_name: dict[str, list[Path]] = defaultdict(list)
    for path in root.rglob("*"):
        if path.is_file() and path.resolve() not in referenced:
            orphans_by_name[path.name].append(path)
    relinked = 0
    adopted: set[Path] = set()
    for asset in missing:
        candidates = [
            candidate
            for candidate in orphans_by_name.get(Path(asset.stored_path).name, [])
            if candidate not in adopted
        ]
        if len(candidates) == 1:
            logger.warning(
                "Relinking missing file '%s' to recovered location %s",
                asset.file_name,
                candidates[0],
            )
            asset.stored_path = str(candidates[0])
            adopted.add(candidates[0])
            relinked += 1
        else:
            logger.warning("Keeping metadata for unavailable file: %s", asset.file_name)
    return relinked


def _clean_stale_staging(max_age_seconds: float = STAGING_MAX_AGE_SECONDS) -> None:
    """Remove staging directories orphaned by dead uploads.

    Age-gated so a concurrently running API process mid-upload (the app is
    single-process by design, but a second instance may be pointed at the same
    data) is never disrupted; anything recent is left alone.
    """
    if not STAGING_ROOT.exists():
        return
    cutoff = time.time() - max_age_seconds
    for directory in STAGING_ROOT.iterdir():
        try:
            if directory.is_dir() and directory.stat().st_mtime < cutoff:
                shutil.rmtree(directory)
        except OSError:
            logger.warning("Could not remove stale staging directory: %s", directory)


def _load_library_index() -> None:
    """Restore the analyzed library from disk so uploads survive API restarts."""
    if not LIBRARY_INDEX_PATH.exists():
        return
    raw_bytes = LIBRARY_INDEX_PATH.read_bytes()
    try:
        raw = json.loads(raw_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(
            "Cannot read library-index.json. Restore library-index.json.bak before restarting."
        ) from exc
    mark_known_good(LIBRARY_INDEX_PATH, raw_bytes)
    for item in raw.get("assets", []):
        try:
            asset = ProjectAsset.model_validate(item)
        except ValidationError:
            continue
        ASSETS.append(asset)
    statuses = raw.get("task_statuses", {})
    if isinstance(statuses, dict):
        TASK_STATUSES.update({str(key): str(value) for key, value in statuses.items()})
    order = raw.get("project_order", [])
    if isinstance(order, list):
        PROJECT_ORDER.extend(str(name) for name in order)
    prefs = raw.get("preferences", [])
    if isinstance(prefs, list):
        PREFERENCES.extend(str(pref) for pref in prefs)
    decisions = raw.get("decisions", [])
    if isinstance(decisions, list):
        for item in decisions:
            try:
                DECISIONS.append(Decision.model_validate(item))
            except ValidationError:
                continue
    _reconcile_missing_files(ASSETS)
    summarize_projects(ASSETS, TASK_STATUSES)  # Migrate legacy task IDs before names change.
    RETRIEVER.add_assets(ASSETS)


def _save_library_index() -> None:
    payload = {
        "assets": [_storable_asset(asset) for asset in ASSETS],
        "task_statuses": TASK_STATUSES,
        "project_order": PROJECT_ORDER,
        "preferences": PREFERENCES,
        "decisions": [decision.model_dump() for decision in DECISIONS],
    }
    save_index(LIBRARY_INDEX_PATH, payload)


def _load_query_log() -> None:
    """Restore the answer log so feedback survives restarts."""
    if not QUERY_LOG_PATH.exists():
        return
    try:
        raw = json.loads(QUERY_LOG_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        logger.warning("Could not read query-log.json; starting a fresh log.")
        return
    if isinstance(raw, list):
        QUERY_LOG.extend(entry for entry in raw if isinstance(entry, dict))


def _save_query_log() -> None:
    try:
        atomic_write(
            QUERY_LOG_PATH,
            json.dumps(QUERY_LOG, default=str).encode("utf-8"),
        )
    except OSError:
        logger.warning("Could not persist the query log.", exc_info=True)


def _log_query(request: ChatRequest, answer, quality: dict, payload: dict) -> str:
    """Record one answered question; returns the id used for feedback."""
    entry = {
        "id": uuid4().hex[:12],
        "ts": datetime.now(UTC).isoformat(timespec="seconds"),
        "question": request.question,
        "project_name": request.project_name,
        "standalone_question": payload.get("standalone_question"),
        "rewrite_method": payload.get("rewrite_method"),
        "engine": quality.get("engine"),
        "mode": quality.get("mode"),
        "model": quality.get("model"),
        "prompt_version": quality.get("prompt_version"),
        "confidence": quality.get("confidence"),
        "grounded": quality.get("grounded"),
        "sources_retrieved": quality.get("sources_retrieved"),
        "files_cited": quality.get("files_cited"),
        "tool_calls": quality.get("tool_calls"),
        "processing_ms": quality.get("processing_ms"),
        "retrieval_ms": quality.get("retrieval_ms"),
        "feedback": None,
    }
    with STATE_LOCK:
        QUERY_LOG.append(entry)
        del QUERY_LOG[:-QUERY_LOG_MAX]
        _save_query_log()
    return entry["id"]


def _query_stats() -> dict:
    unanswered = [
        entry
        for entry in QUERY_LOG
        if not entry.get("sources_retrieved")
        or (entry.get("confidence") == "low" and not entry.get("files_cited"))
    ]
    return {
        "total": len(QUERY_LOG),
        "unanswered": len(unanswered),
        "feedback_up": sum(1 for entry in QUERY_LOG if entry.get("feedback") == "up"),
        "feedback_down": sum(1 for entry in QUERY_LOG if entry.get("feedback") == "down"),
    }


def _storable_asset(asset: ProjectAsset) -> dict:
    payload = asset.model_dump()
    midi = payload.get("midi")
    if midi and len(midi.get("notes", [])) > MAX_STORED_NOTES:
        midi["notes"] = midi["notes"][:MAX_STORED_NOTES]
    return payload


def _ordered_project_names() -> list[str]:
    """Distinct project names honoring the saved manual order, newest last."""
    present = list(dict.fromkeys(asset.project_name for asset in ASSETS))
    ranked = [name for name in PROJECT_ORDER if name in present]
    ranked.extend(name for name in present if name not in ranked)
    return ranked


_load_library_index()
_load_query_log()
_clean_stale_staging()


class ChatTurn(BaseModel):
    role: Literal["user", "assistant"]
    content: str


class ChatRequest(BaseModel):
    question: str
    project_name: str | None = None
    # Recent turns so follow-ups ("what about its key?") can be resolved.
    history: list[ChatTurn] = Field(default_factory=list, max_length=40)


MAX_CHAT_HISTORY = 12


_TRANSCRIBABLE_SUFFIXES = frozenset(
    {".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".aiff", ".aif"}
)


class DecisionCreate(BaseModel):
    text: str
    project_name: str = "Unassigned"
    source_asset_id: str | None = None


class AssetUpdate(BaseModel):
    status: FileStatus | None = None
    tags: list[AssetTag] | None = None
    project_name: str | None = None
    note: str | None = None


class ProjectRename(BaseModel):
    old_name: str
    new_name: str


class ProjectOrder(BaseModel):
    order: list[str]


class ProjectDelete(BaseModel):
    name: str


class TaskUpdate(BaseModel):
    status: TaskStatus


class MemoryUpdate(BaseModel):
    preferences: list[str]


@app.get("/api/health")
def health() -> dict[str, str]:
    return {"status": "ok", "upload_root": str(UPLOAD_ROOT)}


@app.get("/api/supported-types")
def supported_types() -> dict[str, list[str]]:
    return {"types": supported_upload_types()}


@app.get("/api/ai-status")
def ai_status() -> dict:
    """Report which optional AI components are active, so the UI can tell the
    user what to install for smarter answers (models are never shipped)."""
    status = llm_status()
    transcription = transcription_status()
    return {
        "answering": status,
        "vector_search": RETRIEVER.vector_enabled,
        "transcription": transcription,
        "hints": _ai_hints(status, transcription),
    }


def _ai_hints(status: dict[str, str], transcription: dict) -> list[str]:
    hints: list[str] = []
    if status["mode"] == "rules":
        hints.append(
            "Answers use the built-in rules engine. For AI answers, install Ollama "
            "(https://ollama.com), run 'ollama pull llama3.2', and set OPENAI_BASE_URL="
            "http://localhost:11434/v1 and SESSIONIQ_MODEL=llama3.2 in .env - or set "
            "OPENAI_API_KEY for OpenAI."
        )
    if not RETRIEVER.vector_enabled:
        hints.append(
            "Semantic search is off. Install the vector extra "
            '(pip install -e ".[vector]") to enable local ChromaDB embeddings.'
        )
    if not transcription.get("available") and transcription.get("hint"):
        hints.append(transcription["hint"])
    return hints


@app.get("/api/memory")
@synchronized
def get_memory() -> dict:
    """The producer's creative fingerprint: derived from the library + stated prefs."""
    return producer_profile(ASSETS, PREFERENCES)


@app.put("/api/memory")
@mutation
def update_memory(payload: MemoryUpdate) -> dict:
    cleaned = [pref.strip() for pref in payload.preferences if pref.strip()]
    PREFERENCES[:] = cleaned
    return producer_profile(ASSETS, PREFERENCES)


@app.get("/api/decisions")
@synchronized
def list_decisions(project: str | None = None) -> dict:
    """Recorded producer decisions, newest first, optionally scoped to a project."""
    decisions = sorted(DECISIONS, key=lambda item: item.created_at, reverse=True)
    if project and project != "All Projects":
        prefix = project.rstrip("/") + "/"
        decisions = [
            item
            for item in decisions
            if item.project_name == project or item.project_name.startswith(prefix)
        ]
    return {"decisions": [decision.model_dump() for decision in decisions]}


@app.post("/api/decisions")
@mutation
def add_decision(payload: DecisionCreate) -> dict:
    text = payload.text.strip()
    if not text:
        raise HTTPException(status_code=422, detail="Decision text cannot be empty.")
    if payload.source_asset_id:
        _asset_by_id(payload.source_asset_id)  # Reject dangling anchors.
    decision = Decision(
        id=uuid4().hex,
        text=text,
        project_name=payload.project_name.strip() or "Unassigned",
        source_asset_id=payload.source_asset_id,
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
    )
    DECISIONS.append(decision)
    return {"decision": decision.model_dump(), "library": library()}


@app.delete("/api/decisions/{decision_id}")
@mutation
def delete_decision(decision_id: str) -> dict:
    decision = next((item for item in DECISIONS if item.id == decision_id), None)
    if decision is None:
        raise HTTPException(status_code=404, detail=f"Decision '{decision_id}' was not found.")
    DECISIONS.remove(decision)
    return {"deleted": decision_id, "library": library()}


@app.get("/api/projects/report")
@synchronized
def project_report(project: str = "All Projects") -> Response:
    """Markdown session report for one project (or the whole library)."""
    scope = project.strip() or "All Projects"
    markdown = build_session_report(
        scope,
        ASSETS,
        summarize_projects(ASSETS, TASK_STATUSES),
        DECISIONS,
    )
    filename = "sessioniq-library-report.md" if scope == "All Projects" else (
        "sessioniq-report-" + re.sub(r"[^a-zA-Z0-9_-]+", "-", scope).strip("-") + ".md"
    )
    return Response(
        content=markdown,
        media_type="text/markdown; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@app.post("/api/assets/{asset_id}/transcribe")
async def transcribe_asset(asset_id: str) -> dict:
    """Transcribe an audio voice memo into a note asset using local Whisper.

    Synchronous for short memos; for anything long, start a job via
    /api/jobs/transcribe instead so the request does not wait minutes.
    """
    asset = _transcribable_asset(asset_id)
    status = transcription_status()
    if not status.get("available"):
        hint = status.get("hint", "Transcription is unavailable.")
        raise HTTPException(status_code=409, detail=hint)
    text = await run_in_threadpool(transcribe_audio, asset.stored_path)
    if not text:
        raise HTTPException(status_code=422, detail="No speech was detected in this file.")
    return await run_in_threadpool(_commit_transcript, asset, text)


def _transcribable_asset(asset_id: str) -> ProjectAsset:
    with STATE_LOCK:
        asset = _asset_by_id(asset_id)
        if not asset.audio or not asset.stored_path or not Path(asset.stored_path).exists():
            raise HTTPException(
                status_code=400,
                detail="Transcription needs an audio file that is present on disk.",
            )
        if Path(asset.file_name).suffix.lower() not in _TRANSCRIBABLE_SUFFIXES:
            raise HTTPException(status_code=400, detail="This file type cannot be transcribed.")
        return asset


@mutation
def _commit_transcript(source_asset: ProjectAsset, text: str) -> dict:
    stem = Path(source_asset.file_name).stem
    target = safe_upload_path(source_asset.project_name, f"{stem}-transcript.txt")
    target.write_text(text, encoding="utf-8")
    note_asset = ingest_file(
        target,
        note=f"Voice memo transcript of {source_asset.file_name}",
        project_name=source_asset.project_name,
        stored_path=str(target),
    )
    ASSETS.append(note_asset)
    RETRIEVER.add_assets([note_asset])
    return {"asset": _asset_payload(note_asset), "library": library()}


@app.get("/api/plugins")
def plugins() -> dict:
    return plugin_registry(RETRIEVER.vector_enabled)


@app.get("/api/pipeline")
def pipeline() -> dict:
    """The live ingestion + retrieval + answer pipeline, for the architecture view."""
    status = llm_status()
    vector_on = RETRIEVER.vector_enabled
    audio_count = sum(1 for asset in ASSETS if asset.audio)
    midi_count = sum(1 for asset in ASSETS if asset.midi)
    note_count = sum(1 for asset in ASSETS if asset.text)
    engine_label = {
        "rules": "Deterministic engine",
        "local-llm": f"Local LLM · {status['model']}",
        "openai": f"OpenAI · {status['model']}",
    }[status["mode"]]

    stages = [
        {
            "id": "upload",
            "title": "Upload",
            "tech": "FastAPI",
            "state": "active",
            "detail": f"{len(ASSETS)} files stored under .sessioniq-data",
        },
        {
            "id": "audio",
            "title": "Audio Analysis",
            "tech": "librosa",
            "state": "active",
            "detail": f"BPM, key, dB, brightness, beats · {audio_count} audio files",
        },
        {
            "id": "midi",
            "title": "MIDI Analysis",
            "tech": "pretty_midi",
            "state": "active",
            "detail": f"Notes, pitch range, tempo · {midi_count} MIDI files",
        },
        {
            "id": "notes",
            "title": "Metadata & Task Extraction",
            "tech": "SessionIQ",
            "state": "active",
            "detail": f"Action items, tags, statuses · {note_count} notes",
        },
        {
            "id": "embeddings",
            "title": "Embeddings",
            "tech": "ChromaDB (all-MiniLM-L6-v2)",
            "state": "active" if vector_on else "fallback",
            "detail": "Local semantic vectors" if vector_on else "Disabled - lexical only",
        },
        {
            "id": "vectordb",
            "title": "Vector Database",
            "tech": "ChromaDB",
            "state": "active" if vector_on else "fallback",
            "detail": "Persisted vector index" if vector_on else "Not in use",
        },
        {
            "id": "retriever",
            "title": "Hybrid Retriever",
            "tech": "TF-IDF + vectors",
            "state": "active",
            "detail": "Synonym-expanded lexical scoring"
            + (" blended with vectors" if vector_on else ""),
        },
        {
            "id": "llm",
            "title": "Answer Generation",
            "tech": engine_label,
            "state": "active",
            "detail": f"Prompt {PROMPT_VERSION} · grounded, cited",
        },
        {
            "id": "validation",
            "title": "Validation",
            "tech": "Grounding checks",
            "state": "active",
            "detail": "Citations, source mapping, hallucination guard",
        },
        {
            "id": "answer",
            "title": "Answer + Quality Report",
            "tech": "SessionIQ",
            "state": "active",
            "detail": "Confidence, provenance, latency, tokens",
        },
    ]
    return {
        "engine": status,
        "vector_search": vector_on,
        "prompt_version": PROMPT_VERSION,
        "stages": stages,
    }


@app.get("/api/library")
@synchronized
def library() -> dict:
    collections = smart_collections(ASSETS)
    order = _ordered_project_names()
    # One pass for every project's cover artwork instead of rescanning all
    # assets per project summary.
    artwork_by_project: dict[str, str | None] = {}
    for asset in ASSETS:
        if asset.kind == AssetKind.IMAGE and asset.project_name not in artwork_by_project:
            artwork_by_project[asset.project_name] = _media_url(asset)
    summaries = summarize_projects(ASSETS, TASK_STATUSES)
    summaries.sort(
        key=lambda summary: (
            order.index(summary.project_name) if summary.project_name in order else len(order)
        )
    )
    return {
        "assets": [_asset_payload(asset) for asset in ASSETS],
        "projects": [
            _project_payload(summary, artwork_by_project.get(summary.project_name))
            for summary in summaries
        ],
        "smartCollections": {
            name: [asset.id for asset in collection_assets]
            for name, collection_assets in collections.items()
        },
    }


def _project_payload(summary, artwork: str | None = None) -> dict:
    """Project summary plus its cover artwork (first image asset), for folder cards."""
    payload = summary.model_dump()
    payload["artwork"] = artwork
    return payload


@app.post("/api/upload")
async def upload(
    files: Annotated[list[UploadFile], File()],
    project_name: Annotated[str, Form()] = "Unassigned",
    note: Annotated[str, Form()] = "",
    client_metadata: Annotated[str, Form()] = "[]",
) -> dict:
    created: list[ProjectAsset] = []
    client_tags = _client_metadata_by_name(client_metadata)
    staging = UPLOAD_ROOT.parent / "staging" / uuid4().hex
    staging.mkdir(parents=True)
    try:
        for upload_file in files:
            filename = (upload_file.filename or "upload").replace("\\", "/")
            if Path(filename).suffix.lower() not in supported_extensions():
                raise HTTPException(400, f"Unsupported file type: {filename}")
            saved_path = safe_upload_path(project_name, filename, root=staging)
            size = 0
            with saved_path.open("wb") as destination:
                while chunk := await upload_file.read(1024 * 1024):
                    size += len(chunk)
                    if size > 512 * 1024 * 1024:
                        raise HTTPException(413, "Each file must be 512 MB or smaller.")
                    destination.write(chunk)
            try:
                asset = await run_in_threadpool(
                    ingest_file,
                    saved_path,
                    note=note,
                    project_name=project_name,
                    stored_path=str(saved_path),
                )
            except Exception as exc:
                raise HTTPException(400, f"{filename}: {exc}") from exc
            _apply_client_metadata(asset, client_tags.get(upload_file.filename or ""))
            created.append(asset)
        return await run_in_threadpool(_commit_upload, created)
    finally:
        # This directory is generated for this request, never a user project.
        for path in sorted(staging.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        staging.rmdir()


@mutation
def _commit_upload(created: list[ProjectAsset]) -> dict:
    for asset in created:
        original = Path(asset.stored_path)
        target = safe_upload_path(asset.project_name, asset.file_name)
        original.replace(target)
        FILE_MOVES.append((original, target))
        asset.stored_path = str(target)
        asset.file_name = target.name
        ASSETS.append(asset)
    RETRIEVER.add_assets(created)
    return {"assets": [_asset_payload(asset) for asset in created], "library": library()}


@app.patch("/api/assets/{asset_id}")
@mutation
def update_asset(asset_id: str, update: AssetUpdate) -> dict:
    asset = _asset_by_id(asset_id)
    summarize_projects(ASSETS, TASK_STATUSES)
    if update.status is not None:
        asset.status = update.status
    if update.tags is not None:
        asset.tags = update.tags
    if update.note is not None:
        asset.note = update.note.strip()
    if update.project_name is not None:
        target = update.project_name.strip() or "Unassigned"
        if target != asset.project_name:
            _move_asset(asset, target)
    RETRIEVER.refresh_asset(asset)
    return {"asset": _asset_payload(asset), "library": library()}


@app.delete("/api/assets/{asset_id}")
@mutation
def delete_asset(asset_id: str) -> dict:
    asset = _asset_by_id(asset_id)
    _trash_assets([asset])
    ASSETS.remove(asset)
    RETRIEVER.remove_asset(asset_id)
    return {"deleted": asset_id, "library": library()}


@app.post("/api/projects/rename")
@mutation
def rename_project(payload: ProjectRename) -> dict:
    summarize_projects(ASSETS, TASK_STATUSES)
    old = payload.old_name.strip("/")
    new_name = payload.new_name.strip().strip("/") or "Unassigned"
    prefix = old + "/"
    # Prefix-aware: renaming an album folder renames every song path under it.
    matched = [
        asset
        for asset in ASSETS
        if asset.project_name == old or asset.project_name.startswith(prefix)
    ]
    if not matched:
        raise HTTPException(status_code=404, detail=f"Project '{payload.old_name}' was not found.")
    for asset in matched:
        target = new_name + asset.project_name[len(old) :]
        _move_asset(asset, target)
        RETRIEVER.refresh_asset(asset)
    PROJECT_ORDER[:] = [
        new_name + name[len(old) :] if name == old or name.startswith(prefix) else name
        for name in PROJECT_ORDER
    ]
    return {"library": library()}


@app.post("/api/projects/delete")
@mutation
def delete_project(payload: ProjectDelete) -> dict:
    """Delete a project/album and everything under it (all songs + files)."""
    prefix = payload.name.strip().strip("/")
    prefix_slash = prefix + "/"
    matched = [
        asset
        for asset in ASSETS
        if asset.project_name == prefix or asset.project_name.startswith(prefix_slash)
    ]
    if not matched:
        raise HTTPException(status_code=404, detail=f"Project '{payload.name}' was not found.")
    _trash_assets(matched)
    for asset in matched:
        ASSETS.remove(asset)
        RETRIEVER.remove_asset(asset.id)
    PROJECT_ORDER[:] = [
        name for name in PROJECT_ORDER if not (name == prefix or name.startswith(prefix_slash))
    ]
    return {"deleted": prefix, "library": library()}


@app.post("/api/projects/reorder")
@mutation
def reorder_projects(payload: ProjectOrder) -> dict:
    present = {asset.project_name for asset in ASSETS}
    PROJECT_ORDER[:] = [name for name in payload.order if name in present]
    return {"library": library()}


@app.patch("/api/tasks/{task_id}")
@mutation
def update_task(task_id: str, update: TaskUpdate) -> dict:
    known_ids = {
        task.id for summary in summarize_projects(ASSETS, TASK_STATUSES) for task in summary.tasks
    }
    if task_id not in known_ids:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' was not found.")
    TASK_STATUSES[task_id] = update.status.value
    return {"library": library()}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    global LAST_ANSWER, LAST_ANSWER_SOURCES, LAST_ANSWER_DECISIONS
    started = time.perf_counter()
    prepared = _prepare_chat(request)
    answer = prepared["assistant"].answer(
        request.question, prepared["sources"], history=prepared["history"]
    )
    payload = _finalize_chat(request, prepared, answer, started)
    LAST_ANSWER = answer
    LAST_ANSWER_SOURCES = payload["_all_sources"]
    LAST_ANSWER_DECISIONS = prepared["decisions"]
    return {key: value for key, value in payload.items() if not key.startswith("_")}


def _prepare_chat(request: ChatRequest) -> dict:
    """Shared chat prelude: history, follow-up rewriting, retrieval, toolbox.

    LLM condensation runs before the state lock so a slow model never blocks
    every other endpoint; snapshots and retrieval run inside it.
    """
    history = [turn.model_dump() for turn in request.history[-MAX_CHAT_HISTORY:]]
    llm_on = bool(os.getenv("OPENAI_API_KEY") or os.getenv("OPENAI_BASE_URL"))
    standalone, rewrite_method = request.question, None
    assets_snapshot: list[ProjectAsset] | None = None

    # The offline heuristic is free and resolves most follow-ups (they quote a
    # file the previous answer mentioned); the LLM condense round trip only
    # runs when it cannot — one fewer model call on the common path.
    if looks_like_followup(request.question, bool(history)):
        with STATE_LOCK:
            assets_snapshot = list(ASSETS)
        heuristic = deterministic_standalone(request.question, history, assets_snapshot)
        if heuristic != request.question:
            standalone, rewrite_method = heuristic, "heuristic"
        elif llm_on:
            try:
                standalone = condense_with_llm(
                    request.question,
                    history,
                    os.getenv("SESSIONIQ_MODEL", "gpt-4.1-mini"),
                )
                rewrite_method = "llm"
            except Exception:
                logger.warning("LLM condensation failed.", exc_info=True)

    with STATE_LOCK:
        if assets_snapshot is None:
            assets_snapshot = list(ASSETS)
        sources = copy.deepcopy(
            RETRIEVER.search(standalone, project_name=request.project_name or None)
        )
        preferences = list(PREFERENCES)
        decisions = list(DECISIONS)
        summaries = summarize_projects(ASSETS, TASK_STATUSES)
        tasks = [task for project in summaries for task in project.tasks]

    toolbox = LibraryToolbox(
        assets_snapshot,
        tasks=tasks,
        search=RETRIEVER.search,
        default_project=request.project_name or None,
        summaries=summaries,
    )
    assistant = GroundedAssistant(
        preferences=preferences,
        tasks=tasks,
        toolbox=toolbox,
        decisions=decisions,
        summaries=summaries,
    )
    return {
        "history": history,
        "standalone": standalone,
        "rewrite_method": rewrite_method,
        "sources": sources,
        "decisions": decisions,
        "toolbox": toolbox,
        "assistant": assistant,
        "retrieved_ms": time.perf_counter(),
        "_summaries": summaries,
    }


def _finalize_chat(request: ChatRequest, prepared: dict, answer, started: float) -> dict:
    """Build the response payload shared by the plain and streaming endpoints."""
    assistant = prepared["assistant"]
    toolbox = prepared["toolbox"]
    elapsed_ms = (time.perf_counter() - started) * 1000
    retrieved_ms = (prepared.pop("retrieved_ms", started) - started) * 1000

    # Assets surfaced by tool calls count as sources: validation and the UI
    # treat them exactly like retrieved ones.
    retrieved_ids = {source.asset.id for source in prepared["sources"]}
    tool_sources = [
        RetrievedSource(asset=asset, score=0.0)
        for asset in toolbox.touched.values()
        if asset.id not in retrieved_ids
    ]
    all_sources = prepared["sources"] + tool_sources

    errors = validate_grounded_answer(answer, all_sources, decisions=prepared["decisions"])
    quality = _quality_report(
        answer, all_sources, assistant.last_meta, errors, elapsed_ms, retrieved_ms
    )
    source_payloads = [
        _asset_payload(source.asset) | {"score": round(source.score, 4), "via": "retrieval"}
        for source in prepared["sources"]
    ] + [
        _asset_payload(source.asset) | {"score": 0.0, "via": "tool"} for source in tool_sources
    ]
    payload = {
        "answer": answer.model_dump(),
        "sources": source_payloads,
        "validation": errors,
        "quality": quality,
        "standalone_question": (
            prepared["standalone"] if prepared["standalone"] != request.question else None
        ),
        "rewrite_method": prepared["rewrite_method"],
        "_all_sources": all_sources,
    }
    payload["query_id"] = _log_query(request, answer, quality, payload)
    return payload


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


@app.post("/api/chat/stream")
def chat_stream(request: ChatRequest):
    """Server-sent-events chat: interpretation, tool progress, and answer text
    stream as they happen; the final event carries the same validated payload
    as /api/chat (whose text supersedes anything streamed)."""
    return StreamingResponse(
        _chat_sse_events(request),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


def _chat_sse_events(request: ChatRequest):
    started = time.perf_counter()
    events: queue.Queue = queue.Queue()
    done = object()

    def run() -> None:
        try:
            prepared = _prepare_chat(request)
            events.put(
                (
                    "meta",
                    {
                        "standalone_question": (
                            prepared["standalone"]
                            if prepared["standalone"] != request.question
                            else None
                        ),
                        "rewrite_method": prepared["rewrite_method"],
                    },
                )
            )
            streamed_any = False

            def on_event(kind: str, data: dict) -> None:
                nonlocal streamed_any
                if kind == "delta":
                    streamed_any = True
                events.put((kind, data))

            answer = prepared["assistant"].answer(
                request.question, prepared["sources"], history=prepared["history"],
                on_event=on_event,
            )
            payload = _finalize_chat(request, prepared, answer, started)
            global LAST_ANSWER, LAST_ANSWER_SOURCES, LAST_ANSWER_DECISIONS
            LAST_ANSWER = answer
            LAST_ANSWER_SOURCES = payload["_all_sources"]
            LAST_ANSWER_DECISIONS = prepared["decisions"]
            # Engines that do not stream (rules, single-shot fallback) still
            # deliver the full text as one delta so the UI behaves uniformly.
            if not streamed_any and answer.answer:
                events.put(("delta", {"text": answer.answer}))
            events.put(("done", {k: v for k, v in payload.items() if not k.startswith("_")}))
        except Exception as exc:
            logger.warning("Streaming chat failed.", exc_info=True)
            events.put(("error", {"detail": str(exc) or "The answer stream failed."}))
        finally:
            events.put((done, None))

    threading.Thread(target=run, daemon=True).start()
    while True:
        kind, data = events.get()
        if kind is done:
            break
        yield _sse(kind, data)


@app.get("/api/queries")
@synchronized
def list_queries(limit: int = 50, unanswered: bool = False) -> dict:
    """Recent answered questions with their quality reports, plus totals.

    ``unanswered`` filters to questions the library could not ground — the
    backlog that shows what to upload, note down, or fix in retrieval.
    """
    entries = list(reversed(QUERY_LOG))
    if unanswered:
        entries = [
            entry
            for entry in entries
            if not entry.get("sources_retrieved")
            or (entry.get("confidence") == "low" and not entry.get("files_cited"))
        ]
    return {"entries": entries[: max(0, limit)], "stats": _query_stats()}


class FeedbackUpdate(BaseModel):
    feedback: Literal["up", "down"] | None = None


@app.post("/api/queries/{query_id}/feedback")
@synchronized
def update_query_feedback(query_id: str, update: FeedbackUpdate) -> dict:
    entry = next((item for item in QUERY_LOG if item.get("id") == query_id), None)
    if entry is None:
        raise HTTPException(status_code=404, detail=f"Query '{query_id}' was not found.")
    entry["feedback"] = update.feedback
    _save_query_log()
    return {"query_id": query_id, "feedback": update.feedback, "stats": _query_stats()}


@app.post("/api/assets/{asset_id}/reanalyze")
async def reanalyze_asset(asset_id: str) -> dict:
    """Re-run analysis on the stored file, keeping id, status, tags, and notes.

    Upgrades libraries analyzed before newer fields existed (key mode, richer
    search text) one file at a time — a full-library batch belongs to the
    future job queue.
    """
    with STATE_LOCK:
        asset = _asset_by_id(asset_id)
        if not asset.stored_path or not Path(asset.stored_path).exists():
            raise HTTPException(400, "Re-analysis needs the stored file on disk.")
        if Path(asset.file_name).suffix.lower() not in supported_extensions():
            raise HTTPException(400, "This file type cannot be analyzed.")
    fresh = await run_in_threadpool(
        ingest_file,
        asset.stored_path,
        note=asset.note,
        project_name=asset.project_name,
        stored_path=asset.stored_path,
    )
    return await run_in_threadpool(_commit_reanalysis, asset_id, fresh)


@mutation
def _commit_reanalysis(asset_id: str, fresh: ProjectAsset) -> dict:
    asset = _asset_by_id(asset_id)
    # Analysis output is swapped in; user-curated fields (status, tags, note,
    # dates, id) survive untouched so re-analyzing never reorganizes anything.
    asset.audio = fresh.audio
    asset.midi = fresh.midi
    asset.text = fresh.text
    asset.kind = fresh.kind
    asset.last_analyzed = fresh.last_analyzed
    RETRIEVER.refresh_asset(asset)
    return {"asset": _asset_payload(asset), "library": library()}


def _quality_report(
    answer,
    sources: list,
    meta: dict,
    errors: list[str],
    elapsed_ms: float,
    retrieved_ms: float,
) -> dict:
    """LLMOps-style report: grounding, provenance, and cost for one answer."""
    cited_files = {citation.file_name for citation in answer.citations}
    grounded = bool(answer.citations) and not errors
    checks = [
        {"label": "Sources found", "ok": bool(sources)},
        {"label": "Automated citation checks passed", "ok": grounded},
        {"label": "Citations present", "ok": bool(answer.citations)},
        {"label": "Citations map to retrieved files", "ok": not errors},
    ]
    return {
        "confidence": answer.confidence,
        "grounded": grounded,
        "hallucination_risk": "not assessed" if grounded else "elevated",
        "limitation": (
            "Citation and numeric checks do not verify every claim or measure hallucination risk."
        ),
        "sources_retrieved": len(sources),
        "files_cited": len(cited_files),
        "checks": checks,
        "engine": meta.get("engine"),
        "mode": meta.get("mode"),
        "model": meta.get("model"),
        "prompt_version": meta.get("prompt_version"),
        "temperature": meta.get("temperature"),
        "knowledge_source": meta.get("knowledge_source"),
        "token_usage": meta.get("token_usage"),
        "tool_calls": meta.get("tool_calls") or None,
        "retrieval_ms": round(retrieved_ms, 1),
        "processing_ms": round(elapsed_ms, 1),
        "generated_at": datetime.now(UTC).isoformat(),
    }


class SearchRequest(BaseModel):
    query: str
    project_name: str | None = None
    limit: int = 8


@app.post("/api/search")
@synchronized
def semantic_search(request: SearchRequest) -> dict:
    """Meaning-based file search: the hybrid retriever ranks by content, not filename."""
    results = RETRIEVER.search(
        request.query,
        limit=request.limit,
        project_name=request.project_name or None,
    )
    return {
        "query": request.query,
        "results": [
            _asset_payload(source.asset) | {"score": round(source.score, 4)} for source in results
        ],
    }


@app.get("/api/assets/{asset_id}/similar")
def similar(asset_id: str) -> dict:
    target = _asset_by_id(asset_id)
    others = [asset for asset in ASSETS if asset.id != asset_id]
    matches = similar_assets(target, others, limit=6)
    return {
        "target": _asset_payload(target),
        "matches": [
            match | {"asset": _asset_payload(_asset_by_id(match["id"]))} for match in matches
        ],
    }


@app.get("/api/reference")
@synchronized
def reference_comparison_endpoint(project: str) -> dict:
    """Mix-vs-reference deltas for one project (needs a Reference-status audio file)."""
    scope = project.strip()
    if scope == "All Projects":
        raise HTTPException(400, "Pick a specific project to compare against its reference.")
    comparison = reference_comparison(ASSETS, scope)
    if comparison is None:
        return {"reference": None, "comparisons": []}
    return comparison


@app.get("/api/next-up")
@synchronized
def next_up() -> dict:
    """Projects ranked by how finishable they are right now."""
    summaries = summarize_projects(ASSETS, TASK_STATUSES)
    return {"ranking": rank_next(list(ASSETS), summaries)}


@app.get("/api/digest")
@synchronized
def digest() -> dict:
    """A one-glance state of the catalog: stalled work, wins, and gaps."""
    summaries = summarize_projects(ASSETS, TASK_STATUSES)
    return weekly_digest(list(ASSETS), summaries)


class LibraryScan(BaseModel):
    path: str
    project_name: str | None = None
    note: str = ""


MAX_SCAN_FILES = 500
MAX_FILE_BYTES = 512 * 1024 * 1024


@app.post("/api/library/scan")
async def scan_folder(payload: LibraryScan) -> dict:
    """Import every supported file under a folder (recursively, copied not moved).

    The folder stays untouched on disk; files land in the library exactly like
    uploads. Bounded by file count and per-file size so one wrong path cannot
    swallow a drive."""
    root = Path(payload.path).expanduser()
    if not root.is_dir():
        raise HTTPException(400, f"'{payload.path}' is not a folder.")
    files = sorted(
        candidate
        for candidate in root.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in supported_extensions()
    )
    if not files:
        raise HTTPException(400, "No supported audio, MIDI, note, or image files in that folder.")
    if len(files) > MAX_SCAN_FILES:
        raise HTTPException(
            400,
            f"{len(files)} supported files exceeds the {MAX_SCAN_FILES}-file scan limit; "
            "import in smaller folders.",
        )
    project = (payload.project_name or "").strip() or root.name
    staging = UPLOAD_ROOT.parent / "staging" / uuid4().hex
    staging.mkdir(parents=True)
    created: list[ProjectAsset] = []
    try:
        for source in files:
            if source.stat().st_size > MAX_FILE_BYTES:
                raise HTTPException(413, f"{source.name} is over the 512 MB per-file limit.")
            saved = safe_upload_path(project, source.name, root=staging)
            shutil.copy2(source, saved)
            asset = await run_in_threadpool(
                ingest_file,
                saved,
                note=payload.note,
                project_name=project,
                stored_path=str(saved),
            )
            created.append(asset)
        return await run_in_threadpool(_commit_upload, created)
    finally:
        for path in sorted(staging.rglob("*"), key=lambda p: len(p.parts), reverse=True):
            if path.is_file():
                path.unlink(missing_ok=True)
            elif path.is_dir():
                path.rmdir()
        with contextlib.suppress(OSError):
            staging.rmdir()


@app.get("/api/jobs")
def list_jobs() -> dict:
    return {"jobs": jobs.list_jobs()}


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict:
    job = jobs.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail=f"Job '{job_id}' was not found.")
    return job


@app.post("/api/jobs/{job_id}/cancel")
def cancel_job(job_id: str) -> dict:
    if not jobs.request_cancel(job_id):
        raise HTTPException(status_code=409, detail="Job is not running.")
    return {"job_id": job_id, "cancel_requested": True}


class TranscribeJobRequest(BaseModel):
    asset_id: str


@app.post("/api/jobs/transcribe")
def start_transcribe_job(request: TranscribeJobRequest) -> dict:
    """Transcribe a voice memo in the background; poll /api/jobs/{id}."""
    asset = _transcribable_asset(request.asset_id)
    status = transcription_status()
    if not status.get("available"):
        hint = status.get("hint", "Transcription is unavailable.")
        raise HTTPException(status_code=409, detail=hint)

    def runner(job_id: str) -> dict:
        jobs.check_cancel(job_id)
        text = transcribe_audio(asset.stored_path)
        if not text:
            raise RuntimeError("No speech was detected in this file.")
        jobs.check_cancel(job_id)
        return _commit_transcript(asset, text)

    job = jobs.run_job(
        "transcribe",
        f"Transcribing {asset.file_name}",
        runner,
        total=1,
    )
    return {"job_id": job["id"], "job": job}


class ReanalyzeJobRequest(BaseModel):
    scope: str = "all"  # "all" or a project path prefix


@app.post("/api/jobs/reanalyze")
def start_reanalyze_job(request: ReanalyzeJobRequest) -> dict:
    """Re-run analysis across the library (or one project) in the background.

    The upgrade path for libraries analyzed before newer fields existed
    (key mode, LUFS, richer search text). Analysis runs without holding the
    state lock; results commit in one atomic index save at the end.
    """
    scope = request.scope.strip() or "all"
    with STATE_LOCK:
        targets = [
            asset
            for asset in ASSETS
            if asset.stored_path
            and Path(asset.stored_path).exists()
            and Path(asset.file_name).suffix.lower() in supported_extensions()
            and (
                scope == "all"
                or asset.project_name == scope
                or asset.project_name.startswith(scope + "/")
            )
        ]
        snapshot = [
            (asset.id, asset.stored_path, asset.note, asset.project_name, asset.last_analyzed)
            for asset in targets
        ]
    if not snapshot:
        raise HTTPException(status_code=400, detail="Nothing to re-analyze in that scope.")

    def runner(job_id: str) -> dict:
        results = []
        for index, entry in enumerate(snapshot, start=1):
            asset_id, stored_path, note, project, expected_analyzed = entry
            jobs.check_cancel(job_id)
            fresh = ingest_file(
                stored_path,
                note=note,
                project_name=project,
                stored_path=stored_path,
            )
            results.append((asset_id, expected_analyzed, fresh))
            jobs.set_progress(job_id, index, len(snapshot))
        return _commit_batch_reanalysis(results)

    job = jobs.run_job(
        "reanalyze",
        f"Re-analyzing {len(snapshot)} file(s)" + (f" in {scope}" if scope != "all" else ""),
        runner,
        total=len(snapshot),
    )
    return {"job_id": job["id"], "job": job}


@mutation
def _commit_batch_reanalysis(results: list) -> dict:
    updated = 0
    for asset_id, expected_analyzed, fresh in results:
        asset = next((item for item in ASSETS if item.id == asset_id), None)
        # Skip assets deleted or individually re-analyzed while the job ran.
        if asset is None or asset.last_analyzed != expected_analyzed:
            continue
        asset.audio = fresh.audio
        asset.midi = fresh.midi
        asset.text = fresh.text
        asset.kind = fresh.kind
        asset.last_analyzed = fresh.last_analyzed
        RETRIEVER.refresh_asset(asset)
        updated += 1
    return {"updated": updated, "considered": len(results)}


@app.get("/api/validation")
def validation() -> dict:
    if LAST_ANSWER is None:
        return {
            "checks": [
                {
                    "name": "No answer yet",
                    "status": "pending",
                    "detail": "Ask a question to run grounding validation.",
                }
            ]
        }
    errors = validate_grounded_answer(LAST_ANSWER, LAST_ANSWER_SOURCES, LAST_ANSWER_DECISIONS)
    return {
        "checks": [
            {
                "name": "Citations required",
                "status": "pass" if not errors else "fail",
                "detail": "; ".join(errors) if errors else "Answer cites retrieved sources.",
            },
            {
                "name": "Claim verification",
                "status": "pending",
                "detail": "Automated checks cannot verify every claim. Review the cited sources.",
            },
        ]
    }


def _asset_by_id(asset_id: str) -> ProjectAsset:
    for asset in ASSETS:
        if asset.id == asset_id:
            return asset
    raise HTTPException(status_code=404, detail=f"Asset '{asset_id}' was not found.")


def _client_metadata_by_name(raw_metadata: str) -> dict[str, dict]:
    try:
        parsed = json.loads(raw_metadata)
    except json.JSONDecodeError:
        return {}
    if not isinstance(parsed, list):
        return {}
    return {
        item.get("fileName"): item
        for item in parsed
        if isinstance(item, dict) and isinstance(item.get("fileName"), str)
    }


def _apply_client_metadata(asset: ProjectAsset, metadata: dict | None) -> None:
    if not metadata or not asset.audio:
        return
    asset.audio.codec = metadata.get("codec") or asset.audio.codec
    asset.audio.bitrate = metadata.get("bitrate") or asset.audio.bitrate
    asset.audio.sample_rate = metadata.get("sampleRate") or asset.audio.sample_rate
    asset.audio.duration_seconds = metadata.get("duration") or asset.audio.duration_seconds
    for field in ("title", "artist", "album"):
        value = metadata.get(field)
        if value:
            asset.tags.append(AssetTag(label=str(value), ai_suggested=True))


def _asset_payload(asset: ProjectAsset) -> dict:
    payload = asset.compact_metadata()
    payload["media_url"] = _media_url(asset)
    payload["display_type"] = _display_type(asset)
    payload["file_missing"] = bool(asset.stored_path and not Path(asset.stored_path).exists())
    payload["bpm"] = _asset_bpm(asset)
    payload["key"] = _asset_key(asset)
    payload["mode"] = asset.audio.mode_estimate if asset.audio else None
    payload["duration"] = (
        asset.audio.duration_seconds
        if asset.audio
        else asset.midi.duration_seconds
        if asset.midi
        else None
    )
    payload["energy_peak_seconds"] = _energy_peak_seconds(asset)
    payload["first_beat_seconds"] = (
        asset.audio.beat_positions[0] if asset.audio and asset.audio.beat_positions else None
    )
    return payload


def _energy_peak_seconds(asset: ProjectAsset) -> float | None:
    """Time of the loudest moment, derived from the stored energy series.

    The series is downsampled to ~96 points, so this is section-level ("the
    drop around 1:32"), not sample-exact — good enough to jump the player to.
    """
    if not asset.audio or not asset.audio.energy_series or not asset.audio.duration_seconds:
        return None
    series = asset.audio.energy_series
    if len(series) < 2:
        return None
    peak_index = max(range(len(series)), key=lambda index: series[index])
    return round(peak_index / (len(series) - 1) * asset.audio.duration_seconds, 1)


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


def _media_url(asset: ProjectAsset) -> str | None:
    if not asset.stored_path:
        return None
    try:
        relative = Path(asset.stored_path).resolve().relative_to(UPLOAD_ROOT.resolve())
    except ValueError:
        return None
    return f"/uploads/{relative.as_posix()}"


def _display_type(asset: ProjectAsset) -> str:
    if asset.audio:
        return "Audio"
    if asset.midi:
        return "MIDI"
    if asset.text:
        return "Notes"
    if asset.kind == AssetKind.IMAGE:
        return "Image"
    return asset.kind.value.title()
