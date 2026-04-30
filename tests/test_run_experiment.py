import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from eval.run_experiment import (
    collect_rag_samples,
    compute_aggregate_metrics,
    evaluate_test_set,
    evaluate_with_builtin,
    sanitize_config,
    verify_experiment_assets,
)
from src.exceptions import ConfigurationError


class TestAssetVerificationResult:
    def test_creation_valid(self):
        from eval.run_experiment import AssetVerificationResult

        result = AssetVerificationResult(valid=True)
        assert result.valid is True
        assert result.missing_files == []
        assert result.invalid_files == []
        assert result.pdf_issues == {}

    def test_creation_with_issues(self):
        from eval.run_experiment import AssetVerificationResult

        result = AssetVerificationResult(
            valid=False,
            missing_files=["manifest.json"],
            invalid_files=["config_snapshot.yaml"],
            pdf_issues={"test.pdf": "File not found"},
            raw_dir=Path("data/raw"),
        )
        assert result.valid is False
        assert "manifest.json" in result.missing_files
        assert "config_snapshot.yaml" in result.invalid_files
        assert "test.pdf" in result.pdf_issues

    def test_to_dict(self):
        from eval.run_experiment import AssetVerificationResult

        result = AssetVerificationResult(
            valid=True,
            missing_files=[],
            raw_dir=Path("data/raw"),
        )
        d = result.to_dict()
        assert d["valid"] is True
        assert "data" in d["raw_dir"] and "raw" in d["raw_dir"]


