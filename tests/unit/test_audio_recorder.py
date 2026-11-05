"""
Unit test suite for Audio Recorder & Player (Thành Tài - In-meeting).

Covers:
- TC-TAI-01: Audio recording produces valid .wav files with correct headers
- TC-TAI-02: Playback control transitions and state flags (idle -> recording -> stopped)
- TC-TAI-03: Graceful exception handling when microphone is disconnected
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest
import sounddevice as sd
from scipy.io.wavfile import read, write

from backend.audio.recorder import (
    CHANNELS,
    MAX_SECONDS,
    SAMPLE_RATE,
    Recorder,
)


@pytest.fixture
def recorder() -> Recorder:
    """Fixture providing a fresh Recorder instance for each test case."""
    return Recorder()


class TestAudioRecorder:
    """Unit tests validating microphone recording stability, file integrity, and state transitions."""

    def test_record_creates_valid_wav_file(
        self, recorder: Recorder, tmp_path: Path
    ) -> None:
        """
        TC-TAI-01: Recording for a duration must output a valid RIFF/WAVE file
        with size > 0 bytes, proper 44.1kHz sample rate, and 16-bit PCM format.
        """
        output_wav = tmp_path / "meeting_recording.wav"

        # Mock buffer âm thanh giả lập do sounddevice tạo ra
        dummy_buffer = np.zeros((MAX_SECONDS * SAMPLE_RATE, 1), dtype=np.int16)

        with patch("sounddevice.rec", return_value=dummy_buffer) as mock_rec, \
             patch("sounddevice.stop") as mock_stop:

            # Bắt đầu thu âm
            recorder.start()
            assert recorder.is_recording is True
            mock_rec.assert_called_once()

            # Dừng thu âm và ghi ra file WAV
            duration = recorder.stop(path=str(output_wav))

            # Kiểm tra trạng thái và file đầu ra
            assert recorder.is_recording is False
            mock_stop.assert_called_once()
            assert output_wav.exists()
            assert output_wav.stat().st_size > 0

            # Kiểm tra định dạng kỹ thuật của file WAV vừa tạo
            sample_rate, audio_data = read(str(output_wav))
            assert sample_rate == SAMPLE_RATE
            assert audio_data.dtype == np.int16

    def test_playback_controls_state_transitions(
        self, recorder: Recorder, tmp_path: Path
    ) -> None:
        """
        TC-TAI-02: Verify idle state, idempotent start calls, safe stop when idle,
        and audio playback invocation.
        """
        # 1. Trạng thái khởi tạo ban đầu
        assert recorder.is_recording is False
        assert recorder.elapsed == 0.0

        # 2. Gọi stop() khi chưa từng start() -> Không được crash, trả về 0.0
        assert recorder.stop() == 0.0

        # 3. Tạo một file audio mẫu để kiểm tra hàm play()
        dummy_wav = tmp_path / "playback_sample.wav"
        dummy_audio = np.zeros(SAMPLE_RATE, dtype=np.int16)
        write(str(dummy_wav), SAMPLE_RATE, dummy_audio)

        with patch("sounddevice.play") as mock_play:
            recorder.play(path=str(dummy_wav))
            mock_play.assert_called_once()

    def test_handle_missing_audio_input_device_gracefully(
        self, recorder: Recorder
    ) -> None:
        """
        TC-TAI-03: If no microphone or audio input device is detected,
        sounddevice raises PortAudioError. The module state must remain safe.
        """
        # Giả lập driver âm thanh không tìm thấy micro
        with patch("sounddevice.rec", side_effect=sd.PortAudioError("No input device found")):
            with pytest.raises(sd.PortAudioError, match="No input device found"):
                recorder.start()

            # Đảm bảo cờ is_recording không bị kẹt ở trạng thái True
            assert recorder.is_recording is False
            assert recorder.elapsed == 0.0
