import json
import tempfile
import unicodedata
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient

from src.backend.context.app_context import AppContext
from src.backend.extraction.extractor import build_extractions, merge_items
from src.backend.main import app
from src.backend.speech_to_text.segments import make_segment

SEGMENTS = [
    make_segment("m", 1, "Bình sẽ hoàn thành frontend trước ngày 20/10.", "vi", 5.0, 9.0),
    make_segment("m", 2, "Chúng ta thống nhất dùng REST.", "vi", 10.0, 12.0),
    make_segment("m", 3, "Còn chuyện hosting thì chưa rõ.", "vi", 13.0, 15.0, confidence=0.2),
]


def raw(**over):
    base = {
        "type": "action_item",
        "content": "Finish frontend",
        "assignee": "Bình",
        "deadline": "2026-10-20",
        "agenda_item_id": None,
        "segment_ids": ["seg_001"],
        "quote": "Bình sẽ hoàn thành frontend trước ngày 20/10.",
    }
    return {**base, **over}


def build(*items, agenda_ids=frozenset()):
    return build_extractions(list(items), SEGMENTS, "m", agenda_ids)


class TestBuildExtractions(unittest.TestCase):
    def test_complete_item_has_evidence_and_nothing_missing(self):
        (item,) = build(raw())
        self.assertEqual(item["id"], "ext_001")
        self.assertEqual(item["evidence"], {"segment_ids": ["seg_001"], "quote": raw()["quote"]})
        self.assertEqual(item["missing_fields"], [])
        self.assertFalse(item["needs_confirmation"])
        self.assertFalse(item["is_low_confidence"])

    def test_null_fields_are_listed_not_guessed(self):
        (item,) = build(raw(assignee=None, deadline=None))
        self.assertIsNone(item["assignee"])
        self.assertIsNone(item["deadline"])
        self.assertEqual(item["missing_fields"], ["assignee", "deadline"])
        self.assertTrue(item["needs_confirmation"])

    def test_blank_assignee_and_bad_date_count_as_missing(self):
        (item,) = build(raw(assignee="  ", deadline="next week"))
        self.assertEqual(item["missing_fields"], ["assignee", "deadline"])

    def test_decision_has_no_required_fields(self):
        (item,) = build(raw(type="decision", assignee=None, deadline=None,
                            segment_ids=["seg_002"], quote="thống nhất dùng REST"))
        self.assertEqual(item["missing_fields"], [])
        self.assertFalse(item["needs_confirmation"])

    def test_deadline_type_requires_deadline(self):
        (item,) = build(raw(type="deadline", deadline=None))
        self.assertEqual(item["missing_fields"], ["deadline"])

    def test_invented_quote_leaves_evidence_empty(self):
        (item,) = build(raw(quote="Một câu chưa ai nói."))
        self.assertEqual(item["evidence"], {"segment_ids": [], "quote": ""})
        self.assertTrue(item["needs_confirmation"])

    def test_unknown_segment_id_is_not_trusted(self):
        (item,) = build(raw(segment_ids=["seg_999"], quote="Bình sẽ hoàn thành"))
        # Wrong id, but the quote is verbatim in exactly one segment, so it is recovered.
        self.assertEqual(item["evidence"]["segment_ids"], ["seg_001"])
        (item,) = build(raw(segment_ids=["seg_999"], quote="câu không tồn tại"))
        self.assertEqual(item["evidence"]["segment_ids"], [])

    def test_ambiguous_quote_is_not_recovered(self):
        segments = SEGMENTS + [make_segment("m", 4, "Chúng ta thống nhất dùng REST.", "vi")]
        (item,) = build_extractions(
            [raw(segment_ids=[], quote="thống nhất dùng REST")], segments, "m"
        )
        self.assertEqual(item["evidence"]["segment_ids"], [])

    def test_vietnamese_quote_matches_across_unicode_forms_and_spacing(self):
        decomposed = unicodedata.normalize("NFD", "Bình  sẽ hoàn thành")
        (item,) = build(raw(quote=decomposed))
        self.assertEqual(item["evidence"]["segment_ids"], ["seg_001"])

    def test_low_confidence_segment_flags_the_item(self):
        (item,) = build(raw(type="unresolved_issue", segment_ids=["seg_003"],
                            quote="hosting thì chưa rõ"))
        self.assertTrue(item["is_low_confidence"])
        self.assertTrue(item["needs_confirmation"])

    def test_agenda_id_must_exist(self):
        self.assertIsNone(build(raw(agenda_item_id="agd_9"), agenda_ids={"agd_001"})[0]["agenda_item_id"])
        self.assertEqual(build(raw(agenda_item_id="agd_001"), agenda_ids={"agd_001"})[0]["agenda_item_id"], "agd_001")

    def test_bad_type_or_empty_content_is_dropped_and_ids_stay_sequential(self):
        items = build(raw(type="gossip"), raw(content=" "), raw(), raw(type="decision"))
        self.assertEqual([i["id"] for i in items], ["ext_001", "ext_002"])


