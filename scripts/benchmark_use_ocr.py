"""Benchmark script: measure use_ocr performance impact on PDF parsing.

Compares parsing time with use_ocr=True vs use_ocr=False on the same PDFs.
"""
from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# Allow imports from project root
sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymupdf4llm
from loguru import logger

# Suppress loguru output for clean benchmark
logger.remove()


def generate_test_pdfs(output_dir: str, num_pages_per_pdf: int = 100, num_pdfs: int = 5) -> list[Path]:
    """Generate test PDFs with text, tables, and images to simulate financial reports.

    Args:
        output_dir: Directory to save generated PDFs.
        num_pages_per_pdf: Pages per PDF file.
        num_pdfs: Number of PDF files to generate.

    Returns:
        List of generated PDF paths.
    """
    import fitz

    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    pdfs = []

    for idx in range(num_pdfs):
        doc = fitz.open()
        for page_idx in range(num_pages_per_pdf):
            page = doc.new_page(width=595, height=842)  # A4 size

            # Text blocks simulating financial report content
            text_blocks = [
                f"## 第{idx + 1}份报告 - 第{page_idx + 1}页",
                "=" * 50,
                "一、财务摘要",
                "本年度公司实现营业收入12,345,678,901元，同比增长15.6%。",
                "净利润2,345,678,901元，同比增长23.4%。",
                "二、业务分析",
                "公司主营业务包括金融科技、数据分析、风险管理等领域。",
                "其中金融科技板块收入占比达到45%，成为公司最重要的收入来源。",
                "三、风险因素",
                "市场风险：宏观经济波动可能对公司业务产生影响。",
                "信用风险：客户违约可能导致坏账损失增加。",
                "操作风险：系统故障或人为错误可能导致业务中断。",
                "=" * 50,
                "",
            ]

            # Add text to page
            y = 72
            for line in text_blocks:
                if line.startswith("##"):
                    page.insert_text((72, y), line, fontsize=16, fontname="helv")
                    y += 24
                elif line.startswith("="):
                    page.draw_line((72, y), (523, y), width=1)
                    y += 12
                elif line.startswith("一、") or line.startswith("二、") or line.startswith("三、"):
                    page.insert_text((72, y), line, fontsize=14, fontname="helv")
                    y += 20
                elif line:
                    page.insert_text((72, y), line, fontsize=10, fontname="helv")
                    y += 14
                else:
                    y += 10

            # Add a table-like structure
            y += 10
            table_header = "| 指标 | 2024年 | 2023年 | 同比变化 |"
            page.insert_text((72, y), table_header, fontsize=9, fontname="cour")
            y += 14
            table_rows = [
                "| 营业收入 | 123.5亿 | 106.8亿 | +15.6% |",
                "| 净利润 | 23.5亿 | 19.0亿 | +23.4% |",
                "| 毛利率 | 45.2% | 42.8% | +2.4pp |",
                "| 净利率 | 19.0% | 17.8% | +1.2pp |",
            ]
            for row in table_rows:
                page.insert_text((72, y), row, fontsize=9, fontname="cour")
                y += 12

            # Add footer (noise)
            page.insert_text((72, 800), "请务必阅读正文后的重要声明", fontsize=8, fontname="helv")
            page.insert_text((280, 800), f"{page_idx + 1}", fontsize=8, fontname="helv")

        pdf_path = out / f"test_report_{idx + 1:02d}.pdf"
        doc.save(str(pdf_path))
        doc.close()
        pdfs.append(pdf_path)
        logger.info(f"Generated {pdf_path.name} ({num_pages_per_pdf} pages)")

    return pdfs


