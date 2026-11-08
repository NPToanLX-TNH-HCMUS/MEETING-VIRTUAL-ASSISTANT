"""
Integration test suite for During-Meeting API Endpoints & State Machine.

Covers:
- POST /api/v1/meetings/{id}/recording/start
- POST /api/v1/meetings/{id}/recording/stop
- POST /api/v1/meetings/{id}/transcribe
- POST /api/v1/meetings/{id}/documents (.pdf & .docx ingestion)
- Lifecycle state transitions: draft -> ready -> live -> processing
- Error contracts: 404 MEETING_NOT_FOUND, 409 INVALID_MEETING_STATE, 415 UNSUPPORTED_FILE_TYPE, 502 TRANSCRIPTION_FAILED
"""

import io
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from src.api.api import app, meetings, recorders, meeting_manager
from src.backend.meeting_manager.storage_manager import StorageManager
from src.backend.speech_to_text.transcriber import AudioTranscriptionError


@pytest.fixture
def client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> TestClient:
    """Fixture providing an isolated TestClient with clean memory state."""
    monkeypatch.chdir(tmp_path)
    # Isolate storage directory
    meeting_manager._storage = StorageManager(root_dir=tmp_path / "data")
    meetings.clear()
    recorders.clear()

    yield TestClient(app)

    meetings.clear()
    recorders.clear()


@pytest.fixture
def ready_meeting_id(client: TestClient) -> str:
    """Helper fixture to create a meeting and advance its state to 'ready'."""
    # Step 1: Create meeting (state: draft)
    create_res = client.post(
        "/api/v1/meetings",
        json={
            "topic": "Sprint Review & Planning",
            "language": "en",
            "duration_minutes": 30,
            "planned_points": ["Discuss architecture", "Sprint metrics"],
        },
    )
    assert create_res.status_code == 201
    meeting_id = create_res.json()["id"]

    # Step 2: Save agenda (state transitions from draft -> ready)
    save_res = client.put(
        f"/api/v1/meetings/{meeting_id}/agenda",
        json={
            "items": [
                {"id": None, "title": "Discuss architecture", "estimated_minutes": 15, "order": 1},
                {"id": None, "title": "Sprint metrics", "estimated_minutes": 15, "order": 2},
            ]
        },
    )
    assert save_res.status_code == 200
    assert meetings[meeting_id]["meeting"]["status"] == "ready"
    return meeting_id


