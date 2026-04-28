"""
Tests for the evaluator module.

This module tests the evaluator base classes and implementations.
"""

from unittest.mock import MagicMock, patch

import pytest

from eval.evaluators.base import EvaluationResult, EvaluationSample
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


class TestEvaluationSample:
    """Tests for EvaluationSample dataclass."""

    def test_evaluation_sample_creation(self):
        """Test creating an EvaluationSample instance."""
        sample = EvaluationSample(
            question_id="test_001",
            question="What is Python?",
            answer="Python is a programming language.",
            contexts=["Python is a high-level programming language."],
            expected_sources=["doc1.pdf"],
        )

        assert sample.question_id == "test_001"
        assert sample.question == "What is Python?"
        assert sample.answer == "Python is a programming language."
        assert len(sample.contexts) == 1
        assert sample.expected_sources == ["doc1.pdf"]
        assert sample.expect_retrieval is True
        assert sample.expect_no_answer is False

    def test_evaluation_sample_defaults(self):
        """Test EvaluationSample default values."""
        sample = EvaluationSample()

        assert sample.question_id == ""
        assert sample.question == ""
        assert sample.answer == ""
        assert sample.contexts == []
        assert sample.expected_sources is None
        assert sample.expected_answer is None
        assert sample.llm_config is None
        assert sample.retrieval_metrics is None
        assert sample.generation_metrics is None
        assert sample.chunk_ids is None
        assert sample.expected_chunks is None
        assert sample.equivalence_groups is None
        assert sample.expect_retrieval is True
        assert sample.expect_no_answer is False
        assert sample.retrieved_sources is None
        assert sample.question_type is None


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
            EvaluationSample(
                question_id="test_001",
                question="What is Python?",
                answer="Python is a programming language.",
                contexts=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
                expected_sources=["doc1.pdf", "doc4.pdf"],
            )
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
            EvaluationSample(
                question_id="test_002",
                question="What is Python?",
                answer="Python is a programming language.",
                contexts=["doc1.pdf", "doc2.pdf"],
            )
        )

        assert "hit_rate" not in result.retrieval_metrics
        assert "mrr" not in result.retrieval_metrics
        assert "ndcg" not in result.retrieval_metrics

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
            EvaluationSample(
                question_id="test_chunk_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1.pdf", "doc2.pdf"],
                expected_sources=["doc1.pdf"],
                chunk_ids=["doc1::chunk::001", "doc2::chunk::003"],
                expected_chunks=["doc1::chunk::001", "doc1::chunk::002"],
                retrieval_metrics=["chunk_hit_rate", "chunk_mrr", "chunk_ndcg"],
            )
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
            EvaluationSample(
                question_id="test_chunk_002",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1.pdf"],
                expected_sources=["doc1.pdf"],
                retrieval_metrics=["chunk_hit_rate", "chunk_mrr", "chunk_ndcg"],
            )
        )

        assert "chunk_hit_rate" not in result.retrieval_metrics
        assert "chunk_mrr" not in result.retrieval_metrics
        assert "chunk_ndcg" not in result.retrieval_metrics

    def test_evaluate_single_dedup_metrics(self):
        """Test evaluating with dedup metrics."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_dedup_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1.pdf", "doc1.pdf", "doc2.pdf"],
                expected_sources=["doc1.pdf"],
                retrieval_metrics=["dedup_hit_rate", "dedup_mrr", "dedup_ndcg"],
            )
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
            EvaluationSample(
                question_id="test_dedup_eq_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1_summary.pdf", "doc2.pdf"],
                expected_sources=["doc1.pdf"],
                equivalence_groups=equivalence_groups,
                retrieval_metrics=["dedup_hit_rate", "dedup_mrr", "dedup_ndcg"],
            )
        )

        assert "dedup_hit_rate" in result.retrieval_metrics
        assert result.retrieval_metrics["dedup_hit_rate"] == 1.0
        assert result.error is None

    def test_evaluate_single_fpr_metric(self):
        """Test evaluating with false positive rate for irrelevant questions."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_fpr_001",
                question="Tell me a joke.",
                answer="I don't know.",
                contexts=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
                expect_retrieval=False,
                retrieval_metrics=["false_positive_rate"],
            )
        )

        assert "false_positive_rate" in result.retrieval_metrics
        assert result.retrieval_metrics["false_positive_rate"] == 0.6
        assert result.error is None

    def test_evaluate_single_fpr_not_computed_for_retrieval_questions(self):
        """Test that FPR is not computed for questions that expect retrieval."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_fpr_002",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1.pdf"],
                expected_sources=["doc1.pdf"],
                expect_retrieval=True,
                retrieval_metrics=["false_positive_rate"],
            )
        )

        assert "false_positive_rate" not in result.retrieval_metrics

    @patch("eval.evaluators.builtin_evaluator.calculate_context_precision")
    @patch("eval.evaluators.builtin_evaluator.calculate_context_recall")
    def test_evaluate_single_context_precision_recall(
        self, mock_recall, mock_precision
    ):
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
            EvaluationSample(
                question_id="test_ctx_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["Revenue was $1M in 2023."],
                expected_answer="The revenue was $1 million in 2023.",
                llm_config=llm_config,
                retrieval_metrics=["context_precision", "context_recall"],
            )
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
            EvaluationSample(
                question_id="test_ctx_err_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["Revenue was $1M in 2023."],
                expected_sources=["doc1.pdf"],
                expected_answer="Revenue is $1M.",
                expect_retrieval=True,
                llm_config=llm_config,
                retrieval_metrics=["context_precision"],
            )
        )

        assert "context_precision" in result.retrieval_metrics
        assert result.retrieval_metrics["context_precision"] is None

    def test_evaluate_single_no_retrieval_for_irrelevant_question(self):
        """Test that basic retrieval metrics are skipped for truly irrelevant questions (no expected_sources)."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_irrelevant_001",
                question="Tell me a joke.",
                answer="I don't know.",
                contexts=["doc1.pdf"],
                expected_sources=[],
                expect_retrieval=False,
                retrieval_metrics=["hit_rate", "mrr", "ndcg", "false_positive_rate"],
            )
        )

        assert "hit_rate" not in result.retrieval_metrics
        assert "mrr" not in result.retrieval_metrics
        assert "ndcg" not in result.retrieval_metrics
        assert "false_positive_rate" in result.retrieval_metrics

    def test_evaluate_batch_with_new_params(self):
        """Test batch evaluation with new parameters."""
        evaluator = BuiltinEvaluator()

        samples = [
            EvaluationSample(
                question_id="batch_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1.pdf", "doc2.pdf"],
                expected_sources=["doc1.pdf"],
                chunk_ids=["doc1::chunk::001", "doc2::chunk::003"],
                expected_chunks=["doc1::chunk::001"],
                expect_retrieval=True,
            ),
            EvaluationSample(
                question_id="batch_002",
                question="Tell me a joke.",
                answer="I don't know.",
                contexts=["doc3.pdf", "doc4.pdf"],
                expect_retrieval=False,
            ),
        ]

        results = evaluator.evaluate_batch(
            samples,
            retrieval_metrics=["hit_rate", "chunk_hit_rate", "false_positive_rate"],
        )

        assert len(results) == 2
        assert "hit_rate" in results[0].retrieval_metrics
        assert "chunk_hit_rate" in results[0].retrieval_metrics
        assert "false_positive_rate" in results[1].retrieval_metrics

    def test_retrieved_sources_used_for_retrieval_metrics(self):
        """Test that retrieved_sources is used for retrieval metrics when provided."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_sep_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["Revenue was $1M in 2023.", "Profit was $500K."],
                expected_sources=["doc1.pdf", "doc4.pdf"],
                retrieved_sources=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
                retrieval_metrics=["hit_rate", "mrr", "ndcg"],
            )
        )

        assert result.retrieval_metrics["hit_rate"] == 1.0
        assert result.retrieval_metrics["mrr"] == 1.0
        assert result.error is None

    def test_contexts_used_for_generation_metrics(self):
        """Test that contexts (text content) is used for faithfulness, not retrieved_sources."""
        evaluator = BuiltinEvaluator()
        llm_config = {
            "api_key": "test-key",
            "base_url": "https://api.example.com",
            "model_name": "test-model",
        }

        with patch(
            "eval.evaluators.builtin_evaluator.calculate_faithfulness"
        ) as mock_faith:
            mock_faith.return_value = 0.9

            result = evaluator.evaluate_single(
                EvaluationSample(
                    question_id="test_sep_002",
                    question="What is the revenue?",
                    answer="Revenue is $1M.",
                    contexts=["Revenue was $1M in 2023."],
                    expected_sources=["doc1.pdf"],
                    retrieved_sources=["doc1.pdf", "doc2.pdf"],
                    llm_config=llm_config,
                    generation_metrics=["faithfulness"],
                )
            )

            mock_faith.assert_called_once()
            call_kwargs = mock_faith.call_args.kwargs
            assert call_kwargs["contexts"] == ["Revenue was $1M in 2023."]
            assert call_kwargs["contexts"] != ["doc1.pdf", "doc2.pdf"]
            assert result.generation_metrics["faithfulness"] == 0.9

    def test_backward_compat_contexts_used_for_retrieval_without_retrieved_sources(
        self,
    ):
        """Test backward compatibility: contexts is used for retrieval when retrieved_sources is not provided."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_compat_001",
                question="What is Python?",
                answer="Python is a programming language.",
                contexts=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
                expected_sources=["doc1.pdf", "doc4.pdf"],
            )
        )

        assert result.retrieval_metrics["hit_rate"] == 1.0
        assert result.error is None

    @patch("eval.evaluators.builtin_evaluator.calculate_context_precision")
    @patch("eval.evaluators.builtin_evaluator.calculate_context_recall")
    def test_contexts_used_for_context_precision_recall_not_sources(
        self, mock_recall, mock_precision
    ):
        """Test that contexts (text) is used for context_precision/recall, not retrieved_sources (paths)."""
        mock_precision.return_value = 0.85
        mock_recall.return_value = 0.72

        evaluator = BuiltinEvaluator()
        llm_config = {
            "api_key": "test-key",
            "base_url": "https://api.example.com",
            "model_name": "test-model",
        }

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_sep_ctx_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["Revenue was $1M in 2023."],
                expected_sources=["doc1.pdf"],
                expected_answer="Revenue is $1M.",
                expect_retrieval=True,
                retrieved_sources=["doc1.pdf", "doc2.pdf"],
                llm_config=llm_config,
                retrieval_metrics=["context_precision", "context_recall"],
            )
        )

        mock_precision.assert_called_once()
        precision_kwargs = mock_precision.call_args.kwargs
        assert precision_kwargs["retrieval_context"] == ["Revenue was $1M in 2023."]
        assert precision_kwargs["retrieval_context"] != ["doc1.pdf", "doc2.pdf"]

        mock_recall.assert_called_once()
        recall_kwargs = mock_recall.call_args.kwargs
        assert recall_kwargs["retrieval_context"] == ["Revenue was $1M in 2023."]

        assert result.retrieval_metrics["context_precision"] == 0.85
        assert result.retrieval_metrics["context_recall"] == 0.72

    def test_retrieved_sources_used_for_dedup_metrics(self):
        """Test that retrieved_sources is used for dedup metrics when provided."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_sep_dedup_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["Revenue was $1M in 2023."],
                expected_sources=["doc1.pdf"],
                retrieved_sources=["doc1.pdf", "doc1.pdf", "doc2.pdf"],
                retrieval_metrics=["dedup_hit_rate", "dedup_mrr", "dedup_ndcg"],
            )
        )

        assert "dedup_hit_rate" in result.retrieval_metrics
        assert result.retrieval_metrics["dedup_hit_rate"] == 1.0
        assert result.error is None

    def test_retrieved_sources_used_for_fpr(self):
        """Test that retrieved_sources is used for FPR metric when provided."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_sep_fpr_001",
                question="Tell me a joke.",
                answer="I don't know.",
                contexts=["Some text content here."],
                retrieved_sources=["doc1.pdf", "doc2.pdf", "doc3.pdf"],
                expect_retrieval=False,
                retrieval_metrics=["false_positive_rate"],
            )
        )

        assert "false_positive_rate" in result.retrieval_metrics
        assert result.retrieval_metrics["false_positive_rate"] == 0.6
        assert result.error is None

    def test_evaluate_batch_passes_retrieved_sources(self):
        """Test that evaluate_batch forwards retrieved_sources to evaluate_single."""
        evaluator = BuiltinEvaluator()

        samples = [
            EvaluationSample(
                question_id="batch_sep_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["Revenue was $1M in 2023."],
                expected_sources=["doc1.pdf"],
                retrieved_sources=["doc1.pdf", "doc2.pdf"],
                question_type="factual",
            ),
            EvaluationSample(
                question_id="batch_sep_002",
                question="Tell me a joke.",
                answer="I don't know.",
                contexts=["Some text."],
                retrieved_sources=["doc3.pdf"],
                expect_retrieval=False,
                question_type="irrelevant",
            ),
        ]

        results = evaluator.evaluate_batch(
            samples,
            retrieval_metrics=["hit_rate", "false_positive_rate"],
        )

        assert len(results) == 2
        assert "hit_rate" in results[0].retrieval_metrics
        assert results[0].retrieval_metrics["hit_rate"] == 1.0
        assert "false_positive_rate" in results[1].retrieval_metrics

    def test_missing_type_computes_fpr_not_doc_metrics(self):
        """Test that missing type questions compute FPR but not doc-level metrics."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_missing_001",
                question="What is the quantum computing strategy?",
                answer="The document does not mention quantum computing.",
                contexts=["annual_report/company_2023.pdf"],
                expected_sources=["annual_report/company_2023.pdf"],
                expect_retrieval=False,
                retrieval_metrics=["hit_rate", "mrr", "ndcg", "false_positive_rate"],
            )
        )

        assert "hit_rate" not in result.retrieval_metrics
        assert "mrr" not in result.retrieval_metrics
        assert "ndcg" not in result.retrieval_metrics
        assert "false_positive_rate" in result.retrieval_metrics

    def test_irrelevant_type_computes_fpr_only(self):
        """Test that irrelevant type questions compute FPR but not doc metrics."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_irrelevant_001",
                question="Tell me a joke.",
                answer="I don't know.",
                contexts=["doc1.pdf", "doc2.pdf"],
                expect_retrieval=False,
                retrieval_metrics=["hit_rate", "mrr", "ndcg", "false_positive_rate"],
            )
        )

        assert "hit_rate" not in result.retrieval_metrics
        assert "false_positive_rate" in result.retrieval_metrics

    def test_retrieval_diversity_metric(self):
        """Test that retrieval_diversity is computed when sources exist."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_diversity_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1.pdf", "doc1.pdf", "doc2.pdf"],
                expected_sources=["doc1.pdf"],
                retrieval_metrics=["retrieval_diversity"],
            )
        )

        assert "retrieval_diversity" in result.retrieval_metrics
        assert result.retrieval_metrics["retrieval_diversity"] == pytest.approx(2 / 3)

    def test_retrieval_diversity_all_same_doc(self):
        """Test retrieval_diversity when all results from same document."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_diversity_002",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1.pdf", "doc1.pdf", "doc1.pdf", "doc1.pdf", "doc1.pdf"],
                expected_sources=["doc1.pdf"],
                retrieval_metrics=["retrieval_diversity"],
            )
        )

        assert "retrieval_diversity" in result.retrieval_metrics
        assert result.retrieval_metrics["retrieval_diversity"] == pytest.approx(0.2)

    def test_recall_3_5_10_metrics(self):
        """Test recall_3, recall_5, recall_10 metrics."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_recall_001",
                question="What is the revenue?",
                answer="Revenue is $1M.",
                contexts=["doc1.pdf", "doc3.pdf", "doc4.pdf", "doc2.pdf", "doc5.pdf"],
                expected_sources=["doc1.pdf", "doc2.pdf", "doc6.pdf"],
                retrieval_metrics=["recall_3", "recall_5", "recall_10"],
            )
        )

        assert "recall_3" in result.retrieval_metrics
        assert "recall_5" in result.retrieval_metrics
        assert "recall_10" in result.retrieval_metrics
        assert result.retrieval_metrics["recall_3"] == pytest.approx(1 / 3)
        assert result.retrieval_metrics["recall_5"] == pytest.approx(2 / 3)
        assert result.retrieval_metrics["recall_10"] == pytest.approx(2 / 3)

    def test_recall_not_computed_when_expect_retrieval_false(self):
        """Test that recall metrics are not computed for non-retrieval questions."""
        evaluator = BuiltinEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_recall_no_retrieval",
                question="Tell me a joke.",
                answer="I don't know.",
                contexts=["doc1.pdf"],
                expect_retrieval=False,
                retrieval_metrics=["recall_3", "recall_5", "recall_10"],
            )
        )

        assert "recall_3" not in result.retrieval_metrics
        assert "recall_5" not in result.retrieval_metrics
        assert "recall_10" not in result.retrieval_metrics


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
            EvaluationSample(
                question_id="test_001",
                question="What is Python?",
                answer="Python is a programming language.",
                contexts=["Python is a high-level programming language."],
            )
        )

        assert result.error is not None
        assert "llm_config" in result.error.lower()


class TestRagasEvaluatorConfigReading:
    """Tests for RagasEvaluator configuration reading (Task 3.4)."""

    def test_ragas_config_stored_from_init(self):
        """Test that ragas config is correctly stored during initialization."""
        config = {
            "ragas": {
                "run_config": {"max_workers": 3, "timeout": 45, "max_retries": 1},
                "embedding": {"model_name": "custom-model", "device": "cpu"},
                "embedding_model": "override-model",
                "device": "mps",
            }
        }
        evaluator = RagasEvaluator(config=config)

        assert evaluator._ragas_config == config["ragas"]
        assert evaluator._run_config == {
            "max_workers": 3,
            "timeout": 45,
            "max_retries": 1,
        }
        assert evaluator._embedding_config == {
            "model_name": "custom-model",
            "device": "cpu",
        }

    def test_ragas_config_defaults_when_no_config(self):
        """Test that defaults are used when no config is provided."""
        evaluator = RagasEvaluator(config=None)

        assert evaluator._ragas_config == {}
        assert evaluator._run_config == {}
        assert evaluator._embedding_config == {}

    def test_ragas_config_defaults_when_empty_ragas_section(self):
        """Test that defaults are used when ragas section is empty."""
        evaluator = RagasEvaluator(config={"ragas": {}})

        assert evaluator._ragas_config == {}
        assert evaluator._run_config == {}
        assert evaluator._embedding_config == {}

    def test_build_run_config_uses_configured_values(self):
        """Test that _build_run_config uses values from config."""
        config = {
            "ragas": {
                "run_config": {"max_workers": 10, "timeout": 120, "max_retries": 5},
            }
        }
        evaluator = RagasEvaluator(config=config)

        mock_run_config = MagicMock()
        with patch("ragas.RunConfig", return_value=mock_run_config) as mock_cls:
            result = evaluator._build_run_config()

            mock_cls.assert_called_once_with(max_workers=10, timeout=120, max_retries=5)
            assert result == mock_run_config

    def test_build_run_config_uses_defaults_when_missing(self):
        """Test that _build_run_config uses defaults when config is empty."""
        evaluator = RagasEvaluator(config={})

        mock_run_config = MagicMock()
        with patch("ragas.RunConfig", return_value=mock_run_config) as mock_cls:
            result = evaluator._build_run_config()

            mock_cls.assert_called_once_with(max_workers=5, timeout=60, max_retries=3)
            assert result == mock_run_config

    def test_build_run_config_partial_override(self):
        """Test that _build_run_config allows partial overrides with defaults."""
        config = {
            "ragas": {
                "run_config": {"max_workers": 8},
            }
        }
        evaluator = RagasEvaluator(config=config)

        mock_run_config = MagicMock()
        with patch("ragas.RunConfig", return_value=mock_run_config) as mock_cls:
            _ = evaluator._build_run_config()

            mock_cls.assert_called_once_with(max_workers=8, timeout=60, max_retries=3)

    def test_build_run_config_returns_none_on_import_error(self):
        """Test that _build_run_config returns None when RunConfig is not available."""
        evaluator = RagasEvaluator(config={})

        with patch("ragas.RunConfig", side_effect=ImportError):
            result = evaluator._build_run_config()

            assert result is None

    def test_create_embeddings_uses_ragas_config_embedding_model(self):
        """Test that _create_embeddings uses embedding_model from ragas config."""
        config = {
            "ragas": {
                "embedding_model": "custom-bge-model",
                "device": "cpu",
            }
        }
        evaluator = RagasEvaluator(config=config)

        mock_ragas_embeddings = MagicMock()
        with patch(
            "ragas.embeddings.HuggingFaceEmbeddings", return_value=mock_ragas_embeddings
        ) as mock_cls:
            result = evaluator._create_embeddings(config)

            mock_cls.assert_called_once_with(
                model="custom-bge-model",
                device="cpu",
            )
            assert hasattr(result, "embed_query")
            assert hasattr(result, "embed_documents")

    def test_create_embeddings_uses_embedding_subconfig_as_fallback(self):
        """Test that _create_embeddings falls back to embedding sub-config."""
        config = {
            "ragas": {
                "embedding": {"model_name": "fallback-model", "device": "mps"},
            }
        }
        evaluator = RagasEvaluator(config=config)

        mock_ragas_embeddings = MagicMock()
        with patch(
            "ragas.embeddings.HuggingFaceEmbeddings", return_value=mock_ragas_embeddings
        ) as mock_cls:
            result = evaluator._create_embeddings(config)

            mock_cls.assert_called_once_with(
                model="fallback-model",
                device="mps",
            )
            assert hasattr(result, "embed_query")

    def test_create_embeddings_ragas_config_overrides_subconfig(self):
        """Test that top-level ragas config keys override embedding sub-config."""
        config = {
            "ragas": {
                "embedding_model": "top-level-model",
                "device": "cuda:1",
                "embedding": {"model_name": "sub-model", "device": "cpu"},
            }
        }
        evaluator = RagasEvaluator(config=config)

        mock_ragas_embeddings = MagicMock()
        with patch(
            "ragas.embeddings.HuggingFaceEmbeddings", return_value=mock_ragas_embeddings
        ) as mock_cls:
            result = evaluator._create_embeddings(config)

            mock_cls.assert_called_once_with(
                model="top-level-model",
                device="cuda:1",
            )
            assert hasattr(result, "embed_query")

    def test_create_embeddings_uses_defaults_when_no_config(self):
        """Test that _create_embeddings uses defaults when no config is provided."""
        evaluator = RagasEvaluator(config={})

        mock_ragas_embeddings = MagicMock()
        with patch(
            "ragas.embeddings.HuggingFaceEmbeddings", return_value=mock_ragas_embeddings
        ) as mock_cls:
            result = evaluator._create_embeddings({})

            mock_cls.assert_called_once_with(
                model="BAAI/bge-large-zh-v1.5",
                device="cuda",
            )
            assert hasattr(result, "embed_query")

    def test_create_embeddings_uses_config_embedding_key_as_fallback(self):
        """Test that _create_embeddings falls back to config['embedding'] when no ragas config."""
        evaluator = RagasEvaluator(config={})
        system_config = {
            "embedding": {"model_name": "system-model", "device": "cpu"},
        }

        mock_ragas_embeddings = MagicMock()
        with patch(
            "ragas.embeddings.HuggingFaceEmbeddings", return_value=mock_ragas_embeddings
        ) as mock_cls:
            result = evaluator._create_embeddings(system_config)

            mock_cls.assert_called_once_with(
                model="system-model",
                device="cpu",
            )
            assert hasattr(result, "embed_query")


class TestRagasEvaluatorReferenceWarning:
    """Tests for reference-missing warning behavior in RagasEvaluator."""

    def test_evaluate_single_skips_ref_required_metrics_when_no_expected_answer(self):
        """Test that reference-required metrics are skipped when expected_answer is None."""
        evaluator = RagasEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_no_ref",
                question="What is Python?",
                answer="Python is a programming language.",
                contexts=["Python is a high-level programming language."],
                expected_answer=None,
                generation_metrics=[
                    "faithfulness",
                    "context_precision",
                    "context_recall",
                ],
            )
        )

        assert result.error is not None
        assert "llm_config" in result.error.lower() or result.generation_metrics == {}

    def test_evaluate_single_with_ref_required_metrics_and_no_answer(self):
        """Test that when expected_answer is None and only ref-required metrics are requested,
        the result has empty generation_metrics (no crash)."""
        evaluator = RagasEvaluator()

        result = evaluator.evaluate_single(
            EvaluationSample(
                question_id="test_no_ref_2",
                question="What is Python?",
                answer="Python is a programming language.",
                contexts=["Python is a high-level programming language."],
                expected_answer=None,
                generation_metrics=["context_precision", "context_recall"],
            )
        )

        assert result.generation_metrics == {}

    def test_evaluate_batch_does_not_crash_on_missing_reference(self):
        """Test that evaluate_batch handles missing expected_answer gracefully."""
        evaluator = RagasEvaluator()

        samples = [
            EvaluationSample(
                question_id="q1",
                question="What is X?",
                answer="X is Y.",
                contexts=["X is Y."],
                expected_answer=None,
            ),
        ]

        with patch.object(evaluator, "_create_llm", side_effect=Exception("no LLM")):
            result = evaluator.evaluate_batch(
                samples=samples,
                llm_config={"api_key": "test"},
                generation_metrics=["context_precision", "faithfulness"],
            )

        assert isinstance(result, list)


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

        with (
            patch.object(RagasEvaluator, "_create_llm", return_value=MagicMock()),
            patch.object(
                RagasEvaluator, "_create_embeddings", return_value=MagicMock()
            ),
            patch.object(RagasEvaluator, "_create_metrics", return_value=[MagicMock()]),
            patch.object(
                RagasEvaluator, "_build_ragas_dataset", return_value=MagicMock()
            ),
            patch.object(RagasEvaluator, "_build_run_config", return_value=MagicMock()),
            patch("ragas.evaluate", return_value=mock_result),
        ):
            result = evaluator.evaluate_single(
                EvaluationSample(
                    question_id="q1",
                    question="What is RAG?",
                    answer="RAG is retrieval-augmented generation.",
                    contexts=["RAG combines retrieval and generation."],
                    expected_answer="RAG is a technique that combines retrieval with generation.",
                    llm_config={
                        "api_key": "test",
                        "base_url": "http://test",
                        "model_name": "test-model",
                    },
                    generation_metrics=["faithfulness", "answer_relevancy"],
                )
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
            EvaluationSample(
                question_id="q1", question="Q1", answer="A1", contexts=["C1"]
            ),
            EvaluationSample(
                question_id="q2", question="Q2", answer="A2", contexts=["C2"]
            ),
        ]

        with (
            patch.object(RagasEvaluator, "_create_llm", return_value=MagicMock()),
            patch.object(
                RagasEvaluator, "_create_embeddings", return_value=MagicMock()
            ),
            patch.object(RagasEvaluator, "_create_metrics", return_value=[MagicMock()]),
            patch.object(
                RagasEvaluator, "_build_ragas_dataset", return_value=MagicMock()
            ),
            patch.object(RagasEvaluator, "_build_run_config", return_value=MagicMock()),
            patch("ragas.evaluate", return_value=mock_result),
        ):
            results = evaluator.evaluate_batch(
                samples=samples,
                llm_config={
                    "api_key": "test",
                    "base_url": "http://test",
                    "model_name": "test-model",
                },
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

        errors = evaluator.validate_metrics(generation_metrics=["nonexistent_metric"])
        assert len(errors) > 0


class TestEvaluatorIntegration:
    """Integration tests for evaluators."""

    def test_builtin_evaluator_batch(self):
        """Test batch evaluation with builtin evaluator."""
        evaluator = BuiltinEvaluator()

        samples = [
            EvaluationSample(
                question_id="test_001",
                question="What is Python?",
                answer="Python is a programming language.",
                contexts=["doc1.pdf", "doc2.pdf"],
                expected_sources=["doc1.pdf"],
            ),
            EvaluationSample(
                question_id="test_002",
                question="What is Java?",
                answer="Java is a programming language.",
                contexts=["doc3.pdf", "doc4.pdf"],
                expected_sources=["doc3.pdf", "doc5.pdf"],
            ),
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
