"""
Tests for the evaluator module.

This module tests the evaluator base classes and implementations.
"""

import pytest
from typing import Dict, List

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
