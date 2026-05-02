from __future__ import annotations

import json

import pytest

from eval.parser_benchmark.metrics import (
    DocumentMetrics,
    PageMetrics,
    _analyze_table,
    _check_markdown_valid,
    _count_headings,
    _find_markdown_tables,
    compute_document_metrics,
    compute_page_metrics,
)
from eval.parser_benchmark.report_generator import ReportGenerator
from eval.parser_benchmark.test_cases import TestCaseManager

TABLE_MD = (
    "| Header 1 | Header 2 | Header 3 |\n"
    "|---|---|---|\n"
    "| Cell 1 | Cell 2 | Cell 3 |\n"
    "| Cell 4 | Cell 5 | Cell 6 |"
)

HEADING_MD = "# Main Title\n## Section 1\nSome text here\n### Subsection\nMore text"

MIXED_MD = (
    "# Report\n"
    "\n"
    "Introduction paragraph.\n"
    "\n"
    "| Col A | Col B |\n"
    "|---|---|\n"
    "| 1 | 2 |\n"
    "| 3 | 4 |\n"
    "\n"
    "## Details\n"
    "More content.\n"
)


@pytest.mark.unit
class TestComputePageMetrics:
    def test_mixed_content(self):
        result = compute_page_metrics(MIXED_MD, 1)
        assert result.page_number == 1
        assert result.char_count == len(MIXED_MD)
        assert result.word_count == len(MIXED_MD.split())
        assert result.table_count == 1
        assert result.heading_count == 2
        assert result.markdown_valid is True

    def test_empty_text(self):
        result = compute_page_metrics("", 5)
        assert result.page_number == 5
        assert result.char_count == 0
        assert result.word_count == 0
        assert result.table_count == 0
        assert result.heading_count == 0
        assert result.markdown_valid is False

    def test_no_tables(self):
        result = compute_page_metrics(HEADING_MD, 1)
        assert result.table_count == 0
        assert result.table_rows == []
        assert result.table_cols == []
        assert result.table_empty_ratios == []
        assert result.heading_count == 3

    def test_with_table(self):
        result = compute_page_metrics(TABLE_MD, 2)
        assert result.page_number == 2
        assert result.table_count == 1
        assert result.table_rows == [3]
        assert result.table_cols == [3]
        assert result.table_empty_ratios == [0.0]


@pytest.mark.unit
class TestComputeDocumentMetrics:
    def test_aggregation(self):
        p1 = PageMetrics(
            page_number=1,
            char_count=100,
            word_count=20,
            table_count=1,
            table_rows=[3],
            table_cols=[3],
            table_empty_ratios=[0.0],
            heading_count=2,
            markdown_valid=True,
        )
        p2 = PageMetrics(
            page_number=2,
            char_count=200,
            word_count=40,
            table_count=0,
            table_rows=[],
            table_cols=[],
            table_empty_ratios=[],
            heading_count=1,
            markdown_valid=True,
        )
        result = compute_document_metrics("pipeline_a", "/tmp/test.pdf", [p1, p2], 1.5)
        assert result.pipeline_name == "pipeline_a"
        assert result.pdf_path == "/tmp/test.pdf"
        assert result.page_count == 2
        assert result.total_chars == 300
        assert result.total_words == 60
        assert result.total_tables == 1
        assert result.avg_table_rows == 3.0
        assert result.avg_table_cols == 3.0
        assert result.avg_table_empty_ratio == 0.0
        assert result.total_headings == 3
        assert result.markdown_valid_pages == 2
        assert result.markdown_valid_ratio == 1.0
        assert result.parse_time_seconds == 1.5

    def test_empty_page_list(self):
        result = compute_document_metrics("p", "f", [])
        assert result.page_count == 0
        assert result.total_chars == 0
        assert result.total_words == 0
        assert result.total_tables == 0
        assert result.avg_table_rows == 0.0
        assert result.avg_table_cols == 0.0
        assert result.avg_table_empty_ratio == 0.0
        assert result.markdown_valid_ratio == 0.0


@pytest.mark.unit
class TestFindMarkdownTables:
    def test_single_table(self):
        tables = _find_markdown_tables(TABLE_MD)
        assert len(tables) == 1
        assert "Header 1" in tables[0]

    def test_no_table(self):
        tables = _find_markdown_tables("Just plain text\nNo tables here")
        assert tables == []

    def test_multiple_tables(self):
        text = TABLE_MD + "\n\nSome text\n\n" + TABLE_MD
        tables = _find_markdown_tables(text)
        assert len(tables) == 2

    def test_table_without_separator_skipped(self):
        text = "| A | B |\n| 1 | 2 |"
        tables = _find_markdown_tables(text)
        assert tables == []


