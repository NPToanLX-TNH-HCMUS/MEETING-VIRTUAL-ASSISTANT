"""A confirmed meeting is saved to <meeting dir>/archive.json, so it is still there after a restart.

Only confirmed ("archived") meetings are kept: a meeting that was never confirmed still lives in memory
only. The file holds what the post-meeting page needs to show the meeting again (minutes, agenda,
transcript, extractions, conflicts), not the audio or the uploaded documents, which already sit on disk.
"""

import json
import logging
import os
from pathlib import Path

from .session import MeetingSession

LOGGER = logging.getLogger(__name__)

ARCHIVE_FILE = "archive.json"
KEYS = ("meeting", "minutes", "agenda", "transcript", "extractions", "extraction_cursor", "conflicts")


def write_json(path: Path, data) -> None:
    """Whole file or nothing: a crash while writing never leaves half a file behind."""
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_name(path.name + ".tmp")
    with open(temp, "w", encoding="utf-8") as file:
        # ensure_ascii=False keeps Vietnamese readable in the file; default=str never lets one odd value fail a save.
        json.dump(data, file, ensure_ascii=False, indent=1, default=str)
    os.replace(temp, path)


def save_archive(session: MeetingSession) -> None:
    """Call with the session lock held."""
    data = {key: session.get(key) for key in KEYS if session.has(key)}
    write_json(session.root / ARCHIVE_FILE, data)


def load_archives(root_dir: Path) -> list[MeetingSession]:
    sessions = []
    for archive in sorted(root_dir.glob(f"*/{ARCHIVE_FILE}")):
        try:
            data = json.loads(archive.read_text(encoding="utf-8"))
            meeting = data["meeting"]
            if meeting["id"] != archive.parent.name or not isinstance(data.get("minutes"), dict):
                raise ValueError("does not match its folder")
        except (OSError, ValueError, KeyError, TypeError):
            # One broken file must not stop the others from loading.
            LOGGER.warning("Skipping unreadable archive in %s", archive.parent.name)
            continue
        session = MeetingSession(meeting["id"], archive.parent, status="archived")
        for key in KEYS:
            if key in data:
                session.emplace(key, data[key])
        session.emplace("documents", [])
        sessions.append(session)
    return sessions