def benchmark_parse(pdf_path: Path, use_ocr: bool, warmup: bool = False) -> float:
    """Parse a single PDF and return elapsed time.

    Args:
        pdf_path: Path to PDF file.
        use_ocr: Whether to enable OCR.
        warmup: If True, don't log results (used for warmup runs).

    Returns:
        Elapsed time in seconds.
    """
    options = {
        "header": False,
        "footer": False,
        "page_separators": False,
        "write_images": False,
        "force_text": True,
        "ignore_code": True,
        "use_ocr": use_ocr,
        "ocr_language": "chi_sim+eng",
        "show_progress": False,
    }

    start = time.perf_counter()
    pymupdf4llm.to_markdown(str(pdf_path), **options)
    elapsed = time.perf_counter() - start

    return elapsed


def discover_and_sample_pdfs(raw_dir: str, num_annual: int = 3, num_research: int = 2, max_pages_per_pdf: int | None = None) -> tuple[list[Path], dict[str, int]]:
    """Discover and sample real PDFs from the data directory.

    Samples a mix of annual reports and research reports with varying sizes.

    Args:
        raw_dir: Path to the raw PDF directory.
        num_annual: Number of annual reports to sample.
        num_research: Number of research reports to sample.
        max_pages_per_pdf: Optional limit on pages per PDF (skip larger ones).

    Returns:
        Tuple of (list of sampled PDF paths, dict of page counts per PDF).
    """
    import fitz
    import random

    raw_path = Path(raw_dir)
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw PDF directory not found: {raw_dir}")

    # Discover PDFs by category
    annual_pdfs = list(raw_path.rglob("annual_reports/**/*.pdf"))
    research_pdfs = list(raw_path.rglob("research_reports/**/*.pdf"))

    # Exclude summaries (摘要) and English versions to focus on full reports
    annual_pdfs = [p for p in annual_pdfs if "摘要" not in p.name and "英文" not in p.name and "_en" not in p.name.lower()]
    research_pdfs = list(research_pdfs)  # Keep all research reports

    logger.info(f"Discovered {len(annual_pdfs)} annual reports, {len(research_pdfs)} research reports")

    # Sample with size stratification
    def sample_stratified(pdf_list: list[Path], n: int) -> list[Path]:
        if len(pdf_list) <= n:
            return pdf_list

        # Get sizes and stratify
        sized = [(p, p.stat().st_size) for p in pdf_list]
        sized.sort(key=lambda x: x[1])

        # Pick small, medium, large
        third = len(sized) // 3
        small = sized[:third]
        medium = sized[third : 2 * third]
        large = sized[2 * third :]

        sampled = []
        per_bucket = n // 3
        remainder = n % 3

        for bucket in [small, medium, large]:
            count = per_bucket + (1 if remainder > 0 else 0)
            remainder = max(0, remainder - 1)
            if bucket:
                sampled.append(random.choice(bucket)[0])

        # Fill remaining if any
        while len(sampled) < n and len(sized) > n:
            remaining = [s for s in sized if s[0] not in sampled]
            if remaining:
                sampled.append(random.choice(remaining)[0])
            else:
                break

        return sampled[:n]

    sampled_annual = sample_stratified(annual_pdfs, num_annual)
    sampled_research = sample_stratified(research_pdfs, num_research)
    sampled = sampled_annual + sampled_research

    # Get page counts
    page_counts = {}
    for pdf in sampled:
        try:
            doc = fitz.open(str(pdf))
            pages = len(doc)
            doc.close()

            if max_pages_per_pdf and pages > max_pages_per_pdf:
                logger.info(f"Skipping {pdf.name} ({pages} pages, exceeds limit {max_pages_per_pdf})")
                continue

            page_counts[str(pdf)] = pages
            logger.info(f"  {pdf.name}: {pages} pages, {pdf.stat().st_size / 1024 / 1024:.1f} MB")
        except Exception as e:
            logger.warning(f"Failed to read {pdf.name}: {e}")

    sampled = [p for p in sampled if str(p) in page_counts]
    total_pages = sum(page_counts.values())

    logger.info(f"\nSampled {len(sampled)} PDFs, {total_pages} total pages")
    return sampled, page_counts


