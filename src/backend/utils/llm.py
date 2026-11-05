"""
utils/llm.py
=============
The only LLM-calling point for the whole project

* Currently available provider:
    ** Currently available model:
- "google":
    "gemini-4-argon"
    "gemini-3.8-flash"
    "gemini-3.6-flash"
    "gemini-3.5-flash-lite"

"""

from __future__ import annotations

import json
import os
import re

from dotenv import load_dotenv


def call_llm(
    _prompt: str,
    _provider: str,
    _model: str,
    _max_tokens: int = 512,
    _temperature: float = 0.0,
) -> str:

    load_dotenv()

    if _provider == "google":
        GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
        if not GEMINI_API_KEY:
            raise ValueError("GEMINI_API_KEY was not found. Add it to your .env file.")

        from google import genai

        client = genai.Client(api_key=GEMINI_API_KEY)
        response = client.interactions.create(model=_model, input=_prompt)

        return response
    else:
        raise ValueError(f"Unsupported LLM provider: '{_provider}'")


def parse_json_list(text: str) -> list[str]:
    """ """
    cleaned = re.sub(r"```(?:json)?", "", text).strip().rstrip("`").strip()
    try:
        result = json.loads(cleaned)
        if isinstance(result, list):
            return [str(item).strip() for item in result if str(item).strip()]
    except json.JSONDecodeError:
        pass

    # Fallback:
    items = re.findall(r'"([^"]+)"', cleaned)
    if items:
        return items
    return [
        re.sub(r"^\d+[\.\)]\s*", "", line).strip()
        for line in cleaned.splitlines()
        if line.strip() and not line.strip().startswith(("[", "]"))
    ]
