from __future__ import annotations

import re
from copy import deepcopy

from loguru import logger

from src.parsers.base import ParsedPage, ParseResult, TableEnhancer

DEFAULT_TABLE_SETTINGS = {
    "vertical_strategy": "lines",
    "horizontal_strategy": "lines",
    "snap_tolerance": 5,
    "join_tolerance": 5,
    "edge_min_length": 10,
    "intersection_x_tolerance": 5,
    "intersection_y_tolerance": 5,
}

_MD_TABLE_ROW_RE = re.compile(r"^\|.*\|$")
_MD_SEPARATOR_RE = re.compile(r"^\|[\s\-:]+\|[\s\-:|]*$")


class PdfPlumberEnhancer(TableEnhancer):
    """Table enhancer that re-extracts tables using pdfplumber.

    Detects markdown tables in the parsed output, re-extracts those
    table regions with pdfplumber for higher fidelity, and replaces
    the original tables when the pdfplumber version passes quality
    filters.
    """

    def __init__(self, config: dict | None = None):
        """Initialize with optional configuration.

        Args:
            config: Configuration dict with enhancer-specific options:
                strategy (str): Default strategy for both vertical and
                    horizontal. Default "lines".
                vertical_strategy (str): Override vertical strategy.
                    Default None (use *strategy*).
                horizontal_strategy (str): Override horizontal strategy.
                    Default None (use *strategy*).
                table_settings (dict): pdfplumber find_tables() settings.
                    Default DEFAULT_TABLE_SETTINGS.
                min_columns (int): Minimum columns for quality filter.
                    Default 3.
                max_empty_ratio (float): Maximum empty cell ratio.
                    Default 0.5.
                min_data_rows (int): Minimum data rows (excl. header).
                    Default 2.
                replace_policy (str): "better_wins" / "always_replace" /
                    "never_replace". Default "better_wins".
        """
        cfg = config or {}
        self._strategy = cfg.get("strategy", "lines")
        self._vertical_strategy = cfg.get("vertical_strategy", None)
        self._horizontal_strategy = cfg.get("horizontal_strategy", None)
        self._table_settings = cfg.get("table_settings", DEFAULT_TABLE_SETTINGS)
        self._min_columns = cfg.get("min_columns", 3)
        self._max_empty_ratio = cfg.get("max_empty_ratio", 0.5)
        self._min_data_rows = cfg.get("min_data_rows", 2)
        self._replace_policy = cfg.get("replace_policy", "better_wins")

    @property
    def name(self) -> str:
        """Return the unique identifier of this enhancer.

        Returns:
            Enhancer name string used for registration and lookup.
        """
        return "pdfplumber"

    def enhance(self, pdf_path: str, result: ParseResult) -> ParseResult:
        """Enhance table regions in a parsed result using pdfplumber.

        For each page that contains markdown tables, re-extracts those
        tables with pdfplumber and replaces the originals when the
        pdfplumber version is of sufficient quality.

        Args:
            pdf_path: Path to the original PDF file.
            result: ParseResult from the primary parser.

        Returns:
            ParseResult with enhanced table regions.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            Exception: If enhancement fails for any other reason.
        """
        enhanced_pages: list[ParsedPage] = []

        for page in result.pages:
            page_idx = page.page_number - 1
            spans = self._find_md_table_spans(page.text)

            if not spans:
                enhanced_pages.append(page)
                continue

            plumber_tables = self._extract_tables(pdf_path, page_idx)
            plumber_tables = self._filter_low_quality(plumber_tables)

            if not plumber_tables:
                enhanced_pages.append(page)
                continue

            new_text = self._replace_tables(page.text, plumber_tables)
            enhanced_pages.append(
                ParsedPage(
                    page_number=page.page_number,
                    text=new_text,
                    metadata=deepcopy(page.metadata),
                )
            )

        return ParseResult(
            pages=enhanced_pages,
            metadata=deepcopy(result.metadata),
        )

    @staticmethod
    def _find_md_table_spans(text: str) -> list[tuple[int, int]]:
        """Find start/end positions of markdown tables in text.

        A markdown table is a contiguous block of pipe-delimited rows
        that includes at least one separator line (``|---|---|``).

        Args:
            text: Page text that may contain markdown tables.

        Returns:
            List of (start, end) character offsets for each table.
        """
        lines = text.split("\n")
        spans: list[tuple[int, int]] = []
        table_start: int | None = None
        has_separator = False
        pos = 0

        for line in lines:
            line_start = pos
            is_row = bool(_MD_TABLE_ROW_RE.match(line.strip()))
            is_sep = bool(_MD_SEPARATOR_RE.match(line.strip()))

            if is_row:
                if table_start is None:
                    table_start = line_start
                if is_sep:
                    has_separator = True
            else:
                if table_start is not None and has_separator:
                    spans.append((table_start, pos))
                table_start = None
                has_separator = False

            pos = line_start + len(line) + 1

        if table_start is not None and has_separator:
            spans.append((table_start, pos))

        return spans

    def _extract_tables(self, pdf_path: str, page_idx: int) -> list[str]:
        """Extract tables from a page using pdfplumber.

        Args:
            pdf_path: Path to the PDF file.
            page_idx: 0-indexed page index.

        Returns:
            List of markdown table strings extracted by pdfplumber.
        """
        tables: list[str] = []

        try:
            import pdfplumber

            with pdfplumber.open(pdf_path) as pdf:
                if page_idx >= len(pdf.pages):
                    return []

                page = pdf.pages[page_idx]
                settings = dict(self._table_settings)
                settings.setdefault(
                    "vertical_strategy",
                    self._vertical_strategy or self._strategy,
                )
                settings.setdefault(
                    "horizontal_strategy",
                    self._horizontal_strategy or self._strategy,
                )

                plumber_tables = page.find_tables(table_settings=settings)

                for table in plumber_tables:
                    table_data = table.extract()
                    if not table_data or not table_data[0]:
                        continue

                    md = self._table_to_markdown(table_data)
                    if md:
                        tables.append(md)

        except Exception as e:
            logger.warning(
                f"pdfplumber table extraction failed for page {page_idx + 1}: {str(e)}"
            )

        return tables

    @staticmethod
    def _table_to_markdown(table_data: list[list[str | None]]) -> str:
        """Convert pdfplumber table data to Markdown format.

        Filters out degenerate rows where all cells are empty or contain
        only whitespace.

        Args:
            table_data: 2D list from pdfplumber extract(), may contain None.

        Returns:
            Markdown table string, or empty string if conversion fails.
        """
        if not table_data:
            return ""

        cleaned: list[list[str]] = []
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

        non_degenerate = [row for row in cleaned if any(cell.strip() for cell in row)]

        if not non_degenerate:
            return ""

        lines: list[str] = []
        lines.append("| " + " | ".join(non_degenerate[0]) + " |")
        lines.append("|" + "|".join(["---"] * col_count) + "|")
        for row in non_degenerate[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _filter_low_quality(self, tables: list[str]) -> list[str]:
        """Filter tables by quality criteria.

        A table is considered low-quality if it has fewer than
        ``min_columns`` columns, more than ``max_empty_ratio`` empty
        cells, or fewer than ``min_data_rows`` data rows.

        Args:
            tables: List of markdown table strings.

        Returns:
            Filtered list of markdown table strings.
        """
        result: list[str] = []
        for md in tables:
            rows, cols, data_rows, empty_ratio = self._count_table_quality(md)
            if cols < self._min_columns:
                logger.debug(
                    f"Filtered table: cols={cols} < min_columns={self._min_columns}"
                )
                continue
            if empty_ratio > self._max_empty_ratio:
                logger.debug(
                    f"Filtered table: empty_ratio={empty_ratio:.2f} > max={self._max_empty_ratio}"
                )
                continue
            if data_rows < self._min_data_rows:
                logger.debug(
                    f"Filtered table: data_rows={data_rows} < min={self._min_data_rows}"
                )
                continue
            result.append(md)
        return result

    def _replace_tables(self, text: str, plumber_tables: list[str]) -> str:
        """Replace markdown tables in text with pdfplumber versions.

        The replacement strategy depends on ``replace_policy``:
        - "better_wins": Replace each original table with the
          corresponding pdfplumber table only if the pdfplumber version
          has more data rows.
        - "always_replace": Replace each original table with the
          corresponding pdfplumber table unconditionally.
        - "never_replace": Never replace (effectively a no-op).

        When there are fewer plumber tables than original tables, only
        the matching ones are replaced. Extra plumber tables are
        appended at the end.

        Args:
            text: Original page text.
            plumber_tables: List of pdfplumber-extracted markdown tables.

        Returns:
            Text with tables replaced according to the replace policy.
        """
        if self._replace_policy == "never_replace":
            return text

        spans = self._find_md_table_spans(text)
        if not spans:
            return text

        original_tables: list[str] = []
        for start, end in spans:
            original_tables.append(text[start:end].rstrip("\n"))

        result_parts: list[str] = []
        prev_end = 0
        plumber_idx = 0

        for span_idx, (start, end) in enumerate(spans):
            result_parts.append(text[prev_end:start])

            if plumber_idx < len(plumber_tables):
                plumber_md = plumber_tables[plumber_idx]
                should_replace = False

                if self._replace_policy == "always_replace":
                    should_replace = True
                elif self._replace_policy == "better_wins":
                    orig_quality = self._count_table_quality(original_tables[span_idx])
                    plumber_quality = self._count_table_quality(plumber_md)
                    should_replace = plumber_quality[2] > orig_quality[2]

                if should_replace:
                    result_parts.append(plumber_md)
                else:
                    result_parts.append(original_tables[span_idx])
                plumber_idx += 1
            else:
                result_parts.append(original_tables[span_idx])

            prev_end = end

        result_parts.append(text[prev_end:])

        for extra in plumber_tables[plumber_idx:]:
            result_parts.append("\n\n" + extra)

        return "".join(result_parts)

    @staticmethod
    def _count_table_quality(md_table: str) -> tuple[int, int, int, float]:
        """Compute quality metrics for a markdown table.

        Args:
            md_table: Markdown table string.

        Returns:
            Tuple of (total_rows, col_count, data_rows, empty_ratio)
            where *data_rows* excludes the header and separator rows,
            and *empty_ratio* is the fraction of empty cells across
            all rows (including header).
        """
        lines = md_table.strip().split("\n")
        data_lines = [
            line
            for line in lines
            if _MD_TABLE_ROW_RE.match(line.strip())
            and not _MD_SEPARATOR_RE.match(line.strip())
        ]

        total_rows = len(data_lines)
        if total_rows == 0:
            return (0, 0, 0, 1.0)

        col_count = max(len(line.strip().split("|")) - 2 for line in data_lines)
        if col_count <= 0:
            col_count = len(data_lines[0].strip().split("|")) - 2
        if col_count <= 0:
            return (total_rows, 0, 0, 1.0)

        total_cells = total_rows * col_count
        empty_cells = 0
        for line in data_lines:
            cells = line.strip().split("|")[1:-1]
            for cell in cells:
                if not cell.strip():
                    empty_cells += 1

        empty_ratio = empty_cells / total_cells if total_cells > 0 else 1.0
        data_rows = max(0, total_rows - 1)

        return (total_rows, col_count, data_rows, empty_ratio)
