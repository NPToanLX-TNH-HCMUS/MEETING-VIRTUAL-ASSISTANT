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
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Annotated

from fastapi import Depends, FastAPI, Request, UploadFile

from .agenda_extractor.agenda_extractor import extract_topics
from .audio.recorder import Recorder
from .context.app_context import *
from .context.session import *
from .document.markdown_converter import FileConversionError, MarkDownConverter
from .minutes_extractor.minutes_extractor import (
    assemble_markdown,
    extract_minutes,
)
from .speech_to_text.transcriber import (
    AudioTranscriptionError,
    ElevenLabsTranscriber,
)
from .utils.llm import LLMCallError
from .utils.objects import *
from .utils.utils import *


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "ctx"):
        app.state.ctx = AppContext()
    yield
    # Clean up any active microphone stream on server shutdown / reload.
    for session in app.state.ctx.sessions():
        with session:
            recorder = session.pop("recorder")
            if recorder is not None and recorder.is_recording:
                recorder.stop(str(session.path("during_meeting/audio/record.wav")))


app = FastAPI(lifespan=lifespan)
app.state.ctx = AppContext()


@app.exception_handler(MeetingNotFoundError)
def handle_meeting_not_found(_request: Request, exc: MeetingNotFoundError):
    meeting_id = exc.args[0] if exc.args else str(exc)
    return meeting_not_found(meeting_id)


@app.exception_handler(MissingContextError)
def handle_missing_context(_request: Request, exc: MissingContextError):
    message = exc.args[0] if exc.args else str(exc)
    return error(409, "INVALID_MEETING_STATE", message)


@app.exception_handler(LLMCallError)
def handle_llm_error(_request: Request, exc: LLMCallError):
    return error(exc.status, exc.code, str(exc))


def _set_status(session: MeetingSession, status: str, **meeting_updates) -> dict:
    """Keep session.status and the serialized meeting dict in sync."""
    session.status = status
    meeting = session.at("meeting")
    meeting["status"] = status
    meeting.update(meeting_updates)
    return dict(meeting)


def log(mess: str):
    pass


# GET /api/v1/health


@app.get("/api/v1/health")
def health():
    return {"status": "ok", "mock_mode": False}


# POST /api/v1/meetings  - create the meeting


@app.post("/api/v1/meetings", status_code=201, response_model=Meeting)
def create_meeting(body: NewMeeting, ctx: Annotated[AppContext, Depends(get_ctx)]):
    """
    FRONT END SENDS:  NewMeeting Object
    BACK END RETURNS: Meeting, status "draft". The UI keeps meeting.id for every later call.
    """
    session = ctx.create_session()
    meeting = {
        "id": session.id,
        "topic": body.topic,
        "language": body.language,
        "duration_minutes": body.duration_minutes,
        "status": session.status,
        "planned_points": body.planned_points,
        "previous_meeting_id": body.previous_meeting_id,
        "created_at": now(),
        "started_at": None,
        "ended_at": None,
    }
    with session:
        session.emplace("meeting", meeting)
        session.emplace("documents", [])
        session.emplace("agenda", [])
    return meeting


@app.get("/api/v1/meetings/{meeting_id}", response_model=Meeting)
def read_meeting(session: Annotated[MeetingSession, Depends(get_session)]):
    with session:
        return dict(session.at("meeting"))


# POST /api/v1/meetings/{id}/documents  - upload one file

