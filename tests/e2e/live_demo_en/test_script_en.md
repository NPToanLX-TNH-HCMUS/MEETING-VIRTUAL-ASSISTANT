# English test script: Agenda FSM and live extractions

One run checks both features on the During page:

- **Agenda FSM:** the state badge of each agenda item.
- **Extractions:** the tags under transcript lines and the "Captured so far" panel.

| What is tested | Block |
|---|---|
| `not_discussed → in_progress` | 1, 2, 8 |
| `in_progress → discussed` (moved on, no decision) | 2 |
| `in_progress → discussed → concluded` (decision while discussing) | 3, 6 |
| `discussed → in_progress` (reopened) | 5 |
| Decision captured | 3, 6 |
| Action item, complete (owner and deadline) | 4 |
| Action item, deadline missing → "Needs confirmation" | 4 |
| Action item, owner missing → "Needs confirmation" | 8 |
| Deadline moved → `extraction.updated`, "Needs confirmation" | 5 |
| Unresolved issue | 2, 8 |
| Off-topic talk changes nothing | 7 |

A replay of this script through the real LLM (text only, no microphone) on 2026-11-21 matched every expected agenda change, block by block. The end state was 8 captured items.

## 1. Setup

1. Start the backend from the repo root:

   ```bash
   .venv/bin/uvicorn src.backend.main:app --reload --port 8000
   ```

2. Start the front end in a second terminal:

   ```bash
   cd src/frontend && npm run dev
   ```

3. Open http://localhost:5173 and fill in the form:

   | Field | Value |
   |---|---|
   | Topic | `StudyBuddy app launch planning` |
   | Language | **English** (the speech-to-text language comes from this) |
   | Duration (minutes) | `30` |
   | Points you plan to present | `Choose the launch date`, `Approve the marketing budget`, `Assign the beta testing tasks` (one chip each) |
   | Context files | `tests/e2e/live_demo_en/launch_planning_notes.md` |

4. Press **Generate agenda**. The sample agenda below is what to expect (the LLM may reword titles or change the minutes):

   | # | Title | Source |
   |---|---|---|
   | 1 | Choose the launch date | planned point |
   | 2 | Approve the marketing budget | planned point |
   | 3 | Assign the beta testing tasks | planned point |

   If an item is missing or there are extra items, press **Regenerate**, or fix the list by hand. Then press **Confirm agenda**.
5. On the During page, open DevTools → Network → WS. Frames with a `seq` field are the new events: `agenda.item_state`, `extraction.created` and `extraction.updated`.

## 2. Reading rules

- Press **Start recording** and wait until the status line says recognition has started.
- **Pause about 2 seconds after every sentence**, so each sentence becomes its own transcript line. The backend checks after every 3 lines; two sentences merged into one line shift the blocks.
- **Wait about 10 seconds at the end of each block**. The backend makes two LLM calls in a row (agenda, then extractions).
- The whole session is limited to **5 minutes**, pauses included. This script takes about 4 minutes.
- Say numbers and dates as written ("December twelfth"). The year comes from today's date.

## 3. Script

### Block 1: start the launch date

1. Okay, let's start with the first item, choosing the launch date for the app.
2. We have two options, December fifth or December twelfth.
3. December fifth is earlier, but the payment screen is not finished yet.

**Expected:** Launch date `not_discussed → in_progress`. Usually no extraction yet.

### Block 2: move on without a decision

4. We can't decide the launch date today, so let's come back to it later.
5. Now let's move on to the marketing budget.
6. The marketing team is asking for either three thousand or five thousand dollars.

**Expected:**
- Launch date `in_progress → discussed`.
- Marketing budget `not_discussed → in_progress`.
- Unresolved issue: the launch date is not decided. A second one about the $3,000 / $5,000 request may also appear.

### Block 3: decide the budget

7. Three thousand dollars is not enough for the social media ads.
8. So we agree, the marketing budget is five thousand dollars.
9. Great, five thousand dollars is our final decision.

**Expected:**
- Marketing budget `in_progress → discussed → concluded` (two events).
- Decision: the marketing budget is $5,000.

