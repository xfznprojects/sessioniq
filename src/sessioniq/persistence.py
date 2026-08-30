"""Atomic index replacement. Never truncate the only copy of a library."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path

# Content this process already parsed or wrote successfully, so the next save
# can skip re-verifying it. Keyed by resolved destination path.
_KNOWN_GOOD: dict[Path, bytes] = {}


def atomic_write(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, name = tempfile.mkstemp(prefix=f".{path.name}-", dir=path.parent)
    temporary = Path(name)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def mark_known_good(path: Path, content: bytes) -> None:
    """Register content that was already parsed successfully (startup load)."""
    _KNOWN_GOOD[path.resolve()] = content


def save_index(path: Path, payload: dict) -> None:
    content = json.dumps(payload, allow_nan=False, separators=(",", ":")).encode("utf-8")
    if path.exists():
        previous = path.read_bytes()
        if previous != _KNOWN_GOOD.get(path.resolve()):
            json.loads(previous)  # Externally modified: verify before trusting the backup.
        atomic_write(path.with_suffix(".json.bak"), previous)
    atomic_write(path, content)
    mark_known_good(path, content)
