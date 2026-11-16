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

import requests
from dotenv import load_dotenv
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_experimental.text_splitter import SemanticChunker as LCSemanticChunker

from .base import BaseChunker
from .recursive import (
    RecursiveChunker,
)

load_dotenv()
OLLAMA_EMBEDDINGS_URL = os.getenv("EMBED_URL")


class __HFRemoteEmbeddings(Embeddings):
    """Calls the FastAPI server on Colab (Qwen/Qwen3-Embedding-0.6B via sentence-transformers)."""

    def __init__(self, base_url: str, batch_size: int = 64, timeout: int = 120):
        self.base_url = base_url.rstrip("/")
        self.batch_size = batch_size
        self.timeout = timeout

    def _post(self, texts: list[str], is_query: bool) -> list[list[float]]:
        r = requests.post(
            f"{self.base_url}/embed",
            json={"texts": texts, "is_query": is_query},
            timeout=self.timeout,
        )
        r.raise_for_status()
        return r.json()["embeddings"]

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        out: list[list[float]] = []
        for i in range(0, len(texts), self.batch_size):
            out.extend(self._post(texts[i : i + self.batch_size], is_query=False))
        return out

    def embed_query(self, text: str) -> list[float]:
        return self._post([text], is_query=True)[0]


ollama_embeddings = __HFRemoteEmbeddings(base_url=str(OLLAMA_EMBEDDINGS_URL))


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
