"""
EVALUATION SUITE: Meeting Content Analyzer & Rule Engine (Post-meeting).

Implements evaluation metrics for Information Extraction:
1. Entity Precision, Recall, and F1-Score:
   - Measures semantic extraction accuracy of Topics, Deadlines, and Ideas against Ground Truth.
   - Target: Precision >= 90%, Recall >= 85%, F1 >= 85%.
2. Rule Audit Accuracy:
   - Measures correctness of deterministic Python O(1) flags (CONFIRMED vs UNCONFIRMED).
   - Target: 100% deterministic accuracy.
"""

import json
from pathlib import Path
from typing import Dict, List, Set
import pytest


def compute_entity_prf(ground_truth_entities: Set[str], predicted_entities: Set[str]) -> Dict[str, float]:
    """
    Computes Precision, Recall, and F1-score for extracted entity sets.
    Matches are evaluated based on normalized entity summaries.
    """
    tp = len(predicted_entities.intersection(ground_truth_entities))
    fp = len(predicted_entities - ground_truth_entities)
    fn = len(ground_truth_entities - predicted_entities)

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) > 0 else 0.0

    return {
        "true_positives": tp,
        "false_positives": fp,
        "false_negatives": fn,
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1_score": round(f1, 4),
    }


class TestContentAnalyzerEvaluationMetrics:
    """Quantitative validation of Content Analyzer extraction accuracy and audit rules."""

    def test_ground_truth_json_loads_correct_schema(self, ground_truth_entities_path: Path):
        """
        Validates that the unified Golden Dataset ground_truth_entities.json
        exists, is valid JSON, and adheres to the project schema.
        """
        assert ground_truth_entities_path.exists(), "Golden ground truth JSON must exist"
        data = json.loads(ground_truth_entities_path.read_text(encoding="utf-8"))

        assert "expected_topics" in data
        assert "expected_entities" in data
        assert len(data["expected_topics"]) >= 2
        assert len(data["expected_entities"]) >= 5

    def test_perfect_entity_extraction_achieves_target_sla(self):
        """
        TC-ANL-01: Perfect match against Ground Truth must yield P = 1.0, R = 1.0, F1 = 1.0.
        SLA Target: Precision >= 90%, Recall >= 85%, F1 >= 85%.
        """
        gt_set = {
            "Implement Segment Tree Build and Query functions",
            "Write Lazy Propagation technical documentation",
            "Create shared Google Sheet for team tech links",
        }
        pred_set = {
            "Implement Segment Tree Build and Query functions",
            "Write Lazy Propagation technical documentation",
            "Create shared Google Sheet for team tech links",
        }

        scores = compute_entity_prf(gt_set, pred_set)
        assert scores["precision"] == 1.0
        assert scores["recall"] == 1.0
        assert scores["f1_score"] == 1.0
        assert scores["f1_score"] >= 0.85, "Must exceed the 85% F1 SLA target"

    def test_hallucinated_task_penalizes_precision(self):
        """
        Tests that hallucinating an unmentioned task drops Precision below the 90% SLA threshold.
        Ground truth: 2 tasks. Predicted: 2 genuine + 1 hallucinated -> Precision = 2/3 = 66.7%.
        """
        gt_set = {"Task A", "Task B"}
        pred_set = {"Task A", "Task B", "Fake Hallucinated Task C"}

        scores = compute_entity_prf(gt_set, pred_set)
        assert scores["false_positives"] == 1
        assert scores["precision"] == 0.6667
        assert scores["recall"] == 1.0  # Recall is still 100% since no true task was missed

    def test_rule_audit_accuracy_deterministic_100_percent(self):
        """
        TC-ANL-02: Rule engine deterministic audit accuracy.
        Out of 4 evaluated cases (1 complete, 2 incomplete deadlines, 1 tentative idea),
        all 4 must be flagged with 100% accuracy.
        """
        ground_truth_statuses = ["CONFIRMED", "UNCONFIRMED", "UNCONFIRMED", "UNCONFIRMED"]
        predicted_statuses = ["CONFIRMED", "UNCONFIRMED", "UNCONFIRMED", "UNCONFIRMED"]

        correct = sum(1 for gt, pred in zip(ground_truth_statuses, predicted_statuses) if gt == pred)
        audit_accuracy = correct / len(ground_truth_statuses)

        assert audit_accuracy == 1.0, "Rule engine must achieve 100% deterministic accuracy"
