"""
EVALUATION SUITE: Speech-to-Text (STT) Quality & Robustness Benchmark.

Implements mathematical metrics:
1. Word Error Rate (WER):
   Formula: WER = (S + D + I) / N
   Target: WER <= 10% (0.10)
2. Estimated WER (e-WER):
   Formula: e-WER = (ERR / N) * 100%
   Used at runtime when reference ground-truth is not yet available.
"""

import pytest


def compute_wer(reference_text: str, hypothesis_text: str) -> float:
    """
    Computes exact Word Error Rate (WER) using word-level Levenshtein dynamic programming.
    
    Formula:
        WER = (S + D + I) / N
    Where:
        N = Total words in reference
        S = Substitutions (words recognized incorrectly)
        D = Deletions (words spoken but dropped by STT)
        I = Insertions (phantom words hallucinated by STT)
    """
    ref_words = reference_text.strip().lower().split()
    hyp_words = hypothesis_text.strip().lower().split()
    n = len(ref_words)

    if n == 0:
        return 0.0 if len(hyp_words) == 0 else 1.0

    # 2D DP matrix for minimum edit operations (Levenshtein distance)
    dp = [[0] * (len(hyp_words) + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(len(hyp_words) + 1):
        dp[0][j] = j

    for i in range(1, n + 1):
        for j in range(1, len(hyp_words) + 1):
            cost = 0 if ref_words[i - 1] == hyp_words[j - 1] else 1
            dp[i][j] = min(
                dp[i - 1][j] + 1,        # Deletion (D)
                dp[i][j - 1] + 1,        # Insertion (I)
                dp[i - 1][j - 1] + cost  # Substitution (S)
            )

    edit_distance = dp[n][len(hyp_words)]
    return round(edit_distance / n, 4)


def compute_estimated_wer(predicted_errors: int, total_predicted_words: int) -> float:
    """
    Computes runtime Estimated WER (e-WER).
    Formula: e-WER = (ERR / N) * 100%
    """
    if total_predicted_words == 0:
        return 0.0
    return round((predicted_errors / total_predicted_words) * 100, 2)


class TestSTTEvaluationMetrics:
    """Mathematical validation of the STT evaluation formulas."""

    def test_wer_perfect_transcription_zero_error(self):
        """TC-STT-01: When hypothesis matches reference verbatim, WER must be 0.0."""
        ref = "Segment Tree is a binary tree data structure used for interval information"
        hyp = "Segment Tree is a binary tree data structure used for interval information"
        assert compute_wer(ref, hyp) == 0.0

    def test_wer_calculation_with_substitutions_and_deletions(self):
        """
        TC-STT-02: Quantitative error calculation.
        Reference: 10 words.
        - Deletion (1): missing 'tree'
        - Substitution (1): 'four' -> '4'
        WER = (1 + 1) / 10 = 0.20 (20%).
        """
        ref = "the segment tree array size is four times the size"
        hyp = "the segment array size is 4 times the size"
        assert compute_wer(ref, hyp) == 0.20

    def test_wer_exceeding_threshold_fails_sla(self):
        """Validates that a low-quality STT output with WER > 10% is correctly identified."""
        ref = "we need to build query and update functions for segment tree"
        hyp = "we need build and functions"  # 5 deletions out of 11 words (~45%)
        wer = compute_wer(ref, hyp)
        assert wer > 0.10, f"Expected WER > 10%, got {wer * 100}%"

    def test_estimated_wer_runtime_formula(self):
        """Verifies runtime e-WER formula: e-WER = (ERR / N) * 100%."""
        # 2 detected speech-distortion errors in a 20-word utterance -> 10.0%
        e_wer = compute_estimated_wer(predicted_errors=2, total_predicted_words=20)
        assert e_wer == 10.0
