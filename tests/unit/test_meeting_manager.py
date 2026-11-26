"""
Unit test suite for Meeting Manager & Storage Manager (PR #8).

Covers:
- TC-STG-01: Generating unique UUIDv4 and initializing MeetingContext.
- TC-STG-02: Complete creation of all 7 runtime subdirectories.
- TC-STG-03: Preventing overwrites on duplicate meeting IDs (FileExistsError).
- TC-STG-04: Graceful rollback (directory deletion) when subdirectory creation fails.
"""

import uuid
from pathlib import Path
from unittest.mock import patch

import pytest
from backend.meeting_manager.meeting_context import MeetingContext
from backend.meeting_manager.meeting_manager import MeetingManager
from backend.meeting_manager.storage_manager import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    """Fixture providing a StorageManager rooted inside a clean temporary directory."""
    return StorageManager(root_dir=tmp_path)


@pytest.fixture
def manager(storage: StorageManager) -> MeetingManager:
    """Fixture providing a MeetingManager coupled with the isolated storage."""
    return MeetingManager(storage=storage)


class TestMeetingManager:
    """Unit tests validating meeting lifecycle orchestration and directory isolation."""

    def test_create_meeting_generates_valid_uuid_and_context(
        self, manager: MeetingManager, tmp_path: Path
    ) -> None:
        """
        TC-STG-01: create_meeting() must generate a valid UUIDv4 identifier
        and return a correctly configured MeetingContext dataclass.
        """
        # Act
        context = manager.create_meeting()

        # Assert 1: meeting_id must be a valid UUIDv4 string
        assert isinstance(context, MeetingContext)
        parsed_uuid = uuid.UUID(context.meeting_id, version=4)
        assert str(parsed_uuid) == context.meeting_id

        # Assert 2: Meeting root directory must exist
        expected_dir = tmp_path / context.meeting_id
        assert context.meeting_dir == expected_dir
        assert context.meeting_dir.is_dir()

        # Assert 3: Context utility properties must map to correct paths
        assert context.pre_meeting_dir == expected_dir / "pre_meeting"
        assert context.during_meeting_dir == expected_dir / "during_meeting"
        assert context.post_meeting_dir == expected_dir / "post_meeting"

    def test_storage_manager_creates_all_seven_subdirectories(
        self, storage: StorageManager, tmp_path: Path
    ) -> None:
        """
        TC-STG-02: create_meeting_directory() must instantiate all 7 required
        lifecycle subdirectories under the meeting root directory.
        """
        # Arrange
        meeting_id = "meeting_test_alpha"
        expected_subdirectories = [
            "pre_meeting/uploaded",
            "pre_meeting/processed",
            "during_meeting/audio",
            "during_meeting/transcript",
            "post_meeting/meeting_minutes",
            "post_meeting/summary",
            "post_meeting/action_items",
        ]

        # Act
        meeting_dir = storage.create_meeting_directory(meeting_id)

        # Assert
        assert meeting_dir == tmp_path / meeting_id
        assert meeting_dir.is_dir()

        for sub_dir in expected_subdirectories:
            full_path = meeting_dir / sub_dir
            assert full_path.exists(), f"Missing expected subdirectory: {sub_dir}"
            assert full_path.is_dir(), f"Path is not a directory: {sub_dir}"

    def test_storage_manager_raises_error_if_meeting_already_exists(
        self, storage: StorageManager
    ) -> None:
        """
        TC-STG-03: Calling create_meeting_directory with an existing meeting_id
        must raise FileExistsError to protect previously persisted records.
        """
        # Arrange
        meeting_id = "duplicate_meeting_id"
        storage.create_meeting_directory(meeting_id)  # First initialization

        # Act & Assert
        with pytest.raises(FileExistsError):
            storage.create_meeting_directory(meeting_id)

    def test_storage_manager_rollback_on_failure(
        self, storage: StorageManager, tmp_path: Path
    ) -> None:
        """
        TC-STG-04: If an unexpected error occurs during subdirectory creation,
        the storage manager must rollback by deleting the partially created meeting directory.
        """
        # Arrange
        meeting_id = "faulty_meeting_id"
        target_dir = tmp_path / meeting_id

        # Act & Assert: Simulate a disk error midway through subdirectory creation
        with patch("shutil.rmtree") as mock_rmtree:
            with patch.object(Path, "mkdir") as mock_mkdir:
                # 1st call (meeting root creation): Succeeds (returns None)
                # 2nd call (subdirectory creation inside try block): Raises OSError
                mock_mkdir.side_effect = [None, OSError("Simulated disk error")]

                with pytest.raises(OSError, match="Simulated disk error"):
                    storage.create_meeting_directory(meeting_id)

                # Assert that the except block successfully invoked shutil.rmtree for cleanup
                mock_rmtree.assert_called_once_with(target_dir, ignore_errors=True)
                