"""SessionIQ as a Model Context Protocol server.

Exposes the same tool layer the in-app assistant calls, so any MCP client —
Claude Desktop, Cursor, an agent of your own — can query a local SessionIQ
library.

    python scripts/run_mcp.py        # speaks MCP over stdio

Every tool delegates to :class:`~sessioniq.tools.LibraryToolbox`. A question
answered here and the same question asked inside the app are computed by
identical code, and the evaluation in ``evals/`` covers that logic.

Retrieval runs in memory rather than through ChromaDB. The MCP server is a
read-only query surface, so it should start instantly and must not need an
embedding model; the lexical and metadata blend it uses scored 0.733 hit@1
against 0.767 with vectors, which is not worth a model download here.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from sessioniq.models import ProjectAsset
from sessioniq.project_workspace import UPLOAD_ROOT, summarize_projects
from sessioniq.retrieval import InMemoryRetriever
from sessioniq.tools import LibraryToolbox

if TYPE_CHECKING:  # The SDK is an optional install; see the `mcp` extra.
    from mcp.server.mcpserver import MCPServer

LIBRARY_INDEX_NAME = "library-index.json"

KINDS = ("audio", "midi", "note", "image", "reference", "export")
STATUSES = ("Idea", "In Progress", "Needs Work", "Ready", "Reference", "Archived")
STAT_FIELDS = ("bpm", "rms_db", "duration", "brightness", "note_count")
STAT_OPS = ("min", "max", "avg", "count")


class LibraryUnavailable(RuntimeError):
    """Raised when there is no library for the server to answer from."""


def library_index_path() -> Path:
    return UPLOAD_ROOT.parent / LIBRARY_INDEX_NAME


def load_library(index_path: Path | None = None) -> tuple[list[ProjectAsset], dict[str, str]]:
    """Read the analyzed library from disk.

    The API keeps this in memory; the MCP server is a separate process that
    reads the same file at startup. It sees the library as of the moment it
    launched, which is the right trade for a query surface that should never
    block on a running app.
    """
    path = index_path or library_index_path()
    if not path.exists():
        raise LibraryUnavailable(
            f"No library found at {path}. Run the app once, or "
            "`python scripts/seed_demo.py`, to create one."
        )
    try:
        raw = json.loads(path.read_bytes())
    except (OSError, json.JSONDecodeError) as exc:
        raise LibraryUnavailable(f"Could not read {path}: {exc}") from exc

    assets: list[ProjectAsset] = []
    for item in raw.get("assets", []):
        try:
            assets.append(ProjectAsset.model_validate(item))
        except Exception:
            # One unreadable entry must not take down the whole server; the
            # app skips these on load too.
            continue

    statuses = {
        str(key): str(value) for key, value in (raw.get("task_statuses") or {}).items()
    }
    return assets, statuses


def build_toolbox(assets: list[ProjectAsset], statuses: dict[str, str]) -> LibraryToolbox:
    """Assemble the toolbox exactly as the API does, minus the vector layer."""
    summaries = summarize_projects(assets, statuses)
    tasks = [task for project in summaries for task in project.tasks]

    retriever = InMemoryRetriever()
    retriever.add_assets(assets)

    return LibraryToolbox(
        assets,
        tasks=tasks,
        search=retriever.search,
        summaries=summaries,
    )


def build_server(index_path: Path | None = None) -> MCPServer:
    """Create the MCP server, loading the library up front."""
    from mcp.server.mcpserver import MCPServer  # imported here: optional install

    assets, statuses = load_library(index_path)
    toolbox = build_toolbox(assets, statuses)

    def call(tool: str, arguments: dict[str, Any]) -> str:
        """Run a toolbox tool and return its JSON payload."""
        return toolbox.execute(tool, arguments)

    def arguments(**values: Any) -> dict[str, Any]:
        """Drop unset options so the toolbox sees only what was asked for."""
        return {key: value for key, value in values.items() if value is not None}

    server = MCPServer(
        "sessioniq",
        instructions=(
            "Query a local SessionIQ music library: analyzed audio, MIDI and session "
            "notes organized into projects. Start with list_projects to learn the "
            "project names, then filter_assets or compute_stat for exact questions "
            "and search_library for open-ended ones."
        ),
    )

    @server.tool()
    def list_projects() -> str:
        """List every project with its file counts and open task count.

        Call this first: other tools accept a project_name, and this is how you
        find the valid ones.
        """
        return call("list_projects", {})

    @server.tool()
    def search_library(query: str, project_name: str | None = None) -> str:
        """Find files by meaning across the library.

        Best for open-ended questions like "tracks that still need mastering".
        For exact conditions use filter_assets, and for numbers use compute_stat.
        """
        return call("search_library", arguments(query=query, project_name=project_name))

    @server.tool()
    def filter_assets(
        status: str | None = None,
        kind: str | None = None,
        tag: str | None = None,
        key: str | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        project_name: str | None = None,
    ) -> str:
        """List assets matching exact conditions, with the total match count.

        Arguments are combined with AND. status is one of Idea, In Progress,
        Needs Work, Ready, Reference, Archived. kind is one of audio, midi,
        note, image. tag matches any part of a tag label. key is a pitch class
        such as C or F#. The returned list may be truncated; total_matches
        always reflects every match.
        """
        return call(
            "filter_assets",
            arguments(
                status=status,
                kind=kind,
                tag=tag,
                key=key,
                bpm_min=bpm_min,
                bpm_max=bpm_max,
                project_name=project_name,
            ),
        )

    @server.tool()
    def compute_stat(
        field: str,
        op: str,
        status: str | None = None,
        kind: str | None = None,
        tag: str | None = None,
        key: str | None = None,
        bpm_min: float | None = None,
        bpm_max: float | None = None,
        project_name: str | None = None,
    ) -> str:
        """Compute an exact aggregate over the library.

        Use this for any count, average, or superlative — "how many tracks are
        in C", "which track is the loudest". min and max also return the
        winning asset. field is one of bpm, rms_db, duration, brightness,
        note_count; op is one of min, max, avg, count. Filters behave as in
        filter_assets.
        """
        return call(
            "compute_stat",
            arguments(
                field=field,
                op=op,
                status=status,
                kind=kind,
                tag=tag,
                key=key,
                bpm_min=bpm_min,
                bpm_max=bpm_max,
                project_name=project_name,
            ),
        )

    @server.tool()
    def asset_details(asset_id: str) -> str:
        """Full extracted metadata for one asset, including note text and tasks.

        Use an asset_id returned by another tool.
        """
        return call("asset_details", {"asset_id": asset_id})

    @server.tool()
    def similar_tracks(asset_id: str, limit: int = 5) -> str:
        """Tracks most similar to one asset, across tempo, key, tone and loudness."""
        return call("similar_tracks", {"asset_id": asset_id, "limit": limit})

    @server.tool()
    def next_up() -> str:
        """Rank projects by what is closest to finishable right now.

        Blends readiness, task progress and freshness, and flags
        near-finished-but-stale work as stalled. Use for "what should I
        finish next?".
        """
        return call("next_up", {})

    return server


def run(index_path: Path | None = None) -> None:
    """Serve over stdio until the client disconnects."""
    build_server(index_path).run(transport="stdio")
