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
            merged = EvaluationSample(
                question_id=sample.question_id,
                question=sample.question,
                answer=sample.answer,
                contexts=sample.contexts,
                expected_sources=sample.expected_sources,
                expected_answer=sample.expected_answer,
                llm_config=llm_config or sample.llm_config,
                retrieval_metrics=retrieval_metrics or sample.retrieval_metrics,
                generation_metrics=generation_metrics or sample.generation_metrics,
                chunk_ids=sample.chunk_ids,
                expected_chunks=sample.expected_chunks,
                equivalence_groups=sample.equivalence_groups,
                expect_retrieval=sample.expect_retrieval,
                expect_no_answer=sample.expect_no_answer,
                retrieved_sources=sample.retrieved_sources,
                question_type=sample.question_type,
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
