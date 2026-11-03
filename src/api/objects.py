from typing import Literal

from pydantic import BaseModel

Source = Literal["planned_point", "document", "carry_over", "manual"]


class Meeting(BaseModel):
    id: str
    topic: str
    language: str
    duration_minutes: int
    status: str  # draft -> ready -> live <-> paused -> processing -> review -> archived
    planned_points: list[str]
    previous_meeting_id: str | None
    created_at: str
    started_at: str | None
    ended_at: str | None


class Document(BaseModel):
    id: str
    meeting_id: str
    filename: str
    mime_type: str
    size_bytes: int
    uploaded_at: str


class AgendaItem(BaseModel):
    id: str
    meeting_id: str
    title: str
    description: str | None
    source: Source  # where the item came from; the UI shows it as a label
    importance: int | None  # 0..3, from the LLM            (None = not computed yet)
    urgency: int | None  # 0..3, from the deadline          (None = not computed yet)
    relevance: int | None  # 0..3, from the LLM             (None = not computed yet)
    priority_score: float | None  # a*I + b*U + c*R          (None = not computed yet)
    estimated_minutes: int | None
    order: int  # position in the agenda, starts at 1
    state: str  # not_discussed -> in_progress -> discussed -> concluded
    started_at: str | None
    ended_at: str | None
    needs_confirmation: bool  # True until the user confirms the agenda


class DroppedItem(BaseModel):
    title: str
    reason: str  # "exceeds_remaining_time"
    estimated_minutes: int | None


class AgendaProposal(BaseModel):
    items: list[AgendaItem]
    dropped: list[DroppedItem]
    total_estimated_minutes: int
    duration_minutes: int


class AgendaList(BaseModel):
    items: list[AgendaItem]


class NewMeeting(BaseModel):
    """FRONT END SENDS (JSON), built by readDetails() in frontend/js/main.js."""

    topic: str
    language: str
    duration_minutes: int
    planned_points: list[str] = []  # one entry per line of the "Các ý bạn dự định trình bày" box
    previous_meeting_id: str | None = None  # always null for now

class AgendaItemEdit(BaseModel):
    """One row as the UI sends it: only what the user can change."""

    id: str | None = None  # None = a row the user added by hand
    title: str
    estimated_minutes: int
    order: int


class AgendaEdit(BaseModel):
    """FRONT END SENDS (JSON): the FULL list the user wants, in order."""

    items: list[AgendaItemEdit]