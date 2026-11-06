"""
End-to-End (E2E) Test Suite: Full Meeting Lifecycle Pipeline.

Validates the complete, sequential data flow across all three IPO stages:
1. Pre-Meeting: Initialize UUIDv4 workspace (7 folders) and convert agenda (.docx -> .md).
2. In-Meeting: Record 44.1kHz PCM audio (.wav) and transcribe via STT into transcript storage.
3. Post-Meeting: Synthesize audited minutes ([CONFIRMED]/[UNCONFIRMED]), review in Editor, and persist.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import numpy as np
import pytest

from backend.audio.recorder import CHANNELS, MAX_SECONDS, SAMPLE_RATE, Recorder
from backend.document.document import Document
from backend.document.markdown_converter import MarkDownConverter
from backend.meeting_manager.meeting_manager import MeetingManager
from backend.meeting_manager.storage_manager import StorageManager
from backend.speech_to_text.transcriber import ElevenLabsTranscriber


class TestFullPipelineE2E:
    """End-to-End validation of the complete Meeting Intelligence Assistant lifecycle."""

    def test_full_meeting_lifecycle_flow(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """
        E2E-LFC-01: Executes a complete simulated meeting session from workspace creation
        and document ingestion through live audio capture, STT transcription, and
        human-in-the-loop post-meeting minutes approval.
        """
        # Isolate side-effects (such as transcript.json) inside tmp_path
        monkeypatch.chdir(tmp_path)
        # =====================================================================
        # STAGE 1: PRE-MEETING (Workspace Initialization & Document Ingestion)
        # =====================================================================
        storage = StorageManager(root_dir=tmp_path)
        manager = MeetingManager(storage=storage)
        context = manager.create_meeting()

        # Verify isolated workspace and all 7 canonical subdirectories exist
        assert context.meeting_dir.is_dir()
        uploaded_dir = context.pre_meeting_dir / "uploaded"
        processed_dir = context.pre_meeting_dir / "processed"
        audio_dir = context.during_meeting_dir / "audio"
        transcript_dir = context.during_meeting_dir / "transcript"
        minutes_dir = context.post_meeting_dir / "meeting_minutes"

        for folder in (uploaded_dir, processed_dir, audio_dir, transcript_dir, minutes_dir):
            assert folder.is_dir(), f"Missing lifecycle directory: {folder}"

        # Upload raw agenda and convert to standardized Markdown
        raw_agenda = uploaded_dir / "sprint_planning.docx"
        raw_agenda.write_bytes(b"PK\x03\x04MockDocxBinary")
        processed_agenda = processed_dir / "sprint_planning.md"

        agenda_markdown = (
            "# Sprint Planning Agenda\n\n"
            "1. Review Pre-Meeting Ingestion\n"
            "2. Finalize STT & Analyzer Integration\n"
        )
        converter = MarkDownConverter()
        with patch.object(
            converter._converter,
            "convert",
            return_value=MagicMock(text_content=agenda_markdown),
        ):
            converter.convert(input_path=raw_agenda, output_path=processed_agenda)

        assert processed_agenda.exists()
        assert processed_agenda.read_text(encoding="utf-8") == agenda_markdown

        # =====================================================================
        # STAGE 2: IN-MEETING (44.1kHz Audio Capture & STT Transcription)
        # =====================================================================
        recorder = Recorder()
        meeting_wav = audio_dir / "session_recording.wav"
        dummy_pcm_buffer = np.zeros((MAX_SECONDS * SAMPLE_RATE, CHANNELS), dtype=np.int16)

        with patch("sounddevice.rec", return_value=dummy_pcm_buffer), \
             patch("sounddevice.stop"), \
             patch("time.time", side_effect=[1000.0, 1003.0, 1003.0]), \
             patch("time.monotonic", side_effect=[1000.0, 1003.0, 1003.0]):
            recorder.start()
            assert recorder.is_recording is True
            duration = recorder.stop(path=str(meeting_wav))

        assert recorder.is_recording is False
        assert duration == 3.0
        assert meeting_wav.exists()
        assert meeting_wav.stat().st_size > 0

        # Hand over recorded WAV to ElevenLabsTranscriber
        transcriber = ElevenLabsTranscriber(api_key="e2e-mock-api-key")
        transcript_file = transcript_dir / "session_transcript.txt"

        mock_stt_json = {
            "text": "Phước Toàn đã hoàn thành Storage. Cần một bạn viết thêm E2E test trước thứ Sáu.",
            "words": [
                {"word": "Phước", "start": 0.1, "end": 0.4, "speaker_id": "speaker_0"},
                {"word": "Toàn", "start": 0.4, "end": 0.8, "speaker_id": "speaker_0"},
            ],
        }
        mock_http_resp = MagicMock(ok=True)
        mock_http_resp.json.return_value = mock_stt_json

        with patch("backend.speech_to_text.transcriber.requests.post", return_value=mock_http_resp):
            transcript_text = transcriber.transcribe_file(
                audio_path=meeting_wav, output_path=transcript_file
            )

        assert transcript_file.exists()
        assert "Phước Toàn" in transcript_text

        # =====================================================================
        # STAGE 3: POST-MEETING (Audit Synthesis, Human Review & Persistence)
        # =====================================================================
        # Simulate Analyzer generating audited draft minutes from the transcript & agenda
        draft_minutes_path = minutes_dir / "draft_minutes.md"
        final_minutes_path = minutes_dir / "final_minutes.md"

        draft_minutes_content = (
            f"# BIÊN BẢN CUỘC HỌP (ID: {context.meeting_id})\n\n"
            "## Tóm Tắt Nội Dung\n"
            f"- Đối chiếu từ Agenda: {processed_agenda.name}\n"
            "- Phước Toàn đã hoàn thành module Storage.\n\n"
            "## Danh Sách Công Việc (Audited Action Items)\n"
            "- [ ] [UNCONFIRMED] Viết thêm E2E test | Phụ trách: NULL | Hạn: Thứ Sáu\n"
        )
        draft_minutes_path.write_text(draft_minutes_content, encoding="utf-8")

        # Load draft minutes into Document Editor for Human-in-the-Loop sign-off
        editor = Document()
        loaded_draft = editor.load(str(draft_minutes_path))
        assert editor.has_path is True
        assert "[UNCONFIRMED]" in loaded_draft

        # Human reviewer resolves the missing owner and exports finalized minutes
        approved_minutes_content = loaded_draft.replace(
            "- [ ] [UNCONFIRMED] Viết thêm E2E test | Phụ trách: NULL",
            "- [x] [CONFIRMED] Viết thêm E2E test | Phụ trách: Đoàn Khánh Hưng",
        )
        editor.save(approved_minutes_content, path=str(final_minutes_path))

        # Final end-to-end assertions
        assert final_minutes_path.exists()
        assert editor.path == str(final_minutes_path)
        final_persisted_text = final_minutes_path.read_text(encoding="utf-8")
        assert "[CONFIRMED] Viết thêm E2E test | Phụ trách: Đoàn Khánh Hưng" in final_persisted_text
        assert "UNCONFIRMED" not in final_persisted_text
        