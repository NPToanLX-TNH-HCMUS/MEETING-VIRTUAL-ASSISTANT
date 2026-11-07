from src.backend.speech_to_text.transcriber import ElevenLabsTranscriber

stt = ElevenLabsTranscriber()

string_sth = stt.transcribe_file("amthanh.wav")