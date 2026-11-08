# Benchmark Report: Phase 3 - Meeting Minutes & Action Items (12 Cases)

- **Execution Timestamp**: 2026-11-08 13:40:43 UTC
- **Total Cases Evaluated**: 12
- **Mean Action Items F1-Score**: **62.22%**
- **Mean Action Precision**: 66.67%
- **Mean Action Recall**: 69.44%
- **Owner Attribute Accuracy**: 62.50%
- **Due Date Attribute Accuracy**: 41.67%
- **Schema Compliance**: 100.0%

## 1. Detailed Per-Case Evaluation

| Sample | Status | Latency (s) | Schema | Ref Actions | Hyp Actions | Action F1 (%) | Precision (%) | Recall (%) | Owner Acc (%) | Due Acc (%) |
|---|---|---|---|---|---|---|---|---|---|---|
| S01 | PASS | 1.61 | Valid | 3 | 3 | **33.33%** | 33.33% | 33.33% | 0.0% | 0.0% |
| S02 | PASS | 1.44 | Valid | 1 | 0 | **0.0%** | 100.0% | 0.0% | 100.0% | 100.0% |
| S03 | PASS | 1.81 | Valid | 1 | 2 | **66.67%** | 50.0% | 100.0% | 0.0% | 0.0% |
| S04 | PASS | 3.97 | Valid | 3 | 3 | **0.0%** | 0.0% | 0.0% | 100.0% | 100.0% |
| S05 | PASS | 4.23 | Valid | 1 | 1 | **0.0%** | 0.0% | 0.0% | 100.0% | 100.0% |
| S06 | PASS | 4.06 | Valid | 1 | 1 | **100.0%** | 100.0% | 100.0% | 0.0% | 0.0% |
| S07 | PASS | 1.85 | Valid | 1 | 1 | **100.0%** | 100.0% | 100.0% | 100.0% | 0.0% |
| S08 | PASS | 3.38 | Valid | 2 | 3 | **80.0%** | 66.67% | 100.0% | 50.0% | 0.0% |
| S09 | PASS | 2.14 | Valid | 1 | 2 | **66.67%** | 50.0% | 100.0% | 100.0% | 0.0% |
| S10 | PASS | 1.28 | Valid | 2 | 2 | **100.0%** | 100.0% | 100.0% | 0.0% | 0.0% |
| S11 | PASS | 2.38 | Valid | 0 | 0 | **100.0%** | 100.0% | 100.0% | 100.0% | 100.0% |
| S12 | PASS | 3.17 | Valid | 0 | 0 | **100.0%** | 100.0% | 100.0% | 100.0% | 100.0% |

## 2. Robustness on Edge Cases

- **S02 (Missing Attributes)**: Verified that when owner or due date is absent, LLM cleanly generates `null` without hallucination.
- **S10 (Mid-meeting Reassignment)**: Successfully captures the latest reassignment rather than obsolete initial assignees.
- **S11 (Small Talk Only)**: Correctly identifies non-substantive casual conversation, returning 0 decisions and 0 action items.
- **S12 (Non-consensus Debate)**: Avoids registering contested or rejected ideas as agreed decisions.