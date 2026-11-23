"""Real routes and lifecycle, fake microphone/LLM, isolated temporary meeting data."""
import asyncio
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi.testclient import TestClient
from src.backend import main as backend
from src.backend.api import during_meeting, post_meeting
from src.backend.context.app_context import AppContext
from src.backend.utils.objects import MinutesExtraction
from src.backend.during_meeting import meeting_service
from src.backend.during_meeting.meeting_session import MeetingSession
from src.backend.meeting_manager.meeting_manager import MeetingManager
from src.backend.meeting_manager.storage_manager import StorageManager


class MeetingContractTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.old_ctx = backend.app.state.ctx
        backend.app.state.ctx = AppContext(Path(self.directory.name))
        during_meeting.microphone_lock = asyncio.Lock()
        self.emit = None
        self.capture_closed = False
        self.capture_max_seconds = None

        async def capture(send_event, language, stop_event, pause_event, audio_path, max_seconds):
            self.emit = send_event
            self.capture_max_seconds = max_seconds
            await send_event({"type": "ready"})
            await send_event({"type": "committed", "text": "Before websocket."})
            paused = False
            try:
                while not stop_event.is_set():
                    if paused != pause_event.is_set():
                        paused = pause_event.is_set()
                        await send_event({"type": "paused" if paused else "resumed"})
                    await asyncio.sleep(0.005)
                await send_event({"type": "stopping"})
                await send_event({"type": "committed", "text": "Final sentence."})
                return "Before websocket.\nFinal sentence."
            finally:
                self.capture_closed = True

        self.capture = patch.object(meeting_service, "stream_transcript", capture)
        self.extraction = patch.object(post_meeting, "extract_minutes", return_value=MinutesExtraction(
            summary="Meeting summary.", decisions=[], action_items=[], unresolved_issues=[]))
        self.capture.start()
        self.extract_mock = self.extraction.start()
        self.client = TestClient(backend.app)
        self.client.__enter__()
        response = self.client.post("/api/v1/meetings", json={
            "topic": "Offline meeting", "language": "vi", "duration_minutes": 2,
            "planned_points": [],
        })
        self.meeting_id = response.json()["id"]
        backend.app.state.ctx.session(self.meeting_id).status = "ready"
        self.base = f"/api/v1/meetings/{self.meeting_id}"

    def tearDown(self):
        if self.client is not None:
            self.client.__exit__(None, None, None)
        self.capture.stop()
        backend.app.state.ctx = self.old_ctx
        self.extraction.stop()
        self.directory.cleanup()

    def command(self, action):
        return self.client.post(f"{self.base}/{action}")

    def wait_for_minutes(self):
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            state = self.client.get(f"{self.base}/state").json()
            if state["minutes_ready"]:
                return state
            time.sleep(0.01)
        self.fail("Minutes did not become ready")

    def test_rest_controls_reconnect_and_final_output(self):
        self.assertEqual(self.command("pause").status_code, 409)
        started = self.command("start")
        self.assertEqual(started.status_code, 200, started.text)
        self.assertEqual(started.json()["status"], "live")
        self.assertEqual(self.capture_max_seconds, 120)
        self.assertEqual(self.command("start").json()["error"]["code"], "INVALID_MEETING_STATE")
        initial = self.client.get(f"{self.base}/transcript").json()["segments"]
        self.assertEqual(len(initial), 1)
        self.assertIsNone(initial[0]["confidence"])
        cursor = initial[0]["id"]
        path = f"/ws/meetings/{self.meeting_id}"
        with self.client.websocket_connect(path) as ws:
            # WebSocket commands are ignored.
            ws.send_json({"type": "stop"})
            self.client.portal.call(self.emit, {"type": "committed", "text": "During connection."})
            event = ws.receive_json()
            self.assertEqual(event["type"], "transcript.segment")
            self.assertEqual(set(event), {"type", "meeting_id", "seq", "at", "data"})
            last_seq = event["seq"]
        self.assertFalse(self.capture_closed)
        self.assertEqual(self.client.get(f"{self.base}/state").json()["status"], "live")
        self.client.portal.call(self.emit, {"type": "committed", "text": "While disconnected."})
        with self.client.websocket_connect(path) as ws:
            missed = self.client.get(f"{self.base}/transcript", params={"after": cursor}).json()["segments"]
            self.assertEqual([s["text"] for s in missed], [
                "During connection.", "While disconnected."])
            self.client.portal.call(self.emit, {"type": "committed", "text": "After reconnect."})
            event = ws.receive_json()
            self.assertGreater(event["seq"], last_seq)
        self.assertEqual(self.client.get(f"{self.base}/transcript?after=unknown").status_code, 400)
        paused = self.command("pause").json()
        self.assertEqual(paused["status"], "paused")
        elapsed = self.client.get(f"{self.base}/state").json()["elapsed_seconds"]
        time.sleep(0.04)
        self.assertEqual(self.client.get(f"{self.base}/state").json()["elapsed_seconds"], elapsed)
        self.assertEqual(self.command("pause").status_code, 409)
        self.assertEqual(self.command("resume").json()["status"], "live")
        self.assertEqual(self.command("resume").status_code, 409)
        self.assertEqual(self.command("stop").json()["status"], "processing")
        self.wait_for_minutes()
        self.assertEqual(self.command("stop").status_code, 409)
        self.assertTrue(self.capture_closed)
        self.assertFalse(during_meeting.microphone_lock.locked())
        self.assertEqual(self.extract_mock.call_count, 1)
        self.client.post(f"{self.base}/minutes/generate")
        self.assertEqual(self.extract_mock.call_count, 1)
        context = backend.app.state.ctx.session(self.meeting_id)
        self.assertIn("Final sentence.", (
            context.path("during_meeting/transcript/transcript.txt")).read_text())
        self.assertTrue((context.path("post_meeting/summary/final_summary.md")).exists())
        routes = [route.path for route in during_meeting.ws_router.routes]
        self.assertNotIn(f"/ws/meetings/{{meeting_id}}/transcript-test", routes)

    def test_summary_history_survives_viewer_reload(self):
        with patch.object(meeting_service, "SUMMARY_INTERVAL_SECONDS", 0.02), \
                patch.object(meeting_service, "summarize_live", return_value="Cumulative summary"):
            self.command("start")
            deadline = time.monotonic() + 3
            history = []
            while time.monotonic() < deadline:
                history = self.client.get(f"{self.base}/summaries").json()["items"]
                if history:
                    break
                time.sleep(0.01)
            self.assertEqual(history[0]["revision"], 1)
            self.assertEqual(history[0]["text"], "Cumulative summary")
            self.assertEqual(self.client.get(f"{self.base}/summaries").json()["items"], history)
            self.command("stop")
            self.wait_for_minutes()

    def test_minutes_failure_allows_retry(self):
        self.extract_mock.side_effect = RuntimeError("Offline LLM failure")
        self.command("start")
        self.command("stop")
        deadline = time.monotonic() + 3
        state = {}
        while time.monotonic() < deadline:
            state = self.client.get(f"{self.base}/state").json()
            if state["error"]:
                break
            time.sleep(0.01)
        self.assertTrue(state["error"]["recoverable"])
        self.assertTrue(state["transcript_saved"])
        self.assertEqual(state["status"], "processing")
        self.extract_mock.side_effect = None
        self.assertEqual(self.client.post(f"{self.base}/minutes/generate").status_code, 200)
        self.assertIsNone(self.wait_for_minutes()["error"])

    def test_missing_draft_busy_and_stop_while_paused(self):
        self.assertEqual(self.client.post("/api/v1/meetings/missing/start").status_code, 404)
        meeting = backend.app.state.ctx.session(self.meeting_id)
        meeting.status = "draft"
        self.assertEqual(self.command("start").status_code, 409)
        meeting.status = "ready"
        self.command("start")
        other = self.client.post("/api/v1/meetings", json={
            "topic": "Other", "language": "vi", "duration_minutes": 1}).json()["id"]
        backend.app.state.ctx.session(other).status = "ready"
        busy = self.client.post(f"/api/v1/meetings/{other}/start")
        self.assertEqual(busy.json()["error"]["code"], "RECORDING_ALREADY_ACTIVE")
        self.command("pause")
        self.assertEqual(self.command("stop").json()["status"], "processing")
        self.wait_for_minutes()

    def test_start_failure_releases_microphone(self):
        async def fail(**kwargs):
            raise RuntimeError("Offline startup failure")
        with patch.object(meeting_service, "stream_transcript", fail):
            self.assertEqual(self.command("start").status_code, 503)
        self.assertFalse(during_meeting.microphone_lock.locked())
        self.assertEqual(self.client.get(f"{self.base}/state").json()["status"], "ready")
        self.assertEqual(self.command("start").status_code, 200)
        self.command("stop")
        self.wait_for_minutes()

    def test_shutdown_releases_active_microphone(self):
        self.assertEqual(self.command("start").status_code, 200)
        self.client.__exit__(None, None, None)
        self.client = None
        self.assertTrue(self.capture_closed)
        self.assertFalse(during_meeting.microphone_lock.locked())


class SessionQueueTests(unittest.IsolatedAsyncioTestCase):
    async def test_slow_viewer_does_not_block_other_viewers(self):
        session = MeetingSession("meeting")
        slow = session.subscribe()
        fast = session.subscribe()
        for number in range(201):
            await session.publish("timer.sync", {"elapsed_seconds": number})
            event = fast.get_nowait()
            self.assertEqual(event["seq"], number + 1)
        self.assertIsNone(slow.get_nowait())
        self.assertNotIn(slow, session.subscribers)
        self.assertIn(fast, session.subscribers)
