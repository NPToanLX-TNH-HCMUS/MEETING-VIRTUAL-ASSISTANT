from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class MeetingContext:
    meeting_id: str
    meeting_dir: Path

    @property
    def pre_meeting_dir(self):
        return self.meeting_dir / "pre_meeting"

    @property
    def during_meeting_dir(self):
        return self.meeting_dir / "during_meeting"

    @property
    def post_meeting_dir(self):
        return self.meeting_dir / "post_meeting"
