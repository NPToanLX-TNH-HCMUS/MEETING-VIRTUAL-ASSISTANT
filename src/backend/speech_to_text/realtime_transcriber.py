import asyncio
import base64
import json
import os
import wave
from pathlib import Path
from queue import Queue, Empty, Full
from time import monotonic
import numpy as np

import sounddevice as sd
from dotenv import load_dotenv
from websockets.asyncio.client import connect

PROJECT_ROOT = Path(__file__).resolve().parents[3]
load_dotenv(PROJECT_ROOT / ".env")

SAMPLE_RATE = 44100
BLOCK_SIZE = 4410
MAX_SECONDS = 300  # Wall-clock limit, including pauses.
FINAL_WAIT_SECONDS = 2

URL = (
    "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
    "?model_id=scribe_v2_realtime"
    "&audio_format=pcm_44100"
    "&commit_strategy=vad"
)


def save_recording(audio_path, chunks):
    path = Path(audio_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    with wave.open(str(path), "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(SAMPLE_RATE)

        for block in chunks:
            pcm_bytes = block.astype(
                "<i2", copy=False
            ).tobytes()

            wav_file.writeframesraw(pcm_bytes)

def calculate_audio_level(block):
    samples = block.astype(np.float32) / 32768.0

    rms = float(np.sqrt(np.mean(samples ** 2)))
    dbfs = 20 * np.log10(max(rms, 1e-10))

    level = float(np.clip((dbfs + 60) / 60 * 100, 0, 100))

    return {
        "type": "level",
        "level": round(level, 1),
        "dbfs": round(max(dbfs, -60), 1),
    }

async def stream_transcript(send_event, language="vi", stop_event=None, pause_event=None, audio_path=None):
    stop_event = stop_event if stop_event is not None else asyncio.Event()
    pause_event = pause_event if pause_event is not None else asyncio.Event()
    if language not in {"vi", "en"}:
        raise ValueError("Ngôn ngữ chưa được hỗ trợ.")

    url = URL + f"&language_code={language}"
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()

    if not api_key:
        raise ValueError("Chưa có ELEVENLABS_API_KEY trong .env")

    audio_queue = Queue(maxsize=50)
    problems = {
        "input_overflow": False,
        "queue_full": False,
    }
    committed_segments = []
    recorded_chunks = []

    async def send_pcm(connection, pcm_bytes, commit=False):
        await connection.send(json.dumps({
            "message_type": "input_audio_chunk",
            "audio_base_64": base64.b64encode(pcm_bytes).decode("ascii"),
            "sample_rate": SAMPLE_RATE,
            "commit": commit,
        }))

    async def drain_audio(connection):
        # Called after stopping the microphone: preserve audio captured before pause/stop.
        while True:
            try:
                block = audio_queue.get_nowait()
            except Empty:
                return
            await send_pcm(connection, block.astype("<i2", copy=False).tobytes())

    def on_audio(indata, frames, time_info, status):
        if status.input_overflow:
            problems["input_overflow"] = True

        block = indata.copy()

        # Giữ âm thanh thật để lưu bản ghi.
        recorded_chunks.append(block)

        # Chuyển cùng khối đó sang luồng nhận diện.
        try:
            audio_queue.put_nowait(block)
        except Full:
            problems["queue_full"] = True

    async def receive_transcripts(connection):
        async for raw_message in connection:
            message = json.loads(raw_message)
            message_type = message.get("message_type")
            text = message.get("text", "")

            if message_type == "partial_transcript":
                await send_event({
                    "type": "partial",
                    "text": text,
                })

            elif message_type == "committed_transcript":
                if text:
                    committed_segments.append(text)

                    await send_event({
                        "type": "committed",
                        "text": text,
                    })

            elif message_type == "warning":
                print("[Cảnh báo]", message.get("warning"))

            elif (
                message.get("error")
                or message_type == "error"
                or str(message_type).endswith("_error")
            ):
                raise RuntimeError(
                    f"ElevenLabs: {message_type}: "
                    f"{message.get('error', message.get('message', ''))}"
                )

    async with connect(
        url,
        additional_headers={"xi-api-key": api_key},
        open_timeout=15,
        close_timeout=5,
    ) as connection:
        # Chỉ bật microphone sau khi dịch vụ xác nhận phiên đã mở.
        first_message = json.loads(
            await asyncio.wait_for(connection.recv(), timeout=15)
        )

        if first_message.get("message_type") != "session_started":
            raise RuntimeError(
                f"Không mở được phiên: {first_message}"
            )

        receiver = asyncio.create_task(
            receive_transcripts(connection)
        )

        try:
            with sd.InputStream(
                samplerate=SAMPLE_RATE,
                channels=1,
                dtype="int16",
                blocksize=BLOCK_SIZE,
                callback=on_audio,
            ) as microphone:
                started_at = monotonic()
                paused = False
                await send_event({
                    "type": "ready",
                    "message": "Đang nhận diện. Có thể tạm dừng hoặc dừng; giới hạn 5 phút tính cả thời gian tạm dừng.",
                })

                while not stop_event.is_set() and monotonic() - started_at < MAX_SECONDS:
                    # Nếu tác vụ nhận bị lỗi hoặc kết nối đã đóng,
                    # dừng thu thay vì tiếp tục gửi âm thanh.
                    if receiver.done():
                        await receiver
                        raise RuntimeError(
                            "Kết nối nhận transcript đã đóng."
                        )

                    if any(problems.values()):
                        raise RuntimeError(
                            "Âm thanh bị mất do tràn hoặc hàng đợi đầy."
                        )

                    if pause_event.is_set() != paused:
                        paused = pause_event.is_set()
                        if paused:
                            microphone.stop()
                            await drain_audio(connection)
                        else:
                            microphone.start()
                        await send_event({
                            "type": "paused" if paused else "resumed",
                            "message": (
                                "Đã tạm dừng microphone. Các câu trước đó vẫn được giữ."
                                if paused else "Đã tiếp tục nhận diện."
                            ),
                        })

                    if paused:
                        # No microphone audio is captured. Synthetic silence keeps the
                        # provider session alive and lets VAD commit the previous speech.
                        await send_pcm(connection, bytes(BLOCK_SIZE * 2))
                        await asyncio.sleep(BLOCK_SIZE / SAMPLE_RATE)
                        continue

                    try:
                        block = audio_queue.get_nowait()
                    except Empty:
                        await asyncio.sleep(0.01)
                        continue

                    await send_event(calculate_audio_level(block))
                    await send_pcm(connection, block.astype("<i2", copy=False).tobytes())

            await send_event({"type": "stopping", "message": "Đã dừng microphone. Đang xử lý phần cuối…"})
            if any(problems.values()):
                raise RuntimeError("Âm thanh bị mất do tràn hoặc hàng đợi đầy.")
            await drain_audio(connection)
            await send_pcm(connection, b"", commit=True)
            # Bounded prototype wait, not a guaranteed final-result acknowledgement.
            await asyncio.sleep(FINAL_WAIT_SECONDS)

            if receiver.done():
                await receiver

        finally:
            receiver.cancel()

            try:
                await receiver
            except asyncio.CancelledError:
                pass
            finally:
                if audio_path is not None and recorded_chunks:
                    save_recording(audio_path, recorded_chunks)

    return "\n".join(committed_segments)
