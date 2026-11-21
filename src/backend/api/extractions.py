"""
STAGE 2/3: what the LLM pulled out of the conversation.

    GET /api/v1/meetings/{id}/extractions?type=action_item,decision

Contract: docs/system_design/api-contract.md §5.4 and §6.10
"""

from fastapi import APIRouter

from ..extraction.extractor import TYPES, extract_pass
from ..utils.objects import ExtractionList
from ..utils.utils import error, now
from .common import SessionDep

router = APIRouter(prefix="/meetings/{meeting_id}/extractions", tags=["extractions"])

# While recording, the live socket fills the list; a GET only reads it back (page refresh).
LIVE_STATUSES = {"live", "paused"}
# After the recording stops, a GET also covers sentences the live passes did not reach.
DONE_STATUSES = {"processing", "review", "archived"}


@router.get("", response_model=ExtractionList)
def read_extractions(session: SessionDep, type: str | None = None):
    """
    BACK END RETURNS: {items: Extraction[]}. During the meeting: what the live passes
    captured so far. After it: the first call runs the LLM on the sentences not covered yet
    (all of them for a batch transcript); later calls read the stored list back.
    `type`: optional, comma-separated decision | action_item | deadline | unresolved_issue.
    """
    wanted = None
    if type:
        wanted = {part.strip() for part in type.split(",")}
        if not wanted <= set(TYPES):
            return error(422, "INVALID_TYPE", f"type must be among: {', '.join(TYPES)}")

    with session:
        status = session.status
        if status not in LIVE_STATUSES | DONE_STATUSES:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Extractions exist once the meeting has started (current: '{status}').",
            )
        items = list(session.get("extractions") or [])
        cursor = session.get("extraction_cursor", 0)
        segments = list(session.get("transcript", []))
        meeting = dict(session.at("meeting"))
        agenda = [dict(item) for item in session.get("agenda", [])]

    if status in DONE_STATUSES and cursor < len(segments):
        # The LLM call can take seconds, so it runs outside the session lock.
        meeting_date = (meeting.get("ended_at") or now())[:10]
        built, _ = extract_pass(segments, cursor, items, session.id, meeting_date, agenda)
        with session:
            # shortcut: two simultaneous calls both hit the LLM and the last write
            # wins. Add a per-session lock if that ever costs real money.
            if session.get("extraction_cursor", 0) == cursor:
                session.emplace("extractions", built)
                session.emplace("extraction_cursor", len(segments))
            items = list(session.get("extractions"))
    elif status in DONE_STATUSES and not segments:
        return error(
            409,
            "TRANSCRIPT_NOT_FOUND",
            "There are no transcript segments yet. Finish transcribing first.",
        )

    if wanted is not None:
        items = [item for item in items if item["type"] in wanted]
    return {"items": items}
