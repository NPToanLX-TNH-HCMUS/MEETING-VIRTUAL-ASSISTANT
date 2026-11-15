from queue import Queue, Empty, Full
from time import monotonic

import numpy as np
import sounddevice as sd


SAMPLE_RATE = 44100
BLOCK_SIZE = 4410
TEST_SECONDS = 10


def main():
    audio_queue = Queue(maxsize=50)

    problems = {
        "input_overflow": False,
        "queue_full": False,
    }

    def on_audio(indata, frames, time_info, status):
        if status.input_overflow:
            problems["input_overflow"] = True

        try:
            audio_queue.put_nowait(indata.copy())
        except Full:
            problems["queue_full"] = True

    print("Bắt đầu thu 10 giây. Hãy nói vào microphone.")

    with sd.InputStream(
        samplerate=SAMPLE_RATE,
        channels=1,
        dtype="int16",
        blocksize=BLOCK_SIZE,
        callback=on_audio,
    ):
        started_at = monotonic()
        block_count = 0

        while monotonic() - started_at < TEST_SECONDS:
            try:
                block = audio_queue.get(timeout=0.5)
            except Empty:
                print("Chưa nhận được dữ liệu âm thanh.")
                continue

            samples = block.astype(np.float32) / 32768.0
            rms = float(np.sqrt(np.mean(samples ** 2)))

            block_count += 1

            print(
                f"Khối {block_count:03d} | "
                f"Số mẫu: {len(block)} | "
                f"RMS: {rms:.4f}"
            )

    print("Đã dừng.")
    print("Microphone bị tràn:", problems["input_overflow"])
    print("Hàng đợi bị đầy:", problems["queue_full"])


if __name__ == "__main__":
    main()