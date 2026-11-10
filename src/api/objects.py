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
    planned_points: list[
        str
    ] = []  # one entry per line of the "Points you plan to present" box
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


# LLM Return — Agenda extraction
class Topic(BaseModel):
    title: str
    source: Literal["planned_point", "document"]
    minutes: int | None = None  # how long to discuss it; None if the model forgot


class Topics(BaseModel):
    items: list[Topic]


# LLM Return — Minutes extraction
class ActionItem(BaseModel):
    """A task identified from the meeting transcript."""

    task: str  # what needs to be done
    assignee: str | None  # who is responsible; null when unidentifiable
    due: str | None  # YYYY-MM-DD deadline; null when not stated
    quote: str  # verbatim excerpt from the transcript that supports this item


class MinutesExtraction(BaseModel):
    """Raw structured output from the LLM before assembling the final Markdown."""

    summary: str
    decisions: list[str]
    action_items: list[ActionItem]
    unresolved_issues: list[str]


class Minutes(BaseModel):
    """The meeting minutes object returned by the API (§5.8 of api-contract.md)."""

    meeting_id: str
    status: str  # "draft" | "confirmed"
    summary: str
    decisions: list[str]
    action_items: list[ActionItem]
    unresolved_issues: list[str]
    markdown: str  # full Markdown the user can read and edit
    updated_at: str


class MinutesEdit(BaseModel):
    """FRONT END SENDS when the user edits the minutes Markdown draft."""

    markdown: str
