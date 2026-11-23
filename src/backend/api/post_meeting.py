"""
STAGE 3 (after meeting): meeting minutes.

    POST /api/v1/meetings/{id}/minutes/generate  LLM extracts & drafts the minutes   processing -> review
    GET  /api/v1/meetings/{id}/minutes           read the current minutes
    PUT  /api/v1/meetings/{id}/minutes           the user edits the markdown
    POST /api/v1/meetings/{id}/minutes/confirm   the user confirms                  review -> archived

Contract: docs/system_design/api-contract.md §5.8 and §6.12
"""

import asyncio
import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse

from ..minutes_extractor.minutes_extractor import assemble_markdown, extract_minutes
from ..utils.objects import Meeting, Minutes, MinutesEdit
from ..utils.utils import error, now
from ..utils.llm import LLMCallError
from .common import SessionDep, meeting_response

router = APIRouter(prefix="/meetings/{meeting_id}/minutes", tags=["post-meeting"])

TRANSCRIPT_FILE = "during_meeting/transcript/transcript.txt"
MINUTES_DRAFT_FILE = "post_meeting/meeting_minutes/minutes_draft.md"
MINUTES_FINAL_FILE = "post_meeting/meeting_minutes/minutes_final.md"


def _not_processing(session):
    return error(
        409,
        "INVALID_MEETING_STATE",
        f"Cannot generate minutes while the meeting is '{session.status}'. "
        "Stop the recording first.",
    )


def _generate_minutes(session):
    """
    FRONT END SENDS:  nothing (POST with empty body)
    BACK END RETURNS: Minutes object (status="draft") with summary, decisions,
                      action_items and unresolved_issues extracted by the LLM.

    Allowed while meeting status is "processing".
    Reads the transcript stored in the session (or transcript.txt on disk as fallback).
    """
    with session:
        if session.status != "processing":
            return _not_processing(session)

        transcript_text = session.get("transcript_text")
        if transcript_text is None:
            transcript_path = session.path(TRANSCRIPT_FILE)
            if not transcript_path.is_file():
                return error(
                    409,
                    "TRANSCRIPT_NOT_FOUND",
                    "No transcript file found. Run POST .../transcribe before generating minutes.",
                )
            transcript_text = transcript_path.read_text(encoding="utf-8")

        meeting = dict(session.at("meeting"))
        meeting_date = (meeting.get("ended_at") or now())[:10]  # "YYYY-MM-DD"
        agenda_items = list(session.get("agenda", []))

    # The LLM call can take seconds, so it runs outside the session lock.
    extraction = extract_minutes(
        transcript=transcript_text,
        meeting_date=meeting_date,
        agenda_items=agenda_items,
    )
    markdown = assemble_markdown(
        extraction=extraction,
        meeting_id=session.id,
        meeting_topic=meeting.get("topic", ""),
        meeting_date=meeting_date,
    )

    with session:
        # Re-check: the status may have changed while the LLM was running.
        if session.status != "processing":
            return _not_processing(session)

        session.path(MINUTES_DRAFT_FILE).write_text(markdown, encoding="utf-8")
        summary_path = session.path("post_meeting/summary/final_summary.md")
        temporary = summary_path.with_suffix(".tmp")
        temporary.write_text(extraction.summary, encoding="utf-8")
        temporary.replace(summary_path)
        minutes = {
            "meeting_id": session.id,
            "status": "draft",
            "summary": extraction.summary,
            "decisions": extraction.decisions,
            "action_items": [item.model_dump() for item in extraction.action_items],
            "unresolved_issues": extraction.unresolved_issues,
            "markdown": markdown,
            "updated_at": now(),
        }
        session.emplace("minutes", minutes)
        session.status = "review"
        return dict(minutes)


@router.post("/generate", response_model=Minutes)
async def generate_minutes(session: SessionDep):
    # This function and the automatic post-recording task share one lock.
    lock = session.get("minutes_lock")
    if lock is None:
        lock = asyncio.Lock()
        session.emplace("minutes_lock", lock)
    async with lock:
        if session.has("minutes"):
            return dict(session.at("minutes"))
        realtime = session.get("realtime")
        if realtime and not realtime.transcript_saved:
            return error(409, "TRANSCRIPT_NOT_READY", "Transcript has not finished saving.")
        try:
            result = await asyncio.to_thread(_generate_minutes, session)
        except LLMCallError as exc:
            result = error(exc.status, exc.code, str(exc))
        except Exception:
            logging.getLogger(__name__).exception("Minutes failed for %s", session.id)
            result = error(500, "MINUTES_FAILED", "Could not generate minutes; retry is available.")
        if realtime:
            if isinstance(result, JSONResponse):
                import json
                detail = json.loads(result.body).get("error", {})
                realtime.pipeline_error = {"code": detail.get("code", "MINUTES_FAILED"),
                    "message": detail.get("message", "Could not generate minutes."),
                    "recoverable": True}
                await realtime.publish("error", realtime.pipeline_error)
            else:
                realtime.pipeline_error = None
                await realtime.publish("meeting.status", {"status": session.status})
                await realtime.publish("minutes.ready", {
                    "minutes_url": f"/api/v1/meetings/{session.id}/minutes"})
        return result


@router.get("", response_model=Minutes)
def read_minutes(session: SessionDep):
    """
    FRONT END SENDS:  nothing
    BACK END RETURNS: Minutes object (draft or confirmed). Used after a page refresh or a reconnect.
    """
    with session:
        minutes = session.get("minutes")
        if minutes is None:
            return error(
                409,
                "MINUTES_NOT_READY",
                "Minutes have not been generated yet. Call POST .../minutes/generate first.",
            )
        return dict(minutes)


@router.put("", response_model=Minutes)
def update_minutes(body: MinutesEdit, session: SessionDep):
    """
    FRONT END SENDS:  { "markdown": "..." }
    BACK END RETURNS: Updated Minutes object. Only allowed while meeting status is "review".
    """
    with session:
        if session.status != "review":
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Minutes can only be edited while the meeting is in 'review' status "
                f"(current: '{session.status}').",
            )

        minutes = session.get("minutes")
        if minutes is None:
            return error(409, "MINUTES_NOT_READY", "No minutes to edit yet.")

        minutes["markdown"] = body.markdown
        minutes["updated_at"] = now()
        return dict(minutes)


@router.post("/confirm", response_model=Meeting)
def confirm_minutes(session: SessionDep):
    """
    FRONT END SENDS:  nothing (POST with empty body)
    BACK END RETURNS: Meeting with status "archived".
    Saves the final Markdown to disk and closes the meeting. Only allowed in "review".
    """
    with session:
        if session.status != "review":
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Cannot confirm minutes while the meeting is '{session.status}'.",
            )

        minutes = session.get("minutes")
        if minutes is None:
            return error(409, "MINUTES_NOT_READY", "No minutes to confirm yet.")

        session.path(MINUTES_FINAL_FILE).write_text(minutes["markdown"], encoding="utf-8")
        minutes["status"] = "confirmed"
        minutes["updated_at"] = now()
        session.status = "archived"
        return meeting_response(session)
