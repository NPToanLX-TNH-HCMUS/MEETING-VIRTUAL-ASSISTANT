# Test Scenarios — Meeting Virtual Assistant

| Field | Value |
|---|---|
| Version | 0.7 (draft) |
| Date | 2026-11-19 |
| Scope | 13 end-to-end scenarios, English meetings |
| Related | `USE_CASES.md` (UC1–UC12), `SPECIAL_CASES.md` (A1–F10, G1–G3), `coverage.csv` (status tracking) |

## How to read this document

A scenario is one meeting that runs through the whole pipeline: create the meeting, upload documents, propose and confirm the agenda, record (live transcript and agenda tracking), transcribe, generate, edit and confirm the minutes. Every scenario is scored on all stages at once.

This document fixes, for each scenario, **what audio to look for**, **how the meeting is set up**, **which special cases it contains** and **which ground truth it needs**. It is written before any audio is collected, so that collection is targeted.

`coverage.csv` has one row per scenario and tracks the status of each part (audio, ground truth, review).

---

## 1. Principles

1. **Coverage.** Every use case UC1–UC12 and every special-case code is in at least one scenario (B5 is checked manually, see `SPECIAL_CASES.md`).
2. **Balance.** Three groups with at least four scenarios each: normal, hard, adversarial / failure. Native and non-native English accents; small and large groups; clean and difficult audio.
3. **Length.** Every clip is at most 290 seconds, because recording is capped at 300 seconds.
4. **Reuse.** Adversarial and failure scenarios reuse audio from other scenarios, because their special cases are in the documents and the harness. 13 scenarios need 8 original recordings and 2 synthetic meetings.
5. **Same content, different audio.** S03–S05 and S06–S08 share their ground truth, so the effect of the microphone and of noise is measured on its own.
6. **Fixed inputs.** The documents of a scenario never depend on the system's output. In the AMI chain, the previous minutes are written from the ground truth of the previous scenario. The chain run that feeds the system's own minutes forward is a separate run (§4.3).
7. **Fixed meeting date.** Every scenario has a `meeting_date`; the harness freezes the clock at that date, so deadlines can be checked.

---

## 2. Matrix

| ID | Group | Audio | Documents before the meeting | Special cases | Use cases |
|---|---|---|---|---|---|
| S01 | Normal | AMI series, meeting a (kick-off) | None; topic and 4 planned points | C10 | UC1, UC5, UC6, UC11, UC12 |
| S02 | Normal | AMI series, meeting b | Minutes of meeting a, 1–2 tasks marked `[x]` | A1, A4, C7 | UC1, UC2, UC6, UC10, UC11, UC12 |
| S03 | Normal | AMI series, meeting c | Minutes of meeting b | A4, C6 | UC2, UC6, UC10, UC11, UC12 |
| S04 | Normal | AMI series, meeting d | Minutes of meeting c | A4, C5 | UC2, UC6, UC8, UC10, UC11, UC12 |
| S05 | Hard | Same clip as S03, table microphone | As S03 | B1 | UC5, UC11, UC12 |
| S06 | Normal | Synthetic team meeting #1 (scripted, TTS voices) | Previous team minutes in the team's format, UTF-8 with BOM | A1, A6, B3, C1, C2, C3, F1, F3, F5, F7 | UC1, UC2, UC5, UC6, UC7, UC11, UC12 |
| S07 | Hard | Synthetic team meeting #2 (scripted, TTS voices) | Task board (`.docx`) | B2, B3, C4, C8, C9, D2, D3, F2, F4, F6 | UC5, UC6, UC8, UC11, UC12 |
| S08 | Hard | S06 audio mixed with café noise | As S06 | B1, B3 | UC5, UC11, UC12 |
| S09 | Hard | MeetingBank, segment with a vote | Real agenda (many items); planned points that repeat one item; 15 minutes | A2, A3, B2 | UC1, UC3, UC6, UC11, UC12 |
| S10 | Adversarial | MeetingBank, segment with a postponed item | Real agenda with an injected instruction | C6, D1 | UC1, UC6, UC11, UC12 |
| S11 | Adversarial | MeetingBank, another segment | One good file, a corrupt PDF, a `.pptx`, an 11 MB file | A7, E1, E2 | UC1, UC4, UC6, UC11, UC12 |
| S12 | Failure | Reuses S07 audio | As S07 | E3, E4, E5, E6, E7, F8, F9, F10 | UC4, UC5, UC6, UC9, UC11, UC12 |
| S13 | Failure | 60 seconds of silence | None; no planned points | A5, B4 | UC1, UC8, UC11, UC12 |

Every scenario also gets the general checks G1–G3.

---

## 3. Scenario cards

### S01 — AMI kick-off

