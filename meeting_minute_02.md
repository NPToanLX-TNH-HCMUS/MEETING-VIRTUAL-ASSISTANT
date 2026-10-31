# PROJECT MEETING MINUTES — SESSION #02

> **Project:** Meeting Intelligence Assistant  
> **Domain:** D  
> **Course Code:** CSC10014 — Computational Thinking  

---

## GENERAL INFORMATION

| | |
|---|---|
| **Date** | Tuesday, October 20th, 2026 |
| **Time** | 3:00 PM – 6:00 PM |
| **Format** | In-person at the Library |
| **Objective** | Establish Team Contract, resolve Open Issues, define Git/Coding conventions, and assign PoC tasks for next week |

### Attendees

| Full Name | Student ID | Role | Present |
|-----------|------------|------|---------|
| Võ Lê Nam Khánh Ann | 25127274 | Leader | ✅ |
| Nguyễn Thành Tài | 25127134 | Member | ✅ |
| Nguyễn Cao An Bình | 25127183 | Member | ✅ |
| Đoàn Khánh Hưng | 25127195 | Member | ✅ |
| Bùi Đăng Khôi | 25127203 | Member | ✅ |
| Ngô Phước Toàn | 25127522 | Member | ✅ |

---

## 1. PREVIOUS ACTION ITEMS REVIEW (FROM SESSION #01)

| ID | Task | Status | Notes / Outcomes |
|:---|:-----|:-------|:-----------------|
| 01 | Research Speaker Diarization feasibility | ✅ Completed | Integrated into Algorithm Design (OpenAI / Gemini APIs) |
| 02 | Evaluate Web App vs Desktop App | ✅ Completed | Decided to build an App (see Section 3) |
| 03 | Prepare slides for topic confirmation | ✅ Completed | — |
| 04 | Write Phase 1 Proposal (LaTeX/PDF) | 🔄 In Progress | Khôi needs to revise and rewrite his section. Other sections completed. |
| 05 | Draft UI wireframe | 🔄 In Progress | UI design is deferred; focus on a simple phone-like side-window |
| 06 | Push Session #01 minutes to GitHub | ✅ Completed | Pushed by Đoàn Khánh Hưng |

---

## 2. TEAM WORKING AGREEMENT (TEAM CONTRACT)

### 2.1. Context & Motivation

To ensure smooth collaboration and prevent bottlenecks, the team established a formal **Team Contract** (see [`CONTRACT.md`](../CONTRACT.md)).

### 2.2. Key Rules Agreed Upon

- **Task Accountability (The "No-Silence" Rule):** Members must proactively raise issues or request task reassignments if the workload is too heavy or a deadline is at risk (even on the morning of the deadline, the team must be notified for support). Work should be done daily, not crammed in one night.
- **Communication:** The team is moving away from Jira. **Discord** will be the main platform for task tracking and communication. Members must check Discord regularly, and failing to check messages for over 24 hours is unacceptable.

> **Decision:** All 6 members reviewed and agreed to the terms in [`CONTRACT.md`](../CONTRACT.md).

---

## 3. RESOLUTION OF OPEN ISSUES (FROM SESSION #01)

| # | Issue | Final Decision | Rationale / Technical Approach |
|---|-------|----------------|-------------------------------|
| OI-1 | **Platform:** Web App or Desktop App? | **App (Desktop Prototype)** | Saves time on UI/UX design initially. The goal is a minimal UI that runs as a small window on the side of the screen. |
| OI-4 | **Task Management Tool** | **Discord** | Jira is replaced by Discord for easier tracking. Khánh Ann will manage the Discord server, and Tài will assign detailed tasks (with specific inputs/outputs). |

---

## 4. SYSTEM ARCHITECTURE & DEVELOPMENT CONVENTIONS

### 4.1. Technical Workflow

- The system must clearly separate **API calls** from **Custom Algorithms** (the complex logic handled by the team).
- For the PoC, the team must test APIs thoroughly. If one API is not definitively chosen, implement multiple options for comparison testing.
- The Leader will act as the session monitor, dynamically assigning or reassigning tasks to members if the workload is unbalanced.

### 4.2. Coding & Git Conventions

- **Code Comments:** Comments must answer **"Why"** a specific approach was used, not just **"What"** the code does, to ensure team-wide understanding.
- **Git Commit:** Do not use `git commit -m "..."`. Use `git commit` and press Enter to write detailed, multi-line commit messages.
- **Pull Requests (PR):** All PRs must follow a proper, standardized template.
- **Naming Conventions:** Strict naming conventions will be applied across the repository (folders, modules, app structure all within the `source` directory).

---

## 5. ACTION ITEMS (FOR NEXT WEEK)

**Goal for next week:** Deliver a runnable PoC where each member handles one specific part. The workflow must demonstrate: *Input (Text/Audio) → Output (Summarized/Analyzed Text)*.

| ID | Task | Owner | Deadline |
|:---|:-----|:------|:---------|
| 01 | Manage Discord setup and structure | Khánh Ann | ASAP |
| 02 | Define detailed task assignments (Input/Output specs) and assign the base Python app creation | Tài | ASAP |
| 03 | Revise and rewrite assigned Algorithm/Proposal section | Khôi | Next meeting |
| 04 | Implement PoC: Audio-to-Text conversion | *[TBD by Tài]* | Next meeting |
| 05 | Implement PoC: Text Summarization & Analysis | *[TBD by Tài]* | Next meeting |
| 06 | Implement PoC: Agenda Tracking (e.g., crossing out discussed points) | *[TBD by Tài]* | Next meeting |
| 07 | Implement PoC: Question Answering (AI) | *[TBD by Tài]* | Next meeting |
| 08 | Research "localhost" sharing solutions for team collaboration | All Members | Next meeting |
| 09 | Push `CONTRACT.md` and `meeting_minute_02.md` to GitHub | Khánh Hưng | Today |

---

## 6. NOTES & REMINDERS

- **Meeting Schedule:** Weekly in-person meetings every **Tuesday** at the library. Urgent issues will be resolved via Google Meet.
- **Code incrementally:** Do a little bit every day. Do not wait until the night before the deadline.
- **Audio Capture:** For now, record everything and export it; real-time constraints will be optimized later.

---

## NEXT MEETING — TENTATIVE AGENDA

- **Date:** Tuesday, October 27th, 2026
- **Location:** Library
- **Agenda:**
  1. Review runnable PoC modules from each member.
  2. Integrate the 6 separate parts into a single workflow.
  3. Review API comparison test results.

---

> *Minutes compiled from session notes. Members listed in Action Items, please update your progress on Discord before the next meeting.*  
> *For corrections or additions, please open an Issue or Pull Request on GitHub.*