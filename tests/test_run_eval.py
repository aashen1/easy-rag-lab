import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from eval.evaluators.builtin_evaluator import BuiltinEvaluator
from eval.runner.evaluation import collect_rag_samples, evaluate_with_builtin
from eval.runner.metrics import compute_aggregate_metrics
from src.exceptions import ConfigurationError


class TestRunEvalExpConfig:
    def _create_experiment_config(
        self,
        temp_dir: Path,
        meal_name: str = "test_meal",
        variant_name: str = "test_variant",
        strategy: str = "factual",
    ) -> Path:
        config = {
            "name": "test_experiment",
            "description": "Test experiment configuration",
            "data": {
                "meal": meal_name,
                "create_if_missing": {
                    "sample_ratio": 0.1,
                    "seed": 42,
                },
            },
            "test_sets": [
                {
                    "strategy": strategy,
                    "num_questions": 10,
                    "seed": 100,
                }
            ],
            "variants": [
                {
                    "name": variant_name,
                    "description": "Test variant",
                    "config_overrides": {
                        "chunker": {
                            "chunk_size": 512,
                            "chunk_overlap": 0,
                        }
                    },
                },
                {
                    "name": f"{variant_name}_alt",
                    "description": "Alternative variant",
                    "config_overrides": {
                        "chunker": {
                            "chunk_size": 1024,
                            "chunk_overlap": 128,
                        }
                    },
                },
            ],
            "evaluation": {
                "llm_preset": "default",
                "metrics": {
                    "retrieval": ["hit_rate", "mrr", "ndcg"],
                },
            },
        }

        config_path = temp_dir / "exp_config.yaml"
        with open(config_path, "w", encoding="utf-8") as f:
            yaml.dump(config, f)

        return config_path

    def _create_meal_structure(
        self,
        temp_dir: Path,
        meal_name: str,
        test_set_name: str = "auto_factual",
    ) -> Path:
        meals_dir = temp_dir / "meals"
        meal_dir = meals_dir / meal_name
        meal_dir.mkdir(parents=True, exist_ok=True)

        manifest = {
            "name": meal_name,
            "data_id": "test_data_id_123",
            "created_at": "2025-01-01T00:00:00",
            "collection_name": f"m_{meal_name}",
            "config_hashes": {
                "parser": "abc123",
                "chunker": "def456",
                "embedding": "ghi789",
            },
            "pdf_files": [],
            "stats": {
                "total_pdfs": 5,
                "total_pages": 100,
                "total_chunks": 500,
            },
        }
        with open(meal_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        test_sets_dir = meal_dir / "test_sets"
        test_sets_dir.mkdir(exist_ok=True)

        test_set = {
            "name": test_set_name,
            "strategy": "factual",
            "questions": [
                {
                    "id": "q1",
                    "question": "Test question 1?",
                    "source_files": ["test.pdf"],
                },
                {
                    "id": "q2",
                    "question": "Test question 2?",
                    "source_files": ["test2.pdf"],
                },
            ],
        }
        with open(test_sets_dir / f"{test_set_name}.json", "w", encoding="utf-8") as f:
            json.dump(test_set, f)

        return meal_dir

    @pytest.mark.unit
    def test_load_experiment_config_success(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))

            assert exp_config.name == "test_experiment"
            assert exp_config.data.get("meal") == "test_meal"
            assert len(exp_config.variants) == 2
            assert exp_config.variants[0].get("name") == "test_variant"

    @pytest.mark.unit
    def test_load_experiment_config_missing_meal(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            config = {
                "name": "test_experiment",
                "description": "Test",
                "data": {},
                "test_sets": [{"strategy": "factual", "num_questions": 10}],
                "variants": [{"name": "v1"}],
                "evaluation": {"metrics": {}},
            }

            config_path = temp_path / "exp_config.yaml"
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            from src.experiment import load_experiment_config

            with (
                pytest.warns(
                    DeprecationWarning, match="deprecated configuration format"
                ),
                pytest.raises(ConfigurationError, match="meal"),
            ):
                load_experiment_config(str(config_path))

    @pytest.mark.unit
    def test_variant_selection_first_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))

            first_variant = exp_config.variants[0]
            assert first_variant.get("name") == "test_variant"

    @pytest.mark.unit
    def test_variant_selection_specific_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))

            variant_name = "test_variant_alt"
            found_variant = None
            for v in exp_config.variants:
                if v.get("name") == variant_name:
                    found_variant = v
                    break

            assert found_variant is not None
            assert found_variant.get("name") == variant_name

    @pytest.mark.unit
    def test_merge_config_with_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config, merge_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))
            system_config = {
                "chunker": {
                    "chunk_size": 256,
                    "chunk_overlap": 50,
                },
                "embedding": {
                    "model_name": "test-model",
                },
            }

            variant = exp_config.variants[0]
            merged = merge_config(system_config, exp_config, variant)

            assert merged["chunker"]["chunk_size"] == 512
            assert merged["chunker"]["chunk_overlap"] == 0
            assert merged["embedding"]["model_name"] == "test-model"

    @pytest.mark.unit
    def test_merge_config_without_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config, merge_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))
            system_config = {
                "chunker": {
                    "chunk_size": 256,
                    "chunk_overlap": 50,
                },
            }

            merged = merge_config(system_config, exp_config, None)

            assert merged["chunker"]["chunk_size"] == 256
            assert merged["chunker"]["chunk_overlap"] == 50

    @pytest.mark.unit
    def test_backward_compatibility_meal_arg(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self._create_meal_structure(temp_path, "legacy_meal")

            from src.meal import MealManager

            system_config = {
                "meals": {
                    "dir": str(temp_path / "meals"),
                },
            }

            meal_manager = MealManager(system_config)
            assert meal_manager.meal_exists("legacy_meal")

            meal_config = meal_manager.load_meal("legacy_meal")
            assert meal_config.name == "legacy_meal"

    @pytest.mark.unit
    def test_test_set_path_resolution_from_exp_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            self._create_meal_structure(temp_path, "test_meal", "auto_factual")

            test_sets_dir = temp_path / "meals" / "test_meal" / "test_sets"
            expected_path = test_sets_dir / "auto_factual.json"

            assert expected_path.exists()

            with open(expected_path, encoding="utf-8") as f:
                test_set = json.load(f)

            assert test_set["strategy"] == "factual"
            assert len(test_set["questions"]) == 2

    @pytest.mark.unit
    def test_exp_config_missing_variant_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))

            variant_names = [v.get("name") for v in exp_config.variants]
            assert "nonexistent_variant" not in variant_names

    @pytest.mark.unit
    def test_exp_config_overrides_llm_preset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))

            llm_preset = exp_config.evaluation.get("llm_preset", "default")
            assert llm_preset == "default"