| Field | Content |
|---|---|
| Purpose | A normal first meeting; small talk must not become minutes items |
| Audio | AMI corpus, series ES2002 (four meetings a–d by the same group); meeting **a**. Headset mix. Three parts joined (277 s): introductions; small talk and finance decisions; first assignments |
| Topic / duration | "Remote control project — kick-off" / 30 minutes |
| Planned points | "Team introductions and roles", "Project brief and design process", "Project finance and selling price", "Next steps and task assignments" |
| Documents | None |
| Meeting date | Assumed: Monday 2026-11-02 (`meeting_date_is_assumed: true`) |
| Special cases | C10 |
| Ground truth | Transcript, agenda (with tracking labels), minutes, expected behaviour |

### S02 — AMI meeting b, with previous minutes

| Field | Content |
|---|---|
| Purpose | Carry-over from meeting a; completed work must not come back |
| Audio | ES2002b. Headset mix. Two parts joined (236 s; a 36.6 s recording dropout in the source is skipped): recap of meeting a (C7) and three new requirements; assignments and an agreement |
| Topic / duration | "Remote control — functional design" / 30 minutes |
| Documents | `previous_minutes.md`, written from the AMI summary of meeting a; 1–2 tasks marked `[x]` (A1), the others open (A4) |
| Meeting date | Assumed: Monday 2026-11-09 |
| Special cases | A1, A4, C7 |
| Ground truth | Full set. **Double annotation** (two people label the minutes independently) |

### S03 — AMI meeting c

| Field | Content |
|---|---|
| Purpose | A debate with proposals that are not agreed |
| Audio | ES2002c. Headset mix. One part (271 s): jog dial and slogan decisions, jog dial form and flush buttons left open, assignments, closing |
| Topic / duration | "Remote control — conceptual design" / 30 minutes |
| Documents | `previous_minutes.md`, written from the ground truth of S02 |
| Meeting date | Assumed: Monday 2026-11-16 |
| Special cases | A4, C6 |
| Ground truth | Full set; shared with S05 |

### S04 — AMI meeting d

| Field | Content |
|---|---|
| Purpose | Decisions under budget pressure; a task without a deadline must stay empty |
| Audio | ES2002d. Headset mix. One part (286 s): features cut to meet the budget, a report task with no deadline, dimensions agreed |
| Topic / duration | "Remote control — detailed design" / 30 minutes |
| Documents | `previous_minutes.md`, written from the ground truth of S03 |
| Meeting date | Assumed: Monday 2026-11-23 |
| Special cases | A4, C5 (C4 is planted in S07: this meeting has no unowned task) |
| Ground truth | Full set |

### S05 — S03 with a table microphone

| Field | Content |
|---|---|
| Purpose | Effect of a distant microphone, with the same content as S03 |
| Audio | The same time range as S03, from one channel of the AMI table microphone array (for example Array1-01) |
| Setup | Identical to S03 (topic, duration, documents, meeting date) |
| Special cases | B1 |
| Ground truth | Shared with S03; only `expected_behavior.json` is its own |

### S06 — Team meeting #1 (synthetic)

| Field | Content |
|---|---|
| Purpose | Deadlines, owner changes and live agenda tracking, with non-native accents |
| Audio | Synthetic: the dialogue in `ground_truth/script.json` (4 speakers named after the team) is read by text-to-speech voices with Asian English accents and assembled by `scripts/synth_meeting.py`, with pauses, overlaps and a quiet room tone; about 4 minutes |
| Topic / duration | "Evaluation dataset and demo preparation" / 10 minutes |
| Agenda | "Choose the dataset sources", "Evaluation metrics", "Demo plan", "API budget" (dialogue: `ground_truth/script.json`) |
| Planted lines | C1, C2, C3 (five relative dates), F1, F3, F5, F7: written in `script.json` |
| Documents | Previous team minutes in the team's format, saved as UTF-8 with BOM, containing names with diacritics (A6) and two tasks marked `[x]` (A1) |
| Meeting date | Assumed: Tuesday 2026-11-24 |
| Special cases | A1, A6, B3, C1, C2, C3, F1, F3, F5, F7 |
| Ground truth | Transcript and tracking spans are exact (from the script); minutes written from the script; shared with S08. **Double annotation** of the minutes |

### S07 — Team meeting #2 (synthetic)

| Field | Content |
|---|---|
| Purpose | Hard content: overlap, similar names, several tasks in one sentence, spoken injection, sensitive data |
| Audio | Synthetic, as S06: 4 speakers, three overlaps written in the script; about 4 minutes |
| Topic / duration | "Preparing the demo build" / 10 minutes |
| Agenda | "Bug fixes before the demo", "README and documentation", "Demo plan" (returned to, F6), "API budget" (named and postponed, F2) (dialogue: `ground_truth/script.json`) |
| Planted lines | C4, C8, C9, D2, D3 (fake phone number and password), F2, F4, F6: written in `script.json` |
| Documents | `task_board.docx` |
| Meeting date | Assumed: Tuesday 2026-12-01 |
| Special cases | B2, B3, C4, C8, C9, D2, D3, F2, F4, F6 |
| Ground truth | Full set; S12 is derived from it |

