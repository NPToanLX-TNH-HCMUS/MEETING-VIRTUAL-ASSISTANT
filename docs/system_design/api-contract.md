# API CONTRACT — Meeting Virtual Assistant

> **Version:** 0.1.1 (draft) · **Owner:** Võ Lê Nam Khánh Ann (backend + frontend) · **Last updated:** 2026-10-30
> **Purpose:** The single source of truth for how `frontend/` talks to `src/server/`. If the code and this file disagree, fix one of them in the same pull request.

**Why this file exists.** The frontend and backend only meet at this interface. If both sides follow it, the UI can be built against fake data (mock mode) while the real pipeline (speech-to-text → LLM → state machine) is still being written.

**What changed in 0.1.1:** wording only. No field, endpoint or event was added, removed or renamed. New: §0 (overview), §8.2 (what the mock server does differently from this contract today), and a changelog.

---

## 0. The big picture

The browser (JavaScript) and the server (Python) never call each other's functions. They exchange **text in JSON format**:

- **REST** (request → response): the browser asks, the server answers once. Used for everything that changes data.
- **WebSocket** (server → browser, continuous): the server pushes small updates while a meeting is running (new transcript text, timer, state changes).

A meeting goes through three phases:

| Phase | What happens | Main calls |
|---|---|---|
| **BEFORE** | User enters the topic and uploads files. The backend reads the files (Markdown is split into headings), proposes an **agenda**, and the user confirms it. | `POST /meetings` → `POST .../documents` → `POST .../agenda/generate` → `PUT .../agenda` |
| **DURING** | The microphone records. The backend sends transcript text, decisions, action items, deadlines, agenda progress and the remaining time. The user can ask questions. | `POST .../start`, WebSocket events, `POST .../ask` |
| **AFTER** | The backend merges tasks and drafts the minutes. The user reviews, fixes conflicts and confirms. Open tasks carry over to the next meeting. | `GET/PUT .../minutes`, `POST .../minutes/confirm`, conflicts, tasks |

Two rules that shape every endpoint:

1. **The backend is the source of truth.** The UI shows what the backend sends. It never computes agenda states, task merges or priority scores.
2. **AI output is never official until the user confirms it.** The agenda becomes official with `PUT .../agenda`; the minutes with `POST .../minutes/confirm`.

---

## 1. Conventions

| Topic | Rule |
|---|---|
| Base URL | `http://127.0.0.1:8000/api/v1` (local only; the MVP runs on one laptop) |
| WebSocket URL | `ws://127.0.0.1:8000/ws/meetings/{meeting_id}` |
| Format | JSON in UTF-8 (`Content-Type: application/json`). The only exception is file upload (`multipart/form-data`) |
| Field names | `snake_case`. This matches Python, so no conversion is needed |
| IDs | Strings with a prefix: `mtg_` meeting, `agd_` agenda item, `tsk_` task, `seg_` transcript segment, `ext_` extraction, `doc_` document, `cfl_` conflict |
| Timestamps | ISO 8601 with a UTC offset, e.g. `2026-10-28T16:30:00+07:00` |
| Dates (deadlines) | `YYYY-MM-DD`. The year is inferred from the meeting context. If it cannot be inferred, the value is `null` |
| Durations | Integers or decimals. The field-name suffix gives the unit: `_seconds`, `_minutes` |
| Unknown values | `null`. **Never guess.** Missing fields are also listed in `missing_fields` (see §5.4) |
| Language codes | `"vi"`, `"en"` |
| CORS | Not needed while the server also serves `frontend/` (same origin). In development, Vite forwards `/api` and `/ws` to the backend, so the browser still sees one origin |

### 1.1 Error format

Every non-2xx response has this body:

```json
{
  "error": {
    "code": "MEETING_NOT_FOUND",
    "message": "No meeting with id mtg_999",
    "details": {}
  }
}
```

