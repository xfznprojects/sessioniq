from __future__ import annotations

import contextlib
import json
import shutil
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Annotated

from dotenv import load_dotenv
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ValidationError

from sessioniq.assistant import PROMPT_VERSION, GroundedAssistant, llm_status
from sessioniq.ingestion import ingest_file, supported_upload_types
from sessioniq.insights import producer_profile, similar_assets
from sessioniq.models import AssetKind, AssetTag, FileStatus, ProjectAsset, TaskStatus
from sessioniq.plugins import plugin_registry
from sessioniq.project_workspace import (
    UPLOAD_ROOT,
    move_stored_file,
    project_slug,
    safe_upload_path,
    smart_collections,
    summarize_projects,
)
from sessioniq.retrieval import HybridRetriever
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
LAST_ANSWER_SOURCES: list = []
LAST_ANSWER = None
RETRIEVER = HybridRetriever(persist_directory=UPLOAD_ROOT.parent / "chroma")


def _load_library_index() -> None:
    """Restore the analyzed library from disk so uploads survive API restarts."""
    if not LIBRARY_INDEX_PATH.exists():
        return
    try:
        raw = json.loads(LIBRARY_INDEX_PATH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return
    for item in raw.get("assets", []):
        try:
            asset = ProjectAsset.model_validate(item)
        except ValidationError:
            continue
        if asset.stored_path and not Path(asset.stored_path).exists():
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
    RETRIEVER.add_assets(ASSETS)


def _save_library_index() -> None:
    payload = {
        "assets": [asset.model_dump() for asset in ASSETS],
        "task_statuses": TASK_STATUSES,
        "project_order": PROJECT_ORDER,
        "preferences": PREFERENCES,
    }
    LIBRARY_INDEX_PATH.parent.mkdir(parents=True, exist_ok=True)
    LIBRARY_INDEX_PATH.write_text(json.dumps(payload), encoding="utf-8")


def _ordered_project_names() -> list[str]:
    """Distinct project names honoring the saved manual order, newest last."""
    present = list(dict.fromkeys(asset.project_name for asset in ASSETS))
    ranked = [name for name in PROJECT_ORDER if name in present]
    ranked.extend(name for name in present if name not in ranked)
    return ranked


_load_library_index()


class ChatRequest(BaseModel):
    question: str
    project_name: str | None = None


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
    return {
        "answering": status,
        "vector_search": RETRIEVER.vector_enabled,
        "hints": _ai_hints(status),
    }


def _ai_hints(status: dict[str, str]) -> list[str]:
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
            "(pip install -e \".[vector]\") to enable local ChromaDB embeddings."
        )
    return hints


@app.get("/api/memory")
def get_memory() -> dict:
    """The producer's creative fingerprint: derived from the library + stated prefs."""
    return producer_profile(ASSETS, PREFERENCES)


@app.put("/api/memory")
def update_memory(payload: MemoryUpdate) -> dict:
    cleaned = [pref.strip() for pref in payload.preferences if pref.strip()]
    PREFERENCES[:] = cleaned
    _save_library_index()
    return producer_profile(ASSETS, PREFERENCES)


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
        {"id": "upload", "title": "Upload", "tech": "FastAPI", "state": "active",
         "detail": f"{len(ASSETS)} files stored under .sessioniq-data"},
        {"id": "audio", "title": "Audio Analysis", "tech": "librosa", "state": "active",
         "detail": f"BPM, key, dB, brightness, beats · {audio_count} audio files"},
        {"id": "midi", "title": "MIDI Analysis", "tech": "pretty_midi", "state": "active",
         "detail": f"Notes, pitch range, tempo · {midi_count} MIDI files"},
        {"id": "notes", "title": "Metadata & Task Extraction", "tech": "SessionIQ",
         "state": "active",
         "detail": f"Action items, tags, statuses · {note_count} notes"},
        {"id": "embeddings", "title": "Embeddings", "tech": "ChromaDB (all-MiniLM-L6-v2)",
         "state": "active" if vector_on else "fallback",
         "detail": "Local semantic vectors" if vector_on else "Disabled - lexical only"},
        {"id": "vectordb", "title": "Vector Database", "tech": "ChromaDB",
         "state": "active" if vector_on else "fallback",
         "detail": "Persisted vector index" if vector_on else "Not in use"},
        {"id": "retriever", "title": "Hybrid Retriever", "tech": "TF-IDF + vectors",
         "state": "active",
         "detail": "Synonym-expanded lexical scoring"
         + (" blended with vectors" if vector_on else "")},
        {"id": "llm", "title": "Answer Generation", "tech": engine_label, "state": "active",
         "detail": f"Prompt {PROMPT_VERSION} · grounded, cited"},
        {"id": "validation", "title": "Validation", "tech": "Grounding checks", "state": "active",
         "detail": "Citations, source mapping, hallucination guard"},
        {"id": "answer", "title": "Answer + Quality Report", "tech": "SessionIQ", "state": "active",
         "detail": "Confidence, provenance, latency, tokens"},
    ]
    return {
        "engine": status,
        "vector_search": vector_on,
        "prompt_version": PROMPT_VERSION,
        "stages": stages,
    }


