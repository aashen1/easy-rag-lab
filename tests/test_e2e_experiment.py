import json
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.test_generator import TestSetGenerator


@pytest.fixture
def test_pdf_files(temp_project_dir):
    raw_dir = temp_project_dir / "data" / "raw"

    pdf_files = []
    for i in range(2):
        pdf_content = f"""%PDF-1.4
1 0 obj
<< /Type /Catalog /Pages 2 0 R >>
endobj
2 0 obj
<< /Type /Pages /Kids [3 0 R] /Count 1 >>
endobj
3 0 obj
<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R /Resources << /Font << /F1 5 0 R >> >> >>
endobj
4 0 obj
<< /Length 100 >>
stream
BT
/F1 12 Tf
100 700 Td
(Test Document {i}) Tj
0 -20 Td
(This is test content for document {i}.) Tj
ET
endstream
endobj
5 0 obj
<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>
endobj
xref
0 6
0000000000 65535 f
0000000009 00000 n
0000000058 00000 n
0000000115 00000 n
0000000266 00000 n
0000000417 00000 n
trailer
<< /Size 6 /Root 1 0 R >>
startxref
496
%%EOF""".encode("latin-1")

        pdf_path = raw_dir / f"test_doc_{i}.pdf"
        with open(pdf_path, "wb") as f:
            f.write(pdf_content)
        pdf_files.append(pdf_path)

    return pdf_files


@pytest.fixture
def test_system_config(temp_project_dir):
    return {
        "active_mode": "default",
        "llm_presets": {
            "default": {
                "model_name": "test-model",
                "temperature": 0.0,
                "max_tokens": 1024,
                "api_key": "test-api-key",
                "base_url": "https://test.api",
            },
            "sonnet": {
                "model_name": "test-sonnet",
                "temperature": 0.0,
                "max_tokens": 1024,
                "api_key": "test-api-key",
                "base_url": "https://test.api",
            },
        },
        "parser": {
            "input_dir": str(temp_project_dir / "data" / "raw"),
            "output_dir": str(temp_project_dir / "data" / "parsed"),
        },
        "chunker": {
            "input_dir": str(temp_project_dir / "data" / "parsed"),
            "output_dir": str(temp_project_dir / "data" / "chunks"),
            "chunk_size": 512,
            "chunk_overlap": 0,
        },
        "embedding": {
            "model_name": "test-embedding-model",
            "device": "cpu",
            "batch_size": 32,
        },
        "vector_store": {
            "type": "qdrant",
            "collection_name": "test_collection",
            "persist_dir": str(temp_project_dir / "data" / "vector_store"),
            "distance": "Cosine",
        },
        "retrieval": {
            "top_k": 5,
        },
        "experiments": {
            "dir": str(temp_project_dir / "data" / "exp_reports"),
            "configs_dir": str(temp_project_dir / "exp_configs"),
        },
        "meals": {
            "dir": str(temp_project_dir / "data" / "meals"),
            "collection_prefix": "m_",
        },
        "artifacts": {
            "dir": str(temp_project_dir / "data" / "artifacts"),
        },
        "test_generation": {
            "default_strategy": "factual",
            "default_num_questions": 5,
            "max_retries": 3,
        },
        "logging": {
            "level": "INFO",
            "format": "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
            "log_dir": str(temp_project_dir / "logs"),
            "rotation": "10 MB",
            "retention": "7 days",
        },
    }


@pytest.fixture
def test_experiment_config(temp_project_dir):
    return {
        "name": "test_e2e_experiment",
        "description": "End-to-end test experiment",
        "data": {
            "meal": "meal_test_e2e",
            "create_if_missing": {
                "sample_ratio": 1.0,
                "seed": 42,
            },
        },
        "test_sets": [
            {
                "strategy": "factual",
                "num_questions": 3,
                "seed": 100,
            }
        ],
        "variants": [
            {
                "name": "variant_default",
                "description": "Default configuration",
                "config_overrides": {},
            }
        ],
        "evaluation": {
            "llm_preset": "default",
            "metrics": {
                "retrieval": ["hit_rate", "mrr", "ndcg"],
            },
        },
        "llm": {
            "question_generation": "sonnet",
            "answering": "default",
        },
    }


@pytest.fixture
def test_experiment_config_file(temp_project_dir, test_experiment_config):
    config_path = temp_project_dir / "exp_configs" / "test_e2e.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(test_experiment_config, f)
    return config_path


