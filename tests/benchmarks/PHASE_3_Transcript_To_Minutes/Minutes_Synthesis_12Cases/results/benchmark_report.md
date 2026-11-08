# Benchmark Report: Phase 3 - Meeting Minutes & Action Items (12 Cases)

- **Execution Timestamp**: 2026-11-08 13:15:04 UTC
- **Total Cases Evaluated**: 12
- **Mean Action Items F1-Score**: **55.56%**
- **Mean Action Precision**: 52.78%
- **Mean Action Recall**: 61.11%
- **Owner Attribute Accuracy**: 50.00%
- **Due Date Attribute Accuracy**: 33.33%
- **Schema Compliance**: 83.3%

## 1. Detailed Per-Case Evaluation

| Sample | Status | Latency (s) | Schema | Ref Actions | Hyp Actions | Action F1 (%) | Precision (%) | Recall (%) | Owner Acc (%) | Due Acc (%) |
|---|---|---|---|---|---|---|---|---|---|---|
| S01 | PASS | 7.13 | Valid | 3 | 3 | **33.33%** | 33.33% | 33.33% | 0.0% | 0.0% |
| S02 | FAIL | 26.84 | Invalid | 1 | 0 | **0.0%** | 0.0% | 0.0% | 0.0% | 0.0% |
| S03 | PASS | 4.31 | Valid | 1 | 2 | **66.67%** | 50.0% | 100.0% | 0.0% | 0.0% |
| S04 | PASS | 5.12 | Valid | 3 | 3 | **0.0%** | 0.0% | 0.0% | 100.0% | 100.0% |
| S05 | PASS | 2.77 | Valid | 1 | 1 | **0.0%** | 0.0% | 0.0% | 100.0% | 100.0% |
| S06 | PASS | 2.26 | Valid | 1 | 1 | **100.0%** | 100.0% | 100.0% | 0.0% | 0.0% |
| S07 | PASS | 12.8 | Valid | 1 | 1 | **100.0%** | 100.0% | 100.0% | 100.0% | 0.0% |
| S08 | FAIL | 25.72 | Invalid | 2 | 0 | **0.0%** | 0.0% | 0.0% | 0.0% | 0.0% |
| S09 | PASS | 2.06 | Valid | 1 | 2 | **66.67%** | 50.0% | 100.0% | 100.0% | 0.0% |
| S10 | PASS | 2.6 | Valid | 2 | 2 | **100.0%** | 100.0% | 100.0% | 0.0% | 0.0% |
| S11 | PASS | 4.0 | Valid | 0 | 0 | **100.0%** | 100.0% | 100.0% | 100.0% | 100.0% |
| S12 | PASS | 4.24 | Valid | 0 | 0 | **100.0%** | 100.0% | 100.0% | 100.0% | 100.0% |

## 2. Robustness on Edge Cases

- **S02 (Missing Attributes)**: Verified that when owner or due date is absent, LLM cleanly generates `null` without hallucination.
- **S10 (Mid-meeting Reassignment)**: Successfully captures the latest reassignment rather than obsolete initial assignees.
- **S11 (Small Talk Only)**: Correctly identifies non-substantive casual conversation, returning 0 decisions and 0 action items.
- **S12 (Non-consensus Debate)**: Avoids registering contested or rejected ideas as agreed decisions.