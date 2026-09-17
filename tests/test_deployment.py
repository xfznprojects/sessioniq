"""Tests for the configuration that makes a hosted deployment work."""

from __future__ import annotations

from sessioniq.api import _dashboard_directory


class TestDashboardDirectory:
    def test_uses_the_configured_directory_when_it_holds_a_build(self, tmp_path, monkeypatch):
        (tmp_path / "index.html").write_text("<!doctype html>", encoding="utf-8")
        monkeypatch.setenv("SESSIONIQ_STATIC_DIR", str(tmp_path))
        assert _dashboard_directory() == tmp_path

    def test_ignores_a_configured_directory_without_a_build(self, tmp_path, monkeypatch):
        # An empty directory must not be mounted: serving it would turn every
        # path into a 404 and hide the API's own error responses.
        monkeypatch.setenv("SESSIONIQ_STATIC_DIR", str(tmp_path))
        assert _dashboard_directory() != tmp_path
