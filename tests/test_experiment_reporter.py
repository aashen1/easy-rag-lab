from unittest.mock import patch

import pytest

from eval.experiment_reporter import (
    LLM_REPORT_PROMPT_TEMPLATE,
    ExperimentReporter,
    ExperimentResult,
    TestCaseResult,
    VariantResult,
)


class TestTestCaseResult:
    @pytest.mark.unit
    def test_creation(self):
        result = TestCaseResult(
            id="q001",
            question="Test question?",
            answer="Test answer",
            retrieval={"hit_rate": 0.8, "mrr": 0.5, "ndcg": 0.6},
            sources=["doc1.pdf", "doc2.pdf"],
            time_seconds=1.5,
            category="fact_extraction",
        )
        assert result.id == "q001"
        assert result.question == "Test question?"
        assert result.answer == "Test answer"
        assert result.retrieval["hit_rate"] == 0.8
        assert result.sources == ["doc1.pdf", "doc2.pdf"]
        assert result.time_seconds == 1.5
        assert result.category == "fact_extraction"

    @pytest.mark.unit
    def test_optional_fields(self):
        result = TestCaseResult(
            id="q002",
            question="Test?",
            answer=None,
            error="Something went wrong",
        )
        assert result.retrieval is None
        assert result.sources is None
        assert result.error == "Something went wrong"


class TestExperimentResult:
    def _make_sample_dict(self):
        return {
            "timestamp": "2026-04-16T10:00:00",
            "total_test_cases": 3,
            "total_time_seconds": 10.5,
            "avg_time_per_case": 3.5,
            "retrieval_metrics": {
                "avg_hit_rate": 0.75,
                "avg_mrr": 0.6,
                "avg_ndcg": 0.65,
            },
            "results": [
                {
                    "id": "q001",
                    "question": "Question 1?",
                    "answer": "Answer 1",
                    "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                    "sources": ["doc1.pdf"],
                    "time_seconds": 3.0,
                    "category": "fact_extraction",
                },
                {
                    "id": "q002",
                    "question": "Question 2?",
                    "answer": "Answer 2",
                    "retrieval": {"hit_rate": 0.6, "mrr": 0.5, "ndcg": 0.55},
                    "sources": ["doc2.pdf"],
                    "time_seconds": 4.0,
                    "category": "summary",
                },
                {
                    "id": "q003",
                    "question": "Question 3?",
                    "answer": None,
                    "error": "Test error",
                    "time_seconds": 3.5,
                },
            ],
            "meal_data_id": "abc123def456",
            "meal_name": "test_meal",
            "config_snapshot": {
                "chunker": {"chunk_size": 512, "chunk_overlap": 0},
                "embedding": {"model_name": "BAAI/bge-large-zh-v1.5"},
            },
            "config_hashes": {"chunker": "abc123", "embedding": "def456"},
            "pdf_files": [
                {"path": "doc1.pdf", "size_bytes": 1024},
                {"path": "doc2.pdf", "size_bytes": 2048},
            ],
            "stats": {"total_pdfs": 2, "total_pages": 100},
        }

    @pytest.mark.unit
    def test_from_dict(self):
        data = self._make_sample_dict()
        result = ExperimentResult.from_dict(data)

        assert result.timestamp == "2026-04-16T10:00:00"
        assert result.total_test_cases == 3
        assert result.total_time_seconds == 10.5
        assert result.avg_time_per_case == 3.5
        assert result.retrieval_metrics["avg_hit_rate"] == 0.75
        assert len(result.results) == 3
        assert result.meal_data_id == "abc123def456"
        assert result.meal_name == "test_meal"

    @pytest.mark.unit
    def test_from_dict_results_conversion(self):
        data = self._make_sample_dict()
        result = ExperimentResult.from_dict(data)

        assert isinstance(result.results[0], TestCaseResult)
        assert result.results[0].id == "q001"
        assert result.results[0].category == "fact_extraction"
        assert result.results[2].error == "Test error"

    @pytest.mark.unit
    def test_from_dict_minimal(self):
        data = {
            "timestamp": "2026-04-16T10:00:00",
            "total_test_cases": 1,
            "total_time_seconds": 1.0,
            "avg_time_per_case": 1.0,
            "retrieval_metrics": {},
            "results": [],
        }
        result = ExperimentResult.from_dict(data)

        assert result.timestamp == "2026-04-16T10:00:00"
        assert result.total_test_cases == 1
        assert result.meal_data_id is None
        assert result.config_snapshot is None


