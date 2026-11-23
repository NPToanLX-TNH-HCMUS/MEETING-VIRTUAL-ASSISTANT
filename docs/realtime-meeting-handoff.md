# Realtime meeting handoff

## Run locally

Use Python 3.13+, install the project dependencies, and set ELEVENLABS_API_KEY
and the configured LLM provider credentials in your local .env. Do not commit keys.
Use one backend worker: the microphone belongs to the machine running Python,
not to the browser on another computer.

From the repository root:

    python -m uvicorn src.backend.main:app --port 8000

In another terminal:

    cd src/frontend
    npm.cmd install
    npm.cmd run dev

Create a meeting, confirm its agenda, then open the live meeting page.
There are three recording buttons: Start, Pause/Resume, Stop.
Avoid --reload during recording: editing Python restarts the backend.

## Architecture and ownership

The application uses main's AppContext and context/session.py. Each application
session stores the recording runtime under session.get("realtime").
Do not create an independent meeting registry or import the removed src.api.api.
The recording runtime owns microphone tasks, control acknowledgements, subscriber
queues, event sequence, transcript segments and summary history.
Closing a viewer only unsubscribes its queue; it does not stop the microphone.

- backend/main.py: routers and shutdown cancellation.
- backend/api/during_meeting.py: REST controls, recovery reads, viewer WebSocket.
- backend/during_meeting/meeting_service.py: STT events, summaries, timer, final transcript.
- backend/during_meeting/meeting_session.py: runtime state and event fan-out.
- backend/during_meeting/transcript_store.py: append-only committed segments and cursor lookup.
- backend/api/post_meeting.py: serialized minutes generation, retry, review and confirmation.
- frontend/js/during.js: REST controls, timer, volume, transcript and summary rendering.
- frontend/js/socket.js: reconnect/backoff; no control commands over WebSocket.

## API inputs and outputs

All REST routes below have the prefix /api/v1/meetings/{meeting_id}.

| Method/path | Input | Output |
| --- | --- | --- |
| POST /start | No body; meeting must be ready | status=live, started_at, elapsed_seconds, remaining_seconds |
| POST /pause | No body; live only | Same fields, status=paused |
| POST /resume | No body; paused only | Same fields, status=live |
| POST /stop | No body; live or paused | Same fields, status=processing; final processing continues |
| GET /state | No body | Control fields plus seq, transcript_saved, minutes_ready, error |
| GET /transcript | Optional after=segment_id (exclusive cursor) | {"segments": [TranscriptSegment, ...]} |
| GET /summaries | No body | {"items": [{"revision": 1, "created_at": "...", "text": "..."}]} |
| POST /minutes/generate | No body; completed transcript | Minutes; repeated calls return the stored result |
| GET /minutes | No body | Stored Minutes |
| POST /transcribe | Existing batch WAV; no realtime session | Existing batch transcript response; cannot overwrite realtime output |

Wrong control state: 409 INVALID_MEETING_STATE. Busy microphone: 409
RECORDING_ALREADY_ACTIVE. Startup failure: 503 MIC_UNAVAILABLE.
Unknown transcript cursor: 400 INVALID_TRANSCRIPT_CURSOR.
The former /recording/start, /recording/stop, /recording/level and
/ws/meetings/{id}/transcript-test are no longer registered.

Connect after start to /ws/meetings/{meeting_id}. All application messages go
server -> client and have this envelope:

    {"type":"transcript.segment","meeting_id":"...","seq":42,"at":"...","data":{...}}

seq is per meeting runtime, not per connection. Reconnect or a sequence gap:
subscribe, buffer incoming events, fetch /state first (sequence baseline), fetch
/transcript?after=last_segment_id, agenda and summaries, then process queued
events newer than the baseline. Deduplicate transcript by segment ID, not text.
Identical repeated speech remains valid. An unknown cursor triggers a full refetch.

Implemented core events: meeting.status, transcript.segment, timer.sync,
minutes.ready, error. Compatible extensions: transcript.partial {text},
audio.level {level, dbfs}, summary.updated {revision, created_at, text}.
Partial text is ephemeral and is never input to summarization.
summary.updated is cumulative, not the planned 5-10 minute summary.window.
Agenda/extraction/conflict detection and timer.warning generation are not added here.

