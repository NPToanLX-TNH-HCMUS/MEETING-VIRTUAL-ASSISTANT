"""Turn a spoken deadline into a date, following the conversion table of UC7.

The LLM only copies the deadline words as spoken ("next Monday"); this module computes
the date, so the result is the same on every run. A phrase that gives no clear date
returns None (BR7.3: no guessing).
"""

import calendar
import re
from datetime import date, timedelta

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
MONTHS = ["january", "february", "march", "april", "may", "june", "july", "august",
          "september", "october", "november", "december"]
NUMS = {"a": 1, "an": 1, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6,
        "seven": 7, "eight": 8, "nine": 9, "ten": 10}

_DAY = r"(" + "|".join(DAYS) + r")"
# "november", "nov", "nov." -> month number
_MONTH = r"(" + "|".join(m[:3] + r"(?:" + m[3:] + r")?" for m in MONTHS) + r")\.?"
_ORDINAL = r"(\d{1,2})(?:st|nd|rd|th)?"


def _month_number(word: str) -> int:
    return next(i for i, m in enumerate(MONTHS, start=1) if m.startswith(word[:3]))


def _end_of_month(year: int, month: int) -> date:
    return date(year, month, calendar.monthrange(year, month)[1])


def resolve_due(phrase: str | None, meeting: date) -> str | None:
    """'next Monday' + meeting date -> 'YYYY-MM-DD'. None when the phrase gives no clear date."""
    if not phrase:
        return None
    p = phrase.lower()
    monday = meeting - timedelta(days=meeting.weekday())  # weeks start on Monday
    try:
        if re.search(r"\b(asap|soon|later|next meeting)\b", p):
            return None
        if m := re.search(r"\d{4}-\d{2}-\d{2}", p):
            return m.group()
        if "day after tomorrow" in p:
            d = meeting + timedelta(days=2)
        elif "today" in p:
            d = meeting
        elif "tomorrow" in p:
            d = meeting + timedelta(days=1)
        elif m := re.search(r"\bin (\w+) (day|week)s?\b", p):
            n = NUMS.get(m[1]) or (int(m[1]) if m[1].isdigit() else None)
            if n is None:
                return None
            d = meeting + timedelta(days=n * (7 if m[2] == "week" else 1))
        elif "end of next week" in p:
            d = monday + timedelta(days=7 + 4)                    # Friday of next week
        elif re.search(r"end of (this|the) week", p):
            d = monday + timedelta(days=4)                        # Friday of this week
        elif "end of next month" in p:
            first_next = _end_of_month(meeting.year, meeting.month) + timedelta(days=1)
            d = _end_of_month(first_next.year, first_next.month)
        elif re.search(r"end of (this|the) month", p):
            d = _end_of_month(meeting.year, meeting.month)
        elif (m := re.search(r"\b" + _MONTH + r"\s+" + _ORDINAL + r"\b", p)) or \
                (m2 := re.search(r"\b" + _ORDINAL + r"\s+(?:of\s+)?" + _MONTH, p)):
            month, day = (_month_number(m[1]), int(m[2])) if m else (_month_number(m2[2]), int(m2[1]))
            d = date(meeting.year, month, day)                    # "November 25th", "25th of November"
            if d < meeting:
                d = date(meeting.year + 1, month, day)
        elif (m := re.search(_DAY, p)) and "next week" in p:
            d = monday + timedelta(days=7 + DAYS.index(m[1]))     # "Friday next week"
        elif m := re.search(r"next " + _DAY, p):
            d = monday + timedelta(days=7 + DAYS.index(m[1]))     # that day of next week
        elif m := re.search(_DAY, p):
            d = monday + timedelta(days=DAYS.index(m[1]))         # "this Friday", "by Thursday"
            if d < meeting:
                d += timedelta(days=7)
        elif m := re.search(r"\bthe " + _ORDINAL + r"\b", p):
            day = int(m[1])
            d = meeting.replace(day=day)                          # "by the 25th"
            if d < meeting:                                       # day already passed: next month
                first_next = _end_of_month(meeting.year, meeting.month) + timedelta(days=1)
                d = first_next.replace(day=day)
        else:
            return None                                           # unclear: leave it empty
    except ValueError:                                            # a day that does not exist
        return None
    return d.isoformat()
