"""Confirmed minutes survive a restart, can be edited, and can be filed in workspaces (no network, no LLM)."""

import json
import tempfile
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend.api import post_meeting, pre_meeting, workspaces
from src.backend.context.app_context import AppContext, MeetingNotFoundError
from src.backend.context.archive import ARCHIVE_FILE

MARKDOWN = "# Biên bản\n\nNgân sách 5 triệu đồng."


def make_client(data_dir: Path):
    app = FastAPI()
    for router in (pre_meeting.router, post_meeting.router, workspaces.router):
        app.include_router(router, prefix="/api/v1")
    app.state.ctx = AppContext(data_dir)

    @app.exception_handler(MeetingNotFoundError)
    def _missing(_request, exc):
        from fastapi.responses import JSONResponse
        return JSONResponse(status_code=404, content={"error": {"code": "MEETING_NOT_FOUND", "message": str(exc), "details": {}}})

    return TestClient(app), app.state.ctx


def make_meeting(ctx, status="review", topic="Ra mắt app"):
    session = ctx.create_session()
    session.emplace("meeting", {
        "id": session.id, "topic": topic, "language": "vi", "duration_minutes": 30, "planned_points": [],
        "previous_meeting_id": None, "created_at": "2026-11-25T10:00:00+07:00", "started_at": None,
        "ended_at": "2026-11-25T10:30:00+07:00",
    })
    session.emplace("agenda", [{"id": "agd_001", "title": "Ngân sách", "state": "concluded"}])
    session.emplace("transcript", [{"id": "seg_001", "text": "Mình chốt 5 triệu.", "start_seconds": 1.0}])
    session.emplace("extractions", [])
    session.emplace("extraction_cursor", 1)
    session.emplace("conflicts", [])
    session.emplace("minutes", {
        "meeting_id": session.id, "status": "draft", "summary": "", "decisions": [], "action_items": [],
        "unresolved_issues": [], "markdown": MARKDOWN, "updated_at": "2026-11-25T10:31:00+07:00",
    })
    session.status = status
    return session


