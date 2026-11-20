# Annotation Guide — Meeting Virtual Assistant

| Field | Value |
|---|---|
| Version | 0.6 (draft) |
| Date | 2026-11-20 |
| Scope | Ground truth of the end-to-end scenarios (English meetings) |
| Related | `USE_CASES.md`, `SPECIAL_CASES.md`, `SCENARIOS.md`, `sources.csv`, `coverage.csv` |

## How to read this document

The ground truth (GT) is the correct answer for each scenario. Every metric compares the system's output with it, so it must be made the same way by everyone. This guide gives the rules; when a case is not covered, decide, write the decision in §9 and apply it to every scenario.

**Golden rule:** the GT is made from the audio and the input documents, **never from the system's output**. Do not run the system on a clip before its GT is reviewed.

Files per scenario (`scenarios/<folder>/`):

| File | Content | Made from |
|---|---|---|
| `scenario.json` | Meeting setup, source, aliases, key entities, user actions, faults | `SCENARIOS.md`, `sources.csv` |
| `inputs/docs/*` | Documents uploaded before the meeting | Planted or real documents |
| `ground_truth/transcript.txt` | What was said | Audio (AMI: manual transcript, checked by listening) |
| `ground_truth/agenda.json` | Correct agenda and live-tracking labels | Documents and planned points (agenda); audio (tracking) |
| `ground_truth/minutes.json` | Correct minutes | Audio |
| `ground_truth/expected_behavior.json` | Pass / fail checks | `SPECIAL_CASES.md` |

---

## 1. Transcript (`transcript.txt`)

One utterance per line: `[mm:ss.s] ROLE: text`. Times are seconds from the start of the clip.

1. Write every word that is spoken, in English spelling, including hesitations ("um", "uh"), repetitions and false starts.
2. A cut-off word is written as heard ("th", "w").
3. Acronyms spoken letter by letter are written in capitals without spaces: "TV", "VCR", "DVD".
4. Numbers are written in words as spoken: "twenty five Euro", "twelve fifty".
5. Vietnamese names are written without diacritics: "Binh", "Khoi".
6. Unintelligible speech: `[inaudible]`. Do not guess.
7. Speaker label: the role in AMI (PM, ID, UI, ME); the first name in team meetings; `SPEAKER` when unknown. Labels are not scored.
8. Silence-only clips have an empty file.

**AMI clips.** `scripts/ami_transcript.py` drafts the file from the AMI manual transcript (made by human transcribers) and shifts the times to the clip. The draft is then checked by listening; every correction is written in the scenario's `notes` in `coverage.csv`.

**MeetingBank clips.** `scripts/mb_transcript.py` drafts the file from the MeetingBank transcript, which was made by a speech-to-text service (Speechmatics), not by people. It has more errors, mostly in names (`scenario.json` → `source.known_draft_errors` lists the ones already spotted), so the whole clip must be corrected by listening. Speaker labels stay `SPEAKER_n`.

**Scoring normalisation** (done by the evaluator, not in the file): lower case; punctuation removed; contractions expanded; "um", "uh", "er", "hmm", "mm-hmm" removed; `[inaudible]` removed; numbers in digits and in words treated as equal; British and American spellings ("colour" / "color") and a few words written as one or two words ("kick-off" / "kickoff") treated as equal.

---

## 2. Agenda (`agenda.json`)

The agenda is produced **before** the meeting, so its GT is written from the **documents and planned points only**, never from the audio.

| Field | Rule |
|---|---|
| `items[].id` | `I1`, `I2`, … |
| `items[].title` | Short English title |
| `items[].required` | `true`: a planned point, an open task or an open issue from the documents; `false`: acceptable but not needed (it is neither rewarded nor penalised) |
| `items[].from` | `planned_point`, `document`, `topic` |
| `carry_over` | Ids of items carried over from the previous minutes (open tasks and open issues) |
| `must_not_include` | Completed tasks, decisions already made, injected instructions; each with `case` and `keywords` |
| `max_total_minutes` | The meeting duration |

Rules:

1. One planned point = one required item. A document item that repeats a planned point is the same item (A2).
2. An open task or open issue in the previous minutes is a required carry-over item (A4).
3. A task marked `[x]` / "Done" and a decision already made go to `must_not_include` (A1).
4. Keywords in `must_not_include` must be specific enough not to match a legitimate item.

---

## 3. Live agenda tracking (`agenda.json` → `items[].tracking`)

