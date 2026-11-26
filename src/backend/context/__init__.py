"""Centralized runtime context for shared resources and per-meeting state.

Role
----
Replaces scattered module-level dicts with a two-level context managed by the
FastAPI orchestrator (`src/backend/main.py`):

- ``AppContext``
  Owns long-lived shared resources (``storage``, ``converter``, ...) and a thread-safe registry of active ``MeetingSession`` objects.
- ``MeetingSession``
  Single source of truth for one meeting's ``id``, ``root`` directory,
  lifecycle ``status``, per-meeting lock, in-memory key-value data, and on-disk artifact paths.

Classes
-------
- ``AppContext`` (``app_context.py``) — Shared resource container & session registry.
  - Attributes: ``storage``, ``meeting_manager``, ``converter``, ``meeting_repository``, ``cloud_storage``.
  - Methods: ``create_session()``, ``session(meeting_id)``, ``sessions()``.
  - FastAPI deps: ``get_ctx(request)``, ``get_session(meeting_id, ctx)``.
- ``MeetingSession`` (``session.py``) — Per-meeting state, file paths & lock.
  - Attributes: ``id``, ``root``, ``status``, ``lock``.
  - Methods: ``at(key)``, ``get(key, default)``, ``emplace(key, value)``,
    ``has(key)``, ``pop(key, default)``, ``path(artifact)``, ``with session:``.
- ``MeetingNotFoundError`` (``app_context.py``) — Unknown ``meeting_id`` (-> HTTP 404).
- ``MissingContextError`` (``session.py``) — Missing key in ``session.at()`` (-> HTTP 409).

General Usage
-------------
1. Inject via FastAPI dependencies in route handlers::

       @app.post("/api/v1/meetings")
       def create(ctx: Annotated[AppContext, Depends(get_ctx)]):
           session = ctx.create_session()
           ...

       @app.get("/api/v1/meetings/{meeting_id}")
       def read(session: Annotated[MeetingSession, Depends(get_session)]):
           with session:
               return session.at("meeting")

2. Read/write per-meeting data and files::

       with session:
           session.emplace("transcript", segments)      # store / overwrite
           data = session.at("transcript")              # strict read (raises MissingContextError)
           opt = session.get("agenda", [])              # safe read with default
           audio = session.path("during_meeting/audio/record.wav")  # auto-creates parent dirs

3. Concurrency & error handling:
   - Always use ``with session:`` when reading/mutating shared session state,
     but release the lock before slow external calls (LLM, STT).
   - ``ctx.session(id)`` raises ``MeetingNotFoundError`` (-> HTTP 404).
   - ``session.at(key)`` raises ``MissingContextError`` (-> HTTP 409).
"""
