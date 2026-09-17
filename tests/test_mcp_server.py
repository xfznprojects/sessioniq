"""Tests for the MCP server.

The SDK is an optional extra, so the server-surface tests skip when it is not
installed. Library loading and toolbox wiring are tested regardless.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
from pathlib import Path

import pytest

from sessioniq.mcp_server import (
    LibraryUnavailable,
    build_server,
    build_toolbox,
    load_library,
)

requires_mcp = pytest.mark.skipif(
    importlib.util.find_spec("mcp") is None,
    reason="the mcp extra is not installed",
)

EXPECTED_TOOLS = {
    "list_projects",
    "search_library",
    "filter_assets",
    "compute_stat",
    "asset_details",
    "similar_tracks",
    "next_up",
}


def write_library(directory: Path, payload: dict | None = None) -> Path:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / "library-index.json"
    body = json.dumps(payload if payload is not None else SAMPLE_LIBRARY)
    path.write_text(body, encoding="utf-8")
    return path


SAMPLE_LIBRARY = {
    "assets": [
        {
            "id": "loud",
            "file_name": "loud.wav",
            "kind": "audio",
            "project_name": "Album/One",
            "status": "Ready",
            "tags": [{"label": "single", "ai_suggested": False}],
            "audio": {
                "bpm_estimate": 120.0,
                "key_estimate": "C",
                "rms_db": -9.0,
                "spectral_centroid_mean": 1200.0,
                "duration_seconds": 180.0,
            },
        },
        {
            "id": "quiet",
            "file_name": "quiet.wav",
            "kind": "audio",
            "project_name": "Album/Two",
            "status": "Idea",
            "tags": [],
            "audio": {
                "bpm_estimate": 90.0,
                "key_estimate": "A",
                "rms_db": -20.0,
                "spectral_centroid_mean": 800.0,
                "duration_seconds": 200.0,
            },
        },
    ],
    "task_statuses": {},
}


def payload_of(result) -> dict:
    return json.loads(result.content[0].text)


class TestLibraryLoading:
    def test_missing_library_is_reported_clearly(self, tmp_path):
        with pytest.raises(LibraryUnavailable) as excinfo:
            load_library(tmp_path / "nope.json")
        assert "seed_demo" in str(excinfo.value)

    def test_reads_assets_and_statuses(self, tmp_path):
        path = write_library(tmp_path, {**SAMPLE_LIBRARY, "task_statuses": {"t": "Done"}})
        assets, statuses = load_library(path)
        assert [asset.id for asset in assets] == ["loud", "quiet"]
        assert statuses == {"t": "Done"}

    def test_unreadable_entries_are_skipped_not_fatal(self, tmp_path):
        payload = {
            "assets": [SAMPLE_LIBRARY["assets"][0], {"id": "broken"}],
            "task_statuses": {},
        }
        assets, _ = load_library(write_library(tmp_path, payload))
        assert [asset.id for asset in assets] == ["loud"]

    def test_corrupt_json_is_reported_clearly(self, tmp_path):
        tmp_path.mkdir(parents=True, exist_ok=True)
        path = tmp_path / "library-index.json"
        path.write_text("{not json", encoding="utf-8")
        with pytest.raises(LibraryUnavailable):
            load_library(path)


class TestToolboxWiring:
    def test_search_is_wired_to_the_retriever(self, tmp_path):
        assets, statuses = load_library(write_library(tmp_path))
        toolbox = build_toolbox(assets, statuses)
        result = json.loads(toolbox.execute("search_library", {"query": "loud"}))
        assert [match["file_name"] for match in result["matches"]][:1] == ["loud.wav"]

    def test_summaries_are_available_to_next_up(self, tmp_path):
        assets, statuses = load_library(write_library(tmp_path))
        toolbox = build_toolbox(assets, statuses)
        result = json.loads(toolbox.execute("next_up", {}))
        assert "error" not in result, "next_up needs project summaries to be wired"


@requires_mcp
class TestServerSurface:
    def test_exposes_the_tool_layer(self, tmp_path):
        server = build_server(write_library(tmp_path))
        tools = asyncio.run(server.list_tools())
        assert {tool.name for tool in tools} == EXPECTED_TOOLS

    def test_every_tool_describes_itself(self, tmp_path):
        server = build_server(write_library(tmp_path))
        for tool in asyncio.run(server.list_tools()):
            assert tool.description, f"{tool.name} has no description for the model to read"


@requires_mcp
class TestToolDelegation:
    """The MCP layer must not reimplement anything the app already decides."""

    def test_compute_stat_returns_the_winning_asset(self, tmp_path):
        server = build_server(write_library(tmp_path))
        result = asyncio.run(
            server.call_tool("compute_stat", {"field": "rms_db", "op": "max"})
        )
        assert result.is_error is False
        assert payload_of(result)["asset"]["file_name"] == "loud.wav"

    def test_filter_assets_honours_conditions(self, tmp_path):
        server = build_server(write_library(tmp_path))
        result = asyncio.run(server.call_tool("filter_assets", {"status": "Ready"}))
        body = payload_of(result)
        assert body["total_matches"] == 1
        assert body["assets"][0]["file_name"] == "loud.wav"

    def test_list_projects_counts_files(self, tmp_path):
        server = build_server(write_library(tmp_path))
        result = asyncio.run(server.call_tool("list_projects", {}))
        projects = {item["project"]: item["files"] for item in payload_of(result)["projects"]}
        assert projects == {"Album/One": 1, "Album/Two": 1}

    def test_unknown_asset_id_is_an_error_not_a_crash(self, tmp_path):
        server = build_server(write_library(tmp_path))
        result = asyncio.run(server.call_tool("asset_details", {"asset_id": "nope"}))
        assert "error" in payload_of(result)

    def test_read_only_tools_need_no_arguments(self, tmp_path):
        server = build_server(write_library(tmp_path))
        for name in ("list_projects", "next_up"):
            assert payload_of(asyncio.run(server.call_tool(name, {})))
