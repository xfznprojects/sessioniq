"""Check optional local-AI components and guide their installation.

SessionIQ ships no models. This script tells you what is missing, and with
--download it warms the local ChromaDB embedding model (~80 MB, cached in your
user profile, never in the repository).

Usage:
    python scripts/check_local_ai.py            # report only
    python scripts/check_local_ai.py --download # also fetch the embedding model
"""

from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

OLLAMA_DEFAULT = "http://localhost:11434"


def check_dotenv() -> None:
    try:
        from dotenv import load_dotenv

        load_dotenv(ROOT / ".env")
    except ModuleNotFoundError:
        print("[!] python-dotenv is not installed; .env will be ignored.")
        print("    Fix: .venv/Scripts/python -m pip install -e \".[dev]\"")


def check_vector_search(download: bool) -> None:
    print("\n== Semantic search (ChromaDB) ==")
    try:
        import chromadb  # noqa: F401
    except ModuleNotFoundError:
        print("[ ] chromadb is not installed - semantic search stays off (lexical only).")
        print("    Fix: .venv/Scripts/python -m pip install -e \".[vector]\"")
        return
    print("[x] chromadb is installed.")
    if not download:
        print("    Run with --download to fetch the embedding model now (~80 MB,")
        print("    stored in your user cache; otherwise it downloads on first search).")
        return
    print("    Warming the default embedding model (downloads on first run)...")
    try:
        from chromadb.utils.embedding_functions import DefaultEmbeddingFunction

        embedder = DefaultEmbeddingFunction()
        embedder(["warm up"])
        print("[x] Embedding model is ready.")
    except Exception as exc:  # noqa: BLE001
        print(f"[!] Could not prepare the embedding model: {exc}")
        print("    SessionIQ will fall back to lexical search until this works.")


def check_llm() -> None:
    print("\n== Answer generation ==")
    base_url = os.getenv("OPENAI_BASE_URL", "")
    model = os.getenv("SESSIONIQ_MODEL", "gpt-4.1-mini")

    if os.getenv("OPENAI_API_KEY") and not base_url:
        print(f"[x] OpenAI cloud configured (model: {model}).")
        return

    server = base_url.removesuffix("/v1") if base_url else OLLAMA_DEFAULT
    try:
        with urllib.request.urlopen(f"{server}/api/tags", timeout=3) as response:
            tags = json.load(response)
    except (urllib.error.URLError, OSError):
        print("[ ] No LLM configured - answers use the built-in rules engine.")
        print("    For free local AI answers:")
        print("      1. Install Ollama: https://ollama.com/download")
        print("      2. Pull a small model:   ollama pull llama3.2")
        print("      3. Add to .env:")
        print("           OPENAI_BASE_URL=http://localhost:11434/v1")
        print("           SESSIONIQ_MODEL=llama3.2")
        print("    Or set OPENAI_API_KEY in .env for OpenAI cloud answers.")
        return

    models = [item.get("name", "") for item in tags.get("models", [])]
    print(f"[x] Ollama server is running at {server} ({len(models)} model(s) pulled).")
    if not base_url:
        print("    Add OPENAI_BASE_URL=http://localhost:11434/v1 to .env to use it.")
    matched = any(name == model or name.split(":")[0] == model for name in models)
    if models and not matched:
        print(f"[!] Configured model '{model}' is not pulled. Available: {', '.join(models)}")
        print(f"    Fix: ollama pull {model}")
    elif not models:
        print("[!] No models pulled yet. Fix: ollama pull llama3.2")
    else:
        print(f"[x] Model '{model}' is available.")


def main() -> None:
    download = "--download" in sys.argv
    print("SessionIQ local AI check")
    print("========================")
    check_dotenv()
    check_vector_search(download)
    check_llm()
    print("\nDone. Restart the API after changing .env.")


if __name__ == "__main__":
    main()
