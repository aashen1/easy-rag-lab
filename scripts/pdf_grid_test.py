"""PDF Parsing Grid Test — Expanded 2D Matrix.

Rows = text extraction backend (8 variants)
Cols = table enhancement method (6 variants, including pdfplumber strategies)
Total = 8 × 6 = 48 combinations

Row axis — Text Extraction Backends:
  A. 4llm_layout           — pymupdf4llm use_layout(True), production config
  B. 4llm_legacy           — pymupdf4llm use_layout(False), default table_strategy
  C. 4llm_legacy_ts_text   — pymupdf4llm use_layout(False), table_strategy="text"
  D. 4llm_legacy_ts_strict — pymupdf4llm use_layout(False), table_strategy="lines_strict"
  E. 4llm_legacy_ts_explicit — pymupdf4llm use_layout(False), table_strategy="explicit"
  F. fitz_raw              — fitz get_text("dict"), no processing
  G. fitz_enhanced         — fitz + noise filter + heading detection (no tables)
  H. plumber_text          — pdfplumber extract_text() only

Column axis — Table Enhancement (pdfplumber strategies):
  1. builtin               — no pdfplumber tables, use backend's native output
  2. plumber_lines         — vertical_strategy="lines", horizontal_strategy="lines"
  3. plumber_text          — vertical_strategy="text", horizontal_strategy="text"
  4. plumber_lines_strict  — vertical_strategy="lines_strict", horizontal_strategy="lines_strict"
  5. plumber_mixed_lt      — vertical_strategy="lines", horizontal_strategy="text"
  6. plumber_mixed_tl      — vertical_strategy="text", horizontal_strategy="lines"

CRITICAL: pymupdf4llm.use_layout() is a MODULE-LEVEL function, NOT a kwarg
of to_markdown(). We must call it before each test and restore afterwards.
"""

from __future__ import annotations

import json
import re
import sys
import time
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import fitz
import pdfplumber
import pymupdf4llm
from loguru import logger

from src.parsers.pymupdf4llm_parser import PyMuPDF4LLMParser

TARGET_PDF = Path(
    r"b:\project\w0-easy-rag\data\raw\research_reports"
    r"\食品饮料行业ETF周报：茅台C端改革持续进行.pdf"
)
OUTPUT_DIR = Path(r"b:\project\w0-easy-rag\data\pdf_grid_test")


# ============================================================
# pdfplumber strategy variants
# ============================================================

PLUMBER_STRATEGIES = {
    "lines": {
        "vertical_strategy": "lines",
        "horizontal_strategy": "lines",
        "snap_tolerance": 5,
        "join_tolerance": 5,
        "edge_min_length": 10,
        "intersection_x_tolerance": 5,
        "intersection_y_tolerance": 5,
    },
    "text": {
        "vertical_strategy": "text",
        "horizontal_strategy": "text",
        "snap_tolerance": 5,
        "join_tolerance": 5,
        "min_words_vertical": 3,
        "min_words_horizontal": 1,
        "intersection_x_tolerance": 5,
        "intersection_y_tolerance": 5,
    },
    "lines_strict": {
        "vertical_strategy": "lines_strict",
        "horizontal_strategy": "lines_strict",
        "snap_tolerance": 5,
        "join_tolerance": 5,
        "edge_min_length": 10,
        "intersection_x_tolerance": 5,
        "intersection_y_tolerance": 5,
    },
    "mixed_lt": {
        "vertical_strategy": "lines",
        "horizontal_strategy": "text",
        "snap_tolerance": 5,
        "join_tolerance": 5,
        "min_words_horizontal": 1,
        "intersection_x_tolerance": 5,
        "intersection_y_tolerance": 5,
    },
    "mixed_tl": {
        "vertical_strategy": "text",
        "horizontal_strategy": "lines",
        "snap_tolerance": 5,
        "join_tolerance": 5,
        "min_words_vertical": 3,
        "intersection_x_tolerance": 5,
        "intersection_y_tolerance": 5,
    },
}


# ============================================================
# Shared helpers
# ============================================================


def _table_data_to_md(table_data: list[list[str | None]]) -> str:
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


