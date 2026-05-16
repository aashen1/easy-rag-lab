"""
Evaluator abstract base classes for RAG evaluation.

This module provides the abstract base class for all evaluators,
supporting multiple evaluation backends (builtin, RAGAS, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class EvaluationSample:
    """
    Unified input for evaluator methods.

    Encapsulates all data needed for a single evaluation, replacing
    the long parameter lists that violated Liskov Substitution Principle.

    Args:
        question_id: Unique identifier for the question.
        question: The question text.
        answer: The generated answer.
        contexts: List of retrieved context strings (text content).
        expected_sources: Optional list of expected source documents.
        expected_answer: Optional expected answer for reference.
        llm_config: Optional LLM configuration for generation metrics.
        retrieval_metrics: Optional list of retrieval metrics to compute.
        generation_metrics: Optional list of generation metrics to compute.
        chunk_ids: Optional list of retrieved chunk identifiers.
        expected_chunks: Optional list of expected chunk identifiers.
        equivalence_groups: Optional dict mapping group keys to lists of
            equivalent file paths for dedup normalization.
        expect_retrieval: Whether the question expects retrieval results.
        expect_no_answer: Whether the answer is not expected to be found.
        retrieved_sources: Optional list of retrieved source file paths.
        question_type: Optional question type string.

    Returns:
        EvaluationSample instance.
    """

    question_id: str = ""
    question: str = ""
    answer: str = ""
    contexts: list[str] = field(default_factory=list)
    expected_sources: list[str] | None = None
    expected_answer: str | None = None
    llm_config: dict[str, str] | None = None
    retrieval_metrics: list[str] | None = None
    generation_metrics: list[str] | None = None
    chunk_ids: list[str] | None = None
    expected_chunks: list[str] | None = None
    equivalence_groups: dict[str, list[str]] | None = None
    expect_retrieval: bool = True
    expect_no_answer: bool = False
    retrieved_sources: list[str] | None = None
    question_type: str | None = None

    def to_builder(self) -> "EvaluationSampleBuilder":
        """
        Convert current instance to a Builder for modification.

        Returns:
            EvaluationSampleBuilder initialized with current values.
        """
        return EvaluationSampleBuilder(self)

    @classmethod
    def builder(cls) -> "EvaluationSampleBuilder":
        """
        Create a new Builder instance.

        Returns:
            Empty EvaluationSampleBuilder instance.
        """
        return EvaluationSampleBuilder()


@dataclass
class EvaluationResult:
    """
    Unified evaluation result format.

    Args:
        question_id: Unique identifier for the question.
        question: The question text.
        answer: The generated answer.
        contexts: List of retrieved context strings.
        retrieval_metrics: Dictionary of retrieval metric scores.
        generation_metrics: Dictionary of generation metric scores.
        error: Optional error message if evaluation failed.

    Returns:
        EvaluationResult instance.
    """

    question_id: str
    question: str
    answer: str
    contexts: list[str] = field(default_factory=list)
    retrieval_metrics: dict[str, float] = field(default_factory=dict)
    generation_metrics: dict[str, float] = field(default_factory=dict)
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert EvaluationResult to dictionary.

        Returns:
            Dictionary representation of the result.
        """
        result = {
            "question_id": self.question_id,
            "question": self.question,
            "answer": self.answer,
            "contexts": self.contexts,
            "retrieval_metrics": self.retrieval_metrics,
            "generation_metrics": self.generation_metrics,
        }
        if self.error:
            result["error"] = self.error
        return result


