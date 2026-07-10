from __future__ import annotations

from pathlib import Path

from sessioniq.models import MidiMetadata, MidiNote

NOTE_NAMES = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def note_name(note_number: int) -> str:
    octave = (note_number // 12) - 1
    return f"{NOTE_NAMES[note_number % 12]}{octave}"


def analyze_midi(path: str | Path) -> MidiMetadata:
    try:
        return _analyze_midi_pretty(path)
    except Exception:
        return _analyze_midi_mido(path)


def _analyze_midi_pretty(path: str | Path) -> MidiMetadata:
    import pretty_midi

    midi = pretty_midi.PrettyMIDI(str(path))
    notes: list[MidiNote] = []
    instrument_names: list[str] = []
    pitch_counts: dict[str, int] = {}

    for instrument in midi.instruments:
        name = instrument.name or pretty_midi.program_to_instrument_name(instrument.program)
        instrument_names.append(name)
        for note in instrument.notes:
            note_label = note_name(int(note.pitch))
            pitch_counts[note_label] = pitch_counts.get(note_label, 0) + 1
            notes.append(
                MidiNote(
                    note_number=int(note.pitch),
                    note_name=note_label,
                    velocity=int(note.velocity),
                    start_seconds=float(note.start),
                    duration_seconds=max(0.0, float(note.end - note.start)),
                    track_name=name,
                )
            )

    pitches = [note.note_number for note in notes]
    velocities = [note.velocity for note in notes]
    tempo_changes = midi.get_tempo_changes()[1]
    tempo_bpm = float(tempo_changes[0]) if len(tempo_changes) else None

    return MidiMetadata(
        duration_seconds=float(midi.get_end_time()),
        track_names=instrument_names,
        note_count=len(notes),
        notes=notes,
        tempo_bpm=tempo_bpm,
        pitch_min=min(pitches) if pitches else None,
        pitch_max=max(pitches) if pitches else None,
        velocity_min=min(velocities) if velocities else None,
        velocity_max=max(velocities) if velocities else None,
        instrument_names=instrument_names,
        pitch_distribution=pitch_counts,
        key_estimate=_estimate_midi_key(pitches),
        musical_summary=_musical_summary(instrument_names, pitches, velocities),
    )


def _analyze_midi_mido(path: str | Path) -> MidiMetadata:
    import mido

    midi = mido.MidiFile(path)
    track_names: list[str] = []
    notes: list[MidiNote] = []
    tempo_bpm: float | None = None

    for track_index, track in enumerate(midi.tracks):
        elapsed_ticks = 0
        active: dict[tuple[int, int], tuple[int, int]] = {}
        current_track_name = f"Track {track_index + 1}"
        tempos: list[tuple[int, int]] = [(0, 500_000)]

        for message in track:
            elapsed_ticks += message.time
            if message.type == "set_tempo":
                tempo_bpm = 60_000_000 / message.tempo
                tempos.append((elapsed_ticks, message.tempo))
            elif message.type == "track_name":
                current_track_name = message.name
                track_names.append(message.name)
            elif message.type == "note_on" and message.velocity > 0:
                active[(message.note, getattr(message, "channel", 0))] = (
                    elapsed_ticks,
                    message.velocity,
                )
            elif message.type in {"note_off", "note_on"}:
                key = (message.note, getattr(message, "channel", 0))
                if key in active:
                    start_ticks, velocity = active.pop(key)
                    notes.append(
                        MidiNote(
                            note_number=message.note,
                            note_name=note_name(message.note),
                            velocity=velocity,
                            start_seconds=_ticks_to_seconds(
                                start_ticks,
                                tempos,
                                midi.ticks_per_beat,
                            ),
                            duration_seconds=_ticks_to_seconds(
                                elapsed_ticks - start_ticks,
                                [(0, tempos[-1][1])],
                                midi.ticks_per_beat,
                            ),
                            track_name=current_track_name,
                        )
                    )

    duration = max((note.start_seconds + note.duration_seconds for note in notes), default=0.0)
    pitches = [note.note_number for note in notes]
    velocities = [note.velocity for note in notes]
    pitch_counts: dict[str, int] = {}
    for note in notes:
        pitch_counts[note.note_name] = pitch_counts.get(note.note_name, 0) + 1
    return MidiMetadata(
        duration_seconds=duration,
        track_names=track_names,
        note_count=len(notes),
        notes=notes,
        tempo_bpm=tempo_bpm,
        pitch_min=min(pitches) if pitches else None,
        pitch_max=max(pitches) if pitches else None,
        velocity_min=min(velocities) if velocities else None,
        velocity_max=max(velocities) if velocities else None,
        instrument_names=track_names,
        pitch_distribution=pitch_counts,
        key_estimate=_estimate_midi_key(pitches),
        musical_summary=_musical_summary(track_names, pitches, velocities),
    )


def _ticks_to_seconds(
    ticks: int,
    tempo_events: list[tuple[int, int]],
    ticks_per_beat: int,
) -> float:
    if ticks <= 0 or ticks_per_beat <= 0:
        return 0.0

    total_seconds = 0.0
    previous_tick = 0
    previous_tempo = tempo_events[0][1]

    for tick, tempo in tempo_events[1:]:
        if tick >= ticks:
            break
        total_seconds += (tick - previous_tick) * (previous_tempo / 1_000_000) / ticks_per_beat
        previous_tick = tick
        previous_tempo = tempo

    total_seconds += (ticks - previous_tick) * (previous_tempo / 1_000_000) / ticks_per_beat
    return float(total_seconds)


def _estimate_midi_key(pitches: list[int]) -> str | None:
    if not pitches:
        return None
    pitch_classes: dict[int, int] = {}
    for pitch in pitches:
        pitch_classes[pitch % 12] = pitch_classes.get(pitch % 12, 0) + 1
    root = max(pitch_classes, key=pitch_classes.get)
    return NOTE_NAMES[root]


def _musical_summary(
    instrument_names: list[str],
    pitches: list[int],
    velocities: list[int],
) -> str:
    if not pitches:
        return "No note events were detected."
    pitch_range = f"{note_name(min(pitches))}-{note_name(max(pitches))}"
    average_velocity = sum(velocities) / len(velocities) if velocities else 0
    instruments = ", ".join(instrument_names) if instrument_names else "unnamed instruments"
    return (
        f"{len(pitches)} notes across {pitch_range}, average velocity "
        f"{average_velocity:.0f}, using {instruments}."
    )
