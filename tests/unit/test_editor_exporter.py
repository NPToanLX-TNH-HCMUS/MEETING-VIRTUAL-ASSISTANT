"""
Unit test suite for Document Editor & PDF Exporter (Khanh Ann - Post-meeting).

Covers:
- TC-ANN-01: Loading Markdown documents with strictly preserved Vietnamese UTF-8 encoding.
- TC-ANN-02: In-place text modification, save-overwrite, and 'Save As' path branching.
- TC-ANN-03: Guard clauses for unloaded buffer states and non-existent file paths.
- TC-ANN-04: Exporting final edited minutes to a valid .pdf binary (Awaiting PDF engine).
"""

from pathlib import Path

import pytest

from backend.document.document import Document


@pytest.fixture
def document_manager() -> Document:
    """Fixture providing a fresh, isolated Document instance for each test case."""
    return Document()


class TestEditorExporter:
    """
    Unit tests validating document loading, UTF-8 text integrity,
    buffer mutations, state guards, and export capabilities.
    """

    def test_load_markdown_preserves_vietnamese_utf8(
        self, document_manager: Document, tmp_path: Path
    ) -> None:
        """
        TC-ANN-01: Loading a Markdown report must transition state from Unloaded to Loaded
        and preserve all Vietnamese diacritics (ă, â, đ, ê, ô, ơ, ư), tonal marks, and tables.
        """
        # Arrange: Verify initial Unloaded state
        assert document_manager.has_path is False

        sample_file = tmp_path / "bien_ban_cuoc_hop.md"
        raw_vietnamese_content = (
            "# BIÊN BẢN CUỘC HỌP DỰ ÁN MIA\n\n"
            "**Thời gian:** 10:00 AM ngày 05 tháng 11 năm 2026\n"
            "**Chủ trì:** Đăng Khôi\n\n"
            "## 1. Nội Dung Thảo Luận\n"
            "- Thảo luận kiến trúc hệ thống nhận diện giọng nói và phân tích nội dung.\n"
            "- Đảm bảo không lỗi font chữ: Tiếng Việt có dấu, chữ hoa chữ thường: "
            "Ă, Â, Đ, Ê, Ô, Ơ, Ư, ắ, ằ, ẳ, ẵ, ặ, ấ, ầ, ẩ, ẫ, ậ, ữ, ự.\n\n"
            "| Người nhận | Nhiệm vụ | Hạn chót | Trạng thái |\n"
            "|---|---|---|---|\n"
            "| Khánh Ann | Hoàn thiện Document Editor | 15/11/2026 | Đang xử lý |\n"
        )
        sample_file.write_text(raw_vietnamese_content, encoding="utf-8")

        # Act: Load the document into memory
        loaded_content = document_manager.load(str(sample_file))

        # Assert: State transition and 100% UTF-8 fidelity
        assert document_manager.has_path is True
        assert document_manager.path == str(sample_file)
        assert loaded_content == raw_vietnamese_content
        assert "Khánh Ann" in loaded_content
        assert "Đang xử lý" in loaded_content

    def test_save_modified_document_in_place_and_save_as(
        self, document_manager: Document, tmp_path: Path
    ) -> None:
        """
        TC-ANN-02: Editing an unconfirmed task to assign an owner, then saving,
        must overwrite the original file in-place or branch to a new file on 'Save As'.
        """
        # Arrange: Create and load initial document with an unassigned action item
        doc_path = tmp_path / "action_items.md"
        initial_text = (
            "# Action Items\n\n"
            "- [ ] Task 1: Chưa phân công | Deadline: Chưa xác định\n"
        )
        doc_path.write_text(initial_text, encoding="utf-8")
        document_manager.load(str(doc_path))

        # Act 1: Simulate human reviewer resolving the task and performing in-place Save
        updated_text = (
            "# Action Items\n\n"
            "- [x] Task 1: Phước Toàn phụ trách | Deadline: 20/11/2026\n"
        )
        document_manager.save(updated_text)

        # Assert 1: In-place overwrite verified on disk
        persisted_content = doc_path.read_text(encoding="utf-8")
        assert persisted_content == updated_text
        assert document_manager.path == str(doc_path)

        # Act 2: Perform 'Save As' to a new target path
        new_doc_path = tmp_path / "archived_action_items.md"
        document_manager.save(updated_text, path=str(new_doc_path))

        # Assert 2: New file is created, active path switches to new target, original remains intact
        assert new_doc_path.exists()
        assert document_manager.has_path is True
        assert document_manager.path == str(new_doc_path)
        assert new_doc_path.read_text(encoding="utf-8") == updated_text
        assert doc_path.read_text(encoding="utf-8") == updated_text

    def test_unloaded_state_and_missing_file_guards(
        self, document_manager: Document, tmp_path: Path
    ) -> None:
        """
        TC-ANN-03: Verifies that loading a non-existent file raises FileNotFoundError
        and saving without an active path or target raises ValueError.
        """
        # 1. Attempting to load a ghost file must fail cleanly and keep has_path False
        missing_file = tmp_path / "non_existent_minutes.md"
        with pytest.raises(FileNotFoundError):
            document_manager.load(str(missing_file))

        assert document_manager.has_path is False

        # 2. Attempting in-place save when no file is loaded must raise an error
        with pytest.raises((ValueError, TypeError)):
            document_manager.save("Orphaned text content without target path")

    @pytest.mark.skip(
        reason="Awaiting Khanh Ann's PDF export engine integration (e.g., ReportLab / WeasyPrint)"
    )
    def test_export_to_pdf_generates_valid_binary_header(
        self, document_manager: Document, tmp_path: Path
    ) -> None:
        """
        TC-ANN-04: Exporting the active document to PDF must generate a non-empty
        binary file starting with the standard '%PDF-' magic bytes.
        """
        # Arrange
        md_source = tmp_path / "final_minutes.md"
        pdf_output = tmp_path / "final_minutes.pdf"
        md_source.write_text("# Biên Bản Họp Tổng Kết\n\nNội dung tiếng Việt.", encoding="utf-8")
        document_manager.load(str(md_source))

        # Act (Uncomment/adjust method name once implemented in Document class)
        document_manager.export_pdf(str(pdf_output))

        # Assert: Verify file existence, size > 0, and PDF magic header
        assert pdf_output.exists()
        assert pdf_output.stat().st_size > 0
        with pdf_output.open("rb") as f:
            header_bytes = f.read(5)
        assert header_bytes == b"%PDF-"
        