"""Tests for MetricResolver: multi-backend metric allocation."""

from __future__ import annotations

import pytest

from eval.evaluators.base import BaseEvaluator
from eval.metrics.metric_resolver import METRIC_PRESETS, MetricResolver


class MockEvaluator(BaseEvaluator):
    """Mock evaluator with configurable supported metrics."""

    def __init__(
        self,
        name: str,
        retrieval_metrics: list[str] | None = None,
        generation_metrics: list[str] | None = None,
    ):
        super().__init__()
        self._name = name
        self._retrieval_metrics = retrieval_metrics or []
        self._generation_metrics = generation_metrics or []

    @property
    def name(self) -> str:
        return self._name

    @property
    def supported_retrieval_metrics(self) -> list[str]:
        return self._retrieval_metrics

    @property
    def supported_generation_metrics(self) -> list[str]:
        return self._generation_metrics

    def evaluate_single(self, **kwargs):
        raise NotImplementedError


@pytest.fixture
def builtin_evaluator():
    return MockEvaluator(
        name="builtin",
        retrieval_metrics=[
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
        ],
        generation_metrics=["faithfulness", "answer_relevancy"],
    )


@pytest.fixture
def ragas_evaluator():
    return MockEvaluator(
        name="ragas",
        retrieval_metrics=[],
        generation_metrics=[
            "faithfulness",
            "answer_relevancy",
            "context_precision",
            "context_recall",
            "answer_correctness",
            "semantic_similarity",
        ],
    )


@pytest.fixture
def dual_evaluators(builtin_evaluator, ragas_evaluator):
    return {"builtin": builtin_evaluator, "ragas": ragas_evaluator}


class TestMetricPresets:
    @pytest.mark.unit
    def test_core_preset_has_required_metrics(self):
        preset = METRIC_PRESETS["core"]
        assert "hit_rate" in preset["retrieval"]
        assert "faithfulness" in preset["generation"]
        assert "answer_relevancy" in preset["generation"]

    @pytest.mark.unit
    def test_extended_preset_includes_core(self):
        core = METRIC_PRESETS["core"]
        extended = METRIC_PRESETS["extended"]
        for m in core["retrieval"]:
            assert m in extended["retrieval"]
        for m in core["generation"]:
            assert m in extended["generation"]

    @pytest.mark.unit
    def test_full_preset_includes_extended(self):
        extended = METRIC_PRESETS["extended"]
        full = METRIC_PRESETS["full"]
        for m in extended["retrieval"]:
            assert m in full["retrieval"]
        for m in extended["generation"]:
            assert m in full["generation"]

    @pytest.mark.unit
    def test_full_preset_has_ragas_only_metrics(self):
        full = METRIC_PRESETS["full"]
        assert "answer_correctness" in full["generation"]
        assert "semantic_similarity" in full["generation"]


class TestPriorityFallback:
    @pytest.mark.unit
    def test_builtin_priority_no_overlap(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="priority_fallback",
            backend_priority=["builtin", "ragas"],
            metrics_preset="core",
        )
        allocation = resolver.resolve()

        builtin_gen = allocation["builtin"]["generation"]
        ragas_gen = allocation["ragas"]["generation"]

        assert "faithfulness" in builtin_gen
        assert "answer_relevancy" in builtin_gen
        assert "faithfulness" not in ragas_gen
        assert "answer_relevancy" not in ragas_gen

    @pytest.mark.unit
    def test_ragas_priority_no_overlap(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="priority_fallback",
            backend_priority=["ragas", "builtin"],
            metrics_preset="core",
        )
        allocation = resolver.resolve()

        builtin_gen = allocation["builtin"]["generation"]
        ragas_gen = allocation["ragas"]["generation"]

        assert "faithfulness" in ragas_gen
        assert "answer_relevancy" in ragas_gen
        assert "faithfulness" not in builtin_gen
        assert "answer_relevancy" not in builtin_gen

    @pytest.mark.unit
    def test_ragas_only_metrics_assigned_to_ragas(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="priority_fallback",
            backend_priority=["builtin", "ragas"],
            metrics_preset="full",
        )
        allocation = resolver.resolve()

        assert "answer_correctness" in allocation["ragas"]["generation"]
        assert "semantic_similarity" in allocation["ragas"]["generation"]
        assert "answer_correctness" not in allocation["builtin"]["generation"]

    @pytest.mark.unit
    def test_builtin_only_metrics_assigned_to_builtin(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="priority_fallback",
            backend_priority=["ragas", "builtin"],
            metrics_preset="core",
        )
        allocation = resolver.resolve()

        assert "hit_rate" in allocation["builtin"]["retrieval"]
        assert "mrr" in allocation["builtin"]["retrieval"]
        assert "hit_rate" not in allocation["ragas"]["retrieval"]

    @pytest.mark.unit
    def test_single_backend_all_metrics_assigned(self, builtin_evaluator):
        resolver = MetricResolver(
            evaluators={"builtin": builtin_evaluator},
            strategy="priority_fallback",
            metrics_preset="core",
        )
        allocation = resolver.resolve()

        assert len(allocation) == 1
        assert "hit_rate" in allocation["builtin"]["retrieval"]
        assert "faithfulness" in allocation["builtin"]["generation"]


