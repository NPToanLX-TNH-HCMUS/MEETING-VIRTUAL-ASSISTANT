"""State isolation and lock cleanup matter even when every external service is healthy."""

from concurrent.futures import ThreadPoolExecutor

import pytest

from src.backend.context.app_context import AppContext, MeetingNotFoundError
from src.backend.context.session import MeetingSession, MissingContextError


def test_missing_context_is_domain_error_and_optional_read_has_default(tmp_path):
    session = MeetingSession("m", tmp_path)
    with pytest.raises(MissingContextError):
        session.at("transcript")
    assert session.get("transcript", []) == []


def test_remove_context_does_not_leave_stale_data(tmp_path):
    session = MeetingSession("m", tmp_path)
    session.emplace("transcript", "before")
    assert session.has("transcript")
    assert session.pop("transcript") == "before"
    assert not session.has("transcript")
    assert session.pop("transcript", "missing") == "missing"


def test_contexts_for_different_meetings_never_share_mutable_state(tmp_path):
    ctx = AppContext(tmp_path)
    first, second = ctx.create_session(), ctx.create_session()
    first.emplace("agenda", ["Private agenda"])
    assert first.id != second.id
    assert first.root != second.root
    assert second.get("agenda") is None
    assert ctx.session(first.id) is first


def test_registry_snapshot_cannot_clear_active_meetings(tmp_path):
    ctx = AppContext(tmp_path)
    session = ctx.create_session()
    snapshot = ctx.sessions()
    snapshot.clear()
    assert ctx.session(session.id) is session
    with pytest.raises(MeetingNotFoundError):
        ctx.session("unknown")


def test_context_manager_releases_lock_after_exception(tmp_path):
    session = MeetingSession("m", tmp_path)
    with pytest.raises(RuntimeError):
        with session:
            raise RuntimeError("operation failed")

    def another_thread_can_acquire():
        acquired = session.lock.acquire(timeout=0.5)
        if acquired:
            session.lock.release()
        return acquired

    # Reacquiring an RLock from this same thread would not detect a leaked acquisition.
    with ThreadPoolExecutor(max_workers=1) as pool:
        assert pool.submit(another_thread_can_acquire).result(timeout=2)
