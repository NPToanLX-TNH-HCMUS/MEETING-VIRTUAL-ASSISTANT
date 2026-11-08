"""Call cloud LLMs with retries, fallback, and optional schema validation."""

from __future__ import annotations

import json
import logging
import os
from pathlib import Path
from time import sleep

import requests
from dotenv import load_dotenv
from jsonschema import Draft202012Validator, ValidationError

LOGGER = logging.getLogger(__name__)

PRIMARY_MODEL = "openai/gpt-oss-20b"
FALLBACK_MODEL = "nvidia/nemotron-3.5-super-vl:free"
REQUEST_TIMEOUT = (5, 60)
RETRY_DELAY_SECONDS = 0.5

PROVIDER_SETTINGS = {
    "groq": (
        "https://api.groq.com/openai/v1/chat/completions",
        "GROQ_API_KEY",
    ),
    "openrouter": (
        "https://openrouter.ai/api/v1/chat/completions",
        "OPENROUTER_API_KEY",
    ),
}


class LLMCallError(RuntimeError):
    """Report a service failure or an unusable model response."""

    def __init__(self, status: int, code: str, message: str) -> None:
        super().__init__(message)
        self.status = status
        self.code = code


def _request_text(
    provider: str,
    model: str,
    prompt: str,
    max_tokens: int,
    temperature: float,
    schema: dict | None,
) -> str:
    url, key_name = PROVIDER_SETTINGS[provider]
    api_key = os.getenv(key_name, "").strip()
    if not api_key:
        raise LLMCallError(503, "LLM_UNAVAILABLE", f"{key_name} is missing.")

    payload = {
        "model": model,
        "messages": [{"role": "user", "content": prompt}],
        "temperature": temperature,
    }

    if provider == "groq":
        payload["max_completion_tokens"] = max_tokens
        payload["reasoning_effort"] = "low"
    else:
        payload["max_tokens"] = max_tokens

    if schema is not None:
        payload["response_format"] = {
            "type": "json_schema",
            "json_schema": {
                "name": "llm_output",
                "strict": True,
                "schema": schema,
            },
        }
        if provider == "openrouter":
            # Only route to endpoints that support the requested schema format.
            payload["provider"] = {"require_parameters": True}

    try:
        response = requests.post(
            url,
            headers={"Authorization": f"Bearer {api_key}"},
            json=payload,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as error:
        raise LLMCallError(
            503, "LLM_UNAVAILABLE", type(error).__name__
        ) from error

    if not response.ok:
        raise LLMCallError(
            503, "LLM_UNAVAILABLE", f"Provider returned HTTP {response.status_code}."
        )

    try:
        choice = response.json()["choices"][0]
        text = choice["message"]["content"]
        finish_reason = choice.get("finish_reason")
    except (ValueError, KeyError, IndexError, TypeError, AttributeError) as error:
        raise LLMCallError(
            422, "LLM_BAD_OUTPUT", "Unexpected response format."
        ) from error

    if finish_reason == "length":
        raise LLMCallError(422, "LLM_BAD_OUTPUT", "Response reached the token limit.")
    if not isinstance(text, str) or not text.strip():
        raise LLMCallError(422, "LLM_BAD_OUTPUT", "Model returned no text.")

    return text


def call_llm(
    _prompt: str,
    _provider: str = "groq",
    _model: str = PRIMARY_MODEL,
    _max_tokens: int = 512,
    _temperature: float = 0.0,
    _schema: dict | None = None,
) -> str:
    """Return the first usable response from two primary attempts and one fallback."""
    if (_provider, _model) != ("groq", PRIMARY_MODEL):
        raise ValueError(f"The configured primary model is groq/{PRIMARY_MODEL}.")
    if not _prompt.strip():
        raise ValueError("The prompt must not be empty.")
    if _max_tokens < 1:
        raise ValueError("The token limit must be positive.")

    validator = None
    if _schema is not None:
        Draft202012Validator.check_schema(_schema)
        validator = Draft202012Validator(_schema)

    load_dotenv()
    env_file = Path(__file__).resolve().parents[3] / ".env"
    if env_file.is_file():
        load_dotenv(env_file, override=False)

    # Auto-detect key prefix: if a Groq key (starts with gsk_) was assigned to OPENROUTER_API_KEY
    if not os.getenv("GROQ_API_KEY") and os.getenv("OPENROUTER_API_KEY", "").startswith("gsk_"):
        os.environ["GROQ_API_KEY"] = os.getenv("OPENROUTER_API_KEY")
    attempts = (
        (_provider, _model),
        (_provider, _model),
        ("openrouter", FALLBACK_MODEL),
    )
    failures = []

    for attempt_number, (provider, model) in enumerate(attempts, start=1):
        try:
            text = _request_text(
                provider, model, _prompt, _max_tokens, _temperature, _schema
            )
            if validator is not None:
                # Validate locally so both providers follow the same output contract.
                validator.validate(json.loads(text))
        except LLMCallError as error:
            failure = error
        except (json.JSONDecodeError, ValidationError):
            failure = LLMCallError(
                422, "LLM_BAD_OUTPUT", "Model output does not match the JSON schema."
            )
        else:
            return text

        message = (
            f"Attempt {attempt_number} ({provider}, {model}): "
            f"{failure.code}: {failure}"
        )
        failures.append(message)
        LOGGER.warning("%s", message)

        if attempt_number == 1:
            sleep(RETRY_DELAY_SECONDS)

    raise LLMCallError(failure.status, failure.code, " | ".join(failures))
