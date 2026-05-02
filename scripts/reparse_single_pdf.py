"""Re-parse a single PDF with fitz_pdfplumber and verify the output.

Usage:
    pixi run python scripts/reparse_single_pdf.py
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

PDF_PATH = Path(
    "data/raw/research_reports/食品饮料行业ETF周报：茅台C端改革持续进行.pdf"
)
OUTPUT_PATH = Path("data/reparse_test/食品饮料行业ETF周报.pages.json")
TARGET_PAGE = 14


def main():
    from src.parsers.fitz_pdfplumber_parser import FitzPdfPlumberParser

    config = {
        "page_chunks": True,
        "header_filter": True,
        "footer_filter": True,
        "header_zone_ratio": 0.10,
        "footer_zone_ratio": 0.10,
        "table_strategy": "text",
        "table_settings": {
            "vertical_strategy": "text",
            "horizontal_strategy": "text",
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

    output = Path(OUTPUT_PATH)
    output.parent.mkdir(parents=True, exist_ok=True)

    pages_data = [
        {
            "page_number": page.page_number,
            "text": page.text,
            "metadata": page.metadata,
        }
        for page in result.pages
    ]
    with open(output, "w", encoding="utf-8") as f:
        json.dump(pages_data, f, ensure_ascii=False, indent=2)

    print(f"Parsed: {PDF_PATH} -> {OUTPUT_PATH}")
    print(f"Total pages: {len(result.pages)}")

    print("\n" + "=" * 80)
    print(f"PAGE {TARGET_PAGE} CONTENT (first 5000 chars)")
    print("=" * 80)
    for page in result.pages:
        if page.page_number == TARGET_PAGE:
            text = page.text
            print(text[:5000])
            if len(text) > 5000:
                print(f"\n... [truncated, total {len(text)} chars]")

            print("\n" + "=" * 80)
            print("VERIFICATION")
            print("=" * 80)
            has_xiangpiaopiao = "香飘飘" in text
            has_1304 = "13.04" in text
            same_line = any(
                "香飘飘" in line and "13.04" in line for line in text.split("\n")
            )
            print(f"  香飘飘 found: {has_xiangpiaopiao}")
            print(f"  13.04 found: {has_1304}")
            print(f"  Same line: {same_line}")

            if same_line:
                for line in text.split("\n"):
                    if "香飘飘" in line and "13.04" in line:
                        print(f"  >> {line}")
            break


if __name__ == "__main__":
    main()
