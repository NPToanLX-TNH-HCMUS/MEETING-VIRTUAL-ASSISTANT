import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings

from src.backend.text_chunking import semantic as semantic_mod
from src.backend.text_chunking.base import BaseChunker
from src.backend.text_chunking.deduplication import deduplicate_chunks
from src.backend.text_chunking.recursive import RecursiveChunker
from src.backend.text_chunking.semantic import SemanticChunker


class _DummyChunker(BaseChunker):
    def chunk(self, docs):
        return docs


class _FakeEmbeddings(Embeddings):
    """Deterministic local embeddings that separate distinct topics."""

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        return [self.embed_query(t) for t in texts]

    def embed_query(self, text: str) -> list[float]:
        lower = text.lower()
        if "budget" in lower or "finance" in lower:
            return [1.0, 0.0, 0.0]
        if "deploy" in lower or "server" in lower:
            return [0.0, 1.0, 0.0]
        return [0.0, 0.0, 1.0]


class TestBaseChunker(unittest.TestCase):
    def test_cannot_instantiate_abstract_base_chunker(self):
        with self.assertRaises(TypeError):
            BaseChunker()  # type: ignore[abstract]

    def test_default_and_custom_init_params(self):
        default_chunker = _DummyChunker()
        self.assertEqual(default_chunker.chunk_size, 1200)
        self.assertEqual(default_chunker.chunk_overlap, 200)

        custom_chunker = _DummyChunker(chunksize=500, chunkoverlap=50)
        self.assertEqual(custom_chunker.chunk_size, 500)
        self.assertEqual(custom_chunker.chunk_overlap, 50)

    def test_read_file_accepts_str_and_path_with_utf8(self):
        chunker = _DummyChunker()
        content = "Biên bản cuộc họp: 第1回会議\nLine 2"

        with tempfile.TemporaryDirectory() as tmp_dir:
            file_path = Path(tmp_dir) / "sample.txt"
            file_path.write_text(content, encoding="utf-8")

            self.assertEqual(chunker.read_file(file_path), content)
            self.assertEqual(chunker.read_file(str(file_path)), content)

    def test_read_file_missing_raises_file_not_found(self):
        chunker = _DummyChunker()
        with self.assertRaises(FileNotFoundError):
            chunker.read_file("non_existent_file_12345.txt")

    def test_enrich_adds_chunk_index_and_char_count(self):
        docs = [
            Document(page_content="hello", metadata={"source": "a.md"}),
            Document(page_content="world!", metadata={"source": "a.md", "page": 2}),
        ]

        enriched = BaseChunker._enrich(docs)

        self.assertIs(enriched, docs)
        self.assertEqual(
            enriched[0].metadata,
            {"source": "a.md", "chunk_index": 0, "char_count": 5},
        )
        self.assertEqual(
            enriched[1].metadata,
            {"source": "a.md", "page": 2, "chunk_index": 1, "char_count": 6},
        )

    def test_enrich_empty_list(self):
        self.assertEqual(BaseChunker._enrich([]), [])


