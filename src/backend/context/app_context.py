import threading
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from ..document.markdown_converter import MarkDownConverter
from ..meeting_manager.meeting_manager import MeetingManager
from ..meeting_manager.storage_manager import StorageManager
from .session import MeetingSession


class MeetingNotFoundError(KeyError): ...


class AppContext:
    def __init__(self, data_root: Path = Path("data")):
        # Attribute get from other modules
        self.storage = StorageManager(data_root)
        self.meeting_manager = MeetingManager(self.storage)
        self.converter = MarkDownConverter()

        # Private attributes
        self._sessions: dict[str, MeetingSession] = {}
        self._lock = threading.Lock()

    def create_session(self) -> MeetingSession:
        mc = self.meeting_manager.create_meeting()
        session = MeetingSession(mc.meeting_id, mc.meeting_dir)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def session(self, meeting_id: str) -> MeetingSession:
        with self._lock:
            try:
                return self._sessions[meeting_id]
            except KeyError:
                raise MeetingNotFoundError(meeting_id) from None

    def sessions(self) -> list[MeetingSession]:
        with self._lock:
            return list(self._sessions.values())


def get_ctx(request: Request) -> AppContext:
    """fastapi dependency"""
    return request.app.state.ctx


def get_session(
    meeting_id: str, ctx: Annotated[AppContext, Depends(get_ctx)]
) -> MeetingSession:
    return ctx.session(meeting_id)
