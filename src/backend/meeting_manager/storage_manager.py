import shutil
from pathlib import Path


class StorageManager:
    def __init__(self, root_dir="data"):
        self.root_dir = Path(root_dir)

    def create_meeting_directory(self, meeting_id: str):
        meeting_dir = self.root_dir / meeting_id

        meeting_dir.mkdir(parents=True, exist_ok=False)

        directories = [
            "pre_meeting/uploaded",
            "pre_meeting/processed",
            "during_meeting/audio",
            "during_meeting/transcript",
            "post_meeting/meeting_minutes",
            "post_meeting/summary",
            "post_meeting/action_items",
        ]

        try:
            for directory in directories:
                (meeting_dir / directory).mkdir(parents=True)

            return meeting_dir

        except Exception:
            shutil.rmtree(meeting_dir, ignore_errors=True)
            raise
