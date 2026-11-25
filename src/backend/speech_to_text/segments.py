"""Turn raw speech-to-text output into TranscriptSegment dicts (contract section 5.5)."""

import math
import re
from time import monotonic

# Design assumption, not a measured value: below this a segment is flagged for review.
LOW_CONFIDENCE_THRESHOLD = 0.6

_TIME = r"(\d+):(\d{2})\.(\d{2})"
_RANGE = re.compile(rf"^{_TIME} - {_TIME}$")


def make_segment(
    meeting_id: str,
    index: int,
    text: str,
    language: str | None,
    start_seconds: float | None = None,
    end_seconds: float | None = None,
    speaker: str | None = None,
    confidence: float | None = None,
) -> dict:
    return {
        "id": f"seg_{index:03d}",
        "meeting_id": meeting_id,
        "start_seconds": start_seconds,
        "end_seconds": end_seconds,
        "speaker": speaker,
        "text": text,
        "language": language,
        "confidence": confidence,
        # Unknown confidence is not "low": the flag never guesses.
        "is_low_confidence": confidence is not None
        and confidence < LOW_CONFIDENCE_THRESHOLD,
    }


def _seconds(match: tuple[str, str, str]) -> float:
    minutes, whole, centi = (int(part) for part in match)
    return minutes * 60 + whole + centi / 100


def parse_range(timestamp: str) -> tuple[float | None, float | None]:
    """Parse "MM:SS.cc - MM:SS.cc"; anything else (incl. "unknown") gives no times."""
    found = _RANGE.match(timestamp or "")
    if not found:
        return None, None
    groups = found.groups()
    return _seconds(groups[:3]), _seconds(groups[3:])


def from_batch(turns: list[dict], meeting_id: str, language: str | None) -> list[dict]:
    """Convert ElevenLabsTranscriber turns (Timestamp/Speaker/Text) into segments."""
    segments = []
    for index, turn in enumerate(turns, start=1):
        start, end = parse_range(turn.get("Timestamp", ""))
        speaker = turn.get("Speaker")
        segments.append(
            make_segment(
                meeting_id,
                index,
                turn["Text"],
                language,
                start,
                end,
                None if speaker in (None, "unknown") else speaker,
                turn.get("Confidence"),
            )
        )
    return segments


def confidence_from_logprobs(logprobs: list[float]) -> float | None:
    """Geometric-mean token probability; None when the provider sent none."""
    if not logprobs:
        return None
    return round(math.exp(sum(logprobs) / len(logprobs)), 3)


class ActiveClock:
    """Seconds since the meeting started, excluding paused time (contract 5.5)."""

    def __init__(self, now=monotonic):
        self._now = now
        self._started = None
        self._paused_total = 0.0
        self._paused_since = None

    def start(self) -> None:
        self._started = self._now()

    def pause(self) -> None:
        if self._started is not None and self._paused_since is None:
            self._paused_since = self._now()

    def resume(self) -> None:
        if self._paused_since is not None:
            self._paused_total += self._now() - self._paused_since
            self._paused_since = None

    def seconds(self) -> float | None:
        if self._started is None:
            return None
        now = self._paused_since if self._paused_since is not None else self._now()
        return now - self._started - self._paused_total
