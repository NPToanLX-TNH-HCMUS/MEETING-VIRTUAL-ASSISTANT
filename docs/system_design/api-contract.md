# API CONTRACT — Meeting Intelligence Assistant

> **Version:** 0.1 (draft) · **Owner:** Võ Lê Nam Khánh Ann (backend + frontend) · **Last updated:** 2026-10-28
> **Purpose:** The single source of truth for how `frontend/` talks to `src/server/`. If code and this file disagree, fix one of them in the same PR.

**Why this file exists.** The frontend and backend only meet at this interface. If both sides respect it, the UI can be built against fake data (mock mode) while the real pipeline (STT → LLM → FSM) is still being written.

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Base URL | `http://127.0.0.1:8000/api/v1` (local only, MVP runs on one laptop) |
| WebSocket URL | `ws://127.0.0.1:8000/ws/meetings/{meeting_id}` |
| Format | JSON, UTF-8 (`Content-Type: application/json`), except file upload (`multipart/form-data`) |
| Field names | `snake_case` — matches Python, so no conversion layer is needed |
| IDs | Strings with a prefix: `mtg_001`, `agd_001`, `tsk_001`, `seg_001`, `ext_001`, `doc_001` |
| Timestamps | ISO 8601 with offset, e.g. `2026-10-28T16:30:00+07:00` |
| Dates (deadlines) | `YYYY-MM-DD`. Year is inferred from meeting context; if it cannot be inferred the field is `null` |
| Durations | Integers. Suffix says the unit: `_seconds`, `_minutes` |
| Unknown values | `null` — **never guess**. Missing fields are also listed in `missing_fields` (see §4.4) |
| Language codes | `"vi"`, `"en"` |
| CORS | Not needed while the server also serves `frontend/` (same origin). Add only if you split origins |

### 1.1 Error format (all non-2xx responses)

```json
{
  "error": {
    "code": "MEETING_NOT_FOUND",
    "message": "No meeting with id mtg_999",
    "details": {}
  }
}
```

| HTTP | When | Example `code` |
|---|---|---|
| 400 | Bad input (missing/invalid field) | `VALIDATION_ERROR` |
| 404 | Id does not exist | `MEETING_NOT_FOUND`, `TASK_NOT_FOUND` |
| 409 | Action not allowed in current state | `INVALID_MEETING_STATE`, `RECORDING_ALREADY_ACTIVE` |
| 413 | Uploaded file too large | `FILE_TOO_LARGE` |
| 415 | Unsupported file type | `UNSUPPORTED_FILE_TYPE` |
| 422 | LLM returned malformed JSON after retries | `LLM_BAD_OUTPUT` |
| 503 | AI service or microphone unavailable | `LLM_UNAVAILABLE`, `MIC_UNAVAILABLE` |

The frontend shows `message` to the user and branches on `code`, never on `message`.

### 1.2 Status legend (used in §5)

- **P0** = needed for the MVP demo. **P1** = nice to have.
- **Reuses** = which existing function in `src/` the endpoint wraps. `NEW` = module not written yet.

---

## 2. Meeting lifecycle (state of a whole meeting)

```
draft ──► ready ──► live ◄──► paused
                      │
                      ▼
                  processing ──► review ──► archived
```

| Status | Meaning | Allowed actions |
|---|---|---|
| `draft` | Meeting created, inputs being added, agenda not confirmed | upload docs, generate agenda, edit inputs |
| `ready` | Agenda confirmed by the user | start |
| `live` | Recording and tracking | pause, stop, ask |
| `paused` | Recording paused (paused time is **not** counted as elapsed) | resume, stop |
| `processing` | Meeting ended, backend building minutes | wait (WebSocket sends `minutes.ready`) |
| `review` | Minutes drafted, user can edit | edit minutes, resolve conflicts, confirm |
| `archived` | Minutes confirmed and saved; open tasks carry over to the next meeting | read only |

An action called in the wrong status returns `409 INVALID_MEETING_STATE`.