@pytest.mark.unit
class TestAnalyzeTable:
    def test_standard_table(self):
        rows, cols, empty = _analyze_table(TABLE_MD)
        assert rows == 3
        assert cols == 3
        assert empty == 0.0

    def test_table_with_empty_cells(self):
        table = "| A | B |\n|---|---|\n| 1 |  |"
        rows, cols, empty = _analyze_table(table)
        assert rows == 2
        assert cols == 2
        assert empty == pytest.approx(0.25)

    def test_separator_only_table(self):
        table = "|---|---|\n"
        rows, cols, empty = _analyze_table(table)
        assert rows == 0
        assert cols == 0
        assert empty == 1.0


@pytest.mark.unit
class TestCountHeadings:
    def test_multiple_headings(self):
        assert _count_headings(HEADING_MD) == 3

    def test_no_headings(self):
        assert _count_headings("Just plain text") == 0

    def test_h1_only(self):
        assert _count_headings("# Title") == 1

    def test_not_a_heading(self):
        assert _count_headings("#NoSpace") == 0

    def test_empty_text(self):
        assert _count_headings("") == 0


@pytest.mark.unit
class TestCheckMarkdownValid:
    def test_valid_text(self):
        assert _check_markdown_valid("Some content") is True

    def test_empty_text(self):
        assert _check_markdown_valid("") is False

    def test_whitespace_only(self):
        assert _check_markdown_valid("   \n\t  ") is False


@pytest.mark.unit
class TestTestCaseManager:
    def test_load_from_config_nonexistent_files(self):
        manager = TestCaseManager()
        cases = manager.load_from_config(["/nonexistent/file.pdf"])
        assert cases == []
        assert manager.cases == []

    def test_load_from_config_with_existing_file(self, tmp_path):
        pdf = tmp_path / "sample.pdf"
        pdf.write_text("fake pdf")
        annotation = tmp_path / "sample.annotation.json"
        annotation.write_text(json.dumps({"tables": 2}))

        manager = TestCaseManager()
        cases = manager.load_from_config([str(pdf)])
        assert len(cases) == 1
        assert cases[0]["pdf_path"] == str(pdf)
        assert "ground_truth" in cases[0]
        assert cases[0]["ground_truth"]["tables"] == 2

    def test_cases_property_empty(self):
        manager = TestCaseManager()
        assert manager.cases == []

    def test_cases_property_after_load(self, tmp_path):
        pdf = tmp_path / "doc.pdf"
        pdf.write_text("fake")
        manager = TestCaseManager()
        manager.load_from_config([str(pdf)])
        assert len(manager.cases) == 1


@pytest.mark.unit
class TestReportGenerator:
    def _make_doc_metrics(self, pipeline_name: str, pdf_path: str) -> DocumentMetrics:
        return DocumentMetrics(
            pipeline_name=pipeline_name,
            pdf_path=pdf_path,
            page_count=3,
            total_chars=500,
            total_words=100,
            total_tables=2,
            avg_table_rows=4.0,
            avg_table_cols=3.0,
            avg_table_empty_ratio=0.1,
            total_headings=5,
            markdown_valid_pages=3,
            markdown_valid_ratio=1.0,
            parse_time_seconds=2.5,
        )

    def test_generate_creates_files(self, tmp_path):
        run_dir = tmp_path / "run_001"
        run_dir.mkdir()
        metrics_a = self._make_doc_metrics("pipeline_a", "/tmp/a.pdf")
        metrics_b = self._make_doc_metrics("pipeline_b", "/tmp/b.pdf")
        all_results = {
            "pipeline_a": [metrics_a],
            "pipeline_b": [metrics_b],
        }

        gen = ReportGenerator(run_dir)
        report_path = gen.generate(all_results)

        assert report_path.exists()
        assert report_path.name == "report.md"

        comparison_path = run_dir / "results" / "comparison.json"
        assert comparison_path.exists()

        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        assert "pipeline_a" in comparison
        assert "pipeline_b" in comparison
        assert comparison["pipeline_a"]["pdfs_tested"] == 1
        assert comparison["pipeline_a"]["total_tables"] == 2

        report_text = report_path.read_text(encoding="utf-8")
        assert "pipeline_a" in report_text
        assert "pipeline_b" in report_text

    def test_generate_empty_results(self, tmp_path):
        run_dir = tmp_path / "run_002"
        run_dir.mkdir()
        gen = ReportGenerator(run_dir)
        report_path = gen.generate({})

        assert report_path.exists()
        comparison_path = run_dir / "results" / "comparison.json"
        assert comparison_path.exists()
        comparison = json.loads(comparison_path.read_text(encoding="utf-8"))
        assert comparison == {}
