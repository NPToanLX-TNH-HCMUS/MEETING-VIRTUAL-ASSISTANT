import asyncio
import logging
from datetime import datetime

from .live_summary import summarize_live
from .summary_storage import append_summary_history
from .transcript_store import append_segment
from .live_analysis import analyse_pending, analyse_transcript
from ..speech_to_text.realtime_transcriber import stream_transcript
from ..utils.llm import LLMCallError

logger = logging.getLogger(__name__)
SUMMARY_INTERVAL_SECONDS = 15


async def run_live_summary(session, meeting_session):
    last_revision = session.summary_history[-1]["revision"] if session.summary_history else 0
    while not session.stop_event.is_set():
        try:
            await asyncio.wait_for(session.stop_event.wait(), timeout=SUMMARY_INTERVAL_SECONDS)
            return
        except asyncio.TimeoutError:
            pass
        revision = len(session.temp_transcript)
        if revision == last_revision:
            continue
        try:
            summary = await asyncio.to_thread(
                summarize_live, "\n".join(session.temp_transcript),
                meeting_session.at("meeting")["language"],
            )
            if session.stop_event.is_set():
                return
            entry = append_summary_history(
                meeting_session.path(
                    "post_meeting/summary/summary_history.json"
                ).parent,
                revision,
                summary,
                datetime.now().astimezone().isoformat(timespec="seconds"),
            )
        except (LLMCallError, OSError, ValueError) as exc:
            logger.warning("Summary failed: %s", type(exc).__name__)
            await session.publish("error", {
                "code": getattr(exc, "code", "SUMMARY_SAVE_FAILED"),
                "message": "Chưa cập nhật được tóm tắt. Sẽ thử lại.",
                "recoverable": True,
            })
            continue
        session.summary_history.append(entry)
        last_revision = revision
        await session.publish("summary.updated", entry)


async def run_timer(session, meeting_session):
    await session.ready_ack.wait()

    duration = (
        meeting_session.at("meeting")["duration_minutes"] * 60
    )

    while not session.stopped_ack.is_set():
        state = session.control_response(
            meeting_session.status,
            duration,
        )

        await session.publish("timer.sync", {
            "elapsed_seconds": state["elapsed_seconds"],
            "remaining_seconds": state["remaining_seconds"],
        })

        try:
            await asyncio.wait_for(
                session.stopped_ack.wait(),
                timeout=5,
            )
        except asyncio.TimeoutError:
            pass


async def run_recording(session, meeting_session):
    meeting = meeting_session.at("meeting")

    async def handle_event(event):
        kind = event["type"]
        if kind == "committed":
            segment = append_segment(session, meeting_session, event)
            if segment:
                await session.publish("transcript.segment", segment)
                if (len(session.transcript_segments) - session.analysis_revision >= 3
                        and (session.analysis_task is None or session.analysis_task.done())):
                    session.analysis_task = asyncio.create_task(
                        analyse_pending(session, meeting_session)
                    )
            return
        if kind == "partial":
            await session.publish("transcript.partial", {"text": event["text"]})
            return
        if kind == "level":
            await session.publish("audio.level", {
                "level": event["level"], "dbfs": event["dbfs"],
            })
            return
        if kind == "ready":
            session.mark_started()
            meeting["started_at"] = session.started_at
            meeting_session.status = "live"
            session.ready_ack.set()
        elif kind == "paused":
            session.mark_paused()
            meeting_session.status = "paused"
            session.paused_ack.set()
        elif kind == "resumed":
            session.mark_resumed()
            meeting_session.status = "live"
            session.resumed_ack.set()
        elif kind == "stopping":
            session.mark_stopped()
            session.stop_event.set()
            meeting_session.status = "processing"
            meeting["ended_at"] = datetime.now().astimezone().isoformat(timespec="seconds")
            session.stopped_ack.set()
        else:
            return
        await session.publish(
            "meeting.status",
            {"status": meeting_session.status},
        )
        repository = meeting_session.get("repository")
        if repository:
            await asyncio.to_thread(
                repository.update_status, meeting_session.id, meeting_session.status,
                started_at=meeting.get("started_at"), ended_at=meeting.get("ended_at"),
            )

    session.summary_task = asyncio.create_task(run_live_summary(session, meeting_session))
    session.timer_task = asyncio.create_task(run_timer(session, meeting_session))
    try:
        await stream_transcript(
            send_event=handle_event,
            language=meeting["language"],
            stop_event=session.stop_event,
            pause_event=session.pause_event,
            audio_path=meeting_session.path(
                "during_meeting/audio/record.wav"
            ),
            max_seconds=meeting["duration_minutes"] * 60,
        )
        transcript = "\n".join(s["text"] for s in session.transcript_segments)
        if not transcript.strip():
            raise ValueError("Chưa có đoạn transcript nào được chốt.")
        path = meeting_session.path(
            "during_meeting/transcript/transcript.txt"
        )
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = path.with_suffix(".tmp")
        temporary.write_text(transcript, encoding="utf-8")
        temporary.replace(path)
        session.transcript_saved = True
        # Finish analysis on the final, possibly smaller batch before minutes.
        if session.analysis_task is not None:
            await session.analysis_task
        await analyse_transcript(session, meeting_session)
        return transcript
    finally:
        session.mark_stopped()
        session.stop_event.set()
        tasks = [session.summary_task, session.timer_task]
        if session.analysis_task is not None:
            tasks.append(session.analysis_task)
        for task in tasks:
            task.cancel()
        results = await asyncio.gather(*tasks, return_exceptions=True)
        for result in results:
            if isinstance(result, Exception):
                logger.error("Background meeting task failed: %r", result)


async def wait_for_ack(session, acknowledgement, timeout=15):
    waiter = asyncio.create_task(acknowledgement.wait())
    try:
        completed, _ = await asyncio.wait(
            {waiter, session.stream_task}, timeout=timeout,
            return_when=asyncio.FIRST_COMPLETED,
        )
        if acknowledgement.is_set():
            return
        if session.stream_task in completed:
            await session.stream_task
            raise RuntimeError("Recording ended before acknowledgement.")
        raise TimeoutError("Microphone did not acknowledge the command.")
    finally:
        waiter.cancel()
        await asyncio.gather(waiter, return_exceptions=True)
