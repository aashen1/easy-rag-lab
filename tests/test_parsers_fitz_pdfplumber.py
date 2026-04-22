from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from src.exceptions import ParsingError
from src.parsers.fitz_pdfplumber_parser import (
    FitzPdfPlumberParser,
    _TextBlock,
)


@pytest.fixture
def parser() -> FitzPdfPlumberParser:
    return FitzPdfPlumberParser()


@pytest.fixture
def parser_no_filters() -> FitzPdfPlumberParser:
    return FitzPdfPlumberParser(config={
        "header_filter": False,
        "footer_filter": False,
        "noise_patterns": [],
    })


class TestNameProperty:
    def test_name_returns_fitz_pdfplumber(self, parser: FitzPdfPlumberParser) -> None:
        assert parser.name == "fitz_pdfplumber"


class TestIsNoise:
    def test_header_zone_short_text_filtered(self, parser: FitzPdfPlumberParser) -> None:
        bbox = (0, 5, 100, 20)
        result = parser._is_noise("Header text", bbox, page_height=800)
        assert result is True

    def test_header_zone_long_text_not_filtered(self, parser: FitzPdfPlumberParser) -> None:
        long_text = "A" * 81
        bbox = (0, 5, 100, 20)
        result = parser._is_noise(long_text, bbox, page_height=800)
        assert result is False

    def test_footer_zone_short_text_filtered(self, parser: FitzPdfPlumberParser) -> None:
        bbox = (0, 740, 100, 790)
        result = parser._is_noise("Footer text", bbox, page_height=800)
        assert result is True

    def test_footer_zone_long_text_not_filtered(self, parser: FitzPdfPlumberParser) -> None:
        long_text = "A" * 81
        bbox = (0, 740, 100, 790)
        result = parser._is_noise(long_text, bbox, page_height=800)
        assert result is False

    def test_noise_pattern_page_number(self, parser: FitzPdfPlumberParser) -> None:
        bbox = (0, 400, 100, 410)
        result = parser._is_noise("  42  ", bbox, page_height=800)
        assert result is True

    def test_noise_pattern_fraction(self, parser: FitzPdfPlumberParser) -> None:
        bbox = (0, 400, 100, 410)
        result = parser._is_noise("3 / 15", bbox, page_height=800)
        assert result is True

    def test_noise_pattern_url(self, parser: FitzPdfPlumberParser) -> None:
        bbox = (0, 400, 100, 410)
        result = parser._is_noise("www.example.com", bbox, page_height=800)
        assert result is True

    def test_normal_text_not_filtered(self, parser: FitzPdfPlumberParser) -> None:
        bbox = (0, 200, 100, 220)
        result = parser._is_noise("This is normal body text.", bbox, page_height=800)
        assert result is False

    def test_filters_disabled(self, parser_no_filters: FitzPdfPlumberParser) -> None:
        bbox = (0, 5, 100, 20)
        result = parser_no_filters._is_noise("Header text", bbox, page_height=800)
        assert result is False


class TestDetectColumns:
    def test_single_column_page(self, parser: FitzPdfPlumberParser) -> None:
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.get_text.return_value = [
            (72, 100, 540, 110, "text", 0, 0),
            (72, 120, 540, 130, "text", 0, 0),
            (72, 140, 540, 150, "text", 0, 0),
        ]
        result = parser._detect_columns(mock_page)
        assert result == 1

    def test_two_column_page(self, parser: FitzPdfPlumberParser) -> None:
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
        result = parser._detect_columns(mock_page)
        assert result == 2

    def test_column_detection_disabled(self) -> None:
        p = FitzPdfPlumberParser(config={"column_detection": False})
        mock_page = MagicMock()
        result = p._detect_columns(mock_page)
        assert result == 1

    def test_empty_page(self, parser: FitzPdfPlumberParser) -> None:
        mock_page = MagicMock()
        mock_page.rect.width = 612
        mock_page.get_text.return_value = []
        result = parser._detect_columns(mock_page)
        assert result == 1