### Block 4: action items

10. Anna will prepare the ad campaign plan by November twenty-eighth.
11. Someone also needs to update the app store screenshots.
12. Tom, can you take the screenshots? There is no fixed date for that one.

**Expected:**
- No agenda change.
- Action item "Prepare the ad campaign plan": Anna, due 28/11, complete.
- Action item "Update the app store screenshots": Tom, `deadline missing`, card marked **Needs confirmation**.

### Block 5: reopen the launch date and move a deadline

13. Let's go back to the launch date for a moment.
14. If the payment screen is done next week, December twelfth works for everyone.
15. Also, Anna's campaign plan is now due on December first instead.

**Expected:**
- Launch date `discussed → in_progress` (reopened).
- `extraction.updated` for Anna's item: due 01/12, the card is marked **Needs confirmation** (a stated value changed), and the evidence lists both lines (10 and 15).

### Block 6: decide the launch date

16. So we decide the launch date is December twelfth.
17. Everyone agrees, December twelfth is final.
18. That closes the launch date topic.

**Expected:**
- Launch date `in_progress → discussed → concluded`.
- Decision: launch on December 12. The LLM sometimes captures it one block early (line 14), and then not again here. Both are fine; two cards for it are not.

### Block 7: off-topic talk (nothing should change)

19. By the way, the coffee machine on the third floor is broken again.
20. Did anyone watch the football game last night?
21. It was a really close match.

**Expected:** no `agenda.item_state` and no new extraction.

### Block 8: start beta testing, leave it open

22. Last item, assigning the beta testing tasks.
23. We need someone to recruit twenty beta testers before December eighth.
24. We still don't know which testing tool to use, so let's decide that next meeting.

**Expected:**
- Beta testing `not_discussed → in_progress`.
- Action item "Recruit 20 beta testers": due 08/12, `assignee missing`, **Needs confirmation**.
- Unresolved issue: which testing tool to use.

**Wait 10 seconds, then press Stop recording.** After the transcript is saved, the page asks the backend once more for extractions, so lines the live checks did not reach are covered too.

## 4. Expected end state

| Agenda item | State |
|---|---|
| Choose the launch date | Concluded |
| Approve the marketing budget | Concluded |
| Assign the beta testing tasks | In progress |

- The agenda header reads `2/3 concluded`.
- "Captured so far" holds about 8 items:
  - 2 decisions;
  - 3 action items, all marked **Needs confirmation**: screenshots (deadline missing), beta testers (assignee missing), and Anna's (its deadline moved);
  - 2–3 unresolved issues.
- Every card shows `Evidence: m:ss`. A card that says **No evidence in the transcript** means the LLM could not point to the words. That is allowed, but note it.

## 5. Record the results

| Block | Agenda events (from → to) | Extraction events | As expected? | Notes |
|---|---|---|---|---|
| 1 | | | | |
| 2 | | | | |
| 3 | | | | |
| 4 | | | | |
| 5 | | | | |
| 6 | | | | |
| 7 | | | | |
| 8 | | | | |

## 6. When something does not match

| Symptom | Likely cause |
|---|---|
| No events at all | The agenda was not confirmed, or the LLM failed: look for `Agenda tracking failed` or `Live extraction failed` in the uvicorn log (missing key, HTTP 429). |
| Events one block late | Sentences were merged, or the previous LLM call was still running, so this check was skipped. The next check covers the missed lines. |
| An agenda event is missing | The backend refused it: the step is not allowed, or the quote is not word for word in the transcript. |
| An extraction appears twice | Not expected (the backend drops repeats). Note the two cards' evidence times. |
| Wrong word in the transcript | Speech-to-text error. The backend only trusts quotes found in the transcript, so a misheard word can block evidence. |

Check the stored state outside the UI:

```bash
curl -s http://127.0.0.1:8000/api/v1/meetings/<meeting_id>/agenda | python3 -m json.tool
```

```bash
curl -s http://127.0.0.1:8000/api/v1/meetings/<meeting_id>/extractions | python3 -m json.tool
```
