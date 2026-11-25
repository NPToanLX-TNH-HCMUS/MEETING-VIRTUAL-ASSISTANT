import unittest

from src.backend.speech_to_text.segments import (
    ActiveClock,
    confidence_from_logprobs,
    from_batch,
    make_segment,
    parse_range,
)
from src.backend.speech_to_text.transcriber import ElevenLabsTranscriber


class TestSegments(unittest.TestCase):
    def test_parse_range(self):
        self.assertEqual(parse_range("01:02.50 - 01:05.00"), (62.5, 65.0))
        for bad in ("unknown", "unknown - unknown", "", None):
            self.assertEqual(parse_range(bad), (None, None))

    def test_from_batch_numbers_ids_and_keeps_unknown_as_none(self):
        turns = [
            {"Timestamp": "00:00.50 - 00:01.50", "Speaker": "speaker_0", "Text": "Xin chào"},
            {"Timestamp": "unknown", "Speaker": "unknown", "Text": "Hi"},
        ]
        first, second = from_batch(turns, "mtg_1", "vi")
        self.assertEqual((first["id"], first["start_seconds"], first["end_seconds"]), ("seg_001", 0.5, 1.5))
        self.assertEqual(first["speaker"], "speaker_0")
        self.assertEqual(first["text"], "Xin chào")
        self.assertEqual((second["id"], second["start_seconds"], second["speaker"]), ("seg_002", None, None))

    def test_low_confidence_flag(self):
        self.assertTrue(make_segment("m", 1, "t", "vi", confidence=0.3)["is_low_confidence"])
        self.assertFalse(make_segment("m", 1, "t", "vi", confidence=0.9)["is_low_confidence"])
        # Unknown confidence is not treated as low.
        self.assertFalse(make_segment("m", 1, "t", "vi")["is_low_confidence"])

    def test_parser_confidence_only_with_logprobs(self):
        words = [
            {"type": "word", "text": "Hi", "start": 0, "end": 1, "speaker_id": "s", "logprob": -2.0},
            {"type": "word", "text": "there", "start": 1, "end": 2, "speaker_id": "s", "logprob": -2.0},
        ]
        turn = ElevenLabsTranscriber.transcriber_parser({"words": words})[0]
        self.assertAlmostEqual(turn["Confidence"], 0.135, places=3)
        self.assertTrue(from_batch([turn], "m", "en")[0]["is_low_confidence"])
        self.assertIsNone(confidence_from_logprobs([]))

        no_logprob = ElevenLabsTranscriber.transcriber_parser(
            {"words": [{"type": "word", "text": "Hi", "start": 0, "end": 1}]}
        )
        self.assertNotIn("Confidence", no_logprob[0])


class TestActiveClock(unittest.TestCase):
    def test_paused_time_is_excluded(self):
        now = [100.0]
        clock = ActiveClock(lambda: now[0])
        self.assertIsNone(clock.seconds())
        clock.start()
        now[0] = 110.0
        self.assertEqual(clock.seconds(), 10.0)
        clock.pause()
        now[0] = 160.0  # 50 s paused
        self.assertEqual(clock.seconds(), 10.0)
        clock.resume()
        now[0] = 165.0
        self.assertEqual(clock.seconds(), 15.0)


if __name__ == "__main__":
    unittest.main()
