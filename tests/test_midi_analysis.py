from __future__ import annotations

import pytest

from sessioniq.midi_analysis import analyze_midi, note_name


def test_note_name_uses_scientific_pitch_notation():
    assert note_name(60) == "C4"
    assert note_name(61) == "C#4"


def test_analyze_midi_notes_tracks_and_tempo(tmp_path):
    mido = pytest.importorskip("mido")
    path = tmp_path / "riff.mid"
    midi = mido.MidiFile(ticks_per_beat=480)
    track = mido.MidiTrack()
    midi.tracks.append(track)
    track.append(mido.MetaMessage("track_name", name="Lead", time=0))
    track.append(mido.MetaMessage("set_tempo", tempo=mido.bpm2tempo(120), time=0))
    track.append(mido.Message("note_on", note=60, velocity=90, time=0))
    track.append(mido.Message("note_off", note=60, velocity=0, time=480))
    midi.save(path)

    metadata = analyze_midi(path)

    assert metadata.track_names == ["Lead"]
    assert metadata.tempo_bpm == 120
    assert metadata.note_count == 1
    assert metadata.notes[0].note_name == "C4"
    assert metadata.notes[0].velocity == 90
    assert metadata.duration_seconds == 0.5
