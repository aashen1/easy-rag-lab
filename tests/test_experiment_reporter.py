import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from eval.experiment_reporter import (
    ExperimentReporter,
    ExperimentResult,
    TestCaseResult,
    VariantResult,
    LLM_REPORT_PROMPT_TEMPLATE,
)


class TestTestCaseResult:
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

    def test_from_dict_results_conversion(self):
        data = self._make_sample_dict()
        result = ExperimentResult.from_dict(data)

        assert isinstance(result.results[0], TestCaseResult)
        assert result.results[0].id == "q001"
        assert result.results[0].category == "fact_extraction"
        assert result.results[2].error == "Test error"

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

    def test_init(self):
        reporter = ExperimentReporter()
        assert reporter.llm_api_key is None
        assert reporter.llm_base_url is None

    def test_init_with_llm_config(self):
        reporter = ExperimentReporter(
            llm_api_key="test_key",
            llm_base_url="https://api.example.com",
            llm_model_name="test-model",
        )
        assert reporter.llm_api_key == "test_key"
        assert reporter.llm_base_url == "https://api.example.com"
        assert reporter.llm_model_name == "test-model"

    def test_generate_template_report(self, sample_result, tmp_path):
        reporter = ExperimentReporter()
        report = reporter._generate_template_report(sample_result)

        assert "# RAG Experiment Report" in report
        assert "## 1. Experiment Overview" in report
        assert "## 2. Data Source" in report
        assert "## 3. Technical Configuration" in report
        assert "## 4. Test Set Information" in report
        assert "## 5. Evaluation Results" in report
        assert "## 6. Detailed Results Comparison" in report
        assert "## 7. Conclusions and Recommendations" in report
        assert "## 8. Experiment Assets" in report

    def test_generate_overview_section(self, sample_result):
        reporter = ExperimentReporter()
        section = reporter._generate_overview_section(sample_result)

        assert "## 1. Experiment Overview" in section
        assert "2026-04-16T10:00:00" in section
        assert "5" in section
        assert "15.0" in section

    def test_generate_data_section(self, sample_result):
        reporter = ExperimentReporter()
        section = reporter._generate_data_section(sample_result)

        assert "## 2. Data Source" in section
        assert "report1.pdf" in section
        assert "report2.pdf" in section
        assert "Total Pdfs" in section or "Total PDFs" in section

    def test_generate_config_section(self, sample_result):
        reporter = ExperimentReporter()
        section = reporter._generate_config_section(sample_result)

        assert "## 3. Technical Configuration" in section
        assert "chunk_size" in section
        assert "BAAI/bge-large-zh-v1.5" in section

    def test_generate_test_set_section(self, sample_result):
        reporter = ExperimentReporter()
        section = reporter._generate_test_set_section(sample_result)

        assert "## 4. Test Set Information" in section
        assert "fact_extraction" in section
        assert "summary" in section
        assert "comparison" in section

    def test_generate_results_section(self, sample_result):
        reporter = ExperimentReporter()
        section = reporter._generate_results_section(sample_result)

        assert "## 5. Evaluation Results" in section
        assert "Overall Retrieval Metrics" in section
        assert "0.8" in section
        assert "Results by Question Category" in section
        assert "Errors" in section

    def test_generate_comparison_table(self, sample_result):
        reporter = ExperimentReporter()
        section = reporter._generate_comparison_table(sample_result)

        assert "## 6. Detailed Results Comparison" in section
        assert "q001" in section
        assert "q002" in section
        assert "Hit Rate" in section
        assert "MRR" in section
        assert "NDCG" in section

    def test_generate_conclusion_section(self, sample_result):
        reporter = ExperimentReporter()
        section = reporter._generate_conclusion_section(sample_result)

        assert "## 7. Conclusions and Recommendations" in section
        assert "Performance Summary" in section
        assert "Recommendations" in section

    def test_generate_assets_section(self, sample_result):
        reporter = ExperimentReporter()
        section = reporter._generate_assets_section(sample_result)

        assert "## 8. Experiment Assets" in section
        assert "baseline_report.json" in section
        assert "experiment_report.md" in section

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

        with open(output_file, "r", encoding="utf-8") as f:
            saved_content = f.read()
        assert saved_content == report

    def test_generate_markdown_report_creates_parent_dirs(self, sample_result, tmp_path):
        reporter = ExperimentReporter()
        nested_dir = tmp_path / "nested" / "path"

        reporter.generate_markdown_report(
            exp_dir=nested_dir,
            result=sample_result,
            use_llm=False,
        )

        assert (nested_dir / "experiment_report.md").exists()

    def test_llm_prompt_template_format(self, sample_result):
        reporter = ExperimentReporter()
        prompt = reporter._build_llm_prompt(sample_result)

        assert "实验时间" in prompt
        assert "2026-04-16T10:00:00" in prompt
        assert "数据ID" in prompt
        assert "测试用例总数" in prompt
        assert "5" in prompt

    def test_llm_report_fallback_on_error(self, sample_result, tmp_path):
        reporter = ExperimentReporter(llm_api_key=None)

        report = reporter.generate_markdown_report(
            exp_dir=tmp_path,
            result=sample_result,
            use_llm=True,
        )

        assert "# RAG Experiment Report" in report
        assert "## 1. Experiment Overview" in report

    @patch("eval.experiment_reporter.ExperimentReporter._init_llm_client")
    @patch("eval.experiment_reporter.ExperimentReporter._call_llm")
    def test_llm_report_success(self, mock_call_llm, mock_init, sample_result, tmp_path):
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

    def test_format_llm_report(self, sample_result):
        reporter = ExperimentReporter()
        llm_response = "This is the LLM analysis content."

        formatted = reporter._format_llm_report(sample_result, llm_response)

        assert "# RAG Experiment Report" in formatted
        assert "LLM assistance" in formatted
        assert "This is the LLM analysis content." in formatted

    def test_report_with_no_pdf_files(self, tmp_path):
        result = ExperimentResult(
            timestamp="2026-04-16T10:00:00",
            total_test_cases=1,
            total_time_seconds=1.0,
            avg_time_per_case=1.0,
            retrieval_metrics={"avg_hit_rate": 0.5},
            results=[
                TestCaseResult(id="q1", question="Test?", answer="Answer")
            ],
        )

        reporter = ExperimentReporter()
        report = reporter._generate_template_report(result)

        assert "## 2. Data Source" in report

    def test_report_with_many_pdf_files(self, tmp_path):
        pdf_files = [{"path": f"doc{i}.pdf", "size_bytes": 1024} for i in range(30)]
        result = ExperimentResult(
            timestamp="2026-04-16T10:00:00",
            total_test_cases=1,
            total_time_seconds=1.0,
            avg_time_per_case=1.0,
            retrieval_metrics={"avg_hit_rate": 0.5},
            results=[
                TestCaseResult(id="q1", question="Test?", answer="Answer")
            ],
            pdf_files=pdf_files,
        )

        reporter = ExperimentReporter()
        report = reporter._generate_template_report(result)

        assert "doc0.pdf" in report
        assert "and 10 more files" in report

    def test_report_with_many_results(self, tmp_path):
        results = [
            TestCaseResult(
                id=f"q{i:03d}",
                question=f"Question {i}?",
                answer=f"Answer {i}",
                retrieval={"hit_rate": 0.5, "mrr": 0.5, "ndcg": 0.5},
                time_seconds=1.0,
            )
            for i in range(60)
        ]
        result = ExperimentResult(
            timestamp="2026-04-16T10:00:00",
            total_test_cases=60,
            total_time_seconds=60.0,
            avg_time_per_case=1.0,
            retrieval_metrics={"avg_hit_rate": 0.5, "avg_mrr": 0.5, "avg_ndcg": 0.5},
            results=results,
        )

        reporter = ExperimentReporter()
        report = reporter._generate_template_report(result)

        assert "q000" in report
        assert "and 10 more results" in report

    def test_conclusion_with_low_hit_rate(self):
        result = ExperimentResult(
            timestamp="2026-04-16T10:00:00",
            total_test_cases=1,
            total_time_seconds=1.0,
            avg_time_per_case=1.0,
            retrieval_metrics={"avg_hit_rate": 0.3, "avg_mrr": 0.3, "avg_ndcg": 0.3},
            results=[TestCaseResult(id="q1", question="Test?", answer="Answer")],
        )

        reporter = ExperimentReporter()
        section = reporter._generate_conclusion_section(result)

        assert "Needs Improvement" in section
        assert "top_k" in section

    def test_conclusion_with_high_metrics(self):
        result = ExperimentResult(
            timestamp="2026-04-16T10:00:00",
            total_test_cases=1,
            total_time_seconds=1.0,
            avg_time_per_case=1.0,
            retrieval_metrics={"avg_hit_rate": 0.9, "avg_mrr": 0.8, "avg_ndcg": 0.85},
            results=[TestCaseResult(id="q1", question="Test?", answer="Answer")],
        )

        reporter = ExperimentReporter()
        section = reporter._generate_conclusion_section(result)

        assert "Excellent" in section or "satisfactory" in section


