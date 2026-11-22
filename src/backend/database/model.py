from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship

JSON_TYPE = JSON().with_variant(JSONB, "postgresql")


class Base(DeclarativeBase):
    pass


class MeetingModel(Base):
    __tablename__ = "meetings"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    topic: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(10), nullable=False)
    duration_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    planned_points: Mapped[list[str]] = mapped_column(
        JSON_TYPE, nullable=False, default=list
    )
    previous_meeting_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[str] = mapped_column(String(64), nullable=False)
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String(64), nullable=True)

    documents: Mapped[list["DocumentModel"]] = relationship(
        back_populates="meeting", cascade="all, delete-orphan"
    )
    agenda_items: Mapped[list["AgendaItemModel"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="AgendaItemModel.order",
    )
    transcript: Mapped["TranscriptModel | None"] = relationship(
        back_populates="meeting", uselist=False, cascade="all, delete-orphan"
    )
    minutes: Mapped["MinutesModel | None"] = relationship(
        back_populates="meeting", uselist=False, cascade="all, delete-orphan"
    )
    action_items: Mapped[list["ActionItemModel"]] = relationship(
        back_populates="meeting",
        cascade="all, delete-orphan",
        order_by="ActionItemModel.position",
    )


class DocumentModel(Base):
    __tablename__ = "documents"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    mime_type: Mapped[str] = mapped_column(String(50), nullable=False)
    size_bytes: Mapped[int] = mapped_column(Integer, nullable=False)
    uploaded_at: Mapped[str] = mapped_column(String(64), nullable=False)
    text: Mapped[str] = mapped_column(Text, nullable=False)
    headings: Mapped[list[str]] = mapped_column(JSON_TYPE, nullable=False, default=list)

    meeting: Mapped["MeetingModel"] = relationship(back_populates="documents")


class AgendaItemModel(Base):
    __tablename__ = "agenda_items"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    id: Mapped[str] = mapped_column(String(32), primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(30), nullable=False)
    importance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    urgency: Mapped[int | None] = mapped_column(Integer, nullable=True)
    relevance: Mapped[int | None] = mapped_column(Integer, nullable=True)
    priority_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    estimated_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    # "order" is a reserved SQL keyword, so store it as "order_index" in the database.
    order: Mapped[int] = mapped_column("order_index", Integer, nullable=False)
    state: Mapped[str] = mapped_column(
        String(20), nullable=False, default="not_discussed"
    )
    started_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    ended_at: Mapped[str | None] = mapped_column(String(64), nullable=True)
    needs_confirmation: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=True
    )

    meeting: Mapped["MeetingModel"] = relationship(back_populates="agenda_items")


class TranscriptModel(Base):
    __tablename__ = "transcripts"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    segments: Mapped[list[dict[str, str]]] = mapped_column(
        JSON_TYPE, nullable=False, default=list
    )
    full_text: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    meeting: Mapped["MeetingModel"] = relationship(back_populates="transcript")


class MinutesModel(Base):
    __tablename__ = "meeting_minutes"

    meeting_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("meetings.id", ondelete="CASCADE"), primary_key=True
    )
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="draft")
    summary: Mapped[str] = mapped_column(Text, nullable=False)
    decisions: Mapped[list[str]] = mapped_column(
        JSON_TYPE, nullable=False, default=list
    )
    unresolved_issues: Mapped[list[str]] = mapped_column(
        JSON_TYPE, nullable=False, default=list
    )
    markdown: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[str] = mapped_column(String(64), nullable=False)

    meeting: Mapped["MeetingModel"] = relationship(back_populates="minutes")


class ActionItemModel(Base):
    __tablename__ = "action_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    meeting_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey("meetings.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    position: Mapped[int] = mapped_column(Integer, nullable=False)
    task: Mapped[str] = mapped_column(Text, nullable=False)
    assignee: Mapped[str | None] = mapped_column(String(255), nullable=True)
    due: Mapped[str | None] = mapped_column(String(10), nullable=True)
    quote: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(20), nullable=False, default="todo")

    meeting: Mapped["MeetingModel"] = relationship(back_populates="action_items")
