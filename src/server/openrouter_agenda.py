"""
OpenRouter (free cloud models, OpenAI-style API): planned points + documents -> agenda topics.
Settings in .env.example: OPENROUTER_API_KEY (from openrouter.ai/keys), OPENROUTER_MODEL (optional).
Privacy: the text of the uploaded files is sent to OpenRouter and the model's provider.
Try it alone:  python -m src.server.openrouter_agenda notes.md
"""

import os
import sys
import time
from pathlib import Path

import requests

from .llm_common import LLMError, build_prompt, parse_topics, system_prompt

URL = "https://openrouter.ai/api/v1/chat/completions"
MODEL = os.getenv("OPENROUTER_MODEL", "google/gemma-4-31b-it:free")
FALLBACK_MODEL = "openrouter/free"  # OpenRouter picks whichever free model is available right now

# Not every free model accepts a JSON schema, but all accept "json_object", so the shape is described in words.
JSON_HINT = (
    '\nReply with JSON only, exactly like: '
    '{"items": [{"title": "...", "source": "planned_point" or "document", "minutes": 10}]}'
)


def extract_topics(planned_points: list[str], documents: list[dict], duration_minutes: int = 60) -> list[dict]:
    prompt = build_prompt(planned_points, documents)
    if not prompt:
        return []

    key = os.getenv("OPENROUTER_API_KEY", "").strip()
    if not key:
        raise LLMError(503, "LLM_UNAVAILABLE", "OPENROUTER_API_KEY is empty (set it in .env.example)")

    body = {
        "model": MODEL,
        "temperature": 0.2,
        "response_format": {"type": "json_object"},
        "messages": [
            {"role": "system", "content": system_prompt(duration_minutes) + JSON_HINT},
            {"role": "user", "content": prompt},
        ],
    }
    # Free models are often busy (429/502/503): retry the chosen model once, then let OpenRouter pick any free one.
    models = [MODEL, MODEL, FALLBACK_MODEL]
    for n, model in enumerate(models, start=1):
        body["model"] = model
        try:
            response = requests.post(URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=100)
        except requests.RequestException as e:
            raise LLMError(503, "LLM_UNAVAILABLE", f"OpenRouter request failed: {e}") from e
        if response.status_code in (429, 502, 503) and n < len(models):
            time.sleep(3)
            continue
        break

    try:
        data = response.json()
        reply = data["choices"][0]["message"]["content"]
    except (ValueError, KeyError, IndexError, TypeError) as e:  # error body, empty reply...
        raise LLMError(503, "LLM_UNAVAILABLE", f"OpenRouter HTTP {response.status_code}: {response.text[:300]}") from e

    return parse_topics(reply or "", planned_points, documents, duration_minutes)


if __name__ == "__main__":
    docs = [{"filename": Path(f).name, "text": Path(f).read_text(encoding="utf-8-sig")} for f in sys.argv[1:]]
    try:
        for topic in extract_topics([], docs):
            print(topic)
    except LLMError as e:
        raise SystemExit(f"{e.code}: {e}")
