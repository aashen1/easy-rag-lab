"""
Builtin evaluator that wraps the existing metrics implementation.

This evaluator provides a unified interface for the project's
existing evaluation metrics (hit_rate, mrr, ndcg, faithfulness, answer_relevancy).
"""

from typing import Any, Dict, List, Optional

from loguru import logger

from eval.evaluators.base import BaseEvaluator, EvaluationResult
from eval.metrics import (
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
    calculate_chunk_hit_rate,
    calculate_chunk_mrr,
    calculate_chunk_ndcg,
    calculate_dedup_hit_rate,
    calculate_dedup_mrr,
    calculate_dedup_ndcg,
    calculate_false_positive_rate,
    calculate_faithfulness,
    calculate_answer_relevancy,
    calculate_context_precision,
    calculate_context_recall,
    normalize_source_with_equivalence,
    deduplicate_by_document,
)


class BuiltinEvaluator(BaseEvaluator):
    """
    Evaluator that wraps the existing builtin metrics.

    This evaluator provides access to the project's existing evaluation
    metrics without modifying the original implementation.

    Args:
        config: Optional configuration dictionary.

    Returns:
        BuiltinEvaluator instance.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None):
        """
        Initialize the builtin evaluator.

        Args:
            config: Optional configuration dictionary.
        """
        super().__init__(config)
        self._retrieval_metrics = [
            "hit_rate", "mrr", "ndcg",
            "chunk_hit_rate", "chunk_mrr", "chunk_ndcg",
            "dedup_hit_rate", "dedup_mrr", "dedup_ndcg",
            "false_positive_rate",
            "context_precision", "context_recall",
        ]
        self._generation_metrics = ["faithfulness", "answer_relevancy"]

    @property
    def name(self) -> str:
        """
        Get the evaluator name.

        Returns:
            Evaluator name string.
        """
        return "builtin"

    @property
    def supported_retrieval_metrics(self) -> List[str]:
        """
        Get list of supported retrieval metrics.

        Returns:
            List of retrieval metric names.
        """
        return self._retrieval_metrics

    @property
    def supported_generation_metrics(self) -> List[str]:
        """
        Get list of supported generation metrics.

        Returns:
            List of generation metric names.
        """
        return self._generation_metrics

    def evaluate_single(
        self,
        question_id: str,
        question: str,
        answer: str,
        contexts: List[str],
        expected_sources: Optional[List[str]] = None,
        expected_answer: Optional[str] = None,
        llm_config: Optional[Dict[str, str]] = None,
        retrieval_metrics: Optional[List[str]] = None,
        generation_metrics: Optional[List[str]] = None,
        chunk_ids: Optional[List[str]] = None,
        expected_chunks: Optional[List[str]] = None,
        equivalence_groups: Optional[Dict[str, List[str]]] = None,
        expect_retrieval: bool = True,
    ) -> EvaluationResult:
        """
        Evaluate a single sample using builtin metrics.

        Args:
            question_id: Unique identifier for the question.
            question: The question text.
            answer: The generated answer.
            contexts: List of retrieved context strings.
            expected_sources: Optional list of expected source documents.
            expected_answer: Optional expected answer for reference.
            llm_config: Optional LLM configuration for generation metrics.
                Must contain api_key, base_url, and model_name keys.
            retrieval_metrics: Optional list of retrieval metrics to compute.
                Defaults to all supported retrieval metrics.
            generation_metrics: Optional list of generation metrics to compute.
                Defaults to all supported generation metrics if llm_config is provided.
            chunk_ids: Optional list of retrieved chunk identifiers.
            expected_chunks: Optional list of expected chunk identifiers.
            equivalence_groups: Optional dict mapping group keys to lists of
                equivalent file paths for dedup normalization.
            expect_retrieval: Whether the question expects retrieval results.
                Defaults to True. Set to False for irrelevant questions.

        Returns:
            EvaluationResult containing the evaluation scores.
        """
        if retrieval_metrics is None:
            retrieval_metrics = self._retrieval_metrics

        if generation_metrics is None and llm_config:
            generation_metrics = self._generation_metrics

        retrieval_results = {}
        generation_results = {}
        error = None

        try:
            if expected_sources and expect_retrieval:
                if "hit_rate" in retrieval_metrics:
                    retrieval_results["hit_rate"] = calculate_hit_rate(
                        retrieved_sources=contexts,
                        expected_sources=expected_sources,
                    )
                if "mrr" in retrieval_metrics:
                    retrieval_results["mrr"] = calculate_mrr(
                        retrieved_sources=contexts,
                        expected_sources=expected_sources,
                    )
                if "ndcg" in retrieval_metrics:
                    retrieval_results["ndcg"] = calculate_ndcg(
                        retrieved_sources=contexts,
                        expected_sources=expected_sources,
                    )

            if chunk_ids and expected_chunks and expect_retrieval:
                if "chunk_hit_rate" in retrieval_metrics:
                    retrieval_results["chunk_hit_rate"] = calculate_chunk_hit_rate(
                        chunk_ids, expected_chunks
                    )
                if "chunk_mrr" in retrieval_metrics:
                    retrieval_results["chunk_mrr"] = calculate_chunk_mrr(
                        chunk_ids, expected_chunks
                    )
                if "chunk_ndcg" in retrieval_metrics:
                    retrieval_results["chunk_ndcg"] = calculate_chunk_ndcg(
                        chunk_ids, expected_chunks, k=5
                    )

            if expected_sources and expect_retrieval:
                if equivalence_groups:
                    norm_retrieved = [normalize_source_with_equivalence(s, equivalence_groups) for s in contexts]
                    norm_expected = [normalize_source_with_equivalence(s, equivalence_groups) for s in expected_sources]
                else:
                    norm_retrieved = contexts
                    norm_expected = expected_sources

                if "dedup_hit_rate" in retrieval_metrics:
                    retrieval_results["dedup_hit_rate"] = calculate_dedup_hit_rate(
                        norm_retrieved, norm_expected
                    )
                if "dedup_mrr" in retrieval_metrics:
                    retrieval_results["dedup_mrr"] = calculate_dedup_mrr(
                        norm_retrieved, norm_expected
                    )
                if "dedup_ndcg" in retrieval_metrics:
                    retrieval_results["dedup_ndcg"] = calculate_dedup_ndcg(
                        norm_retrieved, norm_expected
                    )

            if not expect_retrieval and not expected_sources:
                if "false_positive_rate" in retrieval_metrics:
                    retrieval_results["false_positive_rate"] = calculate_false_positive_rate(
                        contexts, k=5
                    )

            if llm_config and contexts:
                if "context_precision" in retrieval_metrics:
                    try:
                        cp_score = calculate_context_precision(
                            question=question,
                            expected_output=expected_answer or "",
                            retrieval_context=contexts,
                            api_key=llm_config["api_key"],
                            base_url=llm_config["base_url"],
                            model_name=llm_config["model_name"],
                        )
                        retrieval_results["context_precision"] = cp_score
                    except Exception as e:
                        logger.error(f"Failed to calculate context_precision for {question_id}: {str(e)}")
                        retrieval_results["context_precision"] = None

                if "context_recall" in retrieval_metrics:
                    try:
                        cr_score = calculate_context_recall(
                            question=question,
                            ground_truth=expected_answer or "",
                            retrieval_context=contexts,
                            api_key=llm_config["api_key"],
                            base_url=llm_config["base_url"],
                            model_name=llm_config["model_name"],
                        )
                        retrieval_results["context_recall"] = cr_score
                    except Exception as e:
                        logger.error(f"Failed to calculate context_recall for {question_id}: {str(e)}")
                        retrieval_results["context_recall"] = None

            if generation_metrics and llm_config:
                if "faithfulness" in generation_metrics:
                    try:
                        faithfulness_score = calculate_faithfulness(
                            answer=answer,
                            contexts=contexts,
                            api_key=llm_config["api_key"],
                            base_url=llm_config["base_url"],
                            model_name=llm_config["model_name"],
                        )
                        generation_results["faithfulness"] = faithfulness_score
                    except Exception as e:
                        logger.error(
                            f"Failed to calculate faithfulness for {question_id}: {str(e)}"
                        )
                        generation_results["faithfulness"] = None

                if "answer_relevancy" in generation_metrics:
                    try:
                        relevancy_score = calculate_answer_relevancy(
                            question=question,
                            answer=answer,
                            api_key=llm_config["api_key"],
                            base_url=llm_config["base_url"],
                            model_name=llm_config["model_name"],
                        )
                        generation_results["answer_relevancy"] = relevancy_score
                    except Exception as e:
                        logger.error(
                            f"Failed to calculate answer_relevancy for {question_id}: {str(e)}"
                        )
                        generation_results["answer_relevancy"] = None

        except Exception as e:
            error = str(e)
            logger.error(f"Evaluation failed for {question_id}: {error}")

        return EvaluationResult(
            question_id=question_id,
            question=question,
            answer=answer,
            contexts=contexts,
            retrieval_metrics=retrieval_results,
            generation_metrics=generation_results,
            error=error,
        )

    def evaluate_batch(
        self,
        samples: List[Dict[str, Any]],
        llm_config: Optional[Dict[str, str]] = None,
        retrieval_metrics: Optional[List[str]] = None,
        generation_metrics: Optional[List[str]] = None,
    ) -> List[EvaluationResult]:
        """
        Evaluate a batch of samples using builtin metrics.

        This implementation processes samples sequentially. For better
        performance with LLM-based metrics, consider using the RAGAS
        evaluator which supports batch processing.

        Args:
            samples: List of sample dictionaries.
            llm_config: Optional LLM configuration for generation metrics.
            retrieval_metrics: Optional list of retrieval metrics to compute.
            generation_metrics: Optional list of generation metrics to compute.

        Returns:
            List of EvaluationResult objects.
        """
        results = []
        for i, sample in enumerate(samples):
            logger.info(
                f"Evaluating sample {i+1}/{len(samples)}: {sample.get('question_id', 'unknown')}"
            )
            result = self.evaluate_single(
                question_id=sample.get("question_id", ""),
                question=sample.get("question", ""),
                answer=sample.get("answer", ""),
                contexts=sample.get("contexts", []),
                expected_sources=sample.get("expected_sources"),
                expected_answer=sample.get("expected_answer"),
                llm_config=llm_config,
                retrieval_metrics=retrieval_metrics,
                generation_metrics=generation_metrics,
                chunk_ids=sample.get("chunk_ids"),
                expected_chunks=sample.get("expected_chunks"),
                equivalence_groups=sample.get("equivalence_groups"),
                expect_retrieval=sample.get("expect_retrieval", True),
            )
            results.append(result)
        return results
