"""The live socket sends agenda.item_state after enough sentences (no mic, no LLM, no network)."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from src.backend.api import during_meeting, post_meeting
from src.backend.during_meeting import meeting_service, live_analysis
from src.backend.utils.objects import MinutesExtraction
from src.backend.context.app_context import AppContext
from src.backend.database.model import Base
from src.backend.database.repository import MeetingRepository
from src.backend.database.storage import CloudStorage
from src.backend.main import app

AGENDA_ITEM = {
    "id": "agd_001", "title": "API contract", "state": "not_discussed",
    "started_at": None, "ended_at": None,
}


async def fake_stream(send_event, **_):
    await send_event({"type": "ready", "message": "go"})
    await asyncio.sleep(0.1)
    for n, text in enumerate(["Mình bàn về API contract.", "Ok.", "Tiếp."], start=1):
        await send_event({
            "type": "committed", "text": text, "id": f"seg_{n:03d}",
            "start_seconds": float(n), "end_seconds": n + 0.5,
        })
    await asyncio.sleep(0.5)  # let the background agenda check finish before the stream ends
    await send_event({"type": "stopping"})
    return "Mình bàn về API contract.\nOk.\nTiếp."


def good_proposal(agenda, segments, cursor):
    return [{"agenda_item_id": "agd_001", "to_state": "in_progress",
             "segment_ids": ["seg_001"], "quote": "bàn về API contract"}]


def no_extraction(segments, cursor, store, *_):
    return []


class TestAgendaSocket(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.data_root = Path(tmp.name)
        engine = create_engine(
            "sqlite:///:memory:",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.addCleanup(engine.dispose)
        Base.metadata.create_all(engine)
        self.repo = MeetingRepository(
            sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
        )
        original = app.state.ctx
        app.state.ctx = AppContext(
            self.data_root,
            repository=self.repo,
            cloud_storage=CloudStorage(client=MagicMock()),
        )
        self.addCleanup(setattr, app.state, "ctx", original)
        self.session = app.state.ctx.create_session()
        meeting = {
            "id": self.session.id,
            "topic": "Socket Test",
            "language": "vi",
            "duration_minutes": 30,
            "planned_points": [],
            "previous_meeting_id": None,
            "created_at": "2026-11-25T10:00:00+07:00",
            "started_at": None,
            "ended_at": None,
        }
        self.session.emplace("meeting", meeting)
        self.session.emplace("agenda", [dict(AGENDA_ITEM)])
        self.session.status = "ready"
        self.repo.create_meeting(meeting, status="ready")

    def run_socket(self, proposer, extractor=no_extraction):
        during_meeting.microphone_lock = asyncio.Lock()
        with (
            patch.object(meeting_service, "stream_transcript", fake_stream),
            patch.object(live_analysis, "propose_transitions", proposer),
            patch.object(live_analysis, "propose_items", extractor),
            patch.object(post_meeting, "extract_minutes", return_value=MinutesExtraction(
                summary="Offline", decisions=[], action_items=[], unresolved_issues=[])),
            TestClient(app) as client,
        ):
            response = client.post(f"/api/v1/meetings/{self.session.id}/start")
            self.assertEqual(response.status_code, 200, response.text)
            with client.websocket_connect(f"/ws/meetings/{self.session.id}") as ws:
                messages = []
                while True:
                    message = ws.receive_json()
                    messages.append(message)
                    if message["type"] == "minutes.ready":
                        segments = client.get(f"/api/v1/meetings/{self.session.id}/transcript").json()["segments"]
                        messages.append({"type": "done", "segments": segments})
                        return messages

    def test_state_change_is_pushed_in_the_contract_envelope(self):
        messages = self.run_socket(good_proposal)
        (event,) = [m for m in messages if m["type"] == "agenda.item_state"]
        self.assertEqual(event["meeting_id"], self.session.id)
        self.assertGreater(event["seq"], 0)
        self.assertEqual(event["data"]["from"], "not_discussed")
        self.assertEqual(event["data"]["to"], "in_progress")
        self.assertEqual(event["data"]["evidence"]["segment_ids"], ["seg_001"])
        self.assertEqual(self.session.get("agenda")[0]["state"], "in_progress")

    def test_committed_sentences_are_kept_with_times(self):
        messages = self.run_socket(good_proposal)
        done = messages[-1]
        self.assertEqual([s["id"] for s in done["segments"]], ["seg_001", "seg_002", "seg_003"])
        self.assertEqual(done["segments"][0]["start_seconds"], 1.0)
        reloaded = self.repo.load_session(self.session.id, self.data_root)
        self.assertIsNotNone(reloaded)
        self.assertEqual([s["id"] for s in reloaded.at("transcript")], ["seg_001", "seg_002", "seg_003"])
        self.assertIsNotNone(reloaded.at("meeting")["started_at"])
        self.assertIsNotNone(reloaded.at("meeting")["ended_at"])

    def test_weak_evidence_sends_nothing(self):
        def invented(agenda, segments, cursor):
            return [{"agenda_item_id": "agd_001", "to_state": "in_progress",
                     "segment_ids": ["seg_001"], "quote": "một câu bịa"}]

        messages = self.run_socket(invented)
        self.assertEqual([m for m in messages if m["type"] == "agenda.item_state"], [])
        self.assertEqual(self.session.get("agenda")[0]["state"], "not_discussed")

    def test_extractions_are_pushed_live_after_the_agenda_check(self):
        def extractor(segments, cursor, store, *_):
            return [{"type": "decision", "content": "Bàn API contract", "assignee": None,
                     "deadline": None, "agenda_item_id": None, "update_of": None,
                     "segment_ids": ["seg_001"], "quote": "bàn về API contract"}]

        messages = self.run_socket(good_proposal, extractor)
        envelopes = [m for m in messages if m["type"] in {"agenda.item_state", "extraction.created"}]
        self.assertEqual([m["type"] for m in envelopes], ["agenda.item_state", "extraction.created"])
        self.assertGreater(envelopes[1]["seq"], envelopes[0]["seq"])
        self.assertEqual(envelopes[1]["data"]["id"], "ext_001")
        self.assertEqual(envelopes[1]["data"]["evidence"]["segment_ids"], ["seg_001"])
        self.assertEqual(self.session.get("extraction_cursor"), 3)

    def test_failed_extraction_keeps_the_cursor(self):
        def broken(*_):
            raise RuntimeError("LLM down")

        self.run_socket(good_proposal, broken)
        self.assertIsNone(self.session.get("extraction_cursor"))

    def test_llm_failure_does_not_stop_the_transcript(self):
        def broken(agenda, segments, cursor):
            raise RuntimeError("LLM down")

        messages = self.run_socket(broken)
        self.assertEqual(messages[-1]["type"], "done")


if __name__ == "__main__":
    unittest.main()
