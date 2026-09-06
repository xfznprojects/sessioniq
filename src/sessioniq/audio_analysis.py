from __future__ import annotations

import warnings
from pathlib import Path
from wave import open as wave_open

import numpy as np

from sessioniq.models import AudioMetadata

WAV_EXTENSIONS = {".wav", ".wave"}


class AudioAnalysisError(RuntimeError):
    """Raised when an audio file cannot be decoded for analysis."""


def analyze_audio(path: str | Path) -> AudioMetadata:
    """Analyze an audio file, preferring librosa and falling back to WAV metadata."""
    path = Path(path)
    try:
        import librosa
    except ModuleNotFoundError as exc:
        if path.suffix.lower() in WAV_EXTENSIONS:
            return _analyze_wav_fallback(path)
        raise AudioAnalysisError(
            "Audio analysis for compressed formats requires librosa. "
            "Install the project runtime dependencies, then restart SessionIQ."
        ) from exc

    try:
        y, sr = librosa.load(path, sr=None, mono=True)
        duration = float(librosa.get_duration(y=y, sr=sr))
        bpm = _estimate_bpm(librosa, y, sr)
        peak = float(np.max(np.abs(y))) if y.size else 0.0
        rms = float(np.sqrt(np.mean(np.square(y)))) if y.size else 0.0
        energy_series = _energy_series(librosa, y)
        centroid_series = _spectral_centroid_series(librosa, y, sr)
        beats = _beat_positions(librosa, y, sr)
        key = _estimate_key(librosa, y, sr)
        mode = _estimate_mode(librosa, y, sr, key)
        return AudioMetadata(
            duration_seconds=duration,
            bpm_estimate=bpm,
            sample_rate=int(sr),
            peak_amplitude=peak,
            peak_db=_amp_to_db(peak),
            rms_amplitude=rms,
            rms_db=_amp_to_db(rms),
            spectral_centroid_mean=float(np.mean(centroid_series)) if centroid_series else None,
            energy_series=energy_series,
            spectral_centroid_series=centroid_series,
            beat_positions=beats,
            codec=path.suffix.lower().removeprefix(".").upper() or None,
            key_estimate=key,
            mode_estimate=mode,
        )
    except Exception as exc:
        if path.suffix.lower() in WAV_EXTENSIONS:
            try:
                return _analyze_wav_fallback(path)
            except Exception:
                pass
        raise AudioAnalysisError(
            f"Could not decode '{path.name}'. SessionIQ supports WAV, MP3, FLAC, AIFF, "
            "AIF, OGG, M4A, and AAC when the local audio decoder stack can read them."
        ) from exc


def _analyze_wav_fallback(path: Path) -> AudioMetadata:
    with wave_open(str(path), "rb") as wav:
        sample_rate = wav.getframerate()
        frames = wav.getnframes()
        duration = frames / float(sample_rate) if sample_rate else 0.0
        sample_width = wav.getsampwidth()
        channels = wav.getnchannels()
        raw = wav.readframes(frames)

    if sample_width == 1:
        samples = np.frombuffer(raw, dtype=np.uint8).astype(np.float32)
        normalized = (samples - 128.0) / 128.0
    elif sample_width == 2:
        samples = np.frombuffer(raw, dtype=np.int16).astype(np.float32)
        normalized = samples / float(np.iinfo(np.int16).max)
    elif sample_width == 4:
        samples = np.frombuffer(raw, dtype=np.int32).astype(np.float32)
        normalized = samples / float(np.iinfo(np.int32).max)
    else:
        normalized = np.array([], dtype=np.float32)

    if channels > 1 and normalized.size:
        normalized = normalized.reshape(-1, channels).mean(axis=1)

    peak = float(np.max(np.abs(normalized))) if normalized.size else 0.0
    rms = float(np.sqrt(np.mean(np.square(normalized)))) if normalized.size else 0.0

    return AudioMetadata(
        duration_seconds=float(duration),
        bpm_estimate=None,
        sample_rate=sample_rate,
        peak_amplitude=peak,
        peak_db=_amp_to_db(peak),
        rms_amplitude=rms,
        rms_db=_amp_to_db(rms),
        energy_series=_downsample(normalized.tolist(), limit=96),
        codec="WAV",
    )