def _create_test_set(questions: list[dict]) -> dict:
    return {"name": "test_set", "questions": questions}


def _create_mock_pipeline(query_responses: list[dict]) -> MagicMock:
    pipeline = MagicMock()
    pipeline.config = {"evaluation": {"concurrent_queries": 1}}
    pipeline.query.side_effect = query_responses
    return pipeline


class TestMetricsConfig:
    def _test_questions(self) -> list[dict]:
        return [
            {
                "id": "q1",
                "question": "What is the revenue?",
                "source_files": ["report_a.pdf"],
            },
            {
                "id": "q2",
                "question": "What is the profit?",
                "source_files": ["report_b.pdf"],
            },
        ]

    def _query_responses(self) -> list[dict]:
        return [
            {
                "answer": "Revenue is 100M.",
                "sources": ["report_a.pdf", "report_c.pdf"],
            },
            {
                "answer": "Profit is 50M.",
                "sources": ["report_b.pdf"],
            },
        ]

    @pytest.mark.unit
    def test_default_metrics_when_none(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses())

        samples = collect_rag_samples(pipeline, test_set)
        evaluator = BuiltinEvaluator(config={})
        results = evaluate_with_builtin(
            samples=samples,
            evaluator=evaluator,
            retrieval_metrics=None,
        )

        for result in results:
            assert "hit_rate" in result["retrieval"]
            assert "mrr" in result["retrieval"]
            assert "ndcg" in result["retrieval"]

        aggregate = compute_aggregate_metrics(results)
        assert "avg_hit_rate" in aggregate
        assert "avg_mrr" in aggregate
        assert "avg_ndcg" in aggregate

    @pytest.mark.unit
    def test_subset_metrics_config(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses())

        samples = collect_rag_samples(pipeline, test_set)
        evaluator = BuiltinEvaluator(config={})
        results = evaluate_with_builtin(
            samples=samples,
            evaluator=evaluator,
            retrieval_metrics=["hit_rate", "mrr"],
        )

        for result in results:
            assert "hit_rate" in result["retrieval"]
            assert "mrr" in result["retrieval"]
            assert "ndcg" not in result["retrieval"]

        aggregate = compute_aggregate_metrics(results)
        assert "avg_hit_rate" in aggregate
        assert "avg_mrr" in aggregate
        assert aggregate["avg_ndcg"] == 0.0

    @pytest.mark.unit
    def test_empty_metrics_config(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses())

        samples = collect_rag_samples(pipeline, test_set)
        evaluator = BuiltinEvaluator(config={})
        results = evaluate_with_builtin(
            samples=samples,
            evaluator=evaluator,
            retrieval_metrics=[],
        )

        for result in results:
            assert result["retrieval"] == {}

    @pytest.mark.unit
    def test_single_metric_config(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses())

        samples = collect_rag_samples(pipeline, test_set)
        evaluator = BuiltinEvaluator(config={})
        results = evaluate_with_builtin(
            samples=samples,
            evaluator=evaluator,
            retrieval_metrics=["ndcg"],
        )

        for result in results:
            assert "hit_rate" not in result["retrieval"]
            assert "mrr" not in result["retrieval"]
            assert "ndcg" in result["retrieval"]

        aggregate = compute_aggregate_metrics(results)
        assert aggregate["avg_hit_rate"] == 0.0
        assert aggregate["avg_mrr"] == 0.0
        assert "avg_ndcg" in aggregate

    @pytest.mark.unit
    def test_exp_config_metrics_extraction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            config = {
                "name": "test_experiment",
                "description": "Test",
                "data": {"meal": "test_meal"},
                "test_sets": [{"strategy": "factual", "num_questions": 10}],
                "variants": [{"name": "v1"}],
                "evaluation": {
                    "metrics": {
                        "retrieval": ["hit_rate"],
                    },
                },
            }

            config_path = temp_path / "exp_config.yaml"
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            from src.experiment import load_experiment_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))

            metrics = exp_config.evaluation.get("metrics", {}).get("retrieval")
            assert metrics == ["hit_rate"]


