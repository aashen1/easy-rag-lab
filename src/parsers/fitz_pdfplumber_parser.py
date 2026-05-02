from __future__ import annotations

from src.parsers.base import BaseParser, ParseResult
from src.parsers.composite_parser import CompositeParser
from src.parsers.fitz_parser import FitzParser
from src.parsers.pdfplumber_enhancer import PdfPlumberEnhancer

_FITZ_KEYS = frozenset(
    {
        "header_filter",
        "footer_filter",
        "header_zone_ratio",
        "footer_zone_ratio",
        "noise_patterns",
        "column_detection",
        "heading_detection",
        "heading_thresholds",
    }
)

_PLUMBER_KEYS = frozenset(
    {
        "min_columns",
        "max_empty_ratio",
        "min_data_rows",
        "replace_policy",
        "vertical_strategy",
        "horizontal_strategy",
    }
)


def _split_config(config: dict) -> tuple[dict, dict]:
    """Split a legacy fitz_pdfplumber config into fitz and pdfplumber configs.

    Args:
        config: Legacy configuration dict.

    Returns:
        Tuple of (fitz_config, pdfplumber_config).
    """
    fitz_config: dict = {}
    pdfplumber_config: dict = {}

    for key, value in config.items():
        if key in _FITZ_KEYS:
            fitz_config[key] = value
        elif key in _PLUMBER_KEYS:
            pdfplumber_config[key] = value
        elif key == "table_strategy":
            pdfplumber_config["strategy"] = value
        elif key == "table_settings":
            pdfplumber_config["table_settings"] = value

    return fitz_config, pdfplumber_config


class FitzPdfPlumberParser(BaseParser):
    """Backward-compatible wrapper delegating to CompositeParser(FitzParser, PdfPlumberEnhancer).

    Accepts the same config dict as the legacy monolithic implementation
    and splits it into fitz-specific and pdfplumber-specific options
    before delegating to the composite parser.
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
                heading_detection (bool): Enable heading detection. Default True.
                heading_thresholds (dict): Thresholds for heading levels.
                min_columns (int): Minimum columns for quality filter.
                max_empty_ratio (float): Maximum empty cell ratio.
                min_data_rows (int): Minimum data rows.
                replace_policy (str): Table replacement policy.
                vertical_strategy (str): Override vertical strategy.
                horizontal_strategy (str): Override horizontal strategy.
        """
        cfg = config or {}
        fitz_config, pdfplumber_config = _split_config(cfg)
        primary = FitzParser(fitz_config)
        enhancer = PdfPlumberEnhancer(pdfplumber_config)
        self._composite = CompositeParser(primary, enhancer)

    @property
    def name(self) -> str:
        """Return the unique identifier of this parser.

        Returns:
            The string "fitz_pdfplumber" for backward compatibility.
        """
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
        return self._composite.parse(pdf_path)
