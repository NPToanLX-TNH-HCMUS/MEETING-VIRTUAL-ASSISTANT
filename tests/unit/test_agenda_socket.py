"""The live socket sends agenda.item_state after enough sentences (no mic, no LLM, no network)."""

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.backend.api import during_meeting
from src.backend.context.app_context import AppContext
from src.backend.main import app

AGENDA_ITEM = {
    "id": "agd_001", "title": "API contract", "state": "not_discussed",
    "started_at": None, "ended_at": None,
}


async def fake_stream(send_event, **_):
    await send_event({"type": "ready", "message": "go"})
    for n, text in enumerate(["Mình bàn về API contract.", "Ok.", "Tiếp."], start=1):
        await send_event({
            "type": "committed", "text": text, "id": f"seg_{n:03d}",
            "start_seconds": float(n), "end_seconds": n + 0.5,
        })
    await asyncio.sleep(0.5)  # let the background agenda check finish before the stream ends
    return "Mình bàn về API contract.\nOk.\nTiếp."


def good_proposal(agenda, segments, cursor):
    return [{"agenda_item_id": "agd_001", "to_state": "in_progress",
             "segment_ids": ["seg_001"], "quote": "bàn về API contract"}]


def no_extraction(segments, cursor, store, *_):
    return store, []


class TestAgendaSocket(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        original = app.state.ctx
        app.state.ctx = AppContext(Path(tmp.name))
        self.addCleanup(setattr, app.state, "ctx", original)
        self.session = app.state.ctx.create_session()
        self.session.emplace("meeting", {"id": self.session.id, "language": "vi", "started_at": None, "ended_at": None})
        self.session.emplace("agenda", [dict(AGENDA_ITEM)])
        self.session.status = "ready"

    def run_socket(self, proposer, extractor=no_extraction):
        with (
            patch.object(during_meeting, "stream_transcript", fake_stream),
            patch.object(during_meeting, "propose_transitions", proposer),
            patch.object(during_meeting, "extract_pass", extractor),
            TestClient(app) as client,
            client.websocket_connect(f"/ws/meetings/{self.session.id}/transcript-test") as ws,
        ):
            messages = []
            while True:
                message = ws.receive_json()
                messages.append(message)
                if message["type"] in {"done", "error"}:
                    return messages

    def test_state_change_is_pushed_in_the_contract_envelope(self):
        messages = self.run_socket(good_proposal)
        (event,) = [m for m in messages if m["type"] == "agenda.item_state"]
        self.assertEqual(event["meeting_id"], self.session.id)
        self.assertEqual(event["seq"], 1)
        self.assertEqual(event["data"]["from"], "not_discussed")
        self.assertEqual(event["data"]["to"], "in_progress")
        self.assertEqual(event["data"]["evidence"]["segment_ids"], ["seg_001"])
        self.assertEqual(self.session.get("agenda")[0]["state"], "in_progress")

    def test_committed_sentences_are_kept_with_times(self):
        messages = self.run_socket(good_proposal)
        done = messages[-1]
        self.assertEqual([s["id"] for s in done["segments"]], ["seg_001", "seg_002", "seg_003"])
        self.assertEqual(done["segments"][0]["start_seconds"], 1.0)

    def test_weak_evidence_sends_nothing(self):
        def invented(agenda, segments, cursor):
            return [{"agenda_item_id": "agd_001", "to_state": "in_progress",
                     "segment_ids": ["seg_001"], "quote": "một câu bịa"}]

        messages = self.run_socket(invented)
        self.assertEqual([m for m in messages if m["type"] == "agenda.item_state"], [])
        self.assertEqual(self.session.get("agenda")[0]["state"], "not_discussed")

    def test_extractions_are_pushed_live_after_the_agenda_check(self):
        def extractor(segments, cursor, store, meeting_id, *_):
            item = {"id": "ext_001", "type": "decision"}
            return [item], [("extraction.created", item)]

        messages = self.run_socket(good_proposal, extractor)
        envelopes = [m for m in messages if "seq" in m]
        self.assertEqual([(m["type"], m["seq"]) for m in envelopes],
                         [("agenda.item_state", 1), ("extraction.created", 2)])
        self.assertEqual(envelopes[1]["data"]["id"], "ext_001")
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