def _pdfplumber_tables_to_md_with_strategy(
    pdf_path: str, page_idx: int, strategy: dict
) -> list[str]:
    tables_md = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_idx >= len(pdf.pages):
                return []
            page = pdf.pages[page_idx]
            plumber_tables = page.find_tables(table_settings=strategy)
            for table in plumber_tables:
                table_data = table.extract()
                if not table_data or not table_data[0]:
                    continue
                md = _table_data_to_md(table_data)
                if md:
                    tables_md.append(md)
    except Exception as e:
        logger.warning(
            f"pdfplumber table extraction failed for page {page_idx + 1}: {e}"
        )
    return tables_md


def _get_all_pdfplumber_tables(
    pdf_path: str, total_pages: int, strategy: dict
) -> dict[int, list[str]]:
    result = {}
    try:
        with pdfplumber.open(pdf_path) as pdf:
            for page_idx in range(min(total_pages, len(pdf.pages))):
                page = pdf.pages[page_idx]
                tables = page.find_tables(table_settings=strategy)
                tables_md = []
                for table in tables:
                    table_data = table.extract()
                    if table_data and table_data[0]:
                        md = _table_data_to_md(table_data)
                        if md:
                            tables_md.append(md)
                if tables_md:
                    result[page_idx] = tables_md
    except Exception as e:
        logger.warning(f"pdfplumber table extraction failed: {e}")
    return result


def _find_md_table_spans(text: str) -> list[tuple[int, int]]:
    lines = text.split("\n")
    spans = []
    in_table = False
    start = 0
    for i, line in enumerate(lines):
        stripped = line.strip()
        is_row = stripped.startswith("|") and stripped.endswith("|")
        if is_row and not in_table:
            in_table = True
            start = i
        elif not is_row and in_table:
            spans.append((start, i))
            in_table = False
    if in_table:
        spans.append((start, len(lines)))
    return spans


def _replace_md_tables_with_plumber(page_text: str, plumber_tables: list[str]) -> str:
    if not plumber_tables:
        return page_text

    spans = _find_md_table_spans(page_text)
    lines = page_text.split("\n")

    plumber_idx = 0
    offset = 0
    for start, end in spans:
        if plumber_idx < len(plumber_tables):
            replace_lines = plumber_tables[plumber_idx].split("\n")
            lines[start + offset : end + offset] = replace_lines
            offset += len(replace_lines) - (end - start)
            plumber_idx += 1

    while plumber_idx < len(plumber_tables):
        lines.append("")
        lines.extend(plumber_tables[plumber_idx].split("\n"))
        plumber_idx += 1

    return "\n".join(lines)


def _fitz_raw_extract_page(page: fitz.Page, page_number: int) -> str:
    blocks = []
    raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
    for block in raw_blocks:
        if block["type"] == 1:
            blocks.append(f"[图片: 页{page_number}]")
            continue
        if block["type"] != 0:
            continue
        full_text = ""
        for line in block.get("lines", []):
            for span in line.get("spans", []):
                full_text += span["text"]
            full_text += "\n"
        full_text = full_text.strip()
        if full_text:
            blocks.append(full_text)
    return "\n\n".join(blocks)


