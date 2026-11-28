"""Make unit tests independent of local credentials, services, and audio devices."""

import atexit
import os
import shutil
import tempfile
from pathlib import Path

# Configure offline-safe DB and storage defaults BEFORE importing backend modules so
# unit tests never depend on a local .env or touch a real Supabase/Postgres instance.
_UNIT_DB_DIR = Path(tempfile.mkdtemp(prefix="mia-unit-db-"))
_UNIT_DB_PATH = _UNIT_DB_DIR / "unit.db"
os.environ["DATABASE_URL"] = f"sqlite:///{_UNIT_DB_PATH.as_posix()}"
os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_API_KEY"] = (
    "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9."
    "eyJpc3MiOiJzdXBhYmFzZSIsInJvbGUiOiJhbm9uIn0.dummy"
)

import pytest  # noqa: E402
import requests  # noqa: E402
import sounddevice  # noqa: E402

from src.backend.database.database import engine  # noqa: E402
from src.backend.database.model import Base  # noqa: E402
from src.backend.utils import llm  # noqa: E402

Base.metadata.create_all(engine)


def _cleanup_unit_db() -> None:
    engine.dispose()
    shutil.rmtree(_UNIT_DB_DIR, ignore_errors=True)


atexit.register(_cleanup_unit_db)


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
