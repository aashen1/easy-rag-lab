from __future__ import annotations

from unittest.mock import patch

import pytest

from src.parsers.base import ParseResult
from src.parsers.pymupdf4llm_parser import PyMuPDF4LLMParser


class TestPyMuPDF4LLMParserName:
    def test_name_returns_pymupdf4llm(self):
        parser = PyMuPDF4LLMParser()
        assert parser.name == "pymupdf4llm"


class TestPyMuPDF4LLMParserWholeDocument:
    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_whole_document_mode_returns_single_page(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "# Test Document\n\nThis is test content."

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        parser = PyMuPDF4LLMParser()
        result = parser.parse(str(pdf_file))

        assert isinstance(result, ParseResult)
        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
        assert result.pages[0].text == "# Test Document\n\nThis is test content."
        assert result.metadata["parser"] == "pymupdf4llm"
        assert result.metadata["page_count"] == 1
        assert result.metadata["source"] == str(pdf_file)
        mock_to_markdown.assert_called_once_with(str(pdf_file))

    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_whole_document_metadata_contains_source(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "Some text"

        pdf_file = tmp_path / "doc.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest")

        parser = PyMuPDF4LLMParser()
        result = parser.parse(str(pdf_file))

        assert result.pages[0].metadata["source"] == str(pdf_file)


class TestPyMuPDF4LLMParserPageChunks:
    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_page_chunks_mode_returns_multiple_pages(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = [
            {"text": "Page 1 content", "metadata": {"page_number": 1}},
            {"text": "Page 2 content", "metadata": {"page_number": 2}},
            {"text": "Page 3 content", "metadata": {"page_number": 3}},
        ]

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        parser = PyMuPDF4LLMParser(config={"page_chunks": True})
        result = parser.parse(str(pdf_file))

        assert len(result.pages) == 3
        assert result.pages[0].page_number == 1
        assert result.pages[0].text == "Page 1 content"
        assert result.pages[1].page_number == 2
        assert result.pages[1].text == "Page 2 content"
        assert result.pages[2].page_number == 3
        assert result.pages[2].text == "Page 3 content"
        assert result.metadata["page_count"] == 3
        mock_to_markdown.assert_called_once_with(str(pdf_file), page_chunks=True)

    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_page_chunks_fallback_page_number(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = [
            {"text": "Page A", "metadata": {}},
            {"text": "Page B", "metadata": {}},
        ]

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest")

        parser = PyMuPDF4LLMParser(config={"page_chunks": True})
        result = parser.parse(str(pdf_file))

        assert result.pages[0].page_number == 1
        assert result.pages[1].page_number == 2

    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_page_chunks_missing_metadata_key(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = [
            {"text": "No metadata page"},
        ]

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest")

        parser = PyMuPDF4LLMParser(config={"page_chunks": True})
        result = parser.parse(str(pdf_file))

        assert len(result.pages) == 1
        assert result.pages[0].page_number == 1
        assert result.pages[0].text == "No metadata page"
        assert result.pages[0].metadata == {}


class TestPyMuPDF4LLMParserFileNotFound:
    def test_raises_file_not_found_for_missing_file(self):
        parser = PyMuPDF4LLMParser()
        with pytest.raises(FileNotFoundError) as exc_info:
            parser.parse("nonexistent.pdf")
        assert "PDF file not found" in str(exc_info.value)


class TestPyMuPDF4LLMParserNotAPdf:
    def test_raises_value_error_for_non_pdf(self, tmp_path):
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a pdf")

        parser = PyMuPDF4LLMParser()
        with pytest.raises(ValueError) as exc_info:
            parser.parse(str(txt_file))
        assert "File is not a PDF" in str(exc_info.value)


class TestPyMuPDF4LLMParserOptionsPassthrough:
    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_options_passed_to_to_markdown(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = [
            {"text": "Result", "metadata": {"page_number": 1}},
        ]

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest")

        parser = PyMuPDF4LLMParser(config={
            "page_chunks": True,
            "ignore_images": True,
            "table_strategy": "lines",
        })
        parser.parse(str(pdf_file))

        mock_to_markdown.assert_called_once_with(
            str(pdf_file),
            page_chunks=True,
            ignore_images=True,
            table_strategy="lines",
        )

    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_page_chunks_excluded_from_options(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "Result"

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest")

        parser = PyMuPDF4LLMParser(config={"page_chunks": False})
        parser.parse(str(pdf_file))

        call_kwargs = mock_to_markdown.call_args
        assert "page_chunks" not in call_kwargs.kwargs

    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_empty_config_defaults(self, mock_to_markdown, tmp_path):
        mock_to_markdown.return_value = "Result"

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest")

        parser = PyMuPDF4LLMParser()
        parser.parse(str(pdf_file))

        mock_to_markdown.assert_called_once_with(str(pdf_file))


class TestPyMuPDF4LLMParserParseFailure:
    @patch("src.parsers.pymupdf4llm_parser.pymupdf4llm.to_markdown")
    def test_raises_exception_on_parse_failure(self, mock_to_markdown, tmp_path):
        mock_to_markdown.side_effect = RuntimeError("Parse error")

        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4\ntest pdf content")

        parser = PyMuPDF4LLMParser()
        with pytest.raises(Exception) as exc_info:
            parser.parse(str(pdf_file))
        assert "Failed to parse PDF" in str(exc_info.value)
