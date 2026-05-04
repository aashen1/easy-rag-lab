from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.parsers.base import ParsedPage, ParseResult


@pytest.fixture
def sample_parse_result():
    return ParseResult(
        pages=[
            ParsedPage(page_number=1, text="Page 1 text with some content."),
            ParsedPage(page_number=2, text="Page 2 text with more content."),
        ],
        metadata={"source": "test.pdf", "total_pages": 2},
    )


@pytest.fixture
def mock_parser():
    parser = MagicMock()
    parser.parse.return_value = ParseResult(
        pages=[ParsedPage(page_number=1, text="Parsed text")],
        metadata={"source": "test.pdf"},
    )
    return parser


@pytest.fixture
def mock_enhancer():
    enhancer = MagicMock()
    enhancer.enhance_page.return_value = "Enhanced page text"
    enhancer.enhance_table.return_value = "Enhanced table text"
    return enhancer


class TestParsePdf:
    def test_parse_pdf_with_legacy_parser(self, mock_parser, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        with patch("src.core.ops.parse.ParserRegistry") as mock_registry:
            mock_registry.get.return_value = mock_parser
            from src.core.ops.parse import parse_pdf

            result = parse_pdf(str(pdf_file), parser_name="pymupdf4llm")

        assert len(result.pages) == 1
        assert result.pages[0].text == "Parsed text"
        mock_registry.get.assert_called_once_with(name="pymupdf4llm", config=None)

    def test_parse_pdf_with_composite_parser(
        self, mock_parser, mock_enhancer, tmp_path
    ):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        composite = MagicMock()
        composite.parse.return_value = ParseResult(
            pages=[ParsedPage(page_number=1, text="Composite parsed")],
            metadata={"source": "test.pdf"},
        )

        with patch("src.core.ops.parse.ParserRegistry") as mock_registry:
            mock_registry.get_composite.return_value = composite
            from src.core.ops.parse import parse_pdf

            result = parse_pdf(
                str(pdf_file),
                parser_name="pymupdf4llm",
                enhancer_name="pdfplumber",
            )

        assert result.pages[0].text == "Composite parsed"
        mock_registry.get_composite.assert_called_once()

    def test_parse_pdf_file_not_found(self):
        from src.core.ops.parse import parse_pdf

        with pytest.raises(FileNotFoundError, match="PDF file not found"):
            parse_pdf("/nonexistent/path/test.pdf")

    def test_parse_pdf_with_parser_options(self, mock_parser, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        with patch("src.core.ops.parse.ParserRegistry") as mock_registry:
            mock_registry.get.return_value = mock_parser
            from src.core.ops.parse import parse_pdf

            parse_pdf(
                str(pdf_file), parser_name="pymupdf4llm", parser_options={"key": "val"}
            )

        mock_registry.get.assert_called_once_with(
            name="pymupdf4llm", config={"key": "val"}
        )


class TestEnhancePage:
    def test_enhance_page_delegates_to_enhancer(self, mock_enhancer, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        with patch("src.core.ops.parse.ParserRegistry") as mock_registry:
            mock_registry.get_enhancer.return_value = mock_enhancer
            from src.core.ops.parse import enhance_page

            result = enhance_page(str(pdf_file), 5, "existing text")

        assert result == "Enhanced page text"
        mock_enhancer.enhance_page.assert_called_once_with(
            str(pdf_file), 5, "existing text"
        )

    def test_enhance_page_file_not_found(self):
        from src.core.ops.parse import enhance_page

        with pytest.raises(FileNotFoundError):
            enhance_page("/nonexistent/test.pdf", 1, "text")


class TestEnhanceTable:
    def test_enhance_table_delegates_to_enhancer(self, mock_enhancer, tmp_path):
        pdf_file = tmp_path / "test.pdf"
        pdf_file.write_bytes(b"%PDF-1.4 fake")

        with patch("src.core.ops.parse.ParserRegistry") as mock_registry:
            mock_registry.get_enhancer.return_value = mock_enhancer
            from src.core.ops.parse import enhance_table

            result = enhance_table(str(pdf_file), 3, 2, "existing text")

        assert result == "Enhanced table text"
        mock_enhancer.enhance_table.assert_called_once_with(
            str(pdf_file), 3, 2, "existing text"
        )

    def test_enhance_table_file_not_found(self):
        from src.core.ops.parse import enhance_table

        with pytest.raises(FileNotFoundError):
            enhance_table("/nonexistent/test.pdf", 1, 1, "text")
