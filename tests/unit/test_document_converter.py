"""
Unit test suite for Document Ingestion & Converter (Phước Toàn - Pre-meeting).

Covers:
- TC-TOAN-01: Document conversion from .pdf/.docx to Markdown (.md)
- TC-TOAN-02: Automatic creation of storage and reading directory structure
- TC-TOAN-03: Handling corrupt, empty, or unsupported file formats

Status: Skeleton defined. Blocked by implementation in src/document/.
"""

import pytest


@pytest.mark.skip(reason="Awaiting Phuoc Toan's converter module in src/document/")
class TestDocumentConverter:
    """
    Unit tests validating document ingestion, directory isolation,
    and conversion fidelity before a meeting starts.
    """

    def test_convert_pdf_to_markdown_preserves_content(self):
        """
        TC-TOAN-01: Upload and convert a valid PDF/DOCX to Markdown.
        Expected: Original saved in archive folder, .md produced in reading folder
        with text content fully preserved.
        """
        pass

    def test_auto_create_directories_when_missing(self):
        """
        TC-TOAN-02: If target storage folders do not exist, the module must
        re-create them automatically without raising FileNotFoundError.
        """
        pass

    def test_reject_corrupt_or_unsupported_file(self):
        """
        TC-TOAN-03: Uploading an unsupported file (.exe) or an empty 0-byte file
        must be rejected with a user-facing warning; no corrupted .md produced.
        """
        pass