class TestMergeItems(unittest.TestCase):
    def setUp(self):
        self.store, events = merge_items([], [raw(deadline=None)], SEGMENTS, "m")
        self.assertEqual([(t, i["id"]) for t, i in events], [("extraction.created", "ext_001")])

    def test_new_items_get_the_next_id(self):
        store, events = merge_items(self.store, [raw(type="decision", segment_ids=["seg_002"], quote="dùng REST")], SEGMENTS, "m")
        self.assertEqual([i["id"] for i in store], ["ext_001", "ext_002"])
        self.assertEqual(events[0][0], "extraction.created")
        self.assertEqual(len(self.store), 1, "the input store is not modified")

    def test_repeated_item_is_not_captured_twice(self):
        store, events = merge_items(self.store, [raw(update_of=None)], SEGMENTS, "m")
        self.assertEqual((len(store), events), (1, []))

    def test_update_fills_a_missing_field(self):
        segments = SEGMENTS + [make_segment("m", 4, "Hạn của Bình là ngày 30/10 nhé.", "vi")]
        store, events = merge_items(
            self.store,
            [raw(update_of="ext_001", assignee=None, deadline="2026-10-30", segment_ids=["seg_004"], quote="Hạn của Bình là ngày 30/10")],
            segments, "m",
        )
        ((kind, item),) = events
        self.assertEqual((kind, item["id"]), ("extraction.updated", "ext_001"))
        self.assertEqual((item["assignee"], item["deadline"]), ("Bình", "2026-10-30"), "null never erases")
        self.assertEqual(item["evidence"]["segment_ids"], ["seg_001", "seg_004"])
        self.assertEqual(item["missing_fields"], [])
        # It was flagged (deadline missing) before; only the user may clear that.
        self.assertTrue(item["needs_confirmation"])

    def test_changed_deadline_needs_confirmation(self):
        store, _ = merge_items([], [raw()], SEGMENTS, "m")
        store[0]["needs_confirmation"] = False
        segments = SEGMENTS + [make_segment("m", 4, "Dời deadline frontend sang ngày 02/11.", "vi")]
        _, events = merge_items(
            store,
            [raw(update_of="ext_001", deadline="2026-11-02", segment_ids=["seg_004"], quote="sang ngày 02/11")],
            segments, "m",
        )
        self.assertEqual(events[0][1]["deadline"], "2026-11-02")
        self.assertTrue(events[0][1]["needs_confirmation"])

    def test_update_without_evidence_changes_nothing(self):
        store, events = merge_items(
            self.store, [raw(update_of="ext_001", deadline="2026-12-01", quote="câu bịa")], SEGMENTS, "m"
        )
        self.assertEqual(events, [])
        self.assertIsNone(store[0]["deadline"])

    def test_update_of_unknown_id_is_a_new_item(self):
        store, events = merge_items(
            self.store, [raw(update_of="ext_999", type="decision", segment_ids=["seg_002"], quote="dùng REST")], SEGMENTS, "m"
        )
        self.assertEqual(events[0][0], "extraction.created")