| HTTP status | When | Example `code` |
|---|---|---|
| 400 | Bad input (a field is missing or invalid) | `VALIDATION_ERROR` |
| 404 | The id does not exist | `MEETING_NOT_FOUND`, `TASK_NOT_FOUND` |
| 409 | The action is not allowed in the current status | `INVALID_MEETING_STATE`, `RECORDING_ALREADY_ACTIVE`, `UNRESOLVED_CONFLICTS` |
| 413 | Uploaded file is too large | `FILE_TOO_LARGE` |
| 415 | File type is not supported | `UNSUPPORTED_FILE_TYPE` |
| 422 | The LLM returned malformed JSON after retries | `LLM_BAD_OUTPUT` |
| 503 | The AI service or the microphone is unavailable | `LLM_UNAVAILABLE`, `MIC_UNAVAILABLE` |

**How the frontend uses it:** show `message` to the user, and decide what to do from `code`. Never compare `message` text.

The browser also creates two codes that the server never sends: `BACKEND_UNREACHABLE` (the server is off or the proxy cannot reach it) and `REQUEST_TIMEOUT`.

### 1.2 Legend used in §6

- **P0** = needed for the MVP demo. **P1** = nice to have.
- **Reuses** = the existing function in `src/` that the endpoint wraps. `NEW` = the module is not written yet.

---

## 2. Meeting status (the state of a whole meeting)

```
draft ──► ready ──► live ◄──► paused
                      │
                      ▼
                  processing ──► review ──► archived
```

| Status | Meaning | Allowed actions |
|---|---|---|
| `draft` | The meeting was created. Inputs are being added. The agenda is not confirmed. | Upload documents, generate the agenda |
| `ready` | The user confirmed the agenda. | Start |
| `live` | Recording and tracking. | Pause, stop, ask |
| `paused` | Recording is paused. Paused time is **not** counted as elapsed time. | Resume, stop |
| `processing` | The meeting ended. The backend is building the minutes. | Wait (the WebSocket sends `minutes.ready`) |
| `review` | The minutes are drafted. The user can edit them. | Edit minutes, resolve conflicts, confirm |
| `archived` | The minutes are confirmed and saved. Open tasks carry over to the next meeting. | Read only |

An action called in the wrong status returns `409 INVALID_MEETING_STATE`. The UI should disable the matching button **and** still handle this error.

---

## 3. Agenda item state

Each agenda item has its own state while the meeting is live. It follows a finite state machine:

```
not_discussed ──► in_progress ──► discussed ──► concluded
                      ▲               │
                      └───────────────┘   (the item is reopened)
```

| Value in JSON | Meaning |
|---|---|
| `not_discussed` | The starting state of every item |
| `in_progress` | It is being discussed now |
| `discussed` | The group moved on, but no decision was made |
| `concluded` | A final decision was stated |

If the backend has too little evidence for a change, it **does not** send a state change at all. The UI must never guess a transition.

---

## 4. Shared value: Evidence

Anything the AI extracts must say where it came from.

```json
{ "segment_ids": ["seg_014"], "quote": "Bình sẽ hoàn thành frontend trước ngày 20/10." }
```

- `segment_ids`: the transcript segments the item came from.
- `quote`: the exact words.
- To show a timestamp, the UI finds each segment in the transcript and reads its `start_seconds`.
- No evidence means no record. If an item arrives without evidence, the UI shows a "no evidence" flag instead of hiding the gap.

---

## 5. Data models

### 5.1 Meeting

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

| Field | Notes |
|---|---|
| `topic`, `language`, `duration_minutes` | Required when creating. `duration_minutes` is 1 to 480 |
| `status` | See §2 |
| `planned_points` | The points the user plans to present. Optional |
| `previous_meeting_id` | The earlier meeting this one continues from, or `null` |
| `started_at`, `ended_at` | `null` until the meeting starts or ends |

### 5.2 Document (a file uploaded before the meeting)

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

Accepted types in the MVP: `.md` and `.txt` (P0); `.pdf` and `.docx` (P1). Maximum size: 10 MB.

