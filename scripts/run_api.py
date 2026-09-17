from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

uvicorn.run(
    "sessioniq.api:app",
    host=os.environ.get("SESSIONIQ_HOST", "127.0.0.1"),
    # Most hosts inject PORT; the container sets SESSIONIQ_PORT explicitly.
    port=int(os.environ.get("SESSIONIQ_PORT") or os.environ.get("PORT") or "8000"),
)
