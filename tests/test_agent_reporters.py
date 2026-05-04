from __future__ import annotations

import json

import pytest

pytestmark = pytest.mark.agent


class TestMaintenanceReporter:
    def test_generate_report(self):
        from src.agent.reporters.maintenance_report import MaintenanceReporter

        reporter = MaintenanceReporter()
        state = {
            "current_source": "test.pdf",
            "current_meal": "meal_2024",
            "execution_log": ["TOOL: parse_pdf_tool", "TOOL: chunk_parsed_tool"],
            "stage_history": ["parse_pdf_tool", "chunk_parsed_tool"],
            "diagnosis": [{"issue": "chunk size too large"}],
            "messages": [],
        }
        report = reporter.generate(state, "test-session")
        assert "# 维修报告" in report
        assert "test-session" in report
        assert "test.pdf" in report
        assert "meal_2024" in report
        assert "parse_pdf_tool" in report
        assert "chunk size too large" in report

    def test_generate_report_empty_state(self):
        from src.agent.reporters.maintenance_report import MaintenanceReporter

        reporter = MaintenanceReporter()
        state = {
            "current_source": None,
            "current_meal": None,
            "execution_log": [],
            "stage_history": [],
            "diagnosis": [],
            "messages": [],
        }
        report = reporter.generate(state, "empty-session")
        assert "# 维修报告" in report
        assert "无操作记录" in report

    def test_save_report(self, tmp_path, monkeypatch):
        from src.agent.reporters.maintenance_report import MaintenanceReporter

        monkeypatch.chdir(tmp_path)
        reporter = MaintenanceReporter()
        report = "# Test Report"
        filepath = reporter.save(report, "test-session")
        assert filepath.exists()
        assert filepath.read_text(encoding="utf-8") == report

    def test_save_creates_directory(self, tmp_path, monkeypatch):
        from src.agent.reporters.maintenance_report import MaintenanceReporter

        monkeypatch.chdir(tmp_path)
        reporter = MaintenanceReporter()
        filepath = reporter.save("# Report", "session-1")
        assert "data" in str(filepath)
        assert "maintenance_reports" in str(filepath)


class TestComparisonReporter:
    def test_generate_comparison_report(self):
        from src.agent.reporters.comparison_report import ComparisonReporter

        reporter = ComparisonReporter()
        reporter.add_result("方案A", {"chunk_count": 100, "char_count": 50000})
        reporter.add_result("方案B", {"chunk_count": 85, "char_count": 48000})
        report = reporter.generate()
        assert "# 对比报告" in report
        assert "方案A" in report
        assert "方案B" in report
        assert "chunk_count" in report

    def test_generate_with_insufficient_results(self):
        from src.agent.reporters.comparison_report import ComparisonReporter

        reporter = ComparisonReporter()
        reporter.add_result("方案A", {"chunk_count": 100})
        report = reporter.generate()
        assert "至少两组" in report

    def test_save_comparison_report(self, tmp_path, monkeypatch):
        from src.agent.reporters.comparison_report import ComparisonReporter

        monkeypatch.chdir(tmp_path)
        reporter = ComparisonReporter()
        reporter.add_result("A", {"count": 10})
        reporter.add_result("B", {"count": 20})
        report = reporter.generate()
        filepath = reporter.save(report, "comp-session")
        assert filepath.exists()
        assert "comparison" in filepath.name

    def test_metrics_with_non_numeric_values(self):
        from src.agent.reporters.comparison_report import ComparisonReporter

        reporter = ComparisonReporter()
        reporter.add_result("A", {"strategy": "page_aware", "count": 100})
        reporter.add_result("B", {"strategy": "fixed", "count": 80})
        report = reporter.generate()
        assert "page_aware" in report
        assert "fixed" in report


class TestReportTools:
    def test_generate_maintenance_report_tool_exists(self):
        from src.agent.tools import generate_maintenance_report_tool

        assert (
            generate_maintenance_report_tool.name == "generate_maintenance_report_tool"
        )

    def test_generate_comparison_report_tool_exists(self):
        from src.agent.tools import generate_comparison_report_tool

        assert generate_comparison_report_tool.name == "generate_comparison_report_tool"

    def test_maintenance_report_tool_invocation(self, tmp_path, monkeypatch):
        from src.agent.tools import generate_maintenance_report_tool

        monkeypatch.chdir(tmp_path)
        result = generate_maintenance_report_tool.invoke(
            {
                "session_id": "test",
                "current_source": "test.pdf",
                "execution_log": ["TOOL: parse_pdf_tool"],
                "stage_history": ["parse_pdf_tool"],
            }
        )
        parsed = json.loads(result)
        assert parsed["status"] == "generated"
        assert "report_path" in parsed

    def test_comparison_report_tool_invocation(self, tmp_path, monkeypatch):
        from src.agent.tools import generate_comparison_report_tool

        monkeypatch.chdir(tmp_path)
        result = generate_comparison_report_tool.invoke(
            {
                "results": [
                    {"label": "A", "metrics": {"count": 100}},
                    {"label": "B", "metrics": {"count": 80}},
                ],
                "session_id": "test",
            }
        )
        parsed = json.loads(result)
        assert parsed["status"] == "generated"
        assert "report_path" in parsed

    def test_get_tools_returns_21_tools(self):
        from src.agent.graph import _get_tools

        _get_tools.cache_clear()
        tools = _get_tools()
        assert len(tools) == 21
        tool_names = {t.name for t in tools}
        assert "generate_maintenance_report_tool" in tool_names
        assert "generate_comparison_report_tool" in tool_names
        _get_tools.cache_clear()