### 5.3 AgendaItem

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
| `title` | Short name of the agenda item |
| `description` | Optional extra detail |
| `source` | Where the item came from: `"carry_over"` (an open task from the last meeting), `"planned_point"` (the user typed it), `"document"` (taken from an uploaded file), `"manual"` (the user added it by hand) |
| `importance`, `urgency`, `relevance` | Whole numbers from 0 to 3 (see the Priority Scoring section of the design doc) |
| `priority_score` | `(importance + urgency + relevance) / 3` with equal weights at first. Rounded to 2 decimals for display. **Calculated by the backend; the UI only shows it** |
| `estimated_minutes` | Taken from a default table or a historical average |
| `order` | Position in the agenda, starting at 1 |
| `state` | See §3. Starts as `not_discussed` |
| `started_at`, `ended_at` | When the discussion of this item started and ended, or `null` |
| `needs_confirmation` | `true` until the user accepts the proposed agenda |

### 5.4 Extraction (what the LLM pulled out of the conversation)

All four kinds share one shape, so the frontend can render them with one component.

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
| `type` | `decision`, `action_item`, `deadline` or `unresolved_issue` |
| `assignee`, `deadline` | `null` when nobody said it. The field name is then added to `missing_fields` |
| `agenda_item_id` | Which agenda item this belongs to, or `null` |
| `evidence` | Required (see §4) |
| `missing_fields` | Names of the fields that are `null`, e.g. `["assignee"]` |
| `needs_confirmation` | `true` when something is missing or in conflict. The UI shows a warning marker |
| `task_id` | Set only for `action_item`. Points to the Task in §5.6 |

### 5.5 TranscriptSegment

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

- `start_seconds` and `end_seconds` are measured from the meeting start and **exclude paused time**.
- `speaker` is `null` in the MVP (no speaker detection).
- When `is_low_confidence` is `true`, the UI highlights the segment for review instead of hiding it.

### 5.6 Task (kept across meetings; the Hash Map keyed by id)

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

- `status` is `todo`, `in_progress` or `done`.
- **Task ID rule:** a new fact about an existing task updates the same Task (same `id`). It never creates a second one. The backend does the merge; the UI never removes duplicates itself.
- `history` records every change, so conflicts can be explained to the user.

### 5.7 Conflict

Created when two statements disagree and the system cannot decide (for example, two different deadlines).

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

### 5.8 Minutes

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

- `status` is `draft` or `confirmed`.
- `markdown` is the full text the user edits.
- `sections` is the structured copy, used as input for the next meeting. `decisions`, `action_items` and `unresolved_issues` hold Extraction ids.

---

## 6. REST endpoints

All paths are relative to the base URL in §1.

| # | Method and path | Purpose | Prio | Reuses |
|---|---|---|---|---|
| 1 | `GET /health` | Is the server alive? Is a microphone present? | P0 | `sounddevice.query_devices` |
| 2 | `POST /meetings` | Create a meeting | P0 | NEW |
| 3 | `GET /meetings/{id}` | Read one meeting | P0 | NEW |
| 4 | `POST /meetings/{id}/documents` | Upload a context file | P0 | `Document.load` |
| 5 | `POST /meetings/{id}/agenda/generate` | Build a proposed agenda | P0 | NEW (Max-Heap + Greedy) |
| 6 | `GET /meetings/{id}/agenda` | Read the agenda | P0 | NEW |
| 7 | `PUT /meetings/{id}/agenda` | The user confirms, reorders or edits the agenda | P0 | NEW |
| 8 | `POST /meetings/{id}/start` | Start recording → `live` | P0 | `Recorder.start` |
| 9 | `POST /meetings/{id}/pause` and `/resume` | Pause and resume | P1 | NEW |
| 10 | `POST /meetings/{id}/stop` | Stop → `processing` | P0 | `Recorder.stop` |
| 11 | `GET /meetings/{id}/transcript` | All transcript segments so far | P0 | NEW (Whisper) |
| 12 | `GET /meetings/{id}/extractions` | Decisions, actions, deadlines, issues | P0 | NEW (LLM) |
| 13 | `POST /meetings/{id}/ask` | Ask the assistant a question | P1 | NEW (intent router) |
| 14 | `GET /meetings/{id}/minutes` | Read the draft minutes | P0 | NEW |
| 15 | `PUT /meetings/{id}/minutes` | Save the user's edits | P0 | `Document.save` |
| 16 | `POST /meetings/{id}/minutes/confirm` | Confirm → `archived` | P0 | `Document.save` |
| 17 | `GET /meetings/{id}/conflicts` | List unresolved conflicts | P1 | NEW |
| 18 | `POST /meetings/{id}/conflicts/{cid}/resolve` | Choose a value | P1 | NEW |
| 19 | `GET /tasks?status=todo,in_progress` | Open tasks (carry-over) | P0 | NEW |
| 20 | `PATCH /tasks/{id}` | Change status, assignee or deadline | P1 | NEW |

