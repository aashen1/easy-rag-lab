"""Compare PDF parsing approaches for table quality on the bad case PDF.

Tests three parsing strategies on page 14 of the food & beverage ETF report:
1. pymupdf4llm Layout mode (current default)
2. pymupdf4llm Legacy mode (with table_strategy options)
3. fitz + pdfplumber (with table_strategy options)

Usage:
    pixi run python scripts/compare_parsers_table.py
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PDF_PATH = Path(
    "data/raw/research_reports/食品饮料行业ETF周报：茅台C端改革持续进行.pdf"
)
TARGET_PAGE = 14


def parse_pymupdf4llm_layout() -> str:
    """Parse with pymupdf4llm Layout mode (current default)."""
    import pymupdf4llm

    pymupdf4llm.use_layout(True)
    result = pymupdf4llm.to_markdown(
        str(PDF_PATH),
        page_chunks=True,
        header=False,
        footer=False,
        page_separators=False,
        write_images=False,
        force_text=True,
        ignore_code=True,
    )
    for page_data in result:
        metadata = page_data.get("metadata", {})
        if metadata.get("page_number") == TARGET_PAGE:
            return page_data.get("text", "")
    return ""


def parse_pymupdf4llm_legacy(table_strategy: str = "lines_strict") -> str:
    """Parse with pymupdf4llm Legacy mode (use_layout=False)."""
    import pymupdf4llm

    pymupdf4llm.use_layout(False)
    result = pymupdf4llm.to_markdown(
        str(PDF_PATH),
        page_chunks=True,
        write_images=False,
        force_text=True,
        ignore_code=True,
        table_strategy=table_strategy,
    )
    pymupdf4llm.use_layout(True)
    if isinstance(result, list):
        for page_data in result:
            if isinstance(page_data, dict):
                metadata = page_data.get("metadata", {})
                pn = metadata.get("page_number") or metadata.get("page")
                if pn == TARGET_PAGE:
                    return page_data.get("text", "")
            elif isinstance(page_data, str):
                pass
    if isinstance(result, str):
        return result
    return ""


def parse_fitz_pdfplumber(table_strategy: str = "lines") -> str:
    """Parse with fitz + pdfplumber."""
    from src.parsers.fitz_pdfplumber_parser import FitzPdfPlumberParser

    config = {
        "header_filter": True,
        "footer_filter": True,
        "header_zone_ratio": 0.10,
        "footer_zone_ratio": 0.10,
        "table_strategy": table_strategy,
        "table_settings": {
            "vertical_strategy": table_strategy,
            "horizontal_strategy": table_strategy,
            "snap_tolerance": 5,
            "join_tolerance": 5,
            "edge_min_length": 10,
            "intersection_x_tolerance": 5,
            "intersection_y_tolerance": 5,
        },
        "column_detection": True,
    }
    parser = FitzPdfPlumberParser(config=config)
    result = parser.parse(str(PDF_PATH))
    for page in result.pages:
        if page.page_number == TARGET_PAGE:
            return page.text
    return ""


def count_table_rows(text: str) -> int:
    """Count the number of data rows in markdown tables."""
    lines = text.split("\n")
    data_rows = 0
    for line in lines:
        stripped = line.strip()
        if (
            stripped.startswith("|")
            and stripped.endswith("|")
            and not all(c in "|-: " for c in stripped)
        ):
            data_rows += 1
    return data_rows


def check_xiangpiaopiao(text: str) -> dict:
    """Check if 香飘飘 and its closing price 13.04 are properly associated."""
    has_xiangpiaopiao = "香飘飘" in text
    has_1304 = "13.04" in text
    same_line = False
    for line in text.split("\n"):
        if "香飘飘" in line and "13.04" in line:
            same_line = True
            break
    return {
        "has_香飘飘": has_xiangpiaopiao,
        "has_13.04": has_1304,
        "same_line_or_cell": same_line,
    }


def main():
    if not PDF_PATH.exists():
        print(f"PDF not found: {PDF_PATH}")
        sys.exit(1)

    print(f"PDF: {PDF_PATH}")
    print(f"Target page: {TARGET_PAGE}")
    print("=" * 80)

    results = {}

    print("\n" + "=" * 80)
    print("1. pymupdf4llm Layout mode (current default)")
    print("=" * 80)
    text = parse_pymupdf4llm_layout()
    results["layout"] = text
    print(text[:3000])
    if len(text) > 3000:
        print(f"\n... [truncated, total {len(text)} chars]")
    print(f"\nTable data rows: {count_table_rows(text)}")
    print(f"香飘飘 check: {check_xiangpiaopiao(text)}")

    for strategy in ["lines_strict", "lines", "text"]:
        label = f"legacy_{strategy}"
        print("\n" + "=" * 80)
        print(f"2. pymupdf4llm Legacy mode (table_strategy={strategy})")
        print("=" * 80)
        text = parse_pymupdf4llm_legacy(table_strategy=strategy)
        results[label] = text
        print(text[:3000])
        if len(text) > 3000:
            print(f"\n... [truncated, total {len(text)} chars]")
        print(f"\nTable data rows: {count_table_rows(text)}")
        print(f"香飘飘 check: {check_xiangpiaopiao(text)}")

    for strategy in ["lines", "text"]:
        label = f"fitz_pdfplumber_{strategy}"
        print("\n" + "=" * 80)
        print(f"3. fitz + pdfplumber (table_strategy={strategy})")
        print("=" * 80)
        text = parse_fitz_pdfplumber(table_strategy=strategy)
        results[label] = text
        print(text[:3000])
        if len(text) > 3000:
            print(f"\n... [truncated, total {len(text)} chars]")
        print(f"\nTable data rows: {count_table_rows(text)}")
        print(f"香飘飘 check: {check_xiangpiaopiao(text)}")

    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)
    print(f"{'Method':<35} {'Rows':>5} {'香飘飘':>6} {'13.04':>6} {'同行':>6}")
    print("-" * 60)
    for name, text in results.items():
        check = check_xiangpiaopiao(text)
        rows = count_table_rows(text)
        print(
            f"{name:<35} {rows:>5} {'✓' if check['has_香飘飘'] else '✗':>6} "
            f"{'✓' if check['has_13.04'] else '✗':>6} "
            f"{'✓' if check['same_line_or_cell'] else '✗':>6}"
        )


if __name__ == "__main__":
    main()
