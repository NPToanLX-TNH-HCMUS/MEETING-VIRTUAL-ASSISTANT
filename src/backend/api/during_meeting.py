"""
STAGE 2 (during meeting): record audio and transcribe it.

    POST /api/v1/meetings/{id}/recording/start   microphone on            ready -> live
    POST /api/v1/meetings/{id}/recording/stop    save record.wav          live  -> processing
    POST /api/v1/meetings/{id}/transcribe        ElevenLabs STT + diarization
    GET  /api/v1/meetings/{id}/recording/level   microphone volume of the batch recorder
    WS   /ws/meetings/{id}/transcript-test       realtime STT with pause/resume/stop  ready -> live <-> paused -> processing
"""

import asyncio
import json
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..audio.recorder import Recorder
from ..context.app_context import MeetingNotFoundError
from ..speech_to_text.realtime_transcriber import stream_transcript
from ..speech_to_text.transcriber import AudioTranscriptionError, ElevenLabsTranscriber
from ..utils.objects import Meeting
from ..utils.utils import error, now
from .common import CtxDep, SessionDep, meeting_response

router = APIRouter(prefix="/meetings/{meeting_id}", tags=["during-meeting"])
# The WebSocket lives outside /api/v1 (see the contract), so it gets its own router.
ws_router = APIRouter(tags=["during-meeting"])

# One microphone per laptop: the realtime session and the batch recorder must not overlap.
transcript_test_lock = asyncio.Lock()

AUDIO_FILE = "during_meeting/audio/record.wav"
TRANSCRIPT_FILE = "during_meeting/transcript/transcript.txt"


@router.post("/recording/start", response_model=Meeting)
def start_recording(session: SessionDep):
    if transcript_test_lock.locked():
        return error(
            409,
            "MICROPHONE_BUSY",
            "Microphone đang được dùng cho transcript trực tiếp.",
        )
    with session:
        if session.status != "ready":
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Cannot start recording while the meeting is {session.status}",
            )
        try:
            recorder = Recorder()
            recorder.start()
        except Exception as exc:  # sounddevice raises PortAudioError when there is no microphone / no permission
            return error(500, "RECORDER_FAILED", str(exc))
        session.emplace("recorder", recorder)
        session.status = "live"
        session.at("meeting")["started_at"] = now()
        return meeting_response(session)


@router.post("/recording/stop", response_model=Meeting)
def stop_recording(session: SessionDep):
    with session:
        recorder = session.get("recorder")
        if session.status != "live" or recorder is None:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Cannot stop recording while the meeting is {session.status}",
            )
        recorder.stop(str(session.path(AUDIO_FILE)))
        session.pop("recorder")
        session.status = "processing"
        session.at("meeting")["ended_at"] = now()
        return meeting_response(session)


@router.post("/transcribe")
def transcribe_recording(session: SessionDep):
    with session:
        audio = session.path(AUDIO_FILE)
        if not audio.is_file():
            return error(
                409, "INVALID_MEETING_STATE", "There is no recording to transcribe yet"
            )
        transcript_path = session.path(TRANSCRIPT_FILE)

    # The STT request can take a while, so it runs outside the session lock.
    try:
        segments = ElevenLabsTranscriber().transcribe_file(audio, transcript_path)
    except ValueError as exc:  # missing ELEVENLABS_API_KEY, empty or invalid wav
        return error(422, "TRANSCRIPTION_INPUT_INVALID", str(exc))
    except AudioTranscriptionError as exc:
        return error(502, "TRANSCRIPTION_FAILED", str(exc))

    # Format speaker turns here so the frontend can display the string directly.
    text = "\n\n".join(
        f"[{segment['Timestamp']}] {segment['Speaker']}:\n{segment['Text']}"
        for segment in segments
    )

    with session:
        session.emplace("transcript", segments)
        session.emplace("transcript_text", text)
    return {"transcript": text}


@router.get("/recording/level")
def get_recording_level(session: SessionDep):
    recorder = session.get("recorder")
    if recorder is None:
        return {"level": 0, "dbfs": -60}
    return recorder.get_audio_level()


@ws_router.websocket("/ws/meetings/{meeting_id}/transcript-test")
async def transcript_socket(websocket: WebSocket, ctx: CtxDep, meeting_id: str):
    await websocket.accept()

    try:
        session = ctx.session(meeting_id)
    except MeetingNotFoundError:
        await websocket.send_json(
            {"type": "error", "message": "Không tìm thấy cuộc họp."}
        )
        await websocket.close(code=1008)
        return

    batch_recording = any(s.get("recorder") is not None for s in ctx.sessions())
    if session.status != "ready" or batch_recording or transcript_test_lock.locked():
        await websocket.send_json(
            {
                "type": "error",
                "message": "Hãy xác nhận agenda và dừng các phiên ghi âm trước khi test transcript.",
            }
        )
        await websocket.close(code=1008)
        return

    stop_event = asyncio.Event()
    pause_event = asyncio.Event()

    async def forward_event(event):
        with session:
            if event["type"] == "paused":
                session.status = "paused"
            elif event["type"] in {"ready", "resumed"}:
                session.status = "live"
        await websocket.send_json(event)

    async def wait_for_disconnect():
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            if message["type"] == "websocket.receive" and message.get("text"):
                try:
                    command = json.loads(message["text"])
                except json.JSONDecodeError:
                    continue
                if not isinstance(command, dict):
                    continue
                if command.get("type") == "stop":
                    stop_event.set()
                elif not stop_event.is_set():
                    if command.get("type") == "pause":
                        pause_event.set()
                    elif command.get("type") == "resume":
                        pause_event.clear()

    async with transcript_test_lock:
        with session:
            meeting = session.at("meeting")
            session.status = "live"
            meeting["started_at"] = now()
            meeting["ended_at"] = None
            audio_path = session.path(AUDIO_FILE)
            transcript_path = session.path(TRANSCRIPT_FILE)
            language = meeting["language"]

        stream_task = asyncio.create_task(
            stream_transcript(
                send_event=forward_event,
                language=language,
                stop_event=stop_event,
                pause_event=pause_event,
                audio_path=audio_path,
            )
        )
        disconnect_task = asyncio.create_task(wait_for_disconnect())

        try:
            await asyncio.wait(
                {stream_task, disconnect_task}, return_when=asyncio.FIRST_COMPLETED
            )

            # The user closed the page: stop recognition, keep nothing but the WAV.
            if disconnect_task.done():
                return

            # Re-raises a stream failure into the except branch below.
            transcript = (await stream_task).strip()
            if not transcript:
                raise ValueError(
                    "Chưa có câu nào được chốt. "
                    "Hãy thử lại và ngừng nói vài giây trước khi phiên kết thúc."
                )

            transcript_path.write_text(transcript, encoding="utf-8")
            with session:
                meeting["ended_at"] = now()
                session.status = "processing"

            await websocket.send_json(
                {
                    "type": "done",
                    "has_text": True,
                    "saved": True,
                    "transcript": transcript,
                }
            )

        except WebSocketDisconnect:
            pass

        except Exception as exc:
            with suppress(Exception):
                await websocket.send_json({"type": "error", "message": str(exc)})

        finally:
            for task in (stream_task, disconnect_task):
                task.cancel()
            await asyncio.gather(stream_task, disconnect_task, return_exceptions=True)

            with session:
                if session.status in {"live", "paused"}:
                    session.status = "ready"
                    meeting["started_at"] = None
                    meeting["ended_at"] = None

            with suppress(Exception):
                await websocket.close()
