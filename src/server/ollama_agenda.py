"""
Same job as gemini_agenda.py, but with a small model running in Ollama (local, no API key).

main.py picks this file when LLM_PROVIDER=ollama. Setup:
    ollama pull qwen2.5:3b          (Ollama app/server must be running)
Settings in .env.example (all optional): OLLAMA_URL, OLLAMA_MODEL.
Try it alone:  python -m src.server.ollama_agenda notes.md
"""

import os
import sys
from pathlib import Path

import requests
from pydantic import ValidationError

from .gemini_agenda import INSTRUCTIONS, LANGUAGES, GeminiError, Topics, build_prompt

OLLAMA_URL = os.getenv("OLLAMA_URL", "http://127.0.0.1:11434")
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL", "qwen2.5:3b")


def extract_topics(planned_points: list[str], documents: list[dict], language: str = "vi") -> list[dict]:
    prompt = build_prompt(planned_points, documents)
    if not prompt:
        return []

    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/chat",
            json={
                "model": OLLAMA_MODEL,
                "stream": False,
                "format": Topics.model_json_schema(),  # Ollama forces the reply to match this schema
                "options": {"temperature": 0.2, "num_ctx": 8192},  # default context (4096) would cut long notes
                "messages": [
                    {"role": "system", "content": INSTRUCTIONS.format(language=LANGUAGES.get(language, language))},
                    {"role": "user", "content": prompt},
                ],
            },
            timeout=110,  # the UI gives up after 120 s
        )
        response.raise_for_status()
        content = response.json()["message"]["content"]
    except (requests.RequestException, KeyError, ValueError) as e:  # server off, model not pulled, timeout...
        raise GeminiError(503, "LLM_UNAVAILABLE", f"Ollama request failed ({OLLAMA_URL}, {OLLAMA_MODEL}): {e}") from e

    try:
        topics = Topics.model_validate_json(content)
    except ValidationError as e:
        raise GeminiError(422, "LLM_BAD_OUTPUT", "Ollama did not return the expected JSON") from e

    return [t.model_dump() for t in topics.items if t.title.strip()]


if __name__ == "__main__":
    docs = [{"filename": Path(f).name, "text": Path(f).read_text(encoding="utf-8-sig")} for f in sys.argv[1:]]
    for topic in extract_topics([], docs):
        print(topic)
