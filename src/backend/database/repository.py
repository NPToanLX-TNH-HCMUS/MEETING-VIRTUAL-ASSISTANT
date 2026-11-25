"""
src/backend/database/repository.py
===============================

Main idea: Repository Pattern.
* Every kinds of database query must to be done here, not somewhere else.
"""

from pathlib import Path

from sqlalchemy import delete, select, update
from sqlalchemy.orm import selectinload, sessionmaker

from ..context.session import MeetingSession
from .database import SessionLocal
from .model import (
    ActionItemModel,
    AgendaItemModel,
    DocumentModel,
    MeetingModel,
    MinutesModel,
    TranscriptModel,
)

# Distinguishes an omitted optional argument from an explicit None (e.g. clearing started_at).
_UNSET = object()


class MeetingRepository:
    """Persistence boundary mapping MeetingSession state to/from relational tables."""

    def __init__(self, session_factory: sessionmaker = SessionLocal):
        self._session = session_factory

    def load_session(self, meeting_id: str, data_root: Path) -> MeetingSession | None:
        """Rehydrate an in-memory MeetingSession from persisted DB state on cache miss (e.g. after server restart)."""
        with self._session() as db:
            stmt = (
                select(MeetingModel)
                .where(MeetingModel.id == meeting_id)
                .options(
                    selectinload(MeetingModel.documents),
                    selectinload(MeetingModel.agenda_items),
                    selectinload(MeetingModel.transcript),
                    selectinload(MeetingModel.minutes),
                    selectinload(MeetingModel.action_items),
                )
            )
            row = db.scalar(stmt)
            if row is None:
                return None

            session = MeetingSession(
                meeting_id=row.id,
                root=data_root / row.id,
                status=row.status,
            )

            session.emplace(
                "meeting",
                {
                    "id": row.id,
                    "topic": row.topic,
                    "language": row.language,
                    "duration_minutes": row.duration_minutes,
                    "planned_points": list(row.planned_points),
                    "previous_meeting_id": row.previous_meeting_id,
                    "created_at": row.created_at,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                },
            )

            session.emplace(
                "documents",
                [
                    {
                        "id": doc.id,
                        "meeting_id": doc.meeting_id,
                        "filename": doc.filename,
                        "mime_type": doc.mime_type,
                        "size_bytes": doc.size_bytes,
                        "uploaded_at": doc.uploaded_at,
                        "text": doc.text,
                        "headings": list(doc.headings),
                    }
                    for doc in row.documents
                ],
            )

            session.emplace(
                "agenda",
                [
                    {
                        "id": item.id,
                        "meeting_id": item.meeting_id,
                        "title": item.title,
                        "description": item.description,
                        "source": item.source,
                        "importance": item.importance,
                        "urgency": item.urgency,
                        "relevance": item.relevance,
                        "priority_score": item.priority_score,
                        "estimated_minutes": item.estimated_minutes,
                        "order": item.order,
                        "state": item.state,
                        "started_at": item.started_at,
                        "ended_at": item.ended_at,
                        "needs_confirmation": item.needs_confirmation,
                    }
                    for item in row.agenda_items
                ],
            )

            if row.transcript is not None:
                session.emplace("transcript", list(row.transcript.segments))
                session.emplace("transcript_text", row.transcript.full_text)

            if row.minutes is not None:
                session.emplace(
                    "minutes",
                    {
                        "meeting_id": row.id,
                        "status": row.minutes.status,
                        "summary": row.minutes.summary,
                        "decisions": list(row.minutes.decisions),
                        "action_items": [
                            {
                                "task": item.task,
                                "assignee": item.assignee,
                                "due": item.due,
                                "quote": item.quote,
                            }
                            for item in row.action_items
                        ],
                        "unresolved_issues": list(row.minutes.unresolved_issues),
                        "markdown": row.minutes.markdown,
                        "updated_at": row.minutes.updated_at,
                    },
                )

            return session

    def meeting_exists(self, meeting_id: str) -> bool:
        """Return True if a meeting row with the given id exists in the database."""
        with self._session() as db:
            stmt = select(MeetingModel.id).where(MeetingModel.id == meeting_id)
            return db.scalar(stmt) is not None

    def list_meetings(self, status: str | None = None, limit: int = 50) -> list[dict]:
        """List meetings ordered newest-first, optionally filtered by lifecycle status."""
        with self._session() as db:
            stmt = select(MeetingModel).order_by(MeetingModel.created_at.desc())
            if status is not None:
                stmt = stmt.where(MeetingModel.status == status)
            stmt = stmt.limit(limit)
            rows = db.scalars(stmt).all()
            return [
                {
                    "id": row.id,
                    "topic": row.topic,
                    "language": row.language,
                    "duration_minutes": row.duration_minutes,
                    "status": row.status,
                    "planned_points": list(row.planned_points),
                    "previous_meeting_id": row.previous_meeting_id,
                    "created_at": row.created_at,
                    "started_at": row.started_at,
                    "ended_at": row.ended_at,
                }
                for row in rows
            ]

    def create_meeting(self, meeting: dict, status: str = "draft") -> None:
        """Persist a newly created meeting row."""
        with self._session() as db:
            db.add(
                MeetingModel(
                    id=meeting["id"],
                    topic=meeting["topic"],
                    language=meeting["language"],
                    duration_minutes=meeting["duration_minutes"],
                    status=status,
                    planned_points=list(meeting.get("planned_points", [])),
                    previous_meeting_id=meeting.get("previous_meeting_id"),
                    created_at=meeting["created_at"],
                    started_at=meeting.get("started_at"),
                    ended_at=meeting.get("ended_at"),
                )
            )
            db.commit()

    def update_status(
        self,
        meeting_id: str,
        status: str,
        *,
        started_at: str | None | object = _UNSET,
        ended_at: str | None | object = _UNSET,
    ) -> None:
        """Update meeting status and, when provided, recording timestamps."""
        values: dict[str, object] = {"status": status}
        if started_at is not _UNSET:
            values["started_at"] = started_at
        if ended_at is not _UNSET:
            values["ended_at"] = ended_at

        with self._session() as db:
            db.execute(
                update(MeetingModel)
                .where(MeetingModel.id == meeting_id)
                .values(**values)
            )
            db.commit()

    def add_document(self, document: dict) -> None:
        """Persist a single uploaded and parsed meeting document."""
        with self._session() as db:
            db.add(
                DocumentModel(
                    meeting_id=document["meeting_id"],
                    id=document["id"],
                    filename=document["filename"],
                    mime_type=document["mime_type"],
                    size_bytes=document["size_bytes"],
                    uploaded_at=document["uploaded_at"],
                    text=document["text"],
                    headings=list(document.get("headings", [])),
                )
            )
            db.commit()

    def replace_agenda(self, meeting_id: str, items: list[dict], status: str) -> None:
        """Atomically replace all agenda items for a meeting and update its status."""
        with self._session() as db:
            # Replace in one transaction so regenerated/edited items never leave stale rows.
            db.execute(
                delete(AgendaItemModel).where(AgendaItemModel.meeting_id == meeting_id)
            )
            db.add_all(
                [
                    AgendaItemModel(
                        meeting_id=meeting_id,
                        id=item["id"],
                        title=item["title"],
                        description=item.get("description"),
                        source=item["source"],
                        importance=item.get("importance"),
                        urgency=item.get("urgency"),
                        relevance=item.get("relevance"),
                        priority_score=item.get("priority_score"),
                        estimated_minutes=item.get("estimated_minutes"),
                        order=item["order"],
                        state=item.get("state", "not_discussed"),
                        started_at=item.get("started_at"),
                        ended_at=item.get("ended_at"),
                        needs_confirmation=item.get("needs_confirmation", True),
                    )
                    for item in items
                ]
            )
            db.execute(
                update(MeetingModel)
                .where(MeetingModel.id == meeting_id)
                .values(status=status)
            )
            db.commit()

    def save_transcript(
        self,
        meeting_id: str,
        segments: list[dict[str, str]],
        full_text: str,
        updated_at: str,
    ) -> None:
        """Upsert the transcript (structured segments and formatted text) for a meeting."""
        with self._session() as db:
            db.merge(
                TranscriptModel(
                    meeting_id=meeting_id,
                    segments=list(segments),
                    full_text=full_text,
                    updated_at=updated_at,
                )
            )
            db.commit()

    def save_minutes(
        self, meeting_id: str, minutes: dict, status: str = "review"
    ) -> None:
        """Upsert drafted minutes, replace extracted action items, and update meeting status."""
        with self._session() as db:
            db.merge(
                MinutesModel(
                    meeting_id=meeting_id,
                    status=minutes["status"],
                    summary=minutes["summary"],
                    decisions=list(minutes.get("decisions", [])),
                    unresolved_issues=list(minutes.get("unresolved_issues", [])),
                    markdown=minutes["markdown"],
                    updated_at=minutes["updated_at"],
                )
            )
            db.execute(
                delete(ActionItemModel).where(ActionItemModel.meeting_id == meeting_id)
            )
            db.add_all(
                [
                    ActionItemModel(
                        meeting_id=meeting_id,
                        position=idx,
                        task=item["task"],
                        assignee=item.get("assignee"),
                        due=item.get("due"),
                        quote=item["quote"],
                    )
                    for idx, item in enumerate(minutes.get("action_items", []), start=1)
                ]
            )
            db.execute(
                update(MeetingModel)
                .where(MeetingModel.id == meeting_id)
                .values(status=status)
            )
            db.commit()

    def update_minutes_markdown(
        self, meeting_id: str, markdown: str, updated_at: str
    ) -> None:
        """Update only the edited Markdown draft and timestamp for existing minutes."""
        with self._session() as db:
            db.execute(
                update(MinutesModel)
                .where(MinutesModel.meeting_id == meeting_id)
                .values(markdown=markdown, updated_at=updated_at)
            )
            db.commit()

    def confirm_minutes(self, meeting_id: str, updated_at: str) -> None:
        """Mark minutes as confirmed and archive the meeting in one transaction."""
        with self._session() as db:
            db.execute(
                update(MinutesModel)
                .where(MinutesModel.meeting_id == meeting_id)
                .values(status="confirmed", updated_at=updated_at)
            )
            db.execute(
                update(MeetingModel)
                .where(MeetingModel.id == meeting_id)
                .values(status="archived")
            )
            db.commit()

    def get_previous_context(self, previous_meeting_id: str) -> dict | None:
        """Fetch summary, unresolved issues, and pending action items from a previous meeting."""
        with self._session() as db:
            stmt = (
                select(MeetingModel)
                .where(MeetingModel.id == previous_meeting_id)
                .options(
                    selectinload(MeetingModel.minutes),
                    selectinload(MeetingModel.action_items),
                )
            )
            row = db.scalar(stmt)
            if row is None:
                return None
            return {
                "topic": row.topic,
                "summary": row.minutes.summary if row.minutes else "",
                "unresolved_issues": (
                    list(row.minutes.unresolved_issues) if row.minutes else []
                ),
                "action_items": [
                    {
                        "task": item.task,
                        "assignee": item.assignee,
                        "due": item.due,
                        "status": item.status,
                    }
                    for item in row.action_items
                    if item.status != "done"
                ],
            }