class TestComparison:
    @pytest.mark.unit
    def test_both_backends_compute_overlapping_metrics(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="comparison",
            metrics_preset="core",
        )
        allocation = resolver.resolve()

        assert "faithfulness" in allocation["builtin"]["generation"]
        assert "faithfulness" in allocation["ragas"]["generation"]
        assert "answer_relevancy" in allocation["builtin"]["generation"]
        assert "answer_relevancy" in allocation["ragas"]["generation"]

    @pytest.mark.unit
    def test_ragas_only_metrics_in_ragas(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="comparison",
            metrics_preset="full",
        )
        allocation = resolver.resolve()

        assert "answer_correctness" in allocation["ragas"]["generation"]
        assert "answer_correctness" not in allocation["builtin"]["generation"]

    @pytest.mark.unit
    def test_builtin_only_retrieval_metrics(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="comparison",
            metrics_preset="core",
        )
        allocation = resolver.resolve()

        assert "hit_rate" in allocation["builtin"]["retrieval"]
        assert allocation["ragas"]["retrieval"] == []


class TestCustomPreset:
    @pytest.mark.unit
    def test_custom_metrics(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="priority_fallback",
            backend_priority=["builtin", "ragas"],
            metrics_preset="custom",
            custom_metrics={
                "retrieval": ["hit_rate"],
                "generation": ["faithfulness", "answer_correctness"],
            },
        )
        allocation = resolver.resolve()

        assert "hit_rate" in allocation["builtin"]["retrieval"]
        assert "faithfulness" in allocation["builtin"]["generation"]
        assert "answer_correctness" in allocation["ragas"]["generation"]

    @pytest.mark.unit
    def test_custom_preset_requires_custom_metrics(self, dual_evaluators):
        with pytest.raises(ValueError, match="custom_metrics must be provided"):
            MetricResolver(
                evaluators=dual_evaluators,
                metrics_preset="custom",
            )


class TestValidation:
    @pytest.mark.unit
    def test_validate_all_resolvable(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="priority_fallback",
            metrics_preset="full",
        )
        unresolvable = resolver.validate()
        assert unresolvable == []

    @pytest.mark.unit
    def test_validate_unresolvable_metrics(self):
        evaluator = MockEvaluator(
            name="builtin",
            retrieval_metrics=["hit_rate"],
            generation_metrics=["faithfulness"],
        )
        resolver = MetricResolver(
            evaluators={"builtin": evaluator},
            strategy="priority_fallback",
            metrics_preset="custom",
            custom_metrics={
                "retrieval": ["hit_rate", "nonexistent_metric"],
                "generation": ["faithfulness", "imaginary_metric"],
            },
        )
        unresolvable = resolver.validate()
        assert "retrieval/nonexistent_metric" in unresolvable
        assert "generation/imaginary_metric" in unresolvable


class TestEdgeCases:
    @pytest.mark.unit
    def test_unknown_preset_raises_error(self, dual_evaluators):
        with pytest.raises(ValueError, match="Unknown preset"):
            MetricResolver(
                evaluators=dual_evaluators,
                metrics_preset="nonexistent",
            )

    @pytest.mark.unit
    def test_unknown_strategy_raises_error(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="invalid_strategy",
            metrics_preset="core",
        )
        with pytest.raises(ValueError, match="Unknown resolution strategy"):
            resolver.resolve()

    @pytest.mark.unit
    def test_invalid_backend_priority_raises_error(self, dual_evaluators):
        with pytest.raises(ValueError, match="Backend.*not found"):
            MetricResolver(
                evaluators=dual_evaluators,
                backend_priority=["builtin", "nonexistent"],
                metrics_preset="core",
            )

    @pytest.mark.unit
    def test_default_backend_priority(self, dual_evaluators):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            metrics_preset="core",
        )
        assert resolver.backend_priority == ["builtin", "ragas"]

    @pytest.mark.unit
    def test_empty_allocation_for_backend_with_no_matching_metrics(
        self, dual_evaluators
    ):
        resolver = MetricResolver(
            evaluators=dual_evaluators,
            strategy="priority_fallback",
            backend_priority=["builtin", "ragas"],
            metrics_preset="custom",
            custom_metrics={
                "retrieval": ["hit_rate"],
                "generation": [],
            },
        )
        allocation = resolver.resolve()

        assert "hit_rate" in allocation["builtin"]["retrieval"]
        assert allocation["ragas"]["retrieval"] == []
        assert allocation["ragas"]["generation"] == []
