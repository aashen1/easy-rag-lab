from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.unit


@pytest.fixture
def ui_mock_config():
    with patch(
        "src.utils.load_config",
        return_value={
            "llm": {
                "api_key": "test-key",
                "base_url": "https://api.test.com",
                "model": "claude-sonnet-4-20250514",
            },
            "meal": {"data_dir": "data/meals"},
            "index": {"persist_dir": "data/index"},
            "agent": {
                "checkpoint": {"db_path": "data/test_checkpoints.db"},
                "defaults": {
                    "thread_id": "test-session",
                    "parser_name": "pymupdf4llm",
                },
            },
        },
    ):
        yield


@pytest.fixture
def ui_mock_logger():
    with patch("src.utils.setup_logger"):
        yield


@pytest.fixture
def ui_mock_agent():
    mock_agent = MagicMock()
    mock_result = {
        "messages": [MagicMock(content="诊断完成", tool_calls=[])],
        "execution_log": ["TOOL: list_meals"],
        "stage_history": ["list_meals"],
        "current_meal": None,
        "current_source": None,
        "diagnosis": [],
    }
    mock_agent.invoke.return_value = mock_result
    with patch(
        "src.app_pages.maintenance._get_compiled_agent", return_value=mock_agent
    ):
        yield mock_agent


@pytest.fixture
def app(ui_mock_config, ui_mock_logger, ui_mock_agent):
    from streamlit.testing.v1 import AppTest

    at = AppTest.from_file("src/app.py")
    at.run(timeout=30)
    yield at


class TestMaintenanceTab:
    def test_app_has_maintenance_tab(self, app):
        assert len(app.tabs) >= 4
        tab_labels = [t.label for t in app.tabs]
        assert any("维修工" in label for label in tab_labels)

    def test_maintenance_page_renders(self, app):
        assert not app.exception


class TestMaintenancePageUnit:
    def test_extract_response_text(self):
        from langchain_core.messages import AIMessage

        from src.app_pages.maintenance import _extract_response_text

        result = {
            "messages": [
                AIMessage(content="诊断结果：索引正常"),
            ]
        }
        text = _extract_response_text(result)
        assert "诊断结果" in text

    def test_extract_response_text_empty(self):
        from src.app_pages.maintenance import _extract_response_text

        result = {"messages": []}
        text = _extract_response_text(result)
        assert "无文字回复" in text

    def test_get_tool_names(self):
        from src.app_pages.maintenance import _get_tool_names

        names = _get_tool_names()
        assert "自动" in names
        assert "list_meals" in names
