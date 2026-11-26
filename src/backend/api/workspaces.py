"""
WORKSPACES: groups the user files confirmed minutes under.

    GET    /api/v1/workspaces                    the workspaces
    POST   /api/v1/workspaces                    create one (name, icon, color)
    PATCH  /api/v1/workspaces/{id}               rename, new icon or color
    DELETE /api/v1/workspaces/{id}               delete; its meetings go back to "no workspace"
    PUT    /api/v1/meetings/{id}/workspace       file a confirmed meeting under a workspace, or take it out

Contract: docs/system_design/api-contract.md §6.16
The meeting list (GET /meetings) lives in pre_meeting.py. Workspaces and a meeting's workspace are kept in the database.
"""

import re
import uuid

from fastapi import APIRouter

from ..utils.objects import (
    Meeting,
    MeetingWorkspace,
    Workspace,
    WorkspaceEdit,
    WorkspaceList,
    WorkspaceNew,
)
from ..utils.utils import error, now
from .common import CtxDep, SessionDep, meeting_response

router = APIRouter(tags=["workspaces"])

MAX_NAME_LENGTH = 60
# Icon and colour are names the UI draws; the server only checks they are short and plain.
LABEL = re.compile(r"^[a-z0-9-]{1,32}$")


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


@router.get("/workspaces", response_model=WorkspaceList)
def list_workspaces(ctx: CtxDep):
    return {"items": ctx.meeting_repository.list_workspaces()}


@router.post("/workspaces", status_code=201, response_model=Workspace)
def create_workspace(body: WorkspaceNew, ctx: CtxDep):
    name = body.name.strip()
    if not name:
        return error(400, "VALIDATION_ERROR", f"The name must be 1 to {MAX_NAME_LENGTH} characters.")
    if problem := _check(name, body.icon, body.color):
        return problem
    workspace = {"id": f"wsp_{uuid.uuid4().hex[:8]}", "name": name, "icon": body.icon, "color": body.color, "created_at": now()}
    ctx.meeting_repository.create_workspace(workspace)
    return workspace


@router.patch("/workspaces/{workspace_id}", response_model=Workspace)
def update_workspace(workspace_id: str, body: WorkspaceEdit, ctx: CtxDep):
    name = body.name.strip() if body.name is not None else None
    if name == "":
        return error(400, "VALIDATION_ERROR", f"The name must be 1 to {MAX_NAME_LENGTH} characters.")
    if problem := _check(name, body.icon, body.color):
        return problem
    values = {field: value for field, value in (("name", name), ("icon", body.icon), ("color", body.color)) if value is not None}
    workspace = ctx.meeting_repository.update_workspace(workspace_id, values)
    return workspace if workspace is not None else _not_found(workspace_id)


@router.delete("/workspaces/{workspace_id}", response_model=WorkspaceList)
def delete_workspace(workspace_id: str, ctx: CtxDep):
    if not ctx.meeting_repository.delete_workspace(workspace_id):
        return _not_found(workspace_id)
    # The database cleared the rows; the meetings already in memory follow.
    for session in ctx.sessions():
        with session:
            meeting = session.get("meeting")
            if meeting and meeting.get("workspace_id") == workspace_id:
                meeting["workspace_id"] = None
    return {"items": ctx.meeting_repository.list_workspaces()}


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
    if body.workspace_id is not None and not any(
        item["id"] == body.workspace_id for item in ctx.meeting_repository.list_workspaces()
    ):
        return _not_found(body.workspace_id)
    with session:
        ctx.meeting_repository.set_meeting_workspace(session.id, body.workspace_id)
        session.at("meeting")["workspace_id"] = body.workspace_id
        return meeting_response(session)
