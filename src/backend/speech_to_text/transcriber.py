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

    def transcribe_file(
        self,
        audio_path: str | Path,
        output_path: str | Path | None = "transcript.txt",
    ) -> list[dict[str, str]]:
        path = Path(audio_path)

        if not path.is_file():
            raise FileNotFoundError(f"Audio file not found: {path}")

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
            raise AudioTranscriptionError("Transcription request timed out") from exc
        except requests.RequestException as exc:
            raise AudioTranscriptionError("Unable to connect to ElevenLabs") from exc

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
            raise AudioTranscriptionError("No transcript returned by ElevenLabs")

        segments = self.transcriber_parser(result)

        # Keep a readable copy for the minutes generator, which reads this file.
        if output_path is not None:
            txt_path = Path(output_path)
            if txt_path.parent and str(txt_path.parent) not in ("", "."):
                txt_path.parent.mkdir(parents=True, exist_ok=True)
            formatted_transcript = "\n\n".join(
                f"[{segment['Timestamp']}] {segment['Speaker']}:\n{segment['Text']}"
                for segment in segments
            )
            txt_path.write_text(formatted_transcript, encoding="utf-8")

        return segments

    # No API key or instance state is needed, so the parser can be tested alone.
    @staticmethod
    def transcriber_parser(result: dict) -> list[dict[str, str]]:
        """Return one Timestamp/Speaker/Text dict per consecutive speaker turn.

        Timestamp uses MM:SS.cc - MM:SS.cc relative to the audio file start.
        Missing speaker labels or times are represented by "unknown".
        """
        def format_time(seconds: float | None) -> str:
            # Zero would falsely place missing timing at the recording start.
            if seconds is None:
                return "unknown"

            # Round first so 59.999 becomes 01:00.00 rather than 00:60.00.
            centiseconds = round(seconds * 100)
            # Integer arithmetic avoids floating-point errors when splitting time.
            minutes, remainder = divmod(centiseconds, 6000)
            whole_seconds, fraction = divmod(remainder, 100)
            return f"{minutes:02d}:{whole_seconds:02d}.{fraction:02d}"

        # A list keeps A -> B -> A as three turns instead of merging A's speech.
        turns = []

        # Missing word metadata should still allow the full-text fallback below.
        for item in result.get("words") or []:
            token_type = item.get("type")

            if token_type == "spacing":
                # Preserve supplied spaces so words do not run together.
                if turns:
                    turns[-1]["parts"].append(item.get("text", " "))
                continue

            # Downstream features need spoken words, not sound descriptions.
            if token_type != "word":
                continue

            # Do not guess who spoke when the API supplies no speaker label.
            speaker = item.get("speaker_id") or "unknown"

            # A returning speaker still needs a new turn to preserve dialogue order.
            if not turns or speaker != turns[-1]["speaker"]:
                turns.append({
                    "speaker": speaker,
                    "start": item.get("start"),
                    "end": None,
                    "parts": [],
                })

            turns[-1]["parts"].append(item.get("text", ""))
            # The last word determines when the entire turn ends.
            turns[-1]["end"] = item.get("end")

        # Hide temporary grouping fields so callers depend only on the agreed keys.
        segments = [
            {
                "Timestamp": (
                    f"{format_time(turn['start'])} - "
                    f"{format_time(turn['end'])}"
                ),
                "Speaker": turn["speaker"],
                # Spaces already come from the API; only outer whitespace is unwanted.
                "Text": "".join(turn["parts"]).strip(),
            }
            for turn in turns
        ]

        # Preserve usable text without inventing missing timing or speaker metadata.
        if not segments and (result.get("text") or "").strip():
            segments.append({
                "Timestamp": "unknown",
                "Speaker": "unknown",
                "Text": result["text"].strip(),
            })

        return segments
