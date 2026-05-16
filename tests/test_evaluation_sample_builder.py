"""Tests for EvaluationSampleBuilder functionality."""

import pytest

from eval.evaluators.base import EvaluationSample


@pytest.mark.unit
class TestEvaluationSampleBuilder:
    """Tests for EvaluationSampleBuilder pattern."""

    def test_builder_creates_empty_sample(self):
        """Test that builder creates an empty sample by default."""
        sample = EvaluationSample.builder().build()
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

    def test_builder_sets_all_fields(self):
        """Test that builder can set all fields."""
        sample = (
            EvaluationSample.builder()
            .question_id("q1")
            .question("What is RAG?")
            .answer("RAG is Retrieval-Augmented Generation")
            .contexts(["context1", "context2"])
            .expected_sources(["doc1.pdf", "doc2.pdf"])
            .expected_answer("Expected answer")
            .llm_config({"model": "gpt-4"})
            .retrieval_metrics(["hit_rate", "mrr"])
            .generation_metrics(["faithfulness"])
            .chunk_ids(["chunk1", "chunk2"])
            .expected_chunks(["expected_chunk1"])
            .equivalence_groups({"group1": ["doc1.pdf", "doc1.md"]})
            .expect_retrieval(False)
            .expect_no_answer(True)
            .retrieved_sources(["retrieved1.pdf"])
            .question_type("factual")
            .build()
        )

        assert sample.question_id == "q1"
        assert sample.question == "What is RAG?"
        assert sample.answer == "RAG is Retrieval-Augmented Generation"
        assert sample.contexts == ["context1", "context2"]
        assert sample.expected_sources == ["doc1.pdf", "doc2.pdf"]
        assert sample.expected_answer == "Expected answer"
        assert sample.llm_config == {"model": "gpt-4"}
        assert sample.retrieval_metrics == ["hit_rate", "mrr"]
        assert sample.generation_metrics == ["faithfulness"]
        assert sample.chunk_ids == ["chunk1", "chunk2"]
        assert sample.expected_chunks == ["expected_chunk1"]
        assert sample.equivalence_groups == {"group1": ["doc1.pdf", "doc1.md"]}
        assert sample.expect_retrieval is False
        assert sample.expect_no_answer is True
        assert sample.retrieved_sources == ["retrieved1.pdf"]
        assert sample.question_type == "factual"

    def test_to_builder_from_sample(self):
        """Test converting an existing sample to a builder."""
        original = EvaluationSample(
            question_id="q1",
            question="Original question",
            answer="Original answer",
            contexts=["original_context"],
            expected_sources=["original_source.pdf"],
            llm_config={"model": "gpt-3.5"},
            retrieval_metrics=["hit_rate"],
        )

        modified = (
            original.to_builder()
            .question("Modified question")
            .llm_config({"model": "gpt-4"})
            .build()
        )

        assert modified.question_id == "q1"
        assert modified.question == "Modified question"
        assert modified.answer == "Original answer"
        assert modified.contexts == ["original_context"]
        assert modified.expected_sources == ["original_source.pdf"]
        assert modified.llm_config == {"model": "gpt-4"}
        assert modified.retrieval_metrics == ["hit_rate"]

    def test_builder_fluent_api(self):
        """Test that builder methods return self for chaining."""
        builder = EvaluationSample.builder()
        assert builder.question_id("q1") is builder
        assert builder.question("test") is builder
        assert builder.answer("answer") is builder

    def test_builder_with_none_values(self):
        """Test that builder handles None values correctly."""
        sample = (
            EvaluationSample.builder()
            .question_id("q1")
            .expected_sources(None)
            .llm_config(None)
            .build()
        )

        assert sample.question_id == "q1"
        assert sample.expected_sources is None
        assert sample.llm_config is None

    def test_builder_overwrites_values(self):
        """Test that builder overwrites previously set values."""
        sample = (
            EvaluationSample.builder()
            .question_id("q1")
            .question("First question")
            .question("Second question")
            .build()
        )

        assert sample.question_id == "q1"
        assert sample.question == "Second question"

    def test_to_builder_copies_contexts_list(self):
        """Test that to_builder creates a copy of contexts list."""
        original = EvaluationSample(
            question_id="q1",
            contexts=["context1", "context2"],
        )

        builder = original.to_builder()
        builder._data["contexts"].append("context3")

        # Original should not be modified
        assert original.contexts == ["context1", "context2"]
        # Builder should have the new context
        assert builder._data["contexts"] == ["context1", "context2", "context3"]

    def test_builder_integration_with_evaluator(self):
        """Test that builder creates samples compatible with evaluators."""
        from eval.evaluators.builtin_evaluator import BuiltinEvaluator

        sample = (
            EvaluationSample.builder()
            .question_id("q1")
            .question("What is RAG?")
            .answer("RAG is Retrieval-Augmented Generation")
            .contexts(["RAG combines retrieval and generation"])
            .expected_sources(["doc1.pdf"])
            .retrieval_metrics(["hit_rate"])
            .build()
        )

        evaluator = BuiltinEvaluator()
        result = evaluator.evaluate_single(sample)

        assert result.question_id == "q1"
        assert result.question == "What is RAG?"
        assert "hit_rate" in result.retrieval_metrics
