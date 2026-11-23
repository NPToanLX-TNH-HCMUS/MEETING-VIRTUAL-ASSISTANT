"""REST controls and the outbound-only meeting event channel."""
import asyncio
import json
import logging
from contextlib import suppress

from anyio import CancelScope
from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..context.app_context import MeetingNotFoundError
from ..during_meeting.meeting_session import MeetingSession as RealtimeSession
from ..during_meeting.meeting_service import run_recording, wait_for_ack
from ..during_meeting.transcript_store import segments_after
from ..speech_to_text.transcriber import AudioTranscriptionError, ElevenLabsTranscriber
from ..utils.objects import MeetingControlResponse, TranscriptList
from ..utils.utils import error, now
from .common import SessionDep

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/meetings/{meeting_id}", tags=["during-meeting"])
ws_router = APIRouter(tags=["during-meeting"])
microphone_lock = asyncio.Lock()
AUDIO_FILE = "during_meeting/audio/record.wav"
TRANSCRIPT_FILE = "during_meeting/transcript/transcript.txt"


async def finish_meeting(realtime, session):
    from .post_meeting import generate_minutes
    try:
        await generate_minutes(session)
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Minutes processing failed for %s", session.id)


async def run_meeting_session(realtime, session):
    try:
        text = await run_recording(realtime, session)
        with session:
            session.emplace("transcript_text", text)
            session.emplace("transcript", list(realtime.transcript_segments))
        realtime.processing_task = asyncio.create_task(finish_meeting(realtime, session))
    except asyncio.CancelledError:
        raise
    except Exception:
        logger.exception("Recording failed for %s", session.id)
        realtime.pipeline_error = {
            "code": "RECORDING_FAILED",
            "message": "Recording failed; captured segments are retained. Check backend logs.",
            "recoverable": False,
        }
        with session:
            session.status = "processing" if realtime.ready_ack.is_set() else "ready"
            session.at("meeting")["ended_at"] = now() if realtime.ready_ack.is_set() else None
        await realtime.publish("meeting.status", {"status": session.status})
        await realtime.publish("error", realtime.pipeline_error)
    finally:
        realtime.stop_event.set()


def release_microphone(task):
    microphone_lock.release()
    if not task.cancelled():
        task.exception()


@router.post("/start", response_model=MeetingControlResponse)
async def start_meeting(session: SessionDep):
    if session.status != "ready":
        return error(409, "INVALID_MEETING_STATE", f"Cannot start while {session.status}.")
    if microphone_lock.locked():
        return error(409, "RECORDING_ALREADY_ACTIVE", "Microphone is already in use.")
    await microphone_lock.acquire()
    try:
        previous = session.get("realtime")
        realtime = RealtimeSession(session.id)
        if previous:
            # Preserve cursors and viewers on retry after a failed startup.
            realtime.seq = previous.seq
            realtime.subscribers = previous.subscribers
            realtime.transcript_segments = previous.transcript_segments
            realtime.temp_transcript = previous.temp_transcript
            realtime.summary_history = previous.summary_history
        with session:
            session.emplace("realtime", realtime)
            meeting = session.at("meeting")
            meeting["started_at"] = None
            meeting["ended_at"] = None
            duration = meeting["duration_minutes"] * 60
        realtime.stream_task = asyncio.create_task(run_meeting_session(realtime, session))
    except BaseException:
        microphone_lock.release()
        raise
    realtime.stream_task.add_done_callback(release_microphone)
    try:
        await wait_for_ack(realtime, realtime.ready_ack, timeout=30)
        if realtime.pipeline_error or realtime.stream_task.done():
            raise RuntimeError("Recording ended during startup.")
    except BaseException as exc:
        realtime.stream_task.cancel()
        await asyncio.gather(realtime.stream_task, return_exceptions=True)
        with session:
            session.status = "ready"
            meeting["started_at"] = None
            meeting["ended_at"] = None
        if isinstance(exc, asyncio.CancelledError):
            raise
        if not isinstance(exc, Exception):
            raise
        return error(503, "MIC_UNAVAILABLE", "Could not start recording. Check backend logs.")
    return realtime.control_response("live", duration)