TranscriptSegment fields: id, meeting_id, start_seconds, end_seconds, speaker,
text, language, confidence, is_low_confidence. Current STT adapter leaves missing
timestamps, speaker and confidence null; is_low_confidence=false does not prove
confidence is high. Consumers must tolerate unknown metadata.

## Functions for other team members

| File/function | Inputs | Return and side effects |
| --- | --- | --- |
| api/during_meeting.start_meeting | Application MeetingSession | Control dict or error response; starts runtime |
| api/during_meeting.control_meeting | Application session, pause/resume/stop | Control dict or error; waits for microphone acknowledgement |
| api/during_meeting.run_meeting_session | Runtime, application session | None; saves transcript, starts post-processing, records failure |
| api/during_meeting.read_transcript | Application session, optional after ID | segments wrapper or cursor/read error |
| api/during_meeting.read_state | Application session | Current state, sequence, persistence/error flags |
| api/during_meeting.read_summaries | Application session | items wrapper containing complete saved history |
| meeting_service.run_recording | Runtime, application session | Final transcript string; persists transcript.txt |
| meeting_service.run_live_summary | Runtime, application session | None; persists and emits cumulative summaries |
| meeting_service.wait_for_ack | Runtime, acknowledgement Event, timeout | None on acknowledgement; raises on failure/timeout |
| transcript_store.append_segment | Runtime, application session, committed STT event | Segment dict or None for empty input; saves before publish |
| transcript_store.segments_after | Segment list, optional cursor | New list after cursor; ValueError for unknown ID |
| live_summary.summarize_live | Transcript string, language vi/en | Summary string from LLM; empty string for blank input |
| summary_storage.append_summary_history | Directory, revision, text, created_at | Saved history entry; atomically replaces JSON history |
| meeting_session.MeetingSession.publish | Event type, data dict | Envelope dict; increments seq and queues for subscribers |
| post_meeting.generate_minutes | Application session | Minutes dict or error; serializes generation and emits readiness |
| frontend/socket.connectMeetingSocket | Meeting ID, event callbacks | Controller with close(); reconnects on transient disconnect |

For a new summarization module, consume committed TranscriptSegment records.
Track the last segment ID, request /transcript?after=..., then join segment.text.
Use the returned IDs as evidence references. Never parse frontend DOM or use
partial recognition as durable input. The existing live summary reads the whole
committed transcript every 15 seconds when revision changes; do not attach a
second LLM caller to the same pipeline unless intentionally replacing that step.

## Files produced

Under data/<meeting_id>/:

    during_meeting/audio/record.wav
    during_meeting/transcript/segments.jsonl
    during_meeting/transcript/transcript.txt
    post_meeting/summary/summary_history.json
    post_meeting/summary/final_summary.md
    post_meeting/meeting_minutes/minutes_draft.md
    post_meeting/meeting_minutes/minutes_final.md

segments.jsonl is persisted per committed segment. transcript.txt is finalized
after successful stop. summary_history.json appears after the first successful
live summary; each entry summarizes all committed speech up to its revision.
final_summary.md is generated from the full transcript during minutes generation.
minutes_final.md is written only after human confirmation.
Failed LLM processing preserves the transcript and permits /minutes/generate retry.

## Validation

Offline (no real microphone or external LLM calls):

    python -m unittest discover -s tests -p test_meeting_contract.py -v
    python -m unittest discover -s tests -p test_realtime_controls.py -v
    node --test tests/meeting_frontend.test.mjs
    cd src/frontend
    npm.cmd run build

Manual smoke test before merge:
1. Create meeting and confirm agenda; start, speak and observe signal + partial/committed text.
2. Pause: clock freezes, new microphone speech is not captured. Resume and speak.
3. Reload the page while recording: old committed text returns without duplicates.
4. Speak for at least 20-30 seconds and wait for LLM processing; check summary history.
5. Stop while paused and during speech in separate meetings; check the final sentence.
6. Wait for minutes; verify files above. Confirm minutes.
7. Simulate provider failure; inspect terminal traceback and recovery UI.

## Current limits

One local backend worker. AppContext metadata is in memory: viewer reload/reconnect
is supported, server-restart recovery is not. A backend shutdown cancels capture;
incomplete capture keeps committed JSONL and the available WAV, but is not
automatically converted into minutes. Current final STT flush waits two seconds,
so unusually late provider output can be missed. Real microphone/provider smoke
testing remains necessary. Live summaries resend the full transcript and can
reach model context/cost limits in long meetings. No new authentication or
multi-user deployment capability is introduced.