### S08 — S06 with café noise

| Field | Content |
|---|---|
| Purpose | Effect of background noise, with the same content as S06 |
| Audio | S06 audio mixed with café-like babble at 10 dB SNR by `prepare_audio.py` (`mix`). The babble (`noise/cafe_babble.wav`) sums six parts of AMI ES2002 b–d that no clip uses (CC BY 4.0) |
| Setup | Identical to S06 |
| Special cases | B1, B3 |
| Ground truth | Shared with S06; only `expected_behavior.json` is its own |

### S09 — MeetingBank, vote

| Field | Content |
|---|---|
| Purpose | Many topics in a short meeting; a planned point that repeats a document item; many speakers |
| Audio | MeetingBank, Denver City Council 2017-03-06, 2632.4–2918.8 s (286 s): end of the ethics bill, then debate and roll-call vote on Council Bill 17-0156 (passed, two nays) |
| Topic / duration | The council meeting's title / **15 minutes** (A3) |
| Documents | `agenda.md`: the agenda of that meeting rebuilt from MeetingBank metadata (the official PDF could not be downloaded) |
| Planned points | "Four million dollar contingency transfer for economic development" (= Council Bill 17-0156, A2) and "Council retreat schedule" |
| Meeting date | The real date of the council meeting |
| Special cases | A2, A3, B2 |
| Ground truth | Full set. **Double annotation** |

### S10 — MeetingBank, postponed item and injected instruction

| Field | Content |
|---|---|
| Purpose | Postponed items go to unresolved issues; an instruction inside a document is not followed |
| Audio | MeetingBank, Denver City Council 2016-10-31, 1085.0–1339.7 s (255 s): motion to postpone Council Bill 898 to 2016-11-07, roll call, comment on Council Bill 985 |
| Documents | `agenda.md`: the meeting's agenda rebuilt from MeetingBank metadata, with one injected line (D1, see `SPECIAL_CASES.md` §7.3) |
| Meeting date | The real date of the council meeting |
| Special cases | C6, D1 |
| Ground truth | Full set |

### S11 — MeetingBank, bad files and calls in the wrong order

| Field | Content |
|---|---|
| Purpose | Bad uploads are rejected one by one; calls in the wrong order are rejected; the meeting still finishes |
| Audio | MeetingBank, Denver City Council 2016-10-31, 552.0–785.1 s (233 s): the mayor's 2017 budget, a committee to be set up, budget vote on 2016-11-14 |
| Documents | `good.md` (the rebuilt agenda), `broken.pdf`, `slides.pptx`, `large.txt` (11 MB); the last three are generated by `scripts/make_s11_files.py` |
| Harness actions | Before confirming the agenda: start recording (E2). After stop, before transcribe: generate minutes (E1) |
| Special cases | A7, E1, E2 |
| Ground truth | Full set (agenda from `good.md` only) |

### S12 — Failures and user actions (S07 audio)

| Field | Content |
|---|---|
| Purpose | Service failures, pause / resume, edits and double confirmation, in one meeting |
| Audio | S07 audio |
| Setup | As S07 |
| Harness actions | In this order: every LLM down at agenda generation (E4), then retry; remove the "API budget" item and add "Demo checklist" before confirming (E6); start; pause at 60 s, resume at 80.2 s (F8); close the live STT connection at 120 s (F10); pause at 192 s; stop at 202 s while paused (F9); transcribe without the STT key (E5), then retry; generate minutes with the primary LLM down (E4); append a line to the minutes (E7); confirm; confirm again and edit again (E3) |
| Special cases | E3, E4, E5, E6, E7, F8, F9, F10 |
| Ground truth | Derived from S07: the paused window (60–80.2 s) and everything after 192 s are cut from the transcript (171.8 s recorded); minutes items spoken only in the cut windows are removed; tracking labels use the edited agenda |

### S13 — Silence

| Field | Content |
|---|---|
| Purpose | Nothing in, nothing invented |
| Audio | 60 seconds of silence made with ffmpeg |
| Topic / duration | "Weekly sync" / 10 minutes |
| Documents / planned points | None |
| Meeting date | Assumed: Monday 2026-11-16 |
| Special cases | A5, B4 |
| Ground truth | Empty transcript; agenda with at most the topic; empty minutes; no tracking change |

---

## 4. Coverage

### 4.1 Use case → scenarios

