"""
tests/integration/test_post_meeting_minutes_api.py
==================================================
Integration test suite for Post-Meeting Stage 3 API lifecycle:
- POST /api/v1/meetings/{id}/minutes/generate
- GET  /api/v1/meetings/{id}/minutes
- PUT  /api/v1/meetings/{id}/minutes
- POST /api/v1/meetings/{id}/minutes/confirm

Verifies finite state machine transitions (processing -> review -> archived),
disk persistence of minutes_draft.md and minutes_final.md, and error status guards.
"""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

from src.api.api import app, meetings, recorders, meeting_manager
from src.backend.meeting_manager.storage_manager import StorageManager


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    monkeypatch.chdir(tmp_path)
    meeting_manager._storage = StorageManager(root_dir=tmp_path / "data")
    meetings.clear()
    recorders.clear()

    yield TestClient(app)

    meetings.clear()
    recorders.clear()


@pytest.fixture
def processing_meeting(client: TestClient) -> str:
    """
    Creates a meeting, moves it to 'processing' state, and seeds a valid transcript.txt.
    """
    res = client.post(
        "/api/v1/meetings",
        json={
            "topic": "Quarterly Budget Sync",
            "language": "en",
            "duration_minutes": 30,
            "planned_points": ["Budget allocations", "Cloud infrastructure"],
        },
    )
    assert res.status_code == 201
    meeting_id = res.json()["id"]

    # Save agenda to transition from 'draft' -> 'ready'
    save_res = client.put(
        f"/api/v1/meetings/{meeting_id}/agenda",
        json={
            "items": [
                {"id": None, "title": "Budget allocations", "estimated_minutes": 15, "order": 1},
                {"id": None, "title": "Cloud infrastructure", "estimated_minutes": 15, "order": 2},
            ]
        },
    )
    assert save_res.status_code == 200
    assert meetings[meeting_id]["meeting"]["status"] == "ready"

    # Start recording
    res_start = client.post(f"/api/v1/meetings/{meeting_id}/recording/start")
    assert res_start.status_code == 200

    # Stop recording -> transitions meeting to 'processing'
    res_stop = client.post(f"/api/v1/meetings/{meeting_id}/recording/stop")
    assert res_stop.status_code == 200
    assert meetings[meeting_id]["meeting"]["status"] == "processing"

    # Seed transcript.txt into during_meeting directory
    stored = meetings[meeting_id]
    transcript_file = stored["context"].during_meeting_dir / "transcript" / "transcript.txt"
    transcript_file.parent.mkdir(parents=True, exist_ok=True)
    transcript_file.write_text(
        "Leader: We agreed to approve $50,000 for cloud servers.\n"
        "Alex: I will configure the AWS clusters by Friday.\n",
        encoding="utf-8",
    )

    return meeting_id