def benchmark_parse_real_pdfs(pdfs: list[Path], page_counts: dict[str, int], warmup: bool = False) -> tuple[list[float], list[float]]:
    """Benchmark parsing on real PDFs.

    Args:
        pdfs: List of PDF paths to benchmark.
        page_counts: Dict mapping PDF path strings to page counts.
        warmup: If True, don't log detailed results.

    Returns:
        Tuple of (times_no_ocr, times_with_ocr) lists.
    """
    options_base = {
        "header": False,
        "footer": False,
        "page_separators": False,
        "write_images": False,
        "force_text": True,
        "ignore_code": True,
        "ocr_language": "chi_sim+eng",
        "show_progress": False,
    }

    times_no_ocr = []
    times_with_ocr = []

    for idx, pdf in enumerate(pdfs):
        pages = page_counts.get(str(pdf), 0)

        # Without OCR
        start = time.perf_counter()
        pymupdf4llm.to_markdown(str(pdf), use_ocr=False, **options_base)
        t_no = time.perf_counter() - start
        times_no_ocr.append(t_no)

        # With OCR
        start = time.perf_counter()
        pymupdf4llm.to_markdown(str(pdf), use_ocr=True, **options_base)
        t_with = time.perf_counter() - start
        times_with_ocr.append(t_with)

        if not warmup:
            speed_no = pages / t_no if t_no > 0 else 0
            speed_with = pages / t_with if t_with > 0 else 0
            change = (t_with / t_no - 1) * 100 if t_no > 0 else 0
            logger.info(f"  [{idx + 1}/{len(pdfs)}] {pdf.name} ({pages} pages): No OCR={t_no:.2f}s ({speed_no:.1f}p/s) | With OCR={t_with:.2f}s ({speed_with:.1f}p/s) [{change:+.1f}%]")

    return times_no_ocr, times_with_ocr


