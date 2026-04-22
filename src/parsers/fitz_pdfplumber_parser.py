from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

import fitz
from loguru import logger

from src.exceptions import ParsingError
from src.parsers.base import BaseParser, ParsedPage, ParseResult


@dataclass
class _TextBlock:
    page_number: int
    block_type: str  # "text" | "table" | "image"
    content: str
    bbox: tuple[float, float, float, float]
    font_size: float = 0.0
    is_bold: bool = False


DEFAULT_NOISE_PATTERNS = [
    r"请务必阅读.{0,20}声明",
    r"^\s*\d+\s*$",
    r"^\s*\d+\s*/\s*\d+\s*$",
    r"(?:内部资料|机密|仅供参考).{0,30}$",
    r"^(?:www\.|http).+$",
]

DEFAULT_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "edge_min_length": 10,
    "intersection_x_tolerance": 5,
    "intersection_y_tolerance": 5,
}


class FitzPdfPlumberParser(BaseParser):
    """PDF parser combining fitz text extraction with pdfplumber table extraction.

    Uses fitz (PyMuPDF) for text and layout analysis, and pdfplumber for
    precise table extraction. Tables from pdfplumber replace the corresponding
    text regions from fitz.
    """

    def __init__(self, config: dict | None = None):
        """Initialize with optional configuration.

        Args:
            config: Configuration dict with fitz_pdfplumber-specific options:
                header_filter (bool): Filter header regions. Default True.
                footer_filter (bool): Filter footer regions. Default True.
                header_zone_ratio (float): Header zone as fraction of page height. Default 0.10.
                footer_zone_ratio (float): Footer zone as fraction of page height. Default 0.10.
                noise_patterns (list[str]): Regex patterns for noise text.
                table_strategy (str): pdfplumber table strategy. Default "lines".
                table_settings (dict): pdfplumber find_tables() settings.
                column_detection (bool): Enable multi-column detection. Default True.
        """
        self._config = config or {}
        self._header_filter = self._config.get("header_filter", True)
        self._footer_filter = self._config.get("footer_filter", True)
        self._header_zone_ratio = self._config.get("header_zone_ratio", 0.10)
        self._footer_zone_ratio = self._config.get("footer_zone_ratio", 0.10)
        self._noise_patterns = self._config.get("noise_patterns", DEFAULT_NOISE_PATTERNS)
        self._table_strategy = self._config.get("table_strategy", "lines")
        self._table_settings = self._config.get("table_settings", DEFAULT_TABLE_SETTINGS)
        self._column_detection = self._config.get("column_detection", True)
        self._noise_re = [re.compile(p) for p in self._noise_patterns]

    @property
    def name(self) -> str:
        """Return the unique identifier of this parser."""
        return "fitz_pdfplumber"

    def parse(self, pdf_path: str) -> ParseResult:
        """Parse a PDF file using fitz + pdfplumber.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            ParseResult with one ParsedPage per page, each containing
            Markdown-formatted text with page_number metadata.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            ValueError: If the file is not a PDF.
            Exception: If parsing fails.
        """
        pdf_file = Path(pdf_path)
        if not pdf_file.exists():
            error_msg = f"PDF file not found: {pdf_path}"
            logger.error(error_msg)
            raise ParsingError(error_msg)
        if pdf_file.suffix.lower() != ".pdf":
            error_msg = f"File is not a PDF: {pdf_path}"
            logger.error(error_msg)
            raise ParsingError(error_msg)

        try:
            logger.info(f"Parsing PDF with fitz+pdfplumber: {pdf_path}")
            doc = fitz.open(str(pdf_file))
            total_pages = len(doc)
            pages = []

            for page_idx in range(total_pages):
                page = doc[page_idx]
                page_number = page_idx + 1
                blocks = self._extract_page_blocks(page, page_number)
                table_blocks = self._extract_tables_with_pdfplumber(str(pdf_file), page_idx)
                combined = self._merge_text_and_tables(blocks, table_blocks)
                md_text = self._blocks_to_markdown(combined)
                pages.append(ParsedPage(
                    page_number=page_number,
                    text=md_text,
                    metadata={"source": str(pdf_path), "page_number": page_number},
                ))

            doc.close()
            return ParseResult(
                pages=pages,
                metadata={"source": str(pdf_path), "parser": self.name, "page_count": total_pages},
            )
        except Exception as e:
            error_msg = f"Failed to parse PDF {pdf_path}: {str(e)}"
            logger.error(error_msg)
            raise ParsingError(error_msg) from e

    def _is_noise(self, text: str, bbox: tuple, page_height: float) -> bool:
        """Determine if a text block is noise (header/footer/pattern match).

        Args:
            text: Text content of the block.
            bbox: Bounding box (x0, y0, x1, y1).
            page_height: Height of the page.

        Returns:
            True if the block should be filtered out.
        """
        text_stripped = text.strip()
        y0, y1 = bbox[1], bbox[3]

        if self._header_filter:
            is_header_zone = y0 < page_height * self._header_zone_ratio
            if is_header_zone and len(text_stripped) < 80:
                return True

        if self._footer_filter:
            is_footer_zone = y1 > page_height * (1 - self._footer_zone_ratio)
            if is_footer_zone and len(text_stripped) < 80:
                return True

        return any(pattern.search(text_stripped) for pattern in self._noise_re)

    def _detect_columns(self, page: fitz.Page) -> int:
        """Detect the number of columns on a page.

        Args:
            page: fitz Page object.

        Returns:
            Number of columns (1 or 2).
        """
        if not self._column_detection:
            return 1

        page_width = page.rect.width
        blocks = page.get_text("blocks")

        if not blocks:
            return 1

        x_centers = [
            (b[0] + b[2]) / 2
            for b in blocks
            if b[6] == 0
        ]

        if not x_centers:
            return 1

        left_count = sum(1 for x in x_centers if x < page_width * 0.5)
        right_count = len(x_centers) - left_count

        if left_count > 2 and right_count > 2:
            ratio = min(left_count, right_count) / max(left_count, right_count)
            if ratio > 0.3:
                return 2

        return 1

    def _extract_page_blocks(self, page: fitz.Page, page_number: int) -> list[_TextBlock]:
        """Extract all content blocks from a page using fitz.

        Args:
            page: fitz Page object.
            page_number: 1-indexed page number.

        Returns:
            List of _TextBlock objects sorted by reading order.
        """
        page_height = page.rect.height
        page_width = page.rect.width
        column_count = self._detect_columns(page)

        blocks = []
        raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

        for block in raw_blocks:
            if block["type"] == 1:
                blocks.append(_TextBlock(
                    page_number=page_number,
                    block_type="image",
                    content=f"[图片: 页{page_number}]",
                    bbox=tuple(block["bbox"]),
                ))
                continue

            if block["type"] != 0:
                continue

            full_text = ""
            max_font_size = 0.0
            is_bold = False

            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    full_text += span["text"]
                    if span["size"] > max_font_size:
                        max_font_size = span["size"]
                    if span["flags"] & (1 << 4):
                        is_bold = True
                full_text += "\n"

            full_text = full_text.strip()
            if not full_text:
                continue

            bbox = tuple(block["bbox"])

            if self._is_noise(full_text, bbox, page_height):
                continue

            blocks.append(_TextBlock(
                page_number=page_number,
                block_type="text",
                content=full_text,
                bbox=bbox,
                font_size=max_font_size,
                is_bold=is_bold,
            ))

        if column_count == 2:
            mid_x = page_width / 2
            blocks.sort(key=lambda b: (
                0 if b.bbox[0] < mid_x else 1,
                b.bbox[1],
            ))
        else:
            blocks.sort(key=lambda b: b.bbox[1])

        return blocks

    def _extract_tables_with_pdfplumber(self, pdf_path: str, page_idx: int) -> list[_TextBlock]:
        """Extract tables from a page using pdfplumber.

        Args:
            pdf_path: Path to the PDF file.
            page_idx: 0-indexed page index.

        Returns:
            List of _TextBlock objects for tables.

        Note:
            Silently returns empty list if pdfplumber fails.
        """
        tables = []

        try:
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                if page_idx >= len(pdf.pages):
                    return []

                page = pdf.pages[page_idx]
                settings = dict(self._table_settings)
                settings.setdefault("vertical_strategy", self._table_strategy)
                settings.setdefault("horizontal_strategy", self._table_strategy)

                plumber_tables = page.find_tables(table_settings=settings)

                for _, table in enumerate(plumber_tables):
                    table_data = table.extract()
                    if not table_data or not table_data[0]:
                        continue

                    md_table = self._table_to_markdown(table_data)
                    if not md_table:
                        continue

                    bbox = tuple(table.bbox) if table.bbox else (0, 0, 0, 0)

                    tables.append(_TextBlock(
                        page_number=page_idx + 1,
                        block_type="table",
                        content=md_table,
                        bbox=bbox,
                    ))
        except Exception as e:
            logger.warning(f"pdfplumber table extraction failed for page {page_idx + 1}: {str(e)}")

        return tables

    def _table_to_markdown(self, table_data: list[list[str | None]]) -> str:
        """Convert pdfplumber table data to Markdown format.

        Args:
            table_data: 2D list from pdfplumber extract(), may contain None.

        Returns:
            Markdown table string, or empty string if conversion fails.
        """
        if not table_data:
            return ""

        cleaned = []
        for row in table_data:
            cleaned_row = [
                str(cell).replace("\n", " ").strip() if cell is not None else ""
                for cell in row
            ]
            cleaned.append(cleaned_row)

        if not cleaned[0]:
            return ""

        col_count = max(len(row) for row in cleaned)

        for row in cleaned:
            while len(row) < col_count:
                row.append("")

        lines = []
        lines.append("| " + " | ".join(cleaned[0]) + " |")
        lines.append("|" + "|".join(["---"] * col_count) + "|")
        for row in cleaned[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _merge_text_and_tables(
        self,
        text_blocks: list[_TextBlock],
        table_blocks: list[_TextBlock],
    ) -> list[_TextBlock]:
        """Merge text blocks and table blocks, replacing overlapping text with tables.

        Args:
            text_blocks: Text blocks from fitz.
            table_blocks: Table blocks from pdfplumber.

        Returns:
            Combined and sorted list of blocks.
        """
        if not table_blocks:
            return text_blocks

        result = []
        for tb in text_blocks:
            overlaps_table = any(
                self._bbox_overlap(tb.bbox, tab.bbox) > 0.5
                for tab in table_blocks
            )
            if not overlaps_table:
                result.append(tb)

        result.extend(table_blocks)
        result.sort(key=lambda b: b.bbox[1])
        return result

    def _bbox_overlap(self, bbox1: tuple, bbox2: tuple) -> float:
        """Calculate overlap ratio between two bounding boxes.

        Args:
            bbox1: First bounding box (x0, y0, x1, y1).
            bbox2: Second bounding box (x0, y0, x1, y1).

        Returns:
            Overlap ratio relative to bbox1 area (0.0 to 1.0).
        """
        x0 = max(bbox1[0], bbox2[0])
        y0 = max(bbox1[1], bbox2[1])
        x1 = min(bbox1[2], bbox2[2])
        y1 = min(bbox1[3], bbox2[3])

        if x1 <= x0 or y1 <= y0:
            return 0.0

        overlap_area = (x1 - x0) * (y1 - y0)
        area1 = (bbox1[2] - bbox1[0]) * (bbox1[3] - bbox1[1])

        return overlap_area / area1 if area1 > 0 else 0.0

    def _blocks_to_markdown(self, blocks: list[_TextBlock]) -> str:
        """Convert a list of blocks to a Markdown string.

        Uses font size and bold flags to detect headings and generate
        appropriate Markdown heading markers.

        Args:
            blocks: Sorted list of _TextBlock objects.

        Returns:
            Markdown-formatted string for the page.
        """
        if not blocks:
            return ""

        parts = []
        for block in blocks:
            if block.block_type == "table":
                parts.append(block.content)
                continue

            if block.block_type == "image":
                parts.append(block.content)
                continue

            heading_prefix = self._detect_heading(block)
            if heading_prefix:
                parts.append(f"{heading_prefix} {block.content}")
            else:
                parts.append(block.content)

        return "\n\n".join(parts)

    def _detect_heading(self, block: _TextBlock) -> str:
        """Detect if a text block is a heading based on font size and bold.

        Args:
            block: Text block to analyze.

        Returns:
            Markdown heading prefix string (e.g. "##") or empty string.
        """
        if block.font_size > 16 and block.is_bold:
            return "#"
        if block.font_size > 14 and block.is_bold:
            return "##"
        if block.font_size > 12 and block.is_bold:
            return "###"
        if block.font_size > 11 and block.is_bold and len(block.content) < 100:
            return "####"
        return ""
