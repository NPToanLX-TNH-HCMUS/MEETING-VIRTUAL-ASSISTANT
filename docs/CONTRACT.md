# TEAM WORKING AGREEMENT — TEAM CONTRACT

> **Project:** Meeting Intelligence Assistant  
> **Domain:** Track D — Group 4  
> **Course Code:** CSC10014 — Computational Thinking  
> **Effective Date:** October 20th, 2026  
> **Version:** 1.1 *(Updated: October 21st, 2026)*

---

## 1. MEMBERS & COMMITMENT

By confirming below, all members agree to abide by the rules, communication standards, and accountability protocols established in this document.

| Full Name | Student ID | Role | Responsibility | Status |
|-----------|------------|------|----------------|--------|
| Võ Lê Nam Khánh Ann | 25127274 | Leader | Discord server management, overall coordination | Agreed ✅ |
| Nguyễn Thành Tài | 25127134 | Member | Task assignment, deadline setting, task descriptions (input/output spec) | Agreed ✅ |
| Nguyễn Cao An Bình | 25127183 | Member | — | Agreed ✅ |
| Đoàn Khánh Hưng | 25127195 | Member | — | Agreed ✅ |
| Bùi Đăng Khôi | 25127203 | Member | — | Agreed ✅ |
| Ngô Phước Toàn | 25127522 | Member | — | Agreed ✅ |

---

## 2. CORE PRINCIPLES & TASK ACCOUNTABILITY

### 2.1. Task Ownership & Deadlines (The "No-Silence" Rule)

- **Strict Deadline Adherence:** Every member is fully responsible for their assigned tasks and must deliver them on or before the agreed deadline.
- **Early Assessment:** If a task feels too heavy or too light after receiving it, members must **speak up immediately** so it can be redistributed or adjusted.
- **Proactive Escalation:** If a member encounters blockers or realizes they cannot meet a deadline, they **must raise the issue to the group at least 24 hours in advance** — not the morning of the deadline. If it is the morning of the deadline, raise it immediately so the team can attempt to help.
- **Zero Tolerance for "Silent Failure":** Staying silent while failing to complete a task is strictly unacceptable. Post-deadline excuses without prior notice will not be tolerated.
- **Steady Progress:** Work is to be done incrementally each day. "All-nighters" the day before the deadline are strongly discouraged and are not an excuse for poor quality.

### 2.2. Communication & Meetings

- **Primary Channel:** **Discord** (managed by Võ Lê Nam Khánh Ann). All task tracking, deadline notifications, and announcements will be posted here.
- **Response Time:** Members must check Discord regularly. **No unread messages for more than 24 hours** is acceptable. On submission days, respond to mentions within **4 hours**.
- **Recurring Meeting:** Every **Tuesday**, in-person at the Library.
- **Ad-hoc Meetings:** If a critical issue arises between sessions, an online meeting (Google Meet / Discord) may be called with at least **2 hours' notice**.
- **Tardiness:** If running late to any meeting, notify the team in advance. Late arrivals without notice are subject to penalties (see Section 3).

### 2.3. Development Standards

- **Language:** Python (3.13+)
- **Project Structure:** All source code must be organized under the `source/` directory using a modular structure. Each module lives in its own folder.
- **Naming Conventions:**
  - Variables & functions: `snake_case`
  - Classes: `PascalCase`
  - Private variables/methods: prefix with `_` (single underscore, e.g., `_buffer`)
  - Constants: `UPPER_SNAKE_CASE`
- **Code Comments:** Comments must answer **Why**, not What. Explain the reasoning behind a decision, not just what the code does. This benefits both reviewers and your future self.

  ```python
  # ✅ Good: explains WHY
  # Using a hash map here for O(1) deduplication — linear scan would be too slow at scale
  seen = {}

  # ❌ Bad: explains WHAT (already obvious from the code)
  # Create a dictionary called seen
  seen = {}
  ```

### 2.4. Git & Version Control

- **Commits:** Do **not** use `git commit -m "..."` for substantive commits. Run `git commit` (without `-m`) to open the editor and write a proper multi-line commit message with a subject line and body.
- **Commit message format:**
  ```
  <type>: <short summary>

  <body — explain what changed and why>
  ```
  Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`
- **Pull Requests:** All PRs must follow the team's **PR template** (to be defined in `.github/pull_request_template.md`). No bare/empty PRs.
- **Code Review:** PRs require at least **1 approval** before merging.

---

## 3. PENALTIES & DISCIPLINARY ACTIONS

| Violation | Condition | Penalty / Consequence |
|:----------|:----------|:----------------------|
| **Late to Meeting** | Arriving > 15 minutes late without prior notice | Warning *(1st time)* / Contribute **20,000 VND** to team fund *(subsequent times)* |
| **Unexcused Absence** | Missing a meeting without notifying the team | Formal warning + Mandatory extra documentation/review tasks |
| **Missed Deadline (With Valid Reason)** | Issue raised > 24h in advance with a specific, valid reason | Deadline extension granted; team assists in resolving blockers |
| **Missed Deadline (No Valid Reason)** | Late submission without prior notice | **1st Offense:** Formal warning & peer evaluation deduction.<br>**2nd Offense:** Contribution score reduced by **50%** for that phase. |
| **"Silent Failure" (Ghosting)** | Ignoring messages and leaving tasks incomplete | **Immediate removal from project report** (0% contribution reported to instructor) or task reassignment with zero credit. |
| **Discord Inactivity** | No response to direct mentions for > 24 hours | Formal warning; repeated violations escalate to penalty above. |


---

## 4. CONFLICT RESOLUTION

1. **Direct Discussion:** Disagreements are resolved via team vote (majority rules). In a 3–3 tie, the **Leader** holds the tie-breaking vote.
2. **Instructor Intervention:** If a member repeatedly violates this contract and ignores internal warnings, the Leader will submit the Git commit history, Discord logs, and meeting minutes to the course instructor for official grade adjustment.

---

## 5. AMENDMENTS

Any changes to this contract must be:
1. Proposed at a scheduled team meeting.
2. Approved by a **simple majority vote** (≥ 4 out of 6 members).
3. Documented as a new version (e.g., v1.2) and committed to the repository.

---
