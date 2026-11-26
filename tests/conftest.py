"""
Shared pytest fixtures and paths for the entire test suite.

Why: Centralizing all eval_data paths in one conftest.py prevents every
test file from duplicating path logic and ensures a single source of truth
when the dataset structure changes.
"""

import sys
from pathlib import Path
import pytest

# Ensure src/ is on sys.path so tests can import from backend, frontend, etc.
SRC_DIR = Path(__file__).resolve().parent.parent / "src"
if str(SRC_DIR) not in sys.path:
    sys.path.insert(0, str(SRC_DIR))

# Module-level constants for dynamic path resolution
TESTS_DIR = Path(__file__).parent
EVAL_DATA_DIR = TESTS_DIR / "eval_data"
BENCHMARKS_DIR = TESTS_DIR / "benchmarks"

@pytest.fixture
def eval_data_dir() -> Path:
    return EVAL_DATA_DIR

@pytest.fixture
def benchmarks_dir() -> Path:
    return BENCHMARKS_DIR

@pytest.fixture
def sample_transcript_path() -> Path:
    benchmark_file = (
        BENCHMARKS_DIR
        / "PHASE_3_Transcript_To_Minutes"
        / "Minutes_Synthesis_12Cases"
        / "samples"
        / "S01"
        / "transcript.txt"
    )
    if benchmark_file.exists() and benchmark_file.stat().st_size > 0:
        return benchmark_file
    return EVAL_DATA_DIR / "transcripts" / "sample_transcript.txt"

@pytest.fixture
def sample_audio_path() -> Path:
    benchmark_file = (
        BENCHMARKS_DIR
        / "PHASE_2_Audio_To_Transcript"
        / "STT_English_AMI_16Cases"
        / "samples"
        / "S01"
        / "meeting.wav"
    )
    if benchmark_file.exists() and benchmark_file.stat().st_size > 0:
        return benchmark_file
    return EVAL_DATA_DIR / "input_audio" / "clean_sample_01.wav"

@pytest.fixture
def ground_truth_entities_path() -> Path:
    return EVAL_DATA_DIR / "ground_truth" / "content_analyzer" / "ground_truth_entities.json"

@pytest.fixture
def ground_truth_minutes_path() -> Path:
    benchmark_file = (
        BENCHMARKS_DIR
        / "PHASE_3_Transcript_To_Minutes"
        / "Minutes_Synthesis_12Cases"
        / "samples"
        / "S01"
        / "ground_truth_minutes.json"
    )
    if benchmark_file.exists() and benchmark_file.stat().st_size > 0:
        return benchmark_file
    return None

@pytest.fixture
def reference_agenda_path() -> Path:
    benchmark_file = (
        BENCHMARKS_DIR
        / "PHASE_1_Document_To_Agenda"
        / "Ingestion_Agenda_20Cases"
        / "samples"
        / "S01"
        / "ground_truth_agenda.json"
    )
    if benchmark_file.exists() and benchmark_file.stat().st_size > 0:
        return benchmark_file
    return EVAL_DATA_DIR / "ground_truth" / "agenda_tracker" / "reference_agenda.json"
    
def pytest_collection_modifyitems(config: pytest.Config, items: list[pytest.Item]) -> None:
    """Automatically assign pytest markers based on test directory tier."""
    for item in items:
        rel_path = Path(item.fspath).relative_to(Path(__file__).parent)
        parts = rel_path.parts
        if "unit" in parts:
            item.add_marker(pytest.mark.unit)
        elif "integration" in parts:
            item.add_marker(pytest.mark.integration)
        elif "evaluation" in parts:
            item.add_marker(pytest.mark.evaluation)
        elif "e2e" in parts:
            item.add_marker(pytest.mark.e2e)