MAX_FILE_BYTES = 10 * 1024 * 1024  # 10 MB
MIME_TYPES = {
    ".md": "markdown",
    ".txt": "text",
    ".pdf": "pdf",
    ".docx": "docx",
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


def convert_to_markdown(
    converter: MarkDownConverter, content: bytes, extension: str
) -> str:
    with tempfile.TemporaryDirectory() as tmp:
        source = Path(tmp) / f"upload{extension}"
        source.write_bytes(content)
        return converter.convert(source, Path(tmp) / "upload.md").read_text(
            encoding="utf-8"
        )


@app.post(
    "/api/v1/meetings/{meeting_id}/documents", status_code=201, response_model=Document
)
async def upload_document(
    file: UploadFile,
    session: Annotated[MeetingSession, Depends(get_session)],
    ctx: Annotated[AppContext, Depends(get_ctx)],
):
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
            text = convert_to_markdown(ctx.converter, content, extension)
        except FileConversionError as exc:
            return error(
                415, "UNSUPPORTED_FILE_TYPE", f"Could not read {filename!r}: {exc}"
            )
        headings = split_markdown_headings(text)
    else:
        # utf-8-sig also removes the BOM some Windows editors add.
        text = content.decode("utf-8-sig", errors="replace")
        headings = split_markdown_headings(text) if extension == ".md" else []

    with session:
        documents = session.at("documents")
        document = {
            "id": f"doc_{len(documents) + 1:03d}",
            "meeting_id": session.id,
            "filename": filename,
            "mime_type": MIME_TYPES[extension],
            "size_bytes": len(content),
            "uploaded_at": now(),
        }
        documents.append({**document, "text": text, "headings": headings})

    return document


# POST /api/v1/meetings/{id}/agenda/generate  - build the PROPOSED agenda

# PLACEHOLDER: the real time comes from the Time Estimation step (default table per category,
# later the average of past meetings). Until then every item gets the same value.
PLACEHOLDER_MINUTES = 10

# The agenda can be (re)generated or (re)confirmed until the meeting starts.
AGENDA_EDITABLE = {"draft", "ready"}


def build_candidates(meeting: dict, documents: list[dict]) -> list[dict]:
    candidates = extract_topics(
        planned_points=meeting["planned_points"],
        documents=documents,
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
def generate_agenda(session: Annotated[MeetingSession, Depends(get_session)]):
    """
    BACK END RETURNS: AgendaProposal = {items, dropped, total_estimated_minutes, duration_minutes}
    The UI shows items in "order" and lists "dropped". Nothing is official until step 4.
    """
    with session:
        if session.status not in AGENDA_EDITABLE:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Agenda cannot change while the meeting is {session.status}",
            )
        meeting = dict(session.at("meeting"))
        documents = [dict(doc) for doc in session.at("documents")]

    candidates = build_candidates(meeting, documents)
    chosen, dropped = select_by_time(candidates, meeting["duration_minutes"])

    items = [
        {
            **candidate,
            "id": f"agd_{order:03d}",
            "meeting_id": session.id,
            "order": order,
            "state": "not_discussed",
            "started_at": None,
            "ended_at": None,
            "needs_confirmation": True,
        }
        for order, candidate in enumerate(chosen, start=1)
    ]

    with session:
        if session.status not in AGENDA_EDITABLE:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Agenda cannot change while the meeting is {session.status}",
            )
        session.emplace("agenda", items)
        _set_status(session, "draft")  # a new proposal is not confirmed yet

    return {
        "items": items,
        "dropped": dropped,
        "total_estimated_minutes": sum(item["estimated_minutes"] for item in items),
        "duration_minutes": meeting["duration_minutes"],
    }


# PUT /api/v1/meetings/{id}/agenda  - the user confirms   |   GET  - read it back


@app.put("/api/v1/meetings/{meeting_id}/agenda", response_model=AgendaList)
def save_agenda(
    body: AgendaEdit,
    session: Annotated[MeetingSession, Depends(get_session)],
):
    """
    FRONT END SENDS:  AgendaEdit = {items: [{id, title, estimated_minutes, order}]}
    BACK END RETURNS: AgendaList = {items: AgendaItem[]} with full fields; meeting becomes "ready".
    Fields the user cannot edit (source, scores) are kept from the proposal.
    """
    with session:
        # "ready" is allowed too: the user can edit and confirm again before the meeting starts.
        if session.status not in AGENDA_EDITABLE:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Agenda cannot change while the meeting is {session.status}",
            )

        proposed = {item["id"]: item for item in session.at("agenda")}
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
                    "id": edit.id
                    if edit.id in proposed
                    else f"agd_m{len(saved) + 1:03d}",
                    "meeting_id": session.id,
                    "title": edit.title,
                    "estimated_minutes": edit.estimated_minutes,
                    "order": len(saved) + 1,
                    "needs_confirmation": False,
                }
            )

        session.emplace("agenda", saved)
        _set_status(session, "ready")
        return {"items": saved}


@app.get("/api/v1/meetings/{meeting_id}/agenda", response_model=AgendaList)
def read_agenda(session: Annotated[MeetingSession, Depends(get_session)]):
    """
    FRONT END SENDS:  nothing
    BACK END RETURNS: AgendaList (the proposed or confirmed agenda; used after a page refresh)
    """
    with session:
        return {"items": list(session.at("agenda"))}


# =======================================================================================
# STAGE 2 (during meeting): POST /api/v1/meetings/{id}/recording/start | stop


@app.post("/api/v1/meetings/{meeting_id}/recording/start", response_model=Meeting)
def start_recording(session: Annotated[MeetingSession, Depends(get_session)]):
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
        return _set_status(session, "live", started_at=now())


@app.post("/api/v1/meetings/{meeting_id}/recording/stop", response_model=Meeting)
def stop_recording(session: Annotated[MeetingSession, Depends(get_session)]):
    with session:
        recorder = session.get("recorder")
        if session.status != "live" or recorder is None:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Cannot stop recording while the meeting is {session.status}",
            )
        path = session.path("during_meeting/audio/record.wav")
        recorder.stop(str(path))
        session.pop("recorder")
        return _set_status(session, "processing", ended_at=now())