class TestExperimentReporter:
    @pytest.fixture
    def sample_result(self):
        data = {
            "timestamp": "2026-04-16T10:00:00",
            "total_test_cases": 5,
            "total_time_seconds": 15.0,
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
                    "time_seconds": 2.5,
                    "category": "fact_extraction",
                },
                {
                    "id": "q002",
                    "question": "What is the profit?",
                    "answer": "Profit is 20M.",
                    "retrieval": {"hit_rate": 0.7, "mrr": 0.5, "ndcg": 0.6},
                    "sources": ["report2.pdf"],
                    "time_seconds": 3.0,
                    "category": "fact_extraction",
                },
                {
                    "id": "q003",
                    "question": "Summarize the annual report.",
                    "answer": "Summary...",
                    "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                    "sources": ["report1.pdf", "report2.pdf"],
                    "time_seconds": 4.0,
                    "category": "summary",
                },
                {
                    "id": "q004",
                    "question": "Compare Q1 and Q2.",
                    "answer": "Comparison...",
                    "retrieval": {"hit_rate": 0.6, "mrr": 0.4, "ndcg": 0.5},
                    "sources": ["report3.pdf"],
                    "time_seconds": 3.5,
                    "category": "comparison",
                },
                {
                    "id": "q005",
                    "question": "Analyze market trends.",
                    "answer": None,
                    "error": "Timeout",
                    "time_seconds": 2.0,
                    "category": "analysis",
                },
            ],
            "meal_data_id": "abc123def456789",
            "meal_name": "test_meal",
            "config_snapshot": {
                "chunker": {"chunk_size": 512, "chunk_overlap": 0},
                "embedding": {"model_name": "BAAI/bge-large-zh-v1.5"},
                "retrieval": {"top_k": 5},
            },
            "config_hashes": {"chunker": "abc123", "embedding": "def456"},
            "pdf_files": [
                {"path": "report1.pdf", "size_bytes": 1024000},
                {"path": "report2.pdf", "size_bytes": 2048000},
            ],
            "stats": {"total_pdfs": 2, "total_pages": 100, "total_chunks": 500},
        }
        return ExperimentResult.from_dict(data)

    @pytest.mark.unit
    def test_init(self):
        reporter = ExperimentReporter()
        assert reporter.llm_api_key is None
        assert reporter.llm_base_url is None

    @pytest.mark.unit
    def test_init_with_llm_config(self):
        reporter = ExperimentReporter(
            llm_api_key="test_key",
            llm_base_url="https://api.example.com",
            llm_model_name="test-model",
        )
        assert reporter.llm_api_key == "test_key"
        assert reporter.llm_base_url == "https://api.example.com"
        assert reporter.llm_model_name == "test-model"

    @pytest.mark.unit
    def test_generate_markdown_report_contains_all_sections(self, sample_result, tmp_path):
        reporter = ExperimentReporter()
        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result,
            use_llm=False,
        )

        assert "Experiment Overview" in report
        assert "Data Source" in report
        assert "Technical Configuration" in report
        assert "Test Set Information" in report
        assert "Evaluation Results" in report
        assert "Detailed Results Comparison" in report
        assert "Conclusions and Recommendations" in report
        assert "Experiment Assets" in report

    @pytest.mark.unit
    def test_generate_markdown_report_reflects_data(self, sample_result, tmp_path):
        reporter = ExperimentReporter()
        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result,
            use_llm=False,
        )

        assert "2026-04-16T10:00:00" in report
        assert "0.8" in report
        assert "What is the revenue?" in report
        assert "report1.pdf" in report
        assert "chunk_size" in report
        assert "BAAI/bge-large-zh-v1.5" in report
        assert "fact_extraction" in report
        assert "Timeout" in report

    @pytest.mark.unit
    def test_generate_markdown_report_saves_file(self, sample_result, tmp_path):
        reporter = ExperimentReporter()
        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result,
            use_llm=False,
            output_filename="test_report.md",
        )

        output_file = tmp_path / "test_report.md"
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            saved_content = f.read()
        assert saved_content == report

    @pytest.mark.unit
    def test_generate_markdown_report_creates_parent_dirs(self, sample_result, tmp_path):
        reporter = ExperimentReporter()
        nested_dir = tmp_path / "nested" / "path"

        reporter.generate_markdown_report(
            exp_dir=nested_dir,
            result=sample_result,
            use_llm=False,
        )

        assert (nested_dir / "experiment_report.md").exists()

    @pytest.mark.unit
    def test_llm_report_fallback_on_error(self, sample_result, tmp_path):
        reporter = ExperimentReporter(llm_api_key=None)

        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result,
            use_llm=True,
        )

        assert "# RAG Experiment Report" in report
        assert "## 1. Experiment Overview" in report

    @pytest.mark.unit
    @patch("eval.experiment_reporter.ExperimentReporter._call_llm")
    def test_llm_report_success(self, mock_call_llm, sample_result, tmp_path):
        mock_call_llm.return_value = "This is an LLM-generated analysis."

        reporter = ExperimentReporter(llm_api_key="test_key")
        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result,
            use_llm=True,
        )

        assert "# RAG Experiment Report" in report
        assert "LLM-generated analysis" in report
        mock_call_llm.assert_called_once()


class TestLLMPromptTemplate:
    @pytest.mark.unit
    def test_template_contains_required_sections(self):
        assert "实验概览" in LLM_REPORT_PROMPT_TEMPLATE
        assert "数据来源" in LLM_REPORT_PROMPT_TEMPLATE
        assert "技术配置" in LLM_REPORT_PROMPT_TEMPLATE
        assert "评测结果" in LLM_REPORT_PROMPT_TEMPLATE

    @pytest.mark.unit
    def test_template_contains_analysis_requirements(self):
        assert "实验概述" in LLM_REPORT_PROMPT_TEMPLATE
        assert "数据来源分析" in LLM_REPORT_PROMPT_TEMPLATE
        assert "技术选型分析" in LLM_REPORT_PROMPT_TEMPLATE
        assert "检索性能分析" in LLM_REPORT_PROMPT_TEMPLATE
        assert "生成质量分析" in LLM_REPORT_PROMPT_TEMPLATE
        assert "结论与建议" in LLM_REPORT_PROMPT_TEMPLATE

    @pytest.mark.unit
    def test_template_format_placeholders(self):
        formatted = LLM_REPORT_PROMPT_TEMPLATE.format(
            timestamp="2026-04-16",
            data_id="test123",
            total_test_cases=10,
            data_section="Data content",
            config_section="Config content",
            results_section="Results content",
        )
        assert "2026-04-16" in formatted
        assert "test123" in formatted
        assert "10" in formatted
        assert "Data content" in formatted
        assert "Config content" in formatted
        assert "Results content" in formatted


class TestVariantResult:
    @pytest.mark.unit
    def test_variant_result_creation(self):
        result = VariantResult(
            variant_name="test_variant",
            variant_description="Test variant description",
            retrieval_metrics={"avg_hit_rate": 0.8, "avg_mrr": 0.6, "avg_ndcg": 0.7},
            config_snapshot={"chunker": {"chunk_size": 512}},
            total_questions=20,
            total_time_seconds=30.5,
        )
        assert result.variant_name == "test_variant"
        assert result.variant_description == "Test variant description"
        assert result.retrieval_metrics["avg_hit_rate"] == 0.8
        assert result.total_questions == 20
        assert result.total_time_seconds == 30.5

    @pytest.mark.unit
    def test_variant_result_from_dict(self):
        data = {
            "variant_name": "baseline",
            "variant_description": "Baseline configuration",
            "retrieval_metrics": {"avg_hit_rate": 0.75, "avg_mrr": 0.55, "avg_ndcg": 0.65},
            "config_snapshot": {"chunker": {"chunk_size": 256}},
            "total_questions": 15,
            "total_time_seconds": 25.0,
        }
        result = VariantResult.from_dict(data)
        assert result.variant_name == "baseline"
        assert result.retrieval_metrics["avg_hit_rate"] == 0.75
        assert result.total_questions == 15

    @pytest.mark.unit
    def test_variant_result_with_error(self):
        data = {
            "variant_name": "failed_variant",
            "error": "Index build failed",
        }
        result = VariantResult.from_dict(data)
        assert result.variant_name == "failed_variant"
        assert result.error == "Index build failed"
        assert result.retrieval_metrics is None


