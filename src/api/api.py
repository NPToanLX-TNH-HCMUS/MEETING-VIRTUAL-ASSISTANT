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
import tempfile
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, UploadFile
from fastapi.responses import JSONResponse

from ..backend.agenda_extractor.agenda_extractor import extract_topics
from ..backend.audio.recorder import Recorder
from ..backend.document.markdown_converter import FileConversionError, MarkDownConverter
from ..backend.during_meeting.agenda import receive_agenda
from ..backend.meeting_manager.meeting_manager import MeetingManager
from ..backend.meeting_manager.storage_manager import StorageManager
from ..backend.minutes_extractor.minutes_extractor import (
    assemble_markdown,
    extract_minutes,
)
from ..backend.speech_to_text.transcriber import (
    AudioTranscriptionError,
    ElevenLabsTranscriber,
)
from ..backend.utils.llm import LLMCallError
from .objects import *

app = FastAPI()
meeting_manager = MeetingManager(StorageManager())

# Kept in memory: every restart (including uvicorn --reload after you save this file) empties it.
# meetings[meeting_id] = {
#     "meeting":   Meeting fields (what GET /meetings/{id} returns),
#     "documents": [ {document fields..., "text": str, "headings": [str, ...]} ],
#     "agenda":    [ AgendaItem fields ]   (proposed, then confirmed),
#     "context":   MeetingContext (id + data/<id>/ folders from MeetingManager),
#     "minutes":   Minutes fields dict | None  (None until /minutes/generate is called),
# }
meetings: dict[str, dict] = {}


# ======================================================================================
# Helpers
# ======================================================================================


def now() -> str:
    # ISO 8601 with the local UTC offset, e.g. 2026-10-28T16:30:00+07:00 (contract section 1).
    return datetime.now().astimezone().isoformat(timespec="seconds")


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": {}}},
    )


def meeting_not_found(meeting_id: str) -> JSONResponse:
    return error(404, "MEETING_NOT_FOUND", f"No meeting with id {meeting_id}")


def log(step: str, data) -> None:
    # print(f"[BACKEND] {step}: {data}")
    pass


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

    context = meeting_manager.create_meeting()  # unique id + data/<id>/ folders
    meeting_id = context.meeting_id
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
    meetings[meeting_id] = {
        "meeting": meeting,
        "documents": [],
        "agenda": [],
        "context": context,
        "minutes": None,
    }
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
MIME_TYPES = {
    ".md": "markdown",
    ".txt": "text",
    ".pdf": "pdf",
    ".docx": "docx",
    ".doc": "doc",
}
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


converter = MarkDownConverter()


def convert_to_markdown(content: bytes, extension: str) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"upload{extension}"
        source.write_bytes(content)
        return converter.convert(source, Path(tmp) / "upload.md").read_text(
            encoding="utf-8"
        )


@app.post(
    "/api/v1/meetings/{meeting_id}/documents", status_code=201, response_model=Document
)
async def upload_document(meeting_id: str, file: UploadFile):
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)

    filename = file.filename or ""
    extension = filename[filename.rfind(".") :].lower() if "." in filename else ""
    if extension not in MIME_TYPES:
        return error(
            415,
            "UNSUPPORTED_FILE_TYPE",
            f"Only .md, .txt, .pdf and .docx are accepted, got {filename!r}",
        )

    content = await file.read()
    if len(content) > MAX_FILE_BYTES:
        return error(413, "FILE_TOO_LARGE", f"{filename} is larger than 10 MB")

    if extension in MarkDownConverter.SUPPORTED_EXTENSIONS:
        try:
            text = convert_to_markdown(content, extension)
        except FileConversionError as exc:
            return error(
                415, "UNSUPPORTED_FILE_TYPE", f"Could not read {filename!r}: {exc}"
            )
        headings = split_markdown_headings(text)
    else:
        # utf-8-sig also removes the BOM some Windows editors add.
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

    candidates = extract_topics(
        planned_points=meeting["planned_points"],
        documents=stored["documents"],
        duration_minutes=meeting["duration_minutes"],
        topic=meeting.get("topic", ""),
    )

    for candidate in candidates:
        candidate.update(
            importance=None,
            urgency=None,
            relevance=None,
            priority_score=None,
            estimated_minutes=candidate.get("estimated_minutes") or PLACEHOLDER_MINUTES,
        )
    return candidates