### 6.1 `GET /health`

Response `200`:

```json
{ "status": "ok", "mic_available": true, "mock_mode": false, "version": "0.1.0" }
```

### 6.2 `POST /meetings`

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

Required: `topic`, `language`, `duration_minutes` (1 to 480). Response `201`: a **Meeting** (§5.1) with `status: "draft"`.

There is no endpoint to edit a meeting after it is created. The UI therefore locks the form once the meeting exists.

### 6.3 `GET /meetings/{id}`

Response `200`: a **Meeting**. Error: `404 MEETING_NOT_FOUND`.

The UI calls this after confirming the agenda, to read the real new `status` instead of assuming `ready`.

### 6.4 `POST /meetings/{id}/documents`

Request: `multipart/form-data` with one field named `file`. Response `201`: a **Document** (§5.2).
Errors: `413 FILE_TOO_LARGE`, `415 UNSUPPORTED_FILE_TYPE`.

The backend reads the file and keeps what it needs for the agenda step. For Markdown, it splits the text into headings. The UI sends the file as it is and does not parse it.

### 6.5 `POST /meetings/{id}/agenda/generate`

No body. The backend builds candidate items (from the uploaded documents, the planned points and open tasks from the last meeting), scores them, estimates the time, then picks the best set that fits the meeting length (Max-Heap + Greedy). It does **not** save a confirmed agenda.

Response `200`:

```json
{
  "items": [ /* AgendaItem[] with needs_confirmation: true */ ],
  "dropped": [ { "title": "Refactor config", "reason": "exceeds_remaining_time", "estimated_minutes": 20 } ],
  "total_estimated_minutes": 45,
  "duration_minutes": 60
}
```

| Field | Meaning |
|---|---|
| `items` | The items the backend chose, ordered by `order` |
| `dropped` | Items it left out, with the `reason`. The UI shows them so the user knows what was skipped (Greedy does not always find the best total score) |
| `total_estimated_minutes` | Sum of `estimated_minutes` over `items` |
| `duration_minutes` | The meeting length |

Only allowed while the meeting is `draft`; otherwise `409 INVALID_MEETING_STATE`. It calls an LLM, so it can take a long time. Other errors: `503 LLM_UNAVAILABLE`, `422 LLM_BAD_OUTPUT`.

### 6.6 `GET /meetings/{id}/agenda`

Response `200`: `{ "items": AgendaItem[] }`. Used after a page refresh or a reconnect.

### 6.7 `PUT /meetings/{id}/agenda`

This call is the user's confirmation. Send the **full list** the user wants, in order:

```json
{ "items": [ { "id": "agd_001", "title": "Decide API contract", "estimated_minutes": 15, "order": 1 } ] }
```

- An item the user added by hand has no `id`.
- Response `200`: `{ "items": AgendaItem[] }`. The meeting becomes `ready`.

### 6.8 `POST /meetings/{id}/start` · `pause` · `resume` · `stop`

No body. Response `200`:

```json
{ "status": "live", "started_at": "2026-10-28T16:45:00+07:00", "elapsed_seconds": 0, "remaining_seconds": 3600 }
```

Errors: `409 INVALID_MEETING_STATE`, `409 RECORDING_ALREADY_ACTIVE`, `503 MIC_UNAVAILABLE`.
`stop` returns `status: "processing"`. Progress then arrives on the WebSocket.

### 6.9 `GET /meetings/{id}/transcript?after={segment_id}`

