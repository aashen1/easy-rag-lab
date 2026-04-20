"""
Tests for the evaluator module.

This module tests the evaluator base classes and implementations.
"""

import pytest
from typing import Dict, List
from unittest.mock import patch, MagicMock

from eval.evaluators.base import BaseEvaluator, EvaluationResult
from eval.evaluators.builtin_evaluator import BuiltinEvaluator
from eval.evaluators.ragas_evaluator import RagasEvaluator


class TestEvaluationResult:
    """Tests for EvaluationResult dataclass."""

    def test_evaluation_result_creation(self):
        """Test creating an EvaluationResult instance."""
        result = EvaluationResult(
            question_id="test_001",
            question="What is Python?",
            answer="Python is a programming language.",
            contexts=["Python is a high-level programming language."],
            retrieval_metrics={"hit_rate": 1.0, "mrr": 1.0},
            generation_metrics={"faithfulness": 0.9},
        )

        assert result.question_id == "test_001"
        assert result.question == "What is Python?"
        assert result.answer == "Python is a programming language."
        assert len(result.contexts) == 1
        assert result.retrieval_metrics["hit_rate"] == 1.0
        assert result.generation_metrics["faithfulness"] == 0.9
        assert result.error is None

    def test_evaluation_result_with_error(self):
        """Test creating an EvaluationResult with an error."""
        result = EvaluationResult(
            question_id="test_002",
            question="What is Java?",
            answer="",
            contexts=[],
            retrieval_metrics={},
            generation_metrics={},
            error="Failed to generate answer",
        )

        assert result.error == "Failed to generate answer"

    def test_evaluation_result_to_dict(self):
        """Test converting EvaluationResult to dictionary."""
        result = EvaluationResult(
            question_id="test_003",
            question="What is C++?",
            answer="C++ is a programming language.",
            contexts=["C++ is a general-purpose programming language."],
            retrieval_metrics={"ndcg": 0.8},
            generation_metrics={"answer_relevancy": 0.85},
        )

        result_dict = result.to_dict()

        assert isinstance(result_dict, dict)
        assert result_dict["question_id"] == "test_003"
        assert result_dict["question"] == "What is C++?"
        assert "retrieval_metrics" in result_dict
        assert "generation_metrics" in result_dict


