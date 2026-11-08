"""
Unit test suite for LLM JSON Response Handler.

Covers:
- parse_json_list_to_list_of_string: Valid JSON, markdown fences, quoted fallback, numbered lists.
- parse_topics: Standard format, nested structures, bare objects/lists, source attribution,
  proportional time scaling, and 422 error raising on invalid output.
"""

import json
import pytest

from src.backend.utils.json_handler import (
    parse_json_list_to_list_of_string,
    parse_topics,
)
from src.backend.utils.llm import LLMCallError


class TestParseJsonListToString:
    """Unit tests for parse_json_list_to_list_of_string."""

    def test_valid_json_list_parses_cleanly(self) -> None:
        raw = '["System Architecture", "Database Schema", "Security Review"]'
        result = parse_json_list_to_list_of_string(raw)
        assert result == ["System Architecture", "Database Schema", "Security Review"]

    def test_markdown_code_fence_stripping(self) -> None:
        raw = '```json\n["Sprint Planning", "Retro Action Items"]\n```'
        result = parse_json_list_to_list_of_string(raw)
        assert result == ["Sprint Planning", "Retro Action Items"]

    def test_extracts_quoted_strings_when_json_invalid(self) -> None:
        raw = 'Here are the recommended points: "Setup CI/CD Pipeline", and "Write Unit Tests"'
        result = parse_json_list_to_list_of_string(raw)
        assert result == ["Setup CI/CD Pipeline", "Write Unit Tests"]

    def test_fallback_to_numbered_list(self) -> None:
        raw = (
            "1. Architecture Overview\n"
            "2) API Contract Finalization\n"
            "3. Deployment Strategy"
        )
        result = parse_json_list_to_list_of_string(raw)
        assert result == [
            "Architecture Overview",
            "API Contract Finalization",
            "Deployment Strategy",
        ]

    def test_empty_or_whitespace_string_returns_empty_list(self) -> None:
        assert parse_json_list_to_list_of_string("") == []
        assert parse_json_list_to_list_of_string("   \n\t  ") == []


class TestParseTopics:
    """Unit tests for parse_topics."""

    def test_standard_topics_json_parsing(self) -> None:
        reply = json.dumps(
            {
                "items": [
                    {"title": "Kickoff", "source": "document", "minutes": 10},
                    {"title": "Review", "source": "planned_point", "minutes": 20},
                ]
            }
        )
        items = parse_topics(
            reply,
            planned_points=["Review"],
            documents=[{"filename": "doc.md"}],
            duration_minutes=60,
        )
        assert len(items) == 2
        assert items[0]["title"] == "Kickoff"
        assert items[0]["source"] == "document"
        assert items[0]["estimated_minutes"] == 10
        assert items[0]["description"] is None
        assert items[1]["title"] == "Review"
        assert items[1]["source"] == "planned_point"
        assert items[1]["estimated_minutes"] == 20

    def test_nested_items_structure(self) -> None:
        reply = json.dumps(
            {
                "items": {
                    "items": [
                        {"title": "Nested Topic", "source": "document", "minutes": 15}
                    ]
                }
            }
        )
        items = parse_topics(
            reply,
            planned_points=[],
            documents=[{"filename": "doc.md"}],
            duration_minutes=30,
        )
        assert len(items) == 1
        assert items[0]["title"] == "Nested Topic"
        assert items[0]["estimated_minutes"] == 15

    def test_bare_item_dict(self) -> None:
        reply = json.dumps(
            {"title": "Single Item", "source": "document", "minutes": 25}
        )
        items = parse_topics(
            reply,
            planned_points=[],
            documents=[{"filename": "doc.md"}],
            duration_minutes=30,
        )
        assert len(items) == 1
        assert items[0]["title"] == "Single Item"
        assert items[0]["estimated_minutes"] == 25

    def test_alternative_key_topics(self) -> None:
        reply = json.dumps(
            {
                "topics": [
                    {"title": "Topic Under Other Key", "source": "document", "minutes": 10}
                ]
            }
        )
        items = parse_topics(
            reply,
            planned_points=[],
            documents=[{"filename": "doc.md"}],
            duration_minutes=30,
        )
        assert len(items) == 1
        assert items[0]["title"] == "Topic Under Other Key"

    def test_bare_list(self) -> None:
        reply = json.dumps(
            [
                {"title": "List Topic 1", "source": "document", "minutes": 10},
                {"title": "List Topic 2", "source": "document", "minutes": 10},
            ]
        )
        items = parse_topics(
            reply,
            planned_points=[],
            documents=[{"filename": "doc.md"}],
            duration_minutes=30,
        )
        assert len(items) == 2
        assert items[0]["title"] == "List Topic 1"
        assert items[1]["title"] == "List Topic 2"

    def test_source_auto_assignment_when_only_one_source_present(self) -> None:
        # Case A: Only documents present -> force source to 'document'
        reply = json.dumps(
            {"items": [{"title": "Doc Topic", "source": "planned_point", "minutes": 10}]}
        )
        items = parse_topics(
            reply,
            planned_points=[],
            documents=[{"filename": "doc.md"}],
            duration_minutes=30,
        )
        assert items[0]["source"] == "document"

        # Case B: Only planned points present -> force source to 'planned_point'
        reply_b = json.dumps(
            {"items": [{"title": "Point Topic", "source": "document", "minutes": 10}]}
        )
        items_b = parse_topics(
            reply_b,
            planned_points=["Point Topic"],
            documents=[],
            duration_minutes=30,
        )
        assert items_b[0]["source"] == "planned_point"

    def test_time_scaling_when_total_exceeds_duration(self) -> None:
        # Meeting is 40 minutes, but items sum to 40 + 40 = 80 minutes
        reply = json.dumps(
            {
                "items": [
                    {"title": "Topic A", "source": "document", "minutes": 40},
                    {"title": "Topic B", "source": "document", "minutes": 40},
                ]
            }
        )
        items = parse_topics(
            reply,
            planned_points=[],
            documents=[{"filename": "doc.md"}],
            duration_minutes=40,
        )
        assert len(items) == 2
        # Scaled down proportionally: 40 * 40 // 80 = 20 minutes each
        assert items[0]["estimated_minutes"] == 20
        assert items[1]["estimated_minutes"] == 20
        assert sum(i["estimated_minutes"] for i in items) <= 40

    def test_invalid_json_raises_llm_call_error_422(self) -> None:
        with pytest.raises(LLMCallError) as exc_info:
            parse_topics(
                "Invalid garbage non-json response",
                planned_points=[],
                documents=[],
                duration_minutes=30,
            )
        assert exc_info.value.status == 422
        assert exc_info.value.code == "LLM_BAD_OUTPUT"
