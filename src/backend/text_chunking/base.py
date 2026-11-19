"""
text_chunking/base.py
==================
Base class for all chunkers.

What: shared interface (`chunk()`), file reader, metadata enrichment.
Use: subclass it to add a new chunking strategy.
"""

from abc import ABC, abstractmethod
from pathlib import Path

from langchain_core.documents import Document


class BaseChunker(ABC):
    def __init__(self, chunksize: int = 1200, chunkoverlap: int = 200):
        self.chunk_size = chunksize
        self.chunk_overlap = chunkoverlap

    def read_file(self, file_path: Path | str) -> str:
        with open(file_path, "r", encoding="utf-8") as file:
            text = file.read()

        return text

    @abstractmethod
    def chunk(self, docs: list[str] | list[Document]) -> list[str] | list[Document]:
        """
        Abstract method chunking list of string into smaller chunks
        """

    @staticmethod
    def _enrich(chunks: list[Document]) -> list[Document]:
        """Assign index and number of char into Document.metadata of each chunk."""
        for i, chunk in enumerate(chunks):
            chunk.metadata["chunk_index"] = i
            chunk.metadata["char_count"] = len(chunk.page_content)
        return chunks