class TestGenerationMetrics:
    def _test_questions(self) -> list[dict]:
        return [
            {
                "id": "q1",
                "question": "What is the revenue?",
                "source_files": ["report_a.pdf"],
            },
            {
                "id": "q2",
                "question": "What is the profit?",
                "source_files": ["report_b.pdf"],
            },
        ]

    def _query_responses_with_contexts(self) -> list[dict]:
        return [
            {
                "answer": "Revenue is 100M.",
                "sources": ["report_a.pdf", "report_c.pdf"],
                "contexts": [
                    "Revenue for 2023 was 100 million.",
                    "Total revenue grew by 10%.",
                ],
            },
            {
                "answer": "Profit is 50M.",
                "sources": ["report_b.pdf"],
                "contexts": ["Net profit for 2023 was 50 million."],
            },
        ]

    @pytest.mark.unit
    def test_generation_metrics_disabled_by_default(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses_with_contexts())

        samples = collect_rag_samples(pipeline, test_set)
        evaluator = BuiltinEvaluator(config={})
        results = evaluate_with_builtin(
            samples=samples,
            evaluator=evaluator,
            retrieval_metrics=["hit_rate"],
            generation_metrics=None,
            llm_config=None,
        )

        for result in results:
            assert "generation" not in result

    @pytest.mark.unit
    def test_generation_metrics_empty_config(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses_with_contexts())

        samples = collect_rag_samples(pipeline, test_set)
        evaluator = BuiltinEvaluator(config={})
        results = evaluate_with_builtin(
            samples=samples,
            evaluator=evaluator,
            retrieval_metrics=["hit_rate"],
            generation_metrics=[],
            llm_config={
                "api_key": "test",
                "base_url": "test",
                "model_name": "test",
            },
        )

        for result in results:
            assert "generation" not in result

    @pytest.mark.unit
    def test_generation_metrics_requires_llm_config(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses_with_contexts())

        samples = collect_rag_samples(pipeline, test_set)
        evaluator = BuiltinEvaluator(config={})
        results = evaluate_with_builtin(
            samples=samples,
            evaluator=evaluator,
            retrieval_metrics=["hit_rate"],
            generation_metrics=["faithfulness", "answer_relevancy"],
            llm_config=None,
        )

        for result in results:
            assert "generation" not in result

    @pytest.mark.unit
    def test_generation_metrics_with_mocked_llm(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses_with_contexts())

        with (
            patch(
                "eval.evaluators.builtin_evaluator.calculate_faithfulness"
            ) as mock_faithfulness,
            patch(
                "eval.evaluators.builtin_evaluator.calculate_answer_relevancy"
            ) as mock_relevancy,
        ):
            mock_faithfulness.return_value = 0.85
            mock_relevancy.return_value = 0.92

            samples = collect_rag_samples(pipeline, test_set)
            evaluator = BuiltinEvaluator(config={})
            results = evaluate_with_builtin(
                samples=samples,
                evaluator=evaluator,
                retrieval_metrics=["hit_rate"],
                generation_metrics=["faithfulness", "answer_relevancy"],
                llm_config={
                    "api_key": "test_key",
                    "base_url": "https://test.url",
                    "model_name": "test_model",
                },
            )

            assert mock_faithfulness.call_count == 2
            assert mock_relevancy.call_count == 2

            for result in results:
                assert "generation" in result
                assert "faithfulness" in result["generation"]
                assert "answer_relevancy" in result["generation"]
                assert result["generation"]["faithfulness"] == 0.85
                assert result["generation"]["answer_relevancy"] == 0.92

            aggregate = compute_aggregate_metrics(results)
            assert "generation_metrics" in aggregate
            assert aggregate["generation_metrics"]["avg_faithfulness"] == 0.85
            assert aggregate["generation_metrics"]["avg_answer_relevancy"] == 0.92

    @pytest.mark.unit
    def test_generation_metrics_faithfulness_only(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses_with_contexts())

        with patch(
            "eval.evaluators.builtin_evaluator.calculate_faithfulness"
        ) as mock_faithfulness:
            mock_faithfulness.return_value = 0.75

            samples = collect_rag_samples(pipeline, test_set)
            evaluator = BuiltinEvaluator(config={})
            results = evaluate_with_builtin(
                samples=samples,
                evaluator=evaluator,
                retrieval_metrics=["hit_rate"],
                generation_metrics=["faithfulness"],
                llm_config={
                    "api_key": "test_key",
                    "base_url": "https://test.url",
                    "model_name": "test_model",
                },
            )

            for result in results:
                assert "generation" in result
                assert "faithfulness" in result["generation"]
                assert "answer_relevancy" not in result["generation"]

            aggregate = compute_aggregate_metrics(results)
            assert "generation_metrics" in aggregate
            assert "avg_faithfulness" in aggregate["generation_metrics"]
            assert "avg_answer_relevancy" not in aggregate["generation_metrics"]

    @pytest.mark.unit
    def test_generation_metrics_handles_llm_error(self):
        test_set = _create_test_set(self._test_questions())
        pipeline = _create_mock_pipeline(self._query_responses_with_contexts())

        with (
            patch(
                "eval.evaluators.builtin_evaluator.calculate_faithfulness"
            ) as mock_faithfulness,
            patch(
                "eval.evaluators.builtin_evaluator.calculate_answer_relevancy"
            ) as mock_relevancy,
        ):
            mock_faithfulness.side_effect = Exception("LLM API error")
            mock_relevancy.return_value = 0.90

            samples = collect_rag_samples(pipeline, test_set)
            evaluator = BuiltinEvaluator(config={})
            results = evaluate_with_builtin(
                samples=samples,
                evaluator=evaluator,
                retrieval_metrics=["hit_rate"],
                generation_metrics=["faithfulness", "answer_relevancy"],
                llm_config={
                    "api_key": "test_key",
                    "base_url": "https://test.url",
                    "model_name": "test_model",
                },
            )

            for result in results:
                assert "generation" in result
                assert result["generation"]["faithfulness"] is None
                assert result["generation"]["answer_relevancy"] == 0.90

            aggregate = compute_aggregate_metrics(results)
            assert "generation_metrics" in aggregate
            assert "avg_faithfulness" not in aggregate["generation_metrics"]
            assert aggregate["generation_metrics"]["avg_answer_relevancy"] == 0.90

    @pytest.mark.unit
    def test_exp_config_generation_metrics_extraction(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)

            config = {
                "name": "test_experiment",
                "description": "Test",
                "data": {"meal": "test_meal"},
                "test_sets": [{"strategy": "factual", "num_questions": 10}],
                "variants": [{"name": "v1"}],
                "evaluation": {
                    "llm_preset": "default",
                    "metrics": {
                        "retrieval": ["hit_rate", "mrr"],
                        "generation": ["faithfulness", "answer_relevancy"],
                    },
                },
            }

            config_path = temp_path / "exp_config.yaml"
            with open(config_path, "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            from src.experiment import load_experiment_config

            with pytest.warns(
                DeprecationWarning, match="deprecated configuration format"
            ):
                exp_config = load_experiment_config(str(config_path))

            retrieval_metrics = exp_config.evaluation.get("metrics", {}).get(
                "retrieval"
            )
            generation_metrics = exp_config.evaluation.get("metrics", {}).get(
                "generation"
            )

            assert retrieval_metrics == ["hit_rate", "mrr"]
            assert generation_metrics == ["faithfulness", "answer_relevancy"]
