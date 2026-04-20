import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from eval.run_experiment import compute_aggregate_metrics, evaluate_test_set


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

            result = verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=False)

            assert result.valid is True
            assert result.missing_files == []
            assert result.invalid_files == []

    def test_verify_missing_manifest(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, include_manifest=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=False)

            assert result.valid is False
            assert "manifest.json" in result.missing_files

    def test_verify_missing_config(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, include_config=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=False)

            assert result.valid is False
            assert "config_snapshot.yaml" in result.missing_files

    def test_verify_missing_meal(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, include_meal=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=False)

            assert result.valid is False
            assert "meal_snapshot.json" in result.missing_files

    def test_verify_invalid_manifest(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, valid_manifest=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=False)

            assert result.valid is False
            assert "manifest.json" in result.invalid_files

    def test_verify_invalid_config(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, valid_config=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=False)

            assert result.valid is False
            assert "config_snapshot.yaml" in result.invalid_files

    def test_verify_invalid_meal(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = self._create_experiment_dir(temp_path, valid_meal=False)
            system_config = {"parser": {"input_dir": "data/raw"}}

            result = verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=False)

            assert result.valid is False
            assert "meal_snapshot.json" in result.invalid_files

    def test_verify_nonexistent_directory(self):
        from eval.run_experiment import verify_experiment_assets

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            exp_dir = temp_path / "nonexistent"
            system_config = {"parser": {"input_dir": "data/raw"}}

            with pytest.raises(FileNotFoundError, match="Experiment directory not found"):
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

            meal = {
                "pdf_files": [
                    {"path": "missing.pdf", "sha256": "abc123"}
                ]
            }
            with open(exp_dir / "meal_snapshot.json", "w", encoding="utf-8") as f:
                json.dump(meal, f)

            raw_dir = temp_path / "raw"
            raw_dir.mkdir()
            system_config = {"parser": {"input_dir": str(raw_dir)}}

            result = verify_experiment_assets(exp_dir, system_config, verify_pdf_hashes=True)

            assert result.valid is False
            assert "missing.pdf" in result.pdf_issues
            assert "File not found" in result.pdf_issues["missing.pdf"]


class TestBuildComparisonData:
    def test_build_comparison_data_empty(self):
        from eval.run_experiment import _build_comparison_data

        results = []
        data = _build_comparison_data(results)

        assert data["experiments"] == []
        assert data["best_variants"] == []
        assert data["summary"]["total_experiments"] == 0

    def test_build_comparison_data_single_experiment(self):
        from eval.run_experiment import _build_comparison_data

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

        data = _build_comparison_data(results)

        assert len(data["experiments"]) == 1
        assert data["experiments"][0]["name"] == "test_exp"
        assert len(data["experiments"][0]["variants"]) == 1
        assert data["experiments"][0]["variants"][0]["metrics"]["hit_rate"] == 0.85

    def test_build_comparison_data_multiple_experiments(self):
        from eval.run_experiment import _build_comparison_data

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

        data = _build_comparison_data(results)

        assert len(data["experiments"]) == 2
        assert len(data["best_variants"]) == 2
        assert data["best_variants"][0]["experiment_name"] == "exp_b"
        assert data["best_variants"][0]["metrics"]["hit_rate"] == 0.90

    def test_build_comparison_data_with_meal_info(self):
        from eval.run_experiment import _build_comparison_data

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

        data = _build_comparison_data(results)

        assert data["experiments"][0]["meal_info"]["name"] == "meal_test"
        assert data["experiments"][0]["meal_info"]["pdf_count"] == 5

    def test_build_comparison_data_with_test_sets(self):
        from eval.run_experiment import _build_comparison_data

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

        data = _build_comparison_data(results)

        assert len(data["experiments"][0]["test_sets"]) == 2
        assert data["experiments"][0]["test_sets"][0]["strategy"] == "factual"


