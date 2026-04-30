import json
from typing import Any
from unittest.mock import MagicMock

import pytest

from eval.runner.metrics import (
    compute_aggregate_metrics,
)


class TestRagasParallelConfig:
    def test_ragas_run_config_max_workers(self):
        try:
            from ragas import RunConfig

            config = RunConfig(max_workers=5, timeout=60, max_retries=3)
            assert config.max_workers == 5
        except ImportError:
            pytest.skip("ragas not installed")

    def test_ragas_evaluator_build_run_config(self):
        try:
            from eval.evaluators.ragas_evaluator import RagasEvaluator

            evaluator = RagasEvaluator(
                config={
                    "ragas": {"run_config": {"max_workers": 10}},
                    "embedding": {"model_name": "test"},
                }
            )
            run_config = evaluator._build_run_config()
            if run_config is not None:
                assert run_config.max_workers == 10
        except ImportError:
            pytest.skip("ragas not installed")

    def test_ragas_evaluator_default_max_workers(self):
        try:
            from eval.evaluators.ragas_evaluator import RagasEvaluator

            evaluator = RagasEvaluator(config={"embedding": {"model_name": "test"}})
            run_config = evaluator._build_run_config()
            if run_config is not None:
                assert run_config.max_workers == 5
        except ImportError:
            pytest.skip("ragas not installed")


class TestIndexerCacheIntegration:
    def test_indexer_cache_with_different_chunker_configs(self):
        from src.meal.hashes import compute_chunker_config_hash

        config_512 = {"chunk_size": 512, "chunk_overlap": 0}
        config_256 = {"chunk_size": 256, "chunk_overlap": 0}
        config_512_overlap = {"chunk_size": 512, "chunk_overlap": 64}

        hash_512 = compute_chunker_config_hash(config_512)
        hash_256 = compute_chunker_config_hash(config_256)
        hash_512_overlap = compute_chunker_config_hash(config_512_overlap)

        assert hash_512 != hash_256
        assert hash_512 != hash_512_overlap
        assert hash_256 != hash_512_overlap

    def test_indexer_cache_semantic_vs_fixed_strategy(self):
        from src.meal.hashes import compute_chunker_config_hash

        fixed_config = {"chunk_size": 512, "chunk_overlap": 0, "strategy": "fixed"}
        semantic_config = {
            "chunk_size": 512,
            "chunk_overlap": 0,
            "strategy": "semantic",
            "semantic": {"similarity_threshold": 0.5},
        }

        hash_fixed = compute_chunker_config_hash(fixed_config)
        hash_semantic = compute_chunker_config_hash(semantic_config)

        assert hash_fixed != hash_semantic

    def test_indexer_cache_simulation(self):
        from src.meal.hashes import compute_chunker_config_hash

        cache: dict[str, Any] = {}

        variant_a_config = {"chunk_size": 512, "chunk_overlap": 0}
        variant_b_config = {"chunk_size": 512, "chunk_overlap": 0}
        variant_c_config = {"chunk_size": 256, "chunk_overlap": 0}

        hash_a = compute_chunker_config_hash(variant_a_config)
        mock_indexer = MagicMock(name="indexer_512")
        cache[hash_a] = mock_indexer

        hash_b = compute_chunker_config_hash(variant_b_config)
        assert hash_b in cache
        assert cache[hash_b] is mock_indexer

        hash_c = compute_chunker_config_hash(variant_c_config)
        assert hash_c not in cache

        mock_indexer_c = MagicMock(name="indexer_256")
        cache[hash_c] = mock_indexer_c
        assert len(cache) == 2