def run_real_benchmark(raw_dir: str = "data/raw", num_annual: int = 3, num_research: int = 2, max_pages_per_pdf: int | None = None, warmup_runs: int = 1) -> dict:
    """Run benchmark on real PDFs from the data directory.

    Args:
        raw_dir: Path to the raw PDF directory.
        num_annual: Number of annual reports to sample.
        num_research: Number of research reports to sample.
        max_pages_per_pdf: Optional limit on pages per PDF.
        warmup_runs: Number of warmup runs.

    Returns:
        Results dict with timing statistics.
    """
    logger.info("=" * 70)
    logger.info("Real PDF Benchmark: use_ocr Performance Impact")
    logger.info("=" * 70)

    # Step 1: Discover and sample
    logger.info(f"\n[Step 1] Sampling from {raw_dir}...")
    pdfs, page_counts = discover_and_sample_pdfs(raw_dir, num_annual, num_research, max_pages_per_pdf)
    total_pages = sum(page_counts.values())

    if not pdfs:
        logger.error("No PDFs found to benchmark")
        return {}

    # Step 2: Warmup
    if warmup_runs > 0:
        logger.info(f"\n[Step 2] Running {warmup_runs} warmup pass(es)...")
        benchmark_parse_real_pdfs([pdfs[0]], {str(pdfs[0]): page_counts.get(str(pdfs[0]), 0)}, warmup=True)
        logger.info("  Warmup complete.")

    # Step 3: Benchmark all real PDFs
    logger.info(f"\n[Step 3] Benchmarking {len(pdfs)} real PDFs ({total_pages} total pages)...")
    times_no_ocr, times_with_ocr = benchmark_parse_real_pdfs(pdfs, page_counts)

    # Step 4: Compute statistics
    total_no_ocr = sum(times_no_ocr)
    total_with_ocr = sum(times_with_ocr)
    avg_no_ocr = total_no_ocr / len(times_no_ocr) if times_no_ocr else 0
    avg_with_ocr = total_with_ocr / len(times_with_ocr) if times_with_ocr else 0
    avg_per_page_no_ocr = total_no_ocr / total_pages if total_pages > 0 else 0
    avg_per_page_with_ocr = total_with_ocr / total_pages if total_pages > 0 else 0
    pages_per_sec_no_ocr = total_pages / total_no_ocr if total_no_ocr > 0 else 0
    pages_per_sec_with_ocr = total_pages / total_with_ocr if total_with_ocr > 0 else 0
    slowdown_pct = (total_with_ocr / total_no_ocr - 1) * 100 if total_no_ocr > 0 else 0

    # Step 5: Print summary
    logger.info("\n" + "=" * 70)
    logger.info("REAL PDF BENCHMARK RESULTS")
    logger.info("=" * 70)
    logger.info(f"Total PDFs tested: {len(pdfs)}")
    logger.info(f"Total pages tested: {total_pages}")
    logger.info("")
    logger.info(f"{'Metric':<40} {'No OCR':>15} {'With OCR':>15} {'Change':>15}")
    logger.info("-" * 85)
    logger.info(f"{'Total time (s)':<40} {total_no_ocr:>15.2f} {total_with_ocr:>15.2f} {slowdown_pct:>14.1f}%")
    logger.info(f"{'Avg time per PDF (s)':<40} {avg_no_ocr:>15.2f} {avg_with_ocr:>15.2f} {((avg_with_ocr / avg_no_ocr - 1) * 100) if avg_no_ocr > 0 else 0:>14.1f}%")
    logger.info(f"{'Avg time per page (s)':<40} {avg_per_page_no_ocr:>15.3f} {avg_per_page_with_ocr:>15.3f} {((avg_per_page_with_ocr / avg_per_page_no_ocr - 1) * 100) if avg_per_page_no_ocr > 0 else 0:>14.1f}%")
    logger.info(f"{'Pages per second':<40} {pages_per_sec_no_ocr:>15.1f} {pages_per_sec_with_ocr:>15.1f} {((pages_per_sec_with_ocr / pages_per_sec_no_ocr - 1) * 100) if pages_per_sec_no_ocr > 0 else 0:>14.1f}%")
    logger.info("")
    logger.info("=" * 70)

    # Per-document breakdown
    logger.info("\nPer-document breakdown:")
    for idx, pdf in enumerate(pdfs):
        pages = page_counts.get(str(pdf), 0)
        t_no = times_no_ocr[idx]
        t_with = times_with_ocr[idx]
        change = (t_with / t_no - 1) * 100 if t_no > 0 else 0
        logger.info(f"  {pdf.name:<50s} {pages:>4}p  NoOCR={t_no:>8.2f}s  WithOCR={t_with:>8.2f}s  [{change:+.1f}%]")

    logger.info("=" * 70)

    return {
        "total_pages": total_pages,
        "total_pdfs": len(pdfs),
        "no_ocr": {"total": total_no_ocr, "avg_per_pdf": avg_no_ocr, "avg_per_page": avg_per_page_no_ocr, "pages_per_sec": pages_per_sec_no_ocr},
        "with_ocr": {"total": total_with_ocr, "avg_per_pdf": avg_with_ocr, "avg_per_page": avg_per_page_with_ocr, "pages_per_sec": pages_per_sec_with_ocr},
        "slowdown_pct": slowdown_pct,
    }


