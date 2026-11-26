"""API invariants and contract checks, including cases that expose current gaps.

The error-envelope expectation comes from api-contract.md §1.1; archived meetings
being read-only comes from §2. These remain failures until code/contract is reconciled.
"""

import copy
import json
from unittest.mock import Mock

import pytest
import requests

from src.backend.api import during_meeting, pre_meeting
from src.backend.utils import llm


@pytest.fixture
def meeting(client):
    response = client.post("/api/v1/meetings", json={
        "topic": "API review", "language": "en", "duration_minutes": 30,
        "planned_points": ["Review API"],
    })
    assert response.status_code == 201
    return response.json()


def endpoint(meeting):
    return f"/api/v1/meetings/{meeting['id']}"


@pytest.fixture
def provider(monkeypatch):
    post = Mock()
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm, "sleep", Mock())
    monkeypatch.setattr(llm, "load_dotenv", lambda *args, **kwargs: None)
    monkeypatch.setenv("GROQ_API_KEY", "integration-primary")
    monkeypatch.setenv("OPENROUTER_API_KEY", "integration-fallback")
    return post


def llm_response(items):
    response = Mock(spec=requests.Response)
    response.ok = True
    response.json.return_value = {"choices": [{
        "message": {"content": json.dumps({"items": items})}, "finish_reason": "stop",
    }]}
    return response


@pytest.mark.parametrize("duration", [1, 480])
def test_meeting_duration_accepts_documented_boundaries(client, duration):
    response = client.post("/api/v1/meetings", json={
        "topic": "Review", "language": "en", "duration_minutes": duration,
    })
    assert response.status_code == 201
    assert response.json()["duration_minutes"] == duration


def test_invalid_input_follows_documented_error_contract(client):
    response = client.post("/api/v1/meetings", json={
        "topic": "Review", "language": "en", "duration_minutes": 0,
    })
    assert response.status_code == 400  # Contract §1.1, not FastAPI's default response.
    assert response.json()["error"]["code"] == "VALIDATION_ERROR"


def test_agenda_runs_real_extraction_validation_and_selection(client, meeting, provider):
    uploaded = client.post(endpoint(meeting) + "/documents", files={
        "file": ("notes.md", b"# Budget\nReview the budget."),
    })
    assert uploaded.status_code == 201
    provider.return_value = llm_response([
        {"title": "Review API", "source": "planned_point", "minutes": 20},
        {"title": "Budget", "source": "document", "minutes": 20},
    ])
    response = client.post(endpoint(meeting) + "/agenda/generate")
    assert response.status_code == 200
    body = response.json()
    assert [i["title"] for i in body["items"]] == ["Review API", "Budget"]
    assert [i["source"] for i in body["items"]] == ["planned_point", "document"]
    assert body["total_estimated_minutes"] == 30
    assert all(i["needs_confirmation"] for i in body["items"])
    assert client.get(endpoint(meeting)).json()["status"] == "draft"
    assert client.get(endpoint(meeting) + "/agenda").json()["items"] == body["items"]
    provider.assert_called_once()


def test_missing_estimate_uses_default_without_exceeding_api_budget(client, meeting, provider):
    provider.return_value = llm_response([
        {"title": "API", "source": "planned_point", "minutes": None},
    ])
    response = client.post(endpoint(meeting) + "/agenda/generate")
    assert response.status_code == 200
    body = response.json()
    assert body["items"][0]["estimated_minutes"] > 0
    assert body["total_estimated_minutes"] <= meeting["duration_minutes"]


@pytest.mark.parametrize("fault, status, code", [
    ("outage", 503, "LLM_UNAVAILABLE"), ("bad_schema", 422, "LLM_BAD_OUTPUT"),
])
def test_generation_failure_preserves_existing_confirmed_agenda(client, meeting, provider, fault, status, code):
    response = client.put(endpoint(meeting) + "/agenda", json={"items": [
        {"title": "Keep this agenda", "estimated_minutes": 10, "order": 1},
    ]})
    assert response.status_code == 200
    session = client.app.state.ctx.session(meeting["id"])
    before = copy.deepcopy(session.at("agenda"))
    if fault == "outage":
        provider.side_effect = requests.Timeout("provider timeout")
    else:
        provider.return_value = llm_response([{"title": "Missing required fields"}])
    failed = client.post(endpoint(meeting) + "/agenda/generate")
    assert (failed.status_code, failed.json()["error"]["code"]) == (status, code)
    assert session.status == "ready"
    assert session.at("agenda") == before
    assert provider.call_count == 3


