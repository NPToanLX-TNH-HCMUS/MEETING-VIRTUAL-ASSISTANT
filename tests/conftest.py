"""
Shared pytest fixtures and paths for the entire test suite.

Why: Centralizing all eval_data paths in one conftest.py prevents every
test file from duplicating path logic and ensures a single source of truth
when the dataset structure changes.
"""

import pytest
from pathlib import Path

# Module-level constants for dynamic path resolution
TESTS_DIR = Path(__file__).parent
EVAL_DATA_DIR = TESTS_DIR / "eval_data"

@pytest.fixture
def eval_data_dir() -> Path:
    return EVAL_DATA_DIR

@pytest.fixture
def sample_transcript_path() -> Path:
    return EVAL_DATA_DIR / "transcripts" / "sample_transcript.txt"

@pytest.fixture
def sample_audio_path() -> Path:
    return EVAL_DATA_DIR / "input_audio" / "sample_meeting_01.wav"

@pytest.fixture
def ground_truth_entities_path() -> Path:
    return EVAL_DATA_DIR / "ground_truth" / "ground_truth_entities.json"

@pytest.fixture
def reference_agenda_path() -> Path:
    return EVAL_DATA_DIR / "ground_truth" / "reference_agenda.json"
    