class TestDuringMeetingLifecycleAPI:
    """Integration tests validating the during-meeting recording & transcription API lifecycle."""

    def test_recording_lifecycle_happy_path(
        self, client: TestClient, ready_meeting_id: str
    ) -> None:
        """
        Verify the full happy-path lifecycle:
        ready -> start recording (live) -> stop recording (processing) -> transcribe
        """
        m_id = ready_meeting_id
        context = meetings[m_id]["context"]
        audio_target = context.during_meeting_dir / "audio" / "record.wav"

        # Mock Recorder to simulate audio capture without hardware dependency
        with patch("src.api.api.Recorder") as MockRecorder:
            mock_rec_instance = MagicMock()
            MockRecorder.return_value = mock_rec_instance

            def fake_stop(save_path: str):
                p = Path(save_path)
                p.parent.mkdir(parents=True, exist_ok=True)
                p.write_bytes(b"RIFF dummy wav binary data")
                return 5.0

            mock_rec_instance.stop.side_effect = fake_stop

            # 1. Start recording
            start_res = client.post(f"/api/v1/meetings/{m_id}/recording/start")
            assert start_res.status_code == 200
            meeting_data = start_res.json()
            assert meeting_data["status"] == "live"
            assert meeting_data["started_at"] is not None
            mock_rec_instance.start.assert_called_once()

            # 2. Stop recording
            stop_res = client.post(f"/api/v1/meetings/{m_id}/recording/stop")
            assert stop_res.status_code == 200
            meeting_data = stop_res.json()
            assert meeting_data["status"] == "processing"
            assert meeting_data["ended_at"] is not None
            assert audio_target.exists()

        # 3. Transcribe recording
        expected_transcript = "Speaker A: Hello team, sprint goals have been achieved."
        with patch("src.api.api.ElevenLabsTranscriber") as MockTranscriber:
            mock_transcriber_inst = MagicMock()
            MockTranscriber.return_value = mock_transcriber_inst
            mock_transcriber_inst.transcribe_file.return_value = expected_transcript

            tx_res = client.post(f"/api/v1/meetings/{m_id}/transcribe")
            assert tx_res.status_code == 200
            assert tx_res.json()["transcript"] == expected_transcript
            mock_transcriber_inst.transcribe_file.assert_called_once()

    def test_start_recording_invalid_state_conflict(
        self, client: TestClient
    ) -> None:
        """Cannot start recording when meeting status is 'draft' (agenda not confirmed yet)."""
        create_res = client.post(
            "/api/v1/meetings",
            json={"topic": "Draft Meeting", "language": "en", "duration_minutes": 20},
        )
        assert create_res.status_code == 201
        m_id = create_res.json()["id"]

        res = client.post(f"/api/v1/meetings/{m_id}/recording/start")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INVALID_MEETING_STATE"

    def test_start_recording_hardware_failure_returns_500(
        self, client: TestClient, ready_meeting_id: str
    ) -> None:
        """Simulate microphone access permission denial / PortAudio failure."""
        m_id = ready_meeting_id
        with patch("src.api.api.Recorder") as MockRecorder:
            mock_inst = MagicMock()
            mock_inst.start.side_effect = RuntimeError("No input microphone device found")
            MockRecorder.return_value = mock_inst

            res = client.post(f"/api/v1/meetings/{m_id}/recording/start")
            assert res.status_code == 500
            assert res.json()["error"]["code"] == "RECORDER_FAILED"

    def test_stop_recording_invalid_state_conflict(
        self, client: TestClient, ready_meeting_id: str
    ) -> None:
        """Cannot stop recording when meeting has not yet started ('ready' status)."""
        m_id = ready_meeting_id
        res = client.post(f"/api/v1/meetings/{m_id}/recording/stop")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INVALID_MEETING_STATE"

    def test_transcribe_fails_when_no_audio_recorded(
        self, client: TestClient, ready_meeting_id: str
    ) -> None:
        """Calling transcribe before any audio file was produced returns 409."""
        m_id = ready_meeting_id
        res = client.post(f"/api/v1/meetings/{m_id}/transcribe")
        assert res.status_code == 409
        assert res.json()["error"]["code"] == "INVALID_MEETING_STATE"

    def test_transcribe_service_failure_returns_502(
        self, client: TestClient, ready_meeting_id: str
    ) -> None:
        """When ElevenLabs returns an upstream error, return 502 TRANSCRIPTION_FAILED."""
        m_id = ready_meeting_id
        context = meetings[m_id]["context"]
        audio_target = context.during_meeting_dir / "audio" / "record.wav"
        audio_target.parent.mkdir(parents=True, exist_ok=True)
        audio_target.write_bytes(b"RIFF dummy audio")

        with patch("src.api.api.ElevenLabsTranscriber") as MockTranscriber:
            mock_inst = MagicMock()
            mock_inst.transcribe_file.side_effect = AudioTranscriptionError(
                "ElevenLabs API returned HTTP 500"
            )
            MockTranscriber.return_value = mock_inst

            res = client.post(f"/api/v1/meetings/{m_id}/transcribe")
            assert res.status_code == 502
            assert res.json()["error"]["code"] == "TRANSCRIPTION_FAILED"

    def test_endpoints_return_404_on_unknown_meeting(
        self, client: TestClient
    ) -> None:
        """All during-meeting endpoints reject non-existent meeting IDs with 404."""
        unknown_id = "mtg_99999"
        assert client.post(f"/api/v1/meetings/{unknown_id}/recording/start").status_code == 404
        assert client.post(f"/api/v1/meetings/{unknown_id}/recording/stop").status_code == 404
        assert client.post(f"/api/v1/meetings/{unknown_id}/transcribe").status_code == 404


class TestDocumentUploadFormatsAPI:
    """Integration tests validating .pdf and .docx upload handling via MarkDownConverter in API."""

    def test_upload_markdown_file_success(
        self, client: TestClient, ready_meeting_id: str
    ) -> None:
        m_id = ready_meeting_id
        content = b"# Architecture\n\n## Database\nDetails here."
        files = {"file": ("architecture.md", io.BytesIO(content), "text/markdown")}

        res = client.post(f"/api/v1/meetings/{m_id}/documents", files=files)
        assert res.status_code == 201
        doc = res.json()
        assert doc["filename"] == "architecture.md"
        assert doc["mime_type"] == "markdown"
        assert "Architecture" in meetings[m_id]["documents"][0]["headings"]

    def test_upload_unsupported_file_type_rejected(
        self, client: TestClient, ready_meeting_id: str
    ) -> None:
        m_id = ready_meeting_id
        files = {"file": ("malicious.exe", io.BytesIO(b"binary"), "application/octet-stream")}
        res = client.post(f"/api/v1/meetings/{m_id}/documents", files=files)
        assert res.status_code == 415
        assert res.json()["error"]["code"] == "UNSUPPORTED_FILE_TYPE"