class TestBuiltinEvaluator:
    """Tests for BuiltinEvaluator."""

    def test_evaluator_name(self):
        """Test evaluator name property."""
        evaluator = BuiltinEvaluator()
        assert evaluator.name == "builtin"

    def test_supported_retrieval_metrics(self):
        """Test supported retrieval metrics."""
        evaluator = BuiltinEvaluator()
        metrics = evaluator.supported_retrieval_metrics

        assert "hit_rate" in metrics
        assert "mrr" in metrics
        assert "ndcg" in metrics
        assert "chunk_hit_rate" in metrics
        assert "chunk_mrr" in metrics
        assert "chunk_ndcg" in metrics
        assert "dedup_hit_rate" in metrics
        assert "dedup_mrr" in metrics
        assert "dedup_ndcg" in metrics
        assert "false_positive_rate" in metrics
        assert "context_precision" in metrics
        assert "context_recall" in metrics

    def test_supported_generation_metrics(self):
        """Test supported generation metrics."""
        evaluator = BuiltinEvaluator()
        metrics = evaluator.supported_generation_metrics

        assert "faithfulness" in metrics
        assert "answer_relevancy" in metrics

    def test_evaluate_single_retrieval(self):
        """Test evaluating a single sample with retrieval metrics."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_001",
            question="What is Python?",
            answer="Python is a programming language.",
            contexts=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
            expected_sources=["doc1.pdf", "doc4.pdf"],
        )

        assert result.question_id == "test_001"
        assert "hit_rate" in result.retrieval_metrics
        assert "mrr" in result.retrieval_metrics
        assert "ndcg" in result.retrieval_metrics
        assert result.retrieval_metrics["hit_rate"] == 1.0
        assert result.error is None

    def test_evaluate_single_no_expected_sources(self):
        """Test evaluating without expected sources."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_002",
            question="What is Python?",
            answer="Python is a programming language.",
            contexts=["doc1.pdf", "doc2.pdf"],
        )

        assert result.retrieval_metrics == {}

    def test_validate_metrics(self):
        """Test metric validation."""
        evaluator = BuiltinEvaluator()

        errors = evaluator.validate_metrics(
            retrieval_metrics=["hit_rate", "invalid_metric"],
            generation_metrics=["faithfulness", "unknown_metric"],
        )

        assert len(errors) == 2
        assert any("invalid_metric" in e for e in errors)
        assert any("unknown_metric" in e for e in errors)

    def test_validate_metrics_valid(self):
        """Test metric validation with valid metrics."""
        evaluator = BuiltinEvaluator()

        errors = evaluator.validate_metrics(
            retrieval_metrics=["hit_rate", "mrr", "ndcg"],
            generation_metrics=["faithfulness", "answer_relevancy"],
        )

        assert len(errors) == 0

    def test_evaluate_single_chunk_metrics(self):
        """Test evaluating with chunk-level metrics."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_chunk_001",
            question="What is the revenue?",
            answer="Revenue is $1M.",
            contexts=["doc1.pdf", "doc2.pdf"],
            expected_sources=["doc1.pdf"],
            chunk_ids=["doc1_001", "doc2_003"],
            expected_chunks=["doc1_001", "doc1_002"],
            retrieval_metrics=["chunk_hit_rate", "chunk_mrr", "chunk_ndcg"],
        )

        assert "chunk_hit_rate" in result.retrieval_metrics
        assert "chunk_mrr" in result.retrieval_metrics
        assert "chunk_ndcg" in result.retrieval_metrics
        assert result.retrieval_metrics["chunk_hit_rate"] == 1.0
        assert result.retrieval_metrics["chunk_mrr"] == 1.0
        assert result.error is None

    def test_evaluate_single_chunk_metrics_not_computed_without_data(self):
        """Test that chunk metrics are not computed when chunk_ids are missing."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_chunk_002",
            question="What is the revenue?",
            answer="Revenue is $1M.",
            contexts=["doc1.pdf"],
            expected_sources=["doc1.pdf"],
            retrieval_metrics=["chunk_hit_rate", "chunk_mrr", "chunk_ndcg"],
        )

        assert "chunk_hit_rate" not in result.retrieval_metrics
        assert "chunk_mrr" not in result.retrieval_metrics
        assert "chunk_ndcg" not in result.retrieval_metrics

    def test_evaluate_single_dedup_metrics(self):
        """Test evaluating with dedup metrics."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_dedup_001",
            question="What is the revenue?",
            answer="Revenue is $1M.",
            contexts=["doc1.pdf", "doc1.pdf", "doc2.pdf"],
            expected_sources=["doc1.pdf"],
            retrieval_metrics=["dedup_hit_rate", "dedup_mrr", "dedup_ndcg"],
        )

        assert "dedup_hit_rate" in result.retrieval_metrics
        assert "dedup_mrr" in result.retrieval_metrics
        assert "dedup_ndcg" in result.retrieval_metrics
        assert result.retrieval_metrics["dedup_hit_rate"] == 1.0
        assert result.error is None

    def test_evaluate_single_dedup_metrics_with_equivalence_groups(self):
        """Test evaluating dedup metrics with equivalence groups."""
        evaluator = BuiltinEvaluator()

        equivalence_groups = {
            "doc1": ["doc1.pdf", "doc1_summary.pdf"],
        }

        result = evaluator.evaluate_single(
            question_id="test_dedup_eq_001",
            question="What is the revenue?",
            answer="Revenue is $1M.",
            contexts=["doc1_summary.pdf", "doc2.pdf"],
            expected_sources=["doc1.pdf"],
            equivalence_groups=equivalence_groups,
            retrieval_metrics=["dedup_hit_rate", "dedup_mrr", "dedup_ndcg"],
        )

        assert "dedup_hit_rate" in result.retrieval_metrics
        assert result.retrieval_metrics["dedup_hit_rate"] == 1.0
        assert result.error is None

    def test_evaluate_single_fpr_metric(self):
        """Test evaluating with false positive rate for irrelevant questions."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_fpr_001",
            question="Tell me a joke.",
            answer="I don't know.",
            contexts=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
            expect_retrieval=False,
            retrieval_metrics=["false_positive_rate"],
        )

        assert "false_positive_rate" in result.retrieval_metrics
        assert result.retrieval_metrics["false_positive_rate"] == 0.6
        assert result.error is None

    def test_evaluate_single_fpr_not_computed_for_retrieval_questions(self):
        """Test that FPR is not computed for questions that expect retrieval."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_fpr_002",
            question="What is the revenue?",
            answer="Revenue is $1M.",
            contexts=["doc1.pdf"],
            expected_sources=["doc1.pdf"],
            expect_retrieval=True,
            retrieval_metrics=["false_positive_rate"],
        )

        assert "false_positive_rate" not in result.retrieval_metrics

    @patch("eval.evaluators.builtin_evaluator.calculate_context_precision")
    @patch("eval.evaluators.builtin_evaluator.calculate_context_recall")
    def test_evaluate_single_context_precision_recall(self, mock_recall, mock_precision):
        """Test evaluating with context precision and recall metrics."""
        mock_precision.return_value = 0.85
        mock_recall.return_value = 0.72

        evaluator = BuiltinEvaluator()
        llm_config = {
            "api_key": "test-key",
            "base_url": "https://api.example.com",
            "model_name": "test-model",
        }

        result = evaluator.evaluate_single(
            question_id="test_ctx_001",
            question="What is the revenue?",
            answer="Revenue is $1M.",
            contexts=["Revenue was $1M in 2023."],
            expected_answer="The revenue was $1 million in 2023.",
            llm_config=llm_config,
            retrieval_metrics=["context_precision", "context_recall"],
        )

        assert "context_precision" in result.retrieval_metrics
        assert "context_recall" in result.retrieval_metrics
        assert result.retrieval_metrics["context_precision"] == 0.85
        assert result.retrieval_metrics["context_recall"] == 0.72
        assert result.error is None

    @patch("eval.evaluators.builtin_evaluator.calculate_context_precision")
    def test_evaluate_single_context_precision_error_handling(self, mock_precision):
        """Test that context_precision errors are handled gracefully."""
        mock_precision.side_effect = Exception("LLM API error")

        evaluator = BuiltinEvaluator()
        llm_config = {
            "api_key": "test-key",
            "base_url": "https://api.example.com",
            "model_name": "test-model",
        }

        result = evaluator.evaluate_single(
            question_id="test_ctx_err_001",
            question="What is the revenue?",
            answer="Revenue is $1M.",
            contexts=["Revenue was $1M in 2023."],
            llm_config=llm_config,
            retrieval_metrics=["context_precision"],
        )

        assert "context_precision" in result.retrieval_metrics
        assert result.retrieval_metrics["context_precision"] is None

    def test_evaluate_single_no_retrieval_for_irrelevant_question(self):
        """Test that basic retrieval metrics are skipped for irrelevant questions."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_irrelevant_001",
            question="Tell me a joke.",
            answer="I don't know.",
            contexts=["doc1.pdf"],
            expected_sources=["doc1.pdf"],
            expect_retrieval=False,
            retrieval_metrics=["hit_rate", "mrr", "ndcg"],
        )

        assert "hit_rate" not in result.retrieval_metrics
        assert "mrr" not in result.retrieval_metrics
        assert "ndcg" not in result.retrieval_metrics

    def test_evaluate_batch_with_new_params(self):
        """Test batch evaluation with new parameters."""
        evaluator = BuiltinEvaluator()

        samples = [
            {
                "question_id": "batch_001",
                "question": "What is the revenue?",
                "answer": "Revenue is $1M.",
                "contexts": ["doc1.pdf", "doc2.pdf"],
                "expected_sources": ["doc1.pdf"],
                "chunk_ids": ["doc1_001", "doc2_003"],
                "expected_chunks": ["doc1_001"],
                "expect_retrieval": True,
            },
            {
                "question_id": "batch_002",
                "question": "Tell me a joke.",
                "answer": "I don't know.",
                "contexts": ["doc3.pdf", "doc4.pdf"],
                "expect_retrieval": False,
            },
        ]

        results = evaluator.evaluate_batch(
            samples,
            retrieval_metrics=["hit_rate", "chunk_hit_rate", "false_positive_rate"],
        )

        assert len(results) == 2
        assert "hit_rate" in results[0].retrieval_metrics
        assert "chunk_hit_rate" in results[0].retrieval_metrics
        assert "false_positive_rate" in results[1].retrieval_metrics


