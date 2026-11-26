"""Exercise the real WebSocket state machine; only the STT/audio stream is replaced."""

import asyncio
import threading
from unittest.mock import AsyncMock, Mock

import pytest
from starlette.websockets import WebSocketDisconnect

from src.backend.api import during_meeting


@pytest.fixture
def meeting(client):
    response = client.post("/api/v1/meetings", json={
        "topic": "Socket review", "language": "en", "duration_minutes": 30,
    })
    assert response.status_code == 201
    session = client.app.state.ctx.session(response.json()["id"])
    session.status = "ready"
    return session


def socket_path(meeting_id):
    return f"/ws/meetings/{meeting_id}/transcript-test"


def assert_server_closed(socket):
    # Await the server's close frame before TestClient cancels its ASGI task.
    # Exiting the context immediately can interrupt the handler's cleanup.
    with pytest.raises(WebSocketDisconnect):
        socket.receive_json()


def assert_rejected(client, meeting_id):
    with client.websocket_connect(socket_path(meeting_id)) as socket:
        assert socket.receive_json()["type"] == "error"
        with pytest.raises(WebSocketDisconnect) as caught:
            socket.receive_json()
        assert caught.value.code == 1008


def test_unknown_meeting_is_rejected_without_starting_stream(client, monkeypatch):
    stream = AsyncMock()
    monkeypatch.setattr(during_meeting, "stream_transcript", stream)
    assert_rejected(client, "missing-meeting")
    stream.assert_not_awaited()


@pytest.mark.parametrize("state", ["draft", "live", "paused", "processing", "review", "archived"])
def test_only_ready_meeting_can_open_stream(client, meeting, monkeypatch, state):
    meeting.status = state
    stream = AsyncMock()
    monkeypatch.setattr(during_meeting, "stream_transcript", stream)
    assert_rejected(client, meeting.id)
    assert meeting.status == state
    stream.assert_not_awaited()


def test_batch_recorder_blocks_realtime_stream(client, meeting, monkeypatch):
    other = client.app.state.ctx.create_session()
    other.emplace("recorder", Mock(is_recording=False))
    stream = AsyncMock()
    monkeypatch.setattr(during_meeting, "stream_transcript", stream)
    assert_rejected(client, meeting.id)
    stream.assert_not_awaited()


def test_completed_stream_saves_unicode_transcript_and_finishes_meeting(client, meeting, monkeypatch):
    async def stream(*, send_event, language, stop_event, pause_event, audio_path):
        assert language == "en"
        assert not stop_event.is_set() and not pause_event.is_set()
        assert audio_path.name == "record.wav"
        await send_event({"type": "ready"})
        await send_event({"type": "committed", "text": "Thống nhất triển khai API."})
        return "  Thống nhất triển khai API.\n"

    monkeypatch.setattr(during_meeting, "stream_transcript", stream)
    with client.websocket_connect(socket_path(meeting.id)) as socket:
        assert socket.receive_json()["type"] == "ready"
        assert socket.receive_json()["type"] == "committed"
        done = socket.receive_json()
        assert done == {"type": "done", "saved": True, "has_text": True,
                        "transcript": "Thống nhất triển khai API."}
        assert_server_closed(socket)
    assert meeting.status == "processing"
    assert meeting.path(during_meeting.TRANSCRIPT_FILE).read_text(encoding="utf-8") == done["transcript"]
    assert meeting.at("meeting")["started_at"] is not None
    assert meeting.at("meeting")["ended_at"] is not None
    assert not during_meeting.transcript_test_lock.locked()


@pytest.mark.parametrize("failure", ["provider_error", "empty_transcript"])
def test_failed_stream_restores_ready_state_without_saved_transcript(client, meeting, monkeypatch, failure):
    async def stream(**kwargs):
        if failure == "provider_error":
            raise RuntimeError("provider disconnected")
        return " \t\n"

    monkeypatch.setattr(during_meeting, "stream_transcript", stream)
    with client.websocket_connect(socket_path(meeting.id)) as socket:
        error = socket.receive_json()
        assert error["type"] == "error"
        assert error["message"]
        assert_server_closed(socket)
    assert meeting.status == "ready"
    assert meeting.at("meeting")["started_at"] is None
    assert meeting.at("meeting")["ended_at"] is None
    assert not meeting.path(during_meeting.TRANSCRIPT_FILE).exists()
    assert not during_meeting.transcript_test_lock.locked()


def test_client_disconnect_cancels_stream_and_releases_microphone(client, meeting, monkeypatch):
    cancelled = threading.Event()

    async def stream(*, send_event, **kwargs):
        try:
            await send_event({"type": "ready"})
            await asyncio.Event().wait()
        finally:
            cancelled.set()

    monkeypatch.setattr(during_meeting, "stream_transcript", stream)
    with client.websocket_connect(socket_path(meeting.id)) as socket:
        assert socket.receive_json()["type"] == "ready"
        socket.close()
        assert_server_closed(socket)
    assert cancelled.wait(timeout=2), "Disconnected client left the provider task running"
    assert meeting.status == "ready"
    assert meeting.at("meeting")["started_at"] is None
    assert not during_meeting.transcript_test_lock.locked()


def test_pause_resume_stop_commands_and_malformed_messages(client, meeting, monkeypatch):
    async def stream(*, send_event, stop_event, pause_event, **kwargs):
        await send_event({"type": "ready"})
        await asyncio.wait_for(pause_event.wait(), timeout=5)
        await send_event({"type": "paused"})

        async def wait_for_resume():
            while pause_event.is_set():
                await asyncio.sleep(0.001)

        await asyncio.wait_for(wait_for_resume(), timeout=5)
        await send_event({"type": "resumed"})
        await asyncio.wait_for(stop_event.wait(), timeout=5)
        return "Confirmed after resume."

    monkeypatch.setattr(during_meeting, "stream_transcript", stream)
    with client.websocket_connect(socket_path(meeting.id)) as socket:
        assert socket.receive_json()["type"] == "ready"
        socket.send_text("not json")
        socket.send_json(["pause"])
        socket.send_json({"type": "pause"})
        assert socket.receive_json()["type"] == "paused"
        assert meeting.status == "paused"
        socket.send_json({"type": "resume"})
        assert socket.receive_json()["type"] == "resumed"
        assert meeting.status == "live"
        socket.send_json({"type": "stop"})
        assert socket.receive_json()["type"] == "done"
        assert_server_closed(socket)
    assert meeting.status == "processing"
    assert not during_meeting.transcript_test_lock.locked()


def test_recording_level_without_active_microphone_is_silent(client, meeting):
    response = client.get(f"/api/v1/meetings/{meeting.id}/recording/level")
    assert response.status_code == 200
    assert response.json() == {"level": 0, "dbfs": -60}
