"""
STAGE 2 (during meeting): record audio and transcribe it.

    POST /api/v1/meetings/{id}/recording/start   microphone on            ready -> live
    POST /api/v1/meetings/{id}/recording/stop    save record.wav          live  -> processing
    POST /api/v1/meetings/{id}/transcribe        ElevenLabs STT + diarization
"""

from fastapi import APIRouter

from ..audio.recorder import Recorder
from ..speech_to_text.transcriber import AudioTranscriptionError, ElevenLabsTranscriber
from ..utils.objects import Meeting
from ..utils.utils import error, now
from .common import SessionDep, meeting_response

router = APIRouter(prefix="/meetings/{meeting_id}", tags=["during-meeting"])

AUDIO_FILE = "during_meeting/audio/record.wav"
TRANSCRIPT_FILE = "during_meeting/transcript/transcript.txt"


@router.post("/recording/start", response_model=Meeting)
def start_recording(session: SessionDep):
    with session:
        if session.status != "ready":
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Cannot start recording while the meeting is {session.status}",
            )
        try:
            recorder = Recorder()
            recorder.start()
        except Exception as exc:  # sounddevice raises PortAudioError when there is no microphone / no permission
            return error(500, "RECORDER_FAILED", str(exc))
        session.emplace("recorder", recorder)
        session.status = "live"
        session.at("meeting")["started_at"] = now()
        return meeting_response(session)


@router.post("/recording/stop", response_model=Meeting)
def stop_recording(session: SessionDep):
    with session:
        recorder = session.get("recorder")
        if session.status != "live" or recorder is None:
            return error(
                409,
                "INVALID_MEETING_STATE",
                f"Cannot stop recording while the meeting is {session.status}",
            )
        recorder.stop(str(session.path(AUDIO_FILE)))
        session.pop("recorder")
        session.status = "processing"
        session.at("meeting")["ended_at"] = now()
        return meeting_response(session)


@router.post("/transcribe")
def transcribe_recording(session: SessionDep):
    with session:
        audio = session.path(AUDIO_FILE)
        if not audio.is_file():
            return error(
                409, "INVALID_MEETING_STATE", "There is no recording to transcribe yet"
            )
        transcript_path = session.path(TRANSCRIPT_FILE)

    # The STT request can take a while, so it runs outside the session lock.
    try:
        segments = ElevenLabsTranscriber().transcribe_file(audio, transcript_path)
    except ValueError as exc:  # missing ELEVENLABS_API_KEY, empty or invalid wav
        return error(422, "TRANSCRIPTION_INPUT_INVALID", str(exc))
    except AudioTranscriptionError as exc:
        return error(502, "TRANSCRIPTION_FAILED", str(exc))

    # Format speaker turns here so the frontend can display the string directly.
    text = "\n\n".join(
        f"[{segment['Timestamp']}] {segment['Speaker']}:\n{segment['Text']}"
        for segment in segments
    )

    with session:
        session.emplace("transcript", segments)
        session.emplace("transcript_text", text)
    return {"transcript": text}
