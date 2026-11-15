"""
text_chunking/recursive.py
========================
Recursive chunker.

How: splits on the biggest separator first (headings, code fences, paragraphs,
     lines, sentences, words), recursing to smaller ones until chunks fit chunk_size.
Use: fast, no model needed; good default for general text/markdown.
"""

from __future__ import annotations

from typing import overload

from langchain_core.documents import Document
from langchain_text_splitters import RecursiveCharacterTextSplitter

from backend.text_chunking.base import BaseChunker

_SEPARATORS = [
    "\n#{1,6} ",
    "```\n",
    "\n\n",
    "\n",
    ". ",
    "! ",
    "? ",
    "。",
    "，",
    " ",
    "",
]


class RecursiveChunker(BaseChunker):
    def __init__(self, chunk_size: int = 1200, chunk_overlap: int = 200):
        super().__init__(chunk_size, chunk_overlap)
        self._splitter = RecursiveCharacterTextSplitter(
            chunk_size=self.chunk_size,
            chunk_overlap=self.chunk_overlap,
            separators=_SEPARATORS,
            add_start_index=True,
            strip_whitespace=True,
        )

    @overload
    def chunk(self, docs: list[str]) -> list[str]: ...
    @overload
    def chunk(self, docs: list[Document]) -> list[Document]: ...

    def chunk(self, docs):
        if not docs:
            return []
        if isinstance(docs[0], Document):
            return self._enrich(self._splitter.split_documents(docs))
        chunks: list[str] = []
        for text in docs:
            chunks.extend(self._splitter.split_text(text))
        return chunks