@pytest.mark.parametrize("state", ["live", "paused", "processing", "review", "archived"])
def test_agenda_cannot_change_after_recording_starts(client, meeting, monkeypatch, state):
    session = client.app.state.ctx.session(meeting["id"])
    session.status = state
    extract = Mock()
    monkeypatch.setattr(pre_meeting, "extract_topics", extract)
    generated = client.post(endpoint(meeting) + "/agenda/generate")
    saved = client.put(endpoint(meeting) + "/agenda", json={"items": []})
    assert generated.status_code == saved.status_code == 409
    assert generated.json()["error"]["code"] == "INVALID_MEETING_STATE"
    assert session.status == state
    extract.assert_not_called()


def test_state_change_during_slow_generation_is_not_overwritten(client, meeting, monkeypatch):
    session = client.app.state.ctx.session(meeting["id"])

    def delayed_result(**kwargs):
        with session:
            session.status = "live"
        return []

    monkeypatch.setattr(pre_meeting, "extract_topics", delayed_result)
    response = client.post(endpoint(meeting) + "/agenda/generate")
    assert response.status_code == 409
    assert session.status == "live"
    assert session.at("agenda") == []


def test_greedy_selection_continues_after_an_oversized_candidate():
    chosen, dropped = pre_meeting.select_by_time([
        {"title": "Long", "estimated_minutes": 31},
        {"title": "Exact fit", "estimated_minutes": 30},
    ], 30)
    assert [item["title"] for item in chosen] == ["Exact fit"]
    assert dropped == [{"title": "Long", "estimated_minutes": 31, "reason": "exceeds_remaining_time"}]


def test_manual_ids_are_unique_after_deleting_and_adding_items(client, meeting):
    path = endpoint(meeting) + "/agenda"
    first = client.put(path, json={"items": [
        {"title": "A", "estimated_minutes": 5, "order": 1},
        {"title": "B", "estimated_minutes": 5, "order": 2},
    ]})
    assert first.status_code == 200
    retained_id = first.json()["items"][1]["id"]
    second = client.put(path, json={"items": [
        {"id": retained_id, "title": "B", "estimated_minutes": 5, "order": 1},
        {"title": "C", "estimated_minutes": 5, "order": 2},
    ]})
    assert second.status_code == 200
    ids = [i["id"] for i in second.json()["items"]]
    assert len(ids) == len(set(ids)), f"Duplicate agenda IDs: {ids}"


def test_archived_meeting_is_read_only_for_document_upload(client, meeting):
    # §2 explicitly defines archived as read-only, even if a client bypasses the UI.
    session = client.app.state.ctx.session(meeting["id"])
    session.status = "archived"
    response = client.post(endpoint(meeting) + "/documents", files={"file": ("late.txt", b"late change")})
    assert response.status_code == 409
    assert session.at("documents") == []


def test_upload_exact_size_limit_and_one_byte_over(client, meeting, monkeypatch):
    # Exercise the byte boundary cheaply without allocating a 10 MB fixture per run.
    monkeypatch.setattr(pre_meeting, "MAX_FILE_BYTES", 5)
    accepted = client.post(endpoint(meeting) + "/documents", files={"file": ("ok.txt", b"12345")})
    rejected = client.post(endpoint(meeting) + "/documents", files={"file": ("too-big.txt", b"123456")})
    assert accepted.status_code == 201
    assert rejected.status_code == 413
    assert rejected.json()["error"]["code"] == "FILE_TOO_LARGE"
    assert len(client.app.state.ctx.session(meeting["id"]).at("documents")) == 1


def test_bad_pdf_conversion_does_not_add_a_document(client, meeting, monkeypatch):
    engine = client.app.state.ctx.converter._converter
    monkeypatch.setattr(engine, "convert", Mock(side_effect=ValueError("corrupt PDF")))
    response = client.post(endpoint(meeting) + "/documents", files={"file": ("bad.pdf", b"corrupt PDF")})
    assert response.status_code == 415
    assert client.app.state.ctx.session(meeting["id"]).at("documents") == []


def test_two_batch_meetings_cannot_share_one_microphone(client, meeting, monkeypatch):
    class FakeRecorder:
        is_recording = False

        def start(self):
            self.is_recording = True

        def stop(self, path):
            self.is_recording = False

    monkeypatch.setattr(during_meeting, "Recorder", FakeRecorder)
    other = client.post("/api/v1/meetings", json={
        "topic": "Other", "language": "en", "duration_minutes": 30,
    }).json()
    for item in (meeting, other):
        client.app.state.ctx.session(item["id"]).status = "ready"
    assert client.post(endpoint(meeting) + "/recording/start").status_code == 200
    assert client.post(endpoint(other) + "/recording/start").status_code == 409
