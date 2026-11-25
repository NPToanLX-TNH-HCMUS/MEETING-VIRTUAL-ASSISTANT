"""
STAGE 2 (during meeting): record audio and transcribe it.

    POST /api/v1/meetings/{id}/recording/start   microphone on            ready -> live
    POST /api/v1/meetings/{id}/recording/stop    save record.wav          live  -> processing
    POST /api/v1/meetings/{id}/transcribe        ElevenLabs STT + diarization
    GET  /api/v1/meetings/{id}/recording/level   microphone volume of the batch recorder
    GET  /api/v1/meetings/{id}/transcript        transcript segments with ids and times (contract 6.9)
    WS   /ws/meetings/{id}/transcript-test       realtime STT with pause/resume/stop  ready -> live <-> paused -> processing
"""

import asyncio
import itertools
import json
import logging
from contextlib import suppress

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from ..agenda_tracker.fsm import apply_proposals
from ..agenda_tracker.tracker import propose_transitions
from ..audio.recorder import Recorder
from ..context.app_context import MeetingNotFoundError
from ..extraction.extractor import propose_items
from ..speech_to_text.realtime_transcriber import stream_transcript
from ..speech_to_text.segments import from_batch, make_segment
from ..speech_to_text.transcriber import AudioTranscriptionError, ElevenLabsTranscriber
from ..utils.objects import Meeting, TranscriptList
from ..utils.utils import envelope, error, now
from .common import CtxDep, SessionDep, meeting_response
from .extractions import merge_into_session

router = APIRouter(prefix="/meetings/{meeting_id}", tags=["during-meeting"])
# The WebSocket lives outside /api/v1 (see the contract), so it gets its own router.
ws_router = APIRouter(tags=["during-meeting"])

LOGGER = logging.getLogger(__name__)

# Agenda and extractions are re-checked after this many new sentences: each check is an
# LLM call (time, money, provider rate limits), so not every sentence.
# Design assumptions, tune with real meetings.
TRACK_EVERY = 3

# One microphone per laptop: the realtime session and the batch recorder must not overlap.
transcript_test_lock = asyncio.Lock()

AUDIO_FILE = "during_meeting/audio/record.wav"
TRANSCRIPT_FILE = "during_meeting/transcript/transcript.txt"


@router.post("/recording/start", response_model=Meeting)
def start_recording(session: SessionDep, ctx: CtxDep):
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
        started_at = now()
        ctx.meeting_repository.update_status(session.id, "live", started_at=started_at)
        session.emplace("recorder", recorder)
        session.status = "live"
        session.at("meeting")["started_at"] = started_at
        return meeting_response(session)


@router.post("/recording/stop", response_model=Meeting)
def stop_recording(session: SessionDep, ctx: CtxDep):
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
        ended_at = now()
        ctx.meeting_repository.update_status(
            session.id, "processing", ended_at=ended_at
        )
        session.status = "processing"
        session.at("meeting")["ended_at"] = ended_at
        return meeting_response(session)


@router.post("/transcribe")
def transcribe_recording(session: SessionDep, ctx: CtxDep):
    with session:
        audio = session.path(AUDIO_FILE)
        if not audio.is_file():
            return error(
                409, "INVALID_MEETING_STATE", "There is no recording to transcribe yet"
            )
        transcript_path = session.path(TRANSCRIPT_FILE)
        language = session.at("meeting")["language"]

    # The STT request can take a while, so it runs outside the session lock.
    try:
        segments = ElevenLabsTranscriber().transcribe_file(
            audio, transcript_path, language
        )
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
        language = session.at("meeting")["language"]
        normalized_segments = from_batch(segments, session.id, language)
        ctx.meeting_repository.save_transcript(
            session.id, normalized_segments, text, now()
        )
        session.emplace("transcript", normalized_segments)
        session.emplace("transcript_text", text)
        # They were built from the old transcript.
        session.pop("extractions")
        session.pop("extraction_cursor")
        session.pop("conflicts")
    return {"transcript": text}


@router.get("/transcript", response_model=TranscriptList)
def read_transcript(session: SessionDep, after: str | None = None):
    """
    BACK END RETURNS: {segments: TranscriptSegment[]}. `after` = a segment id: only the
    segments that come after it (used after a reconnect).
    """
    with session:
        segments = list(session.get("transcript", []))
    if after is not None:
        ids = [segment["id"] for segment in segments]
        if after not in ids:
            return error(404, "SEGMENT_NOT_FOUND", f"No segment with id {after}")
        segments = segments[ids.index(after) + 1 :]
    return {"segments": segments}


@router.get("/recording/level")
def get_recording_level(session: SessionDep):
    recorder = session.get("recorder")
    if recorder is None:
        return {"level": 0, "dbfs": -60}
    return recorder.get_audio_level()


