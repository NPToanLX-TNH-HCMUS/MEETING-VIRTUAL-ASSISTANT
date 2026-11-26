"""
Conflicts: one task got two different values for the same field (e.g. two deadlines).

    GET  /api/v1/meetings/{id}/conflicts                     every conflict, open or resolved
    POST /api/v1/meetings/{id}/conflicts/{cid}/resolve       the user picks one of the values

Conflicts are found while extracting (extraction/extractor.py: merge_items). The backend
never picks a value itself. Contract: docs/system_design/api-contract.md §5.7 and §6.13
"""

from fastapi import APIRouter

from ..extraction.extractor import resolve_conflict
from ..utils.objects import Conflict, ConflictList, ConflictResolve
from ..utils.utils import error
from .common import SessionDep

router = APIRouter(prefix="/meetings/{meeting_id}/conflicts", tags=["conflicts"])

# Choices are allowed while the meeting runs and until the minutes are confirmed.
RESOLVABLE_STATUSES = {"live", "paused", "processing", "review"}


@router.get("", response_model=ConflictList)
def read_conflicts(session: SessionDep):
    """BACK END RETURNS: {items: Conflict[]}, in the order they were found."""
    with session:
        return {"items": list(session.get("conflicts") or [])}


@router.post("/{conflict_id}/resolve", response_model=Conflict)
async def resolve(conflict_id: str, body: ConflictResolve, session: SessionDep):
    """
    FRONT END SENDS:  {chosen_value} = one of the conflict's option values.
    BACK END RETURNS: the resolved Conflict. The extraction takes the chosen value; read it
                      back with GET .../extractions.
    """
    with session:
        if session.status not in RESOLVABLE_STATUSES:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Conflicts cannot be resolved while the meeting is '{session.status}'.",
            )
        try:
            store, conflicts, conflict, _ = resolve_conflict(
                session.get("extractions") or [],
                session.get("conflicts") or [],
                conflict_id,
                body.chosen_value,
                session.get("transcript", []),
            )
        except LookupError:
            return error(404, "CONFLICT_NOT_FOUND", f"No conflict with id {conflict_id}")
        except RuntimeError:
            return error(409, "CONFLICT_ALREADY_RESOLVED", f"Conflict {conflict_id} is already resolved.")
        except ValueError:
            return error(422, "INVALID_CHOICE", "chosen_value must be one of the conflict's options.")
        session.emplace("extractions", store)
        session.emplace("conflicts", conflicts)
    realtime = session.get("realtime")
    if realtime:
        await realtime.publish("conflict.updated", conflict)
        for item in store:
            if item["id"] == conflict["extraction_id"]:
                await realtime.publish("extraction.updated", item)
    return conflict