---

## 3. Agenda item state (FSM)

Matches the Finite State Machine in the design doc.

```
Not Discussed ──► In Progress ──► Discussed ──► Concluded
                      ▲               │
                      └───────────────┘   (item reopened)
```

| Value in JSON | Meaning |
|---|---|
| `not_discussed` | Initial state of every item |
| `in_progress` | Currently being discussed |
| `discussed` | Moved on, no decision yet |
| `concluded` | A final decision was stated |

Rule: an event without enough evidence **does not** change state (see `evidence` in §4.3).

---

## 4. Data models

### 4.1 Meeting

```json
{
  "id": "mtg_001",
  "topic": "Sprint review and frontend plan",
  "language": "vi",
  "duration_minutes": 60,
  "status": "draft",
  "planned_points": ["Demo audio recorder", "Decide API contract"],
  "previous_meeting_id": "mtg_000",
  "created_at": "2026-10-28T16:30:00+07:00",
  "started_at": null,
  "ended_at": null
}
```

### 4.2 Document (pre-meeting input)

```json
{
  "id": "doc_001",
  "meeting_id": "mtg_001",
  "filename": "meeting_minute_02.md",
  "mime_type": "text/markdown",
  "size_bytes": 6164,
  "uploaded_at": "2026-10-28T16:31:00+07:00"
}
```

Accepted types for MVP: `.md`, `.txt` (P0); `.pdf`, `.docx` (P1). Max 10 MB.

### 4.3 AgendaItem

```json
{
  "id": "agd_001",
  "meeting_id": "mtg_001",
  "title": "Decide API contract",
  "description": "Agree on endpoints and event names",
  "source": "carry_over",
  "importance": 3,
  "urgency": 2,
  "relevance": 3,
  "priority_score": 2.67,
  "estimated_minutes": 15,
  "order": 1,
  "state": "not_discussed",
  "started_at": null,
  "ended_at": null,
  "needs_confirmation": true
}
```

| Field | Notes |
|---|---|
| `importance` / `urgency` / `relevance` | Integers 0–3, exactly as in the Priority Scoring section of the design doc |
| `priority_score` | `(I + U + R) / 3` with equal weights at first (a = b = c = 1/3). Rounded to 2 decimals for display only |
| `estimated_minutes` | Default table or historical average |
| `source` | `"carry_over"` (open task from last meeting), `"planned_point"`, `"document"`, `"manual"` |
| `needs_confirmation` | `true` until the user accepts the proposed agenda |

### 4.4 Extraction (what the LLM pulled out of the conversation)

One shape for all four kinds, so the frontend can render them with one component.

```json
{
  "id": "ext_001",
  "meeting_id": "mtg_001",
  "type": "action_item",
  "content": "Finish frontend",
  "assignee": "Bình",
  "deadline": "2026-10-20",
  "agenda_item_id": "agd_002",
  "evidence": {
    "segment_ids": ["seg_014"],
    "quote": "Bình sẽ hoàn thành frontend trước ngày 20/10."
  },
  "missing_fields": [],
  "needs_confirmation": false,
  "task_id": "tsk_001"
}
```

| Field | Notes |
|---|---|
| `type` | `decision` · `action_item` · `deadline` · `unresolved_issue` |
| `assignee`, `deadline` | `null` when not stated. The field name is then added to `missing_fields` |
| `evidence` | Required. Traceability is a core pattern in the design: no evidence → no record |
| `needs_confirmation` | `true` when something is missing or conflicting. UI shows a ⚠ marker |
| `task_id` | Set only for `action_item`; points to the Hash-Map record (§4.6) |

### 4.5 TranscriptSegment

```json
{
  "id": "seg_014",
  "meeting_id": "mtg_001",
  "start_seconds": 312.4,
  "end_seconds": 318.9,
  "speaker": null,
  "text": "Bình sẽ hoàn thành frontend trước ngày 20/10.",
  "language": "vi",
  "confidence": 0.91,
  "is_low_confidence": false
}
```