def run_benchmark(test_dir: str = "data/benchmarks/test_pdfs", num_pages: int = 100, num_pdfs: int = 5, warmup_runs: int = 1):
    """Run the full benchmark and print results.

    Args:
        test_dir: Directory for test PDFs.
        num_pages: Pages per test PDF.
        num_pdfs: Number of test PDFs.
        warmup_runs: Number of warmup runs (excluded from timing).
    """
    logger.info("=" * 70)
    logger.info("PDF Parsing Benchmark: use_ocr Performance Impact")
    logger.info("=" * 70)

    # Step 1: Generate test PDFs
    logger.info(f"\n[Step 1] Generating {num_pdfs} test PDFs ({num_pages} pages each)...")
    gen_start = time.perf_counter()
    pdfs = generate_test_pdfs(test_dir, num_pages, num_pdfs)
    gen_elapsed = time.perf_counter() - gen_start
    total_pages = num_pages * num_pdfs
    logger.info(f"Generated {len(pdfs)} PDFs, {total_pages} total pages in {gen_elapsed:.2f}s")

    # Step 2: Warmup
    if warmup_runs > 0:
        logger.info(f"\n[Step 2] Running {warmup_runs} warmup pass(es)...")
        for i in range(warmup_runs):
            logger.info(f"  Warmup {i + 1}/{warmup_runs}: parsing first PDF...")
            benchmark_parse(pdfs[0], use_ocr=False, warmup=True)
        logger.info("  Warmup complete.")

    # Step 3: Benchmark without OCR
    logger.info(f"\n[Step 3] Benchmarking WITHOUT OCR (use_ocr=False)...")
    times_no_ocr = []
    for idx, pdf in enumerate(pdfs):
        t = benchmark_parse(pdf, use_ocr=False)
        times_no_ocr.append(t)
        pages = num_pages
        logger.info(f"  [{idx + 1}/{len(pdfs)}] {pdf.name} ({pages} pages): {t:.2f}s ({pages / t:.1f} pages/s)")

    avg_no_ocr = sum(times_no_ocr) / len(times_no_ocr)
    total_no_ocr = sum(times_no_ocr)
    pages_per_sec_no_ocr = total_pages / total_no_ocr

    # Step 4: Benchmark with OCR
    logger.info(f"\n[Step 4] Benchmarking WITH OCR (use_ocr=True)...")
    times_with_ocr = []
    for idx, pdf in enumerate(pdfs):
        t = benchmark_parse(pdf, use_ocr=True)
        times_with_ocr.append(t)
        pages = num_pages
        logger.info(f"  [{idx + 1}/{len(pdfs)}] {pdf.name} ({pages} pages): {t:.2f}s ({pages / t:.1f} pages/s)")

    avg_with_ocr = sum(times_with_ocr) / len(times_with_ocr)
    total_with_ocr = sum(times_with_ocr)
    pages_per_sec_with_ocr = total_pages / total_with_ocr

    # Step 5: Print summary
    logger.info("\n" + "=" * 70)
    logger.info("BENCHMARK RESULTS")
    logger.info("=" * 70)
    logger.info(f"Total PDFs tested: {len(pdfs)}")
    logger.info(f"Total pages tested: {total_pages}")
    logger.info(f"Pages per PDF: {num_pages}")
    logger.info("")
    logger.info(f"{'Metric':<40} {'No OCR':>15} {'With OCR':>15} {'Change':>15}")
    logger.info("-" * 85)
    logger.info(f"{'Total time (s)':<40} {total_no_ocr:>15.2f} {total_with_ocr:>15.2f} {((total_with_ocr / total_no_ocr - 1) * 100):>14.1f}%")
    logger.info(f"{'Avg time per PDF (s)':<40} {avg_no_ocr:>15.2f} {avg_with_ocr:>15.2f} {((avg_with_ocr / avg_no_ocr - 1) * 100):>14.1f}%")
    logger.info(f"{'Avg time per page (s)':<40} {avg_no_ocr / num_pages:>15.3f} {avg_with_ocr / num_pages:>15.3f} {((avg_with_ocr / avg_no_ocr - 1) * 100):>14.1f}%")
    logger.info(f"{'Pages per second':<40} {pages_per_sec_no_ocr:>15.1f} {pages_per_sec_with_ocr:>15.1f} {((pages_per_sec_with_ocr / pages_per_sec_no_ocr - 1) * 100):>14.1f}%")
    logger.info("")
    logger.info("=" * 70)

    # Extrapolation
    for target_pages in [500, 1000, 2000, 5000]:
        est_no_ocr = target_pages * (avg_no_ocr / num_pages)
        est_with_ocr = target_pages * (avg_with_ocr / num_pages)
        logger.info(f"Extrapolated for {target_pages:>5} pages: No OCR={est_no_ocr:>8.1f}s ({est_no_ocr / 60:.1f}min) | With OCR={est_with_ocr:>8.1f}s ({est_with_ocr / 60:.1f}min)")

    logger.info("=" * 70)

    return {
        "total_pages": total_pages,
        "no_ocr": {"total": total_no_ocr, "avg_per_pdf": avg_no_ocr, "avg_per_page": avg_no_ocr / num_pages, "pages_per_sec": pages_per_sec_no_ocr},
        "with_ocr": {"total": total_with_ocr, "avg_per_pdf": avg_with_ocr, "avg_per_page": avg_with_ocr / num_pages, "pages_per_sec": pages_per_sec_with_ocr},
        "slowdown_pct": (total_with_ocr / total_no_ocr - 1) * 100,
    }


