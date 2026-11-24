"""Shared helpers for every stage router."""

from typing import Annotated

from fastapi import Depends

from ..context.app_context import AppContext, get_ctx, get_session
from ..context.session import MeetingSession

# Reusable dependency aliases: `def endpoint(session: SessionDep)` instead of repeating Annotated[...].
CtxDep = Annotated[AppContext, Depends(get_ctx)]
SessionDep = Annotated[MeetingSession, Depends(get_session)]


def meeting_response(session: MeetingSession) -> dict:
    """Build the Meeting response dict using session.status as the single source of truth."""
    return {**session.at("meeting"), "status": session.status}