`start_seconds` / `end_seconds` are measured from the meeting start, excluding paused time. `speaker` is `null` in the MVP (no diarization). When `is_low_confidence` is `true` the UI highlights the segment for review instead of hiding it.

### 4.6 Task (persisted across meetings; the Hash Map keyed by id)

```json
{
  "id": "tsk_001",
  "title": "Finish frontend",
  "assignee": "Bình",
  "deadline": "2026-10-22",
  "status": "in_progress",
  "created_in_meeting_id": "mtg_001",
  "history": [
    { "at": "2026-10-28T16:40:00+07:00", "field": "deadline", "old": "2026-10-20", "new": "2026-10-22", "meeting_id": "mtg_001" }
  ]
}
```

`status`: `todo` · `in_progress` · `done`. `history` keeps every change so conflicts can be explained to the user.

### 4.7 Conflict

Created when two statements disagree and the system cannot decide (e.g. two different deadlines).

```json
{
  "id": "cfl_001",
  "meeting_id": "mtg_001",
  "task_id": "tsk_001",
  "field": "deadline",
  "options": [
    { "value": "2026-10-20", "evidence": { "segment_ids": ["seg_014"], "quote": "..." } },
    { "value": "2026-10-22", "evidence": { "segment_ids": ["seg_031"], "quote": "..." } }
  ],
  "resolved": false,
  "chosen_value": null
}
```

### 4.8 Minutes

```json
{
  "meeting_id": "mtg_001",
  "status": "draft",
  "sections": {
    "info": "...markdown...",
    "discussion": "...markdown...",
    "decisions": ["ext_003"],
    "action_items": ["ext_001", "ext_002"],
    "unresolved_issues": ["ext_007"]
  },
  "markdown": "# Meeting Minutes\n...",
  "updated_at": "2026-10-28T17:35:00+07:00"
}
```

`status`: `draft` · `confirmed`. `markdown` is the full rendered text the user edits; `sections` is the structured copy for the next meeting's input.

---

## 5. REST endpoints

All paths below are relative to the base URL.

| # | Method & path | Purpose | Prio | Reuses |
|---|---|---|---|---|
| 1 | `GET /health` | Is the server alive? Is a microphone present? | P0 | `sounddevice.query_devices` |
| 2 | `POST /meetings` | Create a meeting (pre-meeting inputs) | P0 | NEW |
| 3 | `GET /meetings/{id}` | Read one meeting | P0 | NEW |
| 4 | `POST /meetings/{id}/documents` | Upload a context file | P0 | `Document.load` |
| 5 | `POST /meetings/{id}/agenda/generate` | Score + select items → proposed agenda | P0 | NEW (Max-Heap + Greedy) |
| 6 | `GET /meetings/{id}/agenda` | Read agenda | P0 | NEW |
| 7 | `PUT /meetings/{id}/agenda` | User confirms / reorders / edits agenda | P0 | NEW |
| 8 | `POST /meetings/{id}/start` | Start recording → `live` | P0 | `Recorder.start` |
| 9 | `POST /meetings/{id}/pause` · `/resume` | Pause / resume | P1 | NEW |
| 10 | `POST /meetings/{id}/stop` | Stop → `processing` | P0 | `Recorder.stop` |
| 11 | `GET /meetings/{id}/transcript` | All segments so far | P0 | NEW (Whisper) |
| 12 | `GET /meetings/{id}/extractions` | Decisions, actions, deadlines, issues | P0 | NEW (LLM) |
| 13 | `POST /meetings/{id}/ask` | Ask the assistant a question | P1 | NEW (intent router) |
| 14 | `GET /meetings/{id}/minutes` | Read draft minutes | P0 | NEW |
| 15 | `PUT /meetings/{id}/minutes` | Save user edits | P0 | `Document.save` |
| 16 | `POST /meetings/{id}/minutes/confirm` | Confirm → `archived` | P0 | `Document.save` |
| 17 | `GET /meetings/{id}/conflicts` | List unresolved conflicts | P1 | NEW |
| 18 | `POST /meetings/{id}/conflicts/{cid}/resolve` | Pick a value | P1 | NEW |
| 19 | `GET /tasks?status=todo,in_progress` | Open tasks (carry-over) | P0 | NEW |
| 20 | `PATCH /tasks/{id}` | Change status / assignee / deadline | P1 | NEW |