def select_by_time(
    candidates: list[dict], duration: int
) -> tuple[list[dict], list[dict]]:
    remaining = duration
    chosen, dropped = [], []
    for candidate in candidates:
        if candidate["estimated_minutes"] <= remaining:
            remaining -= candidate["estimated_minutes"]
            chosen.append(candidate)
        else:
            dropped.append(
                {
                    "title": candidate["title"],
                    "reason": "exceeds_remaining_time",
                    "estimated_minutes": candidate["estimated_minutes"],
                }
            )
    return chosen, dropped


@app.post(
    "/api/v1/meetings/{meeting_id}/agenda/generate", response_model=AgendaProposal
)
def generate_agenda(meeting_id: str):
    """
    BACK END RETURNS: AgendaProposal = {items, dropped, total_estimated_minutes, duration_minutes}
    The UI shows items in "order" and lists "dropped". Nothing is official until step 4.
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)
    meeting = meetings[meeting_id]["meeting"]
    if meeting["status"] not in AGENDA_EDITABLE:
        return error(
            409,
            "INVALID_MEETING_STATE",
            f"Agenda cannot change while the meeting is {meeting['status']}",
        )

    try:
        candidates = build_candidates(meeting_id)
    except LLMCallError as e:  # contract: 503 LLM_UNAVAILABLE / 422 LLM_BAD_OUTPUT
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
    log(
        "3. generate agenda, returning",
        {
            "items": [i["title"] for i in items],
            "dropped": [d["title"] for d in dropped],
        },
    )
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
        return error(
            409,
            "INVALID_MEETING_STATE",
            f"Agenda cannot change while the meeting is {stored['meeting']['status']}",
        )
    log("4. confirm agenda, received", [item.model_dump() for item in body.items])

    proposed = {item["id"]: item for item in stored["agenda"]}
    saved = []
    for edit in sorted(body.items, key=lambda item: item.order):
        base = proposed.get(edit.id)
        if base is None:  # added by hand in the UI
            base = {
                "description": None,
                "source": "manual",
                "importance": None,
                "urgency": None,
                "relevance": None,
                "priority_score": None,
                "state": "not_discussed",
                "started_at": None,
                "ended_at": None,
            }
        saved.append(
            {
                **base,
                "id": edit.id if edit.id in proposed else f"agd_m{len(saved) + 1:03d}",
                "meeting_id": meeting_id,
                "title": edit.title,
                "estimated_minutes": edit.estimated_minutes,
                "order": len(saved) + 1,
                "needs_confirmation": False,
            }
        )

    stored["agenda"] = saved
    stored["meeting"]["status"] = "ready"
    receive_agenda(meeting_id, saved)
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


# ======================================================================================
# 6. STAGE 2 (during meeting): POST /api/v1/meetings/{id}/recording/start | stop
# ======================================================================================

recorders: dict[str, Recorder] = {}


@app.post("/api/v1/meetings/{meeting_id}/recording/start", response_model=Meeting)
def start_recording(meeting_id: str):
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)
    meeting = meetings[meeting_id]["meeting"]
    if meeting["status"] != "ready":
        return error(
            409,
            "INVALID_MEETING_STATE",
            f"Cannot start recording while the meeting is {meeting['status']}",
        )
    try:
        recorder = Recorder()
        recorder.start()
    except Exception as exc:  # sounddevice raises PortAudioError when there is no microphone / no permission
        return error(500, "RECORDER_FAILED", str(exc))
    recorders[meeting_id] = recorder
    meeting["status"] = "live"
    meeting["started_at"] = now()
    return meeting


@app.post("/api/v1/meetings/{meeting_id}/recording/stop", response_model=Meeting)
def stop_recording(meeting_id: str):
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)
    stored = meetings[meeting_id]
    meeting = stored["meeting"]
    recorder = recorders.pop(meeting_id, None)
    if meeting["status"] != "live" or recorder is None:
        return error(
            409,
            "INVALID_MEETING_STATE",
            f"Cannot stop recording while the meeting is {meeting['status']}",
        )
    path = stored["context"].during_meeting_dir / "audio" / "record.wav"
    recorder.stop(str(path))
    meeting["status"] = "processing"
    meeting["ended_at"] = now()
    return meeting


@app.post("/api/v1/meetings/{meeting_id}/transcribe")
def transcribe_recording(meeting_id: str):
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)
    context = meetings[meeting_id]["context"]
    audio = context.during_meeting_dir / "audio" / "record.wav"
    if not audio.is_file():
        return error(
            409, "INVALID_MEETING_STATE", "There is no recording to transcribe yet"
        )
    try:
        segments = ElevenLabsTranscriber().transcribe_file(
            audio, context.during_meeting_dir / "transcript" / "transcript.txt"
        )
        # Format speaker turns here so the frontend can display the string directly.
        text = "\n\n".join(
            f"[{segment['Timestamp']}] {segment['Speaker']}:\n{segment['Text']}"
            for segment in segments
        )
        print(text)
    except ValueError as exc:  # missing ELEVENLABS_API_KEY, empty or invalid wav
        return error(422, "TRANSCRIPTION_INPUT_INVALID", str(exc))
    except AudioTranscriptionError as exc:
        return error(502, "TRANSCRIPTION_FAILED", str(exc))
    return {"transcript": text}


# ======================================================================================
# 7. STAGE 3 (after meeting): Meeting Minutes
#    POST /api/v1/meetings/{id}/minutes/generate  — LLM extracts & drafts the minutes
#    GET  /api/v1/meetings/{id}/minutes           — read the current minutes
#    PUT  /api/v1/meetings/{id}/minutes           — user edits the markdown
#    POST /api/v1/meetings/{id}/minutes/confirm   — user confirms → archived
#
# Contract: docs/system_design/api-contract.md §5.8 and §6.12
# ======================================================================================

# Statuses that allow reading or editing minutes
_MINUTES_READABLE = {"review", "archived"}
_MINUTES_EDITABLE = {"review"}


@app.post("/api/v1/meetings/{meeting_id}/minutes/generate", response_model=Minutes)
def generate_minutes(meeting_id: str):
    """
    FRONT END SENDS:  nothing (POST with empty body)
    BACK END RETURNS: Minutes object (status="draft") with summary, decisions,
                      action_items and unresolved_issues extracted by the LLM.

    Allowed while meeting status is "processing".
    Reads the transcript written by POST .../transcribe from disk:
        data/<meeting_id>/during_meeting/transcript/transcript.txt
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)

    stored = meetings[meeting_id]
    meeting = stored["meeting"]

    if meeting["status"] != "processing":
        return error(
            409,
            "INVALID_MEETING_STATE",
            f"Cannot generate minutes while the meeting is '{meeting['status']}'. "
            "Stop the recording first.",
        )

    # --- Read transcript from disk ---
    transcript_path = (
        stored["context"].during_meeting_dir / "transcript" / "transcript.txt"
    )
    if not transcript_path.is_file():
        return error(
            409,
            "TRANSCRIPT_NOT_FOUND",
            "No transcript file found. Run POST .../transcribe before generating minutes.",
        )
    transcript_text = transcript_path.read_text(encoding="utf-8")

    ended_at = meeting.get("ended_at") or now()
    meeting_date = ended_at[:10]  # "YYYY-MM-DD"
    agenda_items = stored.get("agenda", [])

    # --- Call LLM ---
    try:
        extraction = extract_minutes(
            transcript=transcript_text,
            meeting_date=meeting_date,
            agenda_items=agenda_items,
        )
    except LLMCallError as exc:
        return error(exc.status, exc.code, str(exc))

    markdown = assemble_markdown(
        extraction=extraction,
        meeting_id=meeting_id,
        meeting_topic=meeting.get("topic", ""),
        meeting_date=meeting_date,
    )

    draft_path = (
        stored["context"].post_meeting_dir / "meeting_minutes" / "minutes_draft.md"
    )
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(markdown, encoding="utf-8")

    minutes_dict = {
        "meeting_id": meeting_id,
        "status": "draft",
        "summary": extraction.summary,
        "decisions": extraction.decisions,
        "action_items": [item.model_dump() for item in extraction.action_items],
        "unresolved_issues": extraction.unresolved_issues,
        "markdown": markdown,
        "updated_at": now(),
    }
    stored["minutes"] = minutes_dict
    meeting["status"] = "review"

    log(
        "7. generate minutes, returning", {"meeting_id": meeting_id, "status": "review"}
    )
    return minutes_dict


