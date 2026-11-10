import uuid

from .meeting_context import MeetingContext
from .storage_manager import StorageManager


class MeetingManager:
    def __init__(self, storage: StorageManager):
        self.storage = storage

    def create_meeting(self) -> MeetingContext:
        # Generate unique ID
        meeting_id = str(uuid.uuid4())

        # Create folder structure
        meeting_dir = self.storage.create_meeting_directory(meeting_id)

        # Return context
        return MeetingContext(meeting_id=meeting_id, meeting_dir=meeting_dir)
