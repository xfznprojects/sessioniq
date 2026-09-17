from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sessioniq.mcp_server import LibraryUnavailable, run  # noqa: E402

if __name__ == "__main__":
    # stdout carries the protocol, so anything a human needs to read goes to
    # stderr or it corrupts the stream.
    try:
        run()
    except LibraryUnavailable as exc:
        print(f"sessioniq mcp: {exc}", file=sys.stderr)
        raise SystemExit(1) from exc
    except ModuleNotFoundError as exc:
        print(
            f"sessioniq mcp: {exc}\n"
            'Install the server with:  pip install -e ".[mcp]"',
            file=sys.stderr,
        )
        raise SystemExit(1) from exc
