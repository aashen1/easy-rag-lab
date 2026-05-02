from __future__ import annotations

import re
from dataclasses import dataclass, field

_MD_TABLE_ROW_RE = re.compile(r"^\|.*\|$")
_MD_SEPARATOR_RE = re.compile(r"^\|[\s\-:]+\|[\s\-:|]*$")


@dataclass
class PageMetrics:
    page_number: int
    char_count: int
    word_count: int
    table_count: int
    table_rows: list[int] = field(default_factory=list)
    table_cols: list[int] = field(default_factory=list)
    table_empty_ratios: list[float] = field(default_factory=list)
    heading_count: int
    markdown_valid: bool


@dataclass
class DocumentMetrics:
    pipeline_name: str
    pdf_path: str
    page_count: int
    total_chars: int
    total_words: int
    total_tables: int
    avg_table_rows: float
    avg_table_cols: float
    avg_table_empty_ratio: float
    total_headings: int
    markdown_valid_pages: int
    markdown_valid_ratio: float
    page_metrics: list[PageMetrics] = field(default_factory=list)
    parse_time_seconds: float = 0.0


def compute_page_metrics(page_text: str, page_number: int) -> PageMetrics:
    """Compute metrics for a single parsed page.

    Args:
        page_text: Markdown text of the parsed page.
        page_number: 1-indexed page number.

    Returns:
        PageMetrics with structural quality measurements.
    """
    char_count = len(page_text)
    word_count = len(page_text.split())

    tables = _find_markdown_tables(page_text)
    table_count = len(tables)
    table_rows = []
    table_cols = []
    table_empty_ratios = []

    for table_text in tables:
        rows, cols, empty_ratio = _analyze_table(table_text)
        table_rows.append(rows)
        table_cols.append(cols)
        table_empty_ratios.append(empty_ratio)

    heading_count = _count_headings(page_text)

    markdown_valid = _check_markdown_valid(page_text)

    return PageMetrics(
        page_number=page_number,
        char_count=char_count,
        word_count=word_count,
        table_count=table_count,
        table_rows=table_rows,
        table_cols=table_cols,
        table_empty_ratios=table_empty_ratios,
        heading_count=heading_count,
        markdown_valid=markdown_valid,
    )


def compute_document_metrics(
    pipeline_name: str,
    pdf_path: str,
    page_metrics_list: list[PageMetrics],
    parse_time_seconds: float = 0.0,
) -> DocumentMetrics:
    """Aggregate page-level metrics into document-level metrics.

    Args:
        pipeline_name: Name of the parser pipeline.
        pdf_path: Path to the PDF file.
        page_metrics_list: List of PageMetrics for each page.
        parse_time_seconds: Time taken to parse the document.

    Returns:
        DocumentMetrics with aggregated measurements.
    """
    page_count = len(page_metrics_list)
    total_chars = sum(m.char_count for m in page_metrics_list)
    total_words = sum(m.word_count for m in page_metrics_list)
    total_tables = sum(m.table_count for m in page_metrics_list)
    total_headings = sum(m.heading_count for m in page_metrics_list)
    markdown_valid_pages = sum(1 for m in page_metrics_list if m.markdown_valid)

    all_rows = [r for m in page_metrics_list for r in m.table_rows]
    all_cols = [c for m in page_metrics_list for c in m.table_cols]
    all_empty = [e for m in page_metrics_list for e in m.table_empty_ratios]

    avg_table_rows = sum(all_rows) / len(all_rows) if all_rows else 0.0
    avg_table_cols = sum(all_cols) / len(all_cols) if all_cols else 0.0
    avg_table_empty_ratio = sum(all_empty) / len(all_empty) if all_empty else 0.0
    markdown_valid_ratio = markdown_valid_pages / page_count if page_count > 0 else 0.0

    return DocumentMetrics(
        pipeline_name=pipeline_name,
        pdf_path=pdf_path,
        page_count=page_count,
        total_chars=total_chars,
        total_words=total_words,
        total_tables=total_tables,
        avg_table_rows=avg_table_rows,
        avg_table_cols=avg_table_cols,
        avg_table_empty_ratio=avg_table_empty_ratio,
        total_headings=total_headings,
        markdown_valid_pages=markdown_valid_pages,
        markdown_valid_ratio=markdown_valid_ratio,
        page_metrics=page_metrics_list,
        parse_time_seconds=parse_time_seconds,
    )


def _find_markdown_tables(text: str) -> list[str]:
    """Extract individual markdown table strings from text.

    Args:
        text: Page text containing potential markdown tables.

    Returns:
        List of markdown table strings.
    """
    lines = text.split("\n")
    tables = []
    current_table_lines = []
    in_table = False
    has_separator = False

    for line in lines:
        stripped = line.strip()
        is_row = bool(_MD_TABLE_ROW_RE.match(stripped))
        is_sep = bool(_MD_SEPARATOR_RE.match(stripped))

        if is_row:
            in_table = True
            current_table_lines.append(line)
            if is_sep:
                has_separator = True
        else:
            if in_table and has_separator and current_table_lines:
                tables.append("\n".join(current_table_lines))
            current_table_lines = []
            in_table = False
            has_separator = False

    if in_table and has_separator and current_table_lines:
        tables.append("\n".join(current_table_lines))

    return tables


def _analyze_table(table_text: str) -> tuple[int, int, float]:
    """Analyze a markdown table's structure.

    Args:
        table_text: A single markdown table string.

    Returns:
        Tuple of (row_count, col_count, empty_ratio).
    """
    lines = table_text.strip().split("\n")
    data_lines = [
        line
        for line in lines
        if _MD_TABLE_ROW_RE.match(line.strip())
        and not _MD_SEPARATOR_RE.match(line.strip())
    ]

    row_count = len(data_lines)
    if row_count == 0:
        return (0, 0, 1.0)

    col_count = max(len(line.strip().split("|")) - 2 for line in data_lines)
    if col_count <= 0:
        col_count = len(data_lines[0].strip().split("|")) - 2
    if col_count <= 0:
        return (row_count, 0, 1.0)

    total_cells = row_count * col_count
    empty_cells = 0
    for line in data_lines:
        cells = line.strip().split("|")[1:-1]
        for cell in cells:
            if not cell.strip():
                empty_cells += 1

    empty_ratio = empty_cells / total_cells if total_cells > 0 else 1.0
    return (row_count, col_count, empty_ratio)


def _count_headings(text: str) -> int:
    """Count markdown headings in text.

    Args:
        text: Page text.

    Returns:
        Number of heading lines.
    """
    count = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("#") and len(stripped) > 1 and stripped[1] in (" ", "#"):
            count += 1
    return count


def _check_markdown_valid(text: str) -> bool:
    """Check if the markdown text has basic structural validity.

    A page is considered invalid if it's empty or contains only
    whitespace characters.

    Args:
        text: Page text.

    Returns:
        True if the page has any content.
    """
    return bool(text.strip())
