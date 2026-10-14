# PROJECT MEETING MINUTES — SESSION #01

> **Project:** Meeting Intelligence Assistant  
> **Domain:** D  
> **Course Code:** CSC10014 — Computational Thinking  

---

## GENERAL INFORMATION

| | |
|---|---|
| **Date** | Tuesday, October 13th, 2026 |
| **Time** | 3:00 PM – 6:00 PM |
| **Format** | In-person at the Library |
| **Objective** | Brainstorm core features & define the product's UX/UI direction |

### Attendees

| Full Name | Student ID | Role | Present |
|-----------|------------|------|---------|
| Nguyễn Thành Tài | 25127134 | Member | ✅ |
| Nguyễn Cao An Bình | 25127183 | Member | ✅ |
| Đoàn Khánh Hưng | 25127195 | Member | ✅ |
| Bùi Đăng Khôi | 25127203 | Member | ✅ |
| Võ Lê Nam Khánh Ann | 25127274 | Member | ✅ |
| Ngô Phước Toàn | 25127522 | Member | ✅ |

---

## 1. TOPIC CONFIRMATION

### 1.1. Decision

> **The team officially selected Domain D — Meeting Intelligence Assistant.**

### 1.2. Reasons for Choosing Track D

- Track D has clear real-world applicability with a well-defined target audience: **Leaders and members of working/study groups**.
- Other tracks were either too technically heavy or too vague, lacking a distinct focus.

---

## 2. PROBLEM DEFINITION & SCOPE

### 2.1. Core Problems

The team defines this product as a **Leader support tool** — not a replacement. The following real-world pain points were identified during discussion:

| # | Problem | Consequence |
|---|---------|-------------|
| 1 | Leader must juggle too many tabs and remember too much information | Easy to forget things, wastes preparation time |
| 2 | No designated secretary → no accurate record of decisions, assignments, or deadlines | Information is lost after the meeting ends |
| 3 | In online meetings: hard to track who is speaking, hard to extract individual contributions | Meeting minutes become incomplete or inaccurate |
| 4 | Meetings tend to run longer than necessary | Wastes the entire team's time |
| 5 | Members don't check messages → don't know what the next meeting is about | No preparation, less effective meetings |

### 2.2. Design Philosophy

- **Centralize information in one place** — eliminate the need to switch between tabs.
- **Suggest only, never decide** — the Leader retains full decision-making authority.
- **No background running** — the app activates only when the user opens it (on-demand).

### 2.3. Three Phases of Support

```
┌─────────────────┐     ┌─────────────────┐     ┌─────────────────┐
│   PRE-MEETING   │────▶│   IN-MEETING    │────▶│  POST-MEETING   │
│  (narrow scope) │     │  (core focus)   │     │  (final output) │
└─────────────────┘     └─────────────────┘     └─────────────────┘
```

> 💡 **Team insight:** The *In-Meeting* phase delivers the most value and presents the greatest technical challenge → allocate the most resources here.

---

## 3. FEATURES DISCUSSED & AGREED UPON

### 3.1. Pre-Meeting *(narrow scope)*

| ID | Feature | Description |
|----|---------|-------------|
| P1 | **Preparation Summary** | Automatically reminds the Leader what to report, who is unavailable, and where the meeting takes place |
| P2 | **Deadline Status Check** | Retrieves and reports which deadlines are completed and which tasks are still pending from the previous session |
| P3 | **Meeting Schedule Suggestion** | Suggests optimal meeting times based on members' availability (calendar integration) |
| P4 | **Previous Session Recap** | Summarizes what was decided last time and what is still in progress |

---

### 3.2. In-Meeting *(core focus)*

| ID | Feature | Description |
|----|---------|-------------|
| I1 | **Automatic Attendance Tracking** | Records the list of participants at the start of each session |
| I2 | **Live Transcript** | Displays real-time text transcription; identifies who is speaking during online meetings |
| I3 | **Keyword Trigger** | Detects specific trigger phrases (e.g., *"I have a suggestion"*, *"I'm assigning this task to"*) → immediately logs the statement with the speaker's name |
| I4 | **Micro-summarization** | After each discussion segment, AI automatically generates a brief summary table |
| I5 | **Recurring Issue Detection** | If the same issue is raised multiple times, surfaces a prominent alert on screen |
| I6 | **Agenda Cross-check** | Leader can query the AI: *"Is there anything we haven't covered yet?"* → AI cross-references with the original agenda |
| I7 | **Teleprompter / Cue Card** | Suggests the next talking points for the Leader *(optional — similar to subtitles)* |

---

### 3.3. Post-Meeting *(final output)*

| ID | Feature | Description |
|----|---------|-------------|
| A1 | **Full Meeting Summary** | When recording stops → generates a complete, structured meeting minutes document |
| A2 | **Automatic Deadline Table** | Extracts the list of tasks, owners, and deadlines in a clear table |
| A3 | **Assignee Suggestions** | Based on each member's prior work → suggests the most suitable person for new tasks |
| A4 | **Export Meeting Minutes** | Exports a professional Markdown / DOCX file |
| A5 | **Context for Next Session** | Saves session data → used as input to power suggestions in the next meeting |

> **Assignee Suggestion Example:**  
> *"Khôi handled the database connection last week → suggesting Khôi take on the API integration this week."*

> **Golden Rule:** The app **only suggests assignments** — the Leader is always the final decision-maker.


## 4. OPEN ISSUES — TO BE DECIDED

The following technical and architectural questions remain unresolved and will be voted on at the next meeting:

| # | Issue | Reason Not Yet Resolved |
|---|-------|-------------------------|
| OI-1 | **Platform:** Web App or Desktop App? | Pros and cons of each option not yet fully evaluated |
| OI-2 | **Recording Mechanism:** Who records? How do 6 members use the app simultaneously? | Related to data synchronization architecture |
| OI-3 | **Speaker Diarization:** When multiple people speak at once, how does the AI accurately identify and attribute speakers? | Requires further research into suitable APIs/libraries |

---

## 6. ACTION ITEMS

| ID | Task | Owner | Deadline |
|:---|:-----|:------|:---------|
| 01 | Research Speaker Diarization feasibility (APIs / libraries) | TBD | Next meeting |
| 02 | Evaluate Web App vs Desktop App — document pros & cons | TBD | Next meeting |
| 03 | Prepare slides for topic confirmation submission | TBD | Per course deadline |
| 04 | Write proposal/docx clearly stating product purpose & how it supports the Leader | TBD | Next meeting |
| 05 | Draft UI wireframe (mini-window layout) | TBD | Next meeting |
| 06 | Push this meeting minutes to the team's GitHub repository | Đoàn Khánh Hưng | Today |

---

## 7. NOTES & REMINDERS

- The instructor values **problem-solving thinking** over the product itself — the proposal must clearly articulate *why* this product is needed.
- The proposal/docx must emphasize: this product **supports the Leader**, it does not replace them.
- Time remaining: **~8 weeks** → distribute workload wisely, avoid scope creep.
- Ideal demo scenario: **online meeting** (easier to control the environment and test features).

---

## NEXT MEETING — TENTATIVE AGENDA

- **Date:** *(TBD)*
- **Agenda:**
  1. Vote on Open Issues (OI-1 to OI-3)
  2. Finalize overall system architecture
  3. Assign specific features to team members
  4. Review proposal before submission

---
