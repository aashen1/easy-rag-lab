"""Metric resolution system for multi-backend evaluation.

Provides intelligent metric-to-backend allocation based on user-configured
strategies (priority_fallback or comparison) and metric presets
(core/extended/full/custom).
"""

from __future__ import annotations

from loguru import logger

from eval.evaluators.base import BaseEvaluator

METRIC_PRESETS: dict[str, dict[str, list[str]]] = {
    "core": {
        "retrieval": [
            "hit_rate",
            "mrr",
            "ndcg",
            "recall_3",
            "recall_5",
            "recall_10",
        ],
        "generation": ["faithfulness", "answer_relevancy"],
    },
    "extended": {
        "retrieval": [
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
            "context_precision",
            "context_recall",
        ],
        "generation": ["faithfulness", "answer_relevancy"],
    },
    "full": {
        "retrieval": [
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
            "context_precision",
            "context_recall",
            "false_positive_rate",
            "retrieval_diversity",
        ],
        "generation": [
            "faithfulness",
            "answer_relevancy",
            "answer_correctness",
            "semantic_similarity",
        ],
    },
}


class MetricResolver:
    """Resolve metric-to-backend allocation based on strategy and priority.

    Supports two resolution strategies:
    - priority_fallback: Each metric is assigned to the highest-priority
      backend that supports it. Overlapping metrics are computed only once.
    - comparison: Every backend computes all metrics it supports. Results
      are prefixed with the backend name for cross-comparison.

    Args:
        evaluators: Mapping of backend name to BaseEvaluator instance.
        strategy: Resolution strategy ("priority_fallback" or "comparison").
        backend_priority: Ordered list of backend names (highest priority first).
            Required for priority_fallback strategy.
        metrics_preset: Preset name ("core", "extended", "full", "custom").
        custom_metrics: Custom metric specification when preset="custom".
            Dict with "retrieval" and "generation" keys.

    Returns:
        MetricResolver instance.
    """

    def __init__(
        self,
        evaluators: dict[str, BaseEvaluator],
        strategy: str = "priority_fallback",
        backend_priority: list[str] | None = None,
        metrics_preset: str = "core",
        custom_metrics: dict[str, list[str]] | None = None,
    ):
        self.evaluators = evaluators
        self.strategy = strategy
        self.metrics_preset = metrics_preset
        self.custom_metrics = custom_metrics

        if backend_priority is None:
            self.backend_priority = list(evaluators.keys())
        else:
            missing = [b for b in backend_priority if b not in evaluators]
            if missing:
                logger.warning(
                    f"Backend(s) {missing} in backend_priority not found "
                    f"in evaluators. Available: {list(evaluators.keys())}. "
                    f"Filtering to available backends only."
                )
            self.backend_priority = [b for b in backend_priority if b in evaluators]
            if not self.backend_priority:
                raise ValueError(
                    f"No valid backends in backend_priority. "
                    f"Requested: {backend_priority}, Available: {list(evaluators.keys())}"
                )

        self._requested_metrics = self._expand_preset(metrics_preset, custom_metrics)

    def _expand_preset(
        self, preset: str, custom_metrics: dict[str, list[str]] | None = None
    ) -> dict[str, list[str]]:
        """Expand a preset name into retrieval and generation metric lists.

        Args:
            preset: Preset name ("core", "extended", "full", "custom").
            custom_metrics: Custom metric specification for preset="custom".

        Returns:
            Dict with "retrieval" and "generation" keys.

        Raises:
            ValueError: If preset name is unknown.
        """
        if preset == "custom":
            if custom_metrics is None:
                raise ValueError("custom_metrics must be provided when preset='custom'")
            return {
                "retrieval": custom_metrics.get("retrieval", []),
                "generation": custom_metrics.get("generation", []),
            }

        if preset not in METRIC_PRESETS:
            raise ValueError(
                f"Unknown preset '{preset}'. Available: {list(METRIC_PRESETS.keys())}"
            )
        return METRIC_PRESETS[preset]

    def resolve(self) -> dict[str, dict[str, list[str]]]:
        """Resolve metric allocation for all backends.

        Returns:
            Dict mapping backend name to its allocated metrics:
            {
                "builtin": {
                    "retrieval": ["hit_rate", "mrr", ...],
                    "generation": ["faithfulness", ...]
                },
                "ragas": {
                    "retrieval": [],
                    "generation": ["answer_correctness", ...]
                }
            }
        """
        if self.strategy == "priority_fallback":
            return self._resolve_priority_fallback()
        elif self.strategy == "comparison":
            return self._resolve_comparison()
        else:
            raise ValueError(
                f"Unknown resolution strategy '{self.strategy}'. "
                f"Available: priority_fallback, comparison"
            )

    def _resolve_priority_fallback(self) -> dict[str, dict[str, list[str]]]:
        """Assign each metric to the highest-priority backend that supports it.

        Returns:
            Dict mapping backend name to allocated metrics.
        """
        allocation: dict[str, dict[str, list[str]]] = {
            name: {"retrieval": [], "generation": []} for name in self.evaluators
        }

        for metric_type in ("retrieval", "generation"):
            requested = self._requested_metrics.get(metric_type, [])
            for metric in requested:
                assigned = False
                for backend_name in self.backend_priority:
                    evaluator = self.evaluators[backend_name]
                    supported = (
                        evaluator.supported_retrieval_metrics
                        if metric_type == "retrieval"
                        else evaluator.supported_generation_metrics
                    )
                    if metric in supported:
                        allocation[backend_name][metric_type].append(metric)
                        assigned = True
                        break
                if not assigned:
                    logger.warning(
                        f"No backend supports {metric_type} metric '{metric}'. "
                        f"Checked backends: {self.backend_priority}"
                    )

        self._log_allocation(allocation, "priority_fallback")
        return allocation

    def _resolve_comparison(self) -> dict[str, dict[str, list[str]]]:
        """Assign all supported metrics to every backend for comparison.

        Returns:
            Dict mapping backend name to allocated metrics.
        """
        allocation: dict[str, dict[str, list[str]]] = {}

        for backend_name, evaluator in self.evaluators.items():
            retrieval = [
                m
                for m in self._requested_metrics.get("retrieval", [])
                if m in evaluator.supported_retrieval_metrics
            ]
            generation = [
                m
                for m in self._requested_metrics.get("generation", [])
                if m in evaluator.supported_generation_metrics
            ]
            allocation[backend_name] = {
                "retrieval": retrieval,
                "generation": generation,
            }

        self._log_allocation(allocation, "comparison")
        return allocation

    def validate(self) -> list[str]:
        """Validate that all requested metrics can be computed by some backend.

        Returns:
            List of metric names that no backend can compute.
        """
        unresolvable = []

        for metric_type in ("retrieval", "generation"):
            for metric in self._requested_metrics.get(metric_type, []):
                found = False
                for evaluator in self.evaluators.values():
                    supported = (
                        evaluator.supported_retrieval_metrics
                        if metric_type == "retrieval"
                        else evaluator.supported_generation_metrics
                    )
                    if metric in supported:
                        found = True
                        break
                if not found:
                    unresolvable.append(f"{metric_type}/{metric}")

        return unresolvable

    def _log_allocation(
        self, allocation: dict[str, dict[str, list[str]]], strategy: str
    ) -> None:
        """Log the metric allocation plan.

        Args:
            allocation: The resolved allocation dict.
            strategy: The strategy name for logging context.
        """
        logger.info(f"Metric resolution strategy: {strategy}")
        for backend_name, metrics in allocation.items():
            ret = metrics.get("retrieval", [])
            gen = metrics.get("generation", [])
            total = len(ret) + len(gen)
            if total > 0:
                logger.info(
                    f"  {backend_name}: {total} metrics "
                    f"({len(ret)} retrieval, {len(gen)} generation)"
                )
                if ret:
                    logger.debug(f"    retrieval: {ret}")
                if gen:
                    logger.debug(f"    generation: {gen}")