class TestLLMPromptTemplate:
    def test_template_contains_required_sections(self):
        assert "实验概览" in LLM_REPORT_PROMPT_TEMPLATE
        assert "数据来源" in LLM_REPORT_PROMPT_TEMPLATE
        assert "技术配置" in LLM_REPORT_PROMPT_TEMPLATE
        assert "评测结果" in LLM_REPORT_PROMPT_TEMPLATE

    def test_template_contains_analysis_requirements(self):
        assert "实验概述" in LLM_REPORT_PROMPT_TEMPLATE
        assert "数据来源分析" in LLM_REPORT_PROMPT_TEMPLATE
        assert "技术选型分析" in LLM_REPORT_PROMPT_TEMPLATE
        assert "评测结果分析" in LLM_REPORT_PROMPT_TEMPLATE
        assert "结论与建议" in LLM_REPORT_PROMPT_TEMPLATE

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

    def test_find_best_variant(self, sample_variant_results):
        reporter = ExperimentReporter()
        best = reporter._find_best_variant(sample_variant_results)

        assert best is not None
        assert best["variant_name"] == "small_chunks"
        assert best["retrieval_metrics"]["avg_hit_rate"] == 0.85

    def test_find_best_variant_with_failures(self):
        variant_results = [
            {
                "variant_name": "failed_1",
                "error": "Index build failed",
            },
            {
                "variant_name": "success",
                "retrieval_metrics": {"avg_hit_rate": 0.6, "avg_mrr": 0.5, "avg_ndcg": 0.55},
                "total_questions": 10,
                "total_time_seconds": 15.0,
            },
            {
                "variant_name": "failed_2",
                "error": "Timeout",
            },
        ]

        reporter = ExperimentReporter()
        best = reporter._find_best_variant(variant_results)

        assert best is not None
        assert best["variant_name"] == "success"

    def test_find_best_variant_all_failed(self):
        variant_results = [
            {"variant_name": "failed_1", "error": "Error 1"},
            {"variant_name": "failed_2", "error": "Error 2"},
        ]

        reporter = ExperimentReporter()
        best = reporter._find_best_variant(variant_results)

        assert best is None

    def test_generate_variant_comparison_table(self, sample_variant_results):
        reporter = ExperimentReporter()
        section = reporter._generate_variant_comparison_table_section(sample_variant_results)

        assert "## 2. Variant Comparison Table" in section
        assert "baseline" in section
        assert "small_chunks" in section
        assert "large_chunks" in section
        assert "0.75" in section
        assert "0.85" in section
        assert "0.70" in section
        assert "⭐" in section

    def test_generate_best_variant_section(self, sample_variant_results):
        reporter = ExperimentReporter()
        section = reporter._generate_best_variant_section(sample_variant_results)

        assert "## 3. Best Performing Variant" in section
        assert "small_chunks" in section
        assert "0.85" in section
        assert "chunk_size: 256" in section

    def test_generate_variant_details_section(self, sample_variant_results):
        reporter = ExperimentReporter()
        section = reporter._generate_variant_details_section(sample_variant_results)

        assert "## 4. Variant Details" in section
        assert "baseline" in section
        assert "small_chunks" in section
        assert "large_chunks" in section
        assert "Retrieval Metrics" in section

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

        with open(output_file, "r", encoding="utf-8") as f:
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
