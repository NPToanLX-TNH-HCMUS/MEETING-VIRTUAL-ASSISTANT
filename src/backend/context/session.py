import threading
from pathlib import Path
from typing import Any


class MissingContextError(KeyError):
    """A module asked for data that no earlier step has produced yet."""


class MeetingSession:
    def __init__(self, meeting_id: str, root: Path, status: str = "draft"):
        self.id = meeting_id
        self.root = root
        self.status = status
        self.lock = threading.RLock()
        self._data: dict[str, Any] = {}

    def at(self, key: str) -> Any:
        try:
            return self._data[key]
        except KeyError:
            # Missing data means a step ran out of order (e.g. minutes before transcribe).
            raise MissingContextError(f"Meeting {self.id} has no '{key}' yet") from None

    def get(self, key: str, default: Any = None) -> Any:
        return self._data.get(key, default)

    def emplace(self, key: str, value: Any) -> None:
        self._data[key] = value

    def has(self, key: str) -> bool:
        return key in self._data

    def pop(self, key: str, default: Any = None) -> Any:
        return self._data.pop(key, default)

    # ---- files ----
    def path(self, artifact: str) -> Path:
        """Absolute path for an artifact; parent folder is created so modules can just write."""
        p = self.root / artifact
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    # ---- locking: `with session:` ----
    def __enter__(self):
        self.lock.acquire()
        return self

    def __exit__(self, *exc):
        self.lock.release()
        return False
