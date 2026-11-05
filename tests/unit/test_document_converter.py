"""
Unit test suite for Document Ingestion & Converter (Phước Toàn - Pre-meeting).

Covers:
- TC-TOAN-01: Document conversion from .pdf/.docx to Markdown (.md)
- TC-TOAN-02: Automatic creation of storage and reading directory structure
- TC-TOAN-03: Handling corrupt, empty, or unsupported file formats

Status: Skeleton defined. Blocked by implementation in src/document/.
"""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from backend.document.markdown_converter import (
    EmptyFileError,
    MarkDownConverter,
    UnsupportedFileTypeError,
)


@pytest.fixture
def converter() -> MarkDownConverter:
    """Fixture providing a fresh instance of MarkDownConverter for each test."""
    return MarkDownConverter()

class TestDocumentConverter:
    """
    Unit tests validating document ingestion, directory isolation,
    and conversion fidelity before a meeting starts.
    """

    def test_convert_pdf_to_markdown_preserves_content(self, converter: MarkDownConverter, tmp_path: Path) -> None:
        """
        TC-TOAN-01: Successfully convert .pdf/.docx to Markdown.
        Expectation: Output .md file preserves content and UTF-8 encoding.
        """
        # Arrange
        input_file = tmp_path / "sample_agenda.pdf"
        input_file.write_bytes(b"%PDF-1.4 dummy content")
        output_file = tmp_path / "converted_agenda.md"
        expected_markdown = "# Meeting Minutes\n\n- Architecture Discussion\n- Task Assignment"

        mock_result = MagicMock()
        mock_result.text_content = expected_markdown

        # Act
        with patch.object(converter._converter, "convert", return_value=mock_result):
            result_path = converter.convert(input_file, output_file)

        # Assert
        assert result_path == output_file.resolve()
        assert output_file.exists()
        assert output_file.read_text(encoding="utf-8") == expected_markdown

    def test_auto_create_directories_when_missing(
        self, converter: MarkDownConverter, tmp_path: Path
    ) -> None:
        """
        TC-TOAN-02: Auto-create directory tree if destination folder is missing.
        Expectation: No FileNotFoundError is raised when writing to a nested, non-existent path.
        """
        # Arrange
        input_file = tmp_path / "document.docx"
        input_file.write_bytes(b"PK dummy docx content")
        nested_output_file = tmp_path / "storage" / "processed" / "result.md"
        
        assert not nested_output_file.parent.exists()

        mock_result = MagicMock()
        mock_result.text_content = "# Document Content"

        # Act
        with patch.object(converter._converter, "convert", return_value=mock_result):
            converter.convert(input_file, nested_output_file)

        # Assert
        assert nested_output_file.parent.exists()
        assert nested_output_file.is_file()

    def test_reject_missing_file(
        self, converter: MarkDownConverter, tmp_path: Path
    ) -> None:
        """
        TC-TOAN-03a: Reject non-existent files.
        Expectation: Raises FileNotFoundError and creates no garbage output.
        """
        out_file = tmp_path / "output.md"
        non_existent_file = tmp_path / "ghost.pdf"

        with pytest.raises(FileNotFoundError, match="Input file not found"):
            converter.convert(non_existent_file, out_file)
            
        assert not out_file.exists()

    def test_reject_empty_file(
        self, converter: MarkDownConverter, tmp_path: Path
    ) -> None:
        """
        TC-TOAN-03b: Reject 0-byte (empty) files.
        Expectation: Raises EmptyFileError and creates no garbage output.
        """
        out_file = tmp_path / "output.md"
        empty_file = tmp_path / "empty.docx"
        empty_file.write_bytes(b"")

        with pytest.raises(EmptyFileError, match="Input file is empty"):
            converter.convert(empty_file, out_file)
            
        assert not out_file.exists()

    def test_reject_unsupported_file_format(
        self, converter: MarkDownConverter, tmp_path: Path
    ) -> None:
        """
        TC-TOAN-03c: Reject unsupported file formats (e.g., .exe).
        Expectation: Raises UnsupportedFileTypeError and creates no garbage output.
        """
        out_file = tmp_path / "output.md"
        unsupported_file = tmp_path / "malicious.exe"
        unsupported_file.write_bytes(b"MZ dummy executable")

        with pytest.raises(UnsupportedFileTypeError, match="Unsupported file type"):
            converter.convert(unsupported_file, out_file)
            
        assert not out_file.exists()