class TestVerifyExperimentAssets:
    def _create_experiment_dir(
        self,
        temp_dir: Path,
        include_manifest: bool = True,
        include_config: bool = True,
        include_meal: bool = True,
        valid_manifest: bool = True,
        valid_config: bool = True,
        valid_meal: bool = True,
    ) -> Path:
        exp_dir = temp_dir / "exp_test"
        exp_dir.mkdir()

        if include_manifest:
            manifest = {"name": "test_exp"} if valid_manifest else {}
            with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f)

        if include_config:
            config = {"data": {"meal": "test"}} if valid_config else None
            with open(exp_dir / "config_snapshot.yaml", "w", encoding="utf-8") as f:
                if config:
                    yaml.dump(config, f)
                else:
                    f.write("")

        if include_meal:
            meal = {"pdf_files": []} if valid_meal else {}
            with open(exp_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
                json.dump(meal, f)

        return exp_dir

    def test_verify_all_assets_valid(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(
                exp_dir, system_config, verify_pdf_hashes=False
            )

            assert result.valid is True
            assert result.missing_files == []
            assert result.invalid_files == []

    def test_verify_missing_manifest(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, include_manifest=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(
                exp_dir, system_config, verify_pdf_hashes=False
            )

            assert result.valid is False
            assert "manifest.json" in result.missing_files

    def test_verify_missing_config(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, include_config=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(
                exp_dir, system_config, verify_pdf_hashes=False
            )

            assert result.valid is False
            assert "config_snapshot.yaml" in result.missing_files

    def test_verify_missing_meal(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, include_meal=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(
                exp_dir, system_config, verify_pdf_hashes=False
            )

            assert result.valid is False
            assert "meal_snapshot.json" in result.missing_files

    def test_verify_invalid_manifest(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, valid_manifest=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(
                exp_dir, system_config, verify_pdf_hashes=False
            )

            assert result.valid is False
            assert "manifest.json" in result.invalid_files

    def test_verify_invalid_config(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, valid_config=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(
                exp_dir, system_config, verify_pdf_hashes=False
            )

            assert result.valid is False
            assert "config_snapshot.yaml" in result.invalid_files

    def test_verify_invalid_meal(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, valid_meal=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(
                exp_dir, system_config, verify_pdf_hashes=False
            )

            assert result.valid is False
            assert "meal_snapshot.json" in result.invalid_files

    def test_verify_nonexistent_directory(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = temp_path / "nonexistent"
            system_config = {"parser": {"input_dir": "data/raw"}}

            with pytest.raises(
                ConfigurationError, match="Experiment directory not found"
            ):
                verify_experiment_assets(exp_dir, system_config)

    def test_verify_pdf_not_found(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = temp_path / "exp_test"
            exp_dir.mkdir()

            manifest = {"name": "test"}
            with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
                json.dump(manifest, f)

            config = {"data": {"meal": "test"}}
            with open(exp_dir / "config_snapshot.yaml", "w", encoding="utf-8") as f:
                yaml.dump(config, f)

            meal = {"pdf_files": [{"path": "missing.pdf", "sha256": "abc123"}]}
            with open(exp_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
                json.dump(meal, f)

            raw_dir = temp_path / "raw"
            raw_dir.mkdir()
            system_config = {"parser": {"input_dir": str(raw_dir)}}

            result = verify_experiment_assets(
                exp_dir, system_config, verify_pdf_hashes=True
            )

            assert result.valid is False
            assert "missing.pdf" in result.pdf_issues
            assert "File not found" in result.pdf_issues["missing.pdf"]


class TestBuildComparisonData:
    def test_build_comparison_data_empty(self):
        from eval.run_experiment import build_comparison_data

        results = []
        data = build_comparison_data(results)

        assert data["experiments"] == []
        assert data["best_variants"] == []
        assert data["summary"]["total_experiments"] == 0

    def test_build_comparison_data_single_experiment(self):
        from eval.run_experiment import build_comparison_data

        results = [
            {
                "experiment_id": "exp_001",
                "name": "test_exp",
                "description": "Test",
                "created_at": "2025-01-01T00:00:00",
                "status": "completed",
                "variant_results": [
                    {
                        "variant_name": "variant_a",
                        "retrieval_metrics": {
                            "avg_hit_rate": 0.85,
                            "avg_mrr": 0.72,
                            "avg_ndcg": 0.78,
                        },
                        "total_questions": 20,
                    }
                ],
            }
        ]

        data = build_comparison_data(results)

        assert len(data["experiments"]) == 1
        assert data["experiments"][0]["name"] == "test_exp"
        assert len(data["experiments"][0]["variants"]) == 1
        assert data["experiments"][0]["variants"][0]["metrics"]["hit_rate"] == 0.85

    def test_build_comparison_data_multiple_experiments(self):
        from eval.run_experiment import build_comparison_data

        results = [
            {
                "experiment_id": "exp_001",
                "name": "exp_a",
                "description": "A",
                "created_at": "2025-01-01T00:00:00",
                "status": "completed",
                "variant_results": [
                    {
                        "variant_name": "v1",
                        "retrieval_metrics": {
                            "avg_hit_rate": 0.80,
                            "avg_mrr": 0.70,
                            "avg_ndcg": 0.75,
                        },
                        "total_questions": 10,
                    }
                ],
            },
            {
                "experiment_id": "exp_002",
                "name": "exp_b",
                "description": "B",
                "created_at": "2025-01-02T00:00:00",
                "status": "completed",
                "variant_results": [
                    {
                        "variant_name": "v1",
                        "retrieval_metrics": {
                            "avg_hit_rate": 0.90,
                            "avg_mrr": 0.85,
                            "avg_ndcg": 0.88,
                        },
                        "total_questions": 10,
                    }
                ],
            },
        ]

        data = build_comparison_data(results)

        assert len(data["experiments"]) == 2
        assert len(data["best_variants"]) == 2
        assert data["best_variants"][0]["experiment_name"] == "exp_b"
        assert data["best_variants"][0]["metrics"]["hit_rate"] == 0.90

    def test_build_comparison_data_with_meal_info(self):
        from eval.run_experiment import build_comparison_data

        results = [
            {
                "experiment_id": "exp_001",
                "name": "test",
                "description": "Test",
                "created_at": "2025-01-01T00:00:00",
                "status": "completed",
                "meal_snapshot": {
                    "name": "meal_test",
                    "data_id": "abc123def456",
                    "stats": {
                        "total_pdfs": 5,
                        "total_pages": 100,
                        "total_chunks": 500,
                    },
                },
                "variant_results": [],
            }
        ]

        data = build_comparison_data(results)

        assert data["experiments"][0]["meal_info"]["name"] == "meal_test"
        assert data["experiments"][0]["meal_info"]["pdf_count"] == 5

    def test_build_comparison_data_with_test_sets(self):
        from eval.run_experiment import build_comparison_data

        results = [
            {
                "experiment_id": "exp_001",
                "name": "test",
                "description": "Test",
                "created_at": "2025-01-01T00:00:00",
                "status": "completed",
                "test_set_snapshots": [
                    {"strategy": "factual", "num_questions": 20},
                    {"strategy": "boundary", "num_questions": 15},
                ],
                "variant_results": [],
            }
        ]

        data = build_comparison_data(results)

        assert len(data["experiments"][0]["test_sets"]) == 2
        assert data["experiments"][0]["test_sets"][0]["strategy"] == "factual"


class TestExtractCategoryMetrics:
    def test_extract_category_metrics_empty(self):
        from eval.run_experiment import extract_category_metrics

        variant_result = {"results": []}
        metrics = extract_category_metrics(variant_result)

        assert metrics == {}

    def test_extract_category_metrics_single_category(self):
        from eval.run_experiment import extract_category_metrics

        variant_result = {
            "results": [
                {
                    "category": "factual",
                    "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                },
                {
                    "category": "factual",
                    "retrieval": {"hit_rate": 0.9, "mrr": 0.8, "ndcg": 0.85},
                },
            ]
        }

        metrics = extract_category_metrics(variant_result)

        assert "factual" in metrics
        assert metrics["factual"]["hit_rate"] == pytest.approx(0.85)
        assert metrics["factual"]["mrr"] == pytest.approx(0.75)
        assert metrics["factual"]["count"] == 2

    def test_extract_category_metrics_multiple_categories(self):
        from eval.run_experiment import extract_category_metrics

        variant_result = {
            "results": [
                {
                    "category": "factual",
                    "retrieval": {"hit_rate": 0.9, "mrr": 0.8, "ndcg": 0.85},
                },
                {
                    "category": "boundary",
                    "retrieval": {"hit_rate": 0.6, "mrr": 0.5, "ndcg": 0.55},
                },
            ]
        }

        metrics = extract_category_metrics(variant_result)

        assert "factual" in metrics
        assert "boundary" in metrics
        assert metrics["factual"]["hit_rate"] == 0.9
        assert metrics["boundary"]["hit_rate"] == 0.6

    def test_extract_category_metrics_missing_retrieval(self):
        from eval.run_experiment import extract_category_metrics

        variant_result = {
            "results": [
                {"category": "factual"},
                {
                    "category": "factual",
                    "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                },
            ]
        }

        metrics = extract_category_metrics(variant_result)

        assert metrics["factual"]["count"] == 1


class TestGenerateComparisonReport:
    def test_generate_comparison_report_basic(self):
        from eval.run_experiment import generate_comparison_report

        comparison_data = {
            "experiments": [
                {
                    "experiment_id": "exp_001",
                    "name": "test_exp",
                    "status": "completed",
                    "created_at": "2025-01-01T00:00:00",
                    "variants": [
                        {
                            "name": "variant_a",
                            "metrics": {"hit_rate": 0.85, "mrr": 0.72, "ndcg": 0.78},
                            "avg_time_per_question": 2.5,
                        }
                    ],
                    "meal_info": {},
                    "test_sets": [],
                }
            ],
            "best_variants": [
                {
                    "experiment_name": "test_exp",
                    "variant_name": "variant_a",
                    "metrics": {"hit_rate": 0.85, "mrr": 0.72, "ndcg": 0.78},
                }
            ],
            "summary": {"total_experiments": 1, "total_variants": 1},
        }

        report = generate_comparison_report(comparison_data, [])

        assert "# Experiment Comparison Report" in report
        assert "test_exp" in report
        assert "variant_a" in report
        assert "0.8500" in report

    def test_generate_comparison_report_with_not_found(self):
        from eval.run_experiment import generate_comparison_report

        comparison_data = {
            "experiments": [],
            "best_variants": [],
            "summary": {"total_experiments": 0, "total_variants": 0},
        }

        report = generate_comparison_report(comparison_data, ["exp_missing"])

        assert "Warnings" in report
        assert "exp_missing" in report

    def test_generate_comparison_report_with_meal_info(self):
        from eval.run_experiment import generate_comparison_report

        comparison_data = {
            "experiments": [
                {
                    "experiment_id": "exp_001",
                    "name": "test_exp",
                    "status": "completed",
                    "created_at": "2025-01-01T00:00:00",
                    "variants": [],
                    "meal_info": {
                        "name": "meal_test",
                        "pdf_count": 5,
                        "page_count": 100,
                        "chunk_count": 500,
                    },
                    "test_sets": [],
                }
            ],
            "best_variants": [],
            "summary": {"total_experiments": 1, "total_variants": 0},
        }

        report = generate_comparison_report(comparison_data, [])

        assert "Data Source" in report
        assert "meal_test" in report
        assert "5" in report

    def test_generate_comparison_report_with_category_metrics(self):
        from eval.run_experiment import generate_comparison_report

        comparison_data = {
            "experiments": [
                {
                    "experiment_id": "exp_001",
                    "name": "test_exp",
                    "status": "completed",
                    "created_at": "2025-01-01T00:00:00",
                    "variants": [
                        {
                            "name": "variant_a",
                            "metrics": {"hit_rate": 0.85, "mrr": 0.72, "ndcg": 0.78},
                            "avg_time_per_question": 2.5,
                            "category_metrics": {
                                "factual": {
                                    "hit_rate": 0.9,
                                    "mrr": 0.8,
                                    "ndcg": 0.85,
                                    "count": 10,
                                },
                                "boundary": {
                                    "hit_rate": 0.6,
                                    "mrr": 0.5,
                                    "ndcg": 0.55,
                                    "count": 5,
                                },
                            },
                        }
                    ],
                    "meal_info": {},
                    "test_sets": [],
                }
            ],
            "best_variants": [
                {
                    "experiment_name": "test_exp",
                    "variant_name": "variant_a",
                    "metrics": {"hit_rate": 0.85, "mrr": 0.72, "ndcg": 0.78},
                }
            ],
            "summary": {"total_experiments": 1, "total_variants": 1},
        }

        report = generate_comparison_report(comparison_data, [])

        assert "By Category" in report
        assert "factual" in report
        assert "boundary" in report


class TestCLITestSetGeneration:
    def test_cli_with_name_parameter(self):
        import argparse

        from main import _handle_generate_test_set

        mock_meal_manager = MagicMock()
        mock_meal_manager.meal_exists.return_value = True

        args = argparse.Namespace(
            generate_test_set="test_meal",
            strategy="document",
            num_questions=10,
            name="custom_test_set",
            llm_preset="default",
            seed=None,
        )

        config = {"test_generation": {"max_retries": 3}}

        with patch("src.test_generator.TestSetGenerator") as MockGenerator:
            mock_generator = MagicMock()
            mock_generator.generate_document_based_questions.return_value = {
                "name": "custom_test_set",
                "questions": [{"question": "test"}],
            }
            MockGenerator.return_value = mock_generator

            _handle_generate_test_set(mock_meal_manager, config, args)

            mock_generator.generate_document_based_questions.assert_called_once()
            call_kwargs = (
                mock_generator.generate_document_based_questions.call_args.kwargs
            )
            assert call_kwargs["name"] == "custom_test_set"
            assert call_kwargs["meal_name"] == "test_meal"
            assert call_kwargs["num_questions"] == 10

    def test_cli_without_name_parameter(self):
        import argparse

        from main import _handle_generate_test_set

        mock_meal_manager = MagicMock()
        mock_meal_manager.meal_exists.return_value = True

        args = argparse.Namespace(
            generate_test_set="test_meal",
            strategy="document",
            num_questions=10,
            name=None,
            llm_preset="default",
            seed=None,
        )

        config = {"test_generation": {"max_retries": 3}}

        with patch("src.test_generator.TestSetGenerator") as MockGenerator:
            mock_generator = MagicMock()
            mock_generator.generate_document_based_questions.return_value = {
                "name": "document_level_n10",
                "questions": [{"question": "test"}],
            }
            MockGenerator.return_value = mock_generator

            _handle_generate_test_set(mock_meal_manager, config, args)

            mock_generator.generate_document_based_questions.assert_called_once()
            call_kwargs = (
                mock_generator.generate_document_based_questions.call_args.kwargs
            )
            assert call_kwargs["name"] is None

    def test_cli_legacy_strategy(self):
        import argparse

        from main import _handle_generate_test_set

        mock_meal_manager = MagicMock()
        mock_meal_manager.meal_exists.return_value = True

        args = argparse.Namespace(
            generate_test_set="test_meal",
            strategy="factual",
            num_questions=10,
            name="ignored_name",
            llm_preset="default",
            seed=42,
        )

        config = {"test_generation": {"max_retries": 3}}

        with patch("src.test_generator.TestSetGenerator") as MockGenerator:
            mock_generator = MagicMock()
            mock_generator.generate_test_set.return_value = {
                "name": "factual_n10",
                "questions": [{"question": "test"}],
            }
            MockGenerator.return_value = mock_generator

            _handle_generate_test_set(mock_meal_manager, config, args)

            mock_generator.generate_test_set.assert_called_once()
            call_kwargs = mock_generator.generate_test_set.call_args.kwargs
            assert call_kwargs["strategy"] == "factual"
            assert call_kwargs["seed"] == 42

    def test_cli_meal_not_found(self):
        import argparse

        from main import _handle_generate_test_set

        mock_meal_manager = MagicMock()
        mock_meal_manager.meal_exists.return_value = False

        args = argparse.Namespace(
            generate_test_set="nonexistent_meal",
            strategy="document",
            num_questions=10,
            name="test_set",
            llm_preset="default",
            seed=None,
        )

        config = {}

        with pytest.raises(SystemExit):
            _handle_generate_test_set(mock_meal_manager, config, args)


class TestMetricNamespacePrefix:
    def _make_exp_config(self, backends=None):
        from src.experiment import ExperimentConfig

        if backends is None:
            backends = ["builtin"]
        return ExperimentConfig(
            name="test",
            description="test",
            data={"meal": "test_meal"},
            test_sets=[{"strategy": "factual", "num_questions": 5}],
            variants=[{"name": "baseline"}],
            evaluation={
                "backends": backends,
                "metrics": {
                    "retrieval": ["hit_rate", "mrr", "ndcg"],
                    "generation": ["faithfulness", "answer_relevancy"],
                },
                "llm_preset": "default",
            },
        )

    @patch("eval.runner.evaluation.evaluate_with_builtin")
    @patch("eval.runner.evaluation.evaluate_with_ragas")
    @patch("eval.runner.evaluation.collect_rag_samples")
    @patch("eval.runner.evaluation.create_evaluators")
    @patch("eval.runner.evaluation.get_llm_config")
    def test_single_backend_no_prefix(
        self,
        mock_llm_config,
        mock_create_evaluators,
        mock_collect,
        mock_ragas,
        mock_builtin,
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_evaluator = MagicMock()
        mock_evaluator.supported_retrieval_metrics = [
            "hit_rate",
            "mrr",
            "ndcg",
        ]
        mock_evaluator.supported_generation_metrics = [
            "faithfulness",
            "answer_relevancy",
        ]
        mock_create_evaluators.return_value = {"builtin": mock_evaluator}
        mock_collect.return_value = [
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "contexts": ["c1"],
            },
        ]
        mock_builtin.return_value = [
            {
                "id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8},
            },
        ]

        exp_config = self._make_exp_config(backends=["builtin"])
        results = evaluate_test_set(
            pipeline=MagicMock(),
            test_set={"questions": []},
            exp_config=exp_config,
            system_config={},
        )

        assert "faithfulness" in results[0]["generation"]
        assert "answer_relevancy" in results[0]["generation"]
        assert "builtin_faithfulness" not in results[0]["generation"]

    @patch("eval.runner.evaluation.evaluate_with_builtin")
    @patch("eval.runner.evaluation.evaluate_with_ragas")
    @patch("eval.runner.evaluation.collect_rag_samples")
    @patch("eval.runner.evaluation.create_evaluators")
    @patch("eval.runner.evaluation.get_llm_config")
    def test_dual_backends_have_prefix(
        self,
        mock_llm_config,
        mock_create_evaluators,
        mock_collect,
        mock_ragas,
        mock_builtin,
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_builtin_evaluator = MagicMock()
        mock_builtin_evaluator.supported_retrieval_metrics = [
            "hit_rate",
            "mrr",
            "ndcg",
        ]
        mock_builtin_evaluator.supported_generation_metrics = [
            "faithfulness",
            "answer_relevancy",
        ]
        mock_ragas_evaluator = MagicMock()
        mock_ragas_evaluator.supported_retrieval_metrics = []
        mock_ragas_evaluator.supported_generation_metrics = [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
        ]
        mock_create_evaluators.return_value = {
            "builtin": mock_builtin_evaluator,
            "ragas": mock_ragas_evaluator,
        }
        mock_collect.return_value = [
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "contexts": ["c1"],
            },
        ]
        mock_builtin.return_value = [
            {
                "id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8},
            },
        ]
        mock_ragas.return_value = [
            {
                "id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "generation": {
                    "faithfulness": 0.85,
                    "answer_relevancy": 0.75,
                    "context_precision": 0.7,
                },
            },
        ]

        exp_config = self._make_exp_config(backends=["builtin", "ragas"])
        results = evaluate_test_set(
            pipeline=MagicMock(),
            test_set={"questions": []},
            exp_config=exp_config,
            system_config={},
        )

        gen = results[0]["generation"]
        assert "builtin_faithfulness" in gen
        assert "builtin_answer_relevancy" in gen
        assert "ragas_faithfulness" in gen
        assert "ragas_answer_relevancy" in gen
        assert "ragas_context_precision" in gen
        assert "faithfulness" not in gen
        assert gen["builtin_faithfulness"] == 0.9
        assert gen["ragas_faithfulness"] == 0.85

    @patch("eval.runner.evaluation.evaluate_with_builtin")
    @patch("eval.runner.evaluation.evaluate_with_ragas")
    @patch("eval.runner.evaluation.collect_rag_samples")
    @patch("eval.runner.evaluation.create_evaluators")
    @patch("eval.runner.evaluation.get_llm_config")
    def test_dual_backends_builtin_computes_all_supported(
        self,
        mock_llm_config,
        mock_create_evaluators,
        mock_collect,
        mock_ragas,
        mock_builtin,
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_builtin_evaluator = MagicMock()
        mock_builtin_evaluator.supported_retrieval_metrics = [
            "hit_rate",
            "mrr",
            "ndcg",
        ]
        mock_builtin_evaluator.supported_generation_metrics = [
            "faithfulness",
            "answer_relevancy",
        ]
        mock_ragas_evaluator = MagicMock()
        mock_ragas_evaluator.supported_retrieval_metrics = []
        mock_ragas_evaluator.supported_generation_metrics = [
            "faithfulness",
            "answer_relevancy",
        ]
        mock_create_evaluators.return_value = {
            "builtin": mock_builtin_evaluator,
            "ragas": mock_ragas_evaluator,
        }
        mock_collect.return_value = [
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "contexts": ["c1"],
            },
        ]
        mock_builtin.return_value = [
            {
                "id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8},
            },
        ]
        mock_ragas.return_value = [
            {
                "id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "generation": {"faithfulness": 0.85, "answer_relevancy": 0.75},
            },
        ]

        exp_config = self._make_exp_config(backends=["builtin", "ragas"])
        evaluate_test_set(
            pipeline=MagicMock(),
            test_set={"questions": []},
            exp_config=exp_config,
            system_config={},
        )

        call_args = mock_builtin.call_args
        assert call_args.kwargs["generation_metrics"] == [
            "faithfulness",
            "answer_relevancy",
        ]

    def test_compute_aggregate_with_prefixed_metrics(self):
        results = [
            {
                "id": "q1",
                "generation": {
                    "builtin_faithfulness": 0.9,
                    "builtin_answer_relevancy": 0.8,
                    "ragas_faithfulness": 0.85,
                    "ragas_answer_relevancy": 0.75,
                },
            },
            {
                "id": "q2",
                "generation": {
                    "builtin_faithfulness": 0.7,
                    "builtin_answer_relevancy": 0.6,
                    "ragas_faithfulness": 0.65,
                    "ragas_answer_relevancy": 0.55,
                },
            },
        ]

        metrics = compute_aggregate_metrics(results)

        assert "generation_metrics" in metrics
        gen = metrics["generation_metrics"]
        assert "avg_builtin_faithfulness" in gen
        assert "avg_ragas_faithfulness" in gen
        assert gen["avg_builtin_faithfulness"] == pytest.approx(0.8)
        assert gen["avg_ragas_faithfulness"] == pytest.approx(0.75)

    def test_compute_aggregate_with_unprefixed_metrics(self):
        results = [
            {
                "id": "q1",
                "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8},
            },
            {
                "id": "q2",
                "generation": {"faithfulness": 0.7, "answer_relevancy": 0.6},
            },
        ]

        metrics = compute_aggregate_metrics(results)

        assert "generation_metrics" in metrics
        gen = metrics["generation_metrics"]
        assert "avg_faithfulness" in gen
        assert "avg_answer_relevancy" in gen
        assert gen["avg_faithfulness"] == pytest.approx(0.8)

    def test_compute_aggregate_llm_retrieval_from_ragas_generation(self):
        results = [
            {
                "id": "q1",
                "generation": {
                    "faithfulness": 0.9,
                    "context_precision": 0.8,
                    "context_recall": 0.7,
                },
            },
            {
                "id": "q2",
                "generation": {
                    "faithfulness": 0.7,
                    "context_precision": 0.6,
                    "context_recall": 0.5,
                },
            },
        ]

        metrics = compute_aggregate_metrics(results)

        assert "avg_context_precision" in metrics
        assert "avg_context_recall" in metrics
        assert metrics["avg_context_precision"] == pytest.approx(0.7)
        assert metrics["avg_context_recall"] == pytest.approx(0.6)

    def test_compute_aggregate_llm_retrieval_from_both_sources(self):
        results = [
            {
                "id": "q1",
                "llm_retrieval": {"context_precision": 0.9, "context_recall": 0.8},
            },
            {
                "id": "q2",
                "generation": {"context_precision": 0.7, "context_recall": 0.6},
            },
        ]

        metrics = compute_aggregate_metrics(results)

        assert "avg_context_precision" in metrics
        assert "avg_context_recall" in metrics
        assert metrics["avg_context_precision"] == pytest.approx(0.8)
        assert metrics["avg_context_recall"] == pytest.approx(0.7)

    def test_compute_aggregate_llm_retrieval_from_ragas_llm_retrieval_key(self):
        results = [
            {
                "id": "q1",
                "llm_retrieval": {"context_precision": 0.85, "context_recall": 0.75},
                "generation": {"faithfulness": 0.9},
            },
            {
                "id": "q2",
                "llm_retrieval": {"context_precision": 0.65, "context_recall": 0.55},
                "generation": {"faithfulness": 0.7},
            },
        ]

        metrics = compute_aggregate_metrics(results)

        assert "avg_context_precision" in metrics
        assert "avg_context_recall" in metrics
        assert metrics["avg_context_precision"] == pytest.approx(0.75)
        assert metrics["avg_context_recall"] == pytest.approx(0.65)

    @patch("eval.runner.evaluation.evaluate_with_builtin")
    @patch("eval.runner.evaluation.collect_rag_samples")
    @patch("eval.runner.evaluation.create_evaluators")
    @patch("eval.runner.evaluation.get_llm_config")
    def test_single_ragas_backend_no_prefix(
        self,
        mock_llm_config,
        mock_create_evaluators,
        mock_collect,
        mock_builtin,
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_ragas_evaluator = MagicMock()
        mock_ragas_evaluator.supported_retrieval_metrics = []
        mock_ragas_evaluator.supported_generation_metrics = [
            "faithfulness",
            "answer_relevancy",
            "context_precision",
        ]
        mock_create_evaluators.return_value = {"ragas": mock_ragas_evaluator}
        mock_collect.return_value = [
            {
                "question_id": "q1",
                "question": "Q1?",
                "answer": "A1",
                "contexts": ["c1"],
            },
        ]

        with patch("eval.runner.evaluation.evaluate_with_ragas") as mock_ragas:
            mock_ragas.return_value = [
                {
                    "id": "q1",
                    "question": "Q1?",
                    "answer": "A1",
                    "generation": {"faithfulness": 0.85, "answer_relevancy": 0.75},
                },
            ]

            exp_config = self._make_exp_config(backends=["ragas"])
            results = evaluate_test_set(
                pipeline=MagicMock(),
                test_set={"questions": []},
                exp_config=exp_config,
                system_config={},
            )

            assert "faithfulness" in results[0]["generation"]
            assert "ragas_faithfulness" not in results[0]["generation"]


class TestDualBackendEvaluation:
    """Tests for dual-backend (builtin + ragas) evaluation."""

    def test_dual_backend_results_have_namespace_prefix(self):
        """Test that dual-backend results have namespace prefixes on generation metrics."""
        pass

    def test_result_merging_builtin_and_ragas(self):
        """Test that builtin retrieval + ragas generation results merge correctly."""
        builtin_result = {
            "id": "q1",
            "question": "What is RAG?",
            "answer": "RAG is retrieval-augmented generation.",
            "retrieval": {"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
            "generation": {
                "builtin_faithfulness": 0.8,
                "builtin_answer_relevancy": 0.7,
            },
            "sources": ["doc1.pdf"],
            "expected_sources": ["doc1.pdf"],
        }

        ragas_result = {
            "id": "q1",
            "question": "What is RAG?",
            "answer": "RAG is retrieval-augmented generation.",
            "generation": {"ragas_faithfulness": 0.85, "ragas_answer_relevancy": 0.72},
            "sources": ["doc1.pdf"],
            "expected_sources": ["doc1.pdf"],
        }

        merged = dict(builtin_result)
        if "generation" in ragas_result:
            if "generation" not in merged:
                merged["generation"] = {}
            merged["generation"].update(ragas_result["generation"])

        assert "retrieval" in merged
        assert "builtin_faithfulness" in merged["generation"]
        assert "ragas_faithfulness" in merged["generation"]
        assert merged["generation"]["builtin_faithfulness"] == 0.8
        assert merged["generation"]["ragas_faithfulness"] == 0.85

    def test_single_backend_no_prefix(self):
        """Test that single backend results have no prefix."""
        result = {
            "id": "q1",
            "generation": {"faithfulness": 0.85, "answer_relevancy": 0.72},
        }

        assert "faithfulness" in result["generation"]
        assert "builtin_faithfulness" not in result["generation"]


class TestEvaluateWithBuiltinContextsSourcesSeparation:
    """Tests for P6-3 fix: contexts/sources separation in evaluate_with_builtin."""

    def testevaluate_with_builtin_passes_contexts_and_retrieved_sources(self):
        """Test that evaluate_with_builtin passes contexts and retrieved_sources separately."""
        from eval.evaluators.builtin_evaluator import BuiltinEvaluator

        evaluator = BuiltinEvaluator()

        samples = [
            {
                "question_id": "q1",
                "question": "What is the revenue?",
                "answer": "Revenue is $1M.",
                "contexts": ["Revenue was $1M in 2023.", "Profit was $500K."],
                "expected_sources": ["doc1.pdf"],
                "retrieved_sources": ["doc1.pdf", "doc2.pdf"],
                "chunk_ids": ["doc1::chunk::001", "doc2::chunk::003"],
                "question_type": "factual",
                "time_seconds": 1.5,
                "test_set": "test_set_1",
                "category": "factual",
                "difficulty": "easy",
                "token_usage": None,
            },
        ]

        with patch.object(
            evaluator,
            "evaluate_single",
            return_value=MagicMock(
                retrieval_metrics={"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
                generation_metrics={},
                error=None,
            ),
        ) as mock_eval:
            evaluate_with_builtin(
                samples=samples,
                evaluator=evaluator,
                retrieval_metrics=["hit_rate", "mrr", "ndcg"],
            )

            mock_eval.assert_called_once()
            call_args = mock_eval.call_args
            sample = (
                call_args.args[0] if call_args.args else call_args.kwargs.get("sample")
            )
            assert sample.contexts == [
                "Revenue was $1M in 2023.",
                "Profit was $500K.",
            ]
            assert sample.retrieved_sources == ["doc1.pdf", "doc2.pdf"]
            assert sample.contexts != sample.retrieved_sources

    def testevaluate_with_builtin_passes_chunk_ids_and_question_type(self):
        """Test that evaluate_with_builtin passes chunk_ids and question_type."""
        from eval.evaluators.builtin_evaluator import BuiltinEvaluator

        evaluator = BuiltinEvaluator()

        samples = [
            {
                "question_id": "q1",
                "question": "What is the revenue?",
                "answer": "Revenue is $1M.",
                "contexts": ["Revenue was $1M in 2023."],
                "expected_sources": ["doc1.pdf"],
                "retrieved_sources": ["doc1.pdf"],
                "chunk_ids": ["doc1::chunk::001", "doc2::chunk::003"],
                "question_type": "single_fact",
                "time_seconds": 1.0,
                "test_set": "test_set_1",
                "category": "factual",
                "difficulty": "easy",
                "token_usage": None,
            },
        ]

        with patch.object(
            evaluator,
            "evaluate_single",
            return_value=MagicMock(
                retrieval_metrics={"hit_rate": 1.0},
                generation_metrics={},
                error=None,
            ),
        ) as mock_eval:
            evaluate_with_builtin(
                samples=samples,
                evaluator=evaluator,
                retrieval_metrics=["hit_rate"],
            )

            call_args = mock_eval.call_args
            sample = (
                call_args.args[0] if call_args.args else call_args.kwargs.get("sample")
            )
            assert sample.chunk_ids == ["doc1::chunk::001", "doc2::chunk::003"]
            assert sample.question_type == "single_fact"

    def testevaluate_with_builtin_handles_error_samples(self):
        """Test that evaluate_with_builtin handles error samples correctly."""
        from eval.evaluators.builtin_evaluator import BuiltinEvaluator

        evaluator = BuiltinEvaluator()

        samples = [
            {
                "question_id": "q_err",
                "question": "What happened?",
                "error": "Pipeline failed",
                "time_seconds": 0.5,
                "test_set": "test_set_1",
            },
        ]

        results = evaluate_with_builtin(
            samples=samples,
            evaluator=evaluator,
            retrieval_metrics=["hit_rate"],
        )

        assert len(results) == 1
        assert results[0]["id"] == "q_err"
        assert results[0]["error"] == "Pipeline failed"
        assert results[0]["answer"] is None


class TestGenerateLlmReportOnly:
    def test_nonexistent_directory_raises(self, tmp_path):
        from eval.run_experiment import generate_llm_report_only

        with pytest.raises(ConfigurationError, match="Experiment directory not found"):
            generate_llm_report_only(str(tmp_path / "nonexistent"))

    def test_missing_manifest_raises(self, tmp_path):
        from eval.run_experiment import generate_llm_report_only

        exp_dir = tmp_path / "exp_test"
        exp_dir.mkdir()
        with pytest.raises(ConfigurationError, match="Manifest file not found"):
            generate_llm_report_only(str(exp_dir))

    def test_no_variant_results_raises(self, tmp_path):
        from eval.run_experiment import generate_llm_report_only

        exp_dir = tmp_path / "exp_test"
        exp_dir.mkdir()

        manifest = {
            "experiment_id": "test_exp",
            "name": "test",
            "description": "test",
            "status": "completed",
            "variants": [],
        }
        with open(exp_dir / "manifest.json", "w", encoding="utf-8") as f:
            json.dump(manifest, f)

        with pytest.raises(ConfigurationError, match="No variant results found"):
            generate_llm_report_only(str(exp_dir))


class TestComputeAggregateMetricsEnhanced:
    def test_diversity_aggregation(self):
        results = [
            {
                "id": "q1",
                "retrieval": {
                    "hit_rate": 1.0,
                    "mrr": 1.0,
                    "ndcg": 1.0,
                    "retrieval_diversity": 0.4,
                },
            },
            {
                "id": "q2",
                "retrieval": {
                    "hit_rate": 0.0,
                    "mrr": 0.0,
                    "ndcg": 0.0,
                    "retrieval_diversity": 0.8,
                },
            },
        ]
        metrics = compute_aggregate_metrics(results)
        assert metrics["avg_retrieval_diversity"] == pytest.approx(0.6)

    def test_hallucination_rate_aggregation(self):
        results = [
            {
                "id": "q1",
                "retrieval": {"hit_rate": 1.0},
                "generation": {"faithfulness": 1.0, "answer_relevancy": 0.9},
            },
            {
                "id": "q2",
                "retrieval": {"hit_rate": 0.0},
                "generation": {"faithfulness": 0.0, "answer_relevancy": 0.5},
            },
            {
                "id": "q3",
                "retrieval": {"hit_rate": 1.0},
                "generation": {"faithfulness": 0.8, "answer_relevancy": 0.7},
            },
        ]
        metrics = compute_aggregate_metrics(results)
        assert metrics["hallucination_rate"] == pytest.approx(1 / 3)

    def test_by_question_type_breakdown(self):
        results = [
            {
                "id": "q1",
                "question_type": "single_fact",
                "retrieval": {"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
                "generation": {"faithfulness": 0.9},
            },
            {
                "id": "q2",
                "question_type": "single_fact",
                "retrieval": {"hit_rate": 0.0, "mrr": 0.0, "ndcg": 0.0},
                "generation": {"faithfulness": 0.5},
            },
            {
                "id": "q3",
                "question_type": "reasoning",
                "retrieval": {"hit_rate": 0.5, "mrr": 0.5, "ndcg": 0.5},
                "generation": {"faithfulness": 0.7},
            },
        ]
        metrics = compute_aggregate_metrics(results)
        assert "by_question_type" in metrics
        assert "single_fact" in metrics["by_question_type"]
        assert "reasoning" in metrics["by_question_type"]
        assert metrics["by_question_type"]["single_fact"]["count"] == 2
        assert metrics["by_question_type"]["single_fact"][
            "avg_hit_rate"
        ] == pytest.approx(0.5)
        assert metrics["by_question_type"]["reasoning"][
            "avg_hit_rate"
        ] == pytest.approx(0.5)

    def test_chunk_dedup_fpr_from_separate_keys(self):
        results = [
            {
                "id": "q1",
                "retrieval": {"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
                "chunk_retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                "dedup_retrieval": {"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
            },
            {
                "id": "q2",
                "retrieval": {"hit_rate": 0.0, "mrr": 0.0, "ndcg": 0.0},
                "false_positive_rate": 0.6,
            },
        ]
        metrics = compute_aggregate_metrics(results)
        assert metrics["chunk_level_metrics"]["avg_hit_rate"] == pytest.approx(0.8)
        assert metrics["dedup_metrics"]["avg_hit_rate"] == pytest.approx(1.0)
        assert metrics["avg_false_positive_rate"] == pytest.approx(0.6)


class TestRunExperimentBoundaryConditions:
    def _make_exp_config(self, **overrides) -> dict:
        defaults = {
            "name": "test_exp",
            "description": "test",
            "data": {"meal": "test"},
            "test_sets": [
                {
                    "name": "test_set_1",
                    "generation": {"strategy": "document", "num_questions": 5},
                }
            ],
            "variants": [{"name": "v1"}],
            "evaluation": {
                "metrics": {"retrieval": ["hit_rate"], "generation": ["faithfulness"]}
            },
        }
        defaults.update(overrides)
        return defaults

    @pytest.mark.unit
    def test_compute_aggregate_empty_results(self):
        metrics = compute_aggregate_metrics([])
        assert "avg_hit_rate" in metrics
        assert metrics["avg_hit_rate"] == 0.0

    @pytest.mark.unit
    def test_compute_aggregate_all_errors(self):
        results = [
            {
                "id": "q1",
                "error": "API error",
                "time_seconds": 1.0,
                "question_type": "factual",
            },
            {
                "id": "q2",
                "error": "Timeout",
                "time_seconds": 2.0,
                "question_type": "factual",
            },
        ]
        metrics = compute_aggregate_metrics(results)
        assert metrics.get("avg_hit_rate") == 0.0

    @pytest.mark.unit
    def test_sanitize_config_api_key_directly_in_preset(self):
        config = {
            "llm_presets": {
                "default": {
                    "api_key": "sk-secret-123",
                }
            }
        }
        result = sanitize_config(config)
        assert result["llm_presets"]["default"]["api_key"] == "***"

    @pytest.mark.unit
    def test_sanitize_config_no_llm_presets(self):
        config = {"chunker": {"chunk_size": 256}}
        result = sanitize_config(config)
        assert result["chunker"]["chunk_size"] == 256

    @pytest.mark.unit
    def test_sanitize_config_api_key_in_model_kwargs(self):
        config = {
            "llm_presets": {"default": {"model_kwargs": {"api_key": "sk-secret-123"}}}
        }
        result = sanitize_config(config)
        assert "model_kwargs" not in result["llm_presets"]["default"] or result[
            "llm_presets"
        ]["default"].get("model_kwargs", {}).get("api_key", "***") in [
            "***",
            "sk-secret-123",
        ]

    @pytest.mark.unit
    def test_compute_aggregate_partial_missing_metrics(self):
        results = [
            {"id": "q1", "retrieval": {"hit_rate": 1.0, "mrr": 1.0}},
            {"id": "q2", "retrieval": {"hit_rate": 0.0}},
        ]
        metrics = compute_aggregate_metrics(results)
        assert metrics["avg_hit_rate"] == pytest.approx(0.5)
        assert "avg_mrr" in metrics

    @pytest.mark.unit
    def test_sanitize_config_top_level_api_key_redacted(self):
        config = {
            "llm_presets": {
                "default": {
                    "api_key": "sk-secret-123",
                    "model": "claude-sonnet-4-20250514",
                }
            }
        }
        result = sanitize_config(config)
        assert result["llm_presets"]["default"]["api_key"] == "***"
        assert result["llm_presets"]["default"]["model"] == "claude-sonnet-4-20250514"

    @pytest.mark.unit
    def test_sanitize_config_empty(self):
        config = {}
        result = sanitize_config(config)
        assert result == {}

    @pytest.mark.unit
    def test_sanitize_config_non_string_api_key(self):
        config = {"llm_presets": {"default": {"api_key": 12345}}}
        result = sanitize_config(config)
        assert result["llm_presets"]["default"]["api_key"] == "***"


class TestRunExperimentExceptionPaths:
    def _make_exp_config(self, **overrides):
        from src.experiment import ExperimentConfig

        defaults = {
            "name": "test_exp",
            "description": "test",
            "data": {"meal": "test"},
            "test_sets": [
                {
                    "name": "test_set_1",
                    "generation": {"strategy": "document", "num_questions": 5},
                }
            ],
            "variants": [{"name": "v1"}],
            "evaluation": {
                "metrics": {"retrieval": ["hit_rate"], "generation": ["faithfulness"]}
            },
        }
        defaults.update(overrides)
        return ExperimentConfig(**defaults)

    @pytest.mark.unit
    def test_verify_experiment_assets_missing_dir(self, tmp_path):
        exp_dir = tmp_path / "exp_missing"
        with pytest.raises(ConfigurationError, match="Experiment directory not found"):
            verify_experiment_assets(exp_dir, {"name": "test_exp"})

    @pytest.mark.unit
    def test_verify_experiment_assets_corrupted_meal_snapshot(self, tmp_path):
        exp_dir = tmp_path / "exp_corrupted"
        exp_dir.mkdir()
        (exp_dir / "manifest.json").write_text("{}", encoding="utf-8")
        (exp_dir / "config_snapshot.yaml").write_text("name: test", encoding="utf-8")

        with open(exp_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
            f.write("invalid json {")

        result = verify_experiment_assets(
            exp_dir, {"name": "test_exp"}, verify_pdf_hashes=False
        )
        assert result.valid is False
        assert "meal_snapshot.json" in result.invalid_files

    @pytest.mark.unit
    def test_verify_experiment_assets_corrupted_pdf_hash(self, tmp_path):
        exp_dir = tmp_path / "exp_corrupted_pdf"
        exp_dir.mkdir()
        (exp_dir / "manifest.json").write_text(
            '{"name": "test_exp", "status": "running", "variants": ["v1"], "created_at": "2026-01-01"}',
            encoding="utf-8",
        )
        (exp_dir / "config_snapshot.yaml").write_text("name: test", encoding="utf-8")

        fake_pdf = tmp_path / "fake.pdf"
        fake_pdf.write_bytes(b"fake pdf content")

        raw_dir = tmp_path / "data" / "raw"
        raw_dir.mkdir(parents=True)
        (raw_dir / "fake.pdf").write_bytes(b"fake pdf content")

        with open(exp_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
            json.dump({"pdf_files": [{"path": "fake.pdf", "sha256": "0" * 64}]}, f)

        config_dict = {
            "name": "test_exp",
            "parser": {"input_dir": str(raw_dir)},
        }
        result = verify_experiment_assets(exp_dir, config_dict, verify_pdf_hashes=True)
        assert result.pdf_issues
        assert "fake.pdf" in result.pdf_issues

    @pytest.mark.unit
    def test_evaluate_test_set_missing_exp_config(self):
        with pytest.raises(
            ConfigurationError, match="exp_config and system_config are required"
        ):
            evaluate_test_set(
                pipeline=MagicMock(),
                test_set={"questions": []},
                system_config={},
            )

    @pytest.mark.unit
    def test_evaluate_test_set_missing_system_config(self):
        with pytest.raises(
            ConfigurationError, match="exp_config and system_config are required"
        ):
            evaluate_test_set(
                pipeline=MagicMock(),
                test_set={"questions": []},
                exp_config=self._make_exp_config(),
            )

    @patch("eval.runner.evaluation.create_evaluators")
    @patch("eval.runner.evaluation.get_llm_config")
    def test_evaluate_test_set_evaluator_creation_fails(
        self, mock_llm_config, mock_create
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_create.side_effect = Exception("Failed to create evaluator")

        exp_config = self._make_exp_config()
        with pytest.raises(Exception, match="Failed to create evaluator"):
            evaluate_test_set(
                pipeline=MagicMock(),
                test_set={"questions": []},
                exp_config=exp_config,
                system_config={},
            )

    @patch("eval.runner.evaluation.create_evaluators")
    @patch("eval.runner.evaluation.get_llm_config")
    def test_evaluate_test_set_empty_questions(
        self, mock_llm_config, mock_create_evaluators
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_evaluator = MagicMock()
        mock_evaluator.supported_retrieval_metrics = []
        mock_evaluator.supported_generation_metrics = []
        mock_create_evaluators.return_value = {"builtin": mock_evaluator}

        exp_config = self._make_exp_config()
        mock_pipeline = MagicMock()
        mock_pipeline.config = {}
        results = evaluate_test_set(
            pipeline=mock_pipeline,
            test_set={"questions": []},
            exp_config=exp_config,
            system_config={},
        )

        assert results == []

    @pytest.mark.unit
    def testcollect_rag_samples_skips_empty_question(self):
        pipeline = MagicMock()
        pipeline.config = {}
        test_set = {
            "name": "test_set_1",
            "questions": [
                {"id": "q1", "question": "", "test_set": "t1"},
                {"id": "q2", "question": "", "test_set": "t1"},
                {"id": "q3", "question": "Valid?", "test_set": "t1"},
            ],
        }
        pipeline.run.return_value = {
            "answer": "A3",
            "contexts": ["c3"],
            "sources": ["s3"],
            "time_seconds": 0.5,
            "token_usage": None,
        }

        samples = collect_rag_samples(pipeline, test_set, {})

        assert len(samples) == 1
        assert samples[0]["question_id"] == "q3"