class TestRecursiveChunker(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        chunker = RecursiveChunker(chunk_size=100, chunk_overlap=20)
        self.assertEqual(chunker.chunk([]), [])

    def test_chunk_strings_short_text_single_chunk(self):
        chunker = RecursiveChunker(chunk_size=100, chunk_overlap=20)
        result = chunker.chunk(["Short meeting note."])
        self.assertEqual(result, ["Short meeting note."])

    def test_chunk_strings_respects_chunk_size_and_multiple_inputs(self):
        chunker = RecursiveChunker(chunk_size=50, chunk_overlap=10)
        text_a = "First paragraph about agenda items.\n\nSecond paragraph about action items."
        text_b = "Third paragraph discussing timeline and deliverables in detail."

        chunks = chunker.chunk([text_a, text_b])

        self.assertGreater(len(chunks), 2)
        for c in chunks:
            self.assertIsInstance(c, str)
            self.assertLessEqual(len(c), 50)

    def test_chunk_strings_splits_on_paragraph_separator(self):
        chunker = RecursiveChunker(chunk_size=30, chunk_overlap=0)
        text = "Intro paragraph.\n\nAgenda paragraph."
        chunks = chunker.chunk([text])

        self.assertEqual(chunks, ["Intro paragraph.", "Agenda paragraph."])

    def test_chunk_documents_preserves_metadata_and_enriches(self):
        chunker = RecursiveChunker(chunk_size=45, chunk_overlap=10)
        docs = [
            Document(
                page_content="Sentence one is here. Sentence two follows right after. Sentence three ends it.",
                metadata={"source": "meeting.md", "speaker": "Alice"},
            )
        ]

        chunks = chunker.chunk(docs)

        self.assertGreater(len(chunks), 1)
        for idx, doc in enumerate(chunks):
            self.assertIsInstance(doc, Document)
            self.assertLessEqual(len(doc.page_content), 45)
            self.assertEqual(doc.metadata["source"], "meeting.md")
            self.assertEqual(doc.metadata["speaker"], "Alice")
            self.assertEqual(doc.metadata["chunk_index"], idx)
            self.assertEqual(doc.metadata["char_count"], len(doc.page_content))
            self.assertIn("start_index", doc.metadata)
            self.assertGreaterEqual(doc.metadata["start_index"], 0)


class TestHFRemoteEmbeddings(unittest.TestCase):
    @patch("src.backend.text_chunking.semantic.requests.post")
    def test_embed_documents_batches_requests_and_strips_trailing_slash(self, mock_post):
        resp1 = MagicMock()
        resp1.json.return_value = {"embeddings": [[0.1, 0.2], [0.3, 0.4]]}
        resp2 = MagicMock()
        resp2.json.return_value = {"embeddings": [[0.5, 0.6]]}
        mock_post.side_effect = [resp1, resp2]

        hf_remote_cls = getattr(semantic_mod, "__HFRemoteEmbeddings")
        client = hf_remote_cls(
            base_url="http://localhost:8000/", batch_size=2, timeout=30
        )
        result = client.embed_documents(["a", "b", "c"])

        self.assertEqual(result, [[0.1, 0.2], [0.3, 0.4], [0.5, 0.6]])
        self.assertEqual(mock_post.call_count, 2)
        mock_post.assert_any_call(
            "http://localhost:8000/embed",
            json={"texts": ["a", "b"], "is_query": False},
            timeout=30,
        )
        mock_post.assert_any_call(
            "http://localhost:8000/embed",
            json={"texts": ["c"], "is_query": False},
            timeout=30,
        )
        resp1.raise_for_status.assert_called_once()
        resp2.raise_for_status.assert_called_once()

    @patch("src.backend.text_chunking.semantic.requests.post")
    def test_embed_query_sends_is_query_true(self, mock_post):
        resp = MagicMock()
        resp.json.return_value = {"embeddings": [[0.9, 0.1]]}
        mock_post.return_value = resp

        hf_remote_cls = getattr(semantic_mod, "__HFRemoteEmbeddings")
        client = hf_remote_cls(base_url="http://localhost:8000")
        result = client.embed_query("find agenda")

        self.assertEqual(result, [0.9, 0.1])
        mock_post.assert_called_once_with(
            "http://localhost:8000/embed",
            json={"texts": ["find agenda"], "is_query": True},
            timeout=120,
        )
        resp.raise_for_status.assert_called_once()


class TestSemanticChunker(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        chunker = SemanticChunker(embeddings=_FakeEmbeddings())
        self.assertEqual(chunker.chunk([]), [])

    def test_chunk_strings_splits_and_enforces_chunk_size(self):
        chunker = SemanticChunker(
            embeddings=_FakeEmbeddings(),
            chunk_size=60,
            chunk_overlap=10,
            breakpoint_threshold_amount=50.0,
        )
        text = (
            "We reviewed the quarterly budget today. "
            "Finance approved the extra budget allocation for Q4. "
            "Next we need to deploy the backend server. "
            "The server deployment is scheduled for Friday."
        )

        chunks = chunker.chunk([text])

        self.assertGreater(len(chunks), 1)
        for c in chunks:
            self.assertIsInstance(c, str)
            self.assertLessEqual(len(c), 60)

    def test_chunk_documents_enriches_metadata(self):
        chunker = SemanticChunker(
            embeddings=_FakeEmbeddings(),
            chunk_size=80,
            chunk_overlap=10,
            breakpoint_threshold_amount=50.0,
        )
        docs = [
            Document(
                page_content=(
                    "We discussed the budget plan. "
                    "Now let us deploy the server. "
                    "Finally we wrap up the meeting."
                ),
                metadata={"source": "transcript.txt"},
            )
        ]

        chunks = chunker.chunk(docs)

        self.assertGreater(len(chunks), 0)
        for idx, doc in enumerate(chunks):
            self.assertIsInstance(doc, Document)
            self.assertLessEqual(len(doc.page_content), 80)
            self.assertEqual(doc.metadata["source"], "transcript.txt")
            self.assertEqual(doc.metadata["chunk_index"], idx)
            self.assertEqual(doc.metadata["char_count"], len(doc.page_content))

    def test_oversized_document_piece_shifts_start_index_by_offset(self):
        chunker = SemanticChunker(
            embeddings=_FakeEmbeddings(),
            chunk_size=30,
            chunk_overlap=0,
        )
        small_piece = Document(
            page_content="Short intro.",
            metadata={"source": "doc.md", "start_index": 0},
        )
        oversized_piece = Document(
            page_content="Alpha sentence one. Beta sentence two. Gamma sentence three.",
            metadata={"source": "doc.md", "start_index": 100},
        )
        chunker._chunker.split_documents = MagicMock(
            return_value=[small_piece, oversized_piece]
        )

        result = chunker.chunk([Document(page_content="placeholder")])

        self.assertGreater(len(result), 2)
        self.assertEqual(result[0].page_content, "Short intro.")
        self.assertEqual(result[0].metadata["start_index"], 0)
        self.assertEqual(result[1].metadata["start_index"], 100)
        self.assertGreater(result[2].metadata["start_index"], 100)
        for idx, doc in enumerate(result):
            self.assertEqual(doc.metadata["chunk_index"], idx)
            self.assertEqual(doc.metadata["char_count"], len(doc.page_content))


class TestDeduplication(unittest.TestCase):
    def test_empty_input_returns_empty_list(self):
        self.assertEqual(deduplicate_chunks([], method="exact"), [])
        self.assertEqual(deduplicate_chunks([], method="minhash"), [])

    def test_exact_dedup_strings_preserves_order_and_first_occurrence(self):
        chunks = ["hello world", "foo bar", "hello world", "baz", "foo bar"]
        result = deduplicate_chunks(chunks, method="exact")
        self.assertEqual(result, ["hello world", "foo bar", "baz"])

    def test_exact_dedup_strings_is_case_and_whitespace_sensitive(self):
        chunks = ["Hello", "hello", "Hello "]
        result = deduplicate_chunks(chunks, method="exact")
        self.assertEqual(result, ["Hello", "hello", "Hello "])

    def test_exact_dedup_documents_keeps_first_metadata(self):
        doc1 = Document(page_content="same content", metadata={"id": 1})
        doc2 = Document(page_content="other content", metadata={"id": 2})
        doc3 = Document(page_content="same content", metadata={"id": 3})

        result = deduplicate_chunks([doc1, doc2, doc3], method="exact")

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].metadata["id"], 1)
        self.assertEqual(result[1].metadata["id"], 2)

    def test_minhash_dedup_strings_removes_near_duplicates(self):
        base = "the quick brown fox jumps over the lazy dog in the park"
        near_dup = "the quick brown fox jumps over the lazy dog in the yard"
        distinct = "quarterly financial report shows strong revenue growth in europe"

        result = deduplicate_chunks(
            [base, near_dup, distinct], method="minhash", threshold=0.7
        )

        self.assertEqual(result, [base, distinct])

    def test_minhash_dedup_documents_keeps_first_and_distinct(self):
        doc1 = Document(
            page_content="action item schedule weekly sync with engineering team",
            metadata={"chunk_index": 0},
        )
        doc2 = Document(
            page_content="action item schedule weekly sync with engineering team!",
            metadata={"chunk_index": 1},
        )
        doc3 = Document(
            page_content="completely unrelated topic about marketing campaign budget",
            metadata={"chunk_index": 2},
        )

        result = deduplicate_chunks([doc1, doc2, doc3], method="minhash", threshold=0.7)

        self.assertEqual(len(result), 2)
        self.assertEqual(result[0].metadata["chunk_index"], 0)
        self.assertEqual(result[1].metadata["chunk_index"], 2)

    def test_semantic_method_raises_value_error(self):
        with self.assertRaises(ValueError):
            deduplicate_chunks(["a", "b"], method="semantic")

    def test_unknown_method_raises_value_error(self):
        with self.assertRaises(ValueError):
            deduplicate_chunks(["a", "b"], method="unknown")  # type: ignore[arg-type]


if __name__ == "__main__":
    unittest.main()
