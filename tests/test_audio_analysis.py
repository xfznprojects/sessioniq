from __future__ import annotations

import math
import struct
import wave

import pytest

from sessioniq.audio_analysis import _estimate_bpm, analyze_audio


def test_analyze_wav_duration_and_levels(tmp_path):
    path = tmp_path / "kick.wav"
    sample_rate = 8_000
    duration_seconds = 1.0
    amplitude = 0.5
    frames = []
    for index in range(int(sample_rate * duration_seconds)):
        value = int(amplitude * 32767 * math.sin(2 * math.pi * 220 * index / sample_rate))
        frames.append(struct.pack("<h", value))

    with wave.open(str(path), "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(frames))

    metadata = analyze_audio(path)

    assert metadata.duration_seconds == 1.0
    assert metadata.sample_rate == sample_rate
    assert 0.45 <= metadata.peak_amplitude <= 0.51
    assert 0.30 <= metadata.rms_amplitude <= 0.38


def test_analyze_flac_uses_librosa_compatible_tempo_path(tmp_path):
    np = pytest.importorskip("numpy")
    sf = pytest.importorskip("soundfile")

    path = tmp_path / "loop.flac"
    sample_rate = 22_050
    samples = np.zeros(sample_rate, dtype=np.float32)
    sf.write(path, samples, sample_rate)

    metadata = analyze_audio(path)

    assert metadata.duration_seconds == 1.0
    assert metadata.sample_rate == sample_rate
    assert metadata.peak_amplitude == 0.0
    assert metadata.bpm_estimate is None


def test_estimate_bpm_falls_back_to_librosa_beat_tempo():
    np = pytest.importorskip("numpy")

    class BrokenFeature:
        def __getattr__(self, name):
            if name == "rhythm":
                raise AttributeError("No librosa.feature attribute rhythm")
            raise AttributeError(name)

    class FakeBeat:
        @staticmethod
        def tempo(y, sr):
            return np.array([123.0])

    class FakeLibrosa:
        feature = BrokenFeature()
        beat = FakeBeat()

    samples = np.ones(128, dtype=np.float32)

    assert _estimate_bpm(FakeLibrosa(), samples, 44_100) == 123.0
