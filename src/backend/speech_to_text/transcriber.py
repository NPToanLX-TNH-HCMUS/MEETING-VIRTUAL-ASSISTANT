import os
import json
import wave
from pathlib import Path

import requests
from dotenv import load_dotenv

load_dotenv()

API_URL = "https://api.elevenlabs.io/v1/speech-to-text"
DEFAULT_MODEL_ID = "scribe_v2"
DEFAULT_TIMEOUT = 180


class AudioTranscriptionError(Exception):
    """Raised when audio transcription fails."""

    def __init__(
        self,
        message: str,
        reason: str = "unknown",
        status_code: int | None = None,
    ):
        super().__init__(message)
        self.reason = reason
        self.status_code = status_code


class ElevenLabsTranscriber:
    def __init__(
        self,
        api_key: str | None = None,
        timeout: int = DEFAULT_TIMEOUT,
    ) -> None:
        self._api_key = api_key or os.getenv("ELEVENLABS_API_KEY")
        self._timeout = timeout

        if not self._api_key:
            raise ValueError("Missing ELEVENLABS_API_KEY")

    def transcribe_file(self, audio_path: str | Path) -> str:
        path = Path(audio_path)

        if not path.is_file():
            raise FileNotFoundError(
                f"Audio file not found: {path}"
            )

        if path.suffix.lower() != ".wav":
            raise ValueError("Only WAV files are supported")

        # Reject invalid or empty WAV files before making a
        # paid API request.
        try:
            with wave.open(str(path), "rb") as wav:
                if wav.getnframes() == 0:
                    raise ValueError("Audio file is empty")
        except wave.Error as exc:
            raise ValueError("Invalid WAV file") from exc

        try:
            with path.open("rb") as audio_file:
                response = requests.post(
                    API_URL,
                    headers={
                        "xi-api-key": self._api_key,
                    },
                    files={
                        "file": (
                            path.name,
                            audio_file,
                            "audio/wav",
                        ),
                    },
                    
                    data={
                        "model_id": DEFAULT_MODEL_ID,
                        "language_code": "eng",
                        "diarize": "true",
                        "timestamps_granularity": "word",
                        "tag_audio_events": "false",
                    },

                    timeout=self._timeout,
                )
        except requests.Timeout as exc:
            raise AudioTranscriptionError(
                "Transcription request timed out"
            ) from exc
        except requests.RequestException as exc:
            raise AudioTranscriptionError(
                "Unable to connect to ElevenLabs"
            ) from exc

        if not response.ok:
            raise AudioTranscriptionError(
                f"ElevenLabs API returned HTTP {response.status_code}"
            )

        try:
            result = response.json()
        except ValueError as exc:
            raise AudioTranscriptionError(
                "Invalid JSON response from ElevenLabs"
            ) from exc

        transcript = result.get("text")

        if not isinstance(transcript, str) or not transcript.strip():
            raise AudioTranscriptionError(
                "No transcript returned by ElevenLabs"
            )

        
        transcript = transcript.strip()

        # Save the complete API response for diarization
        # and timestamp processing.
        json_path = Path("transcript.json")
        json_path.write_text(
            json.dumps(result, ensure_ascii=False, indent=2),
            encoding="utf-8"
        )

        
        # Format transcript with speaker IDs and timestamps
        words = result.get("words", [])
        formatted_transcript = format_diarized_transcript(words)

        # Save the diarized transcript to TXT
        output_path = Path("transcript.txt")
        output_path.write_text(
            formatted_transcript or transcript,
            encoding="utf-8"
        )

        return transcript



def format_diarized_transcript(words: list[dict]) -> str:
    def format_time(seconds: float) -> str:
        minutes = int(seconds) // 60
        remaining = seconds % 60
        return f"{minutes:02d}:{remaining:05.2f}"

    segments = []
    current_speaker = None
    start_time = None
    end_time = None
    text_parts = []

    for item in words:
        token_type = item.get("type")

        # Preserve spaces returned by ElevenLabs.
        if token_type == "spacing":
            if text_parts:
                text_parts.append(item.get("text", " "))
            continue

        if token_type != "word":
            continue

        speaker = item.get("speaker_id") or "unknown"

        # A speaker change indicates a new segment.
        if speaker != current_speaker and text_parts:
            segments.append(
                f"[{format_time(start_time)} - "
                f"{format_time(end_time)}] "
                f"{current_speaker}:\n"
                f"{''.join(text_parts).strip()}"
            )
            text_parts = []

        if not text_parts:
            current_speaker = speaker
            start_time = item.get("start", 0)

        text_parts.append(item.get("text", ""))
        end_time = item.get("end", start_time)

    # Save the last speaker segment.
    if text_parts:
        segments.append(
            f"[{format_time(start_time)} - "
            f"{format_time(end_time)}] "
            f"{current_speaker}:\n"
            f"{''.join(text_parts).strip()}"
        )

    return "\n\n".join(segments)