class TestMultiVariantComparison:
    @pytest.fixture
    def sample_variant_results(self):
        return [
            {
                "variant_name": "baseline",
                "variant_description": "Baseline with chunk_size=512",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.75,
                    "avg_mrr": 0.60,
                    "avg_ndcg": 0.65,
                },
                "config_snapshot": {
                    "merged": {
                        "chunker": {"chunk_size": 512, "chunk_overlap": 0},
                        "embedding": {"model_name": "BAAI/bge-large-zh-v1.5"},
                    }
                },
                "total_questions": 20,
                "total_time_seconds": 30.0,
            },
            {
                "variant_name": "small_chunks",
                "variant_description": "Smaller chunks with chunk_size=256",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.85,
                    "avg_mrr": 0.70,
                    "avg_ndcg": 0.75,
                },
                "config_snapshot": {
                    "merged": {
                        "chunker": {"chunk_size": 256, "chunk_overlap": 0},
                        "embedding": {"model_name": "BAAI/bge-large-zh-v1.5"},
                    }
                },
                "total_questions": 20,
                "total_time_seconds": 35.0,
            },
            {
                "variant_name": "large_chunks",
                "variant_description": "Larger chunks with chunk_size=1024",
                "retrieval_metrics": {
                    "avg_hit_rate": 0.70,
                    "avg_mrr": 0.55,
                    "avg_ndcg": 0.60,
                },
                "config_snapshot": {
                    "merged": {
                        "chunker": {"chunk_size": 1024, "chunk_overlap": 0},
                        "embedding": {"model_name": "BAAI/bge-large-zh-v1.5"},
                    }
                },
                "total_questions": 20,
                "total_time_seconds": 28.0,
            },
        ]

    @pytest.fixture
    def sample_meal_info(self):
        return {
            "name": "test_meal",
            "data_id": "abc123def456789",
        }

    @pytest.fixture
    def sample_config_snapshot(self):
        return {
            "data": {"meal": "test_meal"},
            "test_sets": [{"strategy": "factual", "num_questions": 20}],
            "evaluation": {"llm_preset": "default"},
        }

    @pytest.mark.unit
    def test_generate_variant_comparison_report_contains_all_sections(
        self, sample_variant_results, sample_meal_info, sample_config_snapshot, tmp_path
    ):
        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=tmp_path,
            variant_results=sample_variant_results,
            meal_info=sample_meal_info,
            config_snapshot=sample_config_snapshot,
        )

        assert "Multi-Variant Experiment Report" in report
        assert "Variant Comparison Table" in report
        assert "Best Performing Variant" in report
        assert "Variant Details" in report
        assert "Common Configuration" in report
        assert "Recommendations" in report
        assert "baseline" in report
        assert "small_chunks" in report
        assert "large_chunks" in report
        assert "0.75" in report
        assert "0.85" in report
        assert "0.70" in report

    @pytest.mark.unit
    def test_generate_variant_comparison_report(self, sample_variant_results, sample_meal_info, sample_config_snapshot, tmp_path):
        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=tmp_path,
            variant_results=sample_variant_results,
            meal_info=sample_meal_info,
            config_snapshot=sample_config_snapshot,
            output_filename="test_variant_report.md",
        )

        output_file = tmp_path / "test_variant_report.md"
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            saved_content = f.read()
        assert saved_content == report

        assert "# RAG Multi-Variant Experiment Report" in report
        assert "## 1. Experiment Overview" in report
        assert "## 2. Variant Comparison Table" in report
        assert "## 3. Best Performing Variant" in report
        assert "## 4. Variant Details" in report
        assert "## 5. Common Configuration" in report
        assert "## 6. Recommendations" in report
        assert "test_meal" in report
        assert "small_chunks ⭐" in report

    @pytest.mark.unit
    def test_variant_report_with_failures(self, tmp_path):
        variant_results = [
            {
                "variant_name": "success",
                "variant_description": "Successful variant",
                "retrieval_metrics": {"avg_hit_rate": 0.7, "avg_mrr": 0.6, "avg_ndcg": 0.65},
                "total_questions": 10,
                "total_time_seconds": 15.0,
            },
            {
                "variant_name": "failed",
                "variant_description": "Failed variant",
                "error": "Index build failed",
            },
        ]

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=tmp_path,
            variant_results=variant_results,
            output_filename="test_report.md",
        )

        assert "success ⭐" in report
        assert "failed" in report
        assert "ERROR" in report

    @pytest.mark.unit
    def test_variant_report_all_failures(self, tmp_path):
        variant_results = [
            {"variant_name": "failed_1", "error": "Error 1"},
            {"variant_name": "failed_2", "error": "Error 2"},
        ]

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=tmp_path,
            variant_results=variant_results,
            output_filename="test_report.md",
        )

        assert "Failed Variants**: 2" in report
        assert "No successful variants to compare" in report

    @pytest.mark.unit
    def test_variant_recommendations_with_low_performance(self, tmp_path):
        variant_results = [
            {
                "variant_name": "low_perf",
                "variant_description": "Low performance variant",
                "retrieval_metrics": {"avg_hit_rate": 0.3, "avg_mrr": 0.3, "avg_ndcg": 0.3},
                "total_questions": 10,
                "total_time_seconds": 15.0,
            },
        ]

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=tmp_path,
            variant_results=variant_results,
            output_filename="test_report.md",
        )

        assert "Low retrieval performance" in report
        assert "top_k" in report
        assert "hybrid retrieval" in report

    @pytest.mark.unit
    def test_variant_recommendations_with_high_performance(self, tmp_path):
        variant_results = [
            {
                "variant_name": "high_perf",
                "variant_description": "High performance variant",
                "retrieval_metrics": {"avg_hit_rate": 0.9, "avg_mrr": 0.85, "avg_ndcg": 0.88},
                "total_questions": 10,
                "total_time_seconds": 15.0,
            },
        ]

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=tmp_path,
            variant_results=variant_results,
            output_filename="test_report.md",
        )

        assert "Excellent retrieval performance" in report
        assert "satisfactory performance" in report


