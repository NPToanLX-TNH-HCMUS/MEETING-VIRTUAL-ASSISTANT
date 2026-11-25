"""
Meeting Virtual Assistant - backend orchestrator.

Builds the FastAPI app, owns the shared AppContext, maps backend exceptions to the
error format of the API contract, and mounts one router per meeting stage:

    api/pre_meeting.py      STAGE 1  create meeting, documents, agenda
    api/during_meeting.py   STAGE 2  recording, transcription
    api/post_meeting.py     STAGE 3  minutes
    api/extractions.py      STAGE 2/3  decisions, action items, deadlines, open issues
    api/conflicts.py        STAGE 2/3  two values for one field; the user picks
    api/settings.py         the API keys, entered in the UI (never returned)
    api/workspaces.py       meeting list, and the workspaces confirmed minutes are filed under

Run from the repo root:  uvicorn src.backend.main:app --reload --port 8000
The built UI (src/frontend/dist) is served from "/" when it exists, so the desktop app and
the UI share one origin with the API (no CORS). MIA_DATA_DIR moves the meeting data folder.
Contract: docs/system_design/api-contract.md
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.staticfiles import StaticFiles

from .api import conflicts, during_meeting, extractions, post_meeting, pre_meeting, settings, workspaces
from .context.app_context import AppContext, MeetingNotFoundError
from .context.session import MissingContextError
from .database.database import engine
from .database.model import Base
from .utils.llm import LLMCallError
from .utils.utils import error, meeting_not_found, now

API_PREFIX = "/api/v1"
FRONTEND_DIST = Path(__file__).resolve().parents[1] / "frontend" / "dist"


@asynccontextmanager
async def lifespan(app: FastAPI):
    bind = app.state.ctx.meeting_repository._session.kw.get("bind", engine)
    Base.metadata.create_all(bind)
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
# Relative "data" depends on the folder the server starts in; a desktop launcher sets MIA_DATA_DIR.
app.state.ctx = AppContext(Path(os.getenv("MIA_DATA_DIR", "data")))
# Keys saved in the UI replace the ones from .env, so they must be in place before the first request.
settings.apply_saved(app.state.ctx.storage.root_dir)

app.include_router(pre_meeting.router, prefix=API_PREFIX)
app.include_router(during_meeting.router, prefix=API_PREFIX)
app.include_router(during_meeting.ws_router)
app.include_router(post_meeting.router, prefix=API_PREFIX)
app.include_router(extractions.router, prefix=API_PREFIX)
app.include_router(conflicts.router, prefix=API_PREFIX)
app.include_router(settings.router, prefix=API_PREFIX)
app.include_router(workspaces.router, prefix=API_PREFIX)


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


# Last, so it only answers what no API route or WebSocket matched.
if FRONTEND_DIST.is_dir():
    app.mount("/", StaticFiles(directory=FRONTEND_DIST, html=True), name="frontend")
