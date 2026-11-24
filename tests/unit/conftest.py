"""Make unit tests independent of local credentials, services, and audio devices."""

import pytest
import requests
import sounddevice

from src.backend.utils import llm


@pytest.fixture(autouse=True)
def offline_unit_services(monkeypatch):
    def unexpected_external_call(*args, **kwargs):
        raise AssertionError("Unit tests must explicitly mock HTTP/audio operations")

    monkeypatch.setattr(requests.sessions.Session, "request", unexpected_external_call)
    for name in ("rec", "stop", "play", "InputStream"):
        monkeypatch.setattr(sounddevice, name, unexpected_external_call)
    for key in ("GROQ_API_KEY", "OPENROUTER_API_KEY", "ELEVENLABS_API_KEY"):
        monkeypatch.delenv(key, raising=False)
    # call_llm reloads .env: deleting environment variables alone is insufficient.
    monkeypatch.setattr(llm, "load_dotenv", lambda *args, **kwargs: None)