async def control_meeting(session, command):
    realtime = session.get("realtime")
    allowed = {"pause": {"live"}, "resume": {"paused"}, "stop": {"live", "paused"}}
    if realtime is None:
        return error(409, "INVALID_MEETING_STATE", "No active recording.")
    async with realtime.control_lock:
        if (session.status not in allowed[command] or realtime.stop_event.is_set()
                or realtime.stream_task is None or realtime.stream_task.done()):
            return error(409, "INVALID_MEETING_STATE", f"Cannot {command} while {session.status}.")
        ack = {"pause": realtime.paused_ack, "resume": realtime.resumed_ack,
               "stop": realtime.stopped_ack}[command]
        ack.clear()
        if command == "pause":
            realtime.pause_event.set()
        elif command == "resume":
            realtime.pause_event.clear()
        else:
            realtime.stop_event.set()
        try:
            await wait_for_ack(realtime, ack)
        except (Exception, asyncio.CancelledError) as exc:
            realtime.stop_event.set()
            if isinstance(exc, asyncio.CancelledError):
                raise
            return error(503, "MIC_UNAVAILABLE", "Recording did not acknowledge the command.")
        status = {"pause": "paused", "resume": "live", "stop": "processing"}[command]
        return realtime.control_response(status, session.at("meeting")["duration_minutes"] * 60)


@router.post("/pause", response_model=MeetingControlResponse)
async def pause_meeting(session: SessionDep):
    return await control_meeting(session, "pause")


@router.post("/resume", response_model=MeetingControlResponse)
async def resume_meeting(session: SessionDep):
    return await control_meeting(session, "resume")


@router.post("/stop", response_model=MeetingControlResponse)
async def stop_meeting(session: SessionDep):
    return await control_meeting(session, "stop")


@router.get("/transcript", response_model=TranscriptList)
def read_transcript(session: SessionDep, after: str | None = None):
    with session:
        realtime = session.get("realtime")
        if realtime:
            segments = list(realtime.transcript_segments)
        else:
            path = session.path("during_meeting/transcript/segments.jsonl")
            try:
                segments = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                            if line.strip()] if path.exists() else []
            except (ValueError, OSError):
                return error(500, "TRANSCRIPT_READ_FAILED", "Could not read saved transcript.")
    try:
        return {"segments": segments_after(segments, after)}
    except ValueError:
        return error(400, "INVALID_TRANSCRIPT_CURSOR", "Unknown transcript segment ID.")


@router.get("/state")
async def read_state(session: SessionDep):
    realtime = session.get("realtime")
    duration = session.at("meeting")["duration_minutes"] * 60
    state = realtime.control_response(session.status, duration) if realtime else {
        "status": session.status, "started_at": session.at("meeting")["started_at"],
        "elapsed_seconds": 0, "remaining_seconds": duration,
    }
    return {
        **state, "seq": realtime.seq if realtime else 0,
        "transcript_saved": realtime.transcript_saved if realtime else session.has("transcript_text"),
        "minutes_ready": session.has("minutes"),
        "error": realtime.pipeline_error if realtime else None,
    }


@router.get("/summaries")
def read_summaries(session: SessionDep):
    with session:
        path = session.path("post_meeting/summary/summary_history.json")
        try:
            items = json.loads(path.read_text(encoding="utf-8")) if path.exists() else []
            if not isinstance(items, list):
                raise ValueError("Invalid history")
        except (ValueError, OSError):
            return error(500, "SUMMARY_READ_FAILED", "Could not read summary history.")
    return {"items": items}


@ws_router.websocket("/ws/meetings/{meeting_id}")
async def meeting_socket(websocket: WebSocket, meeting_id: str):
    await websocket.accept()
    try:
        session = websocket.app.state.ctx.session(meeting_id)
    except MeetingNotFoundError:
        await websocket.close(code=1008)
        return
    realtime = session.get("realtime")
    if realtime is None:
        await websocket.close(code=1008)
        return
    queue = realtime.subscribe()

    async def send_events():
        while True:
            event = await queue.get()
            if event is None:
                await websocket.close(code=1013)
                return
            await websocket.send_json(event)

    async def wait_disconnect():
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                return
            # Application commands are deliberately ignored; REST owns state.

    tasks = [asyncio.create_task(send_events()), asyncio.create_task(wait_disconnect())]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    except (WebSocketDisconnect, RuntimeError, asyncio.CancelledError):
        pass
    finally:
        realtime.unsubscribe(queue)
        with CancelScope(shield=True):
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)
            with suppress(Exception):
                await websocket.close()


@router.post("/transcribe")
def transcribe_recording(session: SessionDep):
    with session:
        if session.get("realtime") is not None or session.status not in {"ready", "processing"}:
            return error(409, "INVALID_MEETING_STATE",
                         "Batch transcription cannot overwrite a realtime meeting.")
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