@ws_router.websocket("/ws/meetings/{meeting_id}/transcript-test")
async def transcript_socket(websocket: WebSocket, meeting_id: str):
    await websocket.accept()
    ctx = websocket.app.state.ctx

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

    seq = itertools.count(1)
    # agenda_cursor: how many sentences the agenda checks have covered.
    tracking = {"count": 0, "task": None, "agenda_cursor": 0}

    async def send(event_type, data):
        with suppress(Exception):
            await websocket.send_json(envelope(event_type, session.id, next(seq), data))

    async def extract_live():
        with session:
            segments = list(session.get("transcript", []))
            cursor = session.get("extraction_cursor", 0)
            store = list(session.get("extractions") or [])
            agenda = [dict(item) for item in session.get("agenda", [])]
            language = session.at("meeting")["language"]
        try:
            raw_items = await asyncio.to_thread(
                propose_items, segments, cursor, store, now()[:10], agenda, language
            )
        except Exception:  # an LLM outage must not stop the transcript
            LOGGER.warning("Live extraction failed", exc_info=True)
            return  # the cursor stays, so the next pass covers these lines too
        with session:
            # Merged into the current data, so a conflict the user resolved meanwhile stays.
            events = merge_into_session(session, raw_items, segments, len(segments))
        for event_type, item in events:
            await send(event_type, item)

    async def analyse():
        # One after the other, so a meeting makes at most one LLM call at a time.
        await track_agenda()
        await extract_live()

    async def track_agenda():
        with session:
            agenda = [dict(item) for item in session.get("agenda", [])]
            segments = list(session.get("transcript", []))
        cursor = tracking["agenda_cursor"]
        try:
            proposals = await asyncio.to_thread(
                propose_transitions, agenda, segments, cursor
            )
        except Exception:  # an LLM outage must not stop the transcript
            LOGGER.warning("Agenda tracking failed", exc_info=True)
            return  # the cursor stays, so the next check covers these lines too
        tracking["agenda_cursor"] = len(segments)
        new_ids = {segment["id"] for segment in segments[cursor:]}
        with session:
            events = apply_proposals(
                session.get("agenda", []), proposals, segments, now(), new_ids
            )
        for data in events:
            await send("agenda.item_state", data)

    async def forward_event(event):
        new_status = None
        with session:
            if event["type"] == "committed":
                session.get("transcript").append(
                    make_segment(
                        session.id,
                        int(event["id"].removeprefix("seg_")),
                        event["text"],
                        session.at("meeting")["language"],
                        event["start_seconds"],
                        event["end_seconds"],
                    )
                )
            elif event["type"] == "paused":
                session.status = new_status = "paused"
            elif event["type"] in {"ready", "resumed"}:
                session.status = new_status = "live"
        if new_status is not None:
            await asyncio.to_thread(
                ctx.meeting_repository.update_status, session.id, new_status
            )
        await websocket.send_json(event)

        if event["type"] == "committed":
            tracking["count"] += 1
            task = tracking["task"]
            if tracking["count"] % TRACK_EVERY == 0 and (task is None or task.done()):
                tracking["task"] = asyncio.create_task(analyse())

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
        started_at = now()
        with session:
            meeting = session.at("meeting")
            session.status = "live"
            meeting["started_at"] = started_at
            meeting["ended_at"] = None
            audio_path = session.path(AUDIO_FILE)
            transcript_path = session.path(TRANSCRIPT_FILE)
            language = meeting["language"]
            session.emplace("transcript", [])  # a new run replaces the old segments
            session.pop("extractions")
            session.pop("extraction_cursor")
            session.pop("conflicts")

        await asyncio.to_thread(
            ctx.meeting_repository.update_status,
            session.id,
            "live",
            started_at=started_at,
            ended_at=None,
        )

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
            ended_at = now()
            with session:
                saved_segments = list(session.get("transcript") or [])
                session.emplace("transcript_text", transcript)
                meeting["ended_at"] = ended_at
                session.status = "processing"

            await asyncio.to_thread(
                ctx.meeting_repository.save_transcript,
                session.id,
                saved_segments,
                transcript,
                ended_at,
            )
            await asyncio.to_thread(
                ctx.meeting_repository.update_status,
                session.id,
                "processing",
                ended_at=ended_at,
            )
            await websocket.send_json(
                {
                    "type": "done",
                    "has_text": True,
                    "saved": True,
                    "transcript": transcript,
                    "segments": saved_segments,
                }
            )

        except WebSocketDisconnect:
            pass

        except Exception as exc:
            with suppress(Exception):
                await websocket.send_json({"type": "error", "message": str(exc)})

        finally:
            tasks = [stream_task, disconnect_task]
            if tracking["task"] is not None:
                tasks.append(tracking["task"])
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

            reset_needed = False
            with session:
                if session.status in {"live", "paused"}:
                    session.status = "ready"
                    meeting["started_at"] = None
                    meeting["ended_at"] = None
                    reset_needed = True
            if reset_needed:
                with suppress(Exception):
                    await asyncio.to_thread(
                        ctx.meeting_repository.update_status,
                        session.id,
                        "ready",
                        started_at=None,
                        ended_at=None,
                    )

            with suppress(Exception):
                await websocket.close()