class TestTableToMarkdown:
    def test_simple_table(self, parser: FitzPdfPlumberParser) -> None:
        data = [
            ["Name", "Age"],
            ["Alice", "30"],
            ["Bob", "25"],
        ]
        result = parser._table_to_markdown(data)
        lines = result.split("\n")
        assert len(lines) == 4
        assert lines[0] == "| Name | Age |"
        assert lines[1] == "|---|---|"
        assert lines[2] == "| Alice | 30 |"
        assert lines[3] == "| Bob | 25 |"

    def test_table_with_none_values(self, parser: FitzPdfPlumberParser) -> None:
        data = [
            ["A", "B"],
            [None, "X"],
        ]
        result = parser._table_to_markdown(data)
        assert "|  | X |" in result

    def test_table_with_newlines_in_cells(self, parser: FitzPdfPlumberParser) -> None:
        data = [
            ["Header"],
            ["cell\nwith\nnewlines"],
        ]
        result = parser._table_to_markdown(data)
        assert "cell with newlines" in result

    def test_empty_table(self, parser: FitzPdfPlumberParser) -> None:
        result = parser._table_to_markdown([])
        assert result == ""

    def test_table_with_uneven_rows(self, parser: FitzPdfPlumberParser) -> None:
        data = [
            ["A", "B", "C"],
            ["1"],
            ["2", "3"],
        ]
        result = parser._table_to_markdown(data)
        lines = result.split("\n")
        assert "|---|---|---|" in lines[1]
        assert "| 1 |  |  |" in lines[2]
        assert "| 2 | 3 |  |" in lines[3]


class TestBboxOverlap:
    def test_no_overlap(self, parser: FitzPdfPlumberParser) -> None:
        bbox1 = (0, 0, 10, 10)
        bbox2 = (20, 20, 30, 30)
        assert parser._bbox_overlap(bbox1, bbox2) == 0.0

    def test_full_overlap(self, parser: FitzPdfPlumberParser) -> None:
        bbox1 = (0, 0, 10, 10)
        bbox2 = (0, 0, 10, 10)
        assert parser._bbox_overlap(bbox1, bbox2) == 1.0

    def test_partial_overlap(self, parser: FitzPdfPlumberParser) -> None:
        bbox1 = (0, 0, 10, 10)
        bbox2 = (5, 5, 15, 15)
        overlap = parser._bbox_overlap(bbox1, bbox2)
        expected = 25 / 100
        assert abs(overlap - expected) < 1e-6

    def test_zero_area_bbox(self, parser: FitzPdfPlumberParser) -> None:
        bbox1 = (0, 0, 0, 0)
        bbox2 = (0, 0, 10, 10)
        assert parser._bbox_overlap(bbox1, bbox2) == 0.0

    def test_touching_edges_no_overlap(self, parser: FitzPdfPlumberParser) -> None:
        bbox1 = (0, 0, 10, 10)
        bbox2 = (10, 0, 20, 10)
        assert parser._bbox_overlap(bbox1, bbox2) == 0.0


