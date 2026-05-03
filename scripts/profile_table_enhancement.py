"""Profile PDF parsing time: with vs without table enhancement.

Compares two configurations:
  A) primary=pymupdf4llm, enhancer=None          (baseline)
  B) primary=pymupdf4llm, enhancer=pdfplumber    (table enhancement ON)

Forces re-parse (ignores cache), measures per-file wall time,
and prints a summary table.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from loguru import logger

from src.parsers.registry import ParserRegistry

logger.remove()
logger.add(sys.stderr, level="WARNING")

PRIMARY_CONFIG = {
    "header": False,
    "footer": False,
    "page_separators": False,
    "write_images": False,
    "page_chunks": True,
    "force_text": True,
    "ignore_code": True,
    "use_ocr": False,
    "ocr_language": "chi_sim+eng",
    "show_progress": False,
    "clean_degenerate_tables": True,
}

ENHANCER_CONFIG = {
    "strategy": "text",
    "vertical_strategy": "text",
    "horizontal_strategy": "text",
    "table_settings": {
        "snap_tolerance": 5,
        "join_tolerance": 5,
        "edge_min_length": 10,
        "intersection_x_tolerance": 5,
        "intersection_y_tolerance": 5,
    },
    "quality_filter": {
        "min_columns": 3,
        "max_empty_ratio": 0.5,
        "min_data_rows": 2,
    },
    "replace_policy": "better_wins",
}

SAMPLE_PDFS = [
    "annual_reports/2023/五粮液/2023年年度报告摘要.pdf",
    "annual_reports/2023/恒瑞医药/恒瑞医药2023年年度报告摘要.pdf",
    "annual_reports/2023/海天味业/海天味业2023年年度报告摘要.pdf",
    "annual_reports/2024/比亚迪/2024年年度报告摘要.pdf",
    "annual_reports/2024/宁德时代/2024年年度报告摘要.pdf",
    "research_reports/2026年中国白酒行业信用观察.pdf",
    "research_reports/2026年光伏行业分析.pdf",
    "research_reports/半导体行业3月份月报：AI算力驱动上游代工增长，GTC大会发布Vera Rubin AI计算平台.pdf",
    "research_reports/银行业二季度投资策略：绩优成长与稳健红利双主线并举.pdf",
    "research_reports/低空经济行业深度报告之安徽篇：安徽低空，蓄势高飞.pdf",
    "research_reports/商业航天电源行业深度报告：全球卫星星座加速组网，空间电源需求拐点将至.pdf",
    "research_reports/食品饮料行业ETF周报：茅台C端改革持续进行.pdf",
]

RAW_DIR = Path("data/raw")


def _file_size_mb(path: Path) -> float:
    return path.stat().st_size / (1024 * 1024)


def _page_count(path: Path) -> int:
    import fitz

    doc = fitz.open(str(path))
    count = len(doc)
    doc.close()
    return count


def _parse_one(parser, pdf_path: str) -> float:
    t0 = time.perf_counter()
    parser.parse(pdf_path)
    return time.perf_counter() - t0


def main():
    print("=" * 80)
    print("PDF Parsing Profiling: Table Enhancement ON vs OFF")
    print("=" * 80)

    valid_pdfs = []
    for rel in SAMPLE_PDFS:
        p = RAW_DIR / rel
        if p.exists():
            valid_pdfs.append((rel, p))
        else:
            print(f"  [SKIP] not found: {rel}")

    if not valid_pdfs:
        print("No valid PDFs found. Aborting.")
        return

    print(f"\nFound {len(valid_pdfs)} PDFs. Pre-scanning page counts...\n")

    pdf_info = []
    for rel, p in valid_pdfs:
        try:
            pages = _page_count(p)
            size_mb = _file_size_mb(p)
            pdf_info.append((rel, p, pages, size_mb))
        except Exception as e:
            print(f"  [SKIP] cannot read {rel}: {e}")

    pdf_info.sort(key=lambda x: x[2])

    print(f"{'PDF':<60} {'Pages':>5} {'SizeMB':>7}")
    print("-" * 74)
    for rel, _, pages, size_mb in pdf_info:
        short = rel if len(rel) <= 58 else "..." + rel[-55:]
        print(f"{short:<60} {pages:>5} {size_mb:>7.1f}")

    parser_a = ParserRegistry.get_composite("pymupdf4llm", None, PRIMARY_CONFIG, None)
    parser_b = ParserRegistry.get_composite(
        "pymupdf4llm", "pdfplumber", PRIMARY_CONFIG, ENHANCER_CONFIG
    )

    results = []

    print(f"\n{'=' * 80}")
    print("Running benchmarks (force re-parse, no cache)...")
    print(f"{'=' * 80}\n")

    for i, (rel, p, pages, size_mb) in enumerate(pdf_info):
        label = rel if len(rel) <= 58 else "..." + rel[-55:]
        print(f"[{i + 1}/{len(pdf_info)}] {label}")

        try:
            time_a = _parse_one(parser_a, str(p))
        except Exception as e:
            print(f"  Config A FAILED: {e}")
            time_a = None

        try:
            time_b = _parse_one(parser_b, str(p))
        except Exception as e:
            print(f"  Config B FAILED: {e}")
            time_b = None

        if time_a is not None and time_b is not None:
            overhead = time_b - time_a
            overhead_pct = (overhead / time_a * 100) if time_a > 0 else float("inf")
            print(
                f"  A(no-enhance)={time_a:.2f}s  B(enhance)={time_b:.2f}s  "
                f"overhead={overhead:+.2f}s ({overhead_pct:+.1f}%)"
            )
        else:
            overhead = None
            overhead_pct = None
            print(f"  A={time_a}  B={time_b}")

        results.append(
            {
                "rel": rel,
                "pages": pages,
                "size_mb": size_mb,
                "time_a": time_a,
                "time_b": time_b,
                "overhead": overhead,
                "overhead_pct": overhead_pct,
            }
        )

    print(f"\n{'=' * 80}")
    print("SUMMARY")
    print(f"{'=' * 80}\n")

    print(f"{'PDF':<50} {'Pages':>5} {'A(s)':>7} {'B(s)':>7} {'Δ(s)':>7} {'Δ%':>7}")
    print("-" * 85)

    total_a = 0.0
    total_b = 0.0
    valid_count = 0

    for r in results:
        short = r["rel"] if len(r["rel"]) <= 48 else "..." + r["rel"][-45:]
        if r["time_a"] is not None and r["time_b"] is not None:
            print(
                f"{short:<50} {r['pages']:>5} {r['time_a']:>7.2f} {r['time_b']:>7.2f} "
                f"{r['overhead']:>+7.2f} {r['overhead_pct']:>+6.1f}%"
            )
            total_a += r["time_a"]
            total_b += r["time_b"]
            valid_count += 1
        else:
            print(f"{short:<50} {r['pages']:>5}   FAIL   FAIL     N/A     N/A")

    if valid_count > 0:
        total_overhead = total_b - total_a
        total_overhead_pct = (
            (total_overhead / total_a * 100) if total_a > 0 else float("inf")
        )
        print("-" * 85)
        print(
            f"{'TOTAL':<50} {'':>5} {total_a:>7.2f} {total_b:>7.2f} "
            f"{total_overhead:>+7.2f} {total_overhead_pct:>+6.1f}%"
        )
        avg_overhead_per_page = total_overhead / sum(
            r["pages"] for r in results if r["time_a"] is not None
        )
        print(f"\nAverage overhead per page: {avg_overhead_per_page:.3f}s")

    print("\nConfig A = pymupdf4llm only (no table enhancement)")
    print("Config B = pymupdf4llm + pdfplumber table enhancement")


if __name__ == "__main__":
    main()
