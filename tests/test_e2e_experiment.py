import json
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml


@pytest.fixture
def temp_project_dir():
    with tempfile.TemporaryDirectory() as temp_dir:
        temp_path = Path(temp_dir)

        raw_dir = temp_path / "data" / "raw"
        raw_dir.mkdir(parents=True)

        parsed_dir = temp_path / "data" / "parsed"
        parsed_dir.mkdir(parents=True)

        chunks_dir = temp_path / "data" / "chunks"
        chunks_dir.mkdir(parents=True)

        artifacts_dir = temp_path / "data" / "artifacts"
        artifacts_dir.mkdir(parents=True)

        meals_dir = temp_path / "data" / "meals"
        meals_dir.mkdir(parents=True)

        exp_reports_dir = temp_path / "data" / "exp_reports"
        exp_reports_dir.mkdir(parents=True)

        vector_store_dir = temp_path / "data" / "vector_store"
        vector_store_dir.mkdir(parents=True)

        exp_configs_dir = temp_path / "exp_configs"
        exp_configs_dir.mkdir(parents=True)

        yield temp_path


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
        from eval.run_experiment import _build_comparison_data, _generate_comparison_report
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
        from eval.run_experiment import _build_comparison_data, _generate_comparison_report

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