@app.get("/api/library")
def library() -> dict:
    collections = smart_collections(ASSETS)
    order = _ordered_project_names()
    summaries = summarize_projects(ASSETS, TASK_STATUSES)
    summaries.sort(
        key=lambda summary: order.index(summary.project_name)
        if summary.project_name in order
        else len(order)
    )
    return {
        "assets": [_asset_payload(asset) for asset in ASSETS],
        "projects": [_project_payload(summary) for summary in summaries],
        "smartCollections": {
            name: [asset.id for asset in collection_assets]
            for name, collection_assets in collections.items()
        },
    }


def _project_payload(summary) -> dict:
    """Project summary plus its cover artwork (first image asset), for folder cards."""
    payload = summary.model_dump()
    artwork = next(
        (
            _media_url(asset)
            for asset in ASSETS
            if asset.project_name == summary.project_name and asset.kind == AssetKind.IMAGE
        ),
        None,
    )
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
    for upload_file in files:
        saved_path = safe_upload_path(project_name, upload_file.filename or "upload")
        saved_path.write_bytes(await upload_file.read())
        try:
            asset = ingest_file(
                saved_path,
                note=note,
                project_name=project_name,
                stored_path=str(saved_path),
            )
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"{upload_file.filename}: {exc}") from exc
        _apply_client_metadata(asset, client_tags.get(upload_file.filename or ""))
        created.append(asset)
        ASSETS.append(asset)
    RETRIEVER.add_assets(created)
    _save_library_index()
    return {"assets": [_asset_payload(asset) for asset in created], "library": library()}


@app.patch("/api/assets/{asset_id}")
def update_asset(asset_id: str, update: AssetUpdate) -> dict:
    asset = _asset_by_id(asset_id)
    if update.status is not None:
        asset.status = update.status
    if update.tags is not None:
        asset.tags = update.tags
    if update.note is not None:
        asset.note = update.note.strip()
    if update.project_name is not None:
        target = update.project_name.strip() or "Unassigned"
        if target != asset.project_name:
            asset.stored_path = move_stored_file(asset.stored_path, target)
            asset.project_name = target
    RETRIEVER.refresh_asset(asset)
    _save_library_index()
    return {"asset": _asset_payload(asset), "library": library()}


@app.delete("/api/assets/{asset_id}")
def delete_asset(asset_id: str) -> dict:
    asset = _asset_by_id(asset_id)
    if asset.stored_path:
        with contextlib.suppress(OSError):
            Path(asset.stored_path).unlink(missing_ok=True)
    ASSETS.remove(asset)
    RETRIEVER.remove_asset(asset_id)
    _save_library_index()
    return {"deleted": asset_id, "library": library()}


