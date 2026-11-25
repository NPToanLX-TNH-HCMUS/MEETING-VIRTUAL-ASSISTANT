import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.api import post_meeting, pre_meeting
from src.backend.context.app_context import AppContext
from src.backend.database.model import Base
from src.backend.database.repository import MeetingRepository
from src.backend.database.storage import BUCKET_NAME, CloudStorage
from src.backend.utils.objects import NewMeeting


def _make_fake_supabase():
    uploaded: dict[str, tuple[bytes, dict]] = {}
    bucket_mock = MagicMock()

    def fake_upload(path: str, file, file_options=None):
        data = file if isinstance(file, (bytes, bytearray)) else file.read()
        uploaded[path] = (bytes(data), dict(file_options or {}))
        return {"Key": f"{BUCKET_NAME}/{path}"}

    bucket_mock.upload.side_effect = fake_upload

    client_mock = MagicMock()
    client_mock.storage.from_.return_value = bucket_mock
    return client_mock, uploaded


class TestCloudStorageArchive(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.data_root = Path(self.tmp.name)
        self.engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.repo = MeetingRepository(
            sessionmaker(bind=self.engine, autoflush=False, expire_on_commit=False)
        )

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def _prepare_review_meeting(self, ctx: AppContext) -> str:
        meeting = pre_meeting.create_meeting(
            NewMeeting(topic="Archive Test", language="en", duration_minutes=30),
            ctx,
        )
        mid = meeting["id"]
        session = ctx.session(mid)

        session.path("during_meeting/audio/record.wav").write_bytes(b"RIFFwave")
        session.path("during_meeting/transcript/transcript.txt").write_text(
            "Hello team", encoding="utf-8"
        )
        session.path("post_meeting/meeting_minutes/minutes_draft.md").write_text(
            "# Draft", encoding="utf-8"
        )

        minutes = {
            "meeting_id": mid,
            "status": "draft",
            "summary": "Summary",
            "decisions": ["Proceed"],
            "action_items": [
                {"task": "Ship", "assignee": "An", "due": None, "quote": "Hello team"}
            ],
            "unresolved_issues": [],
            "markdown": "# Final Minutes",
            "updated_at": "2026-11-24T06:40:00+07:00",
        }
        self.repo.save_minutes(mid, minutes, status="review")
        session.emplace("minutes", minutes)
        session.status = "review"
        return mid

    def test_upload_preserves_tree_adds_keep_to_empty_dirs_and_cleans_local(self):
        client_mock, uploaded = _make_fake_supabase()
        cloud = CloudStorage(client=client_mock)
        ctx = AppContext(self.data_root, repository=self.repo, cloud_storage=cloud)

        mid = self._prepare_review_meeting(ctx)
        session = ctx.session(mid)
        self.assertTrue(session.root.exists())

        res = post_meeting.confirm_minutes(session, ctx)
        self.assertEqual(res["status"], "archived")
        self.assertFalse(session.root.exists())

        expected_keys = {
            f"{mid}/pre_meeting/uploaded/.keep",
            f"{mid}/pre_meeting/processed/.keep",
            f"{mid}/during_meeting/audio/record.wav",
            f"{mid}/during_meeting/transcript/transcript.txt",
            f"{mid}/post_meeting/meeting_minutes/minutes_draft.md",
            f"{mid}/post_meeting/meeting_minutes/minutes_final.md",
            f"{mid}/post_meeting/summary/.keep",
            f"{mid}/post_meeting/action_items/.keep",
        }
        self.assertEqual(set(uploaded.keys()), expected_keys)
        self.assertEqual(
            uploaded[f"{mid}/during_meeting/audio/record.wav"],
            (b"RIFFwave", {"content-type": "audio/wav", "upsert": "true"}),
        )
        self.assertEqual(
            uploaded[f"{mid}/post_meeting/meeting_minutes/minutes_final.md"],
            (b"# Final Minutes", {"content-type": "text/markdown", "upsert": "true"}),
        )
        self.assertEqual(
            uploaded[f"{mid}/pre_meeting/uploaded/.keep"],
            (b"", {"content-type": "text/plain", "upsert": "true"}),
        )

        # After simulated restart without local folder, DB still serves archived meeting
        restarted_ctx = AppContext(
            self.data_root, repository=self.repo, cloud_storage=cloud
        )
        reloaded = restarted_ctx.session(mid)
        self.assertEqual(reloaded.status, "archived")
        self.assertEqual(
            post_meeting.read_minutes(reloaded)["markdown"], "# Final Minutes"
        )
        self.assertFalse(reloaded.root.exists())

    def test_upload_failure_keeps_local_files_and_review_status(self):
        client_mock, _ = _make_fake_supabase()
        client_mock.storage.from_.return_value.upload.side_effect = RuntimeError(
            "network down"
        )
        cloud = CloudStorage(client=client_mock)
        ctx = AppContext(self.data_root, repository=self.repo, cloud_storage=cloud)

        mid = self._prepare_review_meeting(ctx)
        session = ctx.session(mid)

        res = post_meeting.confirm_minutes(session, ctx)
        self.assertEqual(res.status_code, 502)
        body = json.loads(res.body)
        self.assertEqual(body["error"]["code"], "STORAGE_UPLOAD_FAILED")

        # Local directory and review status must remain untouched
        self.assertTrue(session.root.exists())
        self.assertTrue((session.root / "during_meeting/audio/record.wav").is_file())
        self.assertEqual(session.status, "review")
        reloaded = self.repo.load_session(mid, self.data_root)
        self.assertEqual(reloaded.status, "review")

    def test_missing_env_raises_value_error(self):
        with patch("src.backend.database.storage.SUPABASE_URL", None):
            with self.assertRaises(ValueError):
                CloudStorage()


if __name__ == "__main__":
    unittest.main()