`after` is optional. It lets the client fetch only the new segments after a reconnect.
Response `200`: `{ "segments": TranscriptSegment[] }`.

### 6.10 `GET /meetings/{id}/extractions?type=action_item`

`type` is optional and may list several values separated by commas. Response `200`: `{ "items": Extraction[] }`.

### 6.11 `POST /meetings/{id}/ask`

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

| `intent` | How it is answered |
|---|---|
| `time_progress` | Read from the stored timer and state machine. No LLM answer |
| `meeting_information` | The backend finds the relevant segments and the LLM summarises them. `sources` lists the `segment_ids` |
| `idea_suggestion` | The LLM suggests something. **`is_ai_suggestion` must be `true`**, so the UI labels it as "not a team decision" |

### 6.12 Minutes: `GET` and `PUT /meetings/{id}/minutes`, `POST .../minutes/confirm`

- `GET` returns **Minutes** (§5.8).
- `PUT` body: `{ "markdown": "..." }`.
- `confirm` is refused with `409 UNRESOLVED_CONFLICTS` while any conflict is still `resolved: false`.

### 6.13 Conflicts

- `GET /meetings/{id}/conflicts` returns `{ "items": Conflict[] }`.
- `POST /meetings/{id}/conflicts/{cid}/resolve` body: `{ "chosen_value": "2026-10-22" }`. Response `200`: the updated **Conflict**.

### 6.14 Tasks

- `GET /tasks` returns `{ "items": Task[] }`. Filters: `status` (several values separated by commas) and `assignee`.
- `PATCH /tasks/{id}` body: any of `status`, `assignee`, `deadline`. Response `200`: the updated **Task**.

---

## 7. WebSocket: live events

**Why a WebSocket and not polling:** during a meeting the server pushes many small updates (text, state changes, the timer). Polling would waste requests and add delay.

- Connect to `ws://127.0.0.1:8000/ws/meetings/{meeting_id}` after calling `start`.
- Messages go **from the server to the client only.** Commands always go through REST. This way one place changes state, and the REST response is always the truth.
- Every message has the same envelope:

```json
{ "type": "agenda.item_state", "meeting_id": "mtg_001", "seq": 42, "at": "2026-10-28T16:50:10+07:00", "data": { } }
```

`seq` goes up by 1 on every message. If the client sees a gap, or reconnects, it re-fetches through REST (`transcript?after=...`, `agenda`, `extractions`) and continues from there.

### 7.1 Events

| `type` | When it is sent | `data` |
|---|---|---|
| `meeting.status` | The status changed | `{ "status": "live" }` |
| `transcript.segment` | A new speech-to-text segment is ready | **TranscriptSegment** |
| `summary.window` | A rolling summary, every 5 to 10 minutes | `{ "from_seconds": 0, "to_seconds": 600, "text": "..." }` |
| `agenda.item_state` | An agenda item changed state | `{ "agenda_item_id": "agd_002", "from": "not_discussed", "to": "in_progress", "evidence": { "segment_ids": ["seg_010"], "quote": "..." } }` |
| `extraction.created` | The LLM found a decision, action item, etc. | **Extraction** |
| `extraction.updated` | An existing one changed | **Extraction** |
| `conflict.created` | The user must choose between two values | **Conflict** |
| `timer.sync` | Every 5 seconds | `{ "elapsed_seconds": 1530, "remaining_seconds": 2070 }` |
| `timer.warning` | Remaining time is at or below the user's threshold | `{ "remaining_seconds": 300 }` |
| `minutes.ready` | Processing finished | `{ "minutes_url": "/api/v1/meetings/mtg_001/minutes" }` |
| `error` | A pipeline error that does not stop the meeting | `{ "code": "LLM_UNAVAILABLE", "message": "...", "recoverable": true }` |

**Timer rule:** the UI counts down locally every second and only **corrects** itself when `timer.sync` arrives. Elapsed time = now − start − paused time. Remaining time = max(0, duration − elapsed).

### 7.2 Keep-alive