### 5.1 `GET /health`

Response `200`:

```json
{ "status": "ok", "mic_available": true, "mock_mode": false, "version": "0.1.0" }
```

### 5.2 `POST /meetings`

Request:

```json
{
  "topic": "Sprint review and frontend plan",
  "language": "vi",
  "duration_minutes": 60,
  "planned_points": ["Demo audio recorder", "Decide API contract"],
  "previous_meeting_id": null
}
```

Required: `topic`, `language`, `duration_minutes` (1–480). Response `201`: a **Meeting** (§4.1) with `status: "draft"`.

### 5.3 `POST /meetings/{id}/documents`

`multipart/form-data` with one field `file`. Response `201`: a **Document** (§4.2).
Errors: `413 FILE_TOO_LARGE`, `415 UNSUPPORTED_FILE_TYPE`.

### 5.4 `POST /meetings/{id}/agenda/generate`

No body. Runs: extract → priority score → time estimate → Max-Heap + Greedy. Does **not** save a confirmed agenda.
Response `200`:

```json
{
  "items": [ /* AgendaItem[] with needs_confirmation: true */ ],
  "dropped": [ { "title": "Refactor config", "reason": "exceeds_remaining_time", "estimated_minutes": 20 } ],
  "total_estimated_minutes": 45,
  "duration_minutes": 60
}
```

`dropped` is returned so the UI can explain what Greedy skipped (Greedy does not guarantee the best total score).

### 5.5 `PUT /meetings/{id}/agenda`

Request: the full list the user wants, in order.

```json
{ "items": [ { "id": "agd_001", "title": "Decide API contract", "estimated_minutes": 15, "order": 1 } ] }
```

New items (user added) omit `id`. Response `200`: `{ "items": AgendaItem[] }` and the meeting becomes `ready`.

### 5.6 `POST /meetings/{id}/start` · `pause` · `resume` · `stop`

No body. Response `200`:

```json
{ "status": "live", "started_at": "2026-10-28T16:45:00+07:00", "elapsed_seconds": 0, "remaining_seconds": 3600 }
```

Errors: `409 INVALID_MEETING_STATE`, `409 RECORDING_ALREADY_ACTIVE`, `503 MIC_UNAVAILABLE`.
`stop` returns `status: "processing"`; progress arrives on the WebSocket.

### 5.7 `GET /meetings/{id}/transcript?after={segment_id}`

`after` is optional; it lets the client fetch only new segments after a reconnect.
Response `200`: `{ "segments": TranscriptSegment[] }`.

### 5.8 `GET /meetings/{id}/extractions?type=action_item`

`type` optional (comma-separated). Response `200`: `{ "items": Extraction[] }`.

### 5.9 `POST /meetings/{id}/ask`

Request: `{ "question": "How much time is left?" }`
Response `200`:

```json
{
  "intent": "time_progress",
  "answer": "23 minutes left. 2 of 4 agenda items are concluded.",
  "sources": [],
  "is_ai_suggestion": false
}
```

| `intent` | Handled by |
|---|---|
| `time_progress` | Read from stored timer/FSM — no LLM answer |
| `meeting_information` | Retrieve segments → LLM summarises; `sources` lists `segment_ids` |
| `idea_suggestion` | LLM; **`is_ai_suggestion` must be `true`** so the UI labels it as not a team decision |

### 5.10 `GET` / `PUT /meetings/{id}/minutes` · `POST .../minutes/confirm`

