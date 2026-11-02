import logging
from pathlib import Path

from markitdown import MarkItDown

logger = logging.getLogger(__name__)

SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".doc"}


class FileConversionError(Exception):
    """Base exception for file conversion errors."""


class UnsupportedFileTypeError(FileConversionError):
    """Raised when the input file type is unsupported."""


class EmptyFileError(FileConversionError):
    """Raised when the input file or extracted content is empty."""


class MarkDownConverter:
    """Converts supported document files (.pdf, .doc, .docx) to Markdown."""

    SUPPORTED_EXTENSIONS = SUPPORTED_EXTENSIONS

    def __init__(self) -> None:
        self._converter = MarkItDown()

    def convert(self, input_path: str | Path, output_path: str | Path) -> Path:
        """Convert a document file to Markdown and write it to *output_path*.

        Args:
            input_path:  Path to the source file (.pdf, .doc, or .docx).
            output_path: Path where the resulting .md file will be written.
        """
        input_path = Path(input_path).resolve()
        output_path = Path(output_path).resolve()

        self._validate_input(input_path)

        logger.info("Converting '%s' -> '%s'", input_path, output_path)

        try:
            result = self._converter.convert(str(input_path))
        except Exception as exc:
            raise FileConversionError(
                f"MarkItDown failed to convert '{input_path}': {exc}"
            ) from exc

        markdown_text = result.text_content
        if not markdown_text or not markdown_text.strip():
            raise EmptyFileError(f"Conversion produced no content for '{input_path}'")

        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(markdown_text, encoding="utf-8")

        logger.info(
            "Successfully wrote %d chars to '%s'", len(markdown_text), output_path
        )
        return output_path

    def _validate_input(self, path: Path) -> None:
        """Raise an appropriate exception if *path* cannot be converted."""
        if not path.exists():
            raise FileNotFoundError(f"Input file not found: '{path}'")

        if path.stat().st_size == 0:
            raise EmptyFileError(f"Input file is empty: '{path}'")

        extension = path.suffix.lower()
        if extension not in self.SUPPORTED_EXTENSIONS:
            raise UnsupportedFileTypeError(
                f"Unsupported file type '{extension}'. "
                f"Supported types: {', '.join(sorted(self.SUPPORTED_EXTENSIONS))}"
            )
