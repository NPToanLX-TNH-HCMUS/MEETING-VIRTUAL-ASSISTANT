"""
text_chunking/semantic.py
=====================
Semantic chunker.

How: embeds sentences, splits where similarity between neighbors drops
     (percentile breakpoint); oversized chunks are re-split by RecursiveChunker.
Use: topic-coherent chunks (e.g. meeting transcripts); slower, needs embedding server.
"""

from __future__ import annotations

import os
from typing import overload

from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_experimental.text_splitter import SemanticChunker as LCSemanticChunker
from langchain_ollama import OllamaEmbeddings

from backend.text_chunking.base import BaseChunker
from backend.text_chunking.recursive import (
    RecursiveChunker,
)

load_dotenv()
OLLAMA_EMBEDDINGS_URL = os.getenv("EMBED_URL")

ollama_embeddings = OllamaEmbeddings(
    model="qwen3-embedding:0.6b",
    base_url=str(OLLAMA_EMBEDDINGS_URL),
)


class SemanticChunker(BaseChunker):
    def __init__(
        self,
        embeddings: Embeddings = ollama_embeddings,
        chunk_size: int = 1200,
        chunk_overlap: int = 200,
        breakpoint_threshold_type: str = "percentile",
        breakpoint_threshold_amount: float | None = None,
        buffer_size: int = 1,
        min_chunk_size: int | None = None,
    ):
        super().__init__(chunk_size, chunk_overlap)
        self._chunker = LCSemanticChunker(
            embeddings,
            buffer_size=buffer_size,
            breakpoint_threshold_type=breakpoint_threshold_type,
            breakpoint_threshold_amount=breakpoint_threshold_amount,
            min_chunk_size=min_chunk_size,
            add_start_index=True,
        )
        # Size guard: semantic chunks are not size-bounded, so re-split oversized ones
        self._size_guard = RecursiveChunker(chunk_size, chunk_overlap)

    @overload
    def chunk(self, docs: list[str]) -> list[str]: ...
    @overload
    def chunk(self, docs: list[Document]) -> list[Document]: ...

    def chunk(self, docs):
        if not docs:
            return []
        if isinstance(docs[0], Document):
            return self._enrich(self._chunk_documents(docs))
        return self._chunk_texts(docs)

    def _chunk_texts(self, texts: list[str]) -> list[str]:
        chunks: list[str] = []
        for text in texts:
            for piece in self._chunker.split_text(text):
                if len(piece) > self.chunk_size:
                    chunks.extend(self._size_guard.chunk([piece]))
                else:
                    chunks.append(piece)
        return chunks

    def _chunk_documents(self, docs: list[Document]) -> list[Document]:
        out: list[Document] = []
        for piece in self._chunker.split_documents(docs):
            if len(piece.page_content) <= self.chunk_size:
                out.append(piece)
                continue
            # start_index of sub-chunks is relative to the piece, so shift it back to the position in the original document
            offset = piece.metadata.get("start_index", 0)
            for sub in self._size_guard.chunk([piece]):
                if "start_index" in sub.metadata:
                    sub.metadata["start_index"] += offset
                out.append(sub)
        return out
