"""Turn a spoken deadline into a date"""

import re
from datetime import date, timedelta

DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
NUMS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}


def resolve_due(phrase: str | None, meeting: date) -> str | None:
    """'next Monday' + meeting date -> 'YYYY-MM-DD'. None when the phrase gives no clear date."""
    if not phrase:
        return None
    p = phrase.lower()
    monday = meeting - timedelta(days=meeting.weekday())
    if re.search(r"\b(asap|soon|later|next meeting)\b", p):
        return None
    if m := re.search(r"\d{4}-\d{2}-\d{2}", p):
        return m.group()
    if "today" in p:
        d = meeting
    elif "tomorrow" in p:
        d = meeting + timedelta(days=1)
    elif m := re.search(r"in (\w+) (day|week)s?", p):
        n = NUMS.get(m[1]) or (int(m[1]) if m[1].isdigit() else None)
        if n is None:
            return None
        d = meeting + timedelta(days=n * (7 if m[2] == "week" else 1))
    elif "end of next week" in p:
        d = monday + timedelta(days=7 + 4)                 # Friday of next week
    elif re.search(r"end of (this|the) week", p):
        d = monday + timedelta(days=4)                     # Friday of this week
    elif m := re.search(r"next (" + "|".join(DAYS) + r")", p):
        d = monday + timedelta(days=7 + DAYS.index(m[1]))  # that day of next week
    elif m := re.search("(" + "|".join(DAYS) + ")", p):
        d = monday + timedelta(days=DAYS.index(m[1]))      # "this Friday", "by Thursday"
        if d < meeting:
            d += timedelta(days=7)
    elif m := re.search(r"\bthe (\d{1,2})(?:st|nd|rd|th)\b", p):
        try:
            d = meeting.replace(day=int(m[1]))
            if d < meeting:                                # day already passed: next month
                d = (meeting.replace(day=1) + timedelta(days=32)).replace(day=int(m[1]))
        except ValueError:
            return None
    else:
        return None                                        # unclear: leave it empty
    return d.isoformat()