from __future__ import annotations

import re
import warnings
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

    _SKIP_TEXT_THRESHOLD = 50

    def enhance(self, pdf_path: str, result: ParseResult) -> ParseResult:
        """Enhance table regions in a parsed result using pdfplumber.

        Opens the PDF once and extracts tables for all pages in a
        single pass, then replaces or appends tables per page.

        Pages with no markdown tables and very short text (< 50
        characters) are skipped because they are unlikely to contain
        tables that the primary parser missed.

        Args:
            pdf_path: Path to the original PDF file.
            result: ParseResult from the primary parser.

        Returns:
            ParseResult with enhanced table regions.

        Raises:
            FileNotFoundError: If the PDF file does not exist.
            Exception: If enhancement fails for any other reason.
        """
        page_count = len(result.pages)
        all_tables = self._extract_all_tables(pdf_path, page_count)

        enhanced_pages: list[ParsedPage] = []
        total_extracted = 0
        total_kept = 0
        total_reasons: dict[str, int] = {}
        skipped_pages = 0

        for page in result.pages:
            page_idx = page.page_number - 1
            spans = self._find_md_table_spans(page.text)

            if not spans and len(page.text.strip()) < self._SKIP_TEXT_THRESHOLD:
                enhanced_pages.append(page)
                skipped_pages += 1
                continue

            plumber_tables = all_tables.get(page_idx, [])
            total_extracted += len(plumber_tables)
            plumber_tables, reasons = self._filter_low_quality(plumber_tables)
            total_kept += len(plumber_tables)
            for k, v in reasons.items():
                total_reasons[k] = total_reasons.get(k, 0) + v

            if not plumber_tables:
                enhanced_pages.append(page)
                continue

            if not spans:
                new_text = self._append_tables(page.text, plumber_tables)
                enhanced_pages.append(
                    ParsedPage(
                        page_number=page.page_number,
                        text=new_text,
                        metadata=deepcopy(page.metadata),
                    )
                )
                continue

            new_text = self._replace_tables(page.text, plumber_tables)
            enhanced_pages.append(
                ParsedPage(
                    page_number=page.page_number,
                    text=new_text,
                    metadata=deepcopy(page.metadata),
                )
            )

        if total_extracted > 0:
            logger.debug(
                f"Table enhancement: extracted={total_extracted}, kept={total_kept}, "
                f"filtered={total_extracted - total_kept}, skipped_pages={skipped_pages}"
                + (
                    f" ({', '.join(f'{k}={v}' for k, v in total_reasons.items())})"
                    if total_reasons
                    else ""
                )
            )

        return ParseResult(
            pages=enhanced_pages,
            metadata=deepcopy(result.metadata),
        )

    def enhance_page(self, pdf_path: str, page_number: int, existing_text: str) -> str:
        """Enhance tables on a single page using pdfplumber.

        Extracts tables for the specified page only, filters low-quality
        results, and either replaces existing markdown tables in the
        text or appends the extracted tables at the end.

        Args:
            pdf_path: Path to the original PDF file.
            page_number: 1-indexed page number to enhance.
            existing_text: Text already extracted by the primary parser.

        Returns:
            Enhanced page text with improved table formatting.
        """
        page_idx = page_number - 1
        all_tables = self._extract_all_tables(pdf_path, page_number)
        plumber_tables = all_tables.get(page_idx, [])

        if not plumber_tables:
            return existing_text

        plumber_tables, _ = self._filter_low_quality(plumber_tables)

        if not plumber_tables:
            return existing_text

        spans = self._find_md_table_spans(existing_text)
        if spans:
            return self._replace_tables(existing_text, plumber_tables)
        return self._append_tables(existing_text, plumber_tables)

    def enhance_table(
        self, pdf_path: str, page_number: int, table_index: int, existing_text: str
    ) -> str:
        """Enhance a single table on a page using pdfplumber.

        Extracts tables for the specified page, selects the table at
        the given 1-indexed position, and replaces only that table in
        the existing text.  If the specific table does not exist or
        fails quality filtering, the original text is returned unchanged.

        Args:
            pdf_path: Path to the original PDF file.
            page_number: 1-indexed page number containing the table.
            table_index: 1-indexed position of the table within the page.
            existing_text: Text already extracted by the primary parser.

        Returns:
            Enhanced text with the specified table replaced.
        """
        page_idx = page_number - 1
        table_idx = table_index - 1
        all_tables = self._extract_all_tables(pdf_path, page_number)
        page_tables = all_tables.get(page_idx, [])

        if table_idx >= len(page_tables):
            return existing_text

        target_table = page_tables[table_idx]
        filtered, _ = self._filter_low_quality([target_table])

        if not filtered:
            return existing_text

        plumber_md = filtered[0]
        spans = self._find_md_table_spans(existing_text)

        if table_idx < len(spans):
            start, end = spans[table_idx]
            return existing_text[:start] + plumber_md + existing_text[end:]

        return self._append_tables(existing_text, [plumber_md])

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

    def _extract_all_tables(
        self, pdf_path: str, page_count: int
    ) -> dict[int, list[str]]:
        """Extract tables from all pages in a single PDF open pass.

        Opens the PDF once, iterates over every page, and collects
        all tables found by pdfplumber.  This avoids the overhead
        of opening/closing the PDF file once per page.

        Args:
            pdf_path: Path to the PDF file.
            page_count: Number of pages to process.

        Returns:
            Dict mapping 0-indexed page number to list of markdown
            table strings extracted by pdfplumber.
        """
        result: dict[int, list[str]] = {}

        try:
            import pdfplumber

            settings = dict(self._table_settings)
            v_strategy = self._vertical_strategy or self._strategy
            h_strategy = self._horizontal_strategy or self._strategy
            settings["vertical_strategy"] = v_strategy
            settings["horizontal_strategy"] = h_strategy

            with warnings.catch_warnings():
                warnings.filterwarnings("once", message="Could not get FontBBox")
                with pdfplumber.open(pdf_path) as pdf:
                    for page_idx in range(min(page_count, len(pdf.pages))):
                        page = pdf.pages[page_idx]
                        try:
                            plumber_tables = page.find_tables(table_settings=settings)
                        except Exception as e:
                            logger.warning(
                                f"pdfplumber find_tables failed for page "
                                f"{page_idx + 1}: {str(e)}"
                            )
                            continue

                        tables: list[str] = []
                        for table in plumber_tables:
                            table_data = table.extract()
                            if not table_data or not table_data[0]:
                                continue
                            md = self._table_to_markdown(table_data)
                            if md:
                                tables.append(md)

                        if tables:
                            result[page_idx] = tables

        except Exception as e:
            logger.warning(f"pdfplumber open failed for {pdf_path}: {str(e)}")

        return result

    @staticmethod
    def _table_to_markdown(table_data: list[list[str | None]]) -> str:
        """Convert pdfplumber table data to Markdown format.

        Filters out degenerate rows where all cells are empty or contain
        only whitespace, as well as sparse rows where more than half the
        cells are empty.  Sparse rows typically arise when pdfplumber's
        text strategy captures page headers, footers, or section titles
        as part of the table bounding box.

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

        dense_rows = non_degenerate
        if col_count >= 4:
            dense_rows = [
                row
                for row in non_degenerate
                if sum(1 for cell in row if cell.strip()) > col_count / 2
            ]

        if not dense_rows:
            dense_rows = non_degenerate

        lines: list[str] = []
        lines.append("| " + " | ".join(dense_rows[0]) + " |")
        lines.append("|" + "|".join(["---"] * col_count) + "|")
        for row in dense_rows[1:]:
            lines.append("| " + " | ".join(row) + " |")

        return "\n".join(lines)

    def _filter_low_quality(
        self, tables: list[str]
    ) -> tuple[list[str], dict[str, int]]:
        """Filter tables by quality criteria.

        A table is considered low-quality if it has fewer than
        ``min_columns`` columns, more than ``max_empty_ratio`` empty
        cells, or fewer than ``min_data_rows`` data rows.

        Args:
            tables: List of markdown table strings.

        Returns:
            Tuple of (filtered tables, filter_reasons dict).
        """
        result: list[str] = []
        reasons: dict[str, int] = {}
        for md in tables:
            rows, cols, data_rows, empty_ratio, merged_ratio = (
                self._count_table_quality(md)
            )
            if cols < self._min_columns:
                reasons["cols_too_few"] = reasons.get("cols_too_few", 0) + 1
                continue
            if empty_ratio > self._max_empty_ratio:
                reasons["empty_ratio_high"] = reasons.get("empty_ratio_high", 0) + 1
                continue
            if data_rows < self._min_data_rows:
                reasons["rows_too_few"] = reasons.get("rows_too_few", 0) + 1
                continue
            result.append(md)
        return result, reasons

    @staticmethod
    def _append_tables(text: str, plumber_tables: list[str]) -> str:
        """Append pdfplumber-extracted tables to page text.

        Used when the primary parser did not produce any markdown
        tables.  The extracted tables are appended at the end of
        the page text so that no existing content is lost.

        Args:
            text: Original page text (without markdown tables).
            plumber_tables: List of pdfplumber-extracted markdown tables.

        Returns:
            Text with tables appended.
        """
        if not plumber_tables:
            return text

        table_block = "\n\n".join(plumber_tables)

        if text.strip():
            return f"{text.rstrip()}\n\n{table_block}\n"
        return f"{table_block}\n"

    def _replace_tables(self, text: str, plumber_tables: list[str]) -> str:
        """Replace markdown tables in text with pdfplumber versions.

        The replacement strategy depends on ``replace_policy``:
        - "better_wins": Replace each original table with the
          corresponding pdfplumber table when the pdfplumber version
          is deemed higher quality by ``_is_better_quality``.
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
                    should_replace = self._is_better_quality(
                        original_tables[span_idx], plumber_md
                    )

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

    def _is_better_quality(self, orig_md: str, plumber_md: str) -> bool:
        """Determine whether the plumber table is better than the original.

        Comparison priority:
        1. Merged cells: if the original has ``<br>`` tags (merged
           cells) and plumber does not, plumber wins; and vice versa.
        2. Empty cell ratio: if the difference exceeds 15 percentage
           points, the one with the lower ratio wins.
        3. Data row count: if the difference exceeds 30%, the one
           with more rows wins.
        4. Default: when quality is hard to judge, prefer the
           plumber (enhancement) result.

        Args:
            orig_md: Original markdown table string.
            plumber_md: Pdfplumber-extracted markdown table string.

        Returns:
            True if the plumber version should replace the original.
        """
        orig_q = self._count_table_quality(orig_md)
        plumber_q = self._count_table_quality(plumber_md)

        if orig_q[4] > 0 and plumber_q[4] == 0:
            return True

        if plumber_q[4] > 0 and orig_q[4] == 0:
            return False

        if abs(orig_q[3] - plumber_q[3]) > 0.15:
            return plumber_q[3] < orig_q[3]

        if orig_q[2] > 0 and plumber_q[2] > 0:
            row_diff = abs(plumber_q[2] - orig_q[2]) / max(orig_q[2], plumber_q[2])
            if row_diff > 0.3:
                return plumber_q[2] > orig_q[2]

        return True

    @staticmethod
    def _count_table_quality(
        md_table: str,
    ) -> tuple[int, int, int, float, float]:
        """Compute quality metrics for a markdown table.

        Args:
            md_table: Markdown table string.

        Returns:
            Tuple of (total_rows, col_count, data_rows, empty_ratio,
            merged_ratio) where *data_rows* excludes the header and
            separator rows, *empty_ratio* is the fraction of empty
            cells across all rows (including header), and
            *merged_ratio* is the fraction of cells containing
            ``<br>`` tags (indicating merged cells from the primary
            parser).
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
            return (0, 0, 0, 1.0, 0.0)

        col_count = max(len(line.strip().split("|")) - 2 for line in data_lines)
        if col_count <= 0:
            col_count = len(data_lines[0].strip().split("|")) - 2
        if col_count <= 0:
            return (total_rows, 0, 0, 1.0, 0.0)

        total_cells = total_rows * col_count
        empty_cells = 0
        merged_cells = 0
        for line in data_lines:
            cells = line.strip().split("|")[1:-1]
            for cell in cells:
                stripped = cell.strip()
                if not stripped:
                    empty_cells += 1
                elif "<br>" in stripped:
                    merged_cells += 1

        empty_ratio = empty_cells / total_cells if total_cells > 0 else 1.0
        merged_ratio = merged_cells / total_cells if total_cells > 0 else 0.0
        data_rows = max(0, total_rows - 1)

        return (total_rows, col_count, data_rows, empty_ratio, merged_ratio)
