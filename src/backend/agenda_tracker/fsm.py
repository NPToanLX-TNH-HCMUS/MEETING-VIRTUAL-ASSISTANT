"""Agenda item state machine (contract §3). The backend owns it; the UI only renders it."""

from ..utils import evidence as ev

# not_discussed -> in_progress -> discussed -> concluded, plus discussed -> in_progress (reopened).
ALLOWED = {
    ("not_discussed", "in_progress"),
    ("in_progress", "discussed"),
    ("discussed", "concluded"),
    ("discussed", "in_progress"),
}


def apply_transition(
    item: dict,
    to_state: str,
    segment_ids: list[str],
    quote: str,
    by_id: dict[str, dict],
    at: str,
) -> dict | None:
    """Move `item` to `to_state` and return the agenda.item_state data, or None.

    None means no change: the move is not allowed, or the evidence is weak (missing,
    not verbatim, or from a low-confidence segment). A weak signal never moves an item.
    """
    if (item["state"], to_state) not in ALLOWED:
        return None
    if not ev.verify(segment_ids, quote, by_id) or ev.is_low_confidence(segment_ids, by_id):
        return None

    from_state = item["state"]
    item["state"] = to_state
    if to_state == "in_progress":
        if item["started_at"] is None:
            item["started_at"] = at
        item["ended_at"] = None  # reopened
    else:
        item["ended_at"] = at
    return {
        "agenda_item_id": item["id"],
        "from": from_state,
        "to": to_state,
        "evidence": {"segment_ids": list(segment_ids), "quote": quote},
    }


def apply_proposals(
    agenda: list[dict],
    proposals: list[dict],
    segments: list[dict],
    at: str,
    new_ids: set[str] | None = None,
) -> list[dict]:
    """Apply LLM-proposed transitions in order; return the events that really happened.

    new_ids: the lines this check is about. A proposal must cite at least one of them,
    so an old line (e.g. "let's come back to it later") cannot trigger a change twice.
    """
    by_id = {segment["id"]: segment for segment in segments}
    items = {item["id"]: item for item in agenda}
    events = []
    for proposal in proposals:
        item = items.get(proposal.get("agenda_item_id"))
        if item is None:
            continue
        if new_ids is not None and not new_ids & set(proposal.get("segment_ids") or []):
            continue
        event = apply_transition(
            item,
            proposal.get("to_state"),
            proposal.get("segment_ids") or [],
            proposal.get("quote") or "",
            by_id,
            at,
        )
        if event is not None:
            events.append(event)
    return events
