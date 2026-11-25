# Full test script (English): StudyBuddy launch meeting

One run of about 4 minutes of speech, plus the Before and After pages, tests every feature built so far.

| Feature | Where it is checked |
|---|---|
| Agenda proposal from planned points and a notes file | §2 Before |
| Live transcript: one line per sentence, `m:ss` times, auto-scroll | Every block |
| Pause / Resume: times exclude the pause, `LIVE · PAUSED` badge | After block 4 |
| Agenda FSM `not_discussed → in_progress` | Blocks 1, 2, 8 |
| Agenda FSM `in_progress → discussed` (moved on, no decision) | Block 2 |
| Agenda FSM `→ discussed → concluded` (decision while discussing) | Blocks 3, 6 |
| Agenda FSM `discussed → in_progress` (reopened) | Block 5 |
| Old lines never re-trigger the FSM ("come back to it later") | Blocks 3–4 |
| Extractions: decision, action item, unresolved issue, with evidence time | Blocks 2–8 |
| Tags under the transcript line an item cites | Every block with an extraction |
| Missing owner or deadline → listed in **Needs your choice** | Blocks 4, 8 |
| A missing deadline said later is filled in | Block 7 |
| Deadline conflict (two dates for one task) | Block 5 |
| Assignee conflict, resolved during the meeting | Block 7 |
| Small talk is ignored | Block 7 (line 19) |
| Page refresh brings the transcript, times and panels back | §5 |
| Minutes are drafted; confirm is blocked while a conflict is open (`409 UNRESOLVED_CONFLICTS`) | §6 After |
| Resolve the last conflict on the After page, then confirm → `archived` | §6 After |

A text-only replay of the 24 lines through the real LLM (no microphone, 2026-11-22) gave exactly the agenda changes, extractions and conflicts listed below.

---

## 1. Before you start

- `.env` has `GROQ_API_KEY`, `OPENROUTER_API_KEY` (fallback) and `ELEVENLABS_API_KEY`.
- **The ElevenLabs account has quota left.** One run uses about 5 minutes of realtime speech-to-text. If it has none, recording stops after about a second with a red banner "Recording stopped: ElevenLabs: quota_exceeded…".
- Start the backend from the repo root:

  ```bash
  .venv/bin/uvicorn src.backend.main:app --reload --port 8000
  ```

- Start the front end in a second terminal:

  ```bash
  cd src/frontend && npm run dev
  ```

- Keep the uvicorn terminal visible. `Agenda tracking failed` or `Live extraction failed` there means an LLM call failed (missing key, HTTP 429); the transcript keeps going.

## 2. BEFORE: create the meeting and confirm the agenda

1. Open http://localhost:5173 and fill in the form:

   | Field | Value |
   |---|---|
   | Topic | `StudyBuddy app launch planning` |
   | Language | **English** (the speech-to-text language comes from this) |
   | Duration (minutes) | `30` |
   | Points you plan to present | `Choose the launch date`, `Approve the marketing budget`, `Assign the beta testing tasks` (one chip each) |
   | Context files | `tests/e2e/live_demo_en/launch_planning_notes.md` |

2. Press **Generate agenda**. Expected sample agenda (the LLM may reword titles or change the minutes):

   | # | Title | Source | About |
   |---|---|---|---|
   | 1 | Choose the launch date | planned point | 10 min |
   | 2 | Approve the marketing budget | planned point | 10 min |
   | 3 | Assign the beta testing tasks | planned point | 10 min |

   Check:
   - [ ] 3 items, each with a source label.
   - [ ] Total planned time is at most 30 minutes; anything that did not fit is listed as dropped.
   - [ ] Nothing is official yet (the agenda is marked as proposed).

   If an item is missing or extra, press **Regenerate**, or fix the list by hand.
3. Press **Confirm agenda**, then open the During page.
4. Open DevTools → Network → WS. Frames with a `seq` field are the live events: `agenda.item_state`, `extraction.created`, `extraction.updated`, `conflict.created`.

## 3. Reading rules

- Press **Start recording** and wait until the status line says recognition has started and the badge shows `LIVE · RECORDING`.
- **Pause about 2 seconds after every sentence**, so each sentence becomes its own transcript line. The backend checks after every 3 lines; two merged sentences shift the blocks.
- **Wait about 10 seconds at the end of each block** for the two LLM calls (agenda, then extractions).
- The session is limited to **5 minutes, pauses included**. This script takes about 4. Do not stop to read the notes in the middle; note results after the run.
- Say numbers and dates as written ("December twelfth"). The year comes from today's date.
- **Do not refresh or close the During page while recording**: that ends the session.

