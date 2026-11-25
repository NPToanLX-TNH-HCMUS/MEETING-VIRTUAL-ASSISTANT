import unittest

from src.backend.agenda_tracker.fsm import ALLOWED, apply_proposals, apply_transition
from src.backend.speech_to_text.segments import make_segment

SEGMENTS = [
    make_segment("m", 1, "Bắt đầu bàn về API contract.", "vi"),
    make_segment("m", 2, "Được rồi, chốt dùng REST.", "vi"),
    make_segment("m", 3, "Âm thanh rất nhiễu ở đây.", "vi", confidence=0.1),
]
BY_ID = {s["id"]: s for s in SEGMENTS}
AT = "2026-10-28T16:50:10+07:00"


def item(state="not_discussed", started=None, ended=None):
    return {"id": "agd_001", "state": state, "started_at": started, "ended_at": ended}


def move(it, to, ids=("seg_001",), quote="bàn về API contract"):
    return apply_transition(it, to, list(ids), quote, BY_ID, AT)


class TestTransitions(unittest.TestCase):
    def test_full_path_and_reopen(self):
        it = item()
        self.assertEqual(move(it, "in_progress")["from"], "not_discussed")
        self.assertEqual((it["state"], it["started_at"], it["ended_at"]), ("in_progress", AT, None))
        move(it, "discussed")
        self.assertEqual((it["state"], it["ended_at"]), ("discussed", AT))
        reopened = move(it, "in_progress")
        self.assertEqual((reopened["from"], reopened["to"]), ("discussed", "in_progress"))
        self.assertIsNone(it["ended_at"])
        move(it, "discussed")
        move(it, "concluded", ids=("seg_002",), quote="chốt dùng REST")
        self.assertEqual(it["state"], "concluded")

    def test_event_data_matches_contract(self):
        self.assertEqual(
            move(item(), "in_progress"),
            {
                "agenda_item_id": "agd_001",
                "from": "not_discussed",
                "to": "in_progress",
                "evidence": {"segment_ids": ["seg_001"], "quote": "bàn về API contract"},
            },
        )

    def test_started_at_is_kept_when_reopened(self):
        it = item("discussed", started="earlier", ended="x")
        move(it, "in_progress")
        self.assertEqual(it["started_at"], "earlier")

    def test_every_other_move_is_refused(self):
        states = ["not_discussed", "in_progress", "discussed", "concluded"]
        for src in states:
            for dst in states:
                if (src, dst) in ALLOWED:
                    continue
                with self.subTest(src=src, dst=dst):
                    it = item(src)
                    self.assertIsNone(move(it, dst))
                    self.assertEqual(it["state"], src)

    def test_weak_evidence_never_moves_the_item(self):
        weak = [
            ((), "bàn về API contract"),  # no segment
            (("seg_001",), ""),  # no quote
            (("seg_999",), "bàn về API contract"),  # unknown segment
            (("seg_001",), "một câu bịa"),  # not verbatim
            (("seg_003",), "rất nhiễu"),  # low-confidence segment
        ]
        for ids, quote in weak:
            with self.subTest(ids=ids, quote=quote):
                it = item()
                self.assertIsNone(move(it, "in_progress", ids, quote))
                self.assertEqual((it["state"], it["started_at"]), ("not_discussed", None))


class TestProposals(unittest.TestCase):
    def test_only_valid_proposals_become_events(self):
        agenda = [item(), {**item(), "id": "agd_002"}]
        proposals = [
            {"agenda_item_id": "agd_001", "to_state": "in_progress", "segment_ids": ["seg_001"], "quote": "API contract"},
            {"agenda_item_id": "agd_002", "to_state": "concluded", "segment_ids": ["seg_002"], "quote": "chốt dùng REST"},  # skips states
            {"agenda_item_id": "agd_404", "to_state": "in_progress", "segment_ids": ["seg_001"], "quote": "API contract"},
        ]
        events = apply_proposals(agenda, proposals, SEGMENTS, AT)
        self.assertEqual([(e["agenda_item_id"], e["to"]) for e in events], [("agd_001", "in_progress")])
        self.assertEqual(agenda[1]["state"], "not_discussed")

    def test_old_lines_cannot_trigger_a_change_again(self):
        agenda = [item("discussed")]
        reopen = {"agenda_item_id": "agd_001", "to_state": "in_progress",
                  "segment_ids": ["seg_001"], "quote": "bàn về API contract"}
        self.assertEqual(apply_proposals(agenda, [reopen], SEGMENTS, AT, new_ids={"seg_002", "seg_003"}), [])
        self.assertEqual(agenda[0]["state"], "discussed")
        self.assertEqual(len(apply_proposals(agenda, [reopen], SEGMENTS, AT, new_ids={"seg_001"})), 1)

    def test_decision_while_in_progress_concludes_in_two_events(self):
        agenda = [item("in_progress", started="t0")]
        step = {"agenda_item_id": "agd_001", "segment_ids": ["seg_002"], "quote": "chốt dùng REST"}
        events = apply_proposals(
            agenda, [{**step, "to_state": "discussed"}, {**step, "to_state": "concluded"}], SEGMENTS, AT
        )
        self.assertEqual([(e["from"], e["to"]) for e in events],
                         [("in_progress", "discussed"), ("discussed", "concluded")])
        self.assertEqual(agenda[0]["state"], "concluded")


if __name__ == "__main__":
    unittest.main()