Labelled by listening to the audio, for **every** item in `items` (required and optional).

| Field | Rule |
|---|---|
| `final_state` | `not_discussed`, `discussed` or `concluded` at the end of the clip |
| `spans` | `[start, end]` in clip seconds for each period the group talks about the item |
| `off_agenda` (top level) | Windows of talk not about any item (small talk, exercises, technical set-up) |

1. A span starts at the first sentence clearly about the item (a passing mention or "let's leave X for next week" is not a start — F2), and ends when the group moves to something else.
2. `concluded` only when a final decision or a final assignment is stated for the item; otherwise `discussed`.
3. Only one item is discussed at a time. If an open issue is settled inside another item, the other item is split into two spans around it.
4. Talk that belongs to no item and is not small talk (opening words, "who wants to go first?") is left unlabelled: it is neither a span nor `off_agenda`.
5. `concluded` is final. Later talk about a concluded item is still a span, but its state does not change.

---

## 4. Minutes (`minutes.json`)

Made by listening to the clip only. What is not in the clip is not in the minutes, even if the full meeting contains it.

### 4.1 Sections

| Section | Rule |
|---|---|
| `summary_points` | 3–6 key points a reader must find in the summary; used for summary coverage |
| `decisions` | Something the group settled in the meeting |
| `action_items` | A task a person, a role or the whole team committed to or was assigned |
| `unresolved_issues` | A question raised and not settled, or explicitly postponed |
| `must_not_appear` | Content that must not become a minutes item (small talk, completed work, spoken injection, sensitive data), with `case` and `keywords` |

### 4.2 Decisions versus unresolved issues

- Agreed ("OK, let's do that", "yes, definitely") → decision.
- Proposed but not agreed, postponed, or "we'll discuss it" → unresolved issue (C6).
- A requirement handed down from outside the group (the project brief, the company, a client) and only announced in the meeting → optional decision: accepted if the system lists it, not counted as missing if it does not.

### 4.3 Action items

| Field | Rule |
|---|---|
| `task` | Short imperative sentence |
| `assignee` | Canonical name from `scenario.json` → `aliases` (AMI: the role, e.g. "Industrial Designer"); `"Team"` for the whole team; `null` when nobody takes it (C4) |
| `due` | `YYYY-MM-DD` or `null` (§4.4) |
| `spoken_due` | The words that gave the date, or `null` |
| `quote` | The exact words that create the task, as in `transcript.txt` |
| `time` | Clip second where the task is created |
| `cases` | Special-case codes this item tests |

- The last agreed owner and the last agreed date count (C1, C2).
- A task given to a group named in the meeting ("the designers") is one item; the group is defined in `aliases` (for example `"Designers": ["designers", "ID and UI"]`).
- Several tasks in one sentence are several items (C8).
- Completed work mentioned again is not an action item (C7).

### 4.4 Due dates

Relative dates are resolved from the scenario's `meeting_date`, with the conversion table of UC7. Additional rules:

| Phrase | `due` |
|---|---|
| "today", "this afternoon", "the next meeting is in thirty minutes", "in the thirty minutes after lunch" | the meeting date |
| "before the next meeting" with no date or day stated | `null` |
| "ASAP", "soon", no deadline | `null` |

### 4.5 Optional items

An item with `"optional": true` is acceptable but not required: if the system produces it, it is matched and not counted as a false positive; if it does not, it is not counted as missing. Use it for statements whose status is genuinely uncertain (a tentative answer, a goal stated in passing).

---

## 5. Key entities (`scenario.json` → `key_entities`)

Names of people, numbers, dates and project terms whose correct transcription matters (TR3).

```json
{"text": "twelve fifty Euro", "alts": ["12.50 euro", "12.50 euros", "12,50"]}
```

`alts` lists equivalent written forms. 8–15 entities per scenario.

---

## 6. Review and agreement

1. **Second listener.** Each scenario is checked by a person other than its annotator, who listens to the whole clip against all GT files. Their name goes in `reviewed_by` in `coverage.csv`.
2. **Double annotation** (S02, S06, S09). Two people write `minutes.json` independently; the F1 between their action items, computed with the same matcher as the metrics, must be ≥ 0.8. Differences are discussed and settled; if a rule was unclear, a decision is added to §9.
3. **Matcher decisions.** When the automatic matcher pairs a system item and a GT item wrongly, the correct decision is written in `adjudication.json` and reused in every later run.
4. **Statuses** in `coverage.csv`: `todo` → `in_progress` → `done` (annotator finished) → `reviewed` (second listener agreed).