The client sends `{"type": "ping"}` every 20 seconds. The server replies `{"type": "pong"}`. This is the only message the client sends.

---

## 8. Mock mode

### 8.1 What mock mode is

Mock mode lets the frontend work without the real pipeline.

- Start the server in mock mode. The plan is `MIA_MOCK=1`. `GET /health` then shows `"mock_mode": true`.
- Every endpoint returns fixed, **contract-valid** sample data. The WebSocket replays a scripted meeting (transcript lines, state changes, one conflict, timer sync) in a loop.
- Sample data will live in `src/server/mock_data/*.json`. Each file must validate against the Pydantic models in `src/server/schemas.py`.

### 8.2 Where the current mock server differs from this contract (2026-10-30)

The file `src/server/main.py` is a small first version. It is **not** a full implementation of this contract. The frontend must not rely on anything in the "Today" column that is not also in the "Contract" column.

| Area | Contract | Today (`src/server/main.py`) |
|---|---|---|
| Endpoints | All of §6 | Only `GET /health`, `POST /meetings`, `GET /meetings/{id}`, `POST .../documents`, `POST .../agenda/generate`, `PUT .../agenda`. No WebSocket |
| `GET /health` | `status`, `mic_available`, `mock_mode`, `version` | `status` and `mock_mode` only |
| `POST /meetings` | Reads and returns every Meeting field | Reads `topic`, `language`, `duration_minutes` and ignores the rest. Returns only `id`, `topic`, `language`, `duration_minutes`, `status`. Does not check the 1 to 480 range |
| `POST .../documents` | Returns a Document. Refuses bad types (`415`) and big files (`413`) | Returns only `id` (always `"doc_001"`), `filename`, `size_bytes`. Does not check type or size. Does not read the file |
| `POST .../agenda/generate` | Builds items from the uploaded files, planned points and open tasks. Checks the meeting is `draft`. Returns `total_estimated_minutes` | Picks from a fixed list of three items and ignores the files. Does not check `draft`. Has no `total_estimated_minutes`. Items have only `id`, `title`, `source`, `priority_score`, `estimated_minutes`, `order`, `needs_confirmation`. `dropped` has no `priority_score` |
| `PUT .../agenda` | Returns full AgendaItems. Checks the status | Returns only `id`, `title`, `estimated_minutes`, `order`. Items without an `id` get `agd_new_{order}`. Does not check the status |
| Validation errors | `400 VALIDATION_ERROR` in the error format of §1.1 | FastAPI's default `422` with `{"detail": [...]}`. The frontend sees this as `HTTP_422` |
| Storage | TBD (§10) | In memory only. Restarting the server forgets every meeting, and the next call returns `404 MEETING_NOT_FOUND` |

When the backend closes one of these gaps, delete its row here.

---

## 9. Changing this contract

1. Edit this file in the **same pull request** as the code. (Docs-only changes may go to `main` directly, per `CODEBASE_CONVENTION.md`.)
2. Raise the version number at the top: **patch** for wording, **minor** for new optional fields or endpoints, **major** for anything that breaks the frontend. Add a line to the changelog.
3. Get the backend owner's agreement.
4. Never rename or remove a field without a major version. Add new fields as optional first.
5. If the frontend needs something that is not here, ask for it here first. Do not invent fields, events or endpoints in the UI code.

## 10. Open questions (decide in the next team meeting)

- [ ] Database for saved data: SQLite (simplest) or JSON files?
- [ ] Should `speaker` stay `null`, or do we try speaker detection later?
- [ ] Do we need login? (MVP: no. It runs on localhost only.)
- [ ] Which language should the minutes use when a meeting mixes `vi` and `en`?
- [ ] How does `agenda/generate` report which document and heading an item came from? (Today `source: "document"` carries no file name.)

## 11. Changelog

| Version | Date | Change |
|---|---|---|
| 0.1.1 | 2026-10-30 | Wording only. Added §0 overview, §4 Evidence, §8.2 mock differences, the changelog, and endpoint sections for tasks, conflicts and `GET /meetings/{id}` |
| 0.1 | 2026-10-28 | First draft |
