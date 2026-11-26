"""Agenda tests use hand-written provider replies, not the function's own output as truth."""

import json
from unittest.mock import Mock

import pytest

from src.backend.agenda_extractor import agenda_extractor as agenda
from src.backend.utils.json_handler import parse_topics
from src.backend.utils.llm import LLMCallError


def test_empty_inputs_do_not_call_llm(monkeypatch):
    call = Mock()
    monkeypatch.setattr(agenda, "call_llm", call)
    assert agenda.extract_topics([], []) == []
    call.assert_not_called()


def test_prompt_preserves_both_input_sources_and_topic():
    prompt = agenda.build_prompt(["API review"], [{"filename": "notes.md", "text": "Đánh giá API"}], "Sprint")
    assert "<meeting_topic>\nSprint\n</meeting_topic>" in prompt
    assert "- API review" in prompt
    assert '<document filename="notes.md">\nĐánh giá API\n</document>' in prompt


def test_valid_reply_uses_schema_and_keeps_source_information(monkeypatch):
    call = Mock(return_value=json.dumps({"items": [
        {"title": " API review ", "source": "planned_point", "minutes": 10},
        {"title": "Budget", "source": "document", "minutes": 5},
    ]}))
    monkeypatch.setattr(agenda, "call_llm", call)
    result = agenda.extract_topics(["API review"], [{"filename": "notes.md", "text": "Budget"}], 30)
    assert [(i["title"], i["source"], i["estimated_minutes"]) for i in result] == [
        ("API review", "planned_point", 10), ("Budget", "document", 5),
    ]
    assert call.call_args.kwargs["_schema"] == agenda.AGENDA_SCHEMA


@pytest.mark.parametrize("reply", ["garbage", '{"items": [{"title": "API"}]}'])
def test_bad_model_reply_is_reported_as_bad_output(monkeypatch, reply):
    monkeypatch.setattr(agenda, "call_llm", Mock(return_value=reply))
    with pytest.raises(LLMCallError) as caught:
        agenda.extract_topics(["API"], [])
    assert (caught.value.status, caught.value.code) == (422, "LLM_BAD_OUTPUT")


def test_outage_is_propagated_instead_of_inventing_an_agenda(monkeypatch):
    monkeypatch.setattr(agenda, "call_llm", Mock(side_effect=LLMCallError(503, "LLM_UNAVAILABLE", "outage")))
    with pytest.raises(LLMCallError) as caught:
        agenda.extract_topics(["API"], [])
    assert caught.value.code == "LLM_UNAVAILABLE"


def test_blank_titles_are_not_agenda_items():
    reply = json.dumps({"items": [
        {"title": " \t", "source": "document", "minutes": 10},
        {"title": "API", "source": "document", "minutes": 5},
    ]})
    assert [i["title"] for i in parse_topics(reply, [], [{"filename": "notes.md"}], 30)] == ["API"]


def test_time_normalization_cannot_exceed_budget_when_topics_outnumber_minutes():
    # The prompt requires total <= duration. max(1, scaled_time) can break that promise.
    reply = json.dumps({"items": [
        {"title": "API", "source": "document", "minutes": 1},
        {"title": "Budget", "source": "document", "minutes": 1},
    ]})
    items = parse_topics(reply, [], [{"filename": "notes.md"}], 1)
    assert sum(i["estimated_minutes"] or 0 for i in items) <= 1
