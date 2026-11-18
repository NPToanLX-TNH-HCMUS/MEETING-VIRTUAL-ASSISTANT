from datetime import datetime

from fastapi.responses import JSONResponse


def now() -> str:
    # ISO 8601 with the local UTC offset, e.g. 2026-10-28T16:30:00+07:00 (contract section 1).
    return datetime.now().astimezone().isoformat(timespec="seconds")


def error(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": {}}},
    )


def meeting_not_found(meeting_id: str) -> JSONResponse:
    return error(404, "MEETING_NOT_FOUND", f"No meeting with id {meeting_id}")
