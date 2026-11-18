import tempfile
import unittest
import wave
from pathlib import Path
from unittest.mock import patch

from src.backend.speech_to_text.transcriber import ElevenLabsTranscriber


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
                        "speaker_id": "speaker_0",
                    },
                    {"text": " ", "type": "spacing"},
                    {
                        "text": "everyone.",
                        "start": 0.8,
                        "end": 1.5,
                        "type": "word",
                        "speaker_id": "speaker_0",
                    },
                ],
            }

            with (
                patch(
                    "src.backend.speech_to_text.transcriber.requests.post"
                ) as mock_post,
                patch("pathlib.Path.write_text") as mock_write,
            ):
                mock_post.return_value.ok = True
                mock_post.return_value.json.return_value = mock_response

                transcriber = ElevenLabsTranscriber(api_key="fake-test-key")

                result = transcriber.transcribe_file(audio_path)

                self.assertEqual(result, [{
                    "Timestamp": "00:00.50 - 00:01.50",
                    "Speaker": "speaker_0",
                    "Text": "Hello everyone.",
                }])
                mock_post.assert_called_once()

                mock_write.assert_called_once_with(
                    "[00:00.50 - 00:01.50] speaker_0:\nHello everyone.",
                    encoding="utf-8",
                )

    def test_file_not_found(self):
        transcriber = ElevenLabsTranscriber(api_key="fake-test-key")

        with self.assertRaises(FileNotFoundError):
            transcriber.transcribe_file("nonexistent_audio.wav")


class TestTranscriberParser(unittest.TestCase):
    def test_keeps_speaker_turns_spacing_and_audio_timing(self):
        result = ElevenLabsTranscriber.transcriber_parser({"words": [
            {"type": "spacing", "text": " "},
            {"type": "word", "text": "Hello,", "speaker_id": "speaker_0", "start": 0, "end": 0.4},
            {"type": "spacing", "text": " "},
            {"type": "word", "text": "everyone.", "speaker_id": "speaker_0", "start": 0.5, "end": 1},
            {"type": "audio_event", "text": "(laughter)"},
            {"type": "spacing", "text": " "},
            {"type": "word", "text": "Hi!", "speaker_id": "speaker_1", "start": 2, "end": 3},
            {"type": "word", "text": "Welcome.", "speaker_id": "speaker_0", "start": 4, "end": 5},
        ]})

        self.assertEqual(result, [
            {"Timestamp": "00:00.00 - 00:01.00", "Speaker": "speaker_0", "Text": "Hello, everyone."},
            {"Timestamp": "00:02.00 - 00:03.00", "Speaker": "speaker_1", "Text": "Hi!"},
            {"Timestamp": "00:04.00 - 00:05.00", "Speaker": "speaker_0", "Text": "Welcome."},
        ])

    def test_rounds_across_minute_boundary(self):
        result = ElevenLabsTranscriber.transcriber_parser({"words": [
            {"type": "word", "text": "Hello", "start": 59.999, "end": 60.125},
        ]})

        self.assertEqual(result[0]["Timestamp"], "01:00.00 - 01:00.12")

    def test_missing_metadata_is_not_fabricated(self):
        self.assertEqual(
            ElevenLabsTranscriber.transcriber_parser({"words": [
                {"type": "word", "text": "Hello"},
            ]}),
            [{"Timestamp": "unknown - unknown", "Speaker": "unknown", "Text": "Hello"}],
        )

    def test_preserves_text_without_word_metadata(self):
        for words in (None, []):
            with self.subTest(words=words):
                self.assertEqual(
                    ElevenLabsTranscriber.transcriber_parser({"text": " Hello ", "words": words}),
                    [{"Timestamp": "unknown", "Speaker": "unknown", "Text": "Hello"}],
                )

    def test_empty_response_has_no_turns(self):
        self.assertEqual(ElevenLabsTranscriber.transcriber_parser({}), [])


if __name__ == "__main__":
    unittest.main()
