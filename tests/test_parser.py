import json
from pathlib import Path
from unittest.mock import patch

import pytest

from src.exceptions import ParsingError
from src.parser import parse_all_pdfs, parse_pdf


class TestParsePdf:
    def test_parse_pdf_file_not_found(self):
        with pytest.raises(ParsingError) as exc_info:
            parse_pdf("nonexistent.pdf")
        assert "PDF file not found" in str(exc_info.value)

    def test_parse_pdf_not_a_pdf(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("test content")

        with pytest.raises(ParsingError) as exc_info:
            parse_pdf(str(txt_file))
        assert "File is not a PDF" in str(exc_info.value)

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_pdf_success(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        result = parse_pdf(str(pdf_file))
        assert isinstance(result, str)
        assert len(result) > 0
        assert "Test Document" in result

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_pdf_failure(self, mock_to_markdown, tmp_path):
        mock_to_markdown.side_effect = Exception("Parse error")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        with pytest.raises(ParsingError) as exc_info:
            parse_pdf(str(pdf_file))
        assert "Failed to parse PDF" in str(exc_info.value)


class TestParseAllPdfs:
    def test_parse_all_pdfs_input_dir_not_found(self):
        with pytest.raises(ParsingError) as exc_info:
            parse_all_pdfs("nonexistent_dir", "output_dir")
        assert "Input directory not found" in str(exc_info.value)

    def test_parse_all_pdfs_no_pdfs(self, tmp_path):
        results = parse_all_pdfs(str(tmp_path), str(tmp_path / "output"))
        assert results == []

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_with_pdfs(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pdf_file = input_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        results = parse_all_pdfs(str(input_dir), str(output_dir))

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert results[0]["category"] == "unknown"

        output_file = Path(results[0]["output"])
        assert output_file.exists()
        assert output_file.suffix == ".md"

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_with_category_mapping(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pdf_file = input_dir / "annual_report_2023.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        category_mapping = {"annual_report": "annual_report"}

        results = parse_all_pdfs(
            str(input_dir), str(output_dir), category_mapping=category_mapping
        )

        assert len(results) == 1
        assert results[0]["category"] == "annual_report"

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_auto_category_detection(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        annual_report_dir = input_dir / "annual_reports"
        annual_report_dir.mkdir()
        pdf_file1 = annual_report_dir / "test1.pdf"
        pdf_file1.write_bytes(b"%PDF-1.4\ntest pdf content")

        research_report_dir = input_dir / "research_reports"
        research_report_dir.mkdir()
        pdf_file2 = research_report_dir / "test2.pdf"
        pdf_file2.write_bytes(b"%PDF-1.4\ntest pdf content")

        results = parse_all_pdfs(str(input_dir), str(output_dir))

        assert len(results) == 2
        categories = [r["category"] for r in results]
        assert "annual_report" in categories
        assert "research_report" in categories

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_with_failures(self, mock_to_markdown, tmp_path):
        call_count = [0]

        def side_effect_func(path, **kwargs):
            call_count[0] += 1
            if call_count[0] == 1:
                return "# Valid Document\n\nThis is valid content."
            else:
                raise Exception("Parse error")

        mock_to_markdown.side_effect = side_effect_func

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pdf_file1 = input_dir / "valid.pdf"
        pdf_file1.write_bytes(b"%PDF-1.4\ntest pdf content")

        pdf_file2 = input_dir / "invalid.pdf"
        pdf_file2.write_bytes(b"not a real pdf")

        results = parse_all_pdfs(str(input_dir), str(output_dir))

        assert len(results) == 2
        success_count = sum(1 for r in results if r["status"] == "success")
        failed_count = sum(1 for r in results if r["status"] == "failed")

        assert success_count == 1
        assert failed_count == 1

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_skip_existing(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pdf_file = input_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        output_file = output_dir / "test.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("# Existing content\n\nAlready parsed.")

        results = parse_all_pdfs(str(input_dir), str(output_dir), force=False)

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert mock_to_markdown.call_count == 0

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_force_reparse(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pdf_file = input_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        output_file = output_dir / "test.md"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text("# Existing content\n\nAlready parsed.")

        results = parse_all_pdfs(str(input_dir), str(output_dir), force=True)

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert mock_to_markdown.call_count == 1

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_preserves_directory_structure(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"

        nested_dir = input_dir / "annual_reports" / "2023" / "五粮液"
        nested_dir.mkdir(parents=True)

        pdf_file = nested_dir / "2023年度报告_英文_.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        results = parse_all_pdfs(str(input_dir), str(output_dir))

        assert len(results) == 1
        assert results[0]["status"] == "success"

        expected_output = output_dir / "annual_reports" / "2023" / "五粮液" / "2023年度报告_英文_.md"
        actual_output = Path(results[0]["output"])

        assert actual_output == expected_output
        assert actual_output.exists()

        with open(actual_output, encoding="utf-8") as f:
            content = f.read()
        assert "Test Document" in content

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_pdf_page_chunks_true(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = [
            {"page": 1, "text": "Page 1 content"},
            {"page": 2, "text": "Page 2 content"},
        ]

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        result = parse_pdf(str(pdf_file), page_chunks=True)
        assert isinstance(result, list)
        assert len(result) == 2
        assert result[0]["text"] == "Page 1 content"
        mock_to_markdown.assert_called_once_with(
            str(pdf_file), page_chunks=True
        )

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_pdf_page_chunks_false(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        result = parse_pdf(str(pdf_file), page_chunks=False)
        assert isinstance(result, str)
        assert "Test Document" in result
        mock_to_markdown.assert_called_once_with(
            str(pdf_file), page_chunks=False
        )

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_page_chunks_output(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = [
            {"page": 1, "text": "Page 1 content"},
            {"page": 2, "text": "Page 2 content"},
        ]

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pdf_file = input_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        results = parse_all_pdfs(
            str(input_dir), str(output_dir), parser_options={"page_chunks": True}
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert results[0]["format"] == "pages_json"

        output_file = Path(results[0]["output"])
        assert output_file.name.endswith(".pages.json")
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)
        assert isinstance(data, list)
        assert len(data) == 2
        assert data[0]["text"] == "Page 1 content"

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_page_chunks_skip_existing(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = [
            {"page": 1, "text": "Page 1 content"},
        ]

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pdf_file = input_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        output_file = output_dir / "test.pages.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text('[{"page": 1, "text": "existing"}]')

        results = parse_all_pdfs(
            str(input_dir), str(output_dir), force=False, parser_options={"page_chunks": True}
        )

        assert len(results) == 1
        assert results[0]["status"] == "skipped"
        assert mock_to_markdown.call_count == 0

    @patch("src.parser.pymupdf4llm.to_markdown")
    def test_parse_all_pdfs_page_chunks_force_reparse(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = [
            {"page": 1, "text": "New page 1 content"},
        ]

        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pdf_file = input_dir / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        output_file = output_dir / "test.pages.json"
        output_file.parent.mkdir(parents=True, exist_ok=True)
        output_file.write_text('[{"page": 1, "text": "existing"}]')

        results = parse_all_pdfs(
            str(input_dir), str(output_dir), force=True, parser_options={"page_chunks": True}
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert mock_to_markdown.call_count == 1

        with open(output_file, encoding="utf-8") as f:
            data = json.load(f)
        assert data[0]["text"] == "New page 1 content"