class TestPipelineProfilerStages:
    def test_profiler_stage_lifecycle(self):
        from eval.pipeline_profiler import PipelineProfiler

        profiler = PipelineProfiler(
            experiment_name="test_exp",
            total_pages=10,
            total_questions=5,
        )

        profiler.start_profiling()
        profiler.begin_stage("S1", {"meal_name": "test"})
        profiler.end_stage()

        metrics = profiler.get_stage_metrics("S1")
        assert metrics is not None
        assert metrics.duration_seconds > 0

        profiler.stop_profiling()

    def test_profiler_all_stages(self):
        from eval.pipeline_profiler import PipelineProfiler

        profiler = PipelineProfiler(
            experiment_name="test_exp",
            total_pages=10,
            total_questions=5,
        )

        profiler.start_profiling()

        for stage_id in ["S1", "S2", "S3", "S4", "S5", "S6", "S7", "S8", "S9"]:
            profiler.begin_stage(stage_id)
            profiler.end_stage()

        profiler.stop_profiling()

        report = profiler.generate_markdown_report()
        assert "S1" in report
        assert "S8" in report
        assert "S9" in report

    def test_profiler_profile_stage_context_manager(self):
        from eval.pipeline_profiler import PipelineProfiler

        profiler = PipelineProfiler(
            experiment_name="test_exp",
            total_pages=10,
            total_questions=5,
        )

        profiler.start_profiling()

        with profiler.profile_stage("S1", {"meal_name": "test"}):
            pass

        metrics = profiler.get_stage_metrics("S1")
        assert metrics is not None
        assert metrics.duration_seconds >= 0

        profiler.stop_profiling()

    def test_profiler_save_report(self, tmp_path):
        from eval.pipeline_profiler import PipelineProfiler

        profiler = PipelineProfiler(
            experiment_name="test_exp",
            total_pages=10,
            total_questions=5,
        )

        profiler.start_profiling()
        profiler.begin_stage("S1")
        profiler.end_stage()
        profiler.stop_profiling()

        profiler.save_report(tmp_path, "profile_data.json")

        assert (tmp_path / "profile_data.json").exists()

        with open(tmp_path / "profile_data.json", encoding="utf-8") as f:
            data = json.load(f)
        assert "stages" in data

    def test_profiler_token_tracking(self):
        from eval.pipeline_profiler import PipelineProfiler

        profiler = PipelineProfiler(
            experiment_name="test_exp",
            total_pages=10,
            total_questions=5,
        )

        profiler.start_profiling()
        profiler.begin_stage("S7")
        profiler.report_stage_tokens("S7", 100, 50)
        profiler.end_stage()
        profiler.stop_profiling()

        metrics = profiler.get_stage_metrics("S7")
        assert metrics.input_tokens == 100
        assert metrics.output_tokens == 50

    def test_profiler_untracked_time(self):
        import time

        from eval.pipeline_profiler import PipelineProfiler

        profiler = PipelineProfiler(
            experiment_name="test_exp",
            total_pages=10,
            total_questions=5,
        )

        profiler.start_profiling()

        profiler.begin_stage("S1")
        time.sleep(0.01)
        profiler.end_stage()

        time.sleep(0.1)

        profiler.begin_stage("S2")
        time.sleep(0.01)
        profiler.end_stage()

        profiler.stop_profiling()

        report = profiler.generate_markdown_report()
        assert "未追踪时间" in report

        s1 = profiler.get_stage_metrics("S1")
        s2 = profiler.get_stage_metrics("S2")
        tracked = s1.duration_seconds + s2.duration_seconds
        total = profiler.get_total_duration()
        untracked = total - tracked
        assert untracked > 0.05


class TestTokenTrackerMerge:
    def test_token_tracker_merge(self):
        from src.token_tracker import DetailedTokenUsage, TokenTracker

        tracker1 = TokenTracker()
        tracker2 = TokenTracker()

        usage1 = DetailedTokenUsage(
            input_tokens=100,
            output_tokens=50,
            system_prompt_tokens=10,
            contexts_tokens=20,
            query_tokens=5,
        )
        usage2 = DetailedTokenUsage(
            input_tokens=200,
            output_tokens=100,
            system_prompt_tokens=20,
            contexts_tokens=40,
            query_tokens=10,
        )

        tracker1.record(
            category="rag_qa", model_name="gpt-4", usage=usage1, variant_name="v1"
        )
        tracker2.record(
            category="rag_qa", model_name="gpt-4", usage=usage2, variant_name="v2"
        )

        tracker1.merge(tracker2)

        total = tracker1.get_total()
        assert total.input_tokens == 300
        assert total.output_tokens == 150

    def test_token_tracker_cost_estimation(self):
        from src.token_tracker import DetailedTokenUsage, TokenTracker

        tracker = TokenTracker()
        usage = DetailedTokenUsage(
            input_tokens=1000,
            output_tokens=500,
            system_prompt_tokens=0,
            contexts_tokens=0,
            query_tokens=0,
        )
        tracker.record(category="rag_qa", model_name="gpt-4", usage=usage)

        cost_config = {
            "models": {
                "gpt-4": {
                    "input_price_per_1k": 0.03,
                    "output_price_per_1k": 0.06,
                }
            }
        }

        cost_info = tracker.estimate_cost(cost_config)
        assert cost_info["total_cost"] > 0
        assert cost_info["input_cost"] == pytest.approx(0.03)
        assert cost_info["output_cost"] == pytest.approx(0.03)


