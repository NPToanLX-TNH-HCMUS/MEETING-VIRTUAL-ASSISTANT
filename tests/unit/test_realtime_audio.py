import wave
from unittest.mock import Mock

import numpy as np
import pytest

from src.backend.audio import recorder
from src.backend.speech_to_text.realtime_transcriber import (
    SAMPLE_RATE, calculate_audio_level, save_recording,
)


@pytest.mark.parametrize("sample, expected", [(0, 0), (32767, 100)])
def test_audio_levels_are_finite_and_bounded(sample, expected):
    result = calculate_audio_level(np.full((100, 1), sample, dtype=np.int16))
    assert np.isfinite(result["dbfs"])
    assert result["level"] == pytest.approx(expected, abs=0.1)
    assert -60 <= result["dbfs"] <= 0


def test_saved_realtime_audio_preserves_signed_samples_and_headers(tmp_path):
    path = tmp_path / "nested" / "record.wav"
    samples = np.array([[1], [-2], [32767], [-32768]], dtype=np.int16)
    save_recording(path, [samples[:2], samples[2:]])
    with wave.open(str(path), "rb") as stream:
        assert (stream.getnchannels(), stream.getsampwidth(), stream.getframerate()) == (1, 2, SAMPLE_RATE)
        assert stream.getnframes() == 4
        assert stream.readframes(4) == samples.astype("<i2").tobytes()


def test_batch_recorder_level_handles_silence_without_nan(monkeypatch):
    clock = Mock(return_value=100.0)
    monkeypatch.setattr(recorder.time, "monotonic", clock)
    monkeypatch.setattr(recorder.sd, "rec", Mock(return_value=np.zeros((44100, 1), dtype=np.int16)))
    capture = recorder.Recorder()
    capture.start()
    clock.return_value = 100.1
    assert capture.get_audio_level() == {"level": 0.0, "dbfs": -60}
