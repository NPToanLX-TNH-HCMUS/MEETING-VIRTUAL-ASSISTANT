"""
Meeting Virtual Assistant - backend orchestrator.

Builds the FastAPI app, owns the shared AppContext, maps backend exceptions to the
error format of the API contract, and mounts one router per meeting stage:

    api/pre_meeting.py      STAGE 1  create meeting, documents, agenda
    api/during_meeting.py   STAGE 2  recording, transcription
    api/post_meeting.py     STAGE 3  minutes
    api/extractions.py      STAGE 2/3  decisions, action items, deadlines, open issues
    api/conflicts.py        STAGE 2/3  two values for one field; the user picks

Run from the repo root:  uvicorn src.backend.main:app --reload --port 8000
Contract: docs/system_design/api-contract.md
"""

from contextlib import asynccontextmanager
import asyncio

from fastapi import FastAPI, Request

from .api import conflicts, during_meeting, extractions, post_meeting, pre_meeting
from .context.app_context import AppContext, MeetingNotFoundError
from .context.session import MissingContextError
from .database.database import engine
from .database.model import Base
from .utils.llm import LLMCallError
from .utils.utils import error, meeting_not_found, now

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    bind = app.state.ctx.meeting_repository._session.kw.get("bind", engine)
    Base.metadata.create_all(bind)
    yield
    tasks = []
    for session in app.state.ctx.sessions():
        realtime = session.get("realtime")
        if realtime:
            realtime.stop_event.set()
            for task in (realtime.stream_task, realtime.processing_task):
                if task is not None and not task.done():
                    task.cancel()
                    tasks.append(task)
    await asyncio.gather(*tasks, return_exceptions=True)


app = FastAPI(lifespan=lifespan)
app.state.ctx = AppContext()

app.include_router(pre_meeting.router, prefix=API_PREFIX)
app.include_router(during_meeting.router, prefix=API_PREFIX)
app.include_router(during_meeting.ws_router)
app.include_router(post_meeting.router, prefix=API_PREFIX)
app.include_router(extractions.router, prefix=API_PREFIX)
app.include_router(conflicts.router, prefix=API_PREFIX)


@app.exception_handler(MeetingNotFoundError)
def handle_meeting_not_found(_request: Request, exc: MeetingNotFoundError):
    return meeting_not_found(exc.args[0] if exc.args else "")


@app.exception_handler(MissingContextError)
def handle_missing_context(_request: Request, exc: MissingContextError):
    return error(409, "INVALID_MEETING_STATE", exc.args[0] if exc.args else str(exc))


@app.exception_handler(LLMCallError)
def handle_llm_error(_request: Request, exc: LLMCallError):
    return error(exc.status, exc.code, str(exc))


@app.get(f"{API_PREFIX}/health")
def health():
    return {"status": "ok", "mock_mode": False}
