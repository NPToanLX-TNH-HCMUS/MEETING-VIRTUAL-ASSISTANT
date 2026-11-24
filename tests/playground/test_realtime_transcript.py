import asyncio
import base64
import json
import os
from pathlib import Path
from queue import Queue, Empty, Full
from time import monotonic

import sounddevice as sd
from dotenv import load_dotenv
from websockets.asyncio.client import connect

PROJECT_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(PROJECT_ROOT / ".env")

SAMPLE_RATE = 44100
BLOCK_SIZE = 4410
TEST_SECONDS = 15

URL = (
    "wss://api.elevenlabs.io/v1/speech-to-text/realtime"
    "?model_id=scribe_v2_realtime"
    "&audio_format=pcm_44100"
    "&commit_strategy=vad"
    "&language_code=vi"
)


async def main():
    api_key = os.getenv("ELEVENLABS_API_KEY", "").strip()

    if not api_key:
        raise ValueError("Chưa có ELEVENLABS_API_KEY trong .env")

    audio_queue = Queue(maxsize=50)
    problems = {
        "input_overflow": False,
        "queue_full": False,
    }
    committed_segments = []

    def on_audio(indata, frames, time_info, status):
        if status.input_overflow:
            problems["input_overflow"] = True

        try:
            audio_queue.put_nowait(indata.copy())
        except Full:
            problems["queue_full"] = True

    async def receive_transcripts(connection):
        async for raw_message in connection:
            message = json.loads(raw_message)
            message_type = message.get("message_type")
            text = message.get("text", "")

            if message_type == "partial_transcript":
                if text:
                    print(f"[Đang nhận diện] {text}")

            elif message_type == "committed_transcript":
                if text:
                    committed_segments.append(text)
                    print(f"\n[Đã chốt] {text}\n")

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
        URL,
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

        print("Đã kết nối ElevenLabs.")
        print("Thu trong 15 giây.")
        print("Hãy nói một câu, rồi im lặng vài giây.")
        print("Trong 3 giây cuối, hãy im lặng để dịch vụ chốt câu.\n")

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
            ):
                started_at = monotonic()

                while monotonic() - started_at < TEST_SECONDS:
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

                    try:
                        block = audio_queue.get_nowait()
                    except Empty:
                        await asyncio.sleep(0.01)
                        continue

                    pcm_bytes = block.astype(
                        "<i2", copy=False
                    ).tobytes()

                    await connection.send(json.dumps({
                        "message_type": "input_audio_chunk",
                        "audio_base_64": base64.b64encode(
                            pcm_bytes
                        ).decode("ascii"),
                        "sample_rate": SAMPLE_RATE,
                    }))

            # Test có thời hạn: đợi thêm một chút cho kết quả
            # của đoạn im lặng cuối. Đây chưa phải cơ chế Stop
            # hoàn chỉnh để bảo đảm chốt câu cuối trong app.
            await asyncio.sleep(2)

            if receiver.done():
                await receiver

        finally:
            receiver.cancel()

            try:
                await receiver
            except asyncio.CancelledError:
                pass

    print("\n--- Transcript đã chốt ---")
    print("\n".join(committed_segments) or "(Chưa có đoạn đã chốt)")
    print("\nĐã đóng microphone và kết nối.")


if __name__ == "__main__":
    asyncio.run(main())