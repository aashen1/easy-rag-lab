import hashlib
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

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


@pytest.fixture
def mock_embedding():
    with patch("src.embedder.Embedder") as mock_embedder_class:
        mock_embedder = MagicMock()
        mock_embedder.embed_documents.return_value = [[0.1] * 1024 for _ in range(10)]
        mock_embedder.embed_query.return_value = [0.1] * 1024
        mock_embedder_class.return_value = mock_embedder
        yield mock_embedder


@pytest.fixture
def mock_vector_indexer():
    with patch("src.indexer.VectorIndexer") as mock_indexer_class:
        mock_indexer = MagicMock()
        mock_indexer.get_collection_info.return_value = {"points_count": 100}
        mock_indexer.search.return_value = [
            {
                "id": "chunk_1",
                "score": 0.9,
                "payload": {
                    "text": "Test chunk content",
                    "source": "test_doc_0.pdf",
                    "chunk_id": "chunk_1",
                },
            }
        ]
        mock_indexer_class.return_value = mock_indexer
        yield mock_indexer


@pytest.fixture
def mock_llm_generator():
    with patch("src.generator.LLMGenerator") as mock_generator_class:
        mock_generator = MagicMock()
        mock_generator.generate.return_value = "This is a test answer from the LLM."
        mock_generator_class.return_value = mock_generator
        yield mock_generator


@pytest.fixture
def mock_test_generator():
    with patch("src.test_generator.TestSetGenerator") as mock_generator_class:
        mock_generator = MagicMock()
        mock_generator.generate_test_set.return_value = {
            "name": "auto_factual",
            "strategy": "factual",
            "num_questions": 3,
            "created_at": "2025-01-01T00:00:00",
            "meal_data_id": "test_data_id",
            "questions": [
                {
                    "id": "q1",
                    "question": "What is the main topic of the document?",
                    "source_files": ["test_doc_0.pdf"],
                    "category": "factual",
                    "difficulty": "medium",
                },
                {
                    "id": "q2",
                    "question": "What are the key findings?",
                    "source_files": ["test_doc_0.pdf"],
                    "category": "factual",
                    "difficulty": "medium",
                },
                {
                    "id": "q3",
                    "question": "What conclusions are drawn?",
                    "source_files": ["test_doc_1.pdf"],
                    "category": "factual",
                    "difficulty": "medium",
                },
            ],
        }
        mock_generator_class.return_value = mock_generator
        yield mock_generator


@pytest.fixture
def mock_rag_pipeline(mock_embedding, mock_vector_indexer, mock_llm_generator):
    with patch("src.pipeline.RAGPipeline") as mock_pipeline_class:
        mock_pipeline = MagicMock()
        mock_pipeline.query.return_value = {
            "answer": "This is a test answer.",
            "sources": ["test_doc_0.pdf"],
            "retrieved_chunks": [
                {
                    "text": "Test chunk content",
                    "source": "test_doc_0.pdf",
                    "score": 0.9,
                }
            ],
        }
        mock_pipeline_class.return_value = mock_pipeline
        yield mock_pipeline


class TestEndToEndExperiment:
    @pytest.mark.integration
    def test_create_experiment_directory_structure(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)

        exp_dir = manager.create_experiment_dir(exp_config)

        assert exp_dir.exists()
        assert exp_dir.name.startswith("exp_")
        assert (exp_dir / "test_sets").exists()
        assert (exp_dir / "results").exists()

    @pytest.mark.integration
    def test_save_experiment_snapshots(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)

        exp_dir = manager.create_experiment_dir(exp_config)

        meal_snapshot = {
            "meal_id": "test_meal_id",
            "name": "meal_test_e2e",
            "pdf_count": 2,
            "total_chunks": 10,
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

        assert (exp_dir / "config_snapshot.yaml").exists()
        assert (exp_dir / "meal_snapshot.json").exists()
        assert (exp_dir / "manifest.json").exists()

        with open(exp_dir / "manifest.json", "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["name"] == "test_e2e_experiment"
        assert manifest["status"] == "running"

    @pytest.mark.integration
    def test_generate_template_report(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from eval.experiment_reporter import ExperimentReporter
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        variant_results = [
            {
                "variant_name": "variant_default",
                "variant_description": "Default configuration",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.85,
                    "avg_mrr": 0.72,
                    "avg_ndcg": 0.78,
                },
                "total_questions": 3,
                "total_time_seconds": 10.5,
                "results": [
                    {
                        "id": "q1",
                        "question": "Test question 1",
                        "retrieval": {"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
                        "sources": ["test_doc_0.pdf"],
                    },
                    {
                        "id": "q2",
                        "question": "Test question 2",
                        "retrieval": {"hit_rate": 1.0, "mrr": 0.5, "ndcg": 0.7},
                        "sources": ["test_doc_0.pdf"],
                    },
                    {
                        "id": "q3",
                        "question": "Test question 3",
                        "retrieval": {"hit_rate": 0.0, "mrr": 0.0, "ndcg": 0.0},
                        "sources": ["test_doc_1.pdf"],
                    },
                ],
            }
        ]

        meal_info = {
            "name": "meal_test_e2e",
            "data_id": "test_data_id_123",
        }

        config_snapshot = {
            "data": test_experiment_config["data"],
            "test_sets": test_experiment_config["test_sets"],
            "evaluation": test_experiment_config["evaluation"],
        }

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=exp_dir,
            variant_results=variant_results,
            meal_info=meal_info,
            config_snapshot=config_snapshot,
            output_filename="experiment_report.md",
        )

        assert "# RAG Multi-Variant Experiment Report" in report
        assert "variant_default" in report
        assert "0.8500" in report
        assert "0.7200" in report
        assert "0.7800" in report

        report_path = exp_dir / "experiment_report.md"
        assert report_path.exists()

        with open(report_path, "r", encoding="utf-8") as f:
            saved_report = f.read()
        assert saved_report == report

    @pytest.mark.integration
    def test_generate_llm_report(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from eval.experiment_reporter import ExperimentReporter, ExperimentResult, TestCaseResult
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        result = ExperimentResult(
            timestamp="2025-01-01T00:00:00",
            total_test_cases=3,
            total_time_seconds=10.5,
            avg_time_per_case=3.5,
            retrieval_metrics={
                "avg_hit_rate": 0.85,
                "avg_mrr": 0.72,
                "avg_ndcg": 0.78,
            },
            results=[
                TestCaseResult(
                    id="q1",
                    question="Test question 1",
                    answer="Test answer 1",
                    retrieval={"hit_rate": 1.0, "mrr": 1.0, "ndcg": 1.0},
                    sources=["test_doc_0.pdf"],
                ),
            ],
            meal_data_id="test_data_id_123",
            meal_name="meal_test_e2e",
        )

        reporter = ExperimentReporter(
            llm_api_key="test-api-key",
            llm_base_url="https://test.api",
        )

        with patch.object(reporter, "_call_llm") as mock_call_llm:
            mock_call_llm.return_value = """
# 实验报告

## 1. 实验概述
这是一个测试实验报告。

## 2. 结论
测试成功完成。
"""
            report = reporter._generate_llm_report(result)

        assert "实验报告" in report or "RAG" in report

    @pytest.mark.integration
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

    @pytest.mark.integration
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

    @pytest.mark.integration
    def test_load_experiment_result(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
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

        variant_result = {
            "variant_name": "variant_default",
            "retrieval_metrics": {
                "avg_hit_rate": 0.85,
                "avg_mrr": 0.72,
                "avg_ndcg": 0.78,
            },
        }
        manager.save_variant_result(exp_dir, "variant_default", variant_result)

        result = manager.load_experiment_result(exp_dir)

        assert result.experiment_id == exp_dir.name
        assert result.name == "test_e2e_experiment"
        assert result.meal_snapshot["meal_id"] == "test_meal_id"
        assert len(result.test_set_snapshots) == 1
        assert len(result.variant_results) == 1

    @pytest.mark.integration
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

    @pytest.mark.integration
    def test_reproduce_experiment_from_saved_config(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
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
            }
        ]

        config_snapshot = {
            "data": test_experiment_config["data"],
            "test_sets": test_experiment_config["test_sets"],
            "evaluation": test_experiment_config["evaluation"],
            "llm": test_experiment_config.get("llm", {}),
        }

        manager.save_snapshots(
            exp_dir, exp_config, meal_snapshot, test_set_snapshots, config_snapshot
        )

        variant_result = {
            "variant_name": "variant_default",
            "variant_description": "Default configuration",
            "retrieval_metrics": {
                "avg_hit_rate": 0.85,
                "avg_mrr": 0.72,
                "avg_ndcg": 0.78,
            },
            "config_snapshot": {
                "variant": {
                    "name": "variant_default",
                    "description": "Default configuration",
                    "config_overrides": {},
                },
            },
        }
        manager.save_variant_result(exp_dir, "variant_default", variant_result)

        config_path = exp_dir / "config_snapshot.yaml"
        assert config_path.exists()

        with open(config_path, "r", encoding="utf-8") as f:
            loaded_config = yaml.safe_load(f)

        assert loaded_config["data"]["meal"] == "meal_test_e2e"
        assert len(loaded_config["test_sets"]) == 1

        manifest_path = exp_dir / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert manifest["name"] == "test_e2e_experiment"
        assert "variant_default" in manifest["variants"]


class TestExperimentReporterExtended:
    @pytest.mark.integration
    def test_report_with_multiple_variants(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from eval.experiment_reporter import ExperimentReporter
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        variant_results = [
            {
                "variant_name": "chunk_512",
                "variant_description": "Chunk size 512",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.75,
                    "avg_mrr": 0.65,
                    "avg_ndcg": 0.70,
                },
                "total_questions": 10,
                "total_time_seconds": 15.0,
                "results": [],
            },
            {
                "variant_name": "chunk_1024",
                "variant_description": "Chunk size 1024",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.85,
                    "avg_mrr": 0.75,
                    "avg_ndcg": 0.80,
                },
                "total_questions": 10,
                "total_time_seconds": 12.0,
                "results": [],
            },
            {
                "variant_name": "chunk_256",
                "variant_description": "Chunk size 256",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.65,
                    "avg_mrr": 0.55,
                    "avg_ndcg": 0.60,
                },
                "total_questions": 10,
                "total_time_seconds": 18.0,
                "results": [],
            },
        ]

        meal_info = {
            "name": "meal_test",
            "data_id": "test_data_id",
        }

        config_snapshot = {
            "data": {"meal": "meal_test"},
            "test_sets": [{"strategy": "factual", "num_questions": 10}],
            "evaluation": {"metrics": {"retrieval": ["hit_rate", "mrr", "ndcg"]}},
        }

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=exp_dir,
            variant_results=variant_results,
            meal_info=meal_info,
            config_snapshot=config_snapshot,
        )

        assert "chunk_512" in report
        assert "chunk_1024" in report
        assert "chunk_256" in report
        assert "0.7500" in report
        assert "0.8500" in report
        assert "0.6500" in report

        assert "⭐" in report

        lines = report.split("\n")
        best_line = [l for l in lines if "⭐" in l][0]
        assert "chunk_1024" in best_line

    @pytest.mark.integration
    def test_report_with_failed_variant(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from eval.experiment_reporter import ExperimentReporter
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        variant_results = [
            {
                "variant_name": "variant_success",
                "variant_description": "Successful variant",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.85,
                    "avg_mrr": 0.72,
                    "avg_ndcg": 0.78,
                },
                "total_questions": 10,
                "total_time_seconds": 15.0,
                "results": [],
            },
            {
                "variant_name": "variant_failed",
                "variant_description": "Failed variant",
                "error": "Index build failed: out of memory",
                "total_questions": 0,
                "total_time_seconds": 0,
                "results": [],
            },
        ]

        meal_info = {"name": "meal_test", "data_id": "test_id"}
        config_snapshot = {}

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=exp_dir,
            variant_results=variant_results,
            meal_info=meal_info,
            config_snapshot=config_snapshot,
        )

        assert "variant_success" in report
        assert "variant_failed" in report
        assert "ERROR" in report

    @pytest.mark.integration
    def test_report_with_category_metrics(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from eval.experiment_reporter import ExperimentReporter
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        variant_results = [
            {
                "variant_name": "variant_default",
                "variant_description": "Default configuration",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.75,
                    "avg_mrr": 0.65,
                    "avg_ndcg": 0.70,
                },
                "total_questions": 10,
                "total_time_seconds": 15.0,
                "results": [
                    {
                        "id": "q1",
                        "category": "factual",
                        "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                    },
                    {
                        "id": "q2",
                        "category": "factual",
                        "retrieval": {"hit_rate": 0.9, "mrr": 0.8, "ndcg": 0.85},
                    },
                    {
                        "id": "q3",
                        "category": "boundary",
                        "retrieval": {"hit_rate": 0.5, "mrr": 0.4, "ndcg": 0.45},
                    },
                ],
            }
        ]

        meal_info = {"name": "meal_test", "data_id": "test_id"}
        config_snapshot = {}

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=exp_dir,
            variant_results=variant_results,
            meal_info=meal_info,
            config_snapshot=config_snapshot,
        )

        assert "variant_default" in report
        assert "0.7500" in report
        assert "0.6500" in report
        assert "0.7000" in report


