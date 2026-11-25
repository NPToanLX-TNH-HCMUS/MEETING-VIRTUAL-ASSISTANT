"""
WORKSPACES: groups the user files confirmed minutes under, and the list of meetings they hold.

    GET    /api/v1/meetings?status=archived      the meetings (newest first)
    GET    /api/v1/workspaces                    the workspaces
    POST   /api/v1/workspaces                    create one (name, icon, color)
    PATCH  /api/v1/workspaces/{id}               rename, new icon or color
    DELETE /api/v1/workspaces/{id}               delete; its meetings go back to "no workspace"
    PUT    /api/v1/meetings/{id}/workspace       file a confirmed meeting under a workspace, or take it out

Contract: docs/system_design/api-contract.md §6.16
Workspaces are saved in <data dir>/workspaces.json; the workspace of a meeting is part of its archive.
"""

import json
import re
import threading
import uuid

from fastapi import APIRouter

from ..context.archive import save_archive, write_json
from ..utils.objects import (
    Meeting,
    MeetingList,
    MeetingWorkspace,
    Workspace,
    WorkspaceEdit,
    WorkspaceList,
    WorkspaceNew,
)
from ..utils.utils import error, now
from .common import CtxDep, SessionDep, meeting_response

router = APIRouter(tags=["workspaces"])

WORKSPACES_FILE = "workspaces.json"
MAX_NAME_LENGTH = 60
# Icon and colour are names the UI draws; the server only checks they are short and plain.
LABEL = re.compile(r"^[a-z0-9-]{1,32}$")

_lock = threading.Lock()


def _read(ctx) -> list[dict]:
    try:
        data = json.loads((ctx.storage.root_dir / WORKSPACES_FILE).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return [item for item in data if isinstance(item, dict) and {"id", "name"} <= set(item)] if isinstance(data, list) else []


def _write(ctx, items: list[dict]) -> None:
    write_json(ctx.storage.root_dir / WORKSPACES_FILE, items)


def _not_found(workspace_id: str):
    return error(404, "WORKSPACE_NOT_FOUND", f"No workspace with id {workspace_id}")


def _check(name: str | None, icon: str | None, color: str | None):
    """The first problem as an error response, or None."""
    if name is not None and not 1 <= len(name) <= MAX_NAME_LENGTH:
        return error(400, "VALIDATION_ERROR", f"The name must be 1 to {MAX_NAME_LENGTH} characters.")
    for field, value in (("icon", icon), ("color", color)):
        if value is not None and not LABEL.match(value):
            return error(400, "VALIDATION_ERROR", f"The {field} must be 1 to 32 lowercase letters, digits or dashes.")
    return None


@router.get("/meetings", response_model=MeetingList)
def list_meetings(ctx: CtxDep, status: str | None = None):
    """`status`: optional, comma-separated meeting statuses (the sidebar asks for "archived")."""
    wanted = {part.strip() for part in status.split(",")} if status else None
    items = []
    for session in ctx.sessions():
        with session:
            if session.has("meeting") and (wanted is None or session.status in wanted):
                items.append(meeting_response(session))
    items.sort(key=lambda meeting: meeting.get("ended_at") or meeting["created_at"], reverse=True)
    return {"items": items}


@router.get("/workspaces", response_model=WorkspaceList)
def list_workspaces(ctx: CtxDep):
    with _lock:
        return {"items": _read(ctx)}


@router.post("/workspaces", status_code=201, response_model=Workspace)
def create_workspace(body: WorkspaceNew, ctx: CtxDep):
    name = body.name.strip()
    if not name:
        return error(400, "VALIDATION_ERROR", f"The name must be 1 to {MAX_NAME_LENGTH} characters.")
    if problem := _check(name, body.icon, body.color):
        return problem
    workspace = {"id": f"wsp_{uuid.uuid4().hex[:8]}", "name": name, "icon": body.icon, "color": body.color, "created_at": now()}
    with _lock:
        _write(ctx, _read(ctx) + [workspace])
    return workspace


@router.patch("/workspaces/{workspace_id}", response_model=Workspace)
def update_workspace(workspace_id: str, body: WorkspaceEdit, ctx: CtxDep):
    name = body.name.strip() if body.name is not None else None
    if name == "":
        return error(400, "VALIDATION_ERROR", f"The name must be 1 to {MAX_NAME_LENGTH} characters.")
    if problem := _check(name, body.icon, body.color):
        return problem
    with _lock:
        items = _read(ctx)
        workspace = next((item for item in items if item["id"] == workspace_id), None)
        if workspace is None:
            return _not_found(workspace_id)
        for field, value in (("name", name), ("icon", body.icon), ("color", body.color)):
            if value is not None:
                workspace[field] = value
        _write(ctx, items)
        return workspace


@router.delete("/workspaces/{workspace_id}", response_model=WorkspaceList)
def delete_workspace(workspace_id: str, ctx: CtxDep):
    with _lock:
        items = _read(ctx)
        if not any(item["id"] == workspace_id for item in items):
            return _not_found(workspace_id)
        items = [item for item in items if item["id"] != workspace_id]
        _write(ctx, items)
    # The meetings stay; they just no longer belong to a workspace.
    for session in ctx.sessions():
        with session:
            meeting = session.get("meeting")
            if meeting and meeting.get("workspace_id") == workspace_id:
                meeting["workspace_id"] = None
                if session.status == "archived":
                    save_archive(session)
    return {"items": items}


@router.put("/meetings/{meeting_id}/workspace", response_model=Meeting)
def set_meeting_workspace(body: MeetingWorkspace, session: SessionDep, ctx: CtxDep):
    """FRONT END SENDS {workspace_id}. Only confirmed minutes are filed, so the meeting must be archived."""
    with session:
        if session.status != "archived":
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Only confirmed minutes can be filed in a workspace (the meeting is {session.status}).",
            )
    with _lock:
        if body.workspace_id is not None and not any(item["id"] == body.workspace_id for item in _read(ctx)):
            return _not_found(body.workspace_id)
    with session:
        session.at("meeting")["workspace_id"] = body.workspace_id
        save_archive(session)
        return meeting_response(session)
