from __future__ import annotations

import contextlib
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class ComparisonReporter:
    """Generate comparison reports for multiple experiment results."""

    LOWER_IS_BETTER_KEYS = {
        "error_rate",
        "latency_ms",
        "avg_latency",
        "p95_latency",
        "chunk_overlap",
        "hallucination_rate",
    }

    def __init__(self) -> None:
        self._results: list[dict[str, Any]] = []

    def add_result(self, label: str, metrics: dict[str, Any]) -> None:
        """Add a result set for comparison.

        Args:
            label: Label for this result (e.g., "方案 A").
            metrics: Dict of metric name to value.
        """
        self._results.append({"label": label, "metrics": metrics})

    def generate(self) -> str:
        """Generate a Markdown comparison report.

        Returns:
            Markdown-formatted comparison report string.
        """
        if len(self._results) < 2:
            return "# 对比报告\n\n需要至少两组结果才能生成对比报告"

        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        sections = []
        sections.append(f"# 对比报告 — {timestamp}")

        sections.append("## 对比维度")
        all_keys: set[str] = set()
        for r in self._results:
            all_keys.update(r["metrics"].keys())
        sections.append(", ".join(sorted(all_keys)))

        sections.append("## 指标对比")
        header = "| 指标 |"
        separator = "|------|"
        for r in self._results:
            header += f" {r['label']} |"
            separator += "--------|"
        header += " 差异 |"
        separator += "------|"

        sections.append(header)
        sections.append(separator)

        for key in sorted(all_keys):
            row = f"| {key} |"
            values = []
            for r in self._results:
                val = r["metrics"].get(key, "N/A")
                row += f" {val} |"
                values.append(val)
            if len(values) >= 2:
                try:
                    diff = float(values[0]) - float(values[1])
                    row += f" {diff:+.2f} |"
                except (ValueError, TypeError):
                    row += " - |"
            else:
                row += " - |"
            sections.append(row)

        sections.append("## 差异摘要")
        for key in sorted(all_keys):
            vals = []
            for r in self._results:
                v = r["metrics"].get(key)
                if v is not None:
                    vals.append(v)
            if len(vals) >= 2:
                try:
                    diff = abs(float(vals[0]) - float(vals[1]))
                    if diff > 0:
                        sections.append(
                            f"- **{key}**: {self._results[0]['label']}={vals[0]}, "
                            f"{self._results[1]['label']}={vals[1]}, "
                            f"差异={diff:.2f}"
                        )
                except (ValueError, TypeError):
                    pass

        sections.append("## 推荐方案")
        if len(self._results) >= 2:
            win_counts: dict[str, int] = {r["label"]: 0 for r in self._results}
            win_details: dict[str, list[str]] = {r["label"]: [] for r in self._results}
            for key in sorted(all_keys):
                numeric_vals: list[tuple[str, float]] = []
                for r in self._results:
                    v = r["metrics"].get(key)
                    if v is not None:
                        with contextlib.suppress(ValueError, TypeError):
                            numeric_vals.append((r["label"], float(v)))
                if len(numeric_vals) >= 2:
                    if key in self.LOWER_IS_BETTER_KEYS:
                        best = min(numeric_vals, key=lambda x: x[1])
                    else:
                        best = max(numeric_vals, key=lambda x: x[1])
                    win_counts[best[0]] += 1
                    win_details[best[0]].append(f"{key}={best[1]}")
            recommended = max(win_counts, key=lambda k: win_counts[k])
            if win_counts[recommended] > 0:
                sections.append(f"**推荐：{recommended}**")
                sections.append(
                    f"在 {win_counts[recommended]} 项数值指标上表现最优："
                    f"{', '.join(win_details[recommended])}"
                )
            else:
                sections.append("无数值型指标可比较，推荐需结合业务场景判断。")
            for r in self._results:
                if r["label"] != recommended and win_counts[r["label"]] > 0:
                    sections.append(
                        f"- {r['label']} 在 {win_counts[r['label']]} 项指标上更优："
                        f"{', '.join(win_details[r['label']])}"
                    )
        else:
            sections.append("需要至少两组结果才能推荐方案。")

        return "\n\n".join(sections)

    def save(self, report: str, session_id: str) -> Path:
        """Save the comparison report to data/maintenance_reports/.

        Args:
            report: Markdown report content.
            session_id: Session identifier for filename.

        Returns:
            Path to the saved report file.
        """
        reports_dir = Path("data/maintenance_reports")
        try:
            reports_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            logger.error(f"Failed to create reports directory {reports_dir}: {e}")
            raise

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"comparison_{session_id}_{timestamp}.md"
        filepath = reports_dir / filename

        try:
            filepath.write_text(report, encoding="utf-8")
        except OSError as e:
            logger.error(f"Failed to write comparison report to {filepath}: {e}")
            raise
        logger.info(f"Comparison report saved to {filepath}")
        return filepath
