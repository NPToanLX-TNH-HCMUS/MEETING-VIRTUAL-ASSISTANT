"""
Unit test suite for Audio Recorder & Player (In-meeting Phase).

Covers:
- TC-REC-01: Audio recording produces valid RIFF/WAVE files with strictly 44.1kHz / 16-bit PCM headers.
- TC-REC-02: Playback control transitions, idempotency (double-start prevention), and safe idle states.
- TC-REC-03: Graceful exception handling and state recovery when microphone drivers raise PortAudioError.
"""

from pathlib import Path
from unittest.mock import patch

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
    """Fixture providing an isolated Recorder instance for each test phase."""
    return Recorder()


class TestAudioRecorder:
    """Unit tests validating microphone stream stability, I/O file integrity, and exact state machines."""

    def test_record_creates_valid_wav_file(
        self, recorder: Recorder, tmp_path: Path
    ) -> None:
        """
        TC-REC-01: Validates the full recording lifecycle (start -> time elapse -> stop)
        ensuring the output is a correctly formatted 44.1kHz, 16-bit PCM WAV file.
        """
        # Arrange
        output_wav = tmp_path / "meeting_recording.wav"
        simulated_duration = 2.0  # Simulate 2 seconds of recording

        # Pre-allocate a dummy buffer identical to what sounddevice.rec generates internally
        dummy_buffer = np.zeros((MAX_SECONDS * SAMPLE_RATE, CHANNELS), dtype=np.int16)

        with patch("sounddevice.rec", return_value=dummy_buffer) as mock_rec, \
             patch("sounddevice.stop") as mock_stop, \
             patch("time.monotonic") as mock_monotonic:

            # Act 1: Initialize recording (mock monotonic time starts at 100.0)
            mock_monotonic.return_value = 100.0
            recorder.start()

            # Assert 1: State transitioned correctly
            assert recorder.is_recording is True
            mock_rec.assert_called_once()

            # Act 2: Fast-forward time and halt recording
            mock_monotonic.return_value = 100.0 + simulated_duration
            actual_duration = recorder.stop(path=str(output_wav))

            # Assert 2: Final states and hardware release
            assert recorder.is_recording is False
            mock_stop.assert_called_once()
            assert actual_duration == simulated_duration

            # Assert 3: Binary file integrity checks
            assert output_wav.exists(), "WAV file was not persisted to disk."
            assert output_wav.stat().st_size > 0, "WAV file is empty (0 bytes)."

            # Assert 4: Verify acoustic headers (RIFF format)
            written_rate, written_audio_data = read(str(output_wav))
            assert written_rate == SAMPLE_RATE
            assert written_audio_data.dtype == np.int16

            # The length of the array should match the simulated duration exactly
            expected_frames = int(simulated_duration * SAMPLE_RATE)
            assert len(written_audio_data) == expected_frames

    def test_playback_controls_and_idempotent_states(
        self, recorder: Recorder, tmp_path: Path
    ) -> None:
        """
        TC-REC-02: Verifies idempotent start calls, safe stop executions from an idle state, 
        and hardware playback invocation routing.
        """
        # 1. Validate Initial Idle State
        assert recorder.is_recording is False
        assert recorder.elapsed == 0.0

        # 2. Idempotency Check: Calling stop() safely returns 0.0 without throwing exceptions
        assert recorder.stop() == 0.0

        # 3. Hardware Routing Check: Ensure play() delegates correctly to sounddevice.play
        dummy_wav = tmp_path / "playback_sample.wav"
        dummy_audio = np.zeros(SAMPLE_RATE, dtype=np.int16)
        write(str(dummy_wav), SAMPLE_RATE, dummy_audio)

        with patch("sounddevice.play") as mock_play:
            recorder.play(path=str(dummy_wav))

            # Assert playback engine was triggered
            mock_play.assert_called_once()

        # 4. Concurrency Protection Check: Double start should not crash or override
        with patch("sounddevice.rec") as mock_rec:
            recorder.start()
            recorder.start()  # Immediate second click

            # Assert underlying hardware trigger is strictly called once
            mock_rec.assert_called_once()

    def test_handle_missing_audio_input_device_gracefully(
        self, recorder: Recorder
    ) -> None:
        """
        TC-REC-03: When hardware access fails (e.g., driver issues, missing mic), 
        the recorder must propagate the PortAudioError but cleanly reset its internal flags.
        """
        # Arrange: Simulate OS-level audio driver failure
        simulated_error = sd.PortAudioError("No input device found")

        # Act & Assert
        with patch("sounddevice.rec", side_effect=simulated_error):
            with pytest.raises(sd.PortAudioError, match="No input device found"):
                recorder.start()

            # The system must not be stuck in a 'recording' limbo state
            assert recorder.is_recording is False
            assert recorder.elapsed == 0.0
            