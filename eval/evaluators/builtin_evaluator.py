"""
Builtin evaluator that wraps the existing metrics implementation.

This evaluator provides a unified interface for the project's
existing evaluation metrics (hit_rate, mrr, ndcg, faithfulness, answer_relevancy).
"""

from dataclasses import dataclass
from typing import Any

from loguru import logger

from eval.evaluators.base import BaseEvaluator, EvaluationResult, EvaluationSample
from eval.evaluators.error_handler import execute_metric_safely
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


@dataclass
class _SampleData:
    question_id: str
    question: str
    answer: str
    contexts: list[str]
    expected_sources: list[str] | None
    expected_answer: str | None
    llm_config: dict[str, str] | None
    retrieval_metrics: list[str]
    generation_metrics: list[str] | None
    chunk_ids: list[str] | None
    expected_chunks: list[str] | None
    equivalence_groups: dict[str, list[str]] | None
    expect_retrieval: bool
    expect_no_answer: bool
    sources_for_retrieval: list[str]


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
            "recall_3",
            "recall_5",
            "recall_10",
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

    def _compute_basic_retrieval_metrics(
        self,
        retrieval_metrics: list[str],
        sources_for_retrieval: list[str],
        expected_sources: list[str],
    ) -> dict[str, float]:
        """Compute basic retrieval metrics (hit_rate, mrr, ndcg, recall)."""
        results = {}
        if "hit_rate" in retrieval_metrics:
            results["hit_rate"] = calculate_hit_rate(
                retrieved_sources=sources_for_retrieval,
                expected_sources=expected_sources,
            )
        if "mrr" in retrieval_metrics:
            results["mrr"] = calculate_mrr(
                retrieved_sources=sources_for_retrieval,
                expected_sources=expected_sources,
            )
        if "ndcg" in retrieval_metrics:
            results["ndcg"] = calculate_ndcg(
                retrieved_sources=sources_for_retrieval,
                expected_sources=expected_sources,
            )
        for _k in (3, 5, 10):
            _key = f"recall_{_k}"
            if _key in retrieval_metrics:
                results[_key] = calculate_hit_rate(
                    retrieved_sources=sources_for_retrieval,
                    expected_sources=expected_sources,
                    k=_k,
                    mode="recall",
                )
        return results

    def _compute_chunk_metrics(
        self,
        retrieval_metrics: list[str],
        chunk_ids: list[str],
        expected_chunks: list[str],
    ) -> dict[str, float]:
        """Compute chunk-level retrieval metrics."""
        results = {}
        if "chunk_hit_rate" in retrieval_metrics:
            results["chunk_hit_rate"] = calculate_chunk_hit_rate(
                chunk_ids, expected_chunks
            )
        if "chunk_mrr" in retrieval_metrics:
            results["chunk_mrr"] = calculate_chunk_mrr(chunk_ids, expected_chunks)
        if "chunk_ndcg" in retrieval_metrics:
            results["chunk_ndcg"] = calculate_chunk_ndcg(
                chunk_ids, expected_chunks, k=5
            )
        return results

    def _compute_dedup_metrics(
        self,
        retrieval_metrics: list[str],
        sources_for_retrieval: list[str],
        expected_sources: list[str],
        equivalence_groups: dict[str, list[str]] | None,
    ) -> dict[str, float]:
        """Compute deduplicated retrieval metrics."""
        results = {}
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
                normalize_source(s, include_parent=True) for s in sources_for_retrieval
            ]
            norm_expected = [
                normalize_source(s, include_parent=True) for s in expected_sources
            ]

        if "dedup_hit_rate" in retrieval_metrics:
            results["dedup_hit_rate"] = calculate_dedup_hit_rate(
                norm_retrieved, norm_expected
            )
        if "dedup_mrr" in retrieval_metrics:
            results["dedup_mrr"] = calculate_dedup_mrr(norm_retrieved, norm_expected)
        if "dedup_ndcg" in retrieval_metrics:
            results["dedup_ndcg"] = calculate_dedup_ndcg(norm_retrieved, norm_expected)
        return results

    def _compute_llm_retrieval_metrics(
        self,
        retrieval_metrics: list[str],
        question_id: str,
        question: str,
        expected_answer: str,
        contexts: list[str],
        llm_config: dict[str, str],
        retrieval_results: dict[str, Any],
    ) -> None:
        """Compute LLM-based retrieval metrics (context_precision, context_recall)."""
        if "context_precision" in retrieval_metrics:
            execute_metric_safely(
                "context_precision",
                calculate_context_precision,
                retrieval_results,
                question_id,
                question=question,
                expected_output=expected_answer,
                retrieval_context=contexts,
                api_key=llm_config["api_key"],
                base_url=llm_config["base_url"],
                model_name=llm_config["model_name"],
            )

        if "context_recall" in retrieval_metrics:
            execute_metric_safely(
                "context_recall",
                calculate_context_recall,
                retrieval_results,
                question_id,
                question=question,
                ground_truth=expected_answer,
                retrieval_context=contexts,
                api_key=llm_config["api_key"],
                base_url=llm_config["base_url"],
                model_name=llm_config["model_name"],
            )

    def _compute_generation_metrics(
        self,
        generation_metrics: list[str],
        question_id: str,
        question: str,
        answer: str,
        contexts: list[str],
        llm_config: dict[str, str],
        expect_no_answer: bool,
    ) -> dict[str, Any]:
        """Compute generation metrics (faithfulness, answer_relevancy)."""
        results = {}
        if "faithfulness" in generation_metrics:
            if expect_no_answer:
                results["faithfulness"] = None
            else:
                execute_metric_safely(
                    "faithfulness",
                    calculate_faithfulness,
                    results,
                    question_id,
                    answer=answer,
                    contexts=contexts,
                    api_key=llm_config["api_key"],
                    base_url=llm_config["base_url"],
                    model_name=llm_config["model_name"],
                )

        if "answer_relevancy" in generation_metrics:
            execute_metric_safely(
                "answer_relevancy",
                calculate_answer_relevancy,
                results,
                question_id,
                question=question,
                answer=answer,
                api_key=llm_config["api_key"],
                base_url=llm_config["base_url"],
                model_name=llm_config["model_name"],
            )
        return results

    def _extract_sample_data(self, sample: EvaluationSample) -> _SampleData:
        retrieval_metrics = (
            sample.retrieval_metrics
            if sample.retrieval_metrics is not None
            else self._retrieval_metrics
        )
        generation_metrics = (
            sample.generation_metrics
            if sample.generation_metrics is not None and sample.llm_config
            else (self._generation_metrics if sample.llm_config else None)
        )
        sources_for_retrieval = (
            sample.retrieved_sources
            if sample.retrieved_sources is not None
            else sample.contexts
        )
        return _SampleData(
            question_id=sample.question_id,
            question=sample.question,
            answer=sample.answer,
            contexts=sample.contexts,
            expected_sources=sample.expected_sources,
            expected_answer=sample.expected_answer,
            llm_config=sample.llm_config,
            retrieval_metrics=retrieval_metrics,
            generation_metrics=generation_metrics,
            chunk_ids=sample.chunk_ids,
            expected_chunks=sample.expected_chunks,
            equivalence_groups=sample.equivalence_groups,
            expect_retrieval=sample.expect_retrieval,
            expect_no_answer=sample.expect_no_answer,
            sources_for_retrieval=sources_for_retrieval,
        )

    def evaluate_single(self, sample: EvaluationSample) -> EvaluationResult:
        """
        Evaluate a single sample using builtin metrics.

        Args:
            sample: EvaluationSample containing all data needed for evaluation.

        Returns:
            EvaluationResult containing the evaluation scores.
        """
        data = self._extract_sample_data(sample)
        retrieval_results: dict[str, Any] = {}
        generation_results: dict[str, Any] = {}
        error: str | None = None

        try:
            retrieval_results = self._compute_all_retrieval_metrics(data)
            generation_results = self._compute_all_generation_metrics(data)
        except Exception as e:
            error = str(e)
            logger.error(f"Evaluation failed for {data.question_id}: {error}")

        return EvaluationResult(
            question_id=data.question_id,
            question=data.question,
            answer=data.answer,
            contexts=data.contexts,
            retrieval_metrics=retrieval_results,
            generation_metrics=generation_results,
            error=error,
        )

    def _compute_all_retrieval_metrics(self, data: _SampleData) -> dict[str, Any]:
        results: dict[str, Any] = {}

        if data.expected_sources and data.expect_retrieval:
            results.update(
                self._compute_basic_retrieval_metrics(
                    data.retrieval_metrics,
                    data.sources_for_retrieval,
                    data.expected_sources,
                )
            )

        if data.chunk_ids and data.expected_chunks and data.expect_retrieval:
            results.update(
                self._compute_chunk_metrics(
                    data.retrieval_metrics, data.chunk_ids, data.expected_chunks
                )
            )

        if data.expected_sources and data.expect_retrieval:
            results.update(
                self._compute_dedup_metrics(
                    data.retrieval_metrics,
                    data.sources_for_retrieval,
                    data.expected_sources,
                    data.equivalence_groups,
                )
            )

        if (
            not data.expect_retrieval
            and "false_positive_rate" in data.retrieval_metrics
        ):
            results["false_positive_rate"] = calculate_false_positive_rate(
                data.sources_for_retrieval, k=5
            )

        if (
            "retrieval_diversity" in data.retrieval_metrics
            and data.sources_for_retrieval
        ):
            results["retrieval_diversity"] = calculate_retrieval_diversity(
                data.sources_for_retrieval, k=5
            )

        if (
            data.llm_config
            and data.contexts
            and data.expect_retrieval
            and data.expected_answer
        ):
            self._compute_llm_retrieval_metrics(
                data.retrieval_metrics,
                data.question_id,
                data.question,
                data.expected_answer,
                data.contexts,
                data.llm_config,
                results,
            )

        return results

    def _compute_all_generation_metrics(self, data: _SampleData) -> dict[str, Any]:
        if not data.generation_metrics or not data.llm_config:
            return {}
        return self._compute_generation_metrics(
            data.generation_metrics,
            data.question_id,
            data.question,
            data.answer,
            data.contexts,
            data.llm_config,
            data.expect_no_answer,
        )

    def evaluate_batch(
        self,
        samples: list[EvaluationSample],
        llm_config: dict[str, str] | None = None,
        retrieval_metrics: list[str] | None = None,
        generation_metrics: list[str] | None = None,
    ) -> list[EvaluationResult]:
        """
        Evaluate a batch of samples using builtin metrics.

        Retrieval metrics are computed sequentially (pure computation, fast).
        Generation metrics that require LLM calls are computed concurrently
        using a thread pool for improved throughput.

        Args:
            samples: List of EvaluationSample objects.
            llm_config: Optional LLM configuration for generation metrics.
            retrieval_metrics: Optional list of retrieval metrics to compute.
            generation_metrics: Optional list of generation metrics to compute.

        Returns:
            List of EvaluationResult objects.
        """
        has_gen_metrics = bool(generation_metrics) and bool(llm_config)
        if not has_gen_metrics:
            results = []
            for i, sample in enumerate(samples):
                logger.info(
                    f"Evaluating sample {i + 1}/{len(samples)}: {sample.question_id}"
                )
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

        from concurrent.futures import ThreadPoolExecutor, as_completed

        max_workers = self.config.get("evaluation", {}).get(
            "builtin_concurrent_workers", 3
        )

        merged_samples = []
        for sample in samples:
            merged = (
                sample.to_builder()
                .llm_config(llm_config or sample.llm_config)
                .retrieval_metrics(retrieval_metrics or sample.retrieval_metrics)
                .generation_metrics(generation_metrics or sample.generation_metrics)
                .build()
            )
            merged_samples.append(merged)

        logger.info(
            f"Concurrent evaluation: {len(merged_samples)} samples, "
            f"{max_workers} workers"
        )

        results_dict: dict[int, EvaluationResult] = {}
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            future_to_idx = {}
            for i, sample in enumerate(merged_samples):
                future = executor.submit(self.evaluate_single, sample)
                future_to_idx[future] = i

            for future in as_completed(future_to_idx):
                idx = future_to_idx[future]
                try:
                    results_dict[idx] = future.result()
                except Exception as e:
                    sample = merged_samples[idx]
                    logger.error(
                        f"Concurrent evaluation failed for {sample.question_id}: {str(e)}"
                    )
                    results_dict[idx] = EvaluationResult(
                        question_id=sample.question_id,
                        question=sample.question,
                        answer=sample.answer,
                        contexts=sample.contexts,
                        retrieval_metrics={},
                        generation_metrics={},
                        error=str(e),
                    )

        return [results_dict[i] for i in range(len(merged_samples))]
