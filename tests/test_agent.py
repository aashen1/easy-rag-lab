from __future__ import annotations

import json

import pytest

from src.agent.state import MaintenanceState
from src.agent.tools import HIGH_RISK_TOOLS


@pytest.fixture
def mock_config():
    return {
        "llm": {
            "api_key": "test-key",
            "base_url": "https://api.test.com",
            "model": "claude-sonnet-4-20250514",
        },
        "meal": {"data_dir": "data/meals"},
        "index": {"persist_dir": "data/index"},
    }


class TestMaintenanceState:
    def test_state_has_required_fields(self):
        state = MaintenanceState(
            messages=[],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
        )
        assert state["messages"] == []
        assert state["current_meal"] is None
        assert state["execution_log"] == []

    def test_state_accepts_values(self):
        state = MaintenanceState(
            messages=[{"role": "user", "content": "test"}],
            current_meal="test_meal",
            current_source="test.pdf",
            diagnosis=[{"issue": "bad chunk"}],
            pending_action={"tool": "rebuild_index"},
            approved=True,
            execution_log=["TOOL: list_meals"],
        )
        assert state["current_meal"] == "test_meal"
        assert state["diagnosis"] == [{"issue": "bad chunk"}]
        assert state["approved"] is True


class TestHighRiskTools:
    def test_high_risk_tools_set(self):
        assert "rebuild_index" in HIGH_RISK_TOOLS
        assert "delete_source" in HIGH_RISK_TOOLS
        assert "update_meal" in HIGH_RISK_TOOLS

    def test_safe_tools_not_in_high_risk(self):
        assert "list_meals" not in HIGH_RISK_TOOLS
        assert "get_meal_detail" not in HIGH_RISK_TOOLS
        assert "query_rag_tool" not in HIGH_RISK_TOOLS


class TestToolFunctions:
    def test_list_meals_tool_exists(self):
        from src.agent.tools import list_meals

        assert list_meals.name == "list_meals"
        assert "List all available meals" in list_meals.description

    def test_get_meal_detail_tool_exists(self):
        from src.agent.tools import get_meal_detail

        assert get_meal_detail.name == "get_meal_detail"

    def test_query_rag_tool_exists(self):
        from src.agent.tools import query_rag_tool

        assert query_rag_tool.name == "query_rag_tool"

    def test_parse_pdf_tool_exists(self):
        from src.agent.tools import parse_pdf_tool

        assert parse_pdf_tool.name == "parse_pdf_tool"

    def test_enhance_page_tool_exists(self):
        from src.agent.tools import enhance_page_tool

        assert enhance_page_tool.name == "enhance_page_tool"

    def test_chunk_parsed_tool_exists(self):
        from src.agent.tools import chunk_parsed_tool

        assert chunk_parsed_tool.name == "chunk_parsed_tool"

    def test_evaluate_answer_tool_exists(self):
        from src.agent.tools import evaluate_answer_tool

        assert evaluate_answer_tool.name == "evaluate_answer_tool"

    def test_get_index_info_tool_exists(self):
        from src.agent.tools import get_index_info

        assert get_index_info.name == "get_index_info"

    def test_list_meals_error_handling(self):
        from src.agent.tools import list_meals

        result = list_meals.invoke({})
        assert "Error" in result or isinstance(json.loads(result), list)

    def test_get_meal_detail_error_handling(self):
        from src.agent.tools import get_meal_detail

        result = get_meal_detail.invoke({"meal_name": "nonexistent"})
        assert isinstance(result, str)


class TestGraphBuild:
    def test_build_graph(self):
        from src.agent.graph import build_graph

        graph = build_graph()
        assert "agent" in graph.nodes
        assert "approval" in graph.nodes
        assert "tools" in graph.nodes

    def test_compile_agent(self):
        from src.agent.graph import compile_agent

        agent = compile_agent()
        assert agent is not None

    def test_compile_agent_with_checkpointer(self):
        from langgraph.checkpoint.memory import MemorySaver

        from src.agent.graph import compile_agent

        checkpointer = MemorySaver()
        agent = compile_agent(checkpointer=checkpointer)
        assert agent is not None


class TestShouldContinue:
    def test_routes_to_tools_when_tool_calls(self):
        from langchain_core.messages import AIMessage

        from src.agent.graph import should_continue

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "list_meals", "args": {}, "id": "1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
        )
        assert should_continue(state) == "tools"

    def test_routes_to_end_when_no_tool_calls(self):
        from langchain_core.messages import AIMessage

        from src.agent.graph import should_continue

        state = MaintenanceState(
            messages=[AIMessage(content="I'll help you with that.")],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
        )
        assert should_continue(state) == "__end__"


class TestToolNode:
    def test_tool_node_handles_unknown_tool(self):
        from langchain_core.messages import AIMessage, ToolMessage

        from src.agent.graph import tool_node

        state = MaintenanceState(
            messages=[
                AIMessage(
                    content="",
                    tool_calls=[{"name": "nonexistent_tool", "args": {}, "id": "tc1"}],
                )
            ],
            current_meal=None,
            current_source=None,
            diagnosis=[],
            pending_action=None,
            approved=None,
            execution_log=[],
        )
        result = tool_node(state)
        assert len(result["messages"]) == 1
        assert isinstance(result["messages"][0], ToolMessage)
        assert "Unknown tool" in result["messages"][0].content


class TestSystemPrompt:
    def test_prompt_contains_workflow(self):
        from src.agent.prompt import SYSTEM_PROMPT

        assert "诊断" in SYSTEM_PROMPT
        assert "修复" in SYSTEM_PROMPT
        assert "高风险" in SYSTEM_PROMPT

    def test_prompt_mentions_risk_tools(self):
        from src.agent.prompt import SYSTEM_PROMPT

        assert "rebuild_index" in SYSTEM_PROMPT
        assert "delete_source" in SYSTEM_PROMPT
        assert "update_meal" in SYSTEM_PROMPT
