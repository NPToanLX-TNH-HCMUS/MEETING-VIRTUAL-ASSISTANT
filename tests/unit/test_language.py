"""What the AI writes follows the meeting language ("vi" / "en"). No network, no LLM."""

import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from src.backend.agenda_extractor.agenda_extractor import system_prompt
from src.backend.extraction.extractor import propose_items
from src.backend.minutes_extractor.minutes_extractor import _system_prompt, assemble_markdown
from src.backend.speech_to_text.segments import make_segment
from src.backend.speech_to_text.transcriber import ElevenLabsTranscriber
from src.backend.utils.language import date_context, language_name
from src.backend.utils.objects import ActionItem, MinutesExtraction


class TestPrompts(unittest.TestCase):
    def test_language_names(self):
        self.assertEqual((language_name("vi"), language_name("en"), language_name(None)),
                         ("Vietnamese", "English", "English"))

    def test_calendar_gives_weekdays_and_weeks(self):
        cal = date_context("2026-11-22")  # a Sunday
        self.assertIn("Today is 2026-11-22 (Sunday, Chủ Nhật).", cal)
        self.assertIn("- 2026-11-27 Friday / Thứ Sáu (next week / tuần sau)", cal)
        self.assertIn("- 2026-12-04 Friday / Thứ Sáu (in two weeks / hai tuần nữa)", cal)
        self.assertIn("- 2026-11-25 Wednesday / Thứ Tư (this week / tuần này)", date_context("2026-11-23"))

    def test_agenda_titles_follow_the_meeting_language(self):
        self.assertIn("Write every title in Vietnamese", system_prompt(30, "Họp", "vi"))
        self.assertIn("Write every title in English", system_prompt(30, "Sync", "en"))
        self.assertNotIn("English only", system_prompt(30, "Họp", "vi"))

    def test_minutes_follow_the_meeting_language(self):
        prompt = _system_prompt("vi")
        self.assertIn("Write in Vietnamese", prompt)
        self.assertIn("sentence in Vietnamese", prompt)
        self.assertNotIn("English only", prompt)

    def test_extraction_prompt_follows_the_meeting_language(self):
        segments = [make_segment("m", 1, "Bình sẽ làm xong frontend trước thứ Sáu tuần sau.", "vi")]
        with patch("src.backend.extraction.extractor.call_llm", return_value=json.dumps({"items": []})) as llm:
            propose_items(segments, 0, [], "2026-11-22", [], "vi")
        prompt = llm.call_args.args[0]
        self.assertIn("in Vietnamese, the language of the meeting", prompt)
        self.assertIn("thứ Sáu tuần sau", prompt)


class TestMinutesMarkdown(unittest.TestCase):
    extraction = MinutesExtraction(
        summary="Nhóm chốt ngân sách.",
        decisions=["Ngân sách là 5 triệu"],
        action_items=[ActionItem(task="Viết kế hoạch", assignee=None, due="2026-11-28", quote="q")],
        unresolved_issues=["Chọn công cụ test"],
    )

    def test_vietnamese_headings(self):
        md = assemble_markdown(self.extraction, "mtg_1", "Họp nhóm", "2026-11-22", "vi")
        for heading in ("# Biên bản cuộc họp — Họp nhóm", "## Tóm tắt", "## Quyết định",
                        "## Việc cần làm", "| Công việc | Người phụ trách | Hạn chót |",
                        "## Vấn đề chưa giải quyết", "_Mã cuộc họp: mtg_1_"):
            self.assertIn(heading, md)
        self.assertNotIn("Action Items", md)

    def test_english_stays_the_default(self):
        md = assemble_markdown(self.extraction, "mtg_1", "Sync", "2026-11-22")
        self.assertIn("# Meeting Minutes — Sync", md)
        self.assertIn("## Action Items", md)


class TestBatchSpeechToText(unittest.TestCase):
    def test_sends_the_meeting_language(self):
        with tempfile.TemporaryDirectory() as tmp:
            audio = Path(tmp) / "a.wav"
            with wave.open(str(audio), "wb") as w:
                w.setnchannels(1)
                w.setsampwidth(2)
                w.setframerate(16000)
                w.writeframes(b"\x00\x00" * 160)
            with patch("src.backend.speech_to_text.transcriber.requests.post") as post:
                post.return_value.ok = True
                post.return_value.json.return_value = {"text": "Xin chào", "words": []}
                ElevenLabsTranscriber(api_key="test").transcribe_file(audio, None, "vi")
            self.assertEqual(post.call_args.kwargs["data"]["language_code"], "vi")


if __name__ == "__main__":
    unittest.main()