@pytest.fixture
def test_system_config_file(temp_project_dir, test_system_config):
    config_path = temp_project_dir / "config.yaml"
    with open(config_path, "w", encoding="utf-8") as f:
        yaml.dump(test_system_config, f)
    return config_path


class TestEndToEndExperiment:
    @pytest.mark.unit
    def test_verify_experiment_assets(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from eval.run_experiment import verify_experiment_assets
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        meal_snapshot = {
            "meal_id": "test_meal_id",
            "name": "meal_test_e2e",
            "pdf_files": [],
        }

        test_set_snapshots = [
            {
                "name": "auto_factual",
                "strategy": "factual",
                "num_questions": 3,
                "questions": [],
            }
        ]

        config_snapshot = {
            "data": test_experiment_config["data"],
            "test_sets": test_experiment_config["test_sets"],
            "evaluation": test_experiment_config["evaluation"],
        }

        manager.save_snapshots(
            exp_dir, exp_config, meal_snapshot, test_set_snapshots, config_snapshot
        )

        result = verify_experiment_assets(
            exp_dir, test_system_config, verify_pdf_hashes=False
        )

        assert result.valid is True
        assert result.missing_files == []
        assert result.invalid_files == []

    @pytest.mark.unit
    def test_verify_experiment_assets_missing_files(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_experiment import verify_experiment_assets

        exp_dir = temp_project_dir / "data" / "exp_reports" / "exp_test"
        exp_dir.mkdir(parents=True)

        result = verify_experiment_assets(
            exp_dir, test_system_config, verify_pdf_hashes=False
        )

        assert result.valid is False
        assert "manifest.json" in result.missing_files
        assert "config_snapshot.yaml" in result.missing_files
        assert "meal_snapshot.json" in result.missing_files

    @pytest.mark.unit
    def test_compare_experiments(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from eval.run_experiment import (
            _build_comparison_data,
            _generate_comparison_report,
        )
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)

        exp_dir1 = manager.create_experiment_dir(exp_config)
        meal_snapshot = {"meal_id": "test_id_1", "name": "meal_1", "pdf_files": []}
        manager.save_snapshots(exp_dir1, exp_config, meal_snapshot, [], {})

        variant_result1 = {
            "variant_name": "variant_a",
            "retrieval_metrics": {"avg_hit_rate": 0.85, "avg_mrr": 0.72, "avg_ndcg": 0.78},
        }
        manager.save_variant_result(exp_dir1, "variant_a", variant_result1)

        exp_config2 = ExperimentConfig.from_dict({
            **test_experiment_config,
            "name": "test_experiment_2",
        })
        exp_dir2 = manager.create_experiment_dir(exp_config2)
        meal_snapshot2 = {"meal_id": "test_id_2", "name": "meal_2", "pdf_files": []}
        manager.save_snapshots(exp_dir2, exp_config2, meal_snapshot2, [], {})

        variant_result2 = {
            "variant_name": "variant_b",
            "retrieval_metrics": {"avg_hit_rate": 0.90, "avg_mrr": 0.85, "avg_ndcg": 0.88},
        }
        manager.save_variant_result(exp_dir2, "variant_b", variant_result2)

        result1 = manager.load_experiment_result(exp_dir1)
        result2 = manager.load_experiment_result(exp_dir2)

        comparison_data = _build_comparison_data([
            result1.to_dict(),
            result2.to_dict(),
        ])

        assert len(comparison_data["experiments"]) == 2
        assert comparison_data["summary"]["total_experiments"] == 2
        assert len(comparison_data["best_variants"]) == 2

        report = _generate_comparison_report(comparison_data, [])

        assert "# Experiment Comparison Report" in report
        assert "test_e2e_experiment" in report
        assert "test_experiment_2" in report


class TestAssetVerificationExtended:
    @pytest.mark.unit
    def test_verify_with_pdf_hash_mismatch(
        self,
        temp_project_dir,
        test_system_config,
        test_pdf_files,
    ):
        from eval.run_experiment import verify_experiment_assets
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict({
            "name": "test",
            "description": "Test",
            "data": {"meal": "test"},
            "test_sets": [{"strategy": "factual", "num_questions": 10}],
            "variants": [{"name": "v1"}],
            "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
        })

        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        meal_snapshot = {
            "meal_id": "test_id",
            "name": "test_meal",
            "pdf_files": [
                {
                    "path": "test_doc_0.pdf",
                    "sha256": "wrong_hash_value_12345",
                    "size_bytes": 1000,
                }
            ],
        }

        manager.save_snapshots(exp_dir, exp_config, meal_snapshot, [], {})

        result = verify_experiment_assets(
            exp_dir, test_system_config, verify_pdf_hashes=True
        )

        assert result.valid is False
        assert "test_doc_0.pdf" in result.pdf_issues
        assert "SHA256 mismatch" in result.pdf_issues["test_doc_0.pdf"]

    @pytest.mark.unit
    def test_verify_with_missing_pdf(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_experiment import verify_experiment_assets
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict({
            "name": "test",
            "description": "Test",
            "data": {"meal": "test"},
            "test_sets": [{"strategy": "factual", "num_questions": 10}],
            "variants": [{"name": "v1"}],
            "evaluation": {"metrics": {"retrieval": ["hit_rate"]}},
        })

        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        meal_snapshot = {
            "meal_id": "test_id",
            "name": "test_meal",
            "pdf_files": [
                {
                    "path": "nonexistent.pdf",
                    "sha256": "abc123",
                    "size_bytes": 1000,
                }
            ],
        }

        manager.save_snapshots(exp_dir, exp_config, meal_snapshot, [], {})

        result = verify_experiment_assets(
            exp_dir, test_system_config, verify_pdf_hashes=True
        )

        assert result.valid is False
        assert "nonexistent.pdf" in result.pdf_issues
        assert "File not found" in result.pdf_issues["nonexistent.pdf"]


class TestExperimentComparisonExtended:
    @pytest.mark.unit
    def test_comparison_with_not_found_experiments(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_experiment import (
            _build_comparison_data,
            _generate_comparison_report,
        )

        comparison_data = _build_comparison_data([])

        report = _generate_comparison_report(comparison_data, ["exp_missing_1", "exp_missing_2"])

        assert "Warnings" in report
        assert "exp_missing_1" in report
        assert "exp_missing_2" in report

    @pytest.mark.unit
    def test_comparison_with_different_test_sets(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_experiment import _build_comparison_data

        results = [
            {
                "experiment_id": "exp_001",
                "name": "exp_a",
                "description": "A",
                "created_at": "2025-01-01T00:00:00",
                "status": "completed",
                "test_set_snapshots": [
                    {"strategy": "factual", "num_questions": 20},
                    {"strategy": "boundary", "num_questions": 15},
                ],
                "variant_results": [
                    {
                        "variant_name": "v1",
                        "retrieval_metrics": {"avg_hit_rate": 0.8, "avg_mrr": 0.7, "avg_ndcg": 0.75},
                        "total_questions": 35,
                    }
                ],
            },
            {
                "experiment_id": "exp_002",
                "name": "exp_b",
                "description": "B",
                "created_at": "2025-01-02T00:00:00",
                "status": "completed",
                "test_set_snapshots": [
                    {"strategy": "factual", "num_questions": 30},
                ],
                "variant_results": [
                    {
                        "variant_name": "v1",
                        "retrieval_metrics": {"avg_hit_rate": 0.85, "avg_mrr": 0.75, "avg_ndcg": 0.80},
                        "total_questions": 30,
                    }
                ],
            },
        ]

        comparison_data = _build_comparison_data(results)

        assert len(comparison_data["experiments"]) == 2
        assert len(comparison_data["experiments"][0]["test_sets"]) == 2
        assert len(comparison_data["experiments"][1]["test_sets"]) == 1


class TestReproduceExperiment:
    @pytest.mark.unit
    def test_reproduce_experiment_asset_verification(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
        test_pdf_files,
    ):
        from eval.run_experiment import verify_experiment_assets
        from src.experiment import ExperimentConfig, ExperimentManager
        from src.meal import compute_file_sha256

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        pdf_file = test_pdf_files[0]
        sha256_hash = compute_file_sha256(pdf_file)

        meal_snapshot = {
            "meal_id": "test_meal_id",
            "name": "meal_test_e2e",
            "pdf_files": [
                {
                    "path": pdf_file.name,
                    "sha256": sha256_hash,
                    "size_bytes": pdf_file.stat().st_size,
                }
            ],
        }

        config_snapshot = {
            "data": test_experiment_config["data"],
            "test_sets": test_experiment_config["test_sets"],
            "evaluation": test_experiment_config["evaluation"],
        }

        manager.save_snapshots(exp_dir, exp_config, meal_snapshot, [], config_snapshot)

        result = verify_experiment_assets(
            exp_dir, test_system_config, verify_pdf_hashes=True
        )

        assert result.valid is True
        assert result.missing_files == []
        assert result.pdf_issues == {}


class TestEndToEndEvaluationFlow:
    @pytest.mark.unit
    def test_full_evaluation_flow_with_generation_metrics(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_eval import run_evaluation

        test_data = [
            {
                "id": "q001",
                "question": "What is the revenue?",
                "source_files": ["report_a.pdf"],
            },
            {
                "id": "q002",
                "question": "What is the profit?",
                "source_files": ["report_b.pdf"],
            },
        ]
        test_data_path = temp_project_dir / "test_data.json"
        with open(test_data_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        output_dir = temp_project_dir / "output"

        mock_pipeline = MagicMock()
        mock_pipeline.query.side_effect = [
            {
                "answer": "Revenue is 100M.",
                "sources": ["report_a.pdf"],
                "contexts": ["Revenue for 2023 was 100 million."],
            },
            {
                "answer": "Profit is 50M.",
                "sources": ["report_b.pdf"],
                "contexts": ["Net profit for 2023 was 50 million."],
            },
        ]

        with patch("eval.run_eval.calculate_faithfulness") as mock_faithfulness, \
             patch("eval.run_eval.calculate_answer_relevancy") as mock_relevancy:
            mock_faithfulness.return_value = 0.85
            mock_relevancy.return_value = 0.92

            summary = run_evaluation(
                pipeline=mock_pipeline,
                test_data_path=str(test_data_path),
                output_dir=str(output_dir),
                metrics_config=["hit_rate", "mrr", "ndcg"],
                generation_metrics_config=["faithfulness", "answer_relevancy"],
                llm_config={
                    "api_key": "test_key",
                    "base_url": "https://test.url",
                    "model_name": "test_model",
                },
            )

            assert summary["total_test_cases"] == 2
            assert "retrieval_metrics" in summary
            assert "generation_metrics" in summary

            for result in summary["results"]:
                assert "retrieval" in result
                assert "generation" in result
                assert "hit_rate" in result["retrieval"]
                assert "mrr" in result["retrieval"]
                assert "ndcg" in result["retrieval"]
                assert "faithfulness" in result["generation"]
                assert "answer_relevancy" in result["generation"]

            report_path = output_dir / "baseline_report.json"
            assert report_path.exists()

    @pytest.mark.unit
    def test_evaluation_flow_with_document_level_questions(
        self,
        temp_project_dir,
        test_system_config,
    ):
        test_data = {
            "name": "document_level_n10",
            "strategy": "document",
            "questions": [
                {
                    "id": "q001",
                    "question": "2024年光模块市场规模多少？",
                    "answer": "约100亿美元",
                    "question_type": "single_fact",
                    "source_files": ["report_a.pdf"],
                },
                {
                    "id": "q002",
                    "question": "为什么CPO能降低功耗？",
                    "answer": "因为减少了信号传输距离",
                    "question_type": "reasoning",
                    "source_files": ["report_b.pdf"],
                },
            ],
        }
        test_data_path = temp_project_dir / "test_data.json"
        with open(test_data_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        output_dir = temp_project_dir / "output"

        mock_pipeline = MagicMock()
        mock_pipeline.query.side_effect = [
            {
                "answer": "2024年光模块市场规模约为100亿美元。",
                "sources": ["report_a.pdf"],
                "contexts": ["根据市场研究报告，2024年全球光模块市场规模约为100亿美元。"],
            },
            {
                "answer": "CPO能降低功耗主要是因为减少了信号传输距离。",
                "sources": ["report_b.pdf"],
                "contexts": ["CPO技术通过将光引擎与芯片封装在一起，大幅减少了信号传输距离，从而降低功耗。"],
            },
        ]

        with patch("eval.run_eval.calculate_faithfulness") as mock_faithfulness, \
             patch("eval.run_eval.calculate_answer_relevancy") as mock_relevancy:
            mock_faithfulness.return_value = 0.90
            mock_relevancy.return_value = 0.95

            from eval.run_eval import run_evaluation

            summary = run_evaluation(
                pipeline=mock_pipeline,
                test_data_path=str(test_data_path),
                output_dir=str(output_dir),
                metrics_config=["hit_rate", "ndcg"],
                generation_metrics_config=["faithfulness", "answer_relevancy"],
                llm_config={
                    "api_key": "test_key",
                    "base_url": "https://test.url",
                    "model_name": "test_model",
                },
            )

            assert summary["total_test_cases"] == 2
            assert len(summary["results"]) == 2

            for result in summary["results"]:
                assert "hit_rate" in result["retrieval"]
                assert "ndcg" in result["retrieval"]
                assert "faithfulness" in result["generation"]


class TestBackwardCompatibility:
    @pytest.mark.unit
    def test_evaluation_without_generation_metrics(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_eval import run_evaluation

        test_data = [
            {
                "id": "q001",
                "question": "What is the revenue?",
                "source_files": ["report_a.pdf"],
            },
        ]
        test_data_path = temp_project_dir / "test_data.json"
        with open(test_data_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        output_dir = temp_project_dir / "output"

        mock_pipeline = MagicMock()
        mock_pipeline.query.return_value = {
            "answer": "Revenue is 100M.",
            "sources": ["report_a.pdf"],
        }

        summary = run_evaluation(
            pipeline=mock_pipeline,
            test_data_path=str(test_data_path),
            output_dir=str(output_dir),
            metrics_config=["hit_rate", "mrr", "ndcg"],
            generation_metrics_config=None,
            llm_config=None,
        )

        assert "retrieval_metrics" in summary
        assert "generation_metrics" not in summary
        assert "generation" not in summary["results"][0]

    @pytest.mark.unit
    def test_test_data_format_list(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_eval import run_evaluation

        test_data = [
            {
                "id": "q001",
                "question": "Question 1?",
                "source_files": ["doc_a.pdf"],
            },
        ]
        test_data_path = temp_project_dir / "test_data.json"
        with open(test_data_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        output_dir = temp_project_dir / "output"

        mock_pipeline = MagicMock()
        mock_pipeline.query.return_value = {
            "answer": "Answer 1",
            "sources": ["doc_a.pdf"],
        }

        summary = run_evaluation(
            pipeline=mock_pipeline,
            test_data_path=str(test_data_path),
            output_dir=str(output_dir),
        )

        assert summary["total_test_cases"] == 1

    @pytest.mark.unit
    def test_test_data_format_dict_with_questions(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_eval import run_evaluation

        test_data = {
            "name": "test_set",
            "questions": [
                {
                    "id": "q001",
                    "question": "Question 1?",
                    "source_files": ["doc_a.pdf"],
                },
            ],
        }
        test_data_path = temp_project_dir / "test_data.json"
        with open(test_data_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        output_dir = temp_project_dir / "output"

        mock_pipeline = MagicMock()
        mock_pipeline.query.return_value = {
            "answer": "Answer 1",
            "sources": ["doc_a.pdf"],
        }

        summary = run_evaluation(
            pipeline=mock_pipeline,
            test_data_path=str(test_data_path),
            output_dir=str(output_dir),
        )

        assert summary["total_test_cases"] == 1

    @pytest.mark.unit
    def test_expected_sources_fallback(
        self,
        temp_project_dir,
        test_system_config,
    ):
        from eval.run_eval import run_evaluation

        test_data = [
            {
                "id": "q001",
                "question": "Question 1?",
                "source_files": ["doc_a.pdf"],
            },
        ]
        test_data_path = temp_project_dir / "test_data.json"
        with open(test_data_path, "w", encoding="utf-8") as f:
            json.dump(test_data, f)

        output_dir = temp_project_dir / "output"

        mock_pipeline = MagicMock()
        mock_pipeline.query.return_value = {
            "answer": "Answer 1",
            "sources": ["doc_a.pdf"],
        }

        summary = run_evaluation(
            pipeline=mock_pipeline,
            test_data_path=str(test_data_path),
            output_dir=str(output_dir),
            metrics_config=["hit_rate"],
        )

        assert summary["results"][0]["retrieval"]["hit_rate"] == 1.0

    @pytest.mark.unit
    def test_experiment_config_without_generation_metrics(
        self,
        temp_project_dir,
        test_system_config,
    ):
        config = {
            "name": "test_experiment",
            "description": "Test",
            "data": {"meal": "test_meal"},
            "test_sets": [{"strategy": "factual", "num_questions": 10}],
            "variants": [{"name": "v1"}],
            "evaluation": {
                "llm_preset": "default",
                "metrics": {
                    "retrieval": ["hit_rate", "mrr", "ndcg"],
                },
            },
        }

        from src.experiment import ExperimentConfig

        exp_config = ExperimentConfig.from_dict(config)
        errors = exp_config.validate()

        assert not any("metrics" in e.lower() for e in errors)

        retrieval_metrics = exp_config.evaluation.get("metrics", {}).get("retrieval")
        generation_metrics = exp_config.evaluation.get("metrics", {}).get("generation")

        assert retrieval_metrics == ["hit_rate", "mrr", "ndcg"]
        assert generation_metrics is None

    @pytest.mark.unit
    def test_experiment_result_backward_compatibility(self):
        from eval.experiment_reporter import ExperimentResult

        legacy_data = {
            "timestamp": "2026-04-16T10:00:00",
            "total_test_cases": 2,
            "total_time_seconds": 6.0,
            "avg_time_per_case": 3.0,
            "retrieval_metrics": {
                "avg_hit_rate": 0.8,
                "avg_mrr": 0.65,
                "avg_ndcg": 0.7,
            },
            "results": [
                {
                    "id": "q001",
                    "question": "What is the revenue?",
                    "answer": "Revenue is 100M.",
                    "retrieval": {"hit_rate": 0.9, "mrr": 0.8, "ndcg": 0.85},
                    "sources": ["report1.pdf"],
                    "time_seconds": 3.0,
                },
            ],
        }

        result = ExperimentResult.from_dict(legacy_data)

        assert result.timestamp == "2026-04-16T10:00:00"
        assert result.total_test_cases == 2
        assert result.generation_metrics is None
        assert result.results[0].generation is None

    @pytest.mark.unit
    def test_variant_result_backward_compatibility(self):
        from eval.experiment_reporter import VariantResult

        legacy_data = {
            "variant_name": "baseline",
            "variant_description": "Baseline configuration",
            "retrieval_metrics": {"avg_hit_rate": 0.75, "avg_mrr": 0.55, "avg_ndcg": 0.65},
            "total_questions": 15,
            "total_time_seconds": 25.0,
        }

        result = VariantResult.from_dict(legacy_data)

        assert result.variant_name == "baseline"
        assert result.retrieval_metrics["avg_hit_rate"] == 0.75
        assert result.generation_metrics is None


class TestDocumentLevelQuestionGenerationIntegration:
    @pytest.mark.unit
    def test_question_generation_with_quality_validation(self):
        config = {
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)

        valid_question = {
            "question": "2024年光模块市场规模多少？",
            "answer": "约100亿美元",
            "question_type": "single_fact",
        }
        assert generator._validate_question_quality(valid_question) is True

        invalid_question = {
            "question": "根据文档，市场规模是多少？",
            "answer": "约100亿美元",
            "question_type": "single_fact",
        }
        assert generator._validate_question_quality(invalid_question) is False

    @pytest.mark.unit
    def test_question_type_distribution_integration(self):
        config = {
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)

        distribution = {
            "single_fact": 0.30,
            "multi_fact": 0.25,
            "reasoning": 0.15,
            "comparative": 0.15,
            "missing": 0.10,
            "irrelevant": 0.05,
        }

        result = generator._calculate_question_distribution(100, distribution)

        total = sum(result.values())
        assert total == 100

        assert result["single_fact"] == 30
        assert result["multi_fact"] == 25
        assert result["reasoning"] == 15

    @pytest.mark.unit
    def test_quality_metrics_calculation_integration(self):
        config = {
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)

        questions = [
            {
                "question": "市场规模多少？",
                "answer": "100亿",
                "question_type": "single_fact",
            },
            {
                "question": "根据文档，营收增长多少？",
                "answer": "20%",
                "question_type": "single_fact",
            },
            {
                "question": "为什么增长这么快？",
                "answer": "因为新产品销售增长",
                "question_type": "reasoning",
            },
        ]

        result = generator._calculate_quality_metrics(questions)

        assert result["format_correct_rate"] == 1.0
        assert result["authenticity_pass_rate"] == 2 / 3
        assert result["type_distribution"]["single_fact"] == 2
        assert result["type_distribution"]["reasoning"] == 1
