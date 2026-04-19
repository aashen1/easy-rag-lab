"""
Evaluator module for RAG evaluation.

This module provides a unified interface for multiple evaluation backends,
including the builtin evaluator and RAGAS evaluator.
"""

from eval.evaluators.base import BaseEvaluator, EvaluationResult
from eval.evaluators.builtin_evaluator import BuiltinEvaluator
from eval.evaluators.ragas_evaluator import RagasEvaluator

__all__ = [
    "BaseEvaluator",
    "EvaluationResult",
    "BuiltinEvaluator",
    "RagasEvaluator",
]
