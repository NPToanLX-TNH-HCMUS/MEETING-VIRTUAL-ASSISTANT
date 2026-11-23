## Project Board Tracking
<!-- Required: replace this comment with Closes #<actual issue number> before opening the PR. The issue number has not been provided. -->

## Summary of Changes
Integrates realtime recording into main's modular FastAPI backend. Users can start,
pause, resume and stop a meeting through REST while one outbound-only WebSocket
delivers microphone volume, partial/committed transcript, timer and cumulative summaries.
Reloading the page no longer stops recording, and missed segments are recovered by ID.

After stop, the server finalizes the transcript and generates minutes and a final
summary. Summary history is retained; failed minutes generation can be retried.

## Technical Approach
- Reuses AppContext/MeetingSession and stores recording runtime under the realtime key.
- Replaces the transcript-test channel with /ws/meetings/{id}; all events share
  type, meeting_id, seq, at and data. Controls use REST and reject invalid states with 409.
- Persists committed segments before publishing. Reconnect buffers events, fetches
  REST state/transcript/history and deduplicates by segment ID.
- Owns recording tasks independently of viewer connections, locks the local microphone,
  disconnects slow viewers and cancels runtime tasks on backend shutdown.
- Serializes minutes generation to avoid duplicate LLM calls. Keeps main's UI layout
  and the existing batch STT function, guarding it against overwriting realtime output.
- Documents API and function input/output contracts in docs/realtime-meeting-handoff.md.
- Uses summary.updated for cumulative summaries; summary.window and agenda/extraction/
  conflict detection remain future producers. Unknown STT metadata is nullable.

## Verification
- [x] Automated offline backend and frontend tests added/updated.
- [x] Frontend production build succeeds.
- [ ] Tested with a real local microphone and live API credentials after integration.

Offline commands:
python -m unittest discover -s tests -p test_meeting_contract.py -v
python -m unittest discover -s tests -p test_realtime_controls.py -v
node --test tests/meeting_frontend.test.mjs
npm.cmd run build (from src/frontend)

Manual reproduction: create meeting -> confirm agenda -> start -> speak -> pause ->
resume -> reload page -> stop -> verify summary history, final transcript and minutes.
Also stop while paused and verify that the last spoken sentence is retained.

Limits: one backend worker and server-local microphone; no session recovery after
server restart. The final STT flush still uses a bounded two-second wait.

## Pre-Merge Checklist
- [ ] My code follows the project's style guidelines (review pending).
- [ ] I have verified that this change does not break existing functionality (manual smoke test pending).
- [x] Any required documentation updates have been made.
- [ ] Project Board issue reference has been filled in.