def _estimate_bpm(librosa_module, samples: np.ndarray, sample_rate: int) -> float | None:
    if not samples.size:
        return None
    if float(np.max(np.abs(samples))) < 1e-6:
        return None
    try:
        tempo_function = _tempo_function(librosa_module)
        if tempo_function is None:
            return None
        with warnings.catch_warnings():
            warnings.simplefilter("ignore", FutureWarning)
            tempo = tempo_function(y=samples, sr=sample_rate)
    except Exception:
        return None
    tempo_values = np.asarray(tempo).reshape(-1)
    return float(tempo_values[0]) if tempo_values.size else None


def _tempo_function(librosa_module):
    try:
        rhythm = getattr(librosa_module.feature, "rhythm", None)
        tempo_function = getattr(rhythm, "tempo", None) if rhythm else None
    except AttributeError:
        tempo_function = None
    if tempo_function:
        return tempo_function
    return getattr(librosa_module.beat, "tempo", None)


def _amp_to_db(value: float | None) -> float | None:
    if value is None or value <= 0:
        return None
    return float(20 * np.log10(max(value, 1e-12)))


def _energy_series(librosa_module, samples: np.ndarray) -> list[float]:
    if not samples.size:
        return []
    try:
        rms = librosa_module.feature.rms(y=samples)[0]
        return _downsample(rms.astype(float).tolist(), limit=96)
    except Exception:
        return []


def _spectral_centroid_series(librosa_module, samples: np.ndarray, sample_rate: int) -> list[float]:
    if not samples.size:
        return []
    try:
        centroid = librosa_module.feature.spectral_centroid(y=samples, sr=sample_rate)[0]
        return _downsample(centroid.astype(float).tolist(), limit=96)
    except Exception:
        return []


def _beat_positions(librosa_module, samples: np.ndarray, sample_rate: int) -> list[float]:
    if not samples.size or float(np.max(np.abs(samples))) < 1e-6:
        return []
    try:
        _, beat_frames = librosa_module.beat.beat_track(y=samples, sr=sample_rate)
        times = librosa_module.frames_to_time(beat_frames, sr=sample_rate)
        return [float(value) for value in np.asarray(times).reshape(-1)[:256]]
    except Exception:
        return []


def _estimate_key(librosa_module, samples: np.ndarray, sample_rate: int) -> str | None:
    if not samples.size or float(np.max(np.abs(samples))) < 1e-6:
        return None
    try:
        chroma = librosa_module.feature.chroma_stft(y=samples, sr=sample_rate)
        pitch_class = int(np.argmax(np.mean(chroma, axis=1)))
        return ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")[pitch_class]
    except Exception:
        return None


# Krumhansl-Kessler tonic profiles, indexed from the detected root.
_KK_MAJOR = np.array([6.35, 2.23, 3.48, 2.33, 4.38, 4.09, 2.52, 5.19, 2.39, 3.66, 2.29, 2.88])
_KK_MINOR = np.array([6.33, 2.68, 3.52, 5.38, 2.60, 3.53, 2.54, 4.75, 3.98, 2.69, 3.34, 3.17])
_NOTE_ORDER = ("C", "C#", "D", "D#", "E", "F", "F#", "G", "G#", "A", "A#", "B")


def _estimate_mode(
    librosa_module,
    samples: np.ndarray,
    sample_rate: int,
    key_estimate: str | None,
) -> str | None:
    """Major/minor by correlating chroma against tonic profiles rotated to the
    detected root. Pure numpy over chroma SessionIQ already computes."""
    if key_estimate is None or key_estimate not in _NOTE_ORDER or not samples.size:
        return None
    try:
        chroma = librosa_module.feature.chroma_stft(y=samples, sr=sample_rate)
        if chroma.size == 0:
            return None
        root = _NOTE_ORDER.index(key_estimate)
        rotated = np.roll(np.mean(chroma, axis=1), -root)
        major_score = float(np.corrcoef(rotated, _KK_MAJOR)[0, 1])
        minor_score = float(np.corrcoef(rotated, _KK_MINOR)[0, 1])
        if not (np.isfinite(major_score) and np.isfinite(minor_score)):
            return None
        return "major" if major_score >= minor_score else "minor"
    except Exception:
        return None


def _downsample(values: list[float], limit: int) -> list[float]:
    if len(values) <= limit:
        return [float(value) for value in values]
    indexes = np.linspace(0, len(values) - 1, limit).astype(int)
    return [float(values[index]) for index in indexes]
