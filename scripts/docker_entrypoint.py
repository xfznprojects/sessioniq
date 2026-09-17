"""Container entrypoint: optionally seed demo content, then serve the API.

Seeding is opt-in through SESSIONIQ_SEED_DEMO=1 and is skipped whenever a
library index already exists, so a hosted instance with a persistent volume
generates its demo content once rather than on every restart.
"""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    if os.environ.get("SESSIONIQ_SEED_DEMO") == "1":
        subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "seed_demo.py"), "--if-empty"],
            check=True,
        )
    # Replace this process so uvicorn receives signals directly as PID 1.
    os.execv(sys.executable, [sys.executable, str(ROOT / "scripts" / "run_api.py")])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
