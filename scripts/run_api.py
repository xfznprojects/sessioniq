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
    port=int(os.environ.get("SESSIONIQ_PORT", "8000")),
)