## 4. DURING: the script

### Block 1: start the launch date

1. Okay, let's start with the first item, choosing the launch date for the app.
2. We have two options, December fifth or December twelfth.
3. December fifth is earlier, but the payment screen is not finished yet.

**Expected**
- Agenda: Launch date `not_discussed → in_progress` (card gets a highlighted border).
- Transcript: three lines with times like `0:04`, `0:10`, `0:17`, newest at the bottom.

### Block 2: move on without a decision

4. We can't decide the launch date today, so let's come back to it later.
5. Now let's move on to the marketing budget.
6. The marketing team is asking for either three thousand or five thousand dollars.

**Expected**
- Agenda: Launch date `in_progress → discussed`; Marketing budget `not_discussed → in_progress`.
- Captured: unresolved issue "launch date undecided" (line 4). A second one about the $3,000 / $5,000 request may appear.

### Block 3: decide the budget

7. Three thousand dollars is not enough for the social media ads.
8. So we agree, the marketing budget is five thousand dollars.
9. Great, five thousand dollars is our final decision.

**Expected**
- Agenda: Marketing budget `in_progress → discussed → concluded` (two events). Launch date stays `discussed`: line 4 ("come back to it later") must not reopen it.
- Captured: decision "marketing budget is $5,000", tag under line 8.

### Block 4: action items

10. Anna will prepare the ad campaign plan by November twenty-eighth.
11. Someone also needs to update the app store screenshots.
12. Tom, can you take the screenshots? There is no fixed date for that one.

**Expected**
- Agenda: no change.
- Captured: "Prepare the ad campaign plan", Anna, due 28/11, white card (complete).
- Captured: "Update the app store screenshots", Tom, `deadline missing`, yellow card.
- **Needs your choice**: the screenshots card with the chip `Deadline: Not stated`.

### Pause test (between blocks 4 and 5)

1. Note the time of line 12 in the transcript.
2. Press **Pause**. Check the badge shows `LIVE · PAUSED` and the button reads **Resume**.
3. Wait **10 seconds** in silence, then press **Resume**.

**Expected:** in block 5, line 13's time is only a few seconds after line 12's. The 10-second pause is **not** added.

### Block 5: reopen the launch date and move a deadline

13. Let's go back to the launch date for a moment.
14. If the payment screen is done next week, December twelfth works for everyone.
15. Also, Anna's campaign plan is now due on December first instead.

**Expected**
- Agenda: Launch date `discussed → in_progress` (reopened).
- Captured: a decision about December 12 may appear here already (the LLM reads line 14 as one).
- **Conflict**: `conflict.created` for Anna's item, field deadline, options **28/11** (line 10) and **01/12** (line 15).
  - **Needs your choice** shows a red-bordered Conflict card with two buttons, nothing pre-selected.
  - Anna's item keeps 28/11 and its tag says `deadline conflict`.
- **Do not choose this one.** It is left for the After page.

### Block 6: decide the launch date

16. So we decide the launch date is December twelfth.
17. Everyone agrees, December twelfth is final.
18. That closes the launch date topic.

**Expected**
- Agenda: Launch date `in_progress → discussed → concluded`.
- Captured: decision "launch date December 12", unless it was already captured in block 5.

### Block 7: small talk, a deadline said, and an owner changed

19. By the way, the coffee machine on the third floor is broken again.
20. Tom, please finish the screenshots by December third.
21. Actually, Linh will do the screenshots instead of Tom.

**Expected**
- Agenda: no change. No item from line 19.
- Screenshots item: the deadline is filled in, **due 03/12**, and the `Deadline: Not stated` chip is gone.
- **Conflict**: assignee, options **Tom** (line 12) and **Linh** (line 21). The screenshots card in **Needs your choice** is now a Conflict card.
- **Your action now:** press **Linh**.
  - The conflict card disappears.
  - In Captured, the screenshots item shows Linh, due 03/12, and turns white (nothing left to review).

### Block 8: start beta testing, leave it open

22. Last item, assigning the beta testing tasks.
23. We need someone to recruit twenty beta testers before December eighth.
24. We still don't know which testing tool to use.

**Expected**
- Agenda: Beta testing `not_discussed → in_progress`.
- Captured: action item "Recruit twenty beta testers", due 08/12, `assignee missing`.
- Captured: unresolved issue "testing tool not decided".
- **Needs your choice**: the beta-testers card with the chip `Assignee: Not stated`.

**Wait 10 seconds, then press Stop recording.** The status line says the transcript was saved, and the page asks the backend once more for extractions, covering any line the live checks missed.

## 5. End of the meeting: check, then refresh