@app.get("/api/v1/meetings/{meeting_id}/minutes", response_model=Minutes)
def read_minutes(meeting_id: str):
    """
    FRONT END SENDS:  nothing
    BACK END RETURNS: Minutes object (draft or confirmed).
    Used after a page refresh or a reconnect.
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)

    stored = meetings[meeting_id]
    if stored["minutes"] is None:
        return error(
            409,
            "MINUTES_NOT_READY",
            "Minutes have not been generated yet. Call POST .../minutes/generate first.",
        )
    print(stored['minutes'])
    return stored["minutes"]


@app.put("/api/v1/meetings/{meeting_id}/minutes", response_model=Minutes)
def update_minutes(meeting_id: str, body: MinutesEdit):
    """
    FRONT END SENDS:  { "markdown": "..." }
    BACK END RETURNS: Updated Minutes object.
    Lets the user edit the Markdown draft before confirming.
    Only allowed while meeting status is "review".
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)

    stored = meetings[meeting_id]
    meeting = stored["meeting"]

    if meeting["status"] not in _MINUTES_EDITABLE:
        return error(
            409,
            "INVALID_MEETING_STATE",
            f"Minutes can only be edited while the meeting is in 'review' status "
            f"(current: '{meeting['status']}').",
        )

    if stored["minutes"] is None:
        return error(409, "MINUTES_NOT_READY", "No minutes to edit yet.")

    stored["minutes"]["markdown"] = body.markdown
    stored["minutes"]["updated_at"] = now()
    return stored["minutes"]


