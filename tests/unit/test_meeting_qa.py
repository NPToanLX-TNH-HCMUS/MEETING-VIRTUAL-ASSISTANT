"""In-meeting Q&A: context selection, citation checks and the /ask route (no network, no LLM)."""

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend.api import during_meeting
from src.backend.context.app_context import AppContext
from src.backend.meeting_qa import qa

MEETING = {"id": "mtg_1", "topic": "Ra mắt app", "language": "vi", "duration_minutes": 30}
AGENDA = [{"id": "agd_001", "title": "API contract", "state": "concluded"},
          {"id": "agd_002", "title": "Demo", "state": "in_progress"}]


def seg(n, text, end=None):
    return {"id": f"seg_{n:03d}", "text": text, "speaker": None,
            "start_seconds": float(n), "end_seconds": end if end is not None else n + 0.5}


class TestSelectLines(unittest.TestCase):
    def test_short_transcript_is_sent_whole(self):
        segments = [seg(1, "a"), seg(2, "b")]
        self.assertEqual(qa.select_lines(segments, "x"), [0, 1])

    def test_long_transcript_keeps_hits_with_context(self):
        segments = [seg(i, f"câu số {i} " + "x" * 50) for i in range(1, 41)]
        segments[10]["text"] = "Hạn chót của bản demo là thứ Sáu"
        picked = qa.select_lines(segments, "hạn chót demo khi nào?", budget=400)
        self.assertTrue({8, 9, 10, 11, 12} <= set(picked))
        self.assertEqual(picked, sorted(picked))
        self.assertLessEqual(sum(len(segments[i]["text"]) for i in picked), 400)

    def test_decomposed_vietnamese_still_matches(self):
        import unicodedata
        segments = [seg(i, "y" * 60) for i in range(1, 21)]
        segments[3]["text"] = "Hạn chót là thứ Sáu"
        question = unicodedata.normalize("NFD", "hạn chót")
        self.assertIn(3, qa.select_lines(segments, question, budget=200))


class TestAnswer(unittest.TestCase):
    def test_time_question_does_not_call_the_llm(self):
        with patch.object(qa, "call_llm") as llm:
            result = qa.answer_question(MEETING, AGENDA, [seg(1, "a", end=600.0)], [], "Còn bao lâu nữa?")
        llm.assert_not_called()
        self.assertEqual(result["intent"], "time_progress")
        self.assertIn("còn 20 phút", result["answer"])
        self.assertIn("1/2", result["answer"])

    def test_made_up_citations_are_dropped(self):
        reply = json.dumps({"intent": "meeting_information", "answer": "Thứ Sáu.", "cites": [2, 2, 9, 0]})
        with patch.object(qa, "call_llm", return_value=reply):
            result = qa.answer_question(MEETING, AGENDA, [seg(1, "a"), seg(2, "Hạn là thứ Sáu")], [], "Hạn khi nào?")
        self.assertEqual(result["sources"], ["seg_002"])
        self.assertFalse(result["is_ai_suggestion"])

    def test_idea_suggestion_is_flagged(self):
        reply = json.dumps({"intent": "idea_suggestion", "answer": "Thử A/B test.", "cites": []})
        with patch.object(qa, "call_llm", return_value=reply):
            result = qa.answer_question(MEETING, AGENDA, [seg(1, "a")], [], "Gợi ý cách làm?")
        self.assertTrue(result["is_ai_suggestion"])
        self.assertEqual(result["sources"], [])


class TestAskRoute(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        app = FastAPI()  # only this router: the test needs neither the mic nor the other stages
        app.include_router(during_meeting.router, prefix="/api/v1")
        app.state.ctx = AppContext(Path(tmp.name))
        self.client = TestClient(app)
        self.session = app.state.ctx.create_session()
        self.session.emplace("meeting", dict(MEETING, id=self.session.id))
        self.session.emplace("agenda", [dict(item) for item in AGENDA])
        self.session.emplace("transcript", [seg(1, "Hạn là thứ Sáu")])
        self.url = f"/api/v1/meetings/{self.session.id}/ask"

    def test_wrong_status_is_409(self):
        self.session.status = "ready"
        response = self.client.post(self.url, json={"question": "Hạn khi nào?"})
        self.assertEqual(response.status_code, 409)
        self.assertEqual(response.json()["error"]["code"], "INVALID_MEETING_STATE")

    def test_blank_question_is_400(self):
        self.session.status = "live"
        response = self.client.post(self.url, json={"question": "   "})
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")

    def test_answer_and_history(self):
        self.session.status = "live"
        reply = json.dumps({"intent": "meeting_information", "answer": "Thứ Sáu.", "cites": [1]})
        with patch.object(qa, "call_llm", return_value=reply):
            response = self.client.post(self.url, json={"question": "Hạn khi nào?"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["sources"], ["seg_001"])
        self.assertEqual(self.session.get("qa_history"), [{"question": "Hạn khi nào?", "answer": "Thứ Sáu."}])


if __name__ == "__main__":
    unittest.main()
