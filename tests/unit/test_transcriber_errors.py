"""Failures must stay inside the error types handled by the transcription API."""

import wave
from unittest.mock import Mock

import pytest
import requests

from src.backend.speech_to_text import transcriber as stt


@pytest.fixture
def audio(tmp_path):
    path = tmp_path / "input.wav"
    with wave.open(str(path), "wb") as stream:
        stream.setnchannels(1)
        stream.setsampwidth(2)
        stream.setframerate(16000)
        stream.writeframes(b"\x00\x00" * 160)
    return path


@pytest.mark.parametrize("payload", [None, []])
def test_wrong_json_envelope_is_a_transcription_error(audio, monkeypatch, payload):
    response = Mock(spec=requests.Response)
    response.ok = True
    response.json.return_value = payload
    monkeypatch.setattr(stt.requests, "post", Mock(return_value=response))
    with pytest.raises(stt.AudioTranscriptionError):
        stt.ElevenLabsTranscriber(api_key="unit-key").transcribe_file(audio, output_path=None)


def test_invalid_http_json_is_a_transcription_error(audio, monkeypatch):
    response = Mock(spec=requests.Response)
    response.ok = True
    response.json.side_effect = ValueError("invalid JSON")
    monkeypatch.setattr(stt.requests, "post", Mock(return_value=response))
    with pytest.raises(stt.AudioTranscriptionError, match="Invalid JSON"):
        stt.ElevenLabsTranscriber(api_key="unit-key").transcribe_file(audio, output_path=None)


@pytest.mark.parametrize("status", [429, 503])
def test_failed_provider_does_not_overwrite_previous_transcript(audio, tmp_path, monkeypatch, status):
    response = Mock(spec=requests.Response)
    response.ok = False
    response.status_code = status
    monkeypatch.setattr(stt.requests, "post", Mock(return_value=response))
    target = tmp_path / "transcript.txt"
    target.write_text("Keep previous transcript", encoding="utf-8")
    with pytest.raises(stt.AudioTranscriptionError):
        stt.ElevenLabsTranscriber(api_key="unit-key").transcribe_file(audio, target)
    assert target.read_text(encoding="utf-8") == "Keep previous transcript"


def test_truncated_wav_is_invalid_input_not_an_unhandled_eof(tmp_path, monkeypatch):
    path = tmp_path / "truncated.wav"
    path.write_bytes(b"RIFF")
    post = Mock()
    monkeypatch.setattr(stt.requests, "post", post)
    # The route handles ValueError for invalid audio; EOFError currently escapes it.
    with pytest.raises(ValueError, match="Invalid WAV"):
        stt.ElevenLabsTranscriber(api_key="unit-key").transcribe_file(path, output_path=None)
    post.assert_not_called()


def test_missing_key_fails_before_network():
    with pytest.raises(ValueError, match="Missing ELEVENLABS_API_KEY"):
        stt.ElevenLabsTranscriber()
