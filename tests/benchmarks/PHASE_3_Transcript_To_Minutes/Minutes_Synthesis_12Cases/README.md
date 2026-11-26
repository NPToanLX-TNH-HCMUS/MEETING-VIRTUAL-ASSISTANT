# Benchmark Suite: PHASE 3 - Transcript To Minutes & Action Items

## 1. Overview
Evaluates meeting semantic intelligence:
* Executive meeting summarization.
* Decision identification.
* Action item extraction (Task, Assignee, Due date).
* Deterministic completeness audit (`[CONFIRMED]` vs `[UNCONFIRMED]`).

## 2. Dataset Specification (12 Cases Target)
* Target Cases:
  * `S01` - `S06`: Clean meeting transcripts with complete task assignments.
  * `S07` - `S12`: Edge cases (unassigned deadlines, mid-meeting reassignments, small talk filtering).

## 3. Metrics
* Entity Precision, Recall, F1-Score (Task, Owner, Due).
* Deterministic Rule Audit Accuracy (100% SLA target).
* Remaining Points Tracking F1-Score.

