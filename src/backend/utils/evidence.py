"""Check that a quote the LLM gave really appears in the transcript segments it cites."""

import unicodedata


def _norm(text: str) -> str:
    # NFC keeps Vietnamese diacritics comparable; whitespace/case differences are tolerated.
    return " ".join(unicodedata.normalize("NFC", text).split()).casefold()


def verify(segment_ids: list[str], quote: str, by_id: dict[str, dict]) -> bool:
    """True only when every id exists and the quote is verbatim in their joined text."""
    needle = _norm(quote or "")
    if not needle or not segment_ids or any(i not in by_id for i in segment_ids):
        return False
    return needle in _norm(" ".join(by_id[i]["text"] for i in segment_ids))


def locate(quote: str, segments: list[dict]) -> list[str]:
    """Ids of the one segment containing the quote; [] when none or ambiguous."""
    needle = _norm(quote or "")
    if not needle:
        return []
    hits = [s["id"] for s in segments if needle in _norm(s["text"])]
    return hits if len(hits) == 1 else []


def is_low_confidence(segment_ids: list[str], by_id: dict[str, dict]) -> bool:
    return any(by_id[i]["is_low_confidence"] for i in segment_ids if i in by_id)
