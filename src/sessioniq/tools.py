"""Structured query tools the assistant's LLM can call while answering.

Aggregate questions (counts, superlatives, filtered listings) stay exact:
instead of hoping truncated source blobs contain the answer, the model
queries the real metadata and cites the assets it found. Every asset a tool
returns is recorded in ``touched`` so citations can be validated against it.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from typing import Protocol

from sessioniq.models import FileStatus, ProjectAsset, ProjectTask

# Bounds keep one runaway tool call from flooding the model's context.
MAX_TOOL_ASSETS = 40
MAX_TOOL_RESULT_CHARS = 3500


class _SearchLike(Protocol):
    def __call__(
        self,
        query: str,
        limit: int = 4,
        project_name: str | None = None,
    ) -> list: ...


def _access_bpm(asset: ProjectAsset) -> float | None:
    if asset.audio and asset.audio.bpm_estimate:
        return asset.audio.bpm_estimate
    if asset.midi and asset.midi.tempo_bpm:
        return asset.midi.tempo_bpm
    return None


def _access_rms(asset: ProjectAsset) -> float | None:
    return asset.audio.rms_db if asset.audio else None


def _access_duration(asset: ProjectAsset) -> float | None:
    if asset.audio:
        return asset.audio.duration_seconds
    if asset.midi:
        return asset.midi.duration_seconds
    return None


def _access_brightness(asset: ProjectAsset) -> float | None:
    return asset.audio.spectral_centroid_mean if asset.audio else None


def _access_note_count(asset: ProjectAsset) -> float | None:
    return float(asset.midi.note_count) if asset.midi else None


def _access_key(asset: ProjectAsset) -> str | None:
    if asset.audio:
        return asset.audio.key_estimate
    if asset.midi:
        return asset.midi.key_estimate
    return None


FIELD_ACCESSORS: dict[str, Callable[[ProjectAsset], float | None]] = {
    "bpm": _access_bpm,
    "rms_db": _access_rms,
    "duration": _access_duration,
    "brightness": _access_brightness,
    "note_count": _access_note_count,
}


TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "search_library",
            "description": (
                "Search the library by meaning over extracted metadata and note text. "
                "Use for open-ended questions; use filter_assets for exact conditions."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Natural-language query, e.g. 'tracks that need mastering'.",
                    },
                    "project_name": {"type": "string", "description": "Limit to one project path."},
                },
                "required": ["query"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "filter_assets",
            "description": (
                "List assets matching exact metadata conditions. Returns asset summaries "
                "plus the total match count (the list may be truncated)."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "status": {
                        "type": "string",
                        "enum": [status.value for status in FileStatus],
                    },
                    "kind": {
                        "type": "string",
                        "enum": ["audio", "midi", "note", "image", "reference", "export"],
                    },
                    "tag": {"type": "string", "description": "Substring match on tag labels."},
                    "key": {"type": "string", "description": "Pitch class like 'C' or 'F#'."},
                    "bpm_min": {"type": "number"},
                    "bpm_max": {"type": "number"},
                    "project_name": {"type": "string"},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "compute_stat",
            "description": (
                "Exact aggregation over assets: min, max, avg, or count of a numeric field, "
                "optionally filtered like filter_assets. min/max include the winning asset."
            ),
            "parameters": {
                "type": "object",
                "properties": {
                    "field": {"type": "string", "enum": sorted(FIELD_ACCESSORS)},
                    "op": {"type": "string", "enum": ["min", "max", "avg", "count"]},
                    "status": {"type": "string"},
                    "kind": {"type": "string"},
                    "tag": {"type": "string"},
                    "key": {"type": "string"},
                    "bpm_min": {"type": "number"},
                    "bpm_max": {"type": "number"},
                    "project_name": {"type": "string"},
                },
                "required": ["field", "op"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "asset_details",
            "description": "Full extracted metadata for one asset, including note text and tasks.",
            "parameters": {
                "type": "object",
                "properties": {"asset_id": {"type": "string"}},
                "required": ["asset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "similar_tracks",
            "description": "Tracks most similar to one asset (tempo, key, tone, loudness).",
            "parameters": {
                "type": "object",
                "properties": {
                    "asset_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                },
                "required": ["asset_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_projects",
            "description": "All projects with file counts, task progress, and open task counts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "next_up",
            "description": (
                "Rank projects by what is closest to finishable right now "
                "(readiness, task progress, freshness). Use for 'what should I finish next?'."
            ),
            "parameters": {"type": "object", "properties": {}},
        },
    },
]


def _brief(asset: ProjectAsset) -> dict:
    return {
        "asset_id": asset.id,
        "file_name": asset.file_name,
        "kind": asset.kind.value,
        "project": asset.project_name,
        "status": asset.status.value,
        "bpm": _access_bpm(asset),
        "key": _access_key(asset),
        "duration_s": _access_duration(asset),
        "rms_db": _access_rms(asset),
    }


class LibraryToolbox:
    """Executes tool calls against a snapshot of the library."""

    def __init__(
        self,
        assets: list[ProjectAsset],
        tasks: list[ProjectTask] | None = None,
        search: _SearchLike | None = None,
        default_project: str | None = None,
        summaries: list | None = None,
    ) -> None:
        self._assets = assets
        self._tasks = tasks or []
        self._search = search
        self._default_project = default_project
        self._summaries = summaries or []
        # asset_id -> asset for everything a tool returned, so the API can
        # validate citations against tool-found sources too.
        self.touched: dict[str, ProjectAsset] = {}

    @property
    def assets(self) -> list[ProjectAsset]:
        """The library snapshot this toolbox answers from."""
        return self._assets

    def execute(self, name: str, arguments: dict) -> str:
        handlers = {
            "search_library": self._tool_search,
            "filter_assets": self._tool_filter,
            "compute_stat": self._tool_stat,
            "asset_details": self._tool_details,
            "similar_tracks": self._tool_similar,
            "list_projects": self._tool_projects,
            "next_up": self._tool_next_up,
        }
        handler = handlers.get(name)
        if handler is None:
            return json.dumps({"error": f"Unknown tool '{name}'."})
        try:
            result = handler(arguments)
        except Exception as exc:  # One bad argument must not kill the answer.
            result = {"error": f"{type(exc).__name__}: {exc}"}
        text = json.dumps(result, default=str)
        if len(text) > MAX_TOOL_RESULT_CHARS:
            text = text[:MAX_TOOL_RESULT_CHARS] + '…"}'
        return text

    # --- Filter shared by filter_assets and compute_stat -----------------

    def _matches(self, asset: ProjectAsset, args: dict) -> bool:
        project = args.get("project_name") or self._default_project
        if (
            project
            and project != "All Projects"
            and not (
                asset.project_name == project
                or asset.project_name.startswith(project.rstrip("/") + "/")
            )
        ):
            return False
        status = args.get("status")
        if status and asset.status.value.lower() != str(status).lower():
            return False
        kind = args.get("kind")
        if kind and asset.kind.value != str(kind).lower():
            return False
        tag = args.get("tag")
        if tag and not any(
            str(tag).lower() in existing.label.lower() for existing in asset.tags
        ):
            return False
        key = args.get("key")
        if key:
            asset_key = _access_key(asset)
            wanted = re.sub(r"\s+", " ", str(key).strip()).lower()
            if not asset_key or asset_key.lower() != wanted:
                return False
        bpm = _access_bpm(asset)
        bpm_min, bpm_max = args.get("bpm_min"), args.get("bpm_max")
        if (bpm_min is not None or bpm_max is not None) and bpm is None:
            return False
        if bpm_min is not None and (bpm or 0) < float(bpm_min):
            return False
        return not (bpm_max is not None and (bpm or 0) > float(bpm_max))

    # --- Tools -------------------------------------------------------------

    def _tool_search(self, args: dict) -> dict:
        if self._search is None:
            return {"error": "Search is not available."}
        query = str(args.get("query", "")).strip()
        if not query:
            return {"error": "query is required."}
        project = args.get("project_name") or self._default_project
        results = self._search(query, limit=8, project_name=project)
        for source in results:
            self.touched[source.asset.id] = source.asset
        return {
            "matches": [
                {**_brief(source.asset), "relevance": round(source.score, 3)} for source in results
            ]
        }

    def _tool_filter(self, args: dict) -> dict:
        matched = [asset for asset in self._assets if self._matches(asset, args)]
        for asset in matched[:MAX_TOOL_ASSETS]:
            self.touched[asset.id] = asset
        return {
            "total_matches": len(matched),
            "truncated": len(matched) > MAX_TOOL_ASSETS,
            "assets": [_brief(asset) for asset in matched[:MAX_TOOL_ASSETS]],
        }

    def _tool_stat(self, args: dict) -> dict:
        field = args.get("field")
        op = args.get("op")
        accessor = FIELD_ACCESSORS.get(str(field))
        if accessor is None or op not in {"min", "max", "avg", "count"}:
            return {"error": "Unknown field; op must be one of min/max/avg/count."}
        matched = [asset for asset in self._assets if self._matches(asset, args)]
        values = [(asset, accessor(asset)) for asset in matched]
        values = [(asset, value) for asset, value in values if value is not None]
        if op == "count":
            return {"field": field, "count": len(matched)}
        if not values:
            return {"field": field, "error": "No matching assets have that field."}
        if op == "avg":
            return {
                "field": field,
                "avg": round(sum(value for _, value in values) / len(values), 3),
                "count": len(values),
            }
        winner_fn = max if op == "max" else min
        winner, value = winner_fn(values, key=lambda pair: pair[1])
        self.touched[winner.id] = winner
        return {
            "field": field,
            op: round(value, 3),
            "asset": _brief(winner),
        }

    def _tool_details(self, args: dict) -> dict:
        asset_id = str(args.get("asset_id", ""))
        asset = next((item for item in self._assets if item.id == asset_id), None)
        if asset is None:
            return {"error": f"No asset with id '{asset_id}'."}
        self.touched[asset.id] = asset
        tasks = [
            {"description": task.description, "status": task.status.value}
            for task in self._tasks
            if task.asset_id == asset_id
        ]
        return {"asset": _brief(asset), "metadata": asset.search_text(), "tasks": tasks}

    def _tool_similar(self, args: dict) -> dict:
        from sessioniq.insights import similar_assets

        asset_id = str(args.get("asset_id", ""))
        target = next((item for item in self._assets if item.id == asset_id), None)
        if target is None:
            return {"error": f"No asset with id '{asset_id}'."}
        limit = min(int(args.get("limit", 5) or 5), 10)
        others = [asset for asset in self._assets if asset.id != asset_id]
        matches = similar_assets(target, others, limit=limit)
        self.touched[target.id] = target
        for match in matches:
            asset = next((item for item in self._assets if item.id == match["id"]), None)
            if asset is not None:
                self.touched[asset.id] = asset
        return {
            "target": _brief(target),
            "matches": [
                {
                    "file_name": match["file_name"],
                    "asset_id": match["id"],
                    "score": match["score"],
                    "highlights": match["highlights"],
                }
                for match in matches
            ],
        }

    def _tool_next_up(self, args: dict) -> dict:
        del args
        from sessioniq.advisor import rank_next

        if not self._summaries:
            return {"error": "Project summaries are not available."}
        ranking = rank_next(self._assets, self._summaries)
        for item in ranking[:3]:
            for asset in self._assets:
                if asset.project_name == item["project_name"]:
                    self.touched[asset.id] = asset
        return {"ranking": ranking[:5]}

    def _tool_projects(self, args: dict) -> dict:
        del args
        projects: dict[str, dict] = {}
        for asset in self._assets:
            summary = projects.setdefault(
                asset.project_name,
                {"project": asset.project_name, "files": 0, "audio": 0, "open_tasks": 0},
            )
            summary["files"] += 1
            if asset.audio:
                summary["audio"] += 1
        for task in self._tasks:
            if task.status.value != "Done" and task.project_name in projects:
                projects[task.project_name]["open_tasks"] += 1
        return {"projects": sorted(projects.values(), key=lambda item: item["project"])}
