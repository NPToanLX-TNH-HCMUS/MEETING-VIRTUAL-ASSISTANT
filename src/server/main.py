"""
Meeting Virtual Assistant - backend stub for the BEFORE-meeting flow.

What the front end (frontend/js/main.js -> frontend/js/api.js) calls, in order:

    1. POST /api/v1/meetings                        create the meeting (topic, duration, planned points)
    2. POST /api/v1/meetings/{id}/documents         upload each .md/.txt file, one request per file
    3. POST /api/v1/meetings/{id}/agenda/generate   build a PROPOSED agenda from steps 1 + 2
    4. PUT  /api/v1/meetings/{id}/agenda            the user confirms the (edited) agenda
    5. GET  /api/v1/meetings/{id}                   the UI re-reads the status after confirming

Every endpoint below has a "FRONT END SENDS" / "BACK END RETURNS" note, and the request and
response shapes are Pydantic models, so http://127.0.0.1:8000/docs shows them too.
Contract: docs/system_design/api-contract.md (sections 5 and 6).

"""

import re
from datetime import datetime
from typing import Literal

from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse

from .objects import *
from .llm_common import LLMError
from .openrouter_agenda import extract_topics

app = FastAPI()

# Kept in memory: every restart (including uvicorn --reload after you save this file) empties it.
# meetings[meeting_id] = {
#     "meeting":   Meeting fields (what GET /meetings/{id} returns),
#     "documents": [ {document fields..., "text": str, "headings": [str, ...]} ],
#     "agenda":    [ AgendaItem fields ]   (proposed, then confirmed),
# }
meetings: dict[str, dict] = {}


# ======================================================================================
# Helpers
# ======================================================================================


def now() -> str:
    # ISO 8601 with the local UTC offset, e.g. 2026-10-28T16:30:00+07:00 (contract section 1).
    return datetime.now().astimezone().isoformat(timespec="seconds")


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(status_code=status, content={"error": {"code": code, "message": message, "details": {}}})


def meeting_not_found(meeting_id: str) -> JSONResponse:
    return error(404, "MEETING_NOT_FOUND", f"No meeting with id {meeting_id}")


def log(step: str, data) -> None:
    # Shows in the uvicorn terminal, so you can watch what goes between front and back end.
    print(f"[BACKEND] {step}: {data}")


# ======================================================================================
# 0. GET /api/v1/health
# ======================================================================================


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "mock_mode": True}


# ======================================================================================
# 1. POST /api/v1/meetings  - create the meeting
# ======================================================================================


@app.post("/api/v1/meetings", status_code=201, response_model=Meeting)
def create_meeting(body: NewMeeting):
    """
    FRONT END SENDS:  NewMeeting Object
    BACK END RETURNS: Meeting, status "draft". The UI keeps meeting.id for every later call.
    """
    log("1. create meeting, received", body.model_dump())

    meeting_id = f"mtg_{len(meetings) + 1:03d}"
    meeting = {
        "id": meeting_id,
        "topic": body.topic,
        "language": body.language,
        "duration_minutes": body.duration_minutes,
        "status": "draft",
        "planned_points": body.planned_points,
        "previous_meeting_id": body.previous_meeting_id,
        "created_at": now(),
        "started_at": None,
        "ended_at": None,
    }
    meetings[meeting_id] = {"meeting": meeting, "documents": [], "agenda": []}
    return meeting


@app.get("/api/v1/meetings/{meeting_id}", response_model=Meeting)
def read_meeting(meeting_id: str):
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)
    return meetings[meeting_id]["meeting"]


# ======================================================================================
# 2. POST /api/v1/meetings/{id}/documents  - upload one file
# ======================================================================================

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MIME_TYPES = {".md": "markdown", ".txt": "text"}
HEADING = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$")


def split_markdown_headings(text: str) -> list[str]:
    """'# Plan\\n## Demo recorder\\n...' -> ['Plan', 'Demo recorder']. Skips lines inside ``` code blocks."""
    headings = []
    in_code = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            in_code = not in_code
            continue
        match = HEADING.match(line)
        if match and not in_code:
            headings.append(match.group(2))
    return headings


