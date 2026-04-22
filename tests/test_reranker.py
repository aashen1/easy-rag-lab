from unittest.mock import MagicMock, patch

import pytest
import torch

from src.exceptions import ConfigurationError
from src.reranker import Reranker


@pytest.mark.unit
class TestReranker:
    def _make_mock_model_output(self, scores):
        mock_output = MagicMock()
        mock_logits = torch.tensor(scores).unsqueeze(-1)
        mock_output.logits = mock_logits
        return mock_output

    def _make_test_results(self):
        return [
            {"chunk_id": "c1", "text": "贵州茅台2023年营业收入1500亿元", "metadata": {"source": "moutai.md"}, "score": 0.95},
            {"chunk_id": "c2", "text": "五粮液2023年营收832亿元", "metadata": {"source": "wuliangye.md"}, "score": 0.80},
            {"chunk_id": "c3", "text": "白酒行业整体增速放缓", "metadata": {"source": "industry.md"}, "score": 0.60},
        ]

    @patch("src.reranker.AutoModelForSequenceClassification")
    @patch("src.reranker.AutoTokenizer")
    def test_rerank_returns_results(self, mock_tokenizer_cls, mock_model_cls):
        mock_tokenizer = MagicMock()
        mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

        mock_model = MagicMock()
        mock_model_cls.from_pretrained.return_value = mock_model

        mock_encoded = {
            "input_ids": MagicMock(),
            "attention_mask": MagicMock(),
        }
        mock_tokenizer.return_value = mock_encoded

        mock_output = self._make_mock_model_output([0.5, 0.9, 0.3])
        mock_model.return_value = mock_output
        mock_model.eval.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_model.to.return_value = mock_model

        with patch("src.reranker.torch.cuda.is_available", return_value=False):
            reranker = Reranker(model_name="test-model", device="cpu")

        results = self._make_test_results()
        reranked = reranker.rerank("茅台营收", results)

        assert len(reranked) == 3
        assert all("rerank_score" in r for r in reranked)
        assert reranked[0]["rerank_score"] >= reranked[1]["rerank_score"]

    @patch("src.reranker.AutoModelForSequenceClassification")
    @patch("src.reranker.AutoTokenizer")
    def test_rerank_top_n_limits_results(self, mock_tokenizer_cls, mock_model_cls):
        mock_tokenizer = MagicMock()
        mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

        mock_model = MagicMock()
        mock_model_cls.from_pretrained.return_value = mock_model

        mock_encoded = {
            "input_ids": MagicMock(),
            "attention_mask": MagicMock(),
        }
        mock_tokenizer.return_value = mock_encoded

        mock_output = self._make_mock_model_output([0.5, 0.9, 0.3])
        mock_model.return_value = mock_output
        mock_model.eval.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_model.to.return_value = mock_model

        with patch("src.reranker.torch.cuda.is_available", return_value=False):
            reranker = Reranker(model_name="test-model", device="cpu")

        results = self._make_test_results()
        reranked = reranker.rerank("茅台营收", results, top_n=2)

        assert len(reranked) == 2

    def test_rerank_empty_query_raises(self):
        with patch("src.reranker.AutoModelForSequenceClassification"), \
             patch("src.reranker.AutoTokenizer"):
            pass

        reranker = object.__new__(Reranker)
        with pytest.raises(ConfigurationError, match="Query must be a non-empty string"):
            reranker.rerank("", self._make_test_results())

    def test_rerank_empty_results_returns_empty(self):
        reranker = object.__new__(Reranker)
        result = reranker.rerank("test query", [])
        assert result == []

    @patch("src.reranker.AutoModelForSequenceClassification")
    @patch("src.reranker.AutoTokenizer")
    def test_rerank_preserves_metadata(self, mock_tokenizer_cls, mock_model_cls):
        mock_tokenizer = MagicMock()
        mock_tokenizer_cls.from_pretrained.return_value = mock_tokenizer

        mock_model = MagicMock()
        mock_model_cls.from_pretrained.return_value = mock_model

        mock_encoded = {
            "input_ids": MagicMock(),
            "attention_mask": MagicMock(),
        }
        mock_tokenizer.return_value = mock_encoded

        mock_output = self._make_mock_model_output([0.5, 0.9, 0.3])
        mock_model.return_value = mock_output
        mock_model.eval.return_value = mock_model
        mock_model.half.return_value = mock_model
        mock_model.to.return_value = mock_model

        with patch("src.reranker.torch.cuda.is_available", return_value=False):
            reranker = Reranker(model_name="test-model", device="cpu")

        results = self._make_test_results()
        reranked = reranker.rerank("茅台营收", results)

        for r in reranked:
            assert "chunk_id" in r
            assert "text" in r
            assert "metadata" in r
            assert "score" in r