class TestGenerationMetrics:
    @pytest.fixture
    def sample_result_with_generation(self):
        data = {
            "timestamp": "2026-04-16T10:00:00",
            "total_test_cases": 3,
            "total_time_seconds": 10.0,
            "avg_time_per_case": 3.33,
            "retrieval_metrics": {
                "avg_hit_rate": 0.8,
                "avg_mrr": 0.65,
                "avg_ndcg": 0.7,
            },
            "generation_metrics": {
                "avg_faithfulness": 0.85,
                "avg_answer_relevancy": 0.75,
            },
            "results": [
                {
                    "id": "q001",
                    "question": "What is the revenue?",
                    "answer": "Revenue is 100M.",
                    "retrieval": {"hit_rate": 0.9, "mrr": 0.8, "ndcg": 0.85},
                    "generation": {"faithfulness": 0.9, "answer_relevancy": 0.8},
                    "sources": ["report1.pdf"],
                    "time_seconds": 3.0,
                    "category": "fact_extraction",
                },
                {
                    "id": "q002",
                    "question": "What is the profit?",
                    "answer": "Profit is 20M.",
                    "retrieval": {"hit_rate": 0.7, "mrr": 0.5, "ndcg": 0.6},
                    "generation": {"faithfulness": 0.8, "answer_relevancy": 0.7},
                    "sources": ["report2.pdf"],
                    "time_seconds": 3.5,
                    "category": "fact_extraction",
                },
                {
                    "id": "q003",
                    "question": "Summarize the report.",
                    "answer": "Summary...",
                    "retrieval": {"hit_rate": 0.8, "mrr": 0.7, "ndcg": 0.75},
                    "generation": {"faithfulness": 0.85, "answer_relevancy": 0.75},
                    "sources": ["report1.pdf"],
                    "time_seconds": 3.5,
                    "category": "summary",
                },
            ],
            "meal_data_id": "abc123def456789",
            "meal_name": "test_meal",
        }
        return ExperimentResult.from_dict(data)

    @pytest.mark.unit
    def test_result_with_generation_metrics(self, sample_result_with_generation):
        result = sample_result_with_generation
        assert result.generation_metrics is not None
        assert result.generation_metrics["avg_faithfulness"] == 0.85
        assert result.generation_metrics["avg_answer_relevancy"] == 0.75

    @pytest.mark.unit
    def test_test_case_result_with_generation(self, sample_result_with_generation):
        result = sample_result_with_generation
        assert result.results[0].generation is not None
        assert result.results[0].generation["faithfulness"] == 0.9
        assert result.results[0].generation["answer_relevancy"] == 0.8

    @pytest.mark.unit
    def test_report_contains_generation_metrics_section(self, sample_result_with_generation, tmp_path):
        reporter = ExperimentReporter()
        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result_with_generation,
            use_llm=False,
        )

        assert "Generation Quality Metrics" in report
        assert "Faithfulness" in report
        assert "Answer Relevancy" in report
        assert "0.85" in report
        assert "0.75" in report

    @pytest.mark.unit
    def test_report_comparison_table_with_generation(self, sample_result_with_generation, tmp_path):
        reporter = ExperimentReporter()
        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result_with_generation,
            use_llm=False,
        )

        assert "Faithfulness" in report
        assert "Relevancy" in report

    @pytest.mark.unit
    def test_report_conclusion_with_generation_analysis(self, sample_result_with_generation, tmp_path):
        reporter = ExperimentReporter()
        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result_with_generation,
            use_llm=False,
        )

        assert "Generation Quality Summary" in report
        assert "well-grounded" in report or "grounded" in report.lower()

    @pytest.mark.unit
    def test_variant_result_with_generation_metrics(self):
        data = {
            "variant_name": "test_variant",
            "variant_description": "Test variant with generation metrics",
            "retrieval_metrics": {"avg_hit_rate": 0.8, "avg_mrr": 0.6, "avg_ndcg": 0.7},
            "generation_metrics": {"avg_faithfulness": 0.85, "avg_answer_relevancy": 0.75},
            "total_questions": 10,
            "total_time_seconds": 30.0,
        }
        result = VariantResult.from_dict(data)
        assert result.generation_metrics is not None
        assert result.generation_metrics["avg_faithfulness"] == 0.85
        assert result.generation_metrics["avg_answer_relevancy"] == 0.75

    @pytest.mark.unit
    def test_variant_report_with_generation_metrics(self, tmp_path):
        variant_results = [
            {
                "variant_name": "baseline",
                "variant_description": "Baseline variant",
                "retrieval_metrics": {"avg_hit_rate": 0.75, "avg_mrr": 0.60, "avg_ndcg": 0.65},
                "generation_metrics": {"avg_faithfulness": 0.80, "avg_answer_relevancy": 0.70},
                "total_questions": 20,
                "total_time_seconds": 30.0,
            },
            {
                "variant_name": "optimized",
                "variant_description": "Optimized variant",
                "retrieval_metrics": {"avg_hit_rate": 0.85, "avg_mrr": 0.70, "avg_ndcg": 0.75},
                "generation_metrics": {"avg_faithfulness": 0.90, "avg_answer_relevancy": 0.80},
                "total_questions": 20,
                "total_time_seconds": 35.0,
            },
        ]

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=tmp_path,
            variant_results=variant_results,
            output_filename="test_report.md",
        )

        assert "Faithfulness" in report
        assert "Relevancy" in report
        assert "0.80" in report
        assert "0.90" in report
        assert "Generation Quality Analysis" in report

    @pytest.mark.unit
    def test_variant_report_generation_quality_recommendations(self, tmp_path):
        variant_results = [
            {
                "variant_name": "low_gen_quality",
                "variant_description": "Low generation quality variant",
                "retrieval_metrics": {"avg_hit_rate": 0.8, "avg_mrr": 0.6, "avg_ndcg": 0.7},
                "generation_metrics": {"avg_faithfulness": 0.4, "avg_answer_relevancy": 0.3},
                "total_questions": 10,
                "total_time_seconds": 15.0,
            },
        ]

        reporter = ExperimentReporter()
        report = reporter.generate_variant_comparison_report(
            exp_dir=tmp_path,
            variant_results=variant_results,
            output_filename="test_report.md",
        )

        assert "hallucinations" in report.lower() or "prompt engineering" in report.lower()

    @pytest.mark.unit
    def test_backward_compatibility_without_generation_metrics(self, tmp_path):
        data = {
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
                {
                    "id": "q002",
                    "question": "What is the profit?",
                    "answer": "Profit is 20M.",
                    "retrieval": {"hit_rate": 0.7, "mrr": 0.5, "ndcg": 0.6},
                    "sources": ["report2.pdf"],
                    "time_seconds": 3.0,
                },
            ],
        }
        result = ExperimentResult.from_dict(data)

        assert result.generation_metrics is None
        assert result.results[0].generation is None

        reporter = ExperimentReporter()
        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=result,
            use_llm=False,
        )

        assert "Experiment Overview" in report
        assert "Evaluation Results" in report
        assert "Generation Quality Metrics" not in report


