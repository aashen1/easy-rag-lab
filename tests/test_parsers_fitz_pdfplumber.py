from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.exceptions import ParsingError
from src.parsers.base import ParsedPage, ParseResult
from src.parsers.fitz_parser import FitzParser, _TextBlock
from src.parsers.fitz_pdfplumber_parser import FitzPdfPlumberParser
from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer


@pytest.fixture
def parser() -> FitzPdfPlumberParser:
    return FitzPdfPlumberParser()


@pytest.fixture
def fitz_parser() -> FitzParser:
    return FitzParser()


@pytest.fixture
def fitz_parser_no_filters() -> FitzParser:
    return FitzParser(
        config={
            "header_filter": False,
            "footer_filter": False,
            "noise_patterns": [],
        }
    )


@pytest.fixture
def enhancer() -> PdfPlumberEnhancer:
    return PdfPlumberEnhancer()


class TestNameProperty:
    def test_name_returns_fitz_pdfplumber(self, parser: FitzPdfPlumberParser) -> None:
        assert parser.name == "fitz_pdfplumber"


class TestIsNoise:
    def test_header_zone_short_text_filtered(self, fitz_parser: FitzParser) -> None:
        bbox = (0, 5, 100, 20)
        result = fitz_parser._is_noise("Header text", bbox, page_height=800)
        assert result is True

    def test_header_zone_long_text_not_filtered(self, fitz_parser: FitzParser) -> None:
        long_text = "A" * 81
        bbox = (0, 5, 100, 20)
        result = fitz_parser._is_noise(long_text, bbox, page_height=800)
        assert result is False

    def test_footer_zone_short_text_filtered(self, fitz_parser: FitzParser) -> None:
        bbox = (0, 740, 100, 790)
        result = fitz_parser._is_noise("Footer text", bbox, page_height=800)
        assert result is True

    def test_footer_zone_long_text_not_filtered(self, fitz_parser: FitzParser) -> None:
        long_text = "A" * 81
        bbox = (0, 740, 100, 790)
        result = fitz_parser._is_noise(long_text, bbox, page_height=800)
        assert result is False

    def test_noise_pattern_page_number(self, fitz_parser: FitzParser) -> None:
        bbox = (0, 400, 100, 410)
        result = fitz_parser._is_noise("  42  ", bbox, page_height=800)
        assert result is True

    def test_noise_pattern_fraction(self, fitz_parser: FitzParser) -> None:
        bbox = (0, 400, 100, 410)
        result = fitz_parser._is_noise("3 / 15", bbox, page_height=800)
        assert result is True

    def test_noise_pattern_url(self, fitz_parser: FitzParser) -> None:
        bbox = (0, 400, 100, 410)
        result = fitz_parser._is_noise("www.example.com", bbox, page_height=800)
        assert result is True

    def test_normal_text_not_filtered(self, fitz_parser: FitzParser) -> None:
        bbox = (0, 200, 100, 220)
        result = fitz_parser._is_noise(
            "This is normal body text.", bbox, page_height=800
        )
        assert result is False

    def test_filters_disabled(self, fitz_parser_no_filters: FitzParser) -> None:
        bbox = (0, 5, 100, 20)
        result = fitz_parser_no_filters._is_noise("Header text", bbox, page_height=800)
        assert result is False


class TestDetectColumns:
    def test_single_column_page(self, fitz_parser: FitzParser) -> None:
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.get_text.return_value = [
            (72, 100, 540, 110, "text", 0, 0),
            (72, 120, 540, 130, "text", 0, 0),
            (72, 140, 540, 150, "text", 0, 0),
        ]
        result = fitz_parser._detect_columns(mock_page)
        assert result == 1

    def test_two_column_page(self, fitz_parser: FitzParser) -> None:
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.get_text.return_value = [
            (72, 100, 290, 110, "text", 0, 0),
            (72, 120, 290, 130, "text", 0, 0),
            (72, 140, 290, 150, "text", 0, 0),
            (322, 100, 540, 110, "text", 0, 0),
            (322, 120, 540, 130, "text", 0, 0),
            (322, 140, 540, 150, "text", 0, 0),
        ]
        result = fitz_parser._detect_columns(mock_page)
        assert result == 2

    def test_column_detection_disabled(self) -> None:
        p = FitzParser(config={"column_detection": False})
        mock_page = MagicMock()
        result = p._detect_columns(mock_page)
        assert result == 1

    def test_empty_page(self, fitz_parser: FitzParser) -> None:
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.get_text.return_value = []
        result = fitz_parser._detect_columns(mock_page)
        assert result == 1


