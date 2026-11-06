"""
Integration test suite: Document Conversion & Meeting Storage Pipeline (Converter <-> Storage).

Validates the full pre-meeting ingestion pipeline:
1. Meeting directory creation via StorageManager.
2. Conversion of raw documents (.pdf, .docx) via MarkDownConverter.
3. Ingestion into Document abstraction layer.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from backend.document.document import Document
from backend.document.markdown_converter import (
    FileConversionError,
    MarkDownConverter,
)
from backend.meeting_manager.storage_manager import StorageManager


@pytest.fixture
def storage(tmp_path: Path) -> StorageManager:
    """Fixture providing an isolated StorageManager instance."""
    return StorageManager(root_dir=tmp_path)


@pytest.fixture
def converter() -> MarkDownConverter:
    """Fixture providing a fresh MarkDownConverter instance."""
    return MarkDownConverter()


class TestUploadToMeetingStorageIntegration:
    """Integration test suite connecting Document Converter with Meeting Storage."""

    def test_upload_and_convert_flow_into_meeting_storage(
        self, storage: StorageManager, converter: MarkDownConverter, tmp_path: Path
    ) -> None:
        """
        INT-DOC-01: Verifies that uploading a document into an active meeting
        correctly routes converted markdown into the meeting's pre_meeting storage.
        """
        # Arrange
        meeting_id = "test_meeting_ingest_01"
        meeting_dirs = storage.create_meeting_directory(meeting_id)
        # Resolve concrete physical directory path from meeting_id
        pre_meeting_dir = tmp_path / meeting_id / "pre_meeting"

        raw_doc_path = tmp_path / "segment_tree_agenda.docx"
        raw_doc_path.write_bytes(b"PK\x03\x04MockDocxContent")

        mock_converted_text = (
            "# Segment Tree Meeting Agenda\n\n"
            "1. Introduction to Segment Tree O(log N)\n"
            "2. Range Minimum Query (RMQ)\n"
            "3. Lazy Propagation Techniques\n"
        )

        # Act
        target_md_path = pre_meeting_dir / "agenda.md"
        with patch.object(
            converter._converter,
            "convert",
            return_value=MagicMock(text_content=mock_converted_text),
        ):
            result_path = converter.convert(
                input_path=raw_doc_path, output_path=target_md_path
            )

        # Assert
        assert result_path == target_md_path.resolve()
        assert target_md_path.exists()
        assert target_md_path.read_text(encoding="utf-8") == mock_converted_text

    def test_upload_corrupted_file_does_not_pollute_storage(
        self, storage: StorageManager, converter: MarkDownConverter, tmp_path: Path
    ) -> None:
        """
        INT-DOC-02: Uploading an unparseable or corrupted file must raise
        FileConversionError and must NOT leave partial or empty markdown artifacts.
        """
        # Arrange
        meeting_id = "test_meeting_faulty_doc"
        storage.create_meeting_directory(meeting_id)
        pre_meeting_dir = tmp_path / meeting_id / "pre_meeting"

        corrupt_doc = tmp_path / "corrupt_file.pdf"
        corrupt_doc.write_bytes(b"%PDF-corrupted-bytes")
        target_md_path = pre_meeting_dir / "failed_output.md"

        # Act & Assert
        with patch.object(
            converter._converter,
            "convert",
            side_effect=Exception("Unparseable PDF stream"),
        ):
            with pytest.raises(FileConversionError):
                converter.convert(corrupt_doc, target_md_path)

        assert not target_md_path.exists(), "Storage must not contain partially written files on conversion failure"

    def test_converted_markdown_is_loadable_by_document_manager(
        self, storage: StorageManager, converter: MarkDownConverter, tmp_path: Path
    ) -> None:
        """
        INT-DOC-03: Converted markdown files must seamlessly bind to the Document
        abstraction layer for display and editing.
        """
        # Arrange
        meeting_id = "test_meeting_doc_bind"
        storage.create_meeting_directory(meeting_id)
        target_md = tmp_path / meeting_id / "pre_meeting" / "overview.md"
        dummy_content = "# Meeting Overview\nDiscussion on project architecture."
        
        with patch.object(
            converter._converter,
            "convert",
            return_value=MagicMock(text_content=dummy_content),
        ):
            fake_input = tmp_path / "overview.docx"
            fake_input.write_bytes(b"PK\x03\x04")
            converter.convert(fake_input, target_md)

        # Act
        doc = Document()
        loaded_text = doc.load(str(target_md))

        # Assert
        assert doc.has_path is True
        assert doc.path == str(target_md)
        assert loaded_text == dummy_content
