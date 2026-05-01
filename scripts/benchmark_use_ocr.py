"""Benchmark script: measure use_ocr performance impact on PDF parsing.

Compares parsing time with use_ocr=True vs use_ocr=False on the same PDFs.
Supports two sampling strategies:
  - "stratified": original stratified sampling by category and size
  - "meal": Meal-compatible sampling (count/pages/ratio modes with seed)
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

sys.path.insert(0, str(Path(__file__).resolve().parent))

import pymupdf4llm
from loguru import logger

SAMPLING_MODE = "meal"

PYMUPDF4LLM_OPTIONS = {
    "header": False,
    "footer": False,
    "page_separators": False,
    "write_images": False,
    "force_text": True,
    "ignore_code": True,
    "ocr_language": "chi_sim+eng",
    "show_progress": False,
}


@dataclass
class ResourceSnapshot:
    """A single resource usage sample point.

    Args:
        timestamp: Time of sample (perf_counter).
        cpu_percent: CPU usage percentage.
        memory_mb: RSS memory in MB.
    """

    timestamp: float
    cpu_percent: float
    memory_mb: float


@dataclass
class ResourceMonitor:
    """Background thread resource monitor using psutil.

    Args:
        interval: Sampling interval in seconds.
        enabled: Whether monitoring is active.

    Raises:
        ImportError: If psutil is not installed and enabled=True.
    """

    interval: float = 0.5
    enabled: bool = True
    _samples: list[ResourceSnapshot] = field(default_factory=list, repr=False)
    _running: bool = field(default=False, repr=False)
    _thread: Any = field(default=None, repr=False)
    _process: Any = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.enabled:
            try:
                import psutil

                self._process = psutil.Process(os.getpid())
            except ImportError:
                logger.warning("psutil not installed, resource monitoring disabled")
                self.enabled = False

    def start(self) -> None:
        """Start background resource monitoring."""
        if not self.enabled:
            return
        import threading

        self._running = True
        self._samples = []

        def _loop() -> None:
            while self._running:
                try:
                    cpu = self._process.cpu_percent(interval=0)
                    mem_info = self._process.memory_info()
                    memory_mb = mem_info.rss / 1024 / 1024
                    self._samples.append(
                        ResourceSnapshot(
                            timestamp=time.perf_counter(),
                            cpu_percent=cpu,
                            memory_mb=memory_mb,
                        )
                    )
                except Exception:
                    pass
                time.sleep(self.interval)

        self._thread = threading.Thread(target=_loop, daemon=True)
        self._thread.start()

    def stop(self) -> dict[str, float]:
        """Stop monitoring and return aggregated resource stats.

        Returns:
            Dict with cpu_avg, cpu_peak, memory_avg_mb, memory_peak_mb.
        """
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

        if not self._samples:
            return {
                "cpu_avg": 0.0,
                "cpu_peak": 0.0,
                "memory_avg_mb": 0.0,
                "memory_peak_mb": 0.0,
            }

        cpu_values = [s.cpu_percent for s in self._samples]
        mem_values = [s.memory_mb for s in self._samples]

        return {
            "cpu_avg": sum(cpu_values) / len(cpu_values),
            "cpu_peak": max(cpu_values),
            "memory_avg_mb": sum(mem_values) / len(mem_values),
            "memory_peak_mb": max(mem_values),
        }


@dataclass
class PerDocResult:
    """Per-document benchmark result.

    Args:
        filename: PDF file name.
        pages: Number of pages.
        file_size_mb: File size in MB.
        time_no_ocr: Parse time without OCR in seconds.
        time_with_ocr: Parse time with OCR in seconds.
    """

    filename: str
    pages: int
    file_size_mb: float
    time_no_ocr: float
    time_with_ocr: float

    @property
    def slowdown_pct(self) -> float:
        """OCR slowdown percentage."""
        return (
            (self.time_with_ocr / self.time_no_ocr - 1) * 100
            if self.time_no_ocr > 0
            else 0.0
        )

    @property
    def pages_per_sec_no_ocr(self) -> float:
        """Throughput without OCR."""
        return self.pages / self.time_no_ocr if self.time_no_ocr > 0 else 0.0

    @property
    def pages_per_sec_with_ocr(self) -> float:
        """Throughput with OCR."""
        return self.pages / self.time_with_ocr if self.time_with_ocr > 0 else 0.0


def compute_stats(values: list[float]) -> dict[str, float]:
    """Compute descriptive statistics for a list of values.

    Args:
        values: List of numeric values.

    Returns:
        Dict with mean, std, median, p95, min, max.
    """
    if not values:
        return {
            "mean": 0.0,
            "std": 0.0,
            "median": 0.0,
            "p95": 0.0,
            "min": 0.0,
            "max": 0.0,
        }

    n = len(values)
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / n if n > 1 else 0.0
    std = math.sqrt(variance)

    sorted_vals = sorted(values)
    if n % 2 == 0:
        median = (sorted_vals[n // 2 - 1] + sorted_vals[n // 2]) / 2
    else:
        median = sorted_vals[n // 2]

    p95_idx = min(int(math.ceil(0.95 * n)) - 1, n - 1)
    p95 = sorted_vals[p95_idx]

    return {
        "mean": mean,
        "std": std,
        "median": median,
        "p95": p95,
        "min": sorted_vals[0],
        "max": sorted_vals[-1],
    }


def generate_test_pdfs(
    output_dir: str, num_pages_per_pdf: int = 100, num_pdfs: int = 5
) -> list[Path]:
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
            page = doc.new_page(width=595, height=842)

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

            y = 72
            for line in text_blocks:
                if line.startswith("##"):
                    page.insert_text((72, y), line, fontsize=16, fontname="helv")
                    y += 24
                elif line.startswith("="):
                    page.draw_line((72, y), (523, y), width=1)
                    y += 12
                elif (
                    line.startswith("一、")
                    or line.startswith("二、")
                    or line.startswith("三、")
                ):
                    page.insert_text((72, y), line, fontsize=14, fontname="helv")
                    y += 20
                elif line:
                    page.insert_text((72, y), line, fontsize=10, fontname="helv")
                    y += 14
                else:
                    y += 10

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

            page.insert_text(
                (72, 800), "请务必阅读正文后的重要声明", fontsize=8, fontname="helv"
            )
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
    options = {**PYMUPDF4LLM_OPTIONS, "use_ocr": use_ocr}

    start = time.perf_counter()
    pymupdf4llm.to_markdown(str(pdf_path), **options)
    elapsed = time.perf_counter() - start

    return elapsed


def _discover_all_pdfs(raw_dir: str) -> list[Path]:
    """Discover all PDFs from the raw directory.

    Args:
        raw_dir: Path to the raw PDF directory.

    Returns:
        List of all discovered PDF paths.

    Raises:
        FileNotFoundError: If raw_dir does not exist.
    """
    raw_path = Path(raw_dir)
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw PDF directory not found: {raw_dir}")

    all_pdfs = sorted(raw_path.rglob("**/*.pdf"))
    logger.info(f"Discovered {len(all_pdfs)} PDF files in {raw_dir}")
    return all_pdfs


def _count_pdf_pages(pdf_path: Path) -> int:
    """Count pages in a PDF file.

    Args:
        pdf_path: Path to the PDF file.

    Returns:
        Number of pages, or 0 if the file cannot be read.
    """
    import fitz

    try:
        doc = fitz.open(str(pdf_path))
        pages = len(doc)
        doc.close()
        return pages
    except Exception as e:
        logger.warning(f"Failed to read {pdf_path.name}: {e}")
        return 0


def discover_and_sample_pdfs(
    raw_dir: str,
    num_annual: int = 3,
    num_research: int = 2,
    max_pages_per_pdf: int | None = None,
) -> tuple[list[Path], dict[str, int]]:
    """Discover and sample real PDFs using stratified sampling by category and size.

    Args:
        raw_dir: Path to the raw PDF directory.
        num_annual: Number of annual reports to sample.
        num_research: Number of research reports to sample.
        max_pages_per_pdf: Optional limit on pages per PDF (skip larger ones).

    Returns:
        Tuple of (list of sampled PDF paths, dict of page counts per PDF).

    Raises:
        FileNotFoundError: If raw_dir does not exist.
    """
    import fitz

    raw_path = Path(raw_dir)
    if not raw_path.exists():
        raise FileNotFoundError(f"Raw PDF directory not found: {raw_dir}")

    annual_pdfs = list(raw_path.rglob("annual_reports/**/*.pdf"))
    research_pdfs = list(raw_path.rglob("research_reports/**/*.pdf"))

    annual_pdfs = [
        p
        for p in annual_pdfs
        if "摘要" not in p.name and "英文" not in p.name and "_en" not in p.name.lower()
    ]
    research_pdfs = list(research_pdfs)

    logger.info(
        f"Discovered {len(annual_pdfs)} annual reports, {len(research_pdfs)} research reports"
    )

    def sample_stratified(pdf_list: list[Path], n: int) -> list[Path]:
        if len(pdf_list) <= n:
            return pdf_list

        sized = [(p, p.stat().st_size) for p in pdf_list]
        sized.sort(key=lambda x: x[1])

        third = len(sized) // 3
        small = sized[:third]
        medium = sized[third : 2 * third]
        large = sized[2 * third :]

        sampled = []
        remainder = n % 3

        for bucket in [small, medium, large]:
            remainder = max(0, remainder - 1)
            if bucket:
                sampled.append(random.choice(bucket)[0])

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

    page_counts: dict[str, int] = {}
    for pdf in sampled:
        try:
            doc = fitz.open(str(pdf))
            pages = len(doc)
            doc.close()

            if max_pages_per_pdf and pages > max_pages_per_pdf:
                logger.info(
                    f"Skipping {pdf.name} ({pages} pages, exceeds limit {max_pages_per_pdf})"
                )
                continue

            page_counts[str(pdf)] = pages
            logger.info(
                f"  {pdf.name}: {pages} pages, {pdf.stat().st_size / 1024 / 1024:.1f} MB"
            )
        except Exception as e:
            logger.warning(f"Failed to read {pdf.name}: {e}")

    sampled = [p for p in sampled if str(p) in page_counts]
    total_pages = sum(page_counts.values())

    logger.info(f"\nSampled {len(sampled)} PDFs, {total_pages} total pages")
    return sampled, page_counts


def discover_and_sample_pdfs_meal(
    raw_dir: str,
    sample_mode: str = "pages",
    sample_value: int | float = 1000,
    seed: int = 42,
    max_pages_per_pdf: int | None = None,
) -> tuple[list[Path], dict[str, int]]:
    """Discover and sample real PDFs using Meal-compatible sampling logic.

    Reproduces the same sampling as MealManager.create_meal() with the same
    seed and parameters, allowing benchmark results to be directly correlated
    with experiment results.

    Args:
        raw_dir: Path to the raw PDF directory.
        sample_mode: Sampling mode - "count", "pages", or "ratio".
        sample_value: Sampling threshold value.
        seed: Random seed for reproducibility.
        max_pages_per_pdf: Optional limit on pages per PDF (skip larger ones).

    Returns:
        Tuple of (list of sampled PDF paths, dict of page counts per PDF).

    Raises:
        FileNotFoundError: If raw_dir does not exist.
        ValueError: If sample_mode is invalid.
    """
    random.seed(seed)

    all_pdfs = _discover_all_pdfs(raw_dir)
    if not all_pdfs:
        return [], {}

    if sample_mode == "count":
        count = min(int(sample_value), len(all_pdfs))
        sampled = random.sample(all_pdfs, count)
        logger.info(f"Sampled {len(sampled)} PDFs by count (requested {sample_value})")

    elif sample_mode == "pages":
        pdf_page_counts: list[tuple[Path, int]] = []
        for pdf_file in all_pdfs:
            pages = _count_pdf_pages(pdf_file)
            if pages > 0:
                if max_pages_per_pdf and pages > max_pages_per_pdf:
                    logger.info(
                        f"Skipping {pdf_file.name} ({pages} pages, exceeds limit {max_pages_per_pdf})"
                    )
                    continue
                pdf_page_counts.append((pdf_file, pages))

        if not pdf_page_counts:
            logger.warning("No PDFs could be read for page-based sampling")
            return [], {}

        random.shuffle(pdf_page_counts)

        sampled_list: list[Path] = []
        accumulated_pages = 0
        for pdf_file, pages in pdf_page_counts:
            sampled_list.append(pdf_file)
            accumulated_pages += pages
            if accumulated_pages >= sample_value:
                break

        sampled = sampled_list
        logger.info(
            f"Sampled {len(sampled)} PDFs by pages "
            f"(target {sample_value}, actual {accumulated_pages} pages)"
        )

    elif sample_mode == "ratio":
        count = math.ceil(float(sample_value) * len(all_pdfs))
        count = max(1, min(count, len(all_pdfs)))
        sampled = random.sample(all_pdfs, count)
        logger.info(
            f"Sampled {len(sampled)} PDFs by ratio "
            f"(ratio {sample_value}, {len(all_pdfs)} total)"
        )

    else:
        raise ValueError(
            f"Invalid sample_mode '{sample_mode}', must be 'count', 'pages', or 'ratio'"
        )

    page_counts: dict[str, int] = {}
    for pdf in sampled:
        pages = _count_pdf_pages(pdf)
        if pages > 0:
            page_counts[str(pdf)] = pages
            logger.info(
                f"  {pdf.name}: {pages} pages, {pdf.stat().st_size / 1024 / 1024:.1f} MB"
            )

    sampled = [p for p in sampled if str(p) in page_counts]
    total_pages = sum(page_counts.values())
    logger.info(
        f"\nSampled {len(sampled)} PDFs, {total_pages} total pages (seed={seed})"
    )
    return sampled, page_counts


def benchmark_parse_real_pdfs(
    pdfs: list[Path],
    page_counts: dict[str, int],
    warmup: bool = False,
    monitor: ResourceMonitor | None = None,
) -> tuple[list[float], list[float], list[PerDocResult]]:
    """Benchmark parsing on real PDFs with resource monitoring.

    Args:
        pdfs: List of PDF paths to benchmark.
        page_counts: Dict mapping PDF path strings to page counts.
        warmup: If True, don't log detailed results.
        monitor: Optional ResourceMonitor for tracking CPU/memory.

    Returns:
        Tuple of (times_no_ocr, times_with_ocr, per_doc_results).
    """
    options_base = {k: v for k, v in PYMUPDF4LLM_OPTIONS.items()}

    times_no_ocr: list[float] = []
    times_with_ocr: list[float] = []
    per_doc_results: list[PerDocResult] = []

    for idx, pdf in enumerate(pdfs):
        pages = page_counts.get(str(pdf), 0)
        file_size_mb = pdf.stat().st_size / 1024 / 1024

        start = time.perf_counter()
        pymupdf4llm.to_markdown(str(pdf), use_ocr=False, **options_base)
        t_no = time.perf_counter() - start
        times_no_ocr.append(t_no)

        start = time.perf_counter()
        pymupdf4llm.to_markdown(str(pdf), use_ocr=True, **options_base)
        t_with = time.perf_counter() - start
        times_with_ocr.append(t_with)

        doc_result = PerDocResult(
            filename=pdf.name,
            pages=pages,
            file_size_mb=file_size_mb,
            time_no_ocr=t_no,
            time_with_ocr=t_with,
        )
        per_doc_results.append(doc_result)

        if not warmup:
            logger.info(
                f"  [{idx + 1}/{len(pdfs)}] {pdf.name} ({pages}p): "
                f"NoOCR={t_no:.2f}s ({doc_result.pages_per_sec_no_ocr:.1f}p/s) | "
                f"WithOCR={t_with:.2f}s ({doc_result.pages_per_sec_with_ocr:.1f}p/s) "
                f"[{doc_result.slowdown_pct:+.1f}%]"
            )

    return times_no_ocr, times_with_ocr, per_doc_results


def _build_results_dict(
    per_doc_results: list[PerDocResult],
    page_counts: dict[str, int],
    resource_stats: dict[str, float],
    sampling_info: dict[str, Any],
) -> dict[str, Any]:
    """Build the full results dictionary from benchmark data.

    Args:
        per_doc_results: Per-document benchmark results.
        page_counts: Dict mapping PDF path strings to page counts.
        resource_stats: Resource monitoring statistics.
        sampling_info: Information about the sampling method used.

    Returns:
        Complete results dictionary.
    """
    total_pages = sum(page_counts.values())
    total_pdfs = len(per_doc_results)

    times_no_ocr = [r.time_no_ocr for r in per_doc_results]
    times_with_ocr = [r.time_with_ocr for r in per_doc_results]

    total_no_ocr = sum(times_no_ocr)
    total_with_ocr = sum(times_with_ocr)

    per_page_no_ocr = [
        r.time_no_ocr / r.pages if r.pages > 0 else 0.0 for r in per_doc_results
    ]
    per_page_with_ocr = [
        r.time_with_ocr / r.pages if r.pages > 0 else 0.0 for r in per_doc_results
    ]

    throughput_no_ocr = [r.pages_per_sec_no_ocr for r in per_doc_results]
    throughput_with_ocr = [r.pages_per_sec_with_ocr for r in per_doc_results]

    slowdown_pct = (
        (total_with_ocr / total_no_ocr - 1) * 100 if total_no_ocr > 0 else 0.0
    )

    results: dict[str, Any] = {
        "timestamp": datetime.now().isoformat(),
        "sampling": sampling_info,
        "total_pdfs": total_pdfs,
        "total_pages": total_pages,
        "no_ocr": {
            "total_time": total_no_ocr,
            "avg_per_pdf": total_no_ocr / total_pdfs if total_pdfs > 0 else 0.0,
            "avg_per_page": total_no_ocr / total_pages if total_pages > 0 else 0.0,
            "pages_per_sec": total_pages / total_no_ocr if total_no_ocr > 0 else 0.0,
            "per_pdf_time_stats": compute_stats(times_no_ocr),
            "per_page_time_stats": compute_stats(per_page_no_ocr),
            "throughput_stats": compute_stats(throughput_no_ocr),
        },
        "with_ocr": {
            "total_time": total_with_ocr,
            "avg_per_pdf": total_with_ocr / total_pdfs if total_pdfs > 0 else 0.0,
            "avg_per_page": total_with_ocr / total_pages if total_pages > 0 else 0.0,
            "pages_per_sec": total_pages / total_with_ocr
            if total_with_ocr > 0
            else 0.0,
            "per_pdf_time_stats": compute_stats(times_with_ocr),
            "per_page_time_stats": compute_stats(per_page_with_ocr),
            "throughput_stats": compute_stats(throughput_with_ocr),
        },
        "slowdown_pct": slowdown_pct,
        "resource": resource_stats,
        "per_document": [
            {
                "filename": r.filename,
                "pages": r.pages,
                "file_size_mb": round(r.file_size_mb, 2),
                "time_no_ocr": round(r.time_no_ocr, 3),
                "time_with_ocr": round(r.time_with_ocr, 3),
                "slowdown_pct": round(r.slowdown_pct, 1),
                "pages_per_sec_no_ocr": round(r.pages_per_sec_no_ocr, 1),
                "pages_per_sec_with_ocr": round(r.pages_per_sec_with_ocr, 1),
            }
            for r in per_doc_results
        ],
    }

    return results


def _print_summary(results: dict[str, Any]) -> None:
    """Print a formatted summary of benchmark results.

    Args:
        results: Results dictionary from _build_results_dict.
    """
    no_ocr = results["no_ocr"]
    with_ocr = results["with_ocr"]

    logger.info("\n" + "=" * 90)
    logger.info("BENCHMARK RESULTS")
    logger.info("=" * 90)
    logger.info(
        f"Total PDFs: {results['total_pdfs']}, Total pages: {results['total_pages']}"
    )
    logger.info(f"Sampling: {results['sampling']}")
    logger.info("")

    logger.info(f"{'Metric':<35} {'No OCR':>15} {'With OCR':>15} {'Change':>15}")
    logger.info("-" * 80)
    logger.info(
        f"{'Total time (s)':<35} {no_ocr['total_time']:>15.2f} "
        f"{with_ocr['total_time']:>15.2f} {results['slowdown_pct']:>14.1f}%"
    )
    logger.info(
        f"{'Avg per PDF (s)':<35} {no_ocr['avg_per_pdf']:>15.2f} "
        f"{with_ocr['avg_per_pdf']:>15.2f} "
        f"{((with_ocr['avg_per_pdf'] / no_ocr['avg_per_pdf'] - 1) * 100) if no_ocr['avg_per_pdf'] > 0 else 0:>14.1f}%"
    )
    logger.info(
        f"{'Avg per page (s)':<35} {no_ocr['avg_per_page']:>15.3f} "
        f"{with_ocr['avg_per_page']:>15.3f} "
        f"{((with_ocr['avg_per_page'] / no_ocr['avg_per_page'] - 1) * 100) if no_ocr['avg_per_page'] > 0 else 0:>14.1f}%"
    )
    logger.info(
        f"{'Pages per second':<35} {no_ocr['pages_per_sec']:>15.1f} "
        f"{with_ocr['pages_per_sec']:>15.1f} "
        f"{((with_ocr['pages_per_sec'] / no_ocr['pages_per_sec'] - 1) * 100) if no_ocr['pages_per_sec'] > 0 else 0:>14.1f}%"
    )
    logger.info("")

    for label, key in [
        ("Per-PDF time (s)", "per_pdf_time_stats"),
        ("Per-page time (s)", "per_page_time_stats"),
        ("Throughput (pages/s)", "throughput_stats"),
    ]:
        no_stats = no_ocr[key]
        with_stats = with_ocr[key]
        logger.info(f"  {label}:")
        logger.info(f"    {'':30s} {'No OCR':>12s} {'With OCR':>12s}")
        for stat_name in ["mean", "std", "median", "p95", "min", "max"]:
            logger.info(
                f"    {stat_name:<30s} {no_stats[stat_name]:>12.3f} {with_stats[stat_name]:>12.3f}"
            )
        logger.info("")

    resource = results.get("resource", {})
    if resource.get("memory_peak_mb", 0) > 0:
        logger.info("  Resource usage:")
        logger.info(
            f"    CPU avg: {resource['cpu_avg']:.1f}%, peak: {resource['cpu_peak']:.1f}%"
        )
        logger.info(
            f"    Memory avg: {resource['memory_avg_mb']:.1f} MB, peak: {resource['memory_peak_mb']:.1f} MB"
        )
        logger.info("")

    logger.info("Per-document breakdown:")
    for doc in results["per_document"]:
        logger.info(
            f"  {doc['filename']:<50s} {doc['pages']:>4}p  "
            f"NoOCR={doc['time_no_ocr']:>8.2f}s  WithOCR={doc['time_with_ocr']:>8.2f}s  "
            f"[{doc['slowdown_pct']:+.1f}%]"
        )

    logger.info("=" * 90)

    for target_pages in [500, 1000, 2000, 5000]:
        est_no = target_pages * no_ocr["avg_per_page"]
        est_with = target_pages * with_ocr["avg_per_page"]
        logger.info(
            f"Extrapolated for {target_pages:>5} pages: "
            f"No OCR={est_no:>8.1f}s ({est_no / 60:.1f}min) | "
            f"With OCR={est_with:>8.1f}s ({est_with / 60:.1f}min)"
        )
    logger.info("=" * 90)


def _generate_markdown_report(results: dict[str, Any]) -> str:
    """Generate a Markdown report from benchmark results.

    Args:
        results: Results dictionary from _build_results_dict.

    Returns:
        Markdown formatted report string.
    """
    no_ocr = results["no_ocr"]
    with_ocr = results["with_ocr"]
    resource = results.get("resource", {})

    lines: list[str] = []
    lines.append("# PDF Parsing OCR Benchmark Report")
    lines.append("")
    lines.append(f"**Generated**: {results['timestamp']}")
    lines.append(
        f"**Total PDFs**: {results['total_pdfs']}, **Total pages**: {results['total_pages']}"
    )
    lines.append(f"**OCR Slowdown**: {results['slowdown_pct']:+.1f}%")
    lines.append("")

    lines.append("## Sampling Configuration")
    lines.append("")
    sampling = results["sampling"]
    lines.append(f"- Mode: `{sampling.get('mode', 'unknown')}`")
    if sampling.get("mode") == "meal":
        lines.append(f"- Sample mode: `{sampling.get('sample_mode', 'N/A')}`")
        lines.append(f"- Sample value: `{sampling.get('sample_value', 'N/A')}`")
        lines.append(f"- Seed: `{sampling.get('seed', 'N/A')}`")
    else:
        lines.append(f"- Annual reports: `{sampling.get('num_annual', 'N/A')}`")
        lines.append(f"- Research reports: `{sampling.get('num_research', 'N/A')}`")
    lines.append("")

    lines.append("## Summary")
    lines.append("")
    lines.append("| Metric | No OCR | With OCR | Change |")
    lines.append("|--------|--------|----------|--------|")
    lines.append(
        f"| Total time (s) | {no_ocr['total_time']:.2f} | {with_ocr['total_time']:.2f} | {results['slowdown_pct']:+.1f}% |"
    )
    lines.append(
        f"| Avg per PDF (s) | {no_ocr['avg_per_pdf']:.2f} | {with_ocr['avg_per_pdf']:.2f} | "
        f"{((with_ocr['avg_per_pdf'] / no_ocr['avg_per_pdf'] - 1) * 100) if no_ocr['avg_per_pdf'] > 0 else 0:+.1f}% |"
    )
    lines.append(
        f"| Avg per page (s) | {no_ocr['avg_per_page']:.3f} | {with_ocr['avg_per_page']:.3f} | "
        f"{((with_ocr['avg_per_page'] / no_ocr['avg_per_page'] - 1) * 100) if no_ocr['avg_per_page'] > 0 else 0:+.1f}% |"
    )
    lines.append(
        f"| Pages per second | {no_ocr['pages_per_sec']:.1f} | {with_ocr['pages_per_sec']:.1f} | "
        f"{((with_ocr['pages_per_sec'] / no_ocr['pages_per_sec'] - 1) * 100) if no_ocr['pages_per_sec'] > 0 else 0:+.1f}% |"
    )
    lines.append("")

    lines.append("## Statistical Details")
    lines.append("")
    for label, key in [
        ("Per-PDF time (s)", "per_pdf_time_stats"),
        ("Per-page time (s)", "per_page_time_stats"),
        ("Throughput (pages/s)", "throughput_stats"),
    ]:
        no_stats = no_ocr[key]
        with_stats = with_ocr[key]
        lines.append(f"### {label}")
        lines.append("")
        lines.append("| Statistic | No OCR | With OCR |")
        lines.append("|-----------|--------|----------|")
        for stat_name in ["mean", "std", "median", "p95", "min", "max"]:
            lines.append(
                f"| {stat_name} | {no_stats[stat_name]:.3f} | {with_stats[stat_name]:.3f} |"
            )
        lines.append("")

    if resource.get("memory_peak_mb", 0) > 0:
        lines.append("## Resource Usage")
        lines.append("")
        lines.append("| Metric | Value |")
        lines.append("|--------|-------|")
        lines.append(f"| CPU avg | {resource['cpu_avg']:.1f}% |")
        lines.append(f"| CPU peak | {resource['cpu_peak']:.1f}% |")
        lines.append(f"| Memory avg | {resource['memory_avg_mb']:.1f} MB |")
        lines.append(f"| Memory peak | {resource['memory_peak_mb']:.1f} MB |")
        lines.append("")

    lines.append("## Per-Document Breakdown")
    lines.append("")
    lines.append("| File | Pages | Size (MB) | No OCR (s) | With OCR (s) | Slowdown |")
    lines.append("|------|-------|-----------|------------|--------------|----------|")
    for doc in results["per_document"]:
        lines.append(
            f"| {doc['filename']} | {doc['pages']} | {doc['file_size_mb']:.1f} | "
            f"{doc['time_no_ocr']:.2f} | {doc['time_with_ocr']:.2f} | {doc['slowdown_pct']:+.1f}% |"
        )
    lines.append("")

    lines.append("## Extrapolation")
    lines.append("")
    lines.append("| Target Pages | No OCR | With OCR |")
    lines.append("|-------------|--------|----------|")
    for target_pages in [500, 1000, 2000, 5000]:
        est_no = target_pages * no_ocr["avg_per_page"]
        est_with = target_pages * with_ocr["avg_per_page"]
        lines.append(
            f"| {target_pages} | {est_no:.1f}s ({est_no / 60:.1f}min) | {est_with:.1f}s ({est_with / 60:.1f}min) |"
        )
    lines.append("")

    return "\n".join(lines)


def _save_results(results: dict[str, Any], output_dir: str | Path) -> Path:
    """Save benchmark results to JSON and Markdown files.

    Args:
        results: Results dictionary from _build_results_dict.
        output_dir: Directory to save output files.

    Returns:
        Path to the output directory.
    """
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    timestamp_short = (
        results["timestamp"].replace(":", "").replace("-", "").replace(".", "")[:15]
    )

    json_path = out / f"benchmark_{timestamp_short}.json"
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2, ensure_ascii=False)
    logger.info(f"Results saved to {json_path}")

    md_path = out / f"benchmark_{timestamp_short}.md"
    md_content = _generate_markdown_report(results)
    with open(md_path, "w", encoding="utf-8") as f:
        f.write(md_content)
    logger.info(f"Markdown report saved to {md_path}")

    return out


def run_real_benchmark(
    raw_dir: str = "data/raw",
    num_annual: int = 3,
    num_research: int = 2,
    max_pages_per_pdf: int | None = None,
    warmup_runs: int = 1,
    sample_mode: str = "pages",
    sample_value: int | float = 1000,
    seed: int = 42,
    output_dir: str | None = None,
) -> dict:
    """Run benchmark on real PDFs from the data directory.

    Args:
        raw_dir: Path to the raw PDF directory.
        num_annual: Number of annual reports to sample (stratified mode).
        num_research: Number of research reports to sample (stratified mode).
        max_pages_per_pdf: Optional limit on pages per PDF.
        warmup_runs: Number of warmup runs.
        sample_mode: Meal sampling mode - "count", "pages", or "ratio".
        sample_value: Meal sampling threshold value.
        seed: Random seed for Meal sampling reproducibility.
        output_dir: Optional directory to save results.

    Returns:
        Results dict with timing and resource statistics.
    """
    logger.info("=" * 70)
    logger.info("Real PDF Benchmark: use_ocr Performance Impact")
    logger.info(f"Sampling mode: {SAMPLING_MODE}")
    logger.info("=" * 70)

    logger.info(f"\n[Step 1] Sampling from {raw_dir}...")
    if SAMPLING_MODE == "meal":
        pdfs, page_counts = discover_and_sample_pdfs_meal(
            raw_dir,
            sample_mode=sample_mode,
            sample_value=sample_value,
            seed=seed,
            max_pages_per_pdf=max_pages_per_pdf,
        )
        sampling_info: dict[str, Any] = {
            "mode": "meal",
            "sample_mode": sample_mode,
            "sample_value": sample_value,
            "seed": seed,
        }
    else:
        pdfs, page_counts = discover_and_sample_pdfs(
            raw_dir, num_annual, num_research, max_pages_per_pdf
        )
        sampling_info = {
            "mode": "stratified",
            "num_annual": num_annual,
            "num_research": num_research,
        }

    total_pages = sum(page_counts.values())

    if not pdfs:
        logger.error("No PDFs found to benchmark")
        return {}

    if warmup_runs > 0:
        logger.info(f"\n[Step 2] Running {warmup_runs} warmup pass(es)...")
        benchmark_parse_real_pdfs(
            [pdfs[0]],
            {str(pdfs[0]): page_counts.get(str(pdfs[0]), 0)},
            warmup=True,
        )
        logger.info("  Warmup complete.")

    logger.info(
        f"\n[Step 3] Benchmarking {len(pdfs)} real PDFs ({total_pages} total pages)..."
    )
    monitor = ResourceMonitor(enabled=True)
    monitor.start()

    _, _, per_doc_results = benchmark_parse_real_pdfs(pdfs, page_counts)

    resource_stats = monitor.stop()

    results = _build_results_dict(
        per_doc_results, page_counts, resource_stats, sampling_info
    )

    _print_summary(results)

    if output_dir:
        _save_results(results, output_dir)

    return results


def run_benchmark(
    test_dir: str = "data/benchmarks/test_pdfs",
    num_pages: int = 100,
    num_pdfs: int = 5,
    warmup_runs: int = 1,
    output_dir: str | None = None,
) -> dict:
    """Run the full synthetic benchmark and print results.

    Args:
        test_dir: Directory for test PDFs.
        num_pages: Pages per test PDF.
        num_pdfs: Number of test PDFs.
        warmup_runs: Number of warmup runs (excluded from timing).
        output_dir: Optional directory to save results.

    Returns:
        Results dict with timing statistics.
    """
    logger.info("=" * 70)
    logger.info("PDF Parsing Benchmark: use_ocr Performance Impact (Synthetic)")
    logger.info("=" * 70)

    logger.info(
        f"\n[Step 1] Generating {num_pdfs} test PDFs ({num_pages} pages each)..."
    )
    gen_start = time.perf_counter()
    pdfs = generate_test_pdfs(test_dir, num_pages, num_pdfs)
    gen_elapsed = time.perf_counter() - gen_start
    total_pages = num_pages * num_pdfs
    logger.info(
        f"Generated {len(pdfs)} PDFs, {total_pages} total pages in {gen_elapsed:.2f}s"
    )

    if warmup_runs > 0:
        logger.info(f"\n[Step 2] Running {warmup_runs} warmup pass(es)...")
        for i in range(warmup_runs):
            logger.info(f"  Warmup {i + 1}/{warmup_runs}: parsing first PDF...")
            benchmark_parse(pdfs[0], use_ocr=False, warmup=True)
        logger.info("  Warmup complete.")

    logger.info("\n[Step 3] Benchmarking WITHOUT OCR (use_ocr=False)...")
    times_no_ocr: list[float] = []
    for idx, pdf in enumerate(pdfs):
        t = benchmark_parse(pdf, use_ocr=False)
        times_no_ocr.append(t)
        logger.info(
            f"  [{idx + 1}/{len(pdfs)}] {pdf.name} ({num_pages} pages): {t:.2f}s ({num_pages / t:.1f} pages/s)"
        )

    logger.info("\n[Step 4] Benchmarking WITH OCR (use_ocr=True)...")
    times_with_ocr: list[float] = []
    for idx, pdf in enumerate(pdfs):
        t = benchmark_parse(pdf, use_ocr=True)
        times_with_ocr.append(t)
        logger.info(
            f"  [{idx + 1}/{len(pdfs)}] {pdf.name} ({num_pages} pages): {t:.2f}s ({num_pages / t:.1f} pages/s)"
        )

    page_counts = {str(pdf): num_pages for pdf in pdfs}
    per_doc_results = [
        PerDocResult(
            filename=pdf.name,
            pages=num_pages,
            file_size_mb=pdf.stat().st_size / 1024 / 1024,
            time_no_ocr=times_no_ocr[i],
            time_with_ocr=times_with_ocr[i],
        )
        for i, pdf in enumerate(pdfs)
    ]

    sampling_info: dict[str, Any] = {
        "mode": "synthetic",
        "num_pdfs": num_pdfs,
        "num_pages": num_pages,
    }
    results = _build_results_dict(per_doc_results, page_counts, {}, sampling_info)

    _print_summary(results)

    if output_dir:
        _save_results(results, output_dir)

    return results


if __name__ == "__main__":
    import argparse

    logger.add(sys.stderr, level="INFO")

    parser = argparse.ArgumentParser(description="Benchmark use_ocr performance impact")
    parser.add_argument(
        "--mode",
        choices=["synthetic", "real", "both"],
        default="real",
        help="Benchmark mode",
    )
    parser.add_argument(
        "--num-pdfs",
        type=int,
        default=5,
        help="Number of synthetic test PDFs to generate",
    )
    parser.add_argument(
        "--num-pages", type=int, default=100, help="Pages per synthetic PDF"
    )
    parser.add_argument(
        "--test-dir",
        type=str,
        default="data/benchmarks/test_pdfs",
        help="Synthetic test PDF directory",
    )
    parser.add_argument("--warmup", type=int, default=1, help="Number of warmup runs")
    parser.add_argument(
        "--raw-dir", type=str, default="data/raw", help="Real PDF raw directory"
    )
    parser.add_argument(
        "--num-annual",
        type=int,
        default=3,
        help="Number of annual reports to sample (stratified mode)",
    )
    parser.add_argument(
        "--num-research",
        type=int,
        default=2,
        help="Number of research reports to sample (stratified mode)",
    )
    parser.add_argument(
        "--max-pages",
        type=int,
        default=None,
        help="Max pages per PDF (skip larger ones)",
    )
    parser.add_argument(
        "--sample-mode",
        choices=["count", "pages", "ratio"],
        default="pages",
        help="Meal sampling mode",
    )
    parser.add_argument(
        "--sample-value", type=float, default=1000, help="Meal sampling threshold value"
    )
    parser.add_argument(
        "--seed",
        type=int,
        default=42,
        help="Random seed for Meal sampling reproducibility",
    )
    parser.add_argument(
        "--output",
        type=str,
        default="data/benchmarks/results",
        help="Output directory for results",
    )
    args = parser.parse_args()

    all_results: dict[str, Any] = {}

    if args.mode in ["synthetic", "both"]:
        logger.info("\n" + "=" * 70)
        logger.info("MODE: Synthetic PDF Benchmark")
        logger.info("=" * 70)
        results = run_benchmark(
            test_dir=args.test_dir,
            num_pages=args.num_pages,
            num_pdfs=args.num_pdfs,
            warmup_runs=args.warmup,
            output_dir=args.output,
        )
        all_results["synthetic"] = results

    if args.mode in ["real", "both"]:
        logger.info("\n" + "=" * 70)
        logger.info("MODE: Real PDF Benchmark")
        logger.info(f"Sampling strategy: {SAMPLING_MODE}")
        logger.info("=" * 70)

        real_results = run_real_benchmark(
            raw_dir=args.raw_dir,
            num_annual=args.num_annual,
            num_research=args.num_research,
            max_pages_per_pdf=args.max_pages,
            warmup_runs=args.warmup,
            sample_mode=args.sample_mode,
            sample_value=args.sample_value,
            seed=args.seed,
            output_dir=args.output,
        )
        all_results["real"] = real_results

    if args.mode == "both":
        logger.info("\n" + "=" * 70)
        logger.info("CROSS-MODE COMPARISON")
        logger.info("=" * 70)
        for mode_name, res in all_results.items():
            if res:
                logger.info(
                    f"{mode_name:10s}: slowdown={res['slowdown_pct']:+.1f}%, "
                    f"no_ocr={res['no_ocr']['avg_per_page']:.3f}s/page, "
                    f"with_ocr={res['with_ocr']['avg_per_page']:.3f}s/page"
                )
        logger.info("=" * 70)