class TestExtractCategoryMetrics:
    def test_extract_category_metrics_empty(self):
        from eval.run_experiment import _extract_category_metrics

        variant_result = {"results": []}
        metrics = _extract_category_metrics(variant_result)

        assert metrics == {}

    def test_extract_category_metrics_single_category(self):
        from eval.run_experiment import _extract_category_metrics

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

        metrics = _extract_category_metrics(variant_result)

        assert "factual" in metrics
        assert metrics["factual"]["hit_rate"] == pytest.approx(0.85)
        assert metrics["factual"]["mrr"] == pytest.approx(0.75)
        assert metrics["factual"]["count"] == 2

    def test_extract_category_metrics_multiple_categories(self):
        from eval.run_experiment import _extract_category_metrics

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

        metrics = _extract_category_metrics(variant_result)

        assert "factual" in metrics
        assert "boundary" in metrics
        assert metrics["factual"]["hit_rate"] == 0.9
        assert metrics["boundary"]["hit_rate"] == 0.6

    def test_extract_category_metrics_missing_retrieval(self):
        from eval.run_experiment import _extract_category_metrics

        variant_result = {
            "results": [
                {"category": "factual"},
                {"category": "factual", "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75}},
            ]
        }

        metrics = _extract_category_metrics(variant_result)

        assert metrics["factual"]["count"] == 1


class TestGenerateComparisonReport:
    def test_generate_comparison_report_basic(self):
        from eval.run_experiment import _generate_comparison_report

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

        report = _generate_comparison_report(comparison_data, [])

        assert "# Experiment Comparison Report" in report
        assert "test_exp" in report
        assert "variant_a" in report
        assert "0.8500" in report

    def test_generate_comparison_report_with_not_found(self):
        from eval.run_experiment import _generate_comparison_report

        comparison_data = {
            "experiments": [],
            "best_variants": [],
            "summary": {"total_experiments": 0, "total_variants": 0},
        }

        report = _generate_comparison_report(comparison_data, ["exp_missing"])

        assert "Warnings" in report
        assert "exp_missing" in report

    def test_generate_comparison_report_with_meal_info(self):
        from eval.run_experiment import _generate_comparison_report

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

        report = _generate_comparison_report(comparison_data, [])

        assert "Data Source" in report
        assert "meal_test" in report
        assert "5" in report

    def test_generate_comparison_report_with_category_metrics(self):
        from eval.run_experiment import _generate_comparison_report

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
                                "factual": {"hit_rate": 0.9, "mrr": 0.8, "ndcg": 0.85, "count": 10},
                                "boundary": {"hit_rate": 0.6, "mrr": 0.5, "ndcg": 0.55, "count": 5},
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

        report = _generate_comparison_report(comparison_data, [])

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
            call_kwargs = mock_generator.generate_document_based_questions.call_args.kwargs
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
            call_kwargs = mock_generator.generate_document_based_questions.call_args.kwargs
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
        import sys
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

    @patch("eval.run_experiment._evaluate_with_builtin")
    @patch("eval.run_experiment._evaluate_with_ragas")
    @patch("eval.run_experiment._collect_rag_samples")
    @patch("eval.run_experiment._create_evaluators")
    @patch("eval.run_experiment.get_llm_config")
    def test_single_backend_no_prefix(
        self, mock_llm_config, mock_create_evaluators, mock_collect,
        mock_ragas, mock_builtin,
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_evaluator = MagicMock()
        mock_evaluator.supported_generation_metrics = ["faithfulness", "answer_relevancy"]
        mock_create_evaluators.return_value = {"builtin": mock_evaluator}
        mock_collect.return_value = [
            {"question_id": "q1", "question": "Q1?", "answer": "A1", "contexts": ["c1"]},
        ]
        mock_builtin.return_value = [
            {"id": "q1", "question": "Q1?", "answer": "A1",
             "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
             "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8}},
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

    @patch("eval.run_experiment._evaluate_with_builtin")
    @patch("eval.run_experiment._evaluate_with_ragas")
    @patch("eval.run_experiment._collect_rag_samples")
    @patch("eval.run_experiment._create_evaluators")
    @patch("eval.run_experiment.get_llm_config")
    def test_dual_backends_have_prefix(
        self, mock_llm_config, mock_create_evaluators, mock_collect,
        mock_ragas, mock_builtin,
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_builtin_evaluator = MagicMock()
        mock_builtin_evaluator.supported_generation_metrics = ["faithfulness", "answer_relevancy"]
        mock_ragas_evaluator = MagicMock()
        mock_ragas_evaluator.supported_generation_metrics = [
            "faithfulness", "answer_relevancy", "context_precision",
        ]
        mock_create_evaluators.return_value = {
            "builtin": mock_builtin_evaluator,
            "ragas": mock_ragas_evaluator,
        }
        mock_collect.return_value = [
            {"question_id": "q1", "question": "Q1?", "answer": "A1", "contexts": ["c1"]},
        ]
        mock_builtin.return_value = [
            {"id": "q1", "question": "Q1?", "answer": "A1",
             "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
             "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8}},
        ]
        mock_ragas.return_value = [
            {"id": "q1", "question": "Q1?", "answer": "A1",
             "generation": {"faithfulness": 0.85, "answer_relevancy": 0.75, "context_precision": 0.7}},
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

    @patch("eval.run_experiment._evaluate_with_builtin")
    @patch("eval.run_experiment._evaluate_with_ragas")
    @patch("eval.run_experiment._collect_rag_samples")
    @patch("eval.run_experiment._create_evaluators")
    @patch("eval.run_experiment.get_llm_config")
    def test_dual_backends_builtin_computes_all_supported(
        self, mock_llm_config, mock_create_evaluators, mock_collect,
        mock_ragas, mock_builtin,
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_builtin_evaluator = MagicMock()
        mock_builtin_evaluator.supported_generation_metrics = ["faithfulness", "answer_relevancy"]
        mock_ragas_evaluator = MagicMock()
        mock_ragas_evaluator.supported_generation_metrics = ["faithfulness", "answer_relevancy"]
        mock_create_evaluators.return_value = {
            "builtin": mock_builtin_evaluator,
            "ragas": mock_ragas_evaluator,
        }
        mock_collect.return_value = [
            {"question_id": "q1", "question": "Q1?", "answer": "A1", "contexts": ["c1"]},
        ]
        mock_builtin.return_value = [
            {"id": "q1", "question": "Q1?", "answer": "A1",
             "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8}},
        ]
        mock_ragas.return_value = [
            {"id": "q1", "question": "Q1?", "answer": "A1",
             "generation": {"faithfulness": 0.85, "answer_relevancy": 0.75}},
        ]

        exp_config = self._make_exp_config(backends=["builtin", "ragas"])
        evaluate_test_set(
            pipeline=MagicMock(),
            test_set={"questions": []},
            exp_config=exp_config,
            system_config={},
        )

        call_args = mock_builtin.call_args
        assert call_args.kwargs["generation_metrics"] == ["faithfulness", "answer_relevancy"]

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

    @patch("eval.run_experiment._evaluate_with_builtin")
    @patch("eval.run_experiment._collect_rag_samples")
    @patch("eval.run_experiment._create_evaluators")
    @patch("eval.run_experiment.get_llm_config")
    def test_single_ragas_backend_no_prefix(
        self, mock_llm_config, mock_create_evaluators, mock_collect,
        mock_builtin,
    ):
        mock_llm_config.return_value = {"api_key": "test"}
        mock_ragas_evaluator = MagicMock()
        mock_ragas_evaluator.supported_generation_metrics = [
            "faithfulness", "answer_relevancy", "context_precision",
        ]
        mock_create_evaluators.return_value = {"ragas": mock_ragas_evaluator}
        mock_collect.return_value = [
            {"question_id": "q1", "question": "Q1?", "answer": "A1", "contexts": ["c1"]},
        ]

        with patch("eval.run_experiment._evaluate_with_ragas") as mock_ragas:
            mock_ragas.return_value = [
                {"id": "q1", "question": "Q1?", "answer": "A1",
                 "generation": {"faithfulness": 0.85, "answer_relevancy": 0.75}},
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
