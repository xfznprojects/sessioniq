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
[![Tests](https://img.shields.io/badge/tests-132_passing-2ea44f)](#-testing)
[![Ruff](https://img.shields.io/badge/lint-ruff-261230?logo=ruff&logoColor=white)](https://docs.astral.sh/ruff/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

![SessionIQ dashboard](docs/sessioniq-dashboard.png)

</div>

---

## Your DAW makes the music. SessionIQ makes the whole operation make sense.

A great track can still disappear into a bad workflow: cryptic filenames, forgotten mix notes,
duplicate bounces, scattered TODOs, mystery tempos, and projects that are *almost finished* for
months. The bigger the catalog gets, the more creative time is lost just reconstructing context.

**SessionIQ turns that production sprawl into a searchable creative control room.** Drop in audio,
MIDI, and notes and it builds a living view of what exists, how it sounds, what still needs work,
and what to do next. Ask a question across one song or an entire catalog and get an answer backed by
the exact source files—not another confident AI guess.

### The problems it solves

| The question that slows a session down | What SessionIQ gives you |
| --- | --- |
| **“Where is the right file?”** | One organized album/song workspace with search, smart collections, tags, statuses, and files that move on disk when projects move. |
| **“What is actually finished?”** | Project Health, completion checks, automatically extracted action items, and progress tracking across every song. |
| **“What do we already have that fits?”** | Meaning-based search plus track similarity across tempo, key, brightness, loudness, and duration. |
| **“What did we decide last time?”** | Notes, session history, creative preferences, and a library-wide producer fingerprint that persist between sessions. |
| **“Can I trust this AI answer?”** | File-level citations and a Quality Report with confidence, grounding, hallucination risk, model provenance, latency, and token usage. |
| **“Can I keep sensitive work private?”** | A fully offline baseline with optional local Ollama and local vector search; cloud AI is an upgrade, not a requirement. |

### Built for the people responsible for getting music over the finish line

- **Producers and artists** get less admin, faster session recall, and a clear answer to “what should
  I finish next?”—without interrupting the creative flow to maintain a system by hand.
- **Managers, A&R, and executive producers** get a portfolio-level view of every song, open action,
  reference, master, and readiness signal—without opening every folder or chasing a status update.
- **Engineers and studios** get searchable technical facts, consistent project context, and a faster
  handoff from rough idea to mix-ready or master-ready deliverable.

### One workspace instead of five disconnected tools

SessionIQ can replace much of the day-to-day **glue work** currently split across:

- Finder / File Explorer archaeology and fragile filename conventions
- spreadsheets, Notion pages, or Trello boards used as manual production trackers
- separate BPM/key inspectors and repeated manual audio checks
- scattered text files, task lists, and “I’ll remember that” session notes
- generic AI chats that cannot show which project file supports an answer
- manual catalog audits to find unfinished, missing, related, or release-ready work

It does **not** replace your DAW, audio editor, mastering suite, rights database, or delivery service.
It makes those tools dramatically more useful by becoming the intelligent layer that connects the
files, facts, decisions, and next actions around them.

> **The result:** less time managing the work, less context lost between sessions, and more music
> moving from *promising idea* to *finished release*.

---

## Overview

SessionIQ is **not** a DAW plugin and it does not generate music. It's a smart project notebook and
**LLM-ops-grade AI workflow**: ingestion → analysis → embeddings → vector retrieval → a grounded
assistant → validation → explainability — wrapped in a polished, keyboard-friendly dashboard.

Answers cite project files and include a **Quality Report** with citation checks, numeric checks,
model provenance, latency, and token usage. These checks do not verify every claim or measure
hallucination risk; review the cited evidence for important decisions.

It runs **fully offline** out of the box — a deterministic metadata engine answers when no model is
configured, and semantic search degrades gracefully to lexical when embeddings aren't installed.

## ✨ Highlights

| | |
| --- | --- |
| 🗂️ **Albums & songs** | Nested folder tree — create an album, drop songs inside it, rename (files move on disk), drag files between projects, right-click to delete. |
| 🎚️ **Real analysis** | librosa (BPM, key + major/minor mode, peak/RMS dB, brightness, beats) · pretty_midi (notes, pitch range, tempo) · note/task extraction. |
| 🤖 **Grounded assistant** | Answers cite the files used. **Multi-turn**: ask "what about its key?" and follow-ups resolve against the previous answer. **Streams live** — interpretation, tool calls, and answer text arrive as they happen. Runs a **local Ollama model**, **OpenAI**, or a deterministic offline engine — automatically. |
| 🔧 **Tool-backed answers** | With an LLM configured, the assistant queries your metadata through tools (filter, aggregate, superlatives, similarity) so counts and comparisons are exact — even over 1000+ files. |
| 🔎 **Semantic search & similarity** | Find files by meaning ("tracks that still need mastering") and compare tracks — *"Afterglow is 66% similar to Midnight Drive"* — with a per-dimension breakdown. Tempo folds double/half-time, and key compatibility follows the circle of fifths (relative minors, fourths/fifths). |
| 📊 **Quality Report** | Per-answer confidence, grounding, hallucination risk, provenance (model / prompt version / temperature / latency / tokens / tools used) and automated citation/numeric checks with explicit limitations. Recorded decisions and note text count as grounded claims. |
| 🧾 **Query log & feedback** | Every question is logged with its quality report; thumbs up/down plus an "unanswered questions" backlog show where the library needs more (or better) sources. |
| 🩺 **Project Health** | Completeness score + checklist (audio, notes, reference, master, tasks) + actionable suggestions. |
| 🧠 **AI Memory** | A producer "creative fingerprint" derived from your library, editable preferences, and a **decision log** — record what you chose ("locked 96 BPM") and the assistant can quote it back with citations. |
| 🎤 **Voice memo transcription** | Optional local Whisper (`pip install -e ".[voice]"`) turns recordings into notes with extracted tasks. |
| 📄 **Session reports** | One-click Markdown handoff report per project (or the whole library): status, readiness, tasks, files, notes, decisions. |
| 🕵️ **Duplicate detection** | A "Possible Duplicates" smart collection flags same-length, same-tempo bounces before they multiply. |
| ⏱️ **Time-linked playback** | "Jump to loudest moment" and "play from first beat" seek the bottom player using the stored analysis series. |
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

The right rail has **Assistant / Tasks** tabs, with answer checks under an expandable section.
A persistent bottom player continues across views and remembers the last track and playback position.

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
**Frontend** — React 19, TypeScript, Vite, Tailwind CSS 4, TanStack Table, Recharts, HTML audio, Framer Motion, Lucide, music-metadata.
**Quality** — Pytest, Ruff, `tsc` + Vite build.

## 🚀 Quick start

**Prerequisites:** Python 3.11+ and Node 22.18+ (Node 24 recommended).

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
│   ├── conversation.py     # follow-up questions → standalone questions
│   ├── tools.py            # metadata query tools for agentic answers
│   ├── assistant.py        # grounded answers + quality metadata (Ollama/OpenAI/rules)
│   ├── validation.py       # citation & grounding checks
│   ├── insights.py         # similarity engine + producer profile
│   ├── transcription.py    # optional local Whisper voice-memo transcription
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
.\.venv\Scripts\python.exe -m pytest        # 132 passing
.\.venv\Scripts\python.exe -m ruff check .
cd web; npm test                            # frontend scope regressions
npm run build                               # tsc + vite build
```

## Workspace and safety update

- Smart Collections now filter the file list; project cards open the selected workspace.
  A "Possible Duplicates" collection flags same-length, same-tempo bounces that also
  share a filename token or near-identical loudness/brightness — always a hint, never
  an auto-delete.
- Files appear near the top, with compact project navigation and expandable readiness/analysis.
- The bottom player supports play/pause, seeking, volume, previous/next track, and local resume.
  Space toggles playback outside input controls; Alt+Left/Right switches tracks.
  The inspector can jump the player to the loudest moment or the first detected beat.
- The assistant keeps a conversation (persisted in the browser across reloads): follow-up
  questions ("what about its key?") are rewritten into standalone questions (LLM
  condensation when a model is configured, a deterministic file-name heuristic offline)
  before retrieval. Answers stream over server-sent events — interpretation, tool calls,
  and text arrive as they happen — and each answer shows how the follow-up was interpreted.
  "Save as decision" files an answer into the decision log.
- With an LLM configured, answers can call metadata tools (search, filter, compute
  min/max/avg/count, asset details, similarity, project list) for exact aggregate
  answers; every asset a tool touches is validated as a citable source. The offline
  rules engine is unchanged.
- Recorded decisions live in Studio → Decisions, persist with the library index, and
  are quotable by the assistant (numbers quoted from decisions and note text pass the
  grounding checks). "Export report" downloads a Markdown session report for the
  selected project or the whole library.
- Every question lands in a query log (Insights → Query Log) with its provenance and
  thumbs up/down; the "unanswered only" filter shows the backlog of questions the
  library could not ground.
- "Re-analyze" on any file re-runs analysis on the stored file while keeping its id,
  status, tags, and notes — the upgrade path for libraries analyzed before newer
  fields (key mode, richer search text) existed.
- Voice memo transcription is an optional local extra
  (`pip install -e ".[voice]"`, model via `SESSIONIQ_WHISPER_MODEL`): transcribe an
  audio file into a note asset with extracted tasks.
- Note drafts are retained in this browser. Save notes (or Ctrl/Cmd+Enter) to update the library,
  tasks, and assistant context. Drafts and player resume data are local to the browser origin.
- Completed tasks keep their status after renaming/moving projects. Existing task IDs are migrated
  in memory on load and persisted on the next successful save. Artwork does not count as reference audio.
- Saved preferences and current task statuses are supplied to the optional LLM. The offline rules
  engine uses saved task statuses, but does not personalize its wording from preferences.
- Imports are staged as a batch and committed only after every file succeeds. Audio analysis runs
  in a worker thread; each file is limited to 512 MB. A durable job queue with per-file progress,
  cancellation, and retry is not yet implemented.

### Library persistence and recovery

Run one API process per library. Writes are serialized within that process. The index is replaced
atomically and its previous version retained as `library-index.json.bak` in the data directory.
Do not run multiple API workers against the same library; this is not a multi-process database.

New upload folders include a hash of the exact project name to prevent slug/case collisions.
Existing file paths remain valid. Deletes only remove files owned by the selected assets and move
those files outside the served upload tree into `trash/<id>/`, alongside `manifest.json` containing
original paths, asset metadata, and task statuses. These recovery copies are retained indefinitely;
there is no trash-management UI yet, so disk space is not reclaimed automatically.

For recovery, stop the API, preserve the current data directory, and use the manifest to restore
files and metadata. A damaged index can be replaced with its `.bak` copy. The backup is one save
behind and must be reconciled with any files moved since that save; it is not a complete filesystem
snapshot. Ordinary failed mutations roll back in-process.

On startup the API attempts light recovery: assets whose file is missing are relinked when exactly
one unreferenced file with the same name exists under the uploads directory (typical for a process
killed between file moves and the index save). Ambiguous or absent files keep their metadata, are
flagged `file_missing` in the API and shown with a "File missing" badge in the UI, and may still
require manual recovery. Stale upload staging directories older than 24 hours are removed at
startup. These are heuristics, not a crash-atomic database: a crash mid-move can still split a
project across old and new names until you tidy it manually.

Version comparison and timestamp-linked notes remain follow-up work.

## 📄 License

[MIT](LICENSE) © SessionIQ contributors