class TestAssetVerificationExtended:
    @pytest.mark.integration
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

    @pytest.mark.integration
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
    @pytest.mark.integration
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

    @pytest.mark.integration
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
    @pytest.mark.integration
    def test_reproduce_experiment_config_loading(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
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
            }
        ]

        config_snapshot = {
            "data": test_experiment_config["data"],
            "test_sets": test_experiment_config["test_sets"],
            "evaluation": test_experiment_config["evaluation"],
            "llm": test_experiment_config.get("llm", {}),
        }

        manager.save_snapshots(
            exp_dir, exp_config, meal_snapshot, test_set_snapshots, config_snapshot
        )

        config_path = exp_dir / "config_snapshot.yaml"
        with open(config_path, "r", encoding="utf-8") as f:
            loaded_config = yaml.safe_load(f)

        assert loaded_config["data"]["meal"] == "meal_test_e2e"
        assert loaded_config["data"]["create_if_missing"]["sample_ratio"] == 1.0
        assert len(loaded_config["test_sets"]) == 1
        assert loaded_config["test_sets"][0]["strategy"] == "factual"
        assert loaded_config["test_sets"][0]["num_questions"] == 3

    @pytest.mark.integration
    def test_reproduce_experiment_variant_config(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        meal_snapshot = {
            "meal_id": "test_meal_id",
            "name": "meal_test_e2e",
            "pdf_files": [],
        }

        config_snapshot = {
            "data": test_experiment_config["data"],
            "test_sets": test_experiment_config["test_sets"],
            "evaluation": test_experiment_config["evaluation"],
        }

        manager.save_snapshots(exp_dir, exp_config, meal_snapshot, [], config_snapshot)

        variant_result = {
            "variant_name": "chunk_512_overlap_0",
            "variant_description": "Chunk size 512 with no overlap",
            "retrieval_metrics": {
                "avg_hit_rate": 0.85,
                "avg_mrr": 0.72,
                "avg_ndcg": 0.78,
            },
            "config_snapshot": {
                "variant": {
                    "name": "chunk_512_overlap_0",
                    "description": "Chunk size 512 with no overlap",
                    "config_overrides": {
                        "chunker": {
                            "chunk_size": 512,
                            "chunk_overlap": 0,
                        }
                    },
                },
                "merged": {
                    "chunker": {
                        "chunk_size": 512,
                        "chunk_overlap": 0,
                    },
                    "embedding": {
                        "model_name": "test-embedding-model",
                    },
                },
            },
        }
        manager.save_variant_result(exp_dir, "chunk_512_overlap_0", variant_result)

        result_path = exp_dir / "results" / "chunk_512_overlap_0.json"
        assert result_path.exists()

        with open(result_path, "r", encoding="utf-8") as f:
            loaded_result = json.load(f)

        assert loaded_result["variant_name"] == "chunk_512_overlap_0"
        assert loaded_result["config_snapshot"]["variant"]["config_overrides"]["chunker"]["chunk_size"] == 512

    @pytest.mark.integration
    def test_reproduce_experiment_with_multiple_variants(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from src.experiment import ExperimentConfig, ExperimentManager

        multi_variant_config = {
            **test_experiment_config,
            "variants": [
                {
                    "name": "variant_a",
                    "description": "Variant A",
                    "config_overrides": {"chunker": {"chunk_size": 256}},
                },
                {
                    "name": "variant_b",
                    "description": "Variant B",
                    "config_overrides": {"chunker": {"chunk_size": 512}},
                },
            ],
        }

        exp_config = ExperimentConfig.from_dict(multi_variant_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        meal_snapshot = {
            "meal_id": "test_meal_id",
            "name": "meal_test_e2e",
            "pdf_files": [],
        }

        config_snapshot = {
            "data": test_experiment_config["data"],
            "test_sets": test_experiment_config["test_sets"],
            "evaluation": test_experiment_config["evaluation"],
        }

        manager.save_snapshots(exp_dir, exp_config, meal_snapshot, [], config_snapshot)

        for variant in multi_variant_config["variants"]:
            variant_result = {
                "variant_name": variant["name"],
                "variant_description": variant["description"],
                "retrieval_metrics": {
                    "avg_hit_rate": 0.8,
                    "avg_mrr": 0.7,
                    "avg_ndcg": 0.75,
                },
                "config_snapshot": {
                    "variant": variant,
                },
            }
            manager.save_variant_result(exp_dir, variant["name"], variant_result)

        manifest_path = exp_dir / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)

        assert len(manifest["variants"]) == 2
        assert "variant_a" in manifest["variants"]
        assert "variant_b" in manifest["variants"]

        results_dir = exp_dir / "results"
        assert (results_dir / "variant_a.json").exists()
        assert (results_dir / "variant_b.json").exists()

    @pytest.mark.integration
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

    @pytest.mark.integration
    def test_reproduce_experiment_status_tracking(
        self,
        temp_project_dir,
        test_system_config,
        test_experiment_config,
    ):
        from src.experiment import ExperimentConfig, ExperimentManager

        exp_config = ExperimentConfig.from_dict(test_experiment_config)
        manager = ExperimentManager(test_system_config)
        exp_dir = manager.create_experiment_dir(exp_config)

        meal_snapshot = {
            "meal_id": "test_meal_id",
            "name": "meal_test_e2e",
            "pdf_files": [],
        }

        manager.save_snapshots(exp_dir, exp_config, meal_snapshot, [], {})

        manifest_path = exp_dir / "manifest.json"
        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["status"] == "running"

        manager.update_manifest_status(exp_dir, "completed")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["status"] == "completed"

        manager.update_manifest_status(exp_dir, "failed")

        with open(manifest_path, "r", encoding="utf-8") as f:
            manifest = json.load(f)
        assert manifest["status"] == "failed"