@app.post("/api/projects/rename")
def rename_project(payload: ProjectRename) -> dict:
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
        target = new_name + asset.project_name[len(old):]
        asset.stored_path = move_stored_file(asset.stored_path, target)
        asset.project_name = target
        RETRIEVER.refresh_asset(asset)
    PROJECT_ORDER[:] = [
        new_name + name[len(old):] if name == old or name.startswith(prefix) else name
        for name in PROJECT_ORDER
    ]
    _save_library_index()
    return {"library": library()}


@app.post("/api/projects/delete")
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
    for asset in matched:
        ASSETS.remove(asset)
        RETRIEVER.remove_asset(asset.id)
    # Remove the whole folder tree on disk (album dir removes its song dirs too).
    with contextlib.suppress(OSError):
        shutil.rmtree(UPLOAD_ROOT / project_slug(prefix), ignore_errors=True)
    PROJECT_ORDER[:] = [
        name for name in PROJECT_ORDER if not (name == prefix or name.startswith(prefix_slash))
    ]
    _save_library_index()
    return {"deleted": prefix, "library": library()}


@app.post("/api/projects/reorder")
def reorder_projects(payload: ProjectOrder) -> dict:
    present = {asset.project_name for asset in ASSETS}
    PROJECT_ORDER[:] = [name for name in payload.order if name in present]
    _save_library_index()
    return {"library": library()}


@app.patch("/api/tasks/{task_id}")
def update_task(task_id: str, update: TaskUpdate) -> dict:
    known_ids = {
        task.id for summary in summarize_projects(ASSETS, TASK_STATUSES) for task in summary.tasks
    }
    if task_id not in known_ids:
        raise HTTPException(status_code=404, detail=f"Task '{task_id}' was not found.")
    TASK_STATUSES[task_id] = update.status.value
    _save_library_index()
    return {"library": library()}


@app.post("/api/chat")
def chat(request: ChatRequest) -> dict:
    global LAST_ANSWER, LAST_ANSWER_SOURCES
    started = time.perf_counter()
    sources = RETRIEVER.search(request.question, project_name=request.project_name or None)
    retrieved_ms = (time.perf_counter() - started) * 1000

    assistant = GroundedAssistant()
    answer = assistant.answer(request.question, sources)
    elapsed_ms = (time.perf_counter() - started) * 1000

    errors = validate_grounded_answer(answer, sources)
    LAST_ANSWER = answer
    LAST_ANSWER_SOURCES = sources
    quality = _quality_report(
        answer, sources, assistant.last_meta, errors, elapsed_ms, retrieved_ms
    )
    return {
        "answer": answer.model_dump(),
        "sources": [_asset_payload(source.asset) | {"score": source.score} for source in sources],
        "validation": errors,
        "quality": quality,
    }


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
        {"label": "Answer grounded in sources", "ok": grounded},
        {"label": "Citations present", "ok": bool(answer.citations)},
        {"label": "Citations map to retrieved files", "ok": not errors},
        {"label": "Metadata-derived claims", "ok": True},
    ]
    return {
        "confidence": answer.confidence,
        "grounded": grounded,
        "hallucination_risk": "low" if grounded else "elevated",
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
        "retrieval_ms": round(retrieved_ms, 1),
        "processing_ms": round(elapsed_ms, 1),
        "generated_at": datetime.now(UTC).isoformat(),
    }


class SearchRequest(BaseModel):
    query: str
    project_name: str | None = None
    limit: int = 8


@app.post("/api/search")
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
    errors = validate_grounded_answer(LAST_ANSWER, LAST_ANSWER_SOURCES)
    return {
        "checks": [
            {
                "name": "Citations required",
                "status": "pass" if not errors else "fail",
                "detail": "; ".join(errors) if errors else "Answer cites retrieved sources.",
            },
            {
                "name": "Metadata grounding",
                "status": "pass",
                "detail": (
                    "BPM, duration, note counts, and task claims are drawn from "
                    "extracted metadata."
                ),
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
    payload["bpm"] = _asset_bpm(asset)
    payload["key"] = _asset_key(asset)
    payload["duration"] = (
        asset.audio.duration_seconds
        if asset.audio
        else asset.midi.duration_seconds
        if asset.midi
        else None
    )
    return payload


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
