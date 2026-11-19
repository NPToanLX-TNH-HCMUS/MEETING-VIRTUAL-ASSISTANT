import time
import numpy as np

import sounddevice as sd
from scipy.io.wavfile import read, write

SAMPLE_RATE = 44100
CHANNELS = 1
DTYPE = "int16"
MAX_SECONDS = 300
DEFAULT_PATH = "record.wav"


class Recorder:

    def __init__(self):
        self._buffer = None
        self._start_time = 0.0

    @property
    def is_recording(self):
        return self._buffer is not None

    @property
    def elapsed(self):
        if not self.is_recording:
            return 0.0
        return min(time.monotonic() - self._start_time, MAX_SECONDS)

    def start(self):
        if self.is_recording:
            return
        self._buffer = sd.rec(MAX_SECONDS * SAMPLE_RATE, samplerate=SAMPLE_RATE,
                              channels=CHANNELS, dtype=DTYPE)
        self._start_time = time.monotonic()

    def stop(self, path=DEFAULT_PATH):
        if not self.is_recording:
            return 0.0
        # The buffer is preallocated for MAX_SECONDS, so cut it to what was actually recorded
        frames = min(int(self.elapsed * SAMPLE_RATE), len(self._buffer))
        sd.stop()
        write(path, SAMPLE_RATE, self._buffer[:frames])
        self._buffer = None
        return frames / SAMPLE_RATE

    def get_audio_level(self) -> dict:
        buffer = self._buffer
        if buffer is None:
            return {
                "level": 0,
                "dbfs": -60
            }

        end = int(min(self.elapsed * SAMPLE_RATE, len(buffer)))
        start = max(0, end - int(0.2 * SAMPLE_RATE))
        if start >= end:
            return {
                "level": 0,
                "dbfs": -60
            }

        samples = buffer[start:end].astype(np.float32) / 32768.0

        rms = float(np.sqrt(np.mean(samples ** 2)))
        dbfs = 20 * np.log10(max(rms, 1e-10))

        level = float(np.clip((dbfs + 60) / 60 * 100, 0, 100))

        return {
            "level": round(level, 1),
            "dbfs": round(max(dbfs, -60), 1)
        }

    def play(self, path=DEFAULT_PATH):
        sample_rate, audio = read(path)
        sd.play(audio, samplerate=sample_rate)