class TestComputeAggregateMetricsFull:
    def test_aggregate_with_all_metric_types(self):
        results = [
            {
                "id": "q1",
                "retrieval": {
                    "hit_rate": 1.0,
                    "mrr": 1.0,
                    "ndcg": 1.0,
                    "retrieval_diversity": 0.5,
                },
                "chunk_retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                "dedup_retrieval": {"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
                "false_positive_rate": 0.1,
                "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8},
                "question_type": "factual",
            },
            {
                "id": "q2",
                "retrieval": {
                    "hit_rate": 0.5,
                    "mrr": 0.5,
                    "ndcg": 0.5,
                    "retrieval_diversity": 0.3,
                },
                "chunk_retrieval": {"hit_rate": 0.4, "mrr": 0.3, "ndcg": 0.35},
                "dedup_retrieval": {"hit_rate": 0.5, "mrr": 0.5, "ndcg": 0.5},
                "false_positive_rate": 0.2,
                "generation": {"faithfulness": 0.7, "answer_relevancy": 0.6},
                "question_type": "reasoning",
            },
        ]

        metrics = compute_aggregate_metrics(results)

        assert metrics["avg_hit_rate"] == pytest.approx(0.75)
        assert metrics["avg_mrr"] == pytest.approx(0.75)
        assert metrics["avg_ndcg"] == pytest.approx(0.75)
        assert metrics["avg_retrieval_diversity"] == pytest.approx(0.4)
        assert metrics["avg_false_positive_rate"] == pytest.approx(0.15)
        assert metrics["chunk_level_metrics"]["avg_hit_rate"] == pytest.approx(0.6)
        assert metrics["dedup_metrics"]["avg_hit_rate"] == pytest.approx(0.75)
        assert metrics["hallucination_rate"] is not None
        assert "by_question_type" in metrics
        assert "factual" in metrics["by_question_type"]
        assert "reasoning" in metrics["by_question_type"]

    def test_aggregate_with_namespaced_metrics(self):
        results = [
            {
                "id": "q1",
                "retrieval": {"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
                "generation": {
                    "builtin_faithfulness": 0.9,
                    "ragas_faithfulness": 0.85,
                    "builtin_answer_relevancy": 0.8,
                    "ragas_answer_relevancy": 0.75,
                },
            },
        ]

        metrics = compute_aggregate_metrics(results)

        assert "generation_metrics" in metrics
        gen = metrics["generation_metrics"]
        assert "avg_builtin_faithfulness" in gen
        assert "avg_ragas_faithfulness" in gen
        assert gen["avg_builtin_faithfulness"] == pytest.approx(0.9)
        assert gen["avg_ragas_faithfulness"] == pytest.approx(0.85)

    def test_aggregate_with_llm_retrieval(self):
        results = [
            {
                "id": "q1",
                "retrieval": {"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
                "llm_retrieval": {"context_precision": 0.9, "context_recall": 0.8},
            },
            {
                "id": "q2",
                "retrieval": {"hit_rate": 0.5, "mrr": 0.5, "ndcg": 0.5},
                "llm_retrieval": {"context_precision": 0.7, "context_recall": 0.6},
            },
        ]

        metrics = compute_aggregate_metrics(results)

        assert "avg_context_precision" in metrics
        assert "avg_context_recall" in metrics
        assert metrics["avg_context_precision"] == pytest.approx(0.8)
        assert metrics["avg_context_recall"] == pytest.approx(0.7)
