from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger


class ComparisonReporter:
    """Generate comparison reports for multiple experiment results."""

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
        if self._results:
            sections.append(
                "基于以上对比，推荐选择指标表现更优的方案。具体选择需结合业务场景判断。"
            )

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
        reports_dir.mkdir(parents=True, exist_ok=True)

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"comparison_{session_id}_{timestamp}.md"
        filepath = reports_dir / filename

        filepath.write_text(report, encoding="utf-8")
        logger.info(f"Comparison report saved to {filepath}")
        return filepath
