<div align="center">

# 🎛️ SessionIQ

### A source-grounded AI intelligence platform for music production sessions

Upload audio, MIDI, and notes — SessionIQ analyzes them, organizes them into albums and songs,
and answers questions about your work **with citations to the exact files it used.**

[![Python](https://img.shields.io/badge/Python-3.11+-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
[![React](https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black)](https://react.dev/)
[![TypeScript](https://img.shields.io/badge/TypeScript-3178C6?logo=typescript&logoColor=white)](https://www.typescriptlang.org/)
[![Tailwind CSS](https://img.shields.io/badge/Tailwind_CSS-4-38BDF8?logo=tailwindcss&logoColor=white)](https://tailwindcss.com/)
[![Tests](https://img.shields.io/badge/tests-61_passing-2ea44f)](#-testing)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

![SessionIQ dashboard](docs/sessioniq-dashboard.png)

</div>

---

## Overview

SessionIQ is **not** a DAW plugin and it does not generate music. It's a smart project notebook and
**LLM-ops-grade AI workflow**: ingestion → analysis → embeddings → vector retrieval → a grounded
assistant → validation → explainability — wrapped in a polished, keyboard-friendly dashboard.

Every answer the assistant gives is **grounded in your files** and shipped with a **Quality Report**
(confidence, hallucination risk, sources retrieved, model, prompt version, latency, token usage), so
it reads like a real production AI system, not a chat box wired to an LLM.

It runs **fully offline** out of the box — a deterministic metadata engine answers when no model is
configured, and semantic search degrades gracefully to lexical when embeddings aren't installed.

## ✨ Highlights

| | |
| --- | --- |
| 🗂️ **Albums & songs** | Nested folder tree — create an album, drop songs inside it, rename (files move on disk), drag files between projects, right-click to delete. |
| 🎚️ **Real analysis** | librosa (BPM, key, peak/RMS dB, brightness, beats) · pretty_midi (notes, pitch range, tempo) · note/task extraction. |
| 🤖 **Grounded assistant** | Answers cite the files used. Runs a **local Ollama model**, **OpenAI**, or a deterministic offline engine — automatically. |
| 🔎 **Semantic search & similarity** | Find files by meaning ("tracks that still need mastering") and compare tracks — *"Afterglow is 66% similar to Midnight Drive"* — with a per-dimension breakdown. |
| 📊 **Quality Report** | Per-answer confidence, grounding, hallucination risk, provenance (model / prompt version / temperature / latency / tokens) and a 5-point grounding checklist. |
| 🩺 **Project Health** | Completeness score + checklist (audio, notes, reference, master, tasks) + actionable suggestions. |
| 🧠 **AI Memory** | A producer "creative fingerprint" derived from your library plus editable preferences the assistant remembers across sessions. |
| 🏷️ **Custom tags** | Manual, color-coded tag pills alongside AI-suggested ones. |
| 🎨 **Design** | Token-driven design system (light/dark), tasteful motion, and category color-coding for fast scanning. |

## 🖼️ A tour

<table>
<tr>
<td width="50%"><img src="docs/insights.png" alt="Insights view" /><br/><b>Insights</b> — semantic search, the similarity engine, and creative cross-library prompts.</td>
<td width="50%"><img src="docs/pipeline.png" alt="Pipeline view" /><br/><b>Pipeline</b> — a live diagram of the real ingestion → retrieval → generation → validation path, plus the analyzer plugin registry.</td>
</tr>
<tr>
<td width="50%"><img src="docs/studio.png" alt="Studio view" /><br/><b>Studio</b> — AI Memory (creative fingerprint) and a git-like session timeline.</td>
<td width="50%" valign="top">

**Four workspaces, one docked assistant**

- **Workspace** — library, project health, file table/grid, inspector
- **Insights** — semantic search, similarity engine, creative insights
- **Studio** — AI memory, session timeline
- **Pipeline** — architecture diagram + plugin registry

The **Ask + Quality Report + Tasks** rail stays docked on the right across every view.

</td>
</tr>
</table>

## 🏗️ Architecture

```mermaid
flowchart LR
  U["Upload<br/>audio · MIDI · notes · images"] --> API["FastAPI backend"]
  API --> STORE[".sessioniq-data/<br/>album/song folders"]
  API --> INGEST["Ingestion router"]
  INGEST --> AUDIO["librosa"]
  INGEST --> MIDI["pretty_midi"]
  INGEST --> NOTES["note / task extraction"]
  AUDIO --> META["ProjectAsset metadata"]
  MIDI --> META
  NOTES --> META
  META --> EMB["Embeddings<br/>ChromaDB (optional)"]
  META --> RET["Hybrid retriever<br/>lexical + vector"]
  EMB --> RET
  RET --> AI["Grounded assistant<br/>Ollama · OpenAI · rules"]
  AI --> VAL["Validation + Quality Report"]
  META --> SIM["Similarity · Health · AI Memory"]
  VAL --> FE["React dashboard"]
  SIM --> FE
```

## 🧰 Tech stack

**Backend** — Python 3.11+, FastAPI, Uvicorn, Pydantic, librosa, numpy, soundfile, pretty_midi/mido, ChromaDB (optional), OpenAI SDK (OpenAI **or** Ollama).
**Frontend** — React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Table, Recharts, wavesurfer.js, Framer Motion, Lucide, music-metadata.
**Quality** — Pytest, Ruff, `tsc` + Vite build.

## 🚀 Quick start

**Prerequisites:** Python 3.11+ and Node 18+.

> Paths below use Windows/PowerShell. On macOS/Linux use `.venv/bin/python` instead of `.venv\Scripts\python.exe`.

**1. Backend**

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e ".[dev]"
.\.venv\Scripts\python.exe scripts\run_api.py       # → http://127.0.0.1:8000
```

**2. Frontend** (in a second terminal)

```powershell
cd web
npm install          # or: pnpm install
npm run dev          # → http://127.0.0.1:5173
```

**3. Load demo content** (optional, recommended)

```powershell
.\.venv\Scripts\python.exe scripts\seed_demo.py     # then restart the API
```

Open **http://127.0.0.1:5173** and you're in. Runtime uploads live under `.sessioniq-data/`
(git-ignored), so nothing you test becomes a repo file.

### Demo content

The repo ships **no audio**. `scripts/seed_demo.py` generates royalty-free demo content entirely in
code — synthesized WAV loops (with real, varied BPM/key), a MIDI progression, mix notes, and gradient
album artwork — organized as an album with songs plus standalone projects. Safe to showcase and
screenshot; re-runnable anytime.

### Optional: smarter AI (never shipped, always local-first)

SessionIQ works offline with a deterministic answer engine. To upgrade:

- **Local LLM (Ollama)** — install [Ollama](https://ollama.com), `ollama pull llama3.2`, then copy
  `.env.example` → `.env` and set `OPENAI_BASE_URL=http://localhost:11434/v1` and `SESSIONIQ_MODEL=llama3.2`.
- **OpenAI** — set `OPENAI_API_KEY` in `.env`.
- **Semantic vector search** — `pip install -e ".[vector]"` for local ChromaDB embeddings.

Run `.\.venv\Scripts\python.exe scripts\check_local_ai.py` to see what's active and get setup hints.
Models and vector indexes download to your machine's cache — they are **never committed**.

## 📁 Project structure

```
sessioniq/
├── src/sessioniq/          # FastAPI backend
│   ├── api.py              # endpoints (library, chat, search, similar, memory, pipeline…)
│   ├── ingestion.py        # file → ProjectAsset router
│   ├── audio_analysis.py   # librosa analysis (+ WAV fallback)
│   ├── midi_analysis.py    # pretty_midi (+ mido fallback)
│   ├── retrieval.py        # hybrid lexical + ChromaDB vector retriever
│   ├── assistant.py        # grounded answers + quality metadata (Ollama/OpenAI/rules)
│   ├── validation.py       # citation & grounding checks
│   ├── insights.py         # similarity engine + producer profile
│   ├── plugins.py          # analyzer registry
│   └── project_workspace.py# projects, smart collections, health, file ops
├── web/src/                # React + TypeScript dashboard
│   ├── App.tsx
│   └── components/         # Sidebar, Pipeline, Insights, Studio, ContextMenu, ui
├── scripts/                # run_api, run_streamlit, seed_demo, check_local_ai
└── tests/                  # pytest suite
```

## 🧪 Testing

```powershell
.\.venv\Scripts\python.exe -m pytest        # 61 passing
.\.venv\Scripts\python.exe -m ruff check .
cd web; npm run build                       # tsc + vite build
```

## 📄 License

[MIT](LICENSE) © SessionIQ contributors
