
import json
import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from src.speech_to_text.transcriber import ElevenLabsTranscriber


class TestElevenLabsTranscriber(unittest.TestCase):

    def test_transcribe_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            audio_path = Path(temp_dir) / "test.wav"

            with wave.open(str(audio_path), "wb") as wav:
                wav.setnchannels(1)
                wav.setsampwidth(2)
                wav.setframerate(16000)
                wav.writeframes(b"\x00\x00" * 1600)

            # Simulate the API response without using credits.
            mock_response = {
                "text": "Hello everyone.",
                "words": [
                    {
                        "text": "Hello",
                        "start": 0.5,
                        "end": 0.8,
                        "type": "word",
                        "speaker_id": "speaker_0"
                    },
                    {
                        "text": " ",
                        "type": "spacing"
                    },
                    {
                        "text": "everyone.",
                        "start": 0.8,
                        "end": 1.5,
                        "type": "word",
                        "speaker_id": "speaker_0"
                    }
                ]
            }

            with patch(
                "src.speech_to_text.transcriber.requests.post"
            ) as mock_post, patch(
                "pathlib.Path.write_text"
            ) as mock_write:

                mock_post.return_value.ok = True
                mock_post.return_value.json.return_value = mock_response

                transcriber = ElevenLabsTranscriber(
                    api_key="fake-test-key"
                )

                result = transcriber.transcribe_file(audio_path)

                self.assertEqual(result, "Hello everyone.")
                mock_post.assert_called_once()

                # Verify JSON and TXT were both saved.
                self.assertEqual(mock_write.call_count, 2)

                saved_json = json.loads(
                    mock_write.call_args_list[0].args[0]
                )

                self.assertEqual(
                    saved_json["words"][0]["speaker_id"],
                    "speaker_0"
                )

                mock_write.assert_any_call(
                    "[00:00.50 - 00:01.50] speaker_0:\nHello everyone.",
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