`GET` returns **Minutes** (§4.8). `PUT` body: `{ "markdown": "..." }`. `confirm` is refused with `409 UNRESOLVED_CONFLICTS` if any conflict is still `resolved: false`.

### 5.11 Conflicts

`POST /meetings/{id}/conflicts/{cid}/resolve` body: `{ "chosen_value": "2026-10-22" }`. Response `200`: the updated **Conflict**.

### 5.12 `GET /tasks`

Response `200`: `{ "items": Task[] }`. Filters: `status` (comma-separated), `assignee`.

---

## 6. WebSocket — live events

**Why a WebSocket and not polling:** during a meeting the server must push many small updates (text, state changes, timer). Polling would waste requests and add delay.

- Connect to `ws://127.0.0.1:8000/ws/meetings/{meeting_id}` after calling `start`.
- **Server → client only.** Commands always go through REST, so there is one place that changes state and the REST response is always the truth.
- Every message has the same envelope:

```json
{ "type": "agenda.item_state", "meeting_id": "mtg_001", "seq": 42, "at": "2026-10-28T16:50:10+07:00", "data": { } }
```

`seq` increases by 1 per message. If the client sees a gap, or reconnects, it re-fetches via REST (`transcript?after=...`, `agenda`, `extractions`) and continues.

### 6.1 Events

| `type` | When | `data` |
|---|---|---|
| `meeting.status` | Status changes | `{ "status": "live" }` |
| `transcript.segment` | A new STT segment is ready | **TranscriptSegment** |
| `summary.window` | Every 5–10 min rolling summary | `{ "from_seconds": 0, "to_seconds": 600, "text": "..." }` |
| `agenda.item_state` | FSM transition | `{ "agenda_item_id": "agd_002", "from": "not_discussed", "to": "in_progress", "evidence": { "segment_ids": ["seg_010"], "quote": "..." } }` |
| `extraction.created` | LLM found a decision/action/etc. | **Extraction** |
| `extraction.updated` | An existing one changed | **Extraction** |
| `conflict.created` | System needs the user to choose | **Conflict** |
| `timer.sync` | Every 5 s | `{ "elapsed_seconds": 1530, "remaining_seconds": 2070 }` |
| `timer.warning` | Remaining time ≤ user threshold | `{ "remaining_seconds": 300 }` |
| `minutes.ready` | Processing finished | `{ "minutes_url": "/api/v1/meetings/mtg_001/minutes" }` |
| `error` | Non-fatal pipeline error | `{ "code": "LLM_UNAVAILABLE", "message": "...", "recoverable": true }` |

**Timer rule:** the frontend counts down locally every second and only **corrects** itself when `timer.sync` arrives. This keeps the display smooth and the server load small.

### 6.2 Client keep-alive

Client sends `{"type": "ping"}` every 20 s; server replies `{"type": "pong"}`. This is the only client → server message.

---

## 7. Mock mode (so the frontend never waits for the backend)

- Start the server with `MIA_MOCK=1` (or `GET /health` shows `"mock_mode": true`).
- In mock mode every endpoint returns fixed, **contract-valid** sample data, and the WebSocket replays a scripted meeting (transcript lines, state changes, one conflict, timer sync) on a loop.
- Sample data lives in `src/server/mock_data/*.json`. Each file must validate against the Pydantic models in `src/server/schemas.py`.

---

## 8. Changing this contract

1. Edit this file in the **same PR** as the code (docs-only changes may go to `main` directly, per `CODEBASE_CONVENTION.md`).
2. Bump the version at the top: **patch** for wording, **minor** for new optional fields/endpoints, **major** for anything that breaks the frontend.
3. Never rename or remove a field without a major bump. Add new fields as optional first.

## 9. Open questions (decide in the next team meeting)

- [ ] Database for persistence: SQLite (simplest) or JSON files?
- [ ] Should `speaker` stay `null`, or do we try diarization in a later phase?
- [ ] Do we need authentication? (MVP: no — localhost only.)
- [ ] Which language does the generated minutes use when the meeting mixes `vi` and `en`?