def _fitz_enhanced_extract_page(page: fitz.Page, page_number: int) -> str:
    page_height = page.rect.height
    page_width = page.rect.width

    noise_patterns = [
        re.compile(r"请务必阅读.{0,20}声明"),
        re.compile(r"^\s*\d+\s*$"),
        re.compile(r"^\s*\d+\s*/\s*\d+\s*$"),
        re.compile(r"(?:内部资料|机密|仅供参考).{0,30}$"),
        re.compile(r"^(?:www\.|http).+$"),
    ]

    header_zone_ratio = 0.10
    footer_zone_ratio = 0.10

    blocks = []
    raw_blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]

    for block in raw_blocks:
        if block["type"] == 1:
            blocks.append(
                {
                    "type": "image",
                    "content": f"[图片: 页{page_number}]",
                    "bbox": tuple(block["bbox"]),
                    "font_size": 0,
                    "is_bold": False,
                }
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
        y0, y1 = bbox[1], bbox[3]
        text_stripped = full_text.strip()

        if y0 < page_height * header_zone_ratio and len(text_stripped) < 80:
            continue
        if y1 > page_height * (1 - footer_zone_ratio) and len(text_stripped) < 80:
            continue
        if any(p.search(text_stripped) for p in noise_patterns):
            continue

        blocks.append(
            {
                "type": "text",
                "content": full_text,
                "bbox": bbox,
                "font_size": max_font_size,
                "is_bold": is_bold,
            }
        )

    mid_x = page_width / 2
    x_centers = [b["bbox"][0] + b["bbox"][2] for b in blocks if b["type"] == "text"]
    left_count = sum(1 for x in x_centers if x / 2 < mid_x)
    right_count = len(x_centers) - left_count
    is_two_col = (
        left_count > 2
        and right_count > 2
        and min(left_count, right_count) / max(left_count, right_count) > 0.3
    )

    if is_two_col:
        blocks.sort(key=lambda b: (0 if b["bbox"][0] < mid_x else 1, b["bbox"][1]))
    else:
        blocks.sort(key=lambda b: b["bbox"][1])

    parts = []
    for b in blocks:
        if b["type"] == "image":
            parts.append(b["content"])
            continue
        heading = ""
        if b["font_size"] > 16 and b["is_bold"]:
            heading = "#"
        elif b["font_size"] > 14 and b["is_bold"]:
            heading = "##"
        elif b["font_size"] > 12 and b["is_bold"]:
            heading = "###"
        elif b["font_size"] > 11 and b["is_bold"] and len(b["content"]) < 100:
            heading = "####"
        if heading:
            parts.append(f"{heading} {b['content']}")
        else:
            parts.append(b["content"])

    return "\n\n".join(parts)


def _plumber_extract_page(pdf_path: str, page_idx: int) -> str:
    parts = []
    try:
        with pdfplumber.open(pdf_path) as pdf:
            if page_idx >= len(pdf.pages):
                return ""
            page = pdf.pages[page_idx]
            text = page.extract_text()
            if text:
                parts.append(text)
    except Exception as e:
        logger.warning(f"pdfplumber extraction failed for page {page_idx + 1}: {e}")
    return "\n".join(parts)


# ============================================================
# Row implementations — Text Extraction Backends
# ============================================================


def _4llm_layout_parse(pdf_path: str) -> list[dict]:
    pymupdf4llm.use_layout(True)
    config = {
        "page_chunks": True,
        "header": False,
        "footer": False,
        "page_separators": False,
        "write_images": False,
        "force_text": True,
        "ignore_code": True,
        "use_ocr": True,
        "ocr_language": "chi_sim+eng",
        "show_progress": False,
        "clean_degenerate_tables": True,
    }
    parser = PyMuPDF4LLMParser(config=config)
    result = parser.parse(pdf_path)
    return [{"page_number": p.page_number, "text": p.text} for p in result.pages]


def _4llm_legacy_parse(
    pdf_path: str, table_strategy: str = "lines_strict"
) -> list[dict]:
    pymupdf4llm.use_layout(False)
    try:
        config = {
            "page_chunks": True,
            "table_strategy": table_strategy,
            "write_images": False,
            "force_text": True,
            "ignore_code": True,
            "page_separators": False,
            "show_progress": False,
            "clean_degenerate_tables": True,
        }
        parser = PyMuPDF4LLMParser(config=config)
        result = parser.parse(pdf_path)
        return [{"page_number": p.page_number, "text": p.text} for p in result.pages]
    finally:
        pymupdf4llm.use_layout(True)


def _fitz_raw_parse(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages = []
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pages.append(
            {
                "page_number": page_idx + 1,
                "text": _fitz_raw_extract_page(page, page_idx + 1),
            }
        )
    doc.close()
    return pages


def _fitz_enhanced_parse(pdf_path: str) -> list[dict]:
    doc = fitz.open(pdf_path)
    pages = []
    for page_idx in range(len(doc)):
        page = doc[page_idx]
        pages.append(
            {
                "page_number": page_idx + 1,
                "text": _fitz_enhanced_extract_page(page, page_idx + 1),
            }
        )
    doc.close()
    return pages


def _plumber_text_parse(pdf_path: str) -> list[dict]:
    pages = []
    with pdfplumber.open(pdf_path) as pdf:
        for page_idx in range(len(pdf.pages)):
            pages.append(
                {
                    "page_number": page_idx + 1,
                    "text": _plumber_extract_page(pdf_path, page_idx),
                }
            )
    return pages


ROW_BACKENDS = [
    ("A_4llm_layout", lambda pdf: _4llm_layout_parse(pdf)),
    ("B_4llm_legacy", lambda pdf: _4llm_legacy_parse(pdf, "lines_strict")),
    ("C_4llm_legacy_ts_text", lambda pdf: _4llm_legacy_parse(pdf, "text")),
    ("D_4llm_legacy_ts_strict", lambda pdf: _4llm_legacy_parse(pdf, "lines_strict")),
    ("E_4llm_legacy_ts_explicit", lambda pdf: _4llm_legacy_parse(pdf, "explicit")),
    ("F_fitz_raw", lambda pdf: _fitz_raw_parse(pdf)),
    ("G_fitz_enhanced", lambda pdf: _fitz_enhanced_parse(pdf)),
    ("H_plumber_text", lambda pdf: _plumber_text_parse(pdf)),
]


# ============================================================
# Column implementations — Table Enhancement
# ============================================================


def apply_table_col(
    pages: list[dict], col_id: str, plumber_tables: dict[int, list[str]]
) -> list[dict]:
    if col_id == "1_builtin":
        return pages

    result = []
    for p in pages:
        page_idx = p["page_number"] - 1
        pt = plumber_tables.get(page_idx, [])
        text = p["text"]
        text = _replace_md_tables_with_plumber(text, pt)
        result.append({"page_number": p["page_number"], "text": text})
    return result


COL_ENHANCEMENTS = [
    ("1_builtin", "No pdfplumber", None),
    ("2_plumber_lines", "lines+lines", "lines"),
    ("3_plumber_text", "text+text", "text"),
    ("4_plumber_lines_strict", "lines_strict+lines_strict", "lines_strict"),
    ("5_plumber_mixed_lt", "lines+text", "mixed_lt"),
    ("6_plumber_mixed_tl", "text+lines", "mixed_tl"),
]


# ============================================================
# Metrics
# ============================================================


def count_md_tables(text: str) -> int:
    count = 0
    in_table = False
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            if not in_table:
                in_table = True
                count += 1
        else:
            in_table = False
    return count


def count_md_table_rows(text: str) -> int:
    rows = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            has_content = any(c and not re.match(r"^[-:]+$", c) for c in cells)
            if has_content:
                rows += 1
    return rows


def count_empty_table_rows(text: str) -> int:
    empty = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped.startswith("|") and stripped.endswith("|"):
            cells = [c.strip() for c in stripped.split("|")[1:-1]]
            if all(not c or re.match(r"^[-:]+$", c) for c in cells):
                empty += 1
    return empty


def count_headings(text: str) -> int:
    count = 0
    for line in text.split("\n"):
        stripped = line.strip()
        if re.match(r"^#{1,6}\s", stripped):
            count += 1
    return count


@dataclass
class ComboResult:
    row_id: str = ""
    col_id: str = ""
    combo_id: str = ""
    pages: int = 0
    total_chars: int = 0
    total_tables: int = 0
    total_table_rows: int = 0
    empty_table_rows: int = 0
    headings: int = 0
    elapsed_sec: float = 0.0
    status: str = "ok"
    sample_table: str = ""
    sample_heading: str = ""


# ============================================================
# Main
# ============================================================


def main():
    if not TARGET_PDF.exists():
        logger.error(f"Target PDF not found: {TARGET_PDF}")
        sys.exit(1)

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    logger.info(f"Output directory: {OUTPUT_DIR}")
    logger.info(f"Target PDF: {TARGET_PDF}")

    pdf_path = str(TARGET_PDF)

    doc = fitz.open(pdf_path)
    total_pages = len(doc)
    doc.close()
    logger.info(f"Total pages: {total_pages}")

    results: list[ComboResult] = []

    for row_id, row_func in ROW_BACKENDS:
        for col_id, _col_desc, strategy_name in COL_ENHANCEMENTS:
            combo_id = f"{row_id}__{col_id}"
            logger.info(f"Running: {combo_id}")
            start = time.time()
            try:
                raw_pages = row_func(pdf_path)

                if strategy_name is not None:
                    strategy = PLUMBER_STRATEGIES[strategy_name]
                    plumber_tables = _get_all_pdfplumber_tables(
                        pdf_path, total_pages, strategy
                    )
                else:
                    plumber_tables = {}

                enhanced_pages = apply_table_col(raw_pages, col_id, plumber_tables)
                elapsed = time.time() - start

                all_text = "\n".join(p["text"] for p in enhanced_pages)

                r = ComboResult(
                    row_id=row_id,
                    col_id=col_id,
                    combo_id=combo_id,
                    pages=len(enhanced_pages),
                    total_chars=len(all_text),
                    total_tables=count_md_tables(all_text),
                    total_table_rows=count_md_table_rows(all_text),
                    empty_table_rows=count_empty_table_rows(all_text),
                    headings=count_headings(all_text),
                    elapsed_sec=round(elapsed, 2),
                    status="ok",
                )

                spans = _find_md_table_spans(all_text)
                if spans:
                    lines = all_text.split("\n")
                    s, e = spans[0]
                    r.sample_table = "\n".join(lines[s : min(e, s + 6)])

                for line in all_text.split("\n"):
                    if re.match(r"^#{1,6}\s", line.strip()):
                        r.sample_heading = line.strip()
                        break

                md_lines = []
                for p in enhanced_pages:
                    md_lines.append(f"<!-- Page {p['page_number']} -->\n")
                    md_lines.append(p["text"])
                    md_lines.append("\n")
                md_content = "\n".join(md_lines)
                out_file = OUTPUT_DIR / f"{combo_id}.md"
                out_file.write_text(md_content, encoding="utf-8")

                results.append(r)
                logger.info(
                    f"  {combo_id}: {r.pages}p, {r.total_chars}c, "
                    f"{r.total_tables}t, {r.headings}h, {r.elapsed_sec:.2f}s"
                )
            except Exception as e:
                elapsed = time.time() - start
                logger.error(f"  {combo_id} FAILED: {e}")
                results.append(
                    ComboResult(
                        row_id=row_id,
                        col_id=col_id,
                        combo_id=combo_id,
                        elapsed_sec=round(elapsed, 2),
                        status=f"FAILED: {e}",
                    )
                )

    # ---- Generate Summary ----
    summary_data = [
        {
            "combo": r.combo_id,
            "row": r.row_id,
            "col": r.col_id,
            "pages": r.pages,
            "chars": r.total_chars,
            "tables": r.total_tables,
            "table_rows": r.total_table_rows,
            "empty_rows": r.empty_table_rows,
            "headings": r.headings,
            "time": r.elapsed_sec,
            "status": r.status,
        }
        for r in results
    ]
    summary_file = OUTPUT_DIR / "summary.json"
    summary_file.write_text(
        json.dumps(summary_data, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # ---- Print Summary Table ----
    logger.info("\n===== GRID TEST SUMMARY =====")
    logger.info(
        f"{'Combo':<35} {'Pages':>5} {'Chars':>8} {'Tables':>6} {'Rows':>6} {'H':>3} {'Time':>6}"
    )
    logger.info("-" * 80)
    for r in results:
        if r.status == "ok":
            logger.info(
                f"{r.combo_id:<35} {r.pages:>5} {r.total_chars:>8} "
                f"{r.total_tables:>6} {r.total_table_rows:>6} {r.headings:>3} {r.elapsed_sec:>5.2f}s"
            )
        else:
            logger.info(f"{r.combo_id:<35} FAILED: {r.status[:50]}")

    logger.info(f"\nResults saved to: {OUTPUT_DIR}")


if __name__ == "__main__":
    main()
