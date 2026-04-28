from __future__ import annotations

import re
from pathlib import Path

import pymupdf4llm
from loguru import logger

from src.exceptions import ParsingError
from src.parsers.base import BaseParser, ParsedPage, ParseResult


def clean_degenerate_tables(text: str) -> str:
    """Remove degenerate markdown table rows from text.

    A degenerate row is one where all cells are empty (only pipes and
    whitespace) or contain only separator dashes. Entire tables are
    removed if all their data rows are degenerate.

    Args:
        text: Input text potentially containing markdown tables.

    Returns:
        Text with degenerate table rows removed.
    """
    lines = text.split("\n")
    result_lines: list[str] = []
    table_buffer: list[str] = []
    in_table = False

    def is_table_row(line: str) -> bool:
        stripped = line.strip()
        return stripped.startswith("|") and stripped.endswith("|")

    def is_degenerate_row(line: str) -> bool:
        stripped = line.strip()
        cells = stripped.split("|")
        inner = cells[1:-1]
        if not inner:
            return True
        for cell in inner:
            content = cell.strip()
            if content and not re.match(r"^[-:]+$", content):
                return False
        return True

    def flush_table() -> None:
        nonlocal table_buffer
        if not table_buffer:
            return
        non_degenerate = [line for line in table_buffer if not is_degenerate_row(line)]
        if non_degenerate:
            result_lines.extend(table_buffer)
        table_buffer = []

    for line in lines:
        if is_table_row(line):
            in_table = True
            table_buffer.append(line)
        else:
            if in_table:
                flush_table()
                in_table = False
            result_lines.append(line)

    if in_table:
        flush_table()

    return "\n".join(result_lines)


class PyMuPDF4LLMParser(BaseParser):
    """Parser adapter that delegates to the existing pymupdf4llm pipeline.

    Supports two modes:
    - Whole-document mode (default): Returns the entire document as a single ParsedPage.
    - Page-chunks mode (page_chunks=True): Returns each page as a separate ParsedPage
      with page_number metadata.
    """

    def __init__(self, config: dict | None = None):
        """Initialize with optional configuration.

        Args:
            config: Configuration dict that may contain pymupdf4llm-specific options
                such as header, footer, page_separators, ignore_images, write_images,
                page_chunks, table_strategy, clean_degenerate_tables, etc.
        """
        self._config = config or {}
        self._clean_degenerate_tables = self._config.pop(
            "clean_degenerate_tables", True
        )
        self._options = {
            k: v for k, v in self._config.items() if k not in ("page_chunks",)
        }

    @property
    def name(self) -> str:
        """Return the unique identifier of this parser.

        Returns:
            Parser name string used for registration and lookup.
        """
        return "pymupdf4llm"

    def parse(self, pdf_path: str) -> ParseResult:
        """Parse a PDF file using pymupdf4llm.

        Args:
            pdf_path: Path to the PDF file.

        Returns:
            ParseResult with one ParsedPage per page (if page_chunks=True)
            or a single ParsedPage for the whole document.

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

        page_chunks = self._config.get("page_chunks", False)

        try:
            logger.info(f"Parsing PDF with pymupdf4llm: {pdf_path}")
            if page_chunks:
                result = pymupdf4llm.to_markdown(
                    str(pdf_file), page_chunks=True, **self._options
                )
                pages = []
                for page_data in result:
                    metadata = page_data.get("metadata", {})
                    page_number = metadata.get("page_number", len(pages) + 1)
                    page_text = page_data.get("text", "")
                    if self._clean_degenerate_tables:
                        page_text = clean_degenerate_tables(page_text)
                    pages.append(
                        ParsedPage(
                            page_number=page_number,
                            text=page_text,
                            metadata=metadata,
                        )
                    )
                return ParseResult(
                    pages=pages,
                    metadata={
                        "source": Path(pdf_path).as_posix(),
                        "parser": self.name,
                        "page_count": len(pages),
                    },
                )
            else:
                md_text = pymupdf4llm.to_markdown(str(pdf_file), **self._options)
                if self._clean_degenerate_tables:
                    md_text = clean_degenerate_tables(md_text)
                return ParseResult(
                    pages=[
                        ParsedPage(
                            page_number=1,
                            text=md_text,
                            metadata={"source": Path(pdf_path).as_posix()},
                        )
                    ],
                    metadata={
                        "source": Path(pdf_path).as_posix(),
                        "parser": self.name,
                        "page_count": 1,
                    },
                )
        except Exception as e:
            error_msg = f"Failed to parse PDF {pdf_path}: {str(e)}"
            logger.error(error_msg)
            raise ParsingError(error_msg) from e