if __name__ == "__main__":
    import argparse

    # Ensure logs go to stdout, not to loguru log files
    import sys
    logger.add(sys.stderr, level="INFO")

    parser = argparse.ArgumentParser(description="Benchmark use_ocr performance impact")
    parser.add_argument("--mode", choices=["synthetic", "real", "both"], default="both", help="Benchmark mode")
    parser.add_argument("--num-pdfs", type=int, default=5, help="Number of synthetic test PDFs to generate")
    parser.add_argument("--num-pages", type=int, default=100, help="Pages per synthetic PDF")
    parser.add_argument("--test-dir", type=str, default="data/benchmarks/test_pdfs", help="Synthetic test PDF directory")
    parser.add_argument("--warmup", type=int, default=1, help="Number of warmup runs")
    parser.add_argument("--raw-dir", type=str, default="data/raw", help="Real PDF raw directory")
    parser.add_argument("--num-annual", type=int, default=3, help="Number of annual reports to sample")
    parser.add_argument("--num-research", type=int, default=2, help="Number of research reports to sample")
    parser.add_argument("--max-pages", type=int, default=None, help="Max pages per PDF (skip larger ones)")
    args = parser.parse_args()

    all_results = {}

    if args.mode in ["synthetic", "both"]:
        logger.info("\n" + "=" * 70)
        logger.info("MODE: Synthetic PDF Benchmark")
        logger.info("=" * 70)
        results = run_benchmark(
            test_dir=args.test_dir,
            num_pages=args.num_pages,
            num_pdfs=args.num_pdfs,
            warmup_runs=args.warmup,
        )
        all_results["synthetic"] = results

    if args.mode in ["real", "both"]:
        logger.info("\n" + "=" * 70)
        logger.info("MODE: Real PDF Benchmark")
        logger.info("=" * 70)

        real_results = run_real_benchmark(
            raw_dir=args.raw_dir,
            num_annual=args.num_annual,
            num_research=args.num_research,
            max_pages_per_pdf=args.max_pages,
            warmup_runs=args.warmup,
        )
        all_results["real"] = real_results

    # Final comparison summary
    if args.mode == "both":
        logger.info("\n" + "=" * 70)
        logger.info("CROSS-MODE COMPARISON")
        logger.info("=" * 70)
        for mode_name, res in all_results.items():
            logger.info(f"{mode_name:10s}: slowdown={res['slowdown_pct']:+.1f}%, "
                       f"no_ocr={res['no_ocr']['avg_per_page']:.3f}s/page, "
                       f"with_ocr={res['with_ocr']['avg_per_page']:.3f}s/page")
        logger.info("=" * 70)
