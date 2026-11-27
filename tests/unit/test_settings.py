"""API keys entered in the UI: saved owner-only, applied at once, never sent back (no network)."""

import json
import os
import stat
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

from src.backend.api import settings
from src.backend.context.app_context import AppContext

SECRET = "gsk_abcdefghijklmnop1234"


class TestSettings(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        # os.environ and the "what was there before" memory go back to how they were after each test.
        env = patch.dict(os.environ, {}, clear=False)
        env.start()
        self.addCleanup(env.stop)
        memory = patch.dict(settings._original, {}, clear=True)
        memory.start()
        self.addCleanup(memory.stop)
        for name in settings.KEY_NAMES:
            os.environ.pop(name, None)
        app = FastAPI()
        app.include_router(settings.router, prefix="/api/v1")
        app.state.ctx = AppContext(self.dir)
        self.client = TestClient(app)

    def keys(self, response):
        return {key["name"]: key for key in response.json()["keys"]}

    def test_nothing_set_at_first(self):
        keys = self.keys(self.client.get("/api/v1/settings"))
        self.assertEqual(set(keys), set(settings.KEY_NAMES))
        self.assertTrue(all(not key["is_set"] and key["source"] is None for key in keys.values()))

    def test_key_from_env_is_reported_as_env(self):
        os.environ["GROQ_API_KEY"] = SECRET
        key = self.keys(self.client.get("/api/v1/settings"))["GROQ_API_KEY"]
        self.assertEqual((key["is_set"], key["source"], key["hint"]), (True, "env", "…1234"))

    def test_saved_key_is_applied_stored_owner_only_and_never_returned(self):
        response = self.client.put("/api/v1/settings", json={"values": {"GROQ_API_KEY": f"  {SECRET}  "}})
        self.assertEqual(response.status_code, 200)
        self.assertNotIn(SECRET, response.text)
        self.assertEqual(os.environ["GROQ_API_KEY"], SECRET)  # trimmed, and visible to the STT/LLM code
        key = self.keys(response)["GROQ_API_KEY"]
        self.assertEqual((key["is_set"], key["source"], key["hint"]), (True, "settings", "…1234"))
        path = self.dir / settings.SETTINGS_FILE
        self.assertEqual(json.loads(path.read_text()), {"GROQ_API_KEY": SECRET})
        if os.name == "posix":
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
        self.assertNotIn(SECRET, self.client.get("/api/v1/settings").text)

    def test_removing_a_saved_key_brings_back_the_env_value(self):
        os.environ["GROQ_API_KEY"] = "from-env-0000000000"
        self.client.put("/api/v1/settings", json={"values": {"GROQ_API_KEY": SECRET}})
        response = self.client.put("/api/v1/settings", json={"values": {"GROQ_API_KEY": None}})
        self.assertEqual(os.environ["GROQ_API_KEY"], "from-env-0000000000")
        self.assertEqual(self.keys(response)["GROQ_API_KEY"]["source"], "env")
        self.assertEqual(json.loads((self.dir / settings.SETTINGS_FILE).read_text()), {})

    def test_removing_a_saved_key_with_no_env_value_clears_it(self):
        self.client.put("/api/v1/settings", json={"values": {"GROQ_API_KEY": SECRET}})
        response = self.client.put("/api/v1/settings", json={"values": {"GROQ_API_KEY": None}})
        self.assertNotIn("GROQ_API_KEY", os.environ)
        self.assertFalse(self.keys(response)["GROQ_API_KEY"]["is_set"])

    def test_saving_one_key_keeps_the_others(self):
        self.client.put("/api/v1/settings", json={"values": {"GROQ_API_KEY": SECRET}})
        self.client.put("/api/v1/settings", json={"values": {"ELEVENLABS_API_KEY": "xi-0123456789abcdef"}})
        saved = json.loads((self.dir / settings.SETTINGS_FILE).read_text())
        self.assertEqual(set(saved), {"GROQ_API_KEY", "ELEVENLABS_API_KEY"})

    def test_unknown_name_is_refused_and_nothing_is_saved(self):
        response = self.client.put(
            "/api/v1/settings", json={"values": {"GROQ_API_KEY": SECRET, "PATH": "/tmp/evil"}}
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], "VALIDATION_ERROR")
        self.assertNotEqual(os.environ.get("PATH"), "/tmp/evil")
        self.assertFalse((self.dir / settings.SETTINGS_FILE).exists())

    def test_invalid_values_are_refused_without_echoing_them(self):
        for bad in ["", "   ", "two words", "line\nbreak", "x" * (settings.MAX_KEY_LENGTH + 1)]:
            with self.subTest(bad=bad[:10]):
                response = self.client.put("/api/v1/settings", json={"values": {"GROQ_API_KEY": bad}})
                self.assertEqual(response.status_code, 400)
                self.assertNotIn("two words", response.text)
        self.assertFalse((self.dir / settings.SETTINGS_FILE).exists())

    def test_saved_keys_are_loaded_at_startup(self):
        (self.dir / settings.SETTINGS_FILE).write_text(json.dumps({"GROQ_API_KEY": SECRET, "PATH": "/tmp/evil"}))
        settings.apply_saved(self.dir)
        self.assertEqual(os.environ["GROQ_API_KEY"], SECRET)
        self.assertNotEqual(os.environ.get("PATH"), "/tmp/evil")

    def test_a_broken_settings_file_is_ignored(self):
        (self.dir / settings.SETTINGS_FILE).write_text("{not json")
        settings.apply_saved(self.dir)
        self.assertEqual(self.client.get("/api/v1/settings").status_code, 200)


if __name__ == "__main__":
    unittest.main()