| Agenda item | State |
|---|---|
| Choose the launch date | Concluded |
| Approve the marketing budget | Concluded |
| Assign the beta testing tasks | In progress |

- [ ] The agenda header reads `2/3 concluded`.
- [ ] **Needs your choice**: the Anna deadline conflict (28/11 or 01/12) and the beta-testers card. It may also hold a card marked "No evidence in the transcript"; note it if so.
- [ ] **Captured so far**: about 8 items, as follows.

  | Type | Item |
  |---|---|
  | Decision | Marketing budget $5,000 |
  | Decision | Launch date December 12 (possibly two cards: line 14 and lines 16–17) |
  | Action item | Prepare the ad campaign plan (Anna, deadline conflict) |
  | Action item | Update the app store screenshots (Linh, 03/12) |
  | Action item | Recruit twenty beta testers (08/12, assignee missing) |
  | Unresolved issue | Launch date undecided; budget amount undecided; testing tool not decided |

- [ ] Every card shows `Evidence: m:ss`, or the red "No evidence in the transcript".

**Refresh test:** reload the During page.
- [ ] The transcript comes back with its times; the "No transcript yet" text does not show.
- [ ] Needs your choice and Captured come back the same as before the reload.

## 6. AFTER: minutes, conflict, confirm

1. Press **Go to review →**. The page drafts the minutes (an LLM call, up to about a minute).
2. **Before you confirm** lists the Anna deadline conflict first, then the beta-testers card.
   - [ ] **Confirm and save minutes** is disabled; its tooltip says to choose a value first.
3. Check that the backend refuses too (replace `<meeting_id>` with the id in the page header):

   ```bash
   curl -s -X POST http://127.0.0.1:8000/api/v1/meetings/<meeting_id>/minutes/confirm | python3 -m json.tool
   ```

   - [ ] `"code": "UNRESOLVED_CONFLICTS"`
4. Press **01/12** on the conflict card.
   - [ ] The card disappears, the header count changes, and **Confirm** becomes active.
5. Check the stored choice:

   ```bash
   curl -s http://127.0.0.1:8000/api/v1/meetings/<meeting_id>/conflicts | python3 -m json.tool
   ```

   - [ ] Both conflicts are `"resolved": true`, with chosen values `"Linh"` and `"2026-12-01"`.
6. Press **Confirm and save minutes**.
   - [ ] The badge shows Confirmed. The meeting is `archived` and the minutes are read-only.
   - [ ] The beta-testers card does not block the confirm. Only conflicts do; missing fields are a reminder.

## 7. Record the results

| Step | Agenda events (from → to) | Extraction / conflict events | As expected? | Notes |
|---|---|---|---|---|
| Before (agenda) | — | — | | |
| Block 1 | | | | |
| Block 2 | | | | |
| Block 3 | | | | |
| Block 4 | | | | |
| Pause test | — | — | | Time of line 12: ____ · line 13: ____ |
| Block 5 | | | | |
| Block 6 | | | | |
| Block 7 (and choosing Linh) | | | | |
| Block 8 | | | | |
| End state and refresh | | | | |
| After page | | | | |

## 8. When something does not match

| Symptom | Likely cause |
|---|---|
| Recording stops after about a second | ElevenLabs quota exhausted or key wrong. Read the red banner. |
| No agenda or extraction events at all | The agenda was not confirmed, or every LLM call failed. Look for `Agenda tracking failed` / `Live extraction failed` in the uvicorn terminal (missing key, HTTP 429). |
| Events one block late | Two sentences merged into one line, or the previous LLM call was still running and this check was skipped. The next check covers the missed lines. |
| An agenda change is missing | The backend refused it: the step is not allowed, the quote is not word for word in the transcript, or the evidence is an old line. |
| Block 5 shows a second card for Anna's plan instead of a conflict | The LLM reported the moved deadline as a new item instead of an update. An LLM miss; note it. |
| Block 7 shows no Tom/Linh conflict | Same kind of LLM miss, or line 21 merged with line 20. Note which. |
| Line 13's time includes the 10-second pause | A bug: note both times. |
| A word in the transcript is wrong | Speech-to-text error. Evidence only uses words found in the transcript, so a misheard word can make a card show "No evidence". |

Inspect the stored state without the UI:

```bash
curl -s http://127.0.0.1:8000/api/v1/meetings/<meeting_id>/agenda | python3 -m json.tool
```

```bash
curl -s http://127.0.0.1:8000/api/v1/meetings/<meeting_id>/extractions | python3 -m json.tool
```

```bash
curl -s http://127.0.0.1:8000/api/v1/meetings/<meeting_id>/transcript | python3 -m json.tool
```
