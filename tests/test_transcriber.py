
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from src.speech_to_text.transcriber import ElevenLabsTranscriber


class TestElevenLabsTranscriber(unittest.TestCase):

    def test_transcribe_success(self):
        # Create a temporary valid WAV file
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "test.wav"

            with wave.open(str(audio_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 1600)

            # Mock API and file output to avoid real requests
            with patch(
                "src.speech_to_text.transcriber.requests.post"
            ) as mock_post, patch(
                "pathlib.Path.write_text"
            ) as mock_write:

                mock_post.return_value.ok = True
                mock_post.return_value.json.return_value = {
                    "text": "Xin chào, đây là cuộc họp."
                }

                transcriber = ElevenLabsTranscriber(
                    api_key="fake-test-key"
                )

                result = transcriber.transcribe_file(audio_path)

                self.assertEqual(
                    result,
                    "Xin chào, đây là cuộc họp."
                )
                mock_post.assert_called_once()
                mock_write.assert_called_once_with(
                    "Xin chào, đây là cuộc họp.",
                    encoding="utf-8"
                )

    def test_file_not_found(self):
        transcriber = ElevenLabsTranscriber(
            api_key="fake-test-key"
        )

        with self.assertRaises(FileNotFoundError):
            transcriber.transcribe_file(
                "nonexistent_audio.wav"
            )


if __name__ == "__main__":
    unittest.main()