@app.post("/api/v1/meetings/{meeting_id}/transcribe")
def transcribe_recording(session: Annotated[MeetingSession, Depends(get_session)]):
    with session:
        audio = session.path("during_meeting/audio/record.wav")
        if not audio.is_file():
            return error(
                409, "INVALID_MEETING_STATE", "There is no recording to transcribe yet"
            )
        transcript_path = session.path("during_meeting/transcript/transcript.txt")

    try:
        segments = ElevenLabsTranscriber().transcribe_file(audio, transcript_path)
        # Format speaker turns here so the frontend can display the string directly.
        text = "\n\n".join(
            f"[{segment['Timestamp']}] {segment['Speaker']}:\n{segment['Text']}"
            for segment in segments
        )
    except ValueError as exc:  # missing ELEVENLABS_API_KEY, empty or invalid wav
        return error(422, "TRANSCRIPTION_INPUT_INVALID", str(exc))
    except AudioTranscriptionError as exc:
        return error(502, "TRANSCRIPTION_FAILED", str(exc))

    with session:
        session.emplace("transcript", segments)
        session.emplace("transcript_text", text)
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
def generate_minutes(session: Annotated[MeetingSession, Depends(get_session)]):
    """
    FRONT END SENDS:  nothing (POST with empty body)
    BACK END RETURNS: Minutes object (status="draft") with summary, decisions,
                      action_items and unresolved_issues extracted by the LLM.

    Allowed while meeting status is "processing".
    Reads the transcript stored in session (or transcript.txt on disk as fallback):
        data/<meeting_id>/during_meeting/transcript/transcript.txt
    """
    with session:
        if session.status != "processing":
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Cannot generate minutes while the meeting is '{session.status}'. "
                "Stop the recording first.",
            )

        transcript_text = session.get("transcript_text")
        if transcript_text is None:
            transcript_path = session.path("during_meeting/transcript/transcript.txt")
            if not transcript_path.is_file():
                return error(
                    409,
                    "TRANSCRIPT_NOT_FOUND",
                    "No transcript file found. Run POST .../transcribe before generating minutes.",
                )
            transcript_text = transcript_path.read_text(encoding="utf-8")

        meeting = dict(session.at("meeting"))
        ended_at = meeting.get("ended_at") or now()
        meeting_date = ended_at[:10]  # "YYYY-MM-DD"
        agenda_items = list(session.get("agenda", []))

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
        if session.status != "processing":
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Cannot generate minutes while the meeting is '{session.status}'. "
                "Stop the recording first.",
            )

        draft_path = session.path("post_meeting/meeting_minutes/minutes_draft.md")
        draft_path.write_text(markdown, encoding="utf-8")

        minutes_dict = {
            "meeting_id": session.id,
            "status": "draft",
            "summary": extraction.summary,
            "decisions": extraction.decisions,
            "action_items": [item.model_dump() for item in extraction.action_items],
            "unresolved_issues": extraction.unresolved_issues,
            "markdown": markdown,
            "updated_at": now(),
        }
        session.emplace("minutes", minutes_dict)
        _set_status(session, "review")
        return dict(minutes_dict)


@app.get("/api/v1/meetings/{meeting_id}/minutes", response_model=Minutes)
def read_minutes(session: Annotated[MeetingSession, Depends(get_session)]):
    """
    FRONT END SENDS:  nothing
    BACK END RETURNS: Minutes object (draft or confirmed).
    Used after a page refresh or a reconnect.
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


@app.put("/api/v1/meetings/{meeting_id}/minutes", response_model=Minutes)
def update_minutes(
    body: MinutesEdit,
    session: Annotated[MeetingSession, Depends(get_session)],
):
    """
    FRONT END SENDS:  { "markdown": "..." }
    BACK END RETURNS: Updated Minutes object.
    Lets the user edit the Markdown draft before confirming.
    Only allowed while meeting status is "review".
    """
    with session:
        if session.status not in _MINUTES_EDITABLE:
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


@app.post("/api/v1/meetings/{meeting_id}/minutes/confirm", response_model=Meeting)
def confirm_minutes(session: Annotated[MeetingSession, Depends(get_session)]):
    """
    FRONT END SENDS:  nothing (POST with empty body)
    BACK END RETURNS: Meeting with status "archived".
    Marks the minutes as confirmed, saves the final Markdown to disk,
    and closes the meeting.
    Only allowed while meeting status is "review".
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

        final_path = session.path("post_meeting/meeting_minutes/minutes_final.md")
        final_path.write_text(minutes["markdown"], encoding="utf-8")

        minutes["status"] = "confirmed"
        minutes["updated_at"] = now()
        return _set_status(session, "archived")