class TestGenerationMetricDescription:
    @pytest.mark.unit
    def test_unprefixed_metric_descriptions(self):
        reporter = ExperimentReporter()
        assert "grounded" in reporter._get_generation_metric_description("avg_faithfulness").lower()
        assert "relevant" in reporter._get_generation_metric_description("avg_answer_relevancy").lower()

    @pytest.mark.unit
    def test_builtin_prefixed_metric_descriptions(self):
        reporter = ExperimentReporter()
        desc = reporter._get_generation_metric_description("avg_builtin_faithfulness")
        assert "Builtin" in desc
        assert "grounded" in desc.lower()

        desc = reporter._get_generation_metric_description("avg_builtin_answer_relevancy")
        assert "Builtin" in desc
        assert "relevant" in desc.lower()

    @pytest.mark.unit
    def test_ragas_prefixed_metric_descriptions(self):
        reporter = ExperimentReporter()
        desc = reporter._get_generation_metric_description("avg_ragas_faithfulness")
        assert "RAGAS" in desc
        assert "grounded" in desc.lower()

        desc = reporter._get_generation_metric_description("avg_ragas_answer_relevancy")
        assert "RAGAS" in desc
        assert "relevant" in desc.lower()

        desc = reporter._get_generation_metric_description("avg_ragas_context_precision")
        assert "RAGAS" in desc
        assert "precise" in desc.lower()

        desc = reporter._get_generation_metric_description("avg_ragas_context_recall")
        assert "RAGAS" in desc
        assert "completely" in desc.lower()

        desc = reporter._get_generation_metric_description("avg_ragas_answer_correctness")
        assert "RAGAS" in desc
        assert "correct" in desc.lower()

    @pytest.mark.unit
    def test_unknown_prefixed_metric_fallback(self):
        reporter = ExperimentReporter()
        desc = reporter._get_generation_metric_description("avg_ragas_some_new_metric")
        assert "RAGAS" in desc

        desc = reporter._get_generation_metric_description("avg_builtin_some_new_metric")
        assert "BUILTIN" in desc

    @pytest.mark.unit
    def test_completely_unknown_metric_fallback(self):
        reporter = ExperimentReporter()
        desc = reporter._get_generation_metric_description("avg_unknown_metric")
        assert desc == "Generation quality metric"
