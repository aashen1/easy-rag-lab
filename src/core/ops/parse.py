from __future__ import annotations

from pathlib import Path

from loguru import logger

from src.parsers.base import ParseResult
from src.parsers.registry import ParserRegistry


def parse_pdf(
    pdf_path: str | Path,
    parser_name: str = "pymupdf4llm",
    enhancer_name: str | None = None,
    parser_options: dict | None = None,
    enhancer_options: dict | None = None,
) -> ParseResult:
    """Parse a PDF file using the specified parser and optional enhancer.

    When *enhancer_name* is provided, a composite parser is created via
    ``ParserRegistry.get_composite()``.  Otherwise, the legacy
    ``ParserRegistry.get()`` interface is used so that names like
    ``"fitz_pdfplumber"`` continue to work.

    Args:
        pdf_path: Path to the PDF file to parse.
        parser_name: Name of the primary parser (default ``"pymupdf4llm"``).
        enhancer_name: Optional name of a table enhancer (e.g.
            ``"pdfplumber"``).  When provided, ``get_composite()`` is used.
        parser_options: Optional configuration dict forwarded to the
            primary parser constructor.
        enhancer_options: Optional configuration dict forwarded to the
            enhancer constructor.

    Returns:
        A ``ParseResult`` containing extracted pages and document metadata.

    Raises:
        FileNotFoundError: If *pdf_path* does not exist.
        ValueError: If *parser_name* or *enhancer_name* is not registered.
        ParsingError: If the parser or enhancer cannot be instantiated.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    if enhancer_name is not None:
        logger.debug(
            f"Creating composite parser: primary={parser_name}, "
            f"enhancer={enhancer_name}"
        )
        parser = ParserRegistry.get_composite(
            primary=parser_name,
            enhancer=enhancer_name,
            primary_config=parser_options,
            enhancer_config=enhancer_options,
        )
    else:
        logger.debug(f"Creating parser via legacy interface: {parser_name}")
        parser = ParserRegistry.get(name=parser_name, config=parser_options)

    logger.info(f"Parsing PDF: {pdf_path}")
    result = parser.parse(str(pdf_path))
    logger.info(f"Parsed {len(result.pages)} pages from {pdf_path.name}")
    return result


def enhance_page(
    pdf_path: str | Path,
    page_number: int,
    existing_text: str,
    enhancer_name: str = "pdfplumber",
    enhancer_options: dict | None = None,
) -> str:
    """Re-extract a single page using an enhancer and merge with existing text.

    Args:
        pdf_path: Path to the original PDF file.
        page_number: 1-indexed page number to enhance.
        existing_text: The text already extracted by the primary parser.
        enhancer_name: Name of the enhancer to use (default ``"pdfplumber"``).
        enhancer_options: Optional configuration dict forwarded to the
            enhancer constructor.

    Returns:
        Enhanced text for the page with improved table formatting.

    Raises:
        FileNotFoundError: If *pdf_path* does not exist.
        ParsingError: If *enhancer_name* is not registered.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    enhancer = ParserRegistry.get_enhancer(enhancer_name, enhancer_options)
    logger.debug(f"Enhancing page {page_number} of {pdf_path} with {enhancer_name}")
    result = enhancer.enhance_page(str(pdf_path), page_number, existing_text)
    return result


def enhance_table(
    pdf_path: str | Path,
    page_number: int,
    table_index: int,
    existing_text: str,
    enhancer_name: str = "pdfplumber",
    enhancer_options: dict | None = None,
) -> str:
    """Re-extract a single table using an enhancer and replace existing text.

    Args:
        pdf_path: Path to the original PDF file.
        page_number: 1-indexed page number containing the table.
        table_index: 1-indexed position of the table within the page.
        existing_text: The text already extracted by the primary parser.
        enhancer_name: Name of the enhancer to use (default ``"pdfplumber"``).
        enhancer_options: Optional configuration dict forwarded to the
            enhancer constructor.

    Returns:
        Enhanced text for the table region.

    Raises:
        FileNotFoundError: If *pdf_path* does not exist.
        ParsingError: If *enhancer_name* is not registered.
    """
    pdf_path = Path(pdf_path)
    if not pdf_path.exists():
        raise FileNotFoundError(f"PDF file not found: {pdf_path}")

    enhancer = ParserRegistry.get_enhancer(enhancer_name, enhancer_options)
    logger.debug(
        f"Enhancing table {table_index} on page {page_number} of {pdf_path} "
        f"with {enhancer_name}"
    )
    result = enhancer.enhance_table(
        str(pdf_path), page_number, table_index, existing_text
    )
    return result
