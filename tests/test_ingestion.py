from __future__ import annotations

from sessioniq.ingestion import (
    AUDIO_EXTENSIONS,
    MIDI_EXTENSIONS,
    ingest_file,
    supported_upload_types,
)
from sessioniq.models import AssetKind, AudioMetadata, MidiMetadata


def test_supported_upload_types_include_common_session_formats():
    supported = set(supported_upload_types())

    assert {"mid", "midi"} <= supported
    assert {"wav", "wave", "mp3", "flac", "aiff", "aif", "ogg", "m4a", "aac"} <= supported


def test_ingest_routes_common_audio_extensions(monkeypatch, tmp_path):
    def fake_analyze_audio(path):
        return AudioMetadata(
            duration_seconds=1,
            bpm_estimate=120,
            sample_rate=44_100,
            peak_amplitude=0.5,
            rms_amplitude=0.2,
        )

    monkeypatch.setattr("sessioniq.ingestion.analyze_audio", fake_analyze_audio)

    for extension in AUDIO_EXTENSIONS:
        path = tmp_path / f"loop{extension}"
        path.write_bytes(b"placeholder")

        asset = ingest_file(path, project_name="Vivien remix", stored_path=str(path))

        assert asset.kind == AssetKind.AUDIO
        assert asset.project_name == "Vivien remix"
        assert asset.stored_path == str(path)
        assert asset.audio is not None


def test_ingest_routes_midi_extensions(monkeypatch, tmp_path):
    def fake_analyze_midi(path):
        return MidiMetadata(duration_seconds=1, note_count=0)

    monkeypatch.setattr("sessioniq.ingestion.analyze_midi", fake_analyze_midi)

    for extension in MIDI_EXTENSIONS:
        path = tmp_path / f"riff{extension}"
        path.write_bytes(b"placeholder")

        asset = ingest_file(path)

        assert asset.kind == AssetKind.MIDI
        assert asset.midi is not None


def test_blank_project_name_is_normalized(monkeypatch, tmp_path):
    def fake_analyze_audio(path):
        return AudioMetadata(duration_seconds=1)

    monkeypatch.setattr("sessioniq.ingestion.analyze_audio", fake_analyze_audio)
    path = tmp_path / "loop.wav"
    path.write_bytes(b"placeholder")

    asset = ingest_file(path, project_name="  ")

    assert asset.project_name == "Unassigned"
