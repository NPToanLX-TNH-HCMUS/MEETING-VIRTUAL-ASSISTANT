"""Shared API setup for the AppContext-based backend."""

import pytest
import requests
import sounddevice
from fastapi.testclient import TestClient

from src.backend.context.app_context import AppContext
from src.backend.main import app


@pytest.fixture(autouse=True)
def offline_services(monkeypatch):
    # An incomplete mock must fail the test rather than reach a paid service/device.
    def unexpected_external_call(*args, **kwargs):
        raise AssertionError("Mock the external HTTP or audio operation in this test")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected_external_call)
    for name in ("rec", "stop", "play", "InputStream"):
        monkeypatch.setattr(sounddevice, name, unexpected_external_call)


@pytest.fixture
def client(tmp_path):
    # Exercise real routes and storage while giving each test its own meeting registry.
    original_context = app.state.ctx
    app.state.ctx = AppContext(tmp_path / "data")
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.state.ctx = original_context
