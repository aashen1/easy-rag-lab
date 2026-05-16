from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from src.agent.reporters.base import BaseReporter


class MaintenanceReporter(BaseReporter):
    """Generate maintenance session reports in Markdown format."""

    def generate(self, state: dict[str, Any], session_id: str) -> str:
        """Generate a Markdown maintenance report from agent state.

        Args:
            state: The MaintenanceState dict from the agent graph.
            session_id: Identifier for the session.

        Returns:
            Markdown-formatted report string.
        """
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        current_source = state.get("current_source", "未设置")
        current_meal = state.get("current_meal", "未设置")

        sections = []
        sections.append(f"# 维修报告 — {session_id}")

        sections.append("## 元数据")
        sections.append(f"- 时间：{timestamp}")
        sections.append(f"- 目标 PDF：{current_source}")
        sections.append(f"- 目标 Meal：{current_meal}")

        sections.append("## 操作时间线")
        exec_log = state.get("execution_log", [])
        if exec_log:
            sections.append("| # | 时间 | 工具 | 状态 |")
            sections.append("|---|------|------|------|")
            for i, entry in enumerate(exec_log):
                try:
                    data = json.loads(entry)
                    time_str = data.get("time", "")[11:19]
                    tool = data.get("tool", "")
                    status = data.get("status", "")
                    sections.append(f"| {i + 1} | {time_str} | {tool} | {status} |")
                except (json.JSONDecodeError, TypeError):
                    sections.append(f"| {i + 1} | - | {entry} | - |")
        else:
            sections.append("无操作记录")

        sections.append("## 诊断记录")
        diagnosis = state.get("diagnosis", [])
        if diagnosis:
            for d in diagnosis:
                sections.append(f"- {d}")
        else:
            sections.append("无诊断记录")

        sections.append("## 关键发现")
        messages = state.get("messages", [])
        findings = []
        for msg in messages:
            content = getattr(msg, "content", "")
            if content and len(content) > 50:
                findings.append(
                    content[:300] + "..." if len(content) > 300 else content
                )
        if findings:
            for i, f in enumerate(findings[-5:]):
                sections.append(f"{i + 1}. {f}")
        else:
            sections.append("无关键发现")

        sections.append("## 阶段历史")
        stage_history = state.get("stage_history", [])
        if stage_history:
            for i, step in enumerate(stage_history):
                sections.append(f"{i + 1}. {step}")
        else:
            sections.append("无阶段记录")

        sections.append("## 最终配置推荐")
        config_recommendations = state.get("config_recommendations", [])
        if config_recommendations:
            for rec in config_recommendations:
                if isinstance(rec, dict):
                    sections.append(
                        f"- **{rec.get('item', '未知')}**: "
                        f"{rec.get('value', 'N/A')} "
                        f"({rec.get('reason', '无说明')})"
                    )
                else:
                    sections.append(f"- {rec}")
        else:
            sections.append("无配置推荐")

        sections.append("## 经验记录")
        experiences = state.get("experiences", [])
        if experiences:
            for exp in experiences:
                if isinstance(exp, dict):
                    sections.append(
                        f"- **{exp.get('pdf_type', '未知类型')}**: "
                        f"推荐解析器={exp.get('best_parser', 'N/A')}, "
                        f"分块策略={exp.get('best_chunk_strategy', 'N/A')}, "
                        f"分块大小={exp.get('best_chunk_size', 'N/A')} "
                        f"({exp.get('reason', '无说明')})"
                    )
                else:
                    sections.append(f"- {exp}")
        else:
            sections.append("无经验记录")

        return "\n\n".join(sections)

    def save(
        self, report: str, session_id: str, reports_dir: str | Path | None = None
    ) -> Path:
        return self._save_report(report, session_id, "maintenance", reports_dir)
