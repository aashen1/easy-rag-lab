import json
import tempfile
from pathlib import Path

import pytest

from src.bm25_retriever import BM25Retriever


@pytest.mark.unit
class TestBM25Retriever:
    def _make_test_chunks(self):
        return [
            {
                "chunk_id": "doc1_000",
                "text": "贵州茅台2023年营业收入达到1500亿元，同比增长16.5%",
                "metadata": {"source": "moutai_2023.md", "category": "annual_report"},
            },
            {
                "chunk_id": "doc2_000",
                "text": "五粮液2023年实现营业收入832亿元，净利润302亿元",
                "metadata": {"source": "wuliangye_2023.md", "category": "annual_report"},
            },
            {
                "chunk_id": "doc3_000",
                "text": "白酒行业整体增速放缓，高端白酒市场格局稳定",
                "metadata": {"source": "industry_2023.md", "category": "research_report"},
            },
        ]

    def test_build_index(self):
        retriever = BM25Retriever()
        chunks = self._make_test_chunks()
        retriever.build_index(chunks)

        assert retriever.is_indexed() is True
        assert retriever.get_corpus_size() == 3

    def test_build_index_empty_chunks_raises(self):
        retriever = BM25Retriever()
        with pytest.raises(ValueError, match="Cannot build BM25 index from empty"):
            retriever.build_index([])

    def test_retrieve_before_index_raises(self):
        retriever = BM25Retriever()
        with pytest.raises(RuntimeError, match="BM25 index not built"):
            retriever.retrieve("test query")

    def test_retrieve_empty_query_raises(self):
        retriever = BM25Retriever()
        retriever.build_index(self._make_test_chunks())
        with pytest.raises(ValueError, match="Query must be a non-empty string"):
            retriever.retrieve("")

    def test_retrieve_non_string_query_raises(self):
        retriever = BM25Retriever()
        retriever.build_index(self._make_test_chunks())
        with pytest.raises(ValueError, match="Query must be a non-empty string"):
            retriever.retrieve(123)

    def test_retrieve_returns_results(self):
        retriever = BM25Retriever()
        retriever.build_index(self._make_test_chunks())

        results = retriever.retrieve("茅台营业收入", top_k=2)

        assert len(results) <= 2
        assert all("chunk_id" in r for r in results)
        assert all("text" in r for r in results)
        assert all("metadata" in r for r in results)
        assert all("score" in r for r in results)
        assert all(r["score"] > 0 for r in results)

    def test_retrieve_relevance_ranking(self):
        retriever = BM25Retriever()
        retriever.build_index(self._make_test_chunks())

        results = retriever.retrieve("茅台营业收入", top_k=3)

        assert len(results) >= 1
        assert results[0]["chunk_id"] == "doc1_000"

    def test_retrieve_top_k_limits_results(self):
        retriever = BM25Retriever()
        retriever.build_index(self._make_test_chunks())

        results = retriever.retrieve("白酒", top_k=1)
        assert len(results) == 1

    def test_retrieve_no_matching_tokens_returns_empty(self):
        retriever = BM25Retriever()
        retriever.build_index(self._make_test_chunks())

        results = retriever.retrieve("量子计算机", top_k=5)
        assert len(results) == 0

    def test_tokenize_chinese_text(self):
        tokens = BM25Retriever.tokenize("贵州茅台2023年营业收入")
        assert isinstance(tokens, list)
        assert len(tokens) > 0
        assert all(isinstance(t, str) for t in tokens)

    def test_tokenize_filters_short_tokens(self):
        tokens = BM25Retriever.tokenize("a b c 贵州茅台")
        assert all(len(t) > 1 for t in tokens)

    def test_invalid_k1_raises(self):
        with pytest.raises(ValueError, match="k1 must be non-negative"):
            BM25Retriever(k1=-1)

    def test_invalid_b_raises(self):
        with pytest.raises(ValueError, match="b must be in"):
            BM25Retriever(b=1.5)

    def test_build_index_from_chunks(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = Path(tmpdir)
            chunks_file = chunks_dir / "test.jsonl"

            chunks = self._make_test_chunks()
            with open(chunks_file, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

            retriever = BM25Retriever()
            retriever.build_index_from_chunks(str(chunks_dir))

            assert retriever.is_indexed() is True
            assert retriever.get_corpus_size() == 3

    def test_build_index_from_chunks_dir_not_found(self):
        retriever = BM25Retriever()
        with pytest.raises(FileNotFoundError):
            retriever.build_index_from_chunks("/nonexistent/path")

    def test_build_index_from_chunks_with_source_filter(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            chunks_dir = Path(tmpdir)
            (chunks_dir / "include.jsonl").write_text(
                json.dumps(self._make_test_chunks()[0], ensure_ascii=False) + "\n",
                encoding="utf-8",
            )
            (chunks_dir / "exclude.jsonl").write_text(
                json.dumps(self._make_test_chunks()[1], ensure_ascii=False) + "\n",
                encoding="utf-8",
            )

            retriever = BM25Retriever()
            retriever.build_index_from_chunks(
                str(chunks_dir), source_filter={"include.jsonl"}
            )

            assert retriever.get_corpus_size() == 1

    def test_bm25_parameters_affect_scoring(self):
        chunks = self._make_test_chunks()

        retriever_default = BM25Retriever(k1=1.5, b=0.75)
        retriever_default.build_index(chunks)

        retriever_no_norm = BM25Retriever(k1=1.5, b=0.0)
        retriever_no_norm.build_index(chunks)

        results_default = retriever_default.retrieve("茅台", top_k=3)
        results_no_norm = retriever_no_norm.retrieve("茅台", top_k=3)

        assert len(results_default) > 0
        assert len(results_no_norm) > 0

        if len(results_default) > 1 and len(results_no_norm) > 1:
            scores_differ = (
                results_default[0]["score"] != results_no_norm[0]["score"]
            )
            assert scores_differ