class TestPostMeetingMinutesLifecycleAPI:
    """Integration tests for minutes generation, editing, retrieval, and confirmation."""

    def test_minutes_lifecycle_complete_happy_path(self, client: TestClient, processing_meeting: str):
        meeting_id = processing_meeting

        # 1. Verify reading minutes before generation returns 409 MINUTES_NOT_READY
        res_pre = client.get(f"/api/v1/meetings/{meeting_id}/minutes")
        assert res_pre.status_code == 409
        assert res_pre.json()["error"]["code"] == "MINUTES_NOT_READY"

        # Mock LLM generation output
        mock_extraction = {
            "summary": "Team approved $50k budget for cloud servers.",
            "decisions": ["Approved $50,000 for cloud servers"],
            "action_items": [
                {
                    "task": "Configure AWS clusters",
                    "assignee": "Alex",
                    "due": "2026-11-13",
                    "quote": "Alex: I will configure the AWS clusters by Friday.",
                }
            ],
            "unresolved_issues": [],
        }

        # 2. Call POST .../minutes/generate
        with patch(
            "src.backend.minutes_extractor.minutes_extractor.call_llm",
            return_value=json.dumps(mock_extraction),
        ):
            res_gen = client.post(f"/api/v1/meetings/{meeting_id}/minutes/generate")
            assert res_gen.status_code == 200
            data = res_gen.json()

            assert data["meeting_id"] == meeting_id
            assert data["status"] == "draft"
            assert data["summary"] == mock_extraction["summary"]
            assert len(data["action_items"]) == 1
            assert data["action_items"][0]["assignee"] == "Alex"
            assert "## Summary" in data["markdown"]

            # Verify state transition to 'review'
            assert meetings[meeting_id]["meeting"]["status"] == "review"

            # Verify minutes_draft.md written to disk
            draft_path = (
                meetings[meeting_id]["context"].post_meeting_dir
                / "meeting_minutes"
                / "minutes_draft.md"
            )
            assert draft_path.is_file()
            assert draft_path.read_text(encoding="utf-8") == data["markdown"]

        # 3. Call GET .../minutes -> returns the generated draft
        res_get = client.get(f"/api/v1/meetings/{meeting_id}/minutes")
        assert res_get.status_code == 200
        assert res_get.json()["meeting_id"] == meeting_id

        # 4. Call PUT .../minutes -> user edits the markdown draft
        custom_md = "# Revised Minutes\nUser made changes to the draft."
        res_put = client.put(
            f"/api/v1/meetings/{meeting_id}/minutes",
            json={"markdown": custom_md},
        )
        assert res_put.status_code == 200
        assert res_put.json()["markdown"] == custom_md
        assert meetings[meeting_id]["minutes"]["markdown"] == custom_md

        # 5. Call POST .../minutes/confirm -> transitions to 'archived'
        res_confirm = client.post(f"/api/v1/meetings/{meeting_id}/minutes/confirm")
        assert res_confirm.status_code == 200
        assert res_confirm.json()["status"] == "archived"
        assert meetings[meeting_id]["meeting"]["status"] == "archived"

        # Verify minutes_final.md saved to disk
        final_path = (
            meetings[meeting_id]["context"].post_meeting_dir
            / "meeting_minutes"
            / "minutes_final.md"
        )
        assert final_path.is_file()
        assert final_path.read_text(encoding="utf-8") == custom_md

    def test_generate_minutes_fails_when_no_transcript(self, client: TestClient):
        """Calling generate without transcript returns 409 TRANSCRIPT_NOT_FOUND."""
        res = client.post(
            "/api/v1/meetings",
            json={
                "topic": "Empty Sync",
                "language": "en",
                "duration_minutes": 15,
                "planned_points": ["Topic 1"],
            },
        )
        assert res.status_code == 201
        meeting_id = res.json()["id"]

        # Force state to 'processing' without creating transcript file
        meetings[meeting_id]["meeting"]["status"] = "processing"

        res_gen = client.post(f"/api/v1/meetings/{meeting_id}/minutes/generate")
        assert res_gen.status_code == 409
        assert res_gen.json()["error"]["code"] == "TRANSCRIPT_NOT_FOUND"

    def test_generate_minutes_rejected_in_invalid_state(self, client: TestClient):
        """Calling generate when meeting is in 'draft' status returns 409 INVALID_MEETING_STATE."""
        res = client.post(
            "/api/v1/meetings",
            json={
                "topic": "State Guard Sync",
                "language": "en",
                "duration_minutes": 15,
                "planned_points": ["Topic 1"],
            },
        )
        assert res.status_code == 201
        meeting_id = res.json()["id"]

        res_gen = client.post(f"/api/v1/meetings/{meeting_id}/minutes/generate")
        assert res_gen.status_code == 409
        assert res_gen.json()["error"]["code"] == "INVALID_MEETING_STATE"

    def test_update_minutes_rejected_when_not_in_review(self, client: TestClient):
        """Calling PUT minutes while meeting is not in 'review' returns 409 INVALID_MEETING_STATE."""
        res = client.post(
            "/api/v1/meetings",
            json={
                "topic": "Edit Guard Sync",
                "language": "en",
                "duration_minutes": 15,
                "planned_points": ["Topic 1"],
            },
        )
        assert res.status_code == 201
        meeting_id = res.json()["id"]

        res_put = client.put(
            f"/api/v1/meetings/{meeting_id}/minutes",
            json={"markdown": "Illegal edit attempt"},
        )
        assert res_put.status_code == 409
        assert res_put.json()["error"]["code"] == "INVALID_MEETING_STATE"

    def test_confirm_minutes_rejected_when_not_in_review(self, client: TestClient):
        """Calling confirm while meeting is in 'draft' returns 409 INVALID_MEETING_STATE."""
        res = client.post(
            "/api/v1/meetings",
            json={
                "topic": "Confirm Guard Sync",
                "language": "en",
                "duration_minutes": 15,
                "planned_points": ["Topic 1"],
            },
        )
        assert res.status_code == 201
        meeting_id = res.json()["id"]

        res_conf = client.post(f"/api/v1/meetings/{meeting_id}/minutes/confirm")
        assert res_conf.status_code == 409
        assert res_conf.json()["error"]["code"] == "INVALID_MEETING_STATE"