class TestBlocksToMarkdown:
    def test_text_blocks(self, parser: FitzPdfPlumberParser) -> None:
        blocks = [
            _TextBlock(page_number=1, block_type="text", content="Hello", bbox=(0, 0, 100, 10)),
            _TextBlock(page_number=1, block_type="text", content="World", bbox=(0, 20, 100, 30)),
        ]
        result = parser._blocks_to_markdown(blocks)
        assert result == "Hello\n\nWorld"

    def test_heading_detection_h1(self, parser: FitzPdfPlumberParser) -> None:
        block = _TextBlock(
            page_number=1, block_type="text", content="Title",
            bbox=(0, 0, 100, 10), font_size=18, is_bold=True,
        )
        blocks = [block]
        result = parser._blocks_to_markdown(blocks)
        assert result == "# Title"

    def test_heading_detection_h2(self, parser: FitzPdfPlumberParser) -> None:
        block = _TextBlock(
            page_number=1, block_type="text", content="Section",
            bbox=(0, 0, 100, 10), font_size=15, is_bold=True,
        )
        result = parser._blocks_to_markdown([block])
        assert result == "## Section"

    def test_heading_detection_h3(self, parser: FitzPdfPlumberParser) -> None:
        block = _TextBlock(
            page_number=1, block_type="text", content="Subsection",
            bbox=(0, 0, 100, 10), font_size=13, is_bold=True,
        )
        result = parser._blocks_to_markdown([block])
        assert result == "### Subsection"

    def test_heading_detection_h4(self, parser: FitzPdfPlumberParser) -> None:
        block = _TextBlock(
            page_number=1, block_type="text", content="Sub-sub",
            bbox=(0, 0, 100, 10), font_size=11.5, is_bold=True,
        )
        result = parser._blocks_to_markdown([block])
        assert result == "#### Sub-sub"

    def test_no_heading_for_non_bold(self, parser: FitzPdfPlumberParser) -> None:
        block = _TextBlock(
            page_number=1, block_type="text", content="Not heading",
            bbox=(0, 0, 100, 10), font_size=18, is_bold=False,
        )
        result = parser._blocks_to_markdown([block])
        assert result == "Not heading"

    def test_table_block(self, parser: FitzPdfPlumberParser) -> None:
        blocks = [
            _TextBlock(page_number=1, block_type="table", content="| A | B |\n|---|---|\n| 1 | 2 |", bbox=(0, 0, 100, 50)),
        ]
        result = parser._blocks_to_markdown(blocks)
        assert "| A | B |" in result

    def test_image_block(self, parser: FitzPdfPlumberParser) -> None:
        blocks = [
            _TextBlock(page_number=1, block_type="image", content="[图片: 页1]", bbox=(0, 0, 100, 50)),
        ]
        result = parser._blocks_to_markdown(blocks)
        assert "[图片: 页1]" in result

    def test_empty_blocks(self, parser: FitzPdfPlumberParser) -> None:
        result = parser._blocks_to_markdown([])
        assert result == ""


class TestMergeTextAndTables:
    def test_no_table_blocks(self, parser: FitzPdfPlumberParser) -> None:
        text_blocks = [
            _TextBlock(page_number=1, block_type="text", content="A", bbox=(0, 0, 100, 10)),
        ]
        result = parser._merge_text_and_tables(text_blocks, [])
        assert result == text_blocks

    def test_table_replaces_overlapping_text(self, parser: FitzPdfPlumberParser) -> None:
        text_blocks = [
            _TextBlock(page_number=1, block_type="text", content="Text in table area", bbox=(50, 50, 200, 150)),
            _TextBlock(page_number=1, block_type="text", content="Text outside", bbox=(50, 200, 200, 250)),
        ]
        table_blocks = [
            _TextBlock(page_number=1, block_type="table", content="| A |", bbox=(50, 50, 200, 150)),
        ]
        result = parser._merge_text_and_tables(text_blocks, table_blocks)
        contents = [b.content for b in result]
        assert "Text in table area" not in contents
        assert "Text outside" in contents
        assert "| A |" in contents

    def test_no_overlap_keeps_both(self, parser: FitzPdfPlumberParser) -> None:
        text_blocks = [
            _TextBlock(page_number=1, block_type="text", content="Text", bbox=(0, 0, 100, 10)),
        ]
        table_blocks = [
            _TextBlock(page_number=1, block_type="table", content="| A |", bbox=(0, 200, 100, 250)),
        ]
        result = parser._merge_text_and_tables(text_blocks, table_blocks)
        assert len(result) == 2

    def test_sorted_by_y_position(self, parser: FitzPdfPlumberParser) -> None:
        text_blocks = [
            _TextBlock(page_number=1, block_type="text", content="Below", bbox=(0, 300, 100, 310)),
        ]
        table_blocks = [
            _TextBlock(page_number=1, block_type="table", content="| A |", bbox=(0, 100, 100, 150)),
        ]
        result = parser._merge_text_and_tables(text_blocks, table_blocks)
        assert result[0].content == "| A |"
        assert result[1].content == "Below"


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
