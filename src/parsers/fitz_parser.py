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

DEFAULT_HEADING_THRESHOLDS = {
    "h1": {"font_size": 16, "bold": True},
    "h2": {"font_size": 14, "bold": True},
    "h3": {"font_size": 12, "bold": True},
    "h4": {"font_size": 11, "bold": True, "max_length": 100},
}


class FitzParser(BaseParser):
    """PDF parser using fitz (PyMuPDF) for text extraction only.

    Extracts text blocks, detects headings, filters noise, and produces
    Markdown-formatted output per page. Does not perform table extraction.
    """

    def __init__(self, config: dict | None = None):
        """Initialize with optional configuration.

        Args:
            config: Configuration dict with fitz-specific options:
                header_filter (bool): Filter header regions. Default True.
                footer_filter (bool): Filter footer regions. Default True.
                header_zone_ratio (float): Header zone as fraction of page height. Default 0.10.
                footer_zone_ratio (float): Footer zone as fraction of page height. Default 0.10.
                noise_patterns (list[str]): Regex patterns for noise text.
                column_detection (bool): Enable multi-column detection. Default True.
                heading_detection (bool): Enable heading detection. Default True.
                heading_thresholds (dict): Thresholds for heading levels.
        """
        self._config = config or {}
        self._header_filter = self._config.get("header_filter", True)
        self._footer_filter = self._config.get("footer_filter", True)
        self._header_zone_ratio = self._config.get("header_zone_ratio", 0.10)
        self._footer_zone_ratio = self._config.get("footer_zone_ratio", 0.10)
        self._noise_patterns = self._config.get(
            "noise_patterns", DEFAULT_NOISE_PATTERNS
        )
        self._column_detection = self._config.get("column_detection", True)
        self._heading_detection = self._config.get("heading_detection", True)
        self._heading_thresholds = self._config.get(
            "heading_thresholds", DEFAULT_HEADING_THRESHOLDS
        )
        self._noise_re = [re.compile(p) for p in self._noise_patterns]

    @property
    def name(self) -> str:
        """Return the unique identifier of this parser."""
        return "fitz"

    def parse(self, pdf_path: str) -> ParseResult:
        """Parse a PDF file using fitz text extraction.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            ParseResult with one ParsedPage per page, each containing
            Markdown-formatted text with page_number metadata.

        Raises:
            ParsingError: If the PDF file does not exist, is not a PDF,
                or if parsing fails.
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
            logger.info(f"Parsing PDF with fitz: {pdf_path}")
            doc = fitz.open(str(pdf_file))
            total_pages = len(doc)
            pages = []

            for page_idx in range(total_pages):
                page = doc[page_idx]
                page_number = page_idx + 1
                blocks = self._extract_page_blocks(page, page_number)
                md_text = self._blocks_to_markdown(blocks)
                pages.append(
                    ParsedPage(
                        page_number=page_number,
                        text=md_text,
                        metadata={
                            "source": Path(pdf_path).as_posix(),
                            "page_number": page_number,
                        },
                    )
                )

            doc.close()
            return ParseResult(
                pages=pages,
                metadata={
                    "source": Path(pdf_path).as_posix(),
                    "parser": self.name,
                    "page_count": total_pages,
                },
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

        x_centers = [(b[0] + b[2]) / 2 for b in blocks if b[6] == 0]

        if not x_centers:
            return 1

        left_count = sum(1 for x in x_centers if x < page_width * 0.5)
        right_count = len(x_centers) - left_count

        if left_count > 2 and right_count > 2:
            ratio = min(left_count, right_count) / max(left_count, right_count)
            if ratio > 0.3:
                return 2

        return 1

    def _extract_page_blocks(
        self, page: fitz.Page, page_number: int
    ) -> list[_TextBlock]:
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
        raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)[
            "blocks"
        ]

        for block in raw_blocks:
            if block["type"] == 1:
                blocks.append(
                    _TextBlock(
                        page_number=page_number,
                        block_type="image",
                        content=f"[图片: 页{page_number}]",
                        bbox=tuple(block["bbox"]),
                    )
                )
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

            blocks.append(
                _TextBlock(
                    page_number=page_number,
                    block_type="text",
                    content=full_text,
                    bbox=bbox,
                    font_size=max_font_size,
                    is_bold=is_bold,
                )
            )

        if column_count == 2:
            mid_x = page_width / 2
            blocks.sort(
                key=lambda b: (
                    0 if b.bbox[0] < mid_x else 1,
                    b.bbox[1],
                )
            )
        else:
            blocks.sort(key=lambda b: b.bbox[1])

        return blocks

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
        if not self._heading_detection:
            return ""

        h1 = self._heading_thresholds.get("h1", {})
        h2 = self._heading_thresholds.get("h2", {})
        h3 = self._heading_thresholds.get("h3", {})
        h4 = self._heading_thresholds.get("h4", {})

        if block.font_size > h1.get("font_size", 16) and block.is_bold:
            return "#"
        if block.font_size > h2.get("font_size", 14) and block.is_bold:
            return "##"
        if block.font_size > h3.get("font_size", 12) and block.is_bold:
            return "###"
        h4_max_length = h4.get("max_length", 100)
        if (
            block.font_size > h4.get("font_size", 11)
            and block.is_bold
            and len(block.content) < h4_max_length
        ):
            return "####"
        return ""
