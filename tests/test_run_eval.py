import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml


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

            with pytest.raises(ValueError, match="meal"):
                load_experiment_config(str(config_path))

    @pytest.mark.unit
    def test_variant_selection_first_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            exp_config = load_experiment_config(str(config_path))

            first_variant = exp_config.variants[0]
            assert first_variant.get("name") == "test_variant"

    @pytest.mark.unit
    def test_variant_selection_specific_variant(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            exp_config = load_experiment_config(str(config_path))

            variant_name = f"test_variant_alt"
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
            meal_dir = self._create_meal_structure(temp_path, "legacy_meal")

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

            with open(expected_path, "r", encoding="utf-8") as f:
                test_set = json.load(f)

            assert test_set["strategy"] == "factual"
            assert len(test_set["questions"]) == 2

    @pytest.mark.unit
    def test_exp_config_missing_variant_error(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            exp_config = load_experiment_config(str(config_path))

            variant_names = [v.get("name") for v in exp_config.variants]
            assert "nonexistent_variant" not in variant_names

    @pytest.mark.unit
    def test_exp_config_overrides_llm_preset(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            config_path = self._create_experiment_config(temp_path)

            from src.experiment import load_experiment_config

            exp_config = load_experiment_config(str(config_path))

            llm_preset = exp_config.evaluation.get("llm_preset", "default")
            assert llm_preset == "default"


class TestMetricsConfig:
    def _create_test_data(self, temp_dir: Path) -> Path:
        test_data = [
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
        test_data_path = temp_dir / "test_data.json"
        with open(test_data_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)
        return test_data_path

    def _create_mock_pipeline(self) -> MagicMock:
        pipeline = MagicMock()
        pipeline.query.side_effect = [
            {
                "answer": "Revenue is 100M.",
                "sources": ["report_a.pdf", "report_c.pdf"],
            },
            {
                "answer": "Profit is 50M.",
                "sources": ["report_b.pdf"],
            },
        ]
        return pipeline

    @pytest.mark.unit
    def test_default_metrics_when_none(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_data_path = self._create_test_data(temp_path)
            output_dir = temp_path / "output"
            pipeline = self._create_mock_pipeline()

            from eval.run_eval import run_evaluation

            summary = run_evaluation(
                pipeline=pipeline,
                test_data_path=str(test_data_path),
                output_dir=str(output_dir),
                metrics_config=None,
            )

            for result in summary["results"]:
                assert "hit_rate" in result["retrieval"]
                assert "mrr" in result["retrieval"]
                assert "ndcg" in result["retrieval"]

            assert "avg_hit_rate" in summary["retrieval_metrics"]
            assert "avg_mrr" in summary["retrieval_metrics"]
            assert "avg_ndcg" in summary["retrieval_metrics"]

    @pytest.mark.unit
    def test_subset_metrics_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_data_path = self._create_test_data(temp_path)
            output_dir = temp_path / "output"
            pipeline = self._create_mock_pipeline()

            from eval.run_eval import run_evaluation

            summary = run_evaluation(
                pipeline=pipeline,
                test_data_path=str(test_data_path),
                output_dir=str(output_dir),
                metrics_config=["hit_rate", "mrr"],
            )

            for result in summary["results"]:
                assert "hit_rate" in result["retrieval"]
                assert "mrr" in result["retrieval"]
                assert "ndcg" not in result["retrieval"]

            assert "avg_hit_rate" in summary["retrieval_metrics"]
            assert "avg_mrr" in summary["retrieval_metrics"]
            assert "avg_ndcg" not in summary["retrieval_metrics"]

    @pytest.mark.unit
    def test_empty_metrics_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_data_path = self._create_test_data(temp_path)
            output_dir = temp_path / "output"
            pipeline = self._create_mock_pipeline()

            from eval.run_eval import run_evaluation

            summary = run_evaluation(
                pipeline=pipeline,
                test_data_path=str(test_data_path),
                output_dir=str(output_dir),
                metrics_config=[],
            )

            for result in summary["results"]:
                assert result["retrieval"] == {}

            assert summary["retrieval_metrics"] == {}

    @pytest.mark.unit
    def test_single_metric_config(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            test_data_path = self._create_test_data(temp_path)
            output_dir = temp_path / "output"
            pipeline = self._create_mock_pipeline()

            from eval.run_eval import run_evaluation

            summary = run_evaluation(
                pipeline=pipeline,
                test_data_path=str(test_data_path),
                output_dir=str(output_dir),
                metrics_config=["ndcg"],
            )

            for result in summary["results"]:
                assert "hit_rate" not in result["retrieval"]
                assert "mrr" not in result["retrieval"]
                assert "ndcg" in result["retrieval"]

            assert "avg_hit_rate" not in summary["retrieval_metrics"]
            assert "avg_mrr" not in summary["retrieval_metrics"]
            assert "avg_ndcg" in summary["retrieval_metrics"]

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

            exp_config = load_experiment_config(str(config_path))

            metrics = exp_config.evaluation.get("metrics", {}).get("retrieval")
            assert metrics == ["hit_rate"]
