import unittest
from datetime import date

from src.backend.minutes_extractor.dates import resolve_due

MONDAY = date(2026, 11, 16)    # table of UC7 (USE_CASES.md)
S06_TUESDAY = date(2026, 11, 24)
S07_TUESDAY = date(2026, 12, 1)


class ResolveDueTest(unittest.TestCase):
    def test_uc7_table(self):
        cases = {
            "tomorrow": "2026-11-17",
            "by Wednesday": "2026-11-18",
            "this Friday": "2026-11-20",
            "next Monday": "2026-11-23",
            "by the 25th": "2026-11-25",
            "end of next week": "2026-11-27",
            "in two weeks": "2026-11-30",
            "ASAP": None,
            "soon": None,
            "before the next meeting": None,
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_due(phrase, MONDAY), expected)

    def test_team_meetings(self):
        self.assertEqual(resolve_due("next Monday", S06_TUESDAY), "2026-11-30")       # C2, after the change
        self.assertEqual(resolve_due("by Thursday", S06_TUESDAY), "2026-11-26")
        self.assertEqual(resolve_due("end of next week", S06_TUESDAY), "2026-12-04")
        self.assertEqual(resolve_due("in two weeks", S06_TUESDAY), "2026-12-08")
        self.assertEqual(resolve_due("before Friday", S07_TUESDAY), "2026-12-04")

    def test_other_phrases(self):
        cases = {
            "Friday next week": "2026-12-04",
            "next week on Friday": "2026-12-04",
            "day after tomorrow": "2026-11-26",
            "in a week": "2026-12-01",
            "in 10 days": "2026-12-04",
            "by November 25th": "2026-11-25",
            "25th of November": "2026-11-25",
            "Nov. 30": "2026-11-30",
            "end of the month": "2026-11-30",
            "end of next month": "2026-12-31",
        }
        for phrase, expected in cases.items():
            with self.subTest(phrase=phrase):
                self.assertEqual(resolve_due(phrase, S06_TUESDAY), expected)

    def test_dates_across_the_year(self):
        december = date(2026, 12, 28)
        self.assertEqual(resolve_due("January 5th", december), "2027-01-05")
        self.assertEqual(resolve_due("end of next month", december), "2027-01-31")

    def test_no_clear_date(self):
        for phrase in (None, "", "some day", "next week", "by the 31st"):  # November has 30 days
            with self.subTest(phrase=phrase):
                self.assertIsNone(resolve_due(phrase, S06_TUESDAY))


if __name__ == "__main__":
    unittest.main()
