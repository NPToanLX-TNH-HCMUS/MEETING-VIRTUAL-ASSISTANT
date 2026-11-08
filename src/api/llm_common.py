"""
src/api/llm_common.py
=====================
Backwards-compatibility shim re-exporting agenda extraction functions
now relocated to src.backend.agenda_extractor.agenda_extractor.
"""

from src.backend.agenda_extractor.agenda_extractor import (
    system_prompt,
    build_prompt,
    extract_topics,
)

__all__ = ["system_prompt", "build_prompt", "extract_topics"]