| Use case | Scenarios |
|---|---|
| UC1 | S01, S02, S06, S09, S10, S11, S13 |
| UC2 | S02, S03, S04, S06 |
| UC3 | S09 (budget checked on all) |
| UC4 | S11, S12 (every scenario confirms an agenda) |
| UC5 | All; S05, S06, S07, S08 in particular |
| UC6 | All |
| UC7 | S06 |
| UC8 | S04, S07, S13 |
| UC9 | S12 (every scenario confirms the minutes) |
| UC10 | S02 → S03 → S04 (chain run, §4.3) |
| UC11 | All with speech; S12 in particular |
| UC12 | All with an agenda; S06, S07, S12, S13 in particular |

### 4.2 Checks

| Check | Result |
|---|---|
| Every use case in at least one scenario | Yes |
| Every special-case code in at least one scenario | Yes, except B5 (manual) |
| Normal / hard / adversarial-failure | 5 / 4 / 4 |
| Native / non-native accents | S01–S05, S09–S11 / S06, S07, S08, S12 (synthetic Asian English voices) |
| Clean / difficult audio | S01–S04, S06, S09–S11 / S05, S07, S08 |
| Original recordings | 8: AMI a–d, AMI table microphone (S05), MeetingBank × 3; plus 2 synthetic team meetings and generated silence |

### 4.3 Chain run (UC10)

Besides the 13 scenarios, the AMI series is run once as a chain: the minutes the system confirms in S02 are the previous minutes of S03, and those of S03 are the previous minutes of S04. Carry-over recall (AG4) of this run is the result of UC10. The normal runs of S03 and S04 keep their fixed inputs, so a mistake in S02 does not spread to them.

---

## 5. Audio sources

| Source | Used in | Licence | Note |
|---|---|---|---|
| AMI Meeting Corpus | S01–S05 | CC BY 4.0 | Headset mix (S01–S04), table array channel (S05); manual transcripts help but are checked by listening. The recordings are very quiet, so the clips are raised to a common level (`level_dbfs` −26 in `sources.csv`) |
| MeetingBank | S09, S10, S11 | CC BY-NC-SA 4.0 | Non-commercial use only; real agendas and meeting dates available |
| Synthetic meetings | S06, S07 (S08, S12) | Generated for this project | Scripted dialogue read by Microsoft Edge neural voices (Singapore, Philippines, India, Hong Kong English) |
| AMI babble | S08 | CC BY 4.0 | Six unused parts of ES2002 b–d summed into café-like background noise |
| ffmpeg | S13 | — | Generated silence |

Audio files are not committed. `sources.csv` records the origin, the time range and the SHA-256 of every clip, and `prepare_audio.py` rebuilds them.

---

## 6. Tracking with `coverage.csv`

One row per scenario.

| Column | Meaning |
|---|---|
| `scenario_id`, `folder`, `group`, `batch` | Identity; `batch` is the collection order (1 = S01, S02, S13; 2 = S03, S04, S05, S06, S08; 3 = S07, S09–S12) |
| `source`, `audio_segment`, `mic`, `clip_seconds` | What audio to use |
| `docs`, `special_cases`, `use_cases` | As in §2 |
| `shares_gt_with` | Scenario whose ground truth is reused (S05 → S03, S08 → S06, S12 → S07 derived) |
| `double_annotation` | `yes` for S02, S06, S09 |
| `audio`, `gt_transcript`, `gt_agenda`, `gt_minutes`, `expected_behavior` | Status of each part |
| `reviewed_by`, `notes` | Second person who checked the ground truth; free notes |

**Status values:** `todo` → `in_progress` → `done` → `reviewed`; `shared` when the part comes from another scenario. When all 13 rows are `reviewed`, the dataset is locked.

---

## Changelog

| Version | Date | Change |
|---|---|---|
| 0.1 | 2026-11-19 | First draft: principles, matrix, 13 scenario cards, coverage, chain run, audio sources, tracking columns. |
| 0.2 | 2026-11-20 | S01 and S02 cards updated with the selected clips; S01 uses four planned points. |
| 0.3 | 2026-11-20 | S03 and S04 cards updated with the selected clips; C4 moved from S04 to S07. |
| 0.4 | 2026-11-20 | S06 and S07 agendas fixed. |
| 0.5 | 2026-11-20 | S08 noise built from unused AMI parts instead of a downloaded recording. |
| 0.6 | 2026-11-20 | S09–S11 cards updated with the selected Denver clips and the rebuilt agendas. |
| 0.7 | 2026-11-20 | S06 and S07 are synthetic meetings built from scripts with TTS voices, instead of team recordings. S12 pause and stop times moved into silent gaps of the S07 audio (60–80.2 s, 192 s, 202 s). |
