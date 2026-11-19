"""
text_chunking/deduplication.py
=========================
Post-chunking deduplication — remove duplicate or near-duplicate chunks.
Use: run after any chunker, before embedding. Keeps first occurrence.

| Method   | Mechanism                      | Speed     | Detects                   |
|----------|--------------------------------|-----------|---------------------------|
| exact    | MD5 hash comparison            | Very fast | Exact text match only     |
| minhash  | MinHash + LSH on shingles      | Fast      | Near-duplicates, typos    |
| semantic | Embedding cosine similarity    | Slower    | Paraphrasing, translation | Currently not used |
"""

from __future__ import annotations

import hashlib
from typing import Literal, overload

from langchain_core.documents import Document


def _text(chunk: str | Document) -> str:
    return chunk.page_content if isinstance(chunk, Document) else chunk


@overload
def deduplicate_chunks(
    chunks: list[str],
    method: Literal["exact", "minhash", "semantic"] = ...,
    threshold: float = ...,
    model: str = ...,
) -> list[str]: ...
@overload
def deduplicate_chunks(
    chunks: list[Document],
    method: Literal["exact", "minhash", "semantic"] = ...,
    threshold: float = ...,
    model: str = ...,
) -> list[Document]: ...


def deduplicate_chunks(
    chunks,
    method: Literal["exact", "minhash", "semantic"] = "exact",
    threshold: float = 0.95,
    # model: str = "sentence-transformers/all-MiniLM-L6-v2",
):
    """
    Parameters
    ----------
    chunks    : Output of any chunker: ``list[str]`` or ``list[Document]``.
    method    : Deduplication method — see table in module docstring.
    threshold : Similarity threshold to consider as duplicate; used only by minhash and semantic.
    model     : sentence-transformers model for the semantic method.
    """
    if method == "exact":
        return _exact(chunks)
    if method == "minhash":
        return _minhash(chunks, threshold)
    if method == "semantic":
        raise ValueError("semantic deduplication strategy is currently not available")
    #     return _semantic(chunks, threshold, model)
    raise ValueError(f"Unknown dedup method: '{method}'")


def _exact[T: (str, Document)](chunks: list[T]) -> list[T]:
    seen: set[str] = set()
    unique: list[T] = []
    for chunk in chunks:
        h = hashlib.md5(_text(chunk).encode()).hexdigest()
        if h not in seen:
            seen.add(h)
            unique.append(chunk)
    return unique


def _minhash[T: (str, Document)](chunks: list[T], threshold: float) -> list[T]:
    from datasketch import MinHash, MinHashLSH

    lsh = MinHashLSH(threshold=threshold, num_perm=128)
    unique: list[T] = []

    for i, chunk in enumerate(chunks):
        mh = MinHash(num_perm=128)
        for word in _text(chunk).lower().split():
            mh.update(word.encode("utf-8"))
        key = f"chunk_{i}"
        if not lsh.query(mh):
            lsh.insert(key, mh)
            unique.append(chunk)

    return unique


# def _semantic(
#     chunks: list[Document], threshold: float, model_name: str
# ) -> list[Document]:
#     import numpy as np
#     from sentence_transformers import SentenceTransformer

#     model = SentenceTransformer(model_name)
#     texts = [_text(c) for c in chunks]
#     embeddings = model.encode(texts, normalize_embeddings=True, show_progress_bar=True)

#     unique_indices: list[int] = []
#     for i in range(len(chunks)):
#         is_dup = any(
#             float(np.dot(embeddings[i], embeddings[j])) >= threshold
#             for j in unique_indices
#         )
#         if not is_dup:
#             unique_indices.append(i)

#     return [chunks[i] for i in unique_indices]
