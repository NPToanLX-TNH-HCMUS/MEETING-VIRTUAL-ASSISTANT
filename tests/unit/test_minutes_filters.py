import unittest
from types import SimpleNamespace

from src.backend.minutes_extractor.minutes_extractor import drop_task_decisions


def task(text, assignee=None):
    return SimpleNamespace(task=text, assignee=assignee)


class DropTaskDecisionsTest(unittest.TestCase):
    def test_task_with_owner_is_not_a_decision(self):
        # e2e S07: assignments repeated as decisions
        items = [task("Fix the real-time transcription bug", "Tim"),
                 task("Review the API router pull request", "Tom")]
        decisions = ["Tim will fix the real-time transcription bug",
                     "Tom will review the API router pull request",
                     "The demo starts with the recording and ends with the minutes"]
        self.assertEqual(drop_task_decisions(decisions, items),
                         ["The demo starts with the recording and ends with the minutes"])

    def test_passive_wording(self):
        # e2e S06: "will be written by Tom"
        items = [task("Write the test report", "Tom")]
        self.assertEqual(drop_task_decisions(["The test report will be written by Tom."], items), [])

    def test_decision_without_owner_is_kept(self):
        # e2e S05: the model copied decisions into the action items; the decision stays
        items = [task("Incorporate a jog dial into the device design", "design team")]
        decisions = ["Incorporate a jog dial into the device design"]
        self.assertEqual(drop_task_decisions(decisions, items), decisions)

    def test_unrelated_decision_is_kept(self):
        items = [task("Download the MeetingBank audio", "Tom")]
        decisions = ["We will use AMI and MeetingBank as dataset sources"]
        self.assertEqual(drop_task_decisions(decisions, items), decisions)

    def test_task_without_assignee_never_removes(self):
        items = [task("Check the server logs", None)]
        decisions = ["Check the server logs before Friday"]
        self.assertEqual(drop_task_decisions(decisions, items), decisions)


if __name__ == "__main__":
    unittest.main()