class TestRagasEvaluator:
    """Tests for RagasEvaluator."""

    def test_evaluator_name(self):
        """Test evaluator name property."""
        evaluator = RagasEvaluator()
        assert evaluator.name == "ragas"

    def test_supported_retrieval_metrics(self):
        """Test supported retrieval metrics (should be empty for RAGAS)."""
        evaluator = RagasEvaluator()
        metrics = evaluator.supported_retrieval_metrics

        assert len(metrics) == 0

    def test_supported_generation_metrics(self):
        """Test supported generation metrics."""
        evaluator = RagasEvaluator()
        metrics = evaluator.supported_generation_metrics

        assert "faithfulness" in metrics
        assert "answer_relevancy" in metrics
        assert "context_precision" in metrics
        assert "context_recall" in metrics
        assert "answer_correctness" in metrics
        assert "semantic_similarity" in metrics

    def test_evaluate_single_without_llm_config(self):
        """Test evaluating without LLM config should raise error."""
        evaluator = RagasEvaluator()

        result = evaluator.evaluate_single(
            question_id="test_001",
            question="What is Python?",
            answer="Python is a programming language.",
            contexts=["Python is a high-level programming language."],
        )

        assert result.error is not None
        assert "llm_config" in result.error.lower()


class TestRagasEvaluatorMocked:
    """Tests for RagasEvaluator with mocked RAGAS dependencies."""

    def test_evaluate_single_with_mock_llm(self):
        """Test single evaluation with mocked LLM and embeddings."""
        config = {
            "ragas": {
                "run_config": {"max_workers": 2, "timeout": 30},
                "embedding": {"model_name": "test-model", "device": "cpu"},
            }
        }
        evaluator = RagasEvaluator(config=config)

        mock_result = MagicMock()
        mock_result.scores = [{"faithfulness": 0.85, "answer_relevancy": 0.72}]

        with patch.object(RagasEvaluator, "_create_llm", return_value=MagicMock()), \
             patch.object(RagasEvaluator, "_create_embeddings", return_value=MagicMock()), \
             patch.object(RagasEvaluator, "_create_metrics", return_value=[MagicMock()]), \
             patch.object(RagasEvaluator, "_build_ragas_dataset", return_value=MagicMock()), \
             patch.object(RagasEvaluator, "_build_run_config", return_value=MagicMock()), \
             patch("ragas.evaluate", return_value=mock_result):

            result = evaluator.evaluate_single(
                question_id="q1",
                question="What is RAG?",
                answer="RAG is retrieval-augmented generation.",
                contexts=["RAG combines retrieval and generation."],
                expected_answer="RAG is a technique that combines retrieval with generation.",
                llm_config={"api_key": "test", "base_url": "http://test", "model_name": "test-model"},
                generation_metrics=["faithfulness", "answer_relevancy"],
            )

            assert result.question_id == "q1"
            assert result.generation_metrics.get("faithfulness") == 0.85
            assert result.generation_metrics.get("answer_relevancy") == 0.72
            assert result.error is None

    def test_evaluate_batch_with_mock(self):
        """Test batch evaluation with mocked RAGAS."""
        evaluator = RagasEvaluator(config={})

        mock_result = MagicMock()
        mock_result.scores = [
            {"faithfulness": 0.9, "answer_relevancy": 0.8},
            {"faithfulness": 0.7, "answer_relevancy": 0.6},
        ]

        samples = [
            {"question_id": "q1", "question": "Q1", "answer": "A1", "contexts": ["C1"]},
            {"question_id": "q2", "question": "Q2", "answer": "A2", "contexts": ["C2"]},
        ]

        with patch.object(RagasEvaluator, "_create_llm", return_value=MagicMock()), \
             patch.object(RagasEvaluator, "_create_embeddings", return_value=MagicMock()), \
             patch.object(RagasEvaluator, "_create_metrics", return_value=[MagicMock()]), \
             patch.object(RagasEvaluator, "_build_ragas_dataset", return_value=MagicMock()), \
             patch.object(RagasEvaluator, "_build_run_config", return_value=MagicMock()), \
             patch("ragas.evaluate", return_value=mock_result):

            results = evaluator.evaluate_batch(
                samples=samples,
                llm_config={"api_key": "test", "base_url": "http://test", "model_name": "test-model"},
                generation_metrics=["faithfulness", "answer_relevancy"],
            )

            assert len(results) == 2
            assert results[0].generation_metrics.get("faithfulness") == 0.9
            assert results[1].generation_metrics.get("faithfulness") == 0.7

    def test_ragas_exclusive_metrics_validated(self):
        """Test that RAGAS-exclusive metrics are properly validated."""
        evaluator = RagasEvaluator(config={})

        assert "answer_correctness" in evaluator.supported_generation_metrics
        assert "semantic_similarity" in evaluator.supported_generation_metrics

        errors = evaluator.validate_metrics(
            generation_metrics=["answer_correctness", "semantic_similarity"]
        )
        assert len(errors) == 0

    def test_ragas_unsupported_metrics(self):
        """Test that unsupported metrics are caught."""
        evaluator = RagasEvaluator(config={})

        errors = evaluator.validate_metrics(
            generation_metrics=["nonexistent_metric"]
        )
        assert len(errors) > 0


