"""Committed segments: stable cursors, durable append, no fabricated STT metadata."""
import json
from uuid import uuid4


def append_segment(realtime, meeting_session, event):
    text = event.get("text", "").strip()
    if not text:
        return None

    with meeting_session:
        meeting = meeting_session.at("meeting")

        segment = {
            "id": event.get("id") or f"seg_{uuid4().hex}",
            "meeting_id": meeting_session.id,
            "start_seconds": event.get("start_seconds"),
            "end_seconds": event.get("end_seconds"),
            "speaker": event.get("speaker"),
            "text": text,
            "language": meeting["language"],
            "confidence": event.get("confidence"),
            "is_low_confidence": event.get("is_low_confidence", False),
        }

        if any(old["id"] == segment["id"] for old in realtime.transcript_segments):
            segment["id"] = f"seg_{uuid4().hex}"
        path = meeting_session.path(
            "during_meeting/transcript/segments.jsonl"
        )

        with path.open("a", encoding="utf-8") as output:
            output.write(
                json.dumps(segment, ensure_ascii=False) + "\n"
            )

        realtime.transcript_segments.append(segment)
        realtime.temp_transcript.append(text)
        meeting_session.emplace("transcript", realtime.transcript_segments)

    return segment


def segments_after(segments, after=None):
    if after is None:
        return list(segments)
    for position, segment in enumerate(segments):
        if segment["id"] == after:
            return list(segments[position + 1:])
    raise ValueError("Unknown transcript cursor")