class BaseEvaluator(ABC):
    """
    Abstract base class for evaluators.

    This class defines the interface for all evaluation backends,
    supporting both single-sample and batch evaluation modes.

    Args:
        config: Configuration dictionary for the evaluator.

    Returns:
        BaseEvaluator instance.
    """

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the evaluator.

        Args:
            config: Optional configuration dictionary.
        """
        self.config = config or {}

    @property
    @abstractmethod
    def name(self) -> str:
        """
        Get the evaluator name.

        Returns:
            Evaluator name string.
        """
        pass

    @property
    @abstractmethod
    def supported_retrieval_metrics(self) -> list[str]:
        """
        Get list of supported retrieval metrics.

        Returns:
            List of retrieval metric names.
        """
        pass

    @property
    @abstractmethod
    def supported_generation_metrics(self) -> list[str]:
        """
        Get list of supported generation metrics.

        Returns:
            List of generation metric names.
        """
        pass

    @abstractmethod
    def evaluate_single(self, sample: EvaluationSample) -> EvaluationResult:
        """
        Evaluate a single sample.

        Args:
            sample: EvaluationSample containing all data needed for evaluation.

        Returns:
            EvaluationResult containing the evaluation scores.
        """
        pass

    def evaluate_batch(
        self,
        samples: list[EvaluationSample],
        llm_config: dict[str, str] | None = None,
        retrieval_metrics: list[str] | None = None,
        generation_metrics: list[str] | None = None,
    ) -> list[EvaluationResult]:
        """
        Evaluate a batch of samples.

        The default implementation iterates over samples, merges batch-level
        configuration into each sample, and calls evaluate_single.

        Args:
            samples: List of EvaluationSample objects.
            llm_config: Optional LLM configuration (overrides per-sample config).
            retrieval_metrics: Optional list of retrieval metrics to compute
                (overrides per-sample config).
            generation_metrics: Optional list of generation metrics to compute
                (overrides per-sample config).

        Returns:
            List of EvaluationResult objects.
        """
        results = []
        for sample in samples:
            merged = (
                sample.to_builder()
                .llm_config(llm_config or sample.llm_config)
                .retrieval_metrics(retrieval_metrics or sample.retrieval_metrics)
                .generation_metrics(generation_metrics or sample.generation_metrics)
                .build()
            )
            result = self.evaluate_single(merged)
            results.append(result)
        return results

    def validate_metrics(
        self,
        retrieval_metrics: list[str] | None = None,
        generation_metrics: list[str] | None = None,
    ) -> list[str]:
        """
        Validate requested metrics against supported metrics.

        Args:
            retrieval_metrics: List of requested retrieval metrics.
            generation_metrics: List of requested generation metrics.

        Returns:
            List of validation error messages. Empty if all metrics are valid.
        """
        errors = []

        if retrieval_metrics:
            unsupported = [
                m
                for m in retrieval_metrics
                if m not in self.supported_retrieval_metrics
            ]
            if unsupported:
                errors.append(
                    f"Unsupported retrieval metrics: {unsupported}. "
                    f"Supported: {sorted(self.supported_retrieval_metrics)}"
                )

        if generation_metrics:
            unsupported = [
                m
                for m in generation_metrics
                if m not in self.supported_generation_metrics
            ]
            if unsupported:
                errors.append(
                    f"Unsupported generation metrics: {unsupported}. "
                    f"Supported: {sorted(self.supported_generation_metrics)}"
                )

        return errors


class EvaluationSampleBuilder:
    """
    Builder pattern for constructing EvaluationSample objects.

    Provides a fluent API for creating and modifying EvaluationSample
    instances, reducing code duplication and improving maintainability.

    Args:
        base: Optional EvaluationSample to initialize the builder with.

    Returns:
        EvaluationSampleBuilder instance.

    Example:
        >>> sample = (EvaluationSample.builder()
        ...     .question_id("q1")
        ...     .question("What is RAG?")
        ...     .answer("RAG is Retrieval-Augmented Generation")
        ...     .contexts(["context1", "context2"])
        ...     .build())
    """

    def __init__(self, base: EvaluationSample | None = None):
        """Initialize builder with optional base sample."""
        if base is not None:
            self._data = {
                "question_id": base.question_id,
                "question": base.question,
                "answer": base.answer,
                "contexts": base.contexts.copy() if base.contexts else [],
                "expected_sources": base.expected_sources,
                "expected_answer": base.expected_answer,
                "llm_config": base.llm_config,
                "retrieval_metrics": base.retrieval_metrics,
                "generation_metrics": base.generation_metrics,
                "chunk_ids": base.chunk_ids,
                "expected_chunks": base.expected_chunks,
                "equivalence_groups": base.equivalence_groups,
                "expect_retrieval": base.expect_retrieval,
                "expect_no_answer": base.expect_no_answer,
                "retrieved_sources": base.retrieved_sources,
                "question_type": base.question_type,
            }
        else:
            self._data: dict[str, Any] = {}

    def question_id(self, value: str) -> "EvaluationSampleBuilder":
        """Set question_id field."""
        self._data["question_id"] = value
        return self

    def question(self, value: str) -> "EvaluationSampleBuilder":
        """Set question field."""
        self._data["question"] = value
        return self

    def answer(self, value: str) -> "EvaluationSampleBuilder":
        """Set answer field."""
        self._data["answer"] = value
        return self

    def contexts(self, value: list[str]) -> "EvaluationSampleBuilder":
        """Set contexts field."""
        self._data["contexts"] = value
        return self

    def expected_sources(self, value: list[str] | None) -> "EvaluationSampleBuilder":
        """Set expected_sources field."""
        self._data["expected_sources"] = value
        return self

    def expected_answer(self, value: str | None) -> "EvaluationSampleBuilder":
        """Set expected_answer field."""
        self._data["expected_answer"] = value
        return self

    def llm_config(self, value: dict[str, str] | None) -> "EvaluationSampleBuilder":
        """Set llm_config field."""
        self._data["llm_config"] = value
        return self

    def retrieval_metrics(self, value: list[str] | None) -> "EvaluationSampleBuilder":
        """Set retrieval_metrics field."""
        self._data["retrieval_metrics"] = value
        return self

    def generation_metrics(self, value: list[str] | None) -> "EvaluationSampleBuilder":
        """Set generation_metrics field."""
        self._data["generation_metrics"] = value
        return self

    def chunk_ids(self, value: list[str] | None) -> "EvaluationSampleBuilder":
        """Set chunk_ids field."""
        self._data["chunk_ids"] = value
        return self

    def expected_chunks(self, value: list[str] | None) -> "EvaluationSampleBuilder":
        """Set expected_chunks field."""
        self._data["expected_chunks"] = value
        return self

    def equivalence_groups(
        self, value: dict[str, list[str]] | None
    ) -> "EvaluationSampleBuilder":
        """Set equivalence_groups field."""
        self._data["equivalence_groups"] = value
        return self

    def expect_retrieval(self, value: bool) -> "EvaluationSampleBuilder":
        """Set expect_retrieval field."""
        self._data["expect_retrieval"] = value
        return self

    def expect_no_answer(self, value: bool) -> "EvaluationSampleBuilder":
        """Set expect_no_answer field."""
        self._data["expect_no_answer"] = value
        return self

    def retrieved_sources(self, value: list[str] | None) -> "EvaluationSampleBuilder":
        """Set retrieved_sources field."""
        self._data["retrieved_sources"] = value
        return self

    def question_type(self, value: str | None) -> "EvaluationSampleBuilder":
        """Set question_type field."""
        self._data["question_type"] = value
        return self

    def build(self) -> EvaluationSample:
        """
        Build the final EvaluationSample object.

        Returns:
            EvaluationSample instance with all configured values.
        """
        return EvaluationSample(**self._data)
