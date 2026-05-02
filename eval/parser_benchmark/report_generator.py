from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from loguru import logger

if TYPE_CHECKING:
    from eval.parser_benchmark.metrics import DocumentMetrics


class ReportGenerator:
    """Generates comparison reports from benchmark results."""

    def __init__(self, run_dir: Path):
        """Initialize with the benchmark run directory.

        Args:
            run_dir: Directory where benchmark results are stored.
        """
        self._run_dir = run_dir

    def generate(self, all_results: dict[str, list[DocumentMetrics]]) -> Path:
        """Generate JSON and Markdown comparison reports.

        Args:
            all_results: Dict mapping pipeline names to their
                DocumentMetrics lists.

        Returns:
            Path to the generated Markdown report.
        """
        self._generate_comparison_json(all_results)
        report_path = self._generate_markdown_report(all_results)
        logger.info(f"Report generated: {report_path}")
        return report_path

    def _generate_comparison_json(self, all_results: dict[str, list]) -> None:
        """Generate a JSON comparison file.

        Args:
            all_results: Dict mapping pipeline names to metrics lists.
        """
        comparison = {}
        for pipeline_name, metrics_list in all_results.items():
            if not metrics_list:
                continue
            total_tables = sum(m.total_tables for m in metrics_list)
            total_chars = sum(m.total_chars for m in metrics_list)
            total_words = sum(m.total_words for m in metrics_list)
            total_headings = sum(m.total_headings for m in metrics_list)
            avg_parse_time = (
                sum(m.parse_time_seconds for m in metrics_list) / len(metrics_list)
                if metrics_list
                else 0
            )
            avg_empty_ratio = (
                sum(m.avg_table_empty_ratio for m in metrics_list) / len(metrics_list)
                if metrics_list
                else 0
            )
            avg_valid_ratio = (
                sum(m.markdown_valid_ratio for m in metrics_list) / len(metrics_list)
                if metrics_list
                else 0
            )

            comparison[pipeline_name] = {
                "pdfs_tested": len(metrics_list),
                "total_tables": total_tables,
                "total_chars": total_chars,
                "total_words": total_words,
                "total_headings": total_headings,
                "avg_parse_time_seconds": round(avg_parse_time, 3),
                "avg_table_empty_ratio": round(avg_empty_ratio, 3),
                "avg_markdown_valid_ratio": round(avg_valid_ratio, 3),
            }

        comparison_path = self._run_dir / "results" / "comparison.json"
        comparison_path.parent.mkdir(parents=True, exist_ok=True)
        with open(comparison_path, "w", encoding="utf-8") as f:
            json.dump(comparison, f, ensure_ascii=False, indent=2)

    def _generate_markdown_report(self, all_results: dict[str, list]) -> Path:
        """Generate a Markdown comparison report.

        Args:
            all_results: Dict mapping pipeline names to metrics lists.

        Returns:
            Path to the generated report file.
        """
        lines = []
        lines.append(f"# Parser Benchmark Report: {self._run_dir.name}")
        lines.append("")
        lines.append("## Summary")
        lines.append("")

        header = "| Pipeline | PDFs | Tables | Chars | Words | Headings | Avg Parse Time | Avg Empty Ratio | Valid Ratio |"
        separator = "|----------|------|--------|-------|-------|----------|---------------|----------------|-------------|"
        lines.append(header)
        lines.append(separator)

        for pipeline_name, metrics_list in all_results.items():
            if not metrics_list:
                continue
            total_tables = sum(m.total_tables for m in metrics_list)
            total_chars = sum(m.total_chars for m in metrics_list)
            total_words = sum(m.total_words for m in metrics_list)
            total_headings = sum(m.total_headings for m in metrics_list)
            avg_parse_time = sum(m.parse_time_seconds for m in metrics_list) / len(
                metrics_list
            )
            avg_empty = sum(m.avg_table_empty_ratio for m in metrics_list) / len(
                metrics_list
            )
            avg_valid = sum(m.markdown_valid_ratio for m in metrics_list) / len(
                metrics_list
            )

            lines.append(
                f"| {pipeline_name} | {len(metrics_list)} | {total_tables} | "
                f"{total_chars} | {total_words} | {total_headings} | "
                f"{avg_parse_time:.2f}s | {avg_empty:.3f} | {avg_valid:.3f} |"
            )

        lines.append("")
        lines.append("## Per-PDF Details")
        lines.append("")

        for pipeline_name, metrics_list in all_results.items():
            lines.append(f"### {pipeline_name}")
            lines.append("")
            for m in metrics_list:
                pdf_name = Path(m.pdf_path).stem
                lines.append(f"**{pdf_name}** ({m.parse_time_seconds:.2f}s)")
                lines.append(
                    f"- Pages: {m.page_count}, Tables: {m.total_tables}, Headings: {m.total_headings}"
                )
                lines.append(f"- Chars: {m.total_chars}, Words: {m.total_words}")
                if m.total_tables > 0:
                    lines.append(
                        f"- Avg table rows: {m.avg_table_rows:.1f}, cols: {m.avg_table_cols:.1f}, empty: {m.avg_table_empty_ratio:.3f}"
                    )
                lines.append("")

        report_path = self._run_dir / "report.md"
        with open(report_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))

        return report_path
