"""
STAGE 3 (after meeting): meeting minutes.

    POST /api/v1/meetings/{id}/minutes/generate  drafts (or redrafts) the minutes     processing|review -> review
    GET  /api/v1/meetings/{id}/minutes           read the current minutes
    PUT  /api/v1/meetings/{id}/minutes           the user edits the markdown (also after confirming)
    POST /api/v1/meetings/{id}/minutes/confirm   the user confirms                  review -> archived

Contract: docs/system_design/api-contract.md §5.8 and §6.12
"""

import shutil

from fastapi import APIRouter

from ..database.storage import CloudStorageError
from ..minutes_extractor.minutes_extractor import assemble_markdown, build_minutes, extract_summary
from ..utils.objects import Meeting, Minutes, MinutesEdit
from ..utils.utils import error, now
from .common import CtxDep, SessionDep, meeting_response
from .extractions import catch_up_extractions

router = APIRouter(prefix="/meetings/{meeting_id}/minutes", tags=["post-meeting"])

TRANSCRIPT_FILE = "during_meeting/transcript/transcript.txt"
MINUTES_DRAFT_FILE = "post_meeting/meeting_minutes/minutes_draft.md"
MINUTES_FINAL_FILE = "post_meeting/meeting_minutes/minutes_final.md"


# "review" too: after resolving a conflict the user regenerates so the minutes use the choice.
GENERATE_STATUSES = {"processing", "review"}


def _not_processing(session):
    return error(
        409,
        "INVALID_MEETING_STATE",
        f"Cannot generate minutes while the meeting is '{session.status}'.",
    )


def _unresolved_conflicts(session):
    """The 409 to return while a conflict is open, else None. Call with the lock held."""
    open_ids = [c["id"] for c in session.get("conflicts") or [] if not c["resolved"]]
    if not open_ids:
        return None
    return error(
        409,
        "UNRESOLVED_CONFLICTS",
        f"Choose a value for every conflict first: {', '.join(open_ids)}.",
    )


@router.post("/generate", response_model=Minutes)
def generate_minutes(session: SessionDep, ctx: CtxDep):
    """
    FRONT END SENDS:  nothing (POST with empty body)
    BACK END RETURNS: Minutes object (status="draft"). decisions, action_items and
                      unresolved_issues come from the extractions as the user reviewed
                      them; the LLM only writes the summary.

    Allowed in "processing" and "review" (regenerate; replaces any edited markdown).
    Refused with 409 UNRESOLVED_CONFLICTS while a conflict is open.
    """
    with session:
        if session.status not in GENERATE_STATUSES:
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

    # The minutes must see every item, including sentences the live passes missed.
    catch_up_extractions(session)
    with session:
        blocked = _unresolved_conflicts(session)
        if blocked:
            return blocked
        extractions = [dict(item) for item in session.get("extractions") or []]

    # The LLM call can take seconds, so it runs outside the session lock.
    summary = extract_summary(
        transcript=transcript_text,
        meeting_date=meeting_date,
        agenda_items=agenda_items,
        language=meeting.get("language", "en"),
        extractions=extractions,
    )

    with session:
        # Re-check: the status may have changed while the LLM was running.
        if session.status not in GENERATE_STATUSES:
            return _not_processing(session)
        # Re-read: a value chosen for a conflict while the LLM ran still counts.
        extraction = build_minutes(summary, session.get("extractions") or [])
        markdown = assemble_markdown(
            extraction=extraction,
            meeting_id=session.id,
            meeting_topic=meeting.get("topic", ""),
            meeting_date=meeting_date,
            language=meeting.get("language", "en"),
        )

        session.path(MINUTES_DRAFT_FILE).write_text(markdown, encoding="utf-8")
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
        ctx.meeting_repository.save_minutes(session.id, minutes, status="review")
        session.emplace("minutes", minutes)
        session.status = "review"
        return dict(minutes)


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
def update_minutes(body: MinutesEdit, session: SessionDep, ctx: CtxDep):
    """
    FRONT END SENDS:  { "markdown": "..." }
    BACK END RETURNS: Updated Minutes object. Allowed in "review" and, after confirming, in "archived".
    """
    with session:
        if session.status not in {"review", "archived"}:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Minutes can only be edited while the meeting is in 'review' or 'archived' status "
                f"(current: '{session.status}').",
            )

        minutes = session.get("minutes")
        if minutes is None:
            return error(409, "MINUTES_NOT_READY", "No minutes to edit yet.")

        updated_at = now()
        ctx.meeting_repository.update_minutes_markdown(
            session.id, body.markdown, updated_at
        )
        minutes["markdown"] = body.markdown
        minutes["updated_at"] = updated_at
        return dict(minutes)


@router.post("/confirm", response_model=Meeting)
def confirm_minutes(session: SessionDep, ctx: CtxDep):
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

        updated_at = now()
        blocked = _unresolved_conflicts(session)
        if blocked:
            return blocked

        session.path(MINUTES_FINAL_FILE).write_text(
            minutes["markdown"], encoding="utf-8"
        )
        try:
            ctx.cloud_storage.upload_meeting_directory(session.id, session.root)
        except CloudStorageError as exc:
            return error(502, "STORAGE_UPLOAD_FAILED", str(exc))

        ctx.meeting_repository.confirm_minutes(session.id, updated_at)
        # Only delete local files after cloud upload and DB archival succeed.
        if session.root.exists():
            shutil.rmtree(session.root, ignore_errors=True)

        minutes["status"] = "confirmed"
        minutes["updated_at"] = updated_at
        session.status = "archived"
        return meeting_response(session)
