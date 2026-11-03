import time

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

    def play(self, path=DEFAULT_PATH):
        sample_rate, audio = read(path)
        sd.play(audio, samplerate=sample_rate)
