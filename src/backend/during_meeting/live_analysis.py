import asyncio
import logging
from copy import deepcopy

from ..agenda_tracker.fsm import apply_proposals
from ..agenda_tracker.tracker import propose_transitions
from ..utils.utils import now
from ..extraction.extractor import propose_items, merge_items

logger = logging.getLogger(__name__)


async def track_agenda(realtime, meeting_session):
    # Chụp dữ liệu đầu vào trước khi gọi LLM.
    with meeting_session:
        agenda = deepcopy(meeting_session.get("agenda", []))
        segments = deepcopy(
            meeting_session.get("transcript", [])
        )
        cursor = meeting_session.get("agenda_cursor", 0)

    if not agenda or cursor >= len(segments):
        return

    try:
        proposals = await asyncio.to_thread(
            propose_transitions,
            agenda,
            segments,
            cursor,
        )
    except Exception:
        logger.warning(
            "Agenda tracking failed for %s",
            meeting_session.id,
            exc_info=True,
        )
        # Giữ cursor để lần sau thử lại các đoạn chưa xử lý.
        return

    new_ids = {
        segment["id"]
        for segment in segments[cursor:]
    }

    with meeting_session:
        # Bỏ kết quả cũ nếu một lượt khác đã xử lý đoạn này.
        if meeting_session.get("agenda_cursor", 0) >= len(segments):
            return

        events = apply_proposals(
            meeting_session.get("agenda", []),
            proposals,
            segments,
            now(),
            new_ids,
        )

        meeting_session.emplace(
            "agenda_cursor",
            len(segments),
        )

    for data in events:
        await realtime.publish("agenda.item_state", data)

async def extract_items(realtime, meeting_session):
    with meeting_session:
        segments = deepcopy(
            meeting_session.get("transcript", [])
        )
        cursor = meeting_session.get("extraction_cursor", 0)
        store = deepcopy(
            meeting_session.get("extractions") or []
        )
        agenda = deepcopy(
            meeting_session.get("agenda", [])
        )
        meeting = dict(meeting_session.at("meeting"))

    if cursor >= len(segments):
        return

    meeting_date = (meeting.get("ended_at") or now())[:10]

    try:
        raw_items = await asyncio.to_thread(
            propose_items,
            segments,
            cursor,
            store,
            meeting_date,
            agenda,
            meeting["language"],
        )
    except Exception:
        logger.warning(
            "Extraction failed for %s",
            meeting_session.id,
            exc_info=True,
        )
        return

    with meeting_session:
        # Một lượt xử lý khác có thể đã hoàn thành trước.
        if meeting_session.get("extraction_cursor", 0) >= len(segments):
            return

        agenda_ids = {
            item["id"]
            for item in meeting_session.get("agenda", [])
        }

        # Ghép vào dữ liệu hiện tại, không dùng bản snapshot cũ.
        items, conflicts, events = merge_items(
            meeting_session.get("extractions") or [],
            meeting_session.get("conflicts") or [],
            raw_items,
            segments,
            meeting_session.id,
            agenda_ids,
        )

        meeting_session.emplace("extractions", items)
        meeting_session.emplace("conflicts", conflicts)
        meeting_session.emplace(
            "extraction_cursor",
            len(segments),
        )

    for event_type, data in events:
        await realtime.publish(event_type, data)

async def analyse_transcript(realtime, meeting_session):
    async with realtime.analysis_lock:
        await track_agenda(realtime, meeting_session)
        await extract_items(realtime, meeting_session)


async def analyse_pending(realtime, meeting_session):
    """Catch up when new segments arrive during a slow analysis call."""
    while True:
        revision = len(realtime.transcript_segments)
        await analyse_transcript(realtime, meeting_session)
        realtime.analysis_revision = revision
        if len(realtime.transcript_segments) - revision < 3:
            return