@app.post("/api/v1/meetings/{meeting_id}/documents", status_code=201, response_model=Document)
async def upload_document(meeting_id: str, file: UploadFile):
    """
    FRONT END SENDS:  multipart/form-data with one field "file"
    BACK END RETURNS: Document (no file content in the reply)
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)

    filename = file.filename or ""
    extension = filename[filename.rfind("."):].lower() if "." in filename else ""
    if extension not in MIME_TYPES:
        return error(415, "UNSUPPORTED_FILE_TYPE", f"Only .md and .txt are accepted, got {filename!r}")

    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        return error(413, "FILE_TOO_LARGE", f"{filename} is larger than 10 MB")

    # utf-8-sig also removes the BOM some Windows editors add; Vietnamese diacritics are kept.
    text = content.decode("utf-8-sig", errors="replace")
    headings = split_markdown_headings(text) if extension == ".md" else []

    stored = meetings[meeting_id]
    document = {
        "id": f"doc_{sum(len(m['documents']) for m in meetings.values()) + 1:03d}",
        "meeting_id": meeting_id,
        "filename": filename,
        "mime_type": MIME_TYPES[extension],
        "size_bytes": len(content),
        "uploaded_at": now(),
    }
    stored["documents"].append({**document, "text": text, "headings": headings})
    log("2. upload document, received", {"filename": filename, "size_bytes": len(content), "headings": headings})
    return document


# ======================================================================================
# 3. POST /api/v1/meetings/{id}/agenda/generate  - build the PROPOSED agenda
# ======================================================================================

# PLACEHOLDER: the real time comes from the Time Estimation step (default table per category,
# later the average of past meetings). Until then every item gets the same value.
PLACEHOLDER_MINUTES = 10

# The agenda can be (re)generated or (re)confirmed until the meeting starts.
AGENDA_EDITABLE = {"draft", "ready"}


def build_candidates(meeting_id: str) -> list[dict]:
    stored = meetings[meeting_id]
    meeting = stored["meeting"]

    # The LLM reads the planned points and the document texts together, and sizes the topics to the
    # meeting length (see openrouter_agenda.py). The user can still change each time in the UI.
    candidates = extract_topics(meeting["planned_points"], stored["documents"], meeting["duration_minutes"])

    for candidate in candidates:
        candidate.update(importance=None, urgency=None, relevance=None, priority_score=None,
                         estimated_minutes=candidate.get("estimated_minutes") or PLACEHOLDER_MINUTES)
    return candidates


def select_by_time(candidates: list[dict], duration: int) -> tuple[list[dict], list[dict]]:
    remaining = duration
    chosen, dropped = [], []
    for candidate in candidates:
        if candidate["estimated_minutes"] <= remaining:
            remaining -= candidate["estimated_minutes"]
            chosen.append(candidate)
        else:
            dropped.append({"title": candidate["title"], "reason": "exceeds_remaining_time",
                            "estimated_minutes": candidate["estimated_minutes"]})
    return chosen, dropped


@app.post("/api/v1/meetings/{meeting_id}/agenda/generate", response_model=AgendaProposal)
def generate_agenda(meeting_id: str):
    """
    BACK END RETURNS: AgendaProposal = {items, dropped, total_estimated_minutes, duration_minutes}
    The UI shows items in "order" and lists "dropped". Nothing is official until step 4.
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)
    meeting = meetings[meeting_id]["meeting"]
    if meeting["status"] not in AGENDA_EDITABLE:
        return error(409, "INVALID_MEETING_STATE", f"Agenda cannot change while the meeting is {meeting['status']}")

    try:
        candidates = build_candidates(meeting_id)
    except LLMError as e:  # contract: 503 LLM_UNAVAILABLE / 422 LLM_BAD_OUTPUT
        return error(e.status, e.code, str(e))
    chosen, dropped = select_by_time(candidates, meeting["duration_minutes"])

    items = [
        {
            **candidate,
            "id": f"agd_{order:03d}",
            "meeting_id": meeting_id,
            "order": order,
            "state": "not_discussed",
            "started_at": None,
            "ended_at": None,
            "needs_confirmation": True,
        }
        for order, candidate in enumerate(chosen, start=1)
    ]
    meetings[meeting_id]["agenda"] = items
    meeting["status"] = "draft"  # a new proposal is not confirmed yet

    result = {
        "items": items,
        "dropped": dropped,
        "total_estimated_minutes": sum(item["estimated_minutes"] for item in items),
        "duration_minutes": meeting["duration_minutes"],
    }
    log("3. generate agenda, returning", {"items": [i["title"] for i in items], "dropped": [d["title"] for d in dropped]})
    return result


# ======================================================================================
# 4. PUT /api/v1/meetings/{id}/agenda  - the user confirms   |   GET  - read it back
# ======================================================================================




@app.put("/api/v1/meetings/{meeting_id}/agenda", response_model=AgendaList)
def save_agenda(meeting_id: str, body: AgendaEdit):
    """
    FRONT END SENDS:  AgendaEdit = {items: [{id, title, estimated_minutes, order}]}
    BACK END RETURNS: AgendaList = {items: AgendaItem[]} with full fields; meeting becomes "ready".
    Fields the user cannot edit (source, scores) are kept from the proposal.
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)
    stored = meetings[meeting_id]
    # "ready" is allowed too: the user can edit and confirm again before the meeting starts.
    if stored["meeting"]["status"] not in AGENDA_EDITABLE:
        return error(409, "INVALID_MEETING_STATE", f"Agenda cannot change while the meeting is {stored['meeting']['status']}")
    log("4. confirm agenda, received", [item.model_dump() for item in body.items])

    proposed = {item["id"]: item for item in stored["agenda"]}
    saved = []
    for edit in sorted(body.items, key=lambda item: item.order):
        base = proposed.get(edit.id)
        if base is None:  # added by hand in the UI
            base = {"description": None, "source": "manual", "importance": None, "urgency": None,
                    "relevance": None, "priority_score": None, "state": "not_discussed",
                    "started_at": None, "ended_at": None}
        saved.append({
            **base,
            "id": edit.id if edit.id in proposed else f"agd_m{len(saved) + 1:03d}",
            "meeting_id": meeting_id,
            "title": edit.title,
            "estimated_minutes": edit.estimated_minutes,
            "order": len(saved) + 1,
            "needs_confirmation": False,
        })

    stored["agenda"] = saved
    stored["meeting"]["status"] = "ready"
    return {"items": saved}


@app.get("/api/v1/meetings/{meeting_id}/agenda", response_model=AgendaList)
def read_agenda(meeting_id: str):
    """
    FRONT END SENDS:  nothing
    BACK END RETURNS: AgendaList (the proposed or confirmed agenda; used after a page refresh)
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)
    return {"items": meetings[meeting_id]["agenda"]}
