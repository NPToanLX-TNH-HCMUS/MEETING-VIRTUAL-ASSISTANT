"""
tests/unit/test_minutes_extractor.py
====================================
Unit tests for the Stage 3 meeting minutes extraction and Markdown assembly engine.
Verifies prompt construction, schema validation, empty-input short-circuiting,
error handling, and robust Markdown table rendering.
"""

import json
from unittest.mock import MagicMock, patch

import pytest
from pydantic import ValidationError

from src.api.objects import ActionItem, MinutesExtraction
from src.backend.minutes_extractor.minutes_extractor import (
    MINUTES_SCHEMA,
    assemble_markdown,
    extract_minutes,
)
from src.backend.utils.llm import LLMCallError


class TestMinutesExtractorUnit:
    """Unit tests for extract_minutes function."""

    def test_extract_minutes_empty_or_whitespace_transcript_short_circuits(self):
        """Empty transcript must return default MinutesExtraction without calling LLM."""
        with patch("src.backend.minutes_extractor.minutes_extractor.call_llm") as mock_call_llm:
            res_empty = extract_minutes(transcript="", meeting_date="2026-11-08")
            res_ws = extract_minutes(transcript="   \n  \t  ", meeting_date="2026-11-08")

            assert res_empty.summary == "No transcript was available."
            assert res_empty.decisions == []
            assert res_empty.action_items == []
            assert res_empty.unresolved_issues == []

            assert res_ws.summary == "No transcript was available."
            assert mock_call_llm.call_count == 0

    def test_extract_minutes_valid_structured_llm_response(self):
        """Valid JSON returned by LLM must parse into valid MinutesExtraction model."""
        mock_payload = {
            "summary": "Team aligned on Q4 deliverables and mobile app release timeline.",
            "decisions": ["Launch beta on Nov 25", "Adopt PostgreSQL for analytics"],
            "action_items": [
                {
                    "task": "Finalize database schema migration scripts",
                    "assignee": "Alice",
                    "due": "2026-11-15",
                    "quote": "Alice said: I will finalize the schema migrations by the 15th.",
                },
                {
                    "task": "Review security audit report",
                    "assignee": None,
                    "due": None,
                    "quote": "Someone needs to check the security audit.",
                },
            ],
            "unresolved_issues": ["Third-party payment vendor pricing dispute"],
        }

        with patch(
            "src.backend.minutes_extractor.minutes_extractor.call_llm",
            return_value=json.dumps(mock_payload),
        ) as mock_call:
            extraction = extract_minutes(
                transcript="Alice: I will finalize the schema migrations by the 15th.",
                meeting_date="2026-11-08",
                agenda_items=[{"title": "Architecture Review"}],
            )

            assert isinstance(extraction, MinutesExtraction)
            assert extraction.summary == mock_payload["summary"]
            assert len(extraction.decisions) == 2
            assert len(extraction.action_items) == 2
            assert extraction.action_items[0].task == "Finalize database schema migration scripts"
            assert extraction.action_items[0].assignee == "Alice"
            assert extraction.action_items[0].due == "2026-11-15"
            assert extraction.unresolved_issues == ["Third-party payment vendor pricing dispute"]

            # Verify prompt content
            called_prompt = mock_call.call_args[0][0]
            assert "<agenda>" in called_prompt
            assert "- Architecture Review" in called_prompt
            assert "<transcript>" in called_prompt
            assert mock_call.call_args[1]["_schema"] == MINUTES_SCHEMA

    def test_extract_minutes_invalid_schema_raises_llm_call_error_422(self):
        """When LLM returns invalid structure, extract_minutes must raise LLMCallError with status 422."""
        # Missing required field 'decisions' and 'summary'
        invalid_json = json.dumps({"action_items": []})

        with patch(
            "src.backend.minutes_extractor.minutes_extractor.call_llm",
            return_value=invalid_json,
        ):
            with pytest.raises(LLMCallError) as exc_info:
                extract_minutes(
                    transcript="Bob: Working on it.",
                    meeting_date="2026-11-08",
                )
            assert exc_info.value.status == 422
            assert exc_info.value.code == "LLM_BAD_OUTPUT"


class TestAssembleMarkdownUnit:
    """Unit tests for assemble_markdown function."""

    def test_assemble_markdown_full_content(self):
        """Assembling markdown with all fields present produces valid headers and Markdown table."""
        extraction = MinutesExtraction(
            summary="Product sprint planning concluded successfully.",
            decisions=["Ship MVP on Friday"],
            action_items=[
                ActionItem(
                    task="Update UI design with | special pipe chars",
                    assignee="Carol",
                    due="2026-11-20",
                    quote="Carol: I'll update the UI design.",
                )
            ],
            unresolved_issues=["API rate limit tiers under discussion"],
        )

        md = assemble_markdown(
            extraction=extraction,
            meeting_id="meet-12345",
            meeting_topic="Sprint Planning",
            meeting_date="2026-11-08",
        )

        assert "# Meeting Minutes — Sprint Planning" in md
        assert "**Date:** 2026-11-08" in md
        assert "## Summary\n\nProduct sprint planning concluded successfully." in md
        assert "## Decisions\n\n- Ship MVP on Friday" in md
        assert "## Action Items" in md
        # Pipe character escaping test
        assert "| Update UI design with \\| special pipe chars | Carol | 2026-11-20 |" in md
        assert "## Unresolved Issues\n\n- API rate limit tiers under discussion" in md
        assert "_Meeting ID: meet-12345_" in md

    def test_assemble_markdown_fallback_empty_sections(self):
        """Assembling markdown with empty decisions and actions renders polite fallback text."""
        extraction = MinutesExtraction(
            summary="Brief standup with no new commitments.",
            decisions=[],
            action_items=[],
            unresolved_issues=[],
        )

        md = assemble_markdown(
            extraction=extraction,
            meeting_id="standup-99",
            meeting_topic="Daily Sync",
            meeting_date="2026-11-08",
        )

        assert "_No decisions were made._" in md
        assert "_No action items._" in md
        assert "## Unresolved Issues" not in md
        assert "_Meeting ID: standup-99_" in md

