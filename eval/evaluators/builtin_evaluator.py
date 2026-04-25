"""
Builtin evaluator that wraps the existing metrics implementation.

This evaluator provides a unified interface for the project's
existing evaluation metrics (hit_rate, mrr, ndcg, faithfulness, answer_relevancy).
"""

from typing import Any

from loguru import logger

from eval.evaluators.base import BaseEvaluator, EvaluationResult
from eval.metrics import (
    calculate_answer_relevancy,
    calculate_chunk_hit_rate,
    calculate_chunk_mrr,
    calculate_chunk_ndcg,
    calculate_context_precision,
    calculate_context_recall,
    calculate_dedup_hit_rate,
    calculate_dedup_mrr,
    calculate_dedup_ndcg,
    calculate_faithfulness,
    calculate_false_positive_rate,
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
    calculate_retrieval_diversity,
    normalize_source,
    normalize_source_with_equivalence,
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

    def __init__(self, config: dict[str, Any] | None = None):
        """
        Initialize the builtin evaluator.

        Args:
            config: Optional configuration dictionary.
        """
        super().__init__(config)
        self._retrieval_metrics = [
            "hit_rate",
            "mrr",
            "ndcg",
            "chunk_hit_rate",
            "chunk_mrr",
            "chunk_ndcg",
            "dedup_hit_rate",
            "dedup_mrr",
            "dedup_ndcg",
            "false_positive_rate",
            "retrieval_diversity",
            "context_precision",
            "context_recall",
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
    def supported_retrieval_metrics(self) -> list[str]:
        """
        Get list of supported retrieval metrics.

        Returns:
            List of retrieval metric names.
        """
        return self._retrieval_metrics

    @property
    def supported_generation_metrics(self) -> list[str]:
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
        contexts: list[str],
        expected_sources: list[str] | None = None,
        expected_answer: str | None = None,
        llm_config: dict[str, str] | None = None,
        retrieval_metrics: list[str] | None = None,
        generation_metrics: list[str] | None = None,
        chunk_ids: list[str] | None = None,
        expected_chunks: list[str] | None = None,
        equivalence_groups: dict[str, list[str]] | None = None,
        expect_retrieval: bool = True,
        expect_no_answer: bool = False,
        retrieved_sources: list[str] | None = None,
        question_type: str | None = None,
    ) -> EvaluationResult:
        """
        Evaluate a single sample using builtin metrics.

        Args:
            question_id: Unique identifier for the question.
            question: The question text.
            answer: The generated answer.
            contexts: List of retrieved context strings (text content).
                Used for generation metrics (faithfulness, context_precision,
                context_recall). When retrieved_sources is not provided, also
                used as fallback for retrieval metrics.
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
            expect_no_answer: Whether the answer is not expected to be found
                in the documents. Defaults to False. Set to True for missing
                knowledge questions. When True, faithfulness is skipped.
            retrieved_sources: Optional list of retrieved source file paths.
                Used for retrieval metrics (hit_rate, mrr, ndcg, dedup, FPR).
                When not provided, falls back to contexts for backward
                compatibility.
            question_type: Optional question type string (e.g., 'factual',
                'irrelevant'). Used for logging and result metadata.

        Returns:
            EvaluationResult containing the evaluation scores.
        """
        if retrieval_metrics is None:
            retrieval_metrics = self._retrieval_metrics

        if generation_metrics is None and llm_config:
            generation_metrics = self._generation_metrics

        sources_for_retrieval = (
            retrieved_sources if retrieved_sources is not None else contexts
        )

        retrieval_results = {}
        generation_results = {}
        error = None

        try:
            if expected_sources and expect_retrieval:
                if "hit_rate" in retrieval_metrics:
                    retrieval_results["hit_rate"] = calculate_hit_rate(
                        retrieved_sources=sources_for_retrieval,
                        expected_sources=expected_sources,
                    )
                if "mrr" in retrieval_metrics:
                    retrieval_results["mrr"] = calculate_mrr(
                        retrieved_sources=sources_for_retrieval,
                        expected_sources=expected_sources,
                    )
                if "ndcg" in retrieval_metrics:
                    retrieval_results["ndcg"] = calculate_ndcg(
                        retrieved_sources=sources_for_retrieval,
                        expected_sources=expected_sources,
                    )
                for _k in (3, 5, 10):
                    _key = f"recall_{_k}"
                    if _key in retrieval_metrics:
                        retrieval_results[_key] = calculate_hit_rate(
                            retrieved_sources=sources_for_retrieval,
                            expected_sources=expected_sources,
                            k=_k,
                            mode="recall",
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
                    norm_retrieved = [
                        normalize_source_with_equivalence(
                            s, equivalence_groups, include_parent=True
                        )
                        for s in sources_for_retrieval
                    ]
                    norm_expected = [
                        normalize_source_with_equivalence(
                            s, equivalence_groups, include_parent=True
                        )
                        for s in expected_sources
                    ]
                else:
                    norm_retrieved = [
                        normalize_source(s, include_parent=True)
                        for s in sources_for_retrieval
                    ]
                    norm_expected = [
                        normalize_source(s, include_parent=True)
                        for s in expected_sources
                    ]

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

            if not expect_retrieval and "false_positive_rate" in retrieval_metrics:
                retrieval_results["false_positive_rate"] = (
                    calculate_false_positive_rate(sources_for_retrieval, k=5)
                )

            if "retrieval_diversity" in retrieval_metrics and sources_for_retrieval:
                retrieval_results["retrieval_diversity"] = (
                    calculate_retrieval_diversity(sources_for_retrieval, k=5)
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
                        logger.error(
                            f"Failed to calculate context_precision for {question_id}: {str(e)}"
                        )
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
                        logger.error(
                            f"Failed to calculate context_recall for {question_id}: {str(e)}"
                        )
                        retrieval_results["context_recall"] = None

            if generation_metrics and llm_config:
                if "faithfulness" in generation_metrics:
                    if expect_no_answer:
                        generation_results["faithfulness"] = None
                    else:
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
        samples: list[dict[str, Any]],
        llm_config: dict[str, str] | None = None,
        retrieval_metrics: list[str] | None = None,
        generation_metrics: list[str] | None = None,
    ) -> list[EvaluationResult]:
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
                f"Evaluating sample {i + 1}/{len(samples)}: {sample.get('question_id', 'unknown')}"
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
                expect_no_answer=sample.get("expect_no_answer", False),
                retrieved_sources=sample.get("retrieved_sources"),
                question_type=sample.get("question_type"),
            )
            results.append(result)
        return results