class TestEvaluatorIntegration:
    """Integration tests for evaluators."""

    def test_builtin_evaluator_batch(self):
        """Test batch evaluation with builtin evaluator."""
        evaluator = BuiltinEvaluator()

        samples = [
            {
                "question_id": "test_001",
                "question": "What is Python?",
                "answer": "Python is a programming language.",
                "contexts": ["doc1.pdf", "doc2.pdf"],
                "expected_sources": ["doc1.pdf"],
            },
            {
                "question_id": "test_002",
                "question": "What is Java?",
                "answer": "Java is a programming language.",
                "contexts": ["doc3.pdf", "doc4.pdf"],
                "expected_sources": ["doc3.pdf", "doc5.pdf"],
            },
        ]

        results = evaluator.evaluate_batch(samples)

        assert len(results) == 2
        assert all(r.question_id.startswith("test_") for r in results)
        assert all("hit_rate" in r.retrieval_metrics for r in results)

    def test_evaluator_factory_pattern(self):
        """Test creating evaluators based on configuration."""
        from eval.evaluators import BuiltinEvaluator, RagasEvaluator

        backends = ["builtin", "ragas"]
        evaluators = []

        if "builtin" in backends:
            evaluators.append(BuiltinEvaluator())

        if "ragas" in backends:
            evaluators.append(RagasEvaluator())

        assert len(evaluators) == 2
        assert evaluators[0].name == "builtin"
        assert evaluators[1].name == "ragas"
