from unittest.mock import MagicMock

import numpy as np
import pytest

from src.semantic_chunker import (
    _split_into_paragraphs,
    _split_into_sentences,
    chunk_text_semantic,
)


@pytest.mark.unit
class TestSemanticChunker:
    def _make_mock_embedder(self, similarities=None):
        embedder = MagicMock()
        if similarities is None:
            similarities = [0.8, 0.3, 0.9, 0.2, 0.7]

        embeddings = []
        for i in range(len(similarities) + 1):
            base = np.zeros(10)
            base[0] = 1.0
            if i > 0 and similarities[i - 1] < 0.5:
                base[1] = 1.0
            embeddings.append(base.tolist())

        embedder.embed_texts.return_value = embeddings
        return embedder

    def test_split_into_sentences(self):
        text = "这是第一句话关于茅台公司。这是第二句话关于五粮液公司！这是第三句话关于白酒行业？"
        sentences = _split_into_sentences(text)
        assert len(sentences) >= 2

    def test_split_into_sentences_empty(self):
        sentences = _split_into_sentences("")
        assert sentences == []

    def test_split_into_paragraphs(self):
        text = "第一段内容\n\n第二段内容\n\n第三段内容"
        paragraphs = _split_into_paragraphs(text)
        assert len(paragraphs) == 3

    def test_split_into_paragraphs_with_headers(self):
        text = "# 标题一\n内容一\n\n# 标题二\n内容二"
        paragraphs = _split_into_paragraphs(text)
        assert len(paragraphs) >= 2

    def test_chunk_text_semantic_basic(self):
        embedder = self._make_mock_embedder()
        text = "第一句话内容较多关于茅台。第二句话完全不同的主题关于汽车。第三句话继续茅台的话题讨论。"

        chunks = chunk_text_semantic(text, embedder, chunk_size=512)

        assert len(chunks) > 0
        assert all("text" in c for c in chunks)
        assert all("metadata" in c for c in chunks)
        assert all(c["metadata"]["strategy"] == "semantic" for c in chunks)

    def test_chunk_text_semantic_empty_text(self):
        embedder = self._make_mock_embedder()
        chunks = chunk_text_semantic("", embedder)
        assert chunks == []

    def test_chunk_text_semantic_none_embedder_raises(self):
        with pytest.raises(ValueError, match="Embedder is required"):
            chunk_text_semantic("test text", None)

    def test_chunk_text_semantic_single_sentence(self):
        embedder = MagicMock()
        text = "这是一段很短的文本"
        chunks = chunk_text_semantic(text, embedder, chunk_size=512)

        assert len(chunks) >= 1
        assert chunks[0]["metadata"]["strategy"] == "semantic"

    def test_chunk_text_semantic_respects_chunk_size(self):
        embedder = self._make_mock_embedder(similarities=[0.8] * 10)
        text = "。".join([f"这是第{i}句话内容很多关于茅台公司" for i in range(20)])

        chunks = chunk_text_semantic(text, embedder, chunk_size=64)

        for chunk in chunks:
            assert chunk["metadata"]["token_count"] <= 64 + 10

    def test_chunk_text_semantic_threshold_mode(self):
        similarities = [0.9, 0.1, 0.9, 0.1]
        embedder = self._make_mock_embedder(similarities=similarities)

        text = "。".join([f"这是第{i}句话关于不同主题" for i in range(5)])

        chunks = chunk_text_semantic(
            text, embedder, similarity_threshold=0.5, chunk_size=512
        )

        assert len(chunks) >= 1

    def test_chunk_text_semantic_percentile_mode(self):
        similarities = [0.9, 0.3, 0.8, 0.2]
        embedder = self._make_mock_embedder(similarities=similarities)

        text = "。".join([f"这是第{i}句话关于不同主题" for i in range(5)])

        chunks = chunk_text_semantic(
            text, embedder, breakpoint_percentile=25, chunk_size=512
        )

        assert len(chunks) >= 1

    def test_chunk_text_semantic_metadata(self):
        embedder = self._make_mock_embedder()
        text = "第一句话内容较多关于茅台。第二句话完全不同的主题关于汽车。"

        chunks = chunk_text_semantic(text, embedder, chunk_size=512)

        for chunk in chunks:
            assert "chunk_index" in chunk["metadata"]
            assert "char_count" in chunk["metadata"]
            assert "token_count" in chunk["metadata"]
            assert "start_token" in chunk["metadata"]
            assert "end_token" in chunk["metadata"]
            assert chunk["metadata"]["strategy"] == "semantic"

    def test_chunk_text_semantic_merges_small_chunks(self):
        embedder = self._make_mock_embedder(similarities=[0.1, 0.1, 0.1])
        text = "短句。短句。短句。这是较长的一句话关于茅台公司的营业收入情况。"

        chunks = chunk_text_semantic(
            text, embedder, chunk_size=512, min_chunk_size=5
        )

        assert len(chunks) >= 1