class TestExtractionsEndpoint(unittest.TestCase):
    def setUp(self):
        # A temp data root keeps the tests from creating folders under ./data.
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        original = app.state.ctx
        app.state.ctx = AppContext(Path(tmp.name))
        self.addCleanup(setattr, app.state, "ctx", original)
        self.client = TestClient(app)
        session = app.state.ctx.create_session()
        self.session = session
        self.url = f"/api/v1/meetings/{session.id}/extractions"
        session.emplace("meeting", {"id": session.id, "language": "vi", "ended_at": None})

    def test_not_available_before_the_meeting(self):
        self.session.status = "ready"
        response = self.client.get(self.url)
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "INVALID_MEETING_STATE"))

    def test_live_reads_what_was_captured_without_calling_the_llm(self):
        self.session.status = "live"
        self.session.emplace("transcript", SEGMENTS)
        with patch("src.backend.extraction.extractor.call_llm") as call_llm:
            self.assertEqual(self.client.get(self.url).json(), {"items": []})
            call_llm.assert_not_called()

    def test_after_stop_only_the_tail_goes_to_the_llm(self):
        store, _ = merge_items([], [raw()], SEGMENTS, "m")
        self.session.status = "processing"
        self.session.emplace("transcript", SEGMENTS)
        self.session.emplace("extractions", store)
        self.session.emplace("extraction_cursor", 2)
        tail = [raw(type="unresolved_issue", segment_ids=["seg_003"], quote="hosting thì chưa rõ")]
        with patch("src.backend.extraction.extractor.call_llm") as call_llm:
            call_llm.return_value = json.dumps({"items": tail})
            items = self.client.get(self.url).json()["items"]
            self.client.get(self.url)
            self.assertEqual(call_llm.call_count, 1)
        prompt = call_llm.call_args.args[0]
        self.assertIn("Lines before seg_003", prompt)
        self.assertIn("ext_001 [action_item]", prompt)
        self.assertEqual([i["id"] for i in items], ["ext_001", "ext_002"])

    def test_needs_a_transcript(self):
        self.session.status = "processing"
        response = self.client.get(self.url)
        self.assertEqual((response.status_code, response.json()["error"]["code"]), (409, "TRANSCRIPT_NOT_FOUND"))

    def test_runs_once_then_serves_cache_and_filters_by_type(self):
        self.session.status = "processing"
        self.session.emplace("transcript", SEGMENTS)
        llm = [raw(), raw(type="decision", segment_ids=["seg_002"], quote="dùng REST")]
        with patch("src.backend.extraction.extractor.call_llm") as call_llm:
            call_llm.return_value = json.dumps({"items": llm})
            everything = self.client.get(self.url).json()["items"]
            only_decisions = self.client.get(self.url + "?type=decision").json()["items"]
            self.assertEqual(call_llm.call_count, 1)
        self.assertEqual([i["type"] for i in everything], ["action_item", "decision"])
        self.assertEqual([i["type"] for i in only_decisions], ["decision"])

    def test_rejects_unknown_type(self):
        self.session.status = "processing"
        self.assertEqual(self.client.get(self.url + "?type=nope").status_code, 422)

    def test_transcript_endpoint_after(self):
        self.session.emplace("transcript", SEGMENTS)
        base = f"/api/v1/meetings/{self.session.id}/transcript"
        self.assertEqual(len(self.client.get(base).json()["segments"]), 3)
        self.assertEqual([s["id"] for s in self.client.get(base + "?after=seg_001").json()["segments"]], ["seg_002", "seg_003"])
        self.assertEqual(self.client.get(base + "?after=seg_x").status_code, 404)


if __name__ == "__main__":
    unittest.main()
