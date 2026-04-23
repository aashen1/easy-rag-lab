from unittest.mock import MagicMock

import pytest

from src.bm25_retriever import BM25Retriever
from src.exceptions import RetrievalError
from src.hybrid_retriever import HybridRetriever
from src.retriever import Retriever


@pytest.mark.unit
class TestHybridRetriever:
    def _make_vector_results(self):
        return [
            {
                "chunk_id": "doc1::chunk::000",
                "text": "贵州茅台2023年营业收入1500亿元",
                "metadata": {"source": "moutai.md"},
                "score": 0.95,
            },
            {
                "chunk_id": "doc2::chunk::000",
                "text": "五粮液2023年营收832亿元",
                "metadata": {"source": "wuliangye.md"},
                "score": 0.80,
            },
            {
                "chunk_id": "doc3::chunk::000",
                "text": "白酒行业整体增速放缓",
                "metadata": {"source": "industry.md"},
                "score": 0.60,
            },
        ]

    def _make_bm25_results(self):
        return [
            {
                "chunk_id": "doc2::chunk::000",
                "text": "五粮液2023年营收832亿元",
                "metadata": {"source": "wuliangye.md"},
                "score": 15.2,
            },
            {
                "chunk_id": "doc1::chunk::000",
                "text": "贵州茅台2023年营业收入1500亿元",
                "metadata": {"source": "moutai.md"},
                "score": 12.5,
            },
            {
                "chunk_id": "doc4::chunk::000",
                "text": "泸州老窖2023年营收302亿元",
                "metadata": {"source": "luzhoulaojiao.md"},
                "score": 8.0,
            },
        ]

    def _make_mock_retrievers(self):
        vector_retriever = MagicMock(spec=Retriever)
        vector_retriever.retrieve.return_value = self._make_vector_results()

        bm25_retriever = MagicMock(spec=BM25Retriever)
        bm25_retriever.retrieve.return_value = self._make_bm25_results()

        return vector_retriever, bm25_retriever

    def test_invalid_fusion_method_raises(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        with pytest.raises(RetrievalError, match="fusion_method must be"):
            HybridRetriever(
                vector_retriever=vector_ret,
                bm25_retriever=bm25_ret,
                fusion_method="invalid",
            )

    def test_zero_weights_raises(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        with pytest.raises(RetrievalError, match="vector_weight.*bm25_weight.*must not be zero"):
            HybridRetriever(
                vector_retriever=vector_ret,
                bm25_retriever=bm25_ret,
                vector_weight=0.0,
                bm25_weight=0.0,
            )

    def test_rrf_fusion_returns_results(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        hybrid = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
            fusion_method="rrf",
            top_k=5,
        )

        results = hybrid.retrieve("茅台营收")

        assert len(results) > 0
        assert all("chunk_id" in r for r in results)
        assert all("score" in r for r in results)
        assert all("text" in r for r in results)
        assert all("metadata" in r for r in results)

    def test_weighted_fusion_returns_results(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        hybrid = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
            fusion_method="weighted",
            vector_weight=0.7,
            bm25_weight=0.3,
            top_k=5,
        )

        results = hybrid.retrieve("茅台营收")

        assert len(results) > 0
        assert all(r["score"] >= 0 for r in results)

    def test_rrf_fusion_combines_both_retrievers(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        hybrid = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
            fusion_method="rrf",
            top_k=10,
        )

        results = hybrid.retrieve("茅台营收")
        result_ids = {r["chunk_id"] for r in results}

        assert "doc4::chunk::000" in result_ids

    def test_rrf_fusion_boosts_shared_documents(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        hybrid = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
            fusion_method="rrf",
            top_k=10,
        )

        results = hybrid.retrieve("茅台营收")
        score_map = {r["chunk_id"]: r["score"] for r in results}

        assert "doc1::chunk::000" in score_map
        assert "doc2::chunk::000" in score_map
        assert "doc4::chunk::000" in score_map

        assert score_map["doc1::chunk::000"] > score_map["doc4::chunk::000"]
        assert score_map["doc2::chunk::000"] > score_map["doc4::chunk::000"]

    def test_weighted_fusion_normalizes_scores(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        hybrid = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
            fusion_method="weighted",
            vector_weight=0.5,
            bm25_weight=0.5,
            top_k=10,
        )

        results = hybrid.retrieve("茅台营收")

        assert len(results) > 0
        for r in results:
            assert r["score"] >= 0

    def test_top_k_limits_results(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        hybrid = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
            fusion_method="rrf",
            top_k=2,
        )

        results = hybrid.retrieve("茅台营收")
        assert len(results) <= 2

    def test_empty_query_raises(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()
        hybrid = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
        )

        with pytest.raises(RetrievalError, match="Query must be a non-empty string"):
            hybrid.retrieve("")

    def test_normalize_scores_empty_dict(self):
        result = HybridRetriever._normalize_scores({})
        assert result == {}

    def test_normalize_scores_equal_values(self):
        scores = {"a": 5.0, "b": 5.0, "c": 5.0}
        result = HybridRetriever._normalize_scores(scores)
        assert all(v == 1.0 for v in result.values())

    def test_normalize_scores_range(self):
        scores = {"a": 0.0, "b": 5.0, "c": 10.0}
        result = HybridRetriever._normalize_scores(scores)
        assert result["a"] == 0.0
        assert result["b"] == 0.5
        assert result["c"] == 1.0

    def test_rrf_k_parameter_affects_scores(self):
        vector_ret, bm25_ret = self._make_mock_retrievers()

        hybrid_k10 = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
            fusion_method="rrf",
            rrf_k=10,
            top_k=5,
        )
        hybrid_k100 = HybridRetriever(
            vector_retriever=vector_ret,
            bm25_retriever=bm25_ret,
            fusion_method="rrf",
            rrf_k=100,
            top_k=5,
        )

        results_k10 = hybrid_k10.retrieve("茅台营收")
        results_k100 = hybrid_k100.retrieve("茅台营收")

        assert len(results_k10) > 0
        assert len(results_k100) > 0

        assert results_k10[0]["score"] > results_k100[0]["score"]
