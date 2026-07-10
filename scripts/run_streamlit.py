from __future__ import annotations

import sys
from pathlib import Path

from streamlit.web import cli as streamlit_cli

ROOT = Path(__file__).resolve().parents[1]
APP_PATH = ROOT / "src" / "sessioniq" / "ui" / "streamlit_app.py"

sys.path.insert(0, str(ROOT / "src"))
sys.argv = [
    "streamlit",
    "run",
    str(APP_PATH),
    "--server.port",
    "8501",
    "--server.headless",
    "true",
    "--browser.gatherUsageStats",
    "false",
]

raise SystemExit(streamlit_cli.main())
