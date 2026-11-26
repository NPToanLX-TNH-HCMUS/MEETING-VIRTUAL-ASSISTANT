"""
EVALUATION SUITE: Remaining Points Tracker (In-meeting).

Implements Information Retrieval evaluation metrics:
1. Confusion Matrix:
   - TP: Correctly covered agenda items 
   - FP: Falsely covered items 
   - FN: Missed items 
2. Precision (P): P = TP / (TP + FP)  -> Target: >= 90%
3. Recall (R):    R = TP / (TP + FN)  -> Target: >= 85%
4. F1-Score:      F1 = 2 * (P * R) / (P + R) -> Target: >= 85%
"""

from typing import Dict, Set
import pytest


def evaluate_remaining_points_tracker(
    all_agenda_ids: Set[int],
    ground_truth_remaining_ids: Set[int],
    predicted_remaining_ids: Set[int],
) -> Dict[str, float]:
    """
    Evaluates tracking accuracy when crossing out discussed points.
    Covered items = All Agenda Items - Remaining Items
    """
    # Covered sets (items crossed out)
    gt_covered = all_agenda_ids - ground_truth_remaining_ids
    pred_covered = all_agenda_ids - predicted_remaining_ids

    # Confusion matrix calculations
    tp = len(pred_covered.intersection(gt_covered))
    fp = len(pred_covered - gt_covered)
    fn = len(gt_covered - pred_covered)

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


class TestRemainingPointsEvaluationMetrics:
    """Mathematical validation of the Information Retrieval evaluation metrics."""

    def test_perfect_tracking_step1_yields_f1_one(self):
        """
        TC-TRK-01: Perfect tracking after Snippet Step 1 (Theory discussed).
        All points: {1, 2, 3}.
        Ground truth: Point 1 discussed -> Remaining: {2, 3}.
        Predicted: Tracker crossed off Point 1 -> Remaining: {2, 3}.
        Expected: Precision = 1.0, Recall = 1.0, F1 = 1.0.
        """
        all_points = {1, 2, 3}
        gt_remaining = {2, 3}
        pred_remaining = {2, 3}

        metrics = evaluate_remaining_points_tracker(all_points, gt_remaining, pred_remaining)
        assert metrics["precision"] == 1.0
        assert metrics["recall"] == 1.0
        assert metrics["f1_score"] == 1.0

    def test_false_positive_penalty_on_small_talk(self):
        """
        TC-TRK-02: Robustness against false strike-outs during small talk.
        Suppose tracker prematurely strikes off Point 2 when only greeting occurred.
        Ground truth: Nothing discussed yet -> Covered: {} (Remaining: {1, 2, 3}).
        Predicted: Crossed off Point 2 -> Covered: {2} (Remaining: {1, 3}).
        Expected: TP = 0, FP = 1 -> Precision = 0.0.
        """
        all_points = {1, 2, 3}
        gt_remaining = {1, 2, 3}
        pred_remaining = {1, 3}  # Prematurely crossed off 2

        metrics = evaluate_remaining_points_tracker(all_points, gt_remaining, pred_remaining)
        assert metrics["false_positives"] == 1
        assert metrics["precision"] == 0.0

    def test_missed_points_reduces_recall(self):
        """
        Validates Recall penalty when an item was discussed but tracker missed it.
        Ground truth: Points 1 & 2 discussed (Covered: {1, 2}, Remaining: {3}).
        Predicted: Only crossed off Point 1 (Covered: {1}, Remaining: {2, 3}).
        Expected: TP = 1, FN = 1 -> Recall = 1 / (1 + 1) = 0.50 (50%).
        """
        all_points = {1, 2, 3}
        gt_remaining = {3}
        pred_remaining = {2, 3}

        metrics = evaluate_remaining_points_tracker(all_points, gt_remaining, pred_remaining)
        assert metrics["false_negatives"] == 1
        assert metrics["recall"] == 0.50
        assert metrics["precision"] == 1.0
        # F1 = 2 * (1.0 * 0.5) / (1.0 + 0.5) = 1.0 / 1.5 = 0.6667
        assert metrics["f1_score"] == 0.6667
