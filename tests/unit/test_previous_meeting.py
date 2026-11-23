import json
import tempfile
import unittest
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.api import pre_meeting
from src.backend.context.app_context import AppContext
from src.backend.database.model import Base
from src.backend.database.repository import MeetingRepository
from src.backend.utils.objects import NewMeeting


class TestPreviousMeetingBackend(unittest.TestCase):
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
        self.ctx = AppContext(self.data_root, repository=self.repo)

    def tearDown(self):
        self.engine.dispose()
        self.tmp.cleanup()

    def test_list_meetings_orders_newest_first_and_filters_status(self):
        self.repo.create_meeting(
            {
                "id": "m-old",
                "topic": "Old Sprint",
                "language": "en",
                "duration_minutes": 30,
                "planned_points": [],
                "previous_meeting_id": None,
                "created_at": "2026-11-20T09:00:00+07:00",
                "started_at": None,
                "ended_at": None,
            },
            status="archived",
        )
        self.repo.create_meeting(
            {
                "id": "m-new",
                "topic": "New Sprint",
                "language": "vi",
                "duration_minutes": 45,
                "planned_points": ["Review"],
                "previous_meeting_id": "m-old",
                "created_at": "2026-11-22T09:00:00+07:00",
                "started_at": None,
                "ended_at": None,
            },
            status="draft",
        )

        all_res = pre_meeting.list_meetings(self.ctx, status=None, limit=50)
        self.assertEqual([m["id"] for m in all_res["items"]], ["m-new", "m-old"])

        archived_res = pre_meeting.list_meetings(self.ctx, status="archived", limit=50)
        self.assertEqual([m["id"] for m in archived_res["items"]], ["m-old"])

    def test_create_meeting_with_valid_previous_meeting_id_after_restart(self):
        first = pre_meeting.create_meeting(
            NewMeeting(topic="Sprint 1", language="en", duration_minutes=30),
            self.ctx,
        )
        # Simulate server restart: new AppContext sharing the same database
        restarted_ctx = AppContext(self.data_root, repository=self.repo)
        second = pre_meeting.create_meeting(
            NewMeeting(
                topic="Sprint 2",
                language="en",
                duration_minutes=30,
                previous_meeting_id=first["id"],
            ),
            restarted_ctx,
        )
        self.assertEqual(second["previous_meeting_id"], first["id"])

        reloaded = self.repo.load_session(second["id"], self.data_root)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.at("meeting")["previous_meeting_id"], first["id"])

    def test_create_meeting_with_unknown_previous_meeting_id_returns_404_without_orphan_dir(
        self,
    ):
        res = pre_meeting.create_meeting(
            NewMeeting(
                topic="Orphan Check",
                language="en",
                duration_minutes=30,
                previous_meeting_id="non-existent-id",
            ),
            self.ctx,
        )
        self.assertEqual(res.status_code, 404)
        body = json.loads(res.body)
        self.assertEqual(body["error"]["code"], "MEETING_NOT_FOUND")
        self.assertEqual(list(self.data_root.iterdir()), [])
        self.assertEqual(self.ctx.sessions(), [])


if __name__ == "__main__":
    unittest.main()
