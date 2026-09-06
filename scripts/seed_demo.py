"""Generate SessionIQ demo content from scratch — no copyrighted material.

Everything here is synthesized in code: short WAV loops (numpy), a MIDI chord
progression (pretty_midi), mix notes, and gradient album artwork (a tiny
stdlib PNG encoder). Running this purges the local upload store and rebuilds a
tidy demo library you can showcase, screenshot, and test against.

    .\\.venv\\Scripts\\python.exe scripts\\seed_demo.py
"""

from __future__ import annotations

import json
import shutil
import struct
import sys
import zlib
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import soundfile as sf

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from sessioniq.ingestion import ingest_file  # noqa: E402
from sessioniq.models import AssetTag, FileStatus  # noqa: E402
from sessioniq.project_workspace import UPLOAD_ROOT, safe_upload_path  # noqa: E402

SR = 22_050


# --- synthesis helpers ------------------------------------------------------


def _midi_to_freq(note: int) -> float:
    return 440.0 * 2 ** ((note - 69) / 12)


def synth_wav(
    path: Path, *, seconds: float, bpm: float, root: int, brightness: float, amp: float = 0.85
) -> None:
    """A short musical loop: a triad drone + a beat pulse, so librosa has real
    tonal and rhythmic content to analyze (varied BPM / key / brightness)."""
    rng = np.random.default_rng(root * 1000 + int(bpm))
    t = np.linspace(0, seconds, int(SR * seconds), endpoint=False)

    chord = sum(np.sin(2 * np.pi * _midi_to_freq(root + interval) * t) for interval in (0, 4, 7))
    chord /= 3.0
    # Brighter tracks get more upper harmonics.
    chord += brightness * sum(
        np.sin(2 * np.pi * 2 * _midi_to_freq(root + interval) * t) for interval in (0, 4, 7)
    ) / 3.0

    beat = np.zeros_like(t)
    step = 60.0 / bpm
    burst = int(0.03 * SR)
    envelope = np.exp(-np.linspace(0, 7, burst))
    for onset in np.arange(0, seconds, step):
        start = int(onset * SR)
        end = min(start + burst, len(beat))
        beat[start:end] += rng.standard_normal(end - start) * envelope[: end - start]

    mix = 0.6 * chord + 0.5 * beat
    # Gentle fade in/out.
    fade = int(0.05 * SR)
    mix[:fade] *= np.linspace(0, 1, fade)
    mix[-fade:] *= np.linspace(1, 0, fade)
    mix /= np.max(np.abs(mix)) + 1e-9
    mix *= amp
    sf.write(path, mix.astype(np.float32), SR)


def write_midi(path: Path) -> None:
    import pretty_midi

    pm = pretty_midi.PrettyMIDI(initial_tempo=84.0)
    piano = pretty_midi.Instrument(program=0, name="Rhodes")
    # I–vi–IV–V in C, twice.
    progression = [[60, 64, 67], [57, 60, 64], [65, 69, 72], [67, 71, 74]]
    time = 0.0
    for chord in progression * 2:
        for note in chord:
            piano.notes.append(
                pretty_midi.Note(velocity=78, pitch=note, start=time, end=time + 0.9)
            )
        time += 1.0
    pm.instruments.append(piano)
    pm.write(str(path))


def write_png_gradient(path: Path, top: tuple[int, int, int], bottom: tuple[int, int, int]) -> None:
    """Minimal RGB PNG encoder (stdlib only) — a vertical gradient cover."""
    width = height = 400
    ramp = np.linspace(0, 1, height)[:, None]
    top_arr = np.array(top, dtype=np.float64)
    bottom_arr = np.array(bottom, dtype=np.float64)
    column = top_arr * (1 - ramp) + bottom_arr * ramp  # height x 3
    # subtle diagonal sheen
    sheen = (np.linspace(0, 1, width)[None, :] * 18).astype(np.float64)
    image = np.repeat(column[:, None, :], width, axis=1)
    image += sheen[:, :, None]
    image = np.clip(image, 0, 255).astype(np.uint8)

    raw = b"".join(b"\x00" + image[y].tobytes() for y in range(height))

    def chunk(tag: bytes, data: bytes) -> bytes:
        body = tag + data
        crc = zlib.crc32(body) & 0xFFFFFFFF
        return struct.pack(">I", len(data)) + body + struct.pack(">I", crc)

    signature = b"\x89PNG\r\n\x1a\n"
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0)
    idat = zlib.compress(raw, 9)
    path.write_bytes(
        signature + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    )


# --- demo library definition ------------------------------------------------

COVERS = {
    "aurora": ((37, 61, 140), (14, 20, 38)),
    "amber": ((150, 92, 34), (26, 18, 12)),
    "mint": ((28, 110, 96), (10, 24, 22)),
    "violet": ((78, 44, 130), (18, 12, 30)),
}

MIX_NOTES = """Midnight Drive - mix notes

TODO tighten the kick and sidechain the pads.
Try a wider chorus on the lead.
Reference the master loudness around -8 LUFS.
Arrangement feels good, needs a bridge.
"""

AFTERGLOW_NOTES = """Afterglow - session notes

Add a reference track before mastering.
Check the low end on headphones.
Export a final master when the vocal is in.
"""

LOFI_NOTES = """Lo-Fi Study - ideas

TODO record a dusty piano loop.
Try tape saturation on the drum bus.
Keep it under 80 BPM and warm.
"""

CLIENT_BRIEF = """Client Cue 03 - brief

Needs a 30 second bed, calm and cinematic.
Deliverable: reference mix for approval, then master.
TODO swap the synth for something softer.
"""


