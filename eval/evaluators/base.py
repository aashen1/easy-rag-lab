"""
Evaluator abstract base classes for RAG evaluation.

This module provides the abstract base class for all evaluators,
supporting multiple evaluation backends (builtin, RAGAS, etc.).
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


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
    contexts: List[str] = field(default_factory=list)
    retrieval_metrics: Dict[str, float] = field(default_factory=dict)
    generation_metrics: Dict[str, float] = field(default_factory=dict)
    error: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
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

    def __init__(self, config: Optional[Dict[str, Any]] = None):
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
    def supported_retrieval_metrics(self) -> List[str]:
        """
        Get list of supported retrieval metrics.

        Returns:
            List of retrieval metric names.
        """
        pass

    @property
    @abstractmethod
    def supported_generation_metrics(self) -> List[str]:
        """
        Get list of supported generation metrics.

        Returns:
            List of generation metric names.
        """
        pass

    @abstractmethod
    def evaluate_single(
        self,
        question_id: str,
        question: str,
        answer: str,
        contexts: List[str],
        expected_sources: Optional[List[str]] = None,
        expected_answer: Optional[str] = None,
        llm_config: Optional[Dict[str, str]] = None,
    ) -> EvaluationResult:
        """
        Evaluate a single sample.

        Args:
            question_id: Unique identifier for the question.
            question: The question text.
            answer: The generated answer.
            contexts: List of retrieved context strings.
            expected_sources: Optional list of expected source documents.
            expected_answer: Optional expected answer for reference.
            llm_config: Optional LLM configuration for generation metrics.

        Returns:
            EvaluationResult containing the evaluation scores.
        """
        pass

    def evaluate_batch(
        self,
        samples: List[Dict[str, Any]],
        llm_config: Optional[Dict[str, str]] = None,
        retrieval_metrics: Optional[List[str]] = None,
        generation_metrics: Optional[List[str]] = None,
    ) -> List[EvaluationResult]:
        """
        Evaluate a batch of samples.

        Args:
            samples: List of sample dictionaries, each containing:
                - question_id: Unique identifier
                - question: Question text
                - answer: Generated answer
                - contexts: Retrieved contexts
                - expected_sources: Optional expected sources
                - expected_answer: Optional expected answer
            llm_config: Optional LLM configuration for generation metrics.
            retrieval_metrics: Optional list of retrieval metrics to compute.
            generation_metrics: Optional list of generation metrics to compute.

        Returns:
            List of EvaluationResult objects.
        """
        results = []
        for sample in samples:
            result = self.evaluate_single(
                question_id=sample.get("question_id", ""),
                question=sample.get("question", ""),
                answer=sample.get("answer", ""),
                contexts=sample.get("contexts", []),
                expected_sources=sample.get("expected_sources"),
                expected_answer=sample.get("expected_answer"),
                llm_config=llm_config,
            )
            results.append(result)
        return results

    def validate_metrics(
        self,
        retrieval_metrics: Optional[List[str]] = None,
        generation_metrics: Optional[List[str]] = None,
    ) -> List[str]:
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
                m for m in retrieval_metrics
                if m not in self.supported_retrieval_metrics
            ]
            if unsupported:
                errors.append(
                    f"Unsupported retrieval metrics: {unsupported}. "
                    f"Supported: {sorted(self.supported_retrieval_metrics)}"
                )

        if generation_metrics:
            unsupported = [
                m for m in generation_metrics
                if m not in self.supported_generation_metrics
            ]
            if unsupported:
                errors.append(
                    f"Unsupported generation metrics: {unsupported}. "
                    f"Supported: {sorted(self.supported_generation_metrics)}"
                )

        return errors