class LibraryTestCase(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.client, self.ctx = make_client(self.dir)

    def restart(self):
        """A new backend over the same data folder, as after quitting and reopening the app."""
        self.client, self.ctx = make_client(self.dir)


class TestArchive(LibraryTestCase):
    def test_confirmed_meeting_is_still_there_after_a_restart(self):
        session = make_meeting(self.ctx)
        self.assertEqual(self.client.post(f"/api/v1/meetings/{session.id}/minutes/confirm").status_code, 200)
        self.assertTrue((session.root / ARCHIVE_FILE).is_file())

        self.restart()
        meeting = self.client.get(f"/api/v1/meetings/{session.id}").json()
        self.assertEqual((meeting["topic"], meeting["status"]), ("Ra mắt app", "archived"))
        minutes = self.client.get(f"/api/v1/meetings/{session.id}/minutes").json()
        self.assertEqual((minutes["status"], minutes["markdown"]), ("confirmed", MARKDOWN))

    def test_unconfirmed_meeting_is_not_kept(self):
        session = make_meeting(self.ctx, status="review")
        self.assertFalse((session.root / ARCHIVE_FILE).exists())
        self.restart()
        self.assertEqual(self.client.get(f"/api/v1/meetings/{session.id}").status_code, 404)

    def test_confirmed_minutes_can_be_edited_and_the_edit_survives_a_restart(self):
        session = make_meeting(self.ctx)
        self.client.post(f"/api/v1/meetings/{session.id}/minutes/confirm")
        response = self.client.put(f"/api/v1/meetings/{session.id}/minutes", json={"markdown": "# Đã sửa"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["status"], "confirmed")  # editing does not un-confirm
        self.assertEqual((session.root / "post_meeting/meeting_minutes/minutes_final.md").read_text(encoding="utf-8"), "# Đã sửa")
        self.restart()
        self.assertEqual(self.client.get(f"/api/v1/meetings/{session.id}/minutes").json()["markdown"], "# Đã sửa")

    def test_minutes_cannot_be_edited_before_they_exist_in_review(self):
        session = make_meeting(self.ctx, status="processing")
        response = self.client.put(f"/api/v1/meetings/{session.id}/minutes", json={"markdown": "x"})
        self.assertEqual(response.status_code, 409)

    def test_a_broken_archive_does_not_stop_the_others(self):
        good = make_meeting(self.ctx)
        self.client.post(f"/api/v1/meetings/{good.id}/minutes/confirm")
        bad = make_meeting(self.ctx)
        (bad.root / ARCHIVE_FILE).write_text("{not json")
        self.restart()
        self.assertEqual(self.client.get(f"/api/v1/meetings/{good.id}").status_code, 200)
        self.assertEqual(self.client.get(f"/api/v1/meetings/{bad.id}").status_code, 404)


class TestMeetingList(LibraryTestCase):
    def test_lists_only_the_asked_status_newest_first(self):
        older = make_meeting(self.ctx, status="archived", topic="Cũ")
        older.at("meeting")["ended_at"] = "2026-11-20T10:00:00+07:00"
        newer = make_meeting(self.ctx, status="archived", topic="Mới")
        make_meeting(self.ctx, status="review", topic="Chưa chốt")
        items = self.client.get("/api/v1/meetings", params={"status": "archived"}).json()["items"]
        self.assertEqual([item["topic"] for item in items], ["Mới", "Cũ"])
        self.assertEqual(len(self.client.get("/api/v1/meetings").json()["items"]), 3)
        self.assertIsNone(items[0]["workspace_id"])


class TestWorkspaces(LibraryTestCase):
    def create(self, **body):
        return self.client.post("/api/v1/workspaces", json={"name": "Standup", "icon": "calendar", "color": "violet", **body})

    def test_create_list_rename_and_survive_a_restart(self):
        created = self.create(name="  Khách hàng  ")
        self.assertEqual(created.status_code, 201)
        workspace = created.json()
        self.assertEqual((workspace["name"], workspace["icon"]), ("Khách hàng", "calendar"))
        self.assertTrue(workspace["id"].startswith("wsp_"))
        renamed = self.client.patch(f"/api/v1/workspaces/{workspace['id']}", json={"name": "Sales", "color": "teal"}).json()
        self.assertEqual((renamed["name"], renamed["color"], renamed["icon"]), ("Sales", "teal", "calendar"))
        self.restart()
        items = self.client.get("/api/v1/workspaces").json()["items"]
        self.assertEqual([item["name"] for item in items], ["Sales"])

    def test_bad_input_is_refused(self):
        for body in ({"name": "   "}, {"name": "x" * 61}, {"icon": "Bad Icon"}, {"color": "#ff0000"}):
            with self.subTest(body=body):
                self.assertEqual(self.create(**body).status_code, 400)
        self.assertEqual(self.client.get("/api/v1/workspaces").json()["items"], [])

    def test_unknown_workspace_is_404(self):
        self.assertEqual(self.client.patch("/api/v1/workspaces/wsp_nope", json={"name": "x"}).status_code, 404)
        self.assertEqual(self.client.delete("/api/v1/workspaces/wsp_nope").status_code, 404)

    def test_file_a_meeting_and_take_it_out(self):
        workspace = self.create().json()
        session = make_meeting(self.ctx, status="archived")
        filed = self.client.put(f"/api/v1/meetings/{session.id}/workspace", json={"workspace_id": workspace["id"]})
        self.assertEqual(filed.json()["workspace_id"], workspace["id"])
        self.restart()  # the filing is part of the archive
        self.assertEqual(self.client.get(f"/api/v1/meetings/{session.id}").json()["workspace_id"], workspace["id"])
        out = self.client.put(f"/api/v1/meetings/{session.id}/workspace", json={"workspace_id": None})
        self.assertIsNone(out.json()["workspace_id"])

    def test_only_confirmed_minutes_can_be_filed_and_the_workspace_must_exist(self):
        workspace = self.create().json()
        review = make_meeting(self.ctx, status="review")
        self.assertEqual(self.client.put(f"/api/v1/meetings/{review.id}/workspace", json={"workspace_id": workspace["id"]}).status_code, 409)
        archived = make_meeting(self.ctx, status="archived")
        response = self.client.put(f"/api/v1/meetings/{archived.id}/workspace", json={"workspace_id": "wsp_nope"})
        self.assertEqual(response.status_code, 404)
        self.assertEqual(response.json()["error"]["code"], "WORKSPACE_NOT_FOUND")

    def test_deleting_a_workspace_keeps_its_meetings(self):
        workspace = self.create().json()
        session = make_meeting(self.ctx, status="archived")
        self.client.put(f"/api/v1/meetings/{session.id}/workspace", json={"workspace_id": workspace["id"]})
        self.assertEqual(self.client.delete(f"/api/v1/workspaces/{workspace['id']}").json(), {"items": []})
        self.assertIsNone(self.client.get(f"/api/v1/meetings/{session.id}").json()["workspace_id"])
        self.restart()
        self.assertIsNone(self.client.get(f"/api/v1/meetings/{session.id}").json()["workspace_id"])
        self.assertEqual(json.loads((self.dir / "workspaces.json").read_text()), [])


if __name__ == "__main__":
    unittest.main()
