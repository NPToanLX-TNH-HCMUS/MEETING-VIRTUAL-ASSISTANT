"""The meeting language (Meeting.language, "vi" or "en") decides the language of what the
AI writes: agenda titles, extracted items and the minutes. The UI language is separate."""

LANGUAGE_NAMES = {"vi": "Vietnamese", "en": "English"}


def language_name(code: str | None) -> str:
    # The API only accepts "vi" and "en"; anything else falls back to English.
    return LANGUAGE_NAMES.get(code or "en", "English")


_DAYS_EN = ("Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday")
_DAYS_VI = ("Thứ Hai", "Thứ Ba", "Thứ Tư", "Thứ Năm", "Thứ Sáu", "Thứ Bảy", "Chủ Nhật")


def date_context(meeting_date: str, days: int = 14) -> str:
    """A small calendar for the prompt: LLMs often miscount weekdays ("next Friday",
    "thứ Sáu tuần sau"), so the dates are given instead of left to arithmetic.
    Weeks start on Monday, as in Vietnam."""
    from datetime import date, timedelta

    today = date.fromisoformat(meeting_date)
    week_start = today - timedelta(days=today.weekday())
    lines = [f"Today is {today.isoformat()} ({_DAYS_EN[today.weekday()]}, {_DAYS_VI[today.weekday()]})."]
    lines.append(
        "Calendar (weeks start on Monday). For a weekday such as \"Friday next week\" or "
        "\"thứ Sáu tuần sau\", find the line with that weekday AND that week label and copy "
        "its date. Do not compute dates yourself:"
    )
    for k in range(1, days + 1):
        day = today + timedelta(days=k)
        week = (day - week_start).days // 7
        label = {0: "this week / tuần này", 1: "next week / tuần sau"}.get(week, "in two weeks / hai tuần nữa")
        lines.append(f"- {day.isoformat()} {_DAYS_EN[day.weekday()]} / {_DAYS_VI[day.weekday()]} ({label})")
    return "\n".join(lines)