@app.post("/api/v1/meetings/{meeting_id}/minutes/confirm", response_model=Meeting)
def confirm_minutes(meeting_id: str):
    """
    FRONT END SENDS:  nothing (POST with empty body)
    BACK END RETURNS: Meeting with status "archived".
    Marks the minutes as confirmed, saves the final Markdown to disk,
    and closes the meeting.
    Only allowed while meeting status is "review".
    """
    if meeting_id not in meetings:
        return meeting_not_found(meeting_id)

    stored = meetings[meeting_id]
    meeting = stored["meeting"]

    if meeting["status"] != "review":
        return error(
            409,
            "INVALID_MEETING_STATE",
            f"Cannot confirm minutes while the meeting is '{meeting['status']}'.",
        )

    if stored["minutes"] is None:
        return error(409, "MINUTES_NOT_READY", "No minutes to confirm yet.")

    # Persist final Markdown to disk
    final_path = (
        stored["context"].post_meeting_dir / "meeting_minutes" / "minutes_final.md"
    )
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(stored["minutes"]["markdown"], encoding="utf-8")

    # Finalise state
    stored["minutes"]["status"] = "confirmed"
    stored["minutes"]["updated_at"] = now()
    meeting["status"] = "archived"

    log("7. confirm minutes", {"meeting_id": meeting_id, "status": "archived"})
    return meeting