class TestTableToMarkdown:
    def test_simple_table(self, enhancer: PdfPlumberEnhancer) -> None:
        data = [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ]
        result = enhancer._table_to_markdown(data)
        lines = result.split("\n")
        assert len(lines) == 4
        assert lines[0] == "| Name | Age |"
        assert lines[1] == "|---|---|"
        assert lines[2] == "| Alice | 30 |"
        assert lines[3] == "| Bob | 25 |"

    def test_table_with_none_values(self, enhancer: PdfPlumberEnhancer) -> None:
        data = [
            ["A", "B"],
            [None, "X"],
        ]
        result = enhancer._table_to_markdown(data)
        assert "|  | X |" in result

    def test_table_with_newlines_in_cells(self, enhancer: PdfPlumberEnhancer) -> None:
        data = [
            ["Header"],
            ["cell\nwith\nnewlines"],
        ]
        result = enhancer._table_to_markdown(data)
        assert "cell with newlines" in result

    def test_empty_table(self, enhancer: PdfPlumberEnhancer) -> None:
        result = enhancer._table_to_markdown([])
        assert result == ""

    def test_table_with_uneven_rows(self, enhancer: PdfPlumberEnhancer) -> None:
        data = [
            ["A", "B", "C"],
            ["1"],
            ["2", "3"],
        ]
        result = enhancer._table_to_markdown(data)
        lines = result.split("\n")
        assert "|---|---|---|" in lines[1]
        assert "| 1 |  |  |" in lines[2]
        assert "| 2 | 3 |  |" in lines[3]

    def test_sparse_rows_filtered(self, enhancer: PdfPlumberEnhancer) -> None:
        data = [
            ["", "", "", "Header Noise"],
            ["Code", "Name", "Price", "PE"],
            ["600519", "Moutai", "1413", "19.7"],
            ["000858", "Wuliangye", "103", "14.1"],
        ]
        result = enhancer._table_to_markdown(data)
        assert "Header Noise" not in result
        assert "| Code | Name | Price | PE |" in result
        assert "| 600519 | Moutai | 1413 | 19.7 |" in result

    def test_sparse_rows_not_filtered_for_small_tables(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        data = [
            ["A", "B"],
            ["", "X"],
        ]
        result = enhancer._table_to_markdown(data)
        assert "|  | X |" in result

    def test_sparse_rows_fallback_when_all_sparse(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        data = [
            ["", "", "", "X"],
            ["A", "", "", ""],
            ["", "B", "", ""],
        ]
        result = enhancer._table_to_markdown(data)
        assert result != ""

    def test_dense_rows_preserved(self, enhancer: PdfPlumberEnhancer) -> None:
        data = [
            ["A", "B", "C", "D"],
            ["1", "2", "3", "4"],
            ["5", "6", "", "8"],
        ]
        result = enhancer._table_to_markdown(data)
        assert "| A | B | C | D |" in result
        assert "| 1 | 2 | 3 | 4 |" in result
        assert "| 5 | 6 |  | 8 |" in result


class TestBlocksToMarkdown:
    def test_text_blocks(self, fitz_parser: FitzParser) -> None:
        blocks = [
            _TextBlock(
                page_number=1, block_type="text", content="Hello", bbox=(0, 0, 100, 10)
            ),
            _TextBlock(
                page_number=1, block_type="text", content="World", bbox=(0, 20, 100, 30)
            ),
        ]
        result = fitz_parser._blocks_to_markdown(blocks)
        assert result == "Hello\n\nWorld"

    def test_heading_detection_h1(self, fitz_parser: FitzParser) -> None:
        block = _TextBlock(
            page_number=1,
            block_type="text",
            content="Title",
            bbox=(0, 0, 100, 10),
            font_size=18,
            is_bold=True,
        )
        blocks = [block]
        result = fitz_parser._blocks_to_markdown(blocks)
        assert result == "# Title"

    def test_heading_detection_h2(self, fitz_parser: FitzParser) -> None:
        block = _TextBlock(
            page_number=1,
            block_type="text",
            content="Section",
            bbox=(0, 0, 100, 10),
            font_size=15,
            is_bold=True,
        )
        result = fitz_parser._blocks_to_markdown([block])
        assert result == "## Section"

    def test_heading_detection_h3(self, fitz_parser: FitzParser) -> None:
        block = _TextBlock(
            page_number=1,
            block_type="text",
            content="Subsection",
            bbox=(0, 0, 100, 10),
            font_size=13,
            is_bold=True,
        )
        result = fitz_parser._blocks_to_markdown([block])
        assert result == "### Subsection"

    def test_heading_detection_h4(self, fitz_parser: FitzParser) -> None:
        block = _TextBlock(
            page_number=1,
            block_type="text",
            content="Sub-sub",
            bbox=(0, 0, 100, 10),
            font_size=11.5,
            is_bold=True,
        )
        result = fitz_parser._blocks_to_markdown([block])
        assert result == "#### Sub-sub"

    def test_no_heading_for_non_bold(self, fitz_parser: FitzParser) -> None:
        block = _TextBlock(
            page_number=1,
            block_type="text",
            content="Not heading",
            bbox=(0, 0, 100, 10),
            font_size=18,
            is_bold=False,
        )
        result = fitz_parser._blocks_to_markdown([block])
        assert result == "Not heading"

    def test_table_block(self, fitz_parser: FitzParser) -> None:
        blocks = [
            _TextBlock(
                page_number=1,
                block_type="table",
                content="| A | B |\n|---|---|\n| 1 | 2 |",
                bbox=(0, 0, 100, 50),
            ),
        ]
        result = fitz_parser._blocks_to_markdown(blocks)
        assert "| A | B |" in result

    def test_image_block(self, fitz_parser: FitzParser) -> None:
        blocks = [
            _TextBlock(
                page_number=1,
                block_type="image",
                content="[图片: 页1]",
                bbox=(0, 0, 100, 50),
            ),
        ]
        result = fitz_parser._blocks_to_markdown(blocks)
        assert "[图片: 页1]" in result

    def test_empty_blocks(self, fitz_parser: FitzParser) -> None:
        result = fitz_parser._blocks_to_markdown([])
        assert result == ""


class TestParseFileErrors:
    def test_file_not_found(self, parser: FitzPdfPlumberParser) -> None:
        with pytest.raises(ParsingError) as exc_info:
            parser.parse("nonexistent.pdf")
        assert "PDF file not found" in str(exc_info.value)

    def test_not_a_pdf(self, parser: FitzPdfPlumberParser, tmp_path) -> None:
        txt_file = tmp_path / "test.txt"
        txt_file.write_text("not a pdf")
        with pytest.raises(ParsingError) as exc_info:
            parser.parse(str(txt_file))
        assert "File is not a PDF" in str(exc_info.value)


@pytest.mark.unit
class TestAppendTables:
    def test_append_to_existing_text(self, enhancer: PdfPlumberEnhancer) -> None:
        text = "Some paragraph text."
        tables = ["| A | B |\n|---|---|\n| 1 | 2 |"]
        result = enhancer._append_tables(text, tables)
        assert result.startswith("Some paragraph text.")
        assert "| A | B |" in result
        assert "| 1 | 2 |" in result

    def test_append_multiple_tables(self, enhancer: PdfPlumberEnhancer) -> None:
        text = "Body text"
        tables = [
            "| A | B |\n|---|---|\n| 1 | 2 |",
            "| X | Y |\n|---|---|\n| 3 | 4 |",
        ]
        result = enhancer._append_tables(text, tables)
        assert "| A | B |" in result
        assert "| X | Y |" in result

    def test_append_to_empty_text(self, enhancer: PdfPlumberEnhancer) -> None:
        tables = ["| A | B |\n|---|---|\n| 1 | 2 |"]
        result = enhancer._append_tables("", tables)
        assert result.startswith("| A | B |")

    def test_append_no_tables(self, enhancer: PdfPlumberEnhancer) -> None:
        result = enhancer._append_tables("Some text", [])
        assert result == "Some text"


@pytest.mark.unit
class TestEnhanceAppendMode:
    def test_enhance_appends_tables_when_no_md_tables(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        page_text = "This page has no markdown tables."
        result = ParseResult(
            pages=[ParsedPage(page_number=1, text=page_text, metadata={})],
            metadata={"parser": "fitz"},
        )

        original_extract = enhancer._extract_tables
        enhancer._extract_tables = lambda pdf_path, page_idx: [
            "| Col1 | Col2 | Col3 |\n|---|---|---|\n| a | b | c |\n| d | e | f |"
        ]

        try:
            enhanced = enhancer.enhance("dummy.pdf", result)
        finally:
            enhancer._extract_tables = original_extract

        assert len(enhanced.pages) == 1
        enhanced_text = enhanced.pages[0].text
        assert "This page has no markdown tables." in enhanced_text
        assert "| Col1 | Col2 | Col3 |" in enhanced_text
        assert "| a | b | c |" in enhanced_text

    def test_enhance_no_change_when_no_plumber_tables(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        page_text = "No tables here."
        result = ParseResult(
            pages=[ParsedPage(page_number=1, text=page_text, metadata={})],
            metadata={"parser": "fitz"},
        )

        original_extract = enhancer._extract_tables
        enhancer._extract_tables = lambda pdf_path, page_idx: []

        try:
            enhanced = enhancer.enhance("dummy.pdf", result)
        finally:
            enhancer._extract_tables = original_extract

        assert enhanced.pages[0].text == page_text

    def test_enhance_replaces_existing_md_tables(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        page_text = "Text before\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nText after"
        result = ParseResult(
            pages=[ParsedPage(page_number=1, text=page_text, metadata={})],
            metadata={"parser": "pymupdf4llm"},
        )

        original_extract = enhancer._extract_tables
        enhancer._extract_tables = lambda pdf_path, page_idx: [
            "| A | B |\n|---|---|\n| x | y |\n| 1 | 2 |"
        ]

        try:
            enhanced = enhancer.enhance("dummy.pdf", result)
        finally:
            enhancer._extract_tables = original_extract

        enhanced_text = enhanced.pages[0].text
        assert "Text before" in enhanced_text
        assert "Text after" in enhanced_text


@pytest.mark.unit
class TestCountTableQuality:
    def test_merged_ratio_with_br_tags(self, enhancer: PdfPlumberEnhancer) -> None:
        md = "| A<br>B | C |\n|---|---|\n| 1 | 2 |"
        _, _, _, _, merged_ratio = enhancer._count_table_quality(md)
        assert merged_ratio > 0

    def test_merged_ratio_zero_without_br(self, enhancer: PdfPlumberEnhancer) -> None:
        md = "| A | B |\n|---|---|\n| 1 | 2 |"
        _, _, _, _, merged_ratio = enhancer._count_table_quality(md)
        assert merged_ratio == 0.0

    def test_empty_table_returns_zero_merged(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        result = enhancer._count_table_quality("")
        assert result == (0, 0, 0, 1.0, 0.0)

    def test_multiple_br_cells(self, enhancer: PdfPlumberEnhancer) -> None:
        md = "| X<br>Y | A<br>B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        _, _, _, _, merged_ratio = enhancer._count_table_quality(md)
        assert merged_ratio == pytest.approx(1 / 3)


@pytest.mark.unit
class TestIsBetterQuality:
    def test_orig_merged_plumber_clean_plumber_wins(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig = "| A<br>B | C |\n|---|---|\n| 1 | 2 |"
        plumber = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        assert enhancer._is_better_quality(orig, plumber) is True

    def test_plumber_merged_orig_clean_orig_wins(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        plumber = "| X<br>Y | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        assert enhancer._is_better_quality(orig, plumber) is False

    def test_both_merged_default_plumber(self, enhancer: PdfPlumberEnhancer) -> None:
        orig = "| A<br>B | C |\n|---|---|\n| 1 | 2 |"
        plumber = "| X<br>Y | C |\n|---|---|\n| 1 | 2 |"
        assert enhancer._is_better_quality(orig, plumber) is True

    def test_empty_ratio_significant_plumber_wins(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig = "| A | B | C | D |\n|---|---|---|---|\n| 1 |  |  | 4 |"
        plumber = "| A | B | C | D |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |"
        assert enhancer._is_better_quality(orig, plumber) is True

    def test_empty_ratio_significant_orig_wins(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig = "| A | B | C | D |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |"
        plumber = "| A | B | C | D |\n|---|---|---|---|\n| 1 |  |  | 4 |"
        assert enhancer._is_better_quality(orig, plumber) is False

    def test_row_count_significant_plumber_wins(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig = "| A | B |\n|---|---|\n| 1 | 2 |"
        plumber = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |"
        assert enhancer._is_better_quality(orig, plumber) is True

    def test_row_count_significant_orig_wins(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig = "| A | B |\n|---|---|\n| 1 | 2 |\n| 3 | 4 |\n| 5 | 6 |"
        plumber = "| A | B |\n|---|---|\n| 1 | 2 |"
        assert enhancer._is_better_quality(orig, plumber) is False

    def test_similar_quality_defaults_to_plumber(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |"
        plumber = "| X | Y | Z |\n|---|---|---|\n| 4 | 5 | 6 |"
        assert enhancer._is_better_quality(orig, plumber) is True

    def test_row_count_not_significant_defaults_to_plumber(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig = "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |\n| 7 | 8 | 9 |\n| 10 | 11 | 12 |"
        plumber = (
            "| A | B | C |\n|---|---|---|\n| x | y | z |\n| p | q | r |\n| s | t | u |"
        )
        assert enhancer._is_better_quality(orig, plumber) is True


@pytest.mark.unit
class TestNoDuplicateTables:
    def test_replace_tables_no_duplicate(self, enhancer: PdfPlumberEnhancer) -> None:
        page_text = "Before\n\n| A | B |\n|---|---|\n| 1 | 2 |\n\nAfter"
        result = ParseResult(
            pages=[ParsedPage(page_number=1, text=page_text, metadata={})],
            metadata={"parser": "pymupdf4llm"},
        )

        orig_extract = enhancer._extract_tables
        enhancer._extract_tables = lambda pdf_path, page_idx: [
            "| A | B |\n|---|---|\n| x | y |"
        ]

        try:
            enhanced = enhancer.enhance("dummy.pdf", result)
        finally:
            enhancer._extract_tables = orig_extract

        text = enhanced.pages[0].text
        assert text.count("|---|---|") == 1

    def test_append_tables_no_duplicate(self, enhancer: PdfPlumberEnhancer) -> None:
        page_text = "No tables here."
        result = ParseResult(
            pages=[ParsedPage(page_number=1, text=page_text, metadata={})],
            metadata={"parser": "fitz"},
        )

        orig_extract = enhancer._extract_tables
        enhancer._extract_tables = lambda pdf_path, page_idx: [
            "| A | B | C |\n|---|---|---|\n| 1 | 2 | 3 |\n| 4 | 5 | 6 |"
        ]

        try:
            enhanced = enhancer.enhance("dummy.pdf", result)
        finally:
            enhancer._extract_tables = orig_extract

        text = enhanced.pages[0].text
        assert text.count("|---|---|---|") == 1

    def test_better_wins_replaces_low_quality_orig(
        self, enhancer: PdfPlumberEnhancer
    ) -> None:
        orig_table = "| A<br>B | C | D |\n|---|---|---|\n| 1 | 2 | 3 |"
        page_text = f"Before\n\n{orig_table}\n\nAfter"
        result = ParseResult(
            pages=[ParsedPage(page_number=1, text=page_text, metadata={})],
            metadata={"parser": "pymupdf4llm"},
        )

        orig_extract = enhancer._extract_tables
        enhancer._extract_tables = lambda pdf_path, page_idx: [
            "| A | B | C | D |\n|---|---|---|---|\n| 1 | 2 | 3 | 4 |\n| 5 | 6 | 7 | 8 |"
        ]

        try:
            enhanced = enhancer.enhance("dummy.pdf", result)
        finally:
            enhancer._extract_tables = orig_extract

        text = enhanced.pages[0].text
        assert "A<br>B" not in text
        assert "| A | B | C | D |" in text
