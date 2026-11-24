"""Exercise real request parsing, retries, and schema checks; fake only HTTP and sleep."""

from unittest.mock import Mock

import pytest
import requests
from jsonschema import SchemaError

from src.backend.utils import llm


SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
    "additionalProperties": False,
}


def reply(text='{"items": []}', *, status=200, finish="stop"):
    response = Mock(spec=requests.Response)
    response.ok = status < 400
    response.status_code = status
    response.json.return_value = {
        "choices": [{"message": {"content": text}, "finish_reason": finish}]
    }
    return response


@pytest.fixture
def transport(monkeypatch):
    post = Mock(return_value=reply())
    monkeypatch.setattr(llm.requests, "post", post)
    monkeypatch.setattr(llm, "sleep", Mock())
    monkeypatch.setenv("GROQ_API_KEY", "unit-primary")
    monkeypatch.setenv("OPENROUTER_API_KEY", "unit-fallback")
    return post


def test_first_success_stops_retrying_and_sends_required_parameters(transport):
    assert llm.call_llm("Extract tasks", _max_tokens=123, _schema=SCHEMA) == '{"items": []}'
    transport.assert_called_once()
    request = transport.call_args
    assert request.args[0] == llm.PROVIDER_SETTINGS["groq"][0]
    assert request.kwargs["headers"]["Authorization"] == "Bearer unit-primary"
    assert request.kwargs["timeout"] == llm.REQUEST_TIMEOUT
    assert request.kwargs["json"]["max_completion_tokens"] == 123
    assert request.kwargs["json"]["messages"] == [{"role": "user", "content": "Extract tasks"}]
    assert request.kwargs["json"]["response_format"]["json_schema"]["schema"] == SCHEMA


@pytest.mark.parametrize("failure", [requests.Timeout("timeout"), requests.ConnectionError("offline"), reply(status=429), reply(status=503)])
def test_transient_failure_retries_primary_before_fallback(transport, failure):
    transport.side_effect = [failure, reply()]
    assert llm.call_llm("Extract tasks") == '{"items": []}'
    assert transport.call_count == 2
    assert all(call.args[0] == llm.PROVIDER_SETTINGS["groq"][0] for call in transport.call_args_list)


def test_fallback_uses_its_own_model_key_and_schema(transport):
    transport.side_effect = [reply(status=503), reply(status=503), reply()]
    assert llm.call_llm("Extract tasks", _schema=SCHEMA, _max_tokens=321) == '{"items": []}'
    assert transport.call_count == 3
    fallback = transport.call_args_list[-1]
    assert fallback.args[0] == llm.PROVIDER_SETTINGS["openrouter"][0]
    assert fallback.kwargs["headers"]["Authorization"] == "Bearer unit-fallback"
    assert fallback.kwargs["json"]["model"] == llm.FALLBACK_MODEL
    assert fallback.kwargs["json"]["max_tokens"] == 321
    assert fallback.kwargs["json"]["provider"] == {"require_parameters": True}
    assert fallback.kwargs["json"]["response_format"]["json_schema"]["schema"] == SCHEMA


@pytest.mark.parametrize("status", [401, 429, 500, 503])
def test_all_service_attempts_failing_produce_bounded_domain_error(transport, status):
    transport.return_value = reply(status=status)
    with pytest.raises(llm.LLMCallError) as caught:
        llm.call_llm("Extract tasks")
    assert (caught.value.status, caught.value.code) == (503, "LLM_UNAVAILABLE")
    assert transport.call_count == 3


@pytest.mark.parametrize("payload", [None, [], {}, {"choices": []}, {"choices": [None]}, {"choices": [{"message": None}]}])
def test_malformed_provider_envelope_is_not_an_unhandled_exception(transport, payload):
    transport.return_value.json.return_value = payload
    with pytest.raises(llm.LLMCallError) as caught:
        llm.call_llm("Extract tasks")
    assert (caught.value.status, caught.value.code) == (422, "LLM_BAD_OUTPUT")
    assert transport.call_count == 3


@pytest.mark.parametrize("text, finish", [(None, "stop"), ([], "stop"), ("  ", "stop"), ('{"items": []}', "length")])
def test_empty_or_truncated_completion_is_rejected(transport, text, finish):
    transport.return_value = reply(text, finish=finish)
    with pytest.raises(llm.LLMCallError) as caught:
        llm.call_llm("Extract tasks", _schema=SCHEMA)
    assert caught.value.code == "LLM_BAD_OUTPUT"


@pytest.mark.parametrize("text", ["not json", '{"items": "not an array"}', '{"items": [42]}', '{"items": [], "extra": true}'])
def test_provider_claiming_schema_support_does_not_bypass_local_validation(transport, text):
    transport.return_value = reply(text)
    with pytest.raises(llm.LLMCallError) as caught:
        llm.call_llm("Extract tasks", _schema=SCHEMA)
    assert caught.value.code == "LLM_BAD_OUTPUT"
    assert transport.call_count == 3


def test_invalid_json_body_from_http_is_a_domain_error(transport):
    transport.return_value.json.side_effect = ValueError("invalid HTTP JSON")
    with pytest.raises(llm.LLMCallError) as caught:
        llm.call_llm("Extract tasks")
    assert caught.value.code == "LLM_BAD_OUTPUT"


def test_invalid_first_completion_can_recover_without_leaking_failed_content(transport):
    transport.side_effect = [reply("bad json"), reply('{"items": ["Review API"]}')]
    assert llm.call_llm("Extract tasks", _schema=SCHEMA) == '{"items": ["Review API"]}'
    assert transport.call_count == 2


def test_missing_credentials_do_not_dispatch_http(transport, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY")
    monkeypatch.delenv("OPENROUTER_API_KEY")
    with pytest.raises(llm.LLMCallError) as caught:
        llm.call_llm("Extract tasks")
    assert caught.value.code == "LLM_UNAVAILABLE"
    transport.assert_not_called()


@pytest.mark.parametrize("kwargs", [
    {"_prompt": " \n"}, {"_prompt": "x", "_max_tokens": 0},
    {"_prompt": "x", "_max_tokens": -1}, {"_prompt": "x", "_provider": "unsupported"},
])
def test_invalid_request_is_rejected_before_http(transport, kwargs):
    with pytest.raises(ValueError):
        llm.call_llm(**kwargs)
    transport.assert_not_called()


def test_invalid_schema_is_rejected_before_http(transport):
    with pytest.raises(SchemaError):
        llm.call_llm("Extract tasks", _schema={"type": "not-a-json-type"})
    transport.assert_not_called()