---

## 7. Fixed meeting date

Every scenario has a `meeting_date` in `scenario.json`. For AMI and MeetingBank clips without a usable date, a date is assumed and `meeting_date_is_assumed` is `true`. The harness freezes the system clock at that date.

---

## 8. Checklist before marking a scenario `done`

- [ ] `transcript.txt` checked by listening from start to end
- [ ] Every agenda item has a `tracking` block; spans do not overlap
- [ ] Every action item has `assignee`, `due`, `spoken_due`, `quote`, `time`
- [ ] Every special case of the scenario has at least one check in `expected_behavior.json`
- [ ] All JSON files parse
- [ ] `python tests/e2e_eval/harness/validate.py <scenario>` reports no error
- [ ] `coverage.csv` updated

---

## 9. Decisions log

| # | Date | Decision |
|---|---|---|
| 1 | 2026-11-20 | A clip may join several parts of the same meeting when no single part contains every planted case; cuts are placed in silences and listed in `sources.csv`. |
| 2 | 2026-11-20 | Work due before a next meeting stated to be the same day ("in thirty minutes", "after lunch") is due on the meeting date. |
| 3 | 2026-11-20 | AMI assignees are written as roles; the first names said in the meeting are aliases. |
| 4 | 2026-11-20 | A team exercise during the meeting (AMI "draw your favourite animal") is small talk for the minutes and off-agenda for tracking. |
| 5 | 2026-11-20 | `concluded` is final for tracking (no change back to `in_progress`), as the allowed changes of UC12 say. |
| 6 | 2026-11-20 | In the AMI chain, the previous minutes of S03 and S04 are written from the ground truth of S02 and S03, in the system's minutes format with a Status column. |
| 7 | 2026-11-20 | Carry-over tasks whose presentation is not in the clip stay `not_discussed`, even when related words are said. |
| 8 | 2026-11-20 | When an official agenda cannot be downloaded, it is rebuilt from MeetingBank metadata and the usual order of the meeting; the rebuild is recorded in `scenario.json` → `source.constructed_docs`. |
| 9 | 2026-11-20 | A postponed item is `discussed` for tracking and an unresolved issue in the minutes, never a decision (C6). |
| 10 | 2026-11-20 | Procedural agenda items (roll call, minutes, announcements, proclamations, consent block) are optional in the agenda ground truth. |
| 11 | 2026-11-20 | Synthetic meetings (S06, S07): the transcript and tracking spans are generated from `script.json` by `scripts/synth_meeting.py gt`, so they are exact; minutes items point to their script line (`line`) and get their `time` from the assembly. The second listener still listens once to check that every line was read correctly. |
| 12 | 2026-11-20 | Words in the AMI annotation that cannot be heard in the clip (for example a speaker whose headset was not yet plugged in) are removed from the transcript: the ground truth follows the audio file, not the source annotation. |
| 13 | 2026-11-20 | AMI transcripts have one sentence per line (scripts/ami_transcript.py splits at . ? !), so that the order of the lines follows the audio when people talk over each other. Speech that is there but cannot be made out in the clip (quiet overlap) is written `[inaudible]`, which is not scored; speech that cannot be heard at all is removed (decision 12). |
| 14 | 2026-11-20 | Requirements handed down from outside the group and only announced (S01: price, market and cost from the brief; S02: teletext, TV only, corporate colour and slogan from the company) are optional decisions. Only what the group settles in the meeting is a required decision. |
| 15 | 2026-11-20 | The people of the synthetic team meetings (S06–S08, S12) have English first names (Ann, Ben, Henry, Kevin, Tim, Tom); their audio was read again by the same voices. |

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-11-20 | First draft: transcript, agenda, tracking, minutes, key entities, review, decisions log. |
| 0.2 | 2026-11-20 | Rules for concluded items and group assignees; decisions 5–7. |
| 0.3 | 2026-11-20 | MeetingBank transcript drafts; decisions 8–10. |
| 0.4 | 2026-11-20 | Decision 11: synthetic meetings. |
| 0.5 | 2026-11-20 | Decisions 12–14: inaudible words removed, AMI sentence lines, announced requirements optional. |
| 0.6 | 2026-11-20 | Decision 15: English names in the team meetings. |
