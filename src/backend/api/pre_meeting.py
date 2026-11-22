"""
STAGE 1 (before meeting): create meeting, upload documents, propose and confirm the agenda.

    POST /api/v1/meetings                        create the meeting (topic, duration, planned points)
    GET  /api/v1/meetings/{id}                   read the meeting (status, timestamps)
    POST /api/v1/meetings/{id}/documents         upload one .md/.txt/.pdf/.docx file
    POST /api/v1/meetings/{id}/agenda/generate   build a PROPOSED agenda
    PUT  /api/v1/meetings/{id}/agenda            the user confirms the (edited) agenda -> "ready"
    GET  /api/v1/meetings/{id}/agenda            read the agenda back (after a page refresh)

Contract: docs/system_design/api-contract.md (sections 5 and 6).
"""

import re
import tempfile
from pathlib import Path

from fastapi import APIRouter, UploadFile

from ..agenda_extractor.agenda_extractor import extract_topics
from ..document.markdown_converter import FileConversionError, MarkDownConverter
from ..utils.objects import (
    AgendaEdit,
    AgendaList,
    AgendaProposal,
    Document,
    Meeting,
    NewMeeting,
)
from ..utils.utils import error, now
from .common import CtxDep, SessionDep, meeting_response

router = APIRouter(prefix="/meetings", tags=["pre-meeting"])


# POST /meetings  - create the meeting


@router.post("", status_code=201, response_model=Meeting)
def create_meeting(body: NewMeeting, ctx: CtxDep):
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
        ctx.meeting_repository.create_meeting(meeting, status=session.status)
        return meeting_response(session)


@router.get("/{meeting_id}", response_model=Meeting)
def read_meeting(session: SessionDep):
    with session:
        return meeting_response(session)


# POST /meetings/{id}/documents  - upload one file

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


@router.post("/{meeting_id}/documents", status_code=201, response_model=Document)
async def upload_document(file: UploadFile, session: SessionDep, ctx: CtxDep):
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
        full_doc = {**document, "text": text, "headings": headings}
        ctx.meeting_repository.add_document(full_doc)
        documents.append(full_doc)

    return document


# POST /meetings/{id}/agenda/generate  - build the PROPOSED agenda

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


def _agenda_locked(session) -> object | None:
    if session.status not in AGENDA_EDITABLE:
        return error(
            409,
            "INVALID_MEETING_STATE",
            f"Agenda cannot change while the meeting is {session.status}",
        )
    return None


@router.post("/{meeting_id}/agenda/generate", response_model=AgendaProposal)
def generate_agenda(session: SessionDep, ctx: CtxDep):
    """
    BACK END RETURNS: AgendaProposal = {items, dropped, total_estimated_minutes, duration_minutes}
    The UI shows items in "order" and lists "dropped". Nothing is official until PUT /agenda.
    """
    with session:
        if (locked := _agenda_locked(session)) is not None:
            return locked
        meeting = dict(session.at("meeting"))
        documents = [dict(doc) for doc in session.at("documents")]

    # The LLM call can take seconds, so it runs outside the session lock.
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
        # Re-check: the status may have changed while the LLM was running.
        if (locked := _agenda_locked(session)) is not None:
            return locked
        ctx.meeting_repository.replace_agenda(session.id, items, status="draft")
        session.emplace("agenda", items)
        session.status = "draft"  # a new proposal is not confirmed yet

    return {
        "items": items,
        "dropped": dropped,
        "total_estimated_minutes": sum(item["estimated_minutes"] for item in items),
        "duration_minutes": meeting["duration_minutes"],
    }


# PUT /meetings/{id}/agenda  - the user confirms   |   GET  - read it back


@router.put("/{meeting_id}/agenda", response_model=AgendaList)
def save_agenda(body: AgendaEdit, session: SessionDep, ctx: CtxDep):
    """
    FRONT END SENDS:  AgendaEdit = {items: [{id, title, estimated_minutes, order}]}
    BACK END RETURNS: AgendaList = {items: AgendaItem[]} with full fields; meeting becomes "ready".
    Fields the user cannot edit (source, scores) are kept from the proposal.
    """
    with session:
        # "ready" is allowed too: the user can edit and confirm again before the meeting starts.
        if (locked := _agenda_locked(session)) is not None:
            return locked

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

        ctx.meeting_repository.replace_agenda(session.id, saved, status="ready")
        session.emplace("agenda", saved)
        session.status = "ready"
        return {"items": saved}


@router.get("/{meeting_id}/agenda", response_model=AgendaList)
def read_agenda(session: SessionDep):
    """
    FRONT END SENDS:  nothing
    BACK END RETURNS: AgendaList (the proposed or confirmed agenda; used after a page refresh)
    """
    with session:
        return {"items": list(session.at("agenda"))}
