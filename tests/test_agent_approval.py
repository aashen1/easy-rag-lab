from __future__ import annotations

from unittest.mock import patch

import pytest
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage

from src.agent.graph import _route_after_approval, approval_node
from src.agent.state import MaintenanceState

pytestmark = pytest.mark.agent


def _make_state(messages, **overrides):
    defaults = {
        "messages": messages,
        "current_meal": None,
        "current_source": None,
        "diagnosis": [],
        "pending_action": None,
        "approved": None,
        "execution_log": [],
        "stage_history": [],
        "auto_review": False,
    }
    defaults.update(overrides)
    return MaintenanceState(**defaults)


class TestApprovalNode:
    def test_no_approval_needed_for_low_risk_tool(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_meals", "args": {}, "id": "tc1"}],
        )
        state = _make_state([HumanMessage(content="hi"), ai_msg])

        result = approval_node(state)

        assert result == {}

    def test_no_approval_for_non_ai_message(self):
        state = _make_state([HumanMessage(content="hi")])

        result = approval_node(state)

        assert result == {}

    def test_no_approval_for_ai_message_without_tool_calls(self):
        ai_msg = AIMessage(content="I will help you.")
        state = _make_state([HumanMessage(content="hi"), ai_msg])

        result = approval_node(state)

        assert result == {}

    def test_forbidden_operation_blocked_without_interrupt(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "delete_collection", "args": {}, "id": "tc1"},
            ],
        )
        state = _make_state([HumanMessage(content="hi"), ai_msg])

        with patch("src.agent.graph.interrupt") as mock_interrupt:
            result = approval_node(state)
            mock_interrupt.assert_not_called()

        assert "messages" in result
        assert "execution_log" in result
        assert any("FORBIDDEN" in e for e in result["execution_log"])

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert (
            "禁止" in tool_msgs[0].content
            or "forbidden" in tool_msgs[0].content.lower()
        )

    def test_high_risk_tool_approved(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "rebuild_index", "args": {"source": "test.pdf"}, "id": "tc1"},
            ],
        )
        state = _make_state([HumanMessage(content="hi"), ai_msg])

        with patch("src.agent.graph.interrupt", return_value=True):
            result = approval_node(state)

        assert result == {}

    def test_high_risk_tool_rejected(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "delete_source", "args": {"source": "test.pdf"}, "id": "tc1"},
            ],
        )
        state = _make_state([HumanMessage(content="hi"), ai_msg])

        with patch("src.agent.graph.interrupt", return_value=False):
            result = approval_node(state)

        assert "messages" in result
        assert "execution_log" in result
        assert any("REJECTED" in e for e in result["execution_log"])

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1
        assert (
            "拒绝" in tool_msgs[0].content or "rejected" in tool_msgs[0].content.lower()
        )

        updated_ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert len(updated_ai_msgs) == 1
        assert updated_ai_msgs[0].tool_calls == []

    def test_mixed_forbidden_and_high_risk(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "delete_collection", "args": {}, "id": "tc1"},
                {"name": "rebuild_index", "args": {}, "id": "tc2"},
            ],
        )
        state = _make_state([HumanMessage(content="hi"), ai_msg])

        with patch("src.agent.graph.interrupt", return_value=True):
            result = approval_node(state)

        assert "messages" in result
        assert any("FORBIDDEN" in e for e in result["execution_log"])
        assert any("APPROVED" in e for e in result["execution_log"])

        updated_ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert len(updated_ai_msgs) == 1
        assert len(updated_ai_msgs[0].tool_calls) == 1
        assert updated_ai_msgs[0].tool_calls[0]["name"] == "rebuild_index"

    def test_mixed_approved_and_rejected_high_risk(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "rebuild_index", "args": {}, "id": "tc1"},
                {"name": "delete_source", "args": {}, "id": "tc2"},
            ],
        )
        state = _make_state([HumanMessage(content="hi"), ai_msg])

        call_count = 0

        def side_effect(_value):
            nonlocal call_count
            call_count += 1
            return call_count == 1

        with patch("src.agent.graph.interrupt", side_effect=side_effect):
            result = approval_node(state)

        updated_ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert len(updated_ai_msgs[0].tool_calls) == 1
        assert updated_ai_msgs[0].tool_calls[0]["name"] == "rebuild_index"

        tool_msgs = [m for m in result["messages"] if isinstance(m, ToolMessage)]
        assert len(tool_msgs) == 1

    def test_all_rejected_preserves_original_ai_content(self):
        original_content = "I was about to delete this source."
        ai_msg = AIMessage(
            content=original_content,
            tool_calls=[
                {"name": "delete_source", "args": {}, "id": "tc1"},
            ],
        )
        state = _make_state([HumanMessage(content="hi"), ai_msg])

        with patch("src.agent.graph.interrupt", return_value=False):
            result = approval_node(state)

        updated_ai_msgs = [m for m in result["messages"] if isinstance(m, AIMessage)]
        assert updated_ai_msgs[0].content == original_content

    def test_execution_log_appended_to_existing(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[
                {"name": "delete_collection", "args": {}, "id": "tc1"},
            ],
        )
        state = _make_state(
            [HumanMessage(content="hi"), ai_msg],
            execution_log=["PREVIOUS_ENTRY"],
        )

        with patch("src.agent.graph.interrupt"):
            result = approval_node(state)

        assert "PREVIOUS_ENTRY" in result["execution_log"]
        assert any("FORBIDDEN" in e for e in result["execution_log"])


class TestRouteAfterApproval:
    def test_routes_to_tools_when_ai_has_tool_calls(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_meals", "args": {}, "id": "tc1"}],
        )
        state = _make_state([ai_msg])

        result = _route_after_approval(state)

        assert result == "tools"

    def test_routes_to_agent_when_last_is_tool_message(self):
        tool_msg = ToolMessage(content="Result", tool_call_id="tc1")
        state = _make_state([tool_msg])

        result = _route_after_approval(state)

        assert result == "agent"

    def test_routes_to_agent_when_ai_has_no_tool_calls(self):
        ai_msg = AIMessage(content="Done.")
        state = _make_state([ai_msg])

        result = _route_after_approval(state)

        assert result == "agent"

    def test_routes_to_tools_after_partial_approval(self):
        ai_msg = AIMessage(
            content="",
            tool_calls=[{"name": "list_meals", "args": {}, "id": "tc1"}],
        )
        tool_msg = ToolMessage(content="Rejected", tool_call_id="tc2")
        state = _make_state([tool_msg, ai_msg])

        result = _route_after_approval(state)

        assert result == "tools"

    def test_routes_to_agent_after_all_rejected(self):
        tool_msg = ToolMessage(content="Rejected", tool_call_id="tc1")
        ai_msg = AIMessage(content="", tool_calls=[])
        state = _make_state([ai_msg, tool_msg])

        result = _route_after_approval(state)

        assert result == "agent"