def build() -> None:
    now = datetime.now(UTC).isoformat()
    assets: list = []
    task_statuses: dict[str, str] = {}

    def add(project: str, name: str, generator, *, status: FileStatus | None = None) -> None:
        path = safe_upload_path(project, name)
        generator(path)
        asset = ingest_file(path, project_name=project, stored_path=str(path))
        if status is not None:
            asset.status = status
        assets.append(asset)

    # Album "Neon Horizon" with three songs.
    add(
        "Neon Horizon/Intro",
        "intro.wav",
        lambda p: synth_wav(p, seconds=6, bpm=90, root=60, brightness=0.2),
    )
    add("Neon Horizon/Intro", "cover.png", lambda p: write_png_gradient(p, *COVERS["aurora"]))

    add(
        "Neon Horizon/Midnight Drive",
        "midnight_drive.wav",
        lambda p: synth_wav(p, seconds=8, bpm=120, root=69, brightness=0.55),
        status=FileStatus.IN_PROGRESS,
    )
    drive = "Neon Horizon/Midnight Drive"
    add(drive, "mix_notes.txt", lambda p: p.write_text(MIX_NOTES))
    add(drive, "cover.png", lambda p: write_png_gradient(p, *COVERS["violet"]))

    add(
        "Neon Horizon/Afterglow",
        "afterglow.wav",
        lambda p: synth_wav(p, seconds=8, bpm=120, root=69, brightness=0.4),
    )
    add(
        "Neon Horizon/Afterglow",
        "afterglow_master.wav",
        lambda p: synth_wav(p, seconds=8, bpm=120, root=69, brightness=0.45),
    )
    # A quieter reference bounce so Mix vs reference shows real deltas.
    add(
        "Neon Horizon/Afterglow",
        "afterglow_reference.wav",
        lambda p: synth_wav(p, seconds=8, bpm=120, root=69, brightness=0.30, amp=0.4),
    )
    add("Neon Horizon/Afterglow", "notes.txt", lambda p: p.write_text(AFTERGLOW_NOTES))
    add("Neon Horizon/Afterglow", "cover.png", lambda p: write_png_gradient(p, *COVERS["amber"]))

    # Standalone lo-fi sketch with a MIDI progression.
    add(
        "Lo-Fi Study",
        "lofi_sketch.wav",
        lambda p: synth_wav(p, seconds=7, bpm=75, root=65, brightness=0.15),
    )
    add("Lo-Fi Study", "chords.mid", write_midi)
    add("Lo-Fi Study", "ideas.txt", lambda p: p.write_text(LOFI_NOTES))
    add("Lo-Fi Study", "cover.png", lambda p: write_png_gradient(p, *COVERS["mint"]))

    # Client work with a reference and a brief.
    add(
        "Client Cue 03",
        "cue_draft.wav",
        lambda p: synth_wav(p, seconds=6, bpm=100, root=62, brightness=0.3),
        status=FileStatus.NEEDS_WORK,
    )
    add(
        "Client Cue 03",
        "reference.wav",
        lambda p: synth_wav(p, seconds=6, bpm=98, root=62, brightness=0.35),
    )
    add("Client Cue 03", "brief.txt", lambda p: p.write_text(CLIENT_BRIEF))

    # A few color-coded manual tags to showcase custom tagging.
    manual_tags = {
        "midnight_drive.wav": [
            AssetTag(label="single", ai_suggested=False, color="red"),
            AssetTag(label="synthwave", ai_suggested=False, color="violet"),
        ],
        "afterglow.wav": [AssetTag(label="favorite", ai_suggested=False, color="amber")],
        "lofi_sketch.wav": [AssetTag(label="chill", ai_suggested=False, color="teal")],
    }
    for asset in assets:
        asset.date_added = now
        asset.last_analyzed = now
        extra = manual_tags.get(asset.file_name)
        if extra:
            asset.tags = list(asset.tags) + extra

    index = {
        "assets": [asset.model_dump() for asset in assets],
        "task_statuses": task_statuses,
        "project_order": [
            "Neon Horizon/Intro",
            "Neon Horizon/Midnight Drive",
            "Neon Horizon/Afterglow",
            "Lo-Fi Study",
            "Client Cue 03",
        ],
        "preferences": ["darker kicks", "Ableton", "warm pads", "lo-fi textures", "LUFS -8"],
        "decisions": [
            {
                "id": "seed-decision-1",
                "text": "Locked Midnight Drive at 120 BPM; single release, bridge cut.",
                "project_name": "Neon Horizon/Midnight Drive",
                "source_asset_id": None,
                "created_at": now,
            },
            {
                "id": "seed-decision-2",
                "text": "Client Cue 03: deliver the 30s bed before the master.",
                "project_name": "Client Cue 03",
                "source_asset_id": None,
                "created_at": now,
            },
        ],
    }
    index_path = UPLOAD_ROOT.parent / "library-index.json"
    index_path.write_text(json.dumps(index), encoding="utf-8")
    return len(assets)


def purge() -> None:
    data_dir = UPLOAD_ROOT.parent
    for target in (UPLOAD_ROOT, data_dir / "chroma", data_dir / "library-index.json"):
        if target.is_dir():
            shutil.rmtree(target, ignore_errors=True)
        elif target.exists():
            target.unlink()
    UPLOAD_ROOT.mkdir(parents=True, exist_ok=True)


if __name__ == "__main__":
    print(f"Purging {UPLOAD_ROOT.parent} ...")
    purge()
    print("Generating synthetic demo content ...")
    count = build()
    print(f"Done. Seeded {count} demo files across 5 projects (1 album, 4 tracks).")
    print("Restart the API to load the fresh demo library.")
