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

    def test_thinking_parts_persisted_in_message(self):
        thinking_parts = [
            {"type": "thinking", "content": "分析索引状态"},
            {"type": "tool_call", "tool": "list_meals", "args": {}},
            {"type": "tool_result", "tool_id": "tc1", "content": "3 meals found"},
        ]
        msg = {
            "role": "assistant",
            "content": "诊断完成",
            "thinking_parts": thinking_parts,
            "thinking_expanded": True,
        }
        assert msg["thinking_parts"] == thinking_parts
        assert msg["thinking_expanded"] is True
        assert len(msg["thinking_parts"]) == 3

    def test_message_backward_compatibility(self):
        msg = {"role": "assistant", "content": "旧格式消息"}
        assert msg.get("thinking_parts") is None
        assert msg.get("thinking_expanded", True) is True

    def test_expand_all_updates_thinking_expanded(self):
        messages = [
            {
                "role": "assistant",
                "content": "回复1",
                "thinking_parts": [{"type": "thinking", "content": "思考1"}],
                "thinking_expanded": False,
            },
            {
                "role": "assistant",
                "content": "回复2",
                "thinking_parts": [{"type": "thinking", "content": "思考2"}],
                "thinking_expanded": False,
            },
            {"role": "user", "content": "问题"},
        ]
        for msg in messages:
            if msg["role"] == "assistant" and msg.get("thinking_parts"):
                msg["thinking_expanded"] = True
        assert messages[0]["thinking_expanded"] is True
        assert messages[1]["thinking_expanded"] is True

    def test_collapse_all_updates_thinking_expanded(self):
        messages = [
            {
                "role": "assistant",
                "content": "回复1",
                "thinking_parts": [{"type": "thinking", "content": "思考1"}],
                "thinking_expanded": True,
            },
            {
                "role": "assistant",
                "content": "回复2",
                "thinking_parts": [{"type": "thinking", "content": "思考2"}],
                "thinking_expanded": True,
            },
        ]
        for msg in messages:
            if msg["role"] == "assistant" and msg.get("thinking_parts"):
                msg["thinking_expanded"] = False
        assert messages[0]["thinking_expanded"] is False
        assert messages[1]["thinking_expanded"] is False

    def test_toggle_does_not_affect_existing_messages(self):
        messages = [
            {
                "role": "assistant",
                "content": "回复1",
                "thinking_parts": [{"type": "thinking", "content": "思考1"}],
                "thinking_expanded": True,
            },
        ]
        new_collapse = True
        new_msg = {
            "role": "assistant",
            "content": "回复2",
            "thinking_parts": [{"type": "thinking", "content": "思考2"}],
            "thinking_expanded": not new_collapse,
        }
        messages.append(new_msg)
        assert messages[0]["thinking_expanded"] is True
        assert messages[1]["thinking_expanded"] is False
