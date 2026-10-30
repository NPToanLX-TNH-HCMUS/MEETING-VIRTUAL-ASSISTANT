
import os
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
                        "language_code": "vie",
                        "diarize": "false",
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

        # Save the transcription to a text file
        output_path = Path("transcript.txt")
        output_path.write_text(transcript, encoding="utf-8")

        return transcript
