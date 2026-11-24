import threading
from pathlib import Path
from typing import Annotated

from fastapi import Depends, Request

from ..database.repository import MeetingRepository
from ..database.storage import CloudStorage
from ..document.markdown_converter import MarkDownConverter
from ..meeting_manager.meeting_manager import MeetingManager
from ..meeting_manager.storage_manager import StorageManager
from .session import MeetingSession


class MeetingNotFoundError(KeyError): ...


class AppContext:
    def __init__(
        self,
        data_root: Path = Path("data"),
        repository: MeetingRepository | None = None,
        cloud_storage: CloudStorage | None = None,
    ):
        # Attribute get from other modules
        self.storage = StorageManager(data_root)
        self.meeting_manager = MeetingManager(self.storage)
        self.converter = MarkDownConverter()
        self.meeting_repository = repository or MeetingRepository()
        self.cloud_storage = cloud_storage or CloudStorage()

        # Private attributes
        self._sessions: dict[str, MeetingSession] = {}
        self._lock = threading.Lock()

    def create_session(self) -> MeetingSession:
        mc = self.meeting_manager.create_meeting()
        session = MeetingSession(mc.meeting_id, mc.meeting_dir)
        with self._lock:
            self._sessions[session.id] = session
        return session

    def has(self, key: str):
        return key in self._sessions

    def session(self, meeting_id: str) -> MeetingSession:
        with self._lock:
            if self.has(meeting_id):
                return self._sessions[meeting_id]
            else:
                loaded = self.meeting_repository.load_session(
                    meeting_id, self.storage.root_dir
                )
                if loaded is None:
                    raise MeetingNotFoundError(meeting_id) from None

                # In case server was accidentally downed while recording:
                if loaded.status in {"live", "paused"}:
                    has_audio = loaded.path("during_meeting/audio/record.wav").is_file()
                    new_status = (
                        "processing"
                        if (has_audio or loaded.has("transcript_text"))
                        else "ready"
                    )
                    loaded.status = new_status
                    self.meeting_repository.update_status(loaded.id, new_status)

            self._sessions[meeting_id] = loaded
            return loaded

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
