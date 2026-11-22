"""
Meeting Virtual Assistant - backend orchestrator.

Builds the FastAPI app, owns the shared AppContext, maps backend exceptions to the
error format of the API contract, and mounts one router per meeting stage:

    api/pre_meeting.py      STAGE 1  create meeting, documents, agenda
    api/during_meeting.py   STAGE 2  recording, transcription
    api/post_meeting.py     STAGE 3  minutes

Run from the repo root:  uvicorn src.backend.main:app --reload --port 8000
Contract: docs/system_design/api-contract.md
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI, Request

from .api import during_meeting, post_meeting, pre_meeting
from .context.app_context import AppContext, MeetingNotFoundError
from .context.session import MissingContextError
from .database.database import engine
from .database.model import Base
from .utils.llm import LLMCallError
from .utils.utils import error, meeting_not_found, now

API_PREFIX = "/api/v1"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    yield
    # Stop any microphone stream still running on shutdown / reload so the audio is not lost.
    for session in app.state.ctx.sessions():
        with session:
            recorder = session.pop("recorder")
            if recorder is not None and recorder.is_recording:
                recorder.stop(str(session.path(during_meeting.AUDIO_FILE)))
                ended_at = now()
                session.status = "processing"
                session.at("meeting")["ended_at"] = ended_at
                app.state.ctx.meeting_repository.update_status(
                    session.id, "processing", ended_at=ended_at
                )


app = FastAPI(lifespan=lifespan)
app.state.ctx = AppContext()

app.include_router(pre_meeting.router, prefix=API_PREFIX)
app.include_router(during_meeting.router, prefix=API_PREFIX)
app.include_router(during_meeting.ws_router)
app.include_router(post_meeting.router, prefix=API_PREFIX)


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
