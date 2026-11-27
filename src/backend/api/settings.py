"""
SETTINGS: the API keys the backend needs, entered in the UI instead of a .env file.

    GET /api/v1/settings   which keys are set (never their values)
    PUT /api/v1/settings   save a key, or remove a saved one with null

Contract: docs/system_design/api-contract.md §6.15

A saved key is written to <data dir>/settings.json (owner-only) and put in os.environ, where the
STT and LLM code already reads it, so it works at once without a restart. It wins over a value from
.env; removing it brings the .env value back. The value is never sent back to the client.
"""

import json
import logging
import os
import threading
from pathlib import Path

from fastapi import APIRouter

from ..utils.objects import SettingKey, SettingsEdit, SettingsView
from ..utils.utils import error
from .common import CtxDep

router = APIRouter(prefix="/settings", tags=["settings"])

LOGGER = logging.getLogger(__name__)

# Only these names can be written: a request must never set an arbitrary environment variable.
KEY_NAMES = ("ELEVENLABS_API_KEY", "GROQ_API_KEY", "OPENROUTER_API_KEY")
MAX_KEY_LENGTH = 512
SETTINGS_FILE = "settings.json"

# What os.environ held (from .env or the shell) before a saved key replaced it.
_original: dict[str, str | None] = {}
_lock = threading.Lock()


def _read(path: Path) -> dict[str, str]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError):
        # Never log the content: it holds secrets.
        LOGGER.warning("Could not read %s; ignoring it", path.name)
        return {}
    return {name: data[name] for name in KEY_NAMES if isinstance(data.get(name), str) and data[name]}


def _write(path: Path, saved: dict[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(".tmp")
    # Created owner-only from the start, so the keys are never readable by others, even briefly.
    descriptor = os.open(temp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(descriptor, "w", encoding="utf-8") as file:
        json.dump(saved, file)
    os.replace(temp, path)


def _apply(saved: dict[str, str]) -> None:
    for name in KEY_NAMES:
        if name in saved:
            _original.setdefault(name, os.environ.get(name))
            os.environ[name] = saved[name]
        elif name in _original:
            previous = _original.pop(name)
            if previous is None:
                os.environ.pop(name, None)
            else:
                os.environ[name] = previous


def apply_saved(data_dir: Path) -> None:
    """Called once at startup, so keys saved earlier are in place before the first request."""
    with _lock:
        _apply(_read(data_dir / SETTINGS_FILE))


def _view(saved: dict[str, str]) -> SettingsView:
    keys = []
    for name in KEY_NAMES:
        value = os.environ.get(name, "").strip()
        source = "settings" if name in saved else "env" if value else None
        # The last four characters help tell two keys apart; a short value shows nothing.
        hint = f"…{value[-4:]}" if value and len(value) >= 12 else None
        keys.append(SettingKey(name=name, is_set=bool(value), source=source, hint=hint))
    return SettingsView(keys=keys)


def _invalid(value: str) -> bool:
    return not value or len(value) > MAX_KEY_LENGTH or any(c.isspace() or not c.isprintable() for c in value)


@router.get("", response_model=SettingsView)
def read_settings(ctx: CtxDep):
    with _lock:
        return _view(_read(ctx.storage.root_dir / SETTINGS_FILE))


@router.put("", response_model=SettingsView)
def update_settings(body: SettingsEdit, ctx: CtxDep):
    """FRONT END SENDS {values: {NAME: "key" | null}}. A string saves, null removes the saved key."""
    unknown = sorted(set(body.values) - set(KEY_NAMES))
    if unknown:
        return error(400, "VALIDATION_ERROR", f"Unknown setting: {', '.join(unknown)}")
    cleaned = {name: value.strip() if value is not None else None for name, value in body.values.items()}
    bad = sorted(name for name, value in cleaned.items() if value is not None and _invalid(value))
    if bad:
        # Names only, never the value.
        return error(400, "VALIDATION_ERROR", f"Not a valid key: {', '.join(bad)}")

    path = ctx.storage.root_dir / SETTINGS_FILE
    with _lock:
        saved = _read(path)
        for name, value in cleaned.items():
            if value is None:
                saved.pop(name, None)
            else:
                saved[name] = value
        _write(path, saved)
        _apply(saved)
        return _view(saved)
