from __future__ import annotations

from typing import Any, Literal

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from loguru import logger

from src.agent.prompt import SYSTEM_PROMPT
from src.agent.state import MaintenanceState
from src.agent.tools import HIGH_RISK_TOOLS


def _get_tools():
    from src.agent.tools import (
        chunk_parsed_tool,
        delete_source,
        enhance_page_tool,
        evaluate_answer_tool,
        get_index_info,
        get_meal_detail,
        list_meals,
        parse_pdf_tool,
        query_rag_tool,
        rebuild_index,
        update_meal,
    )

    return [
        list_meals,
        get_meal_detail,
        query_rag_tool,
        parse_pdf_tool,
        enhance_page_tool,
        chunk_parsed_tool,
        evaluate_answer_tool,
        get_index_info,
        rebuild_index,
        delete_source,
        update_meal,
    ]


def _get_llm():
    from src.llm_client import create_langchain_anthropic_client
    from src.utils import get_llm_config, load_config

    config = load_config()
    llm_config = get_llm_config(config)
    return create_langchain_anthropic_client(
        api_key=llm_config["api_key"],
        base_url=llm_config["base_url"],
        model_name=llm_config["model_name"],
        temperature=llm_config["temperature"],
        max_tokens=llm_config["max_tokens"],
    )


def agent_node(state: MaintenanceState) -> dict[str, Any]:
    """LLM decision node: invoke the model with tools bound.

    Args:
        state: Current graph state.

    Returns:
        State update with the LLM's response message.
    """
    llm = _get_llm()
    tools = _get_tools()
    llm_with_tools = llm.bind_tools(tools)

    messages = [SystemMessage(content=SYSTEM_PROMPT)] + state["messages"]
    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}


def approval_node(state: MaintenanceState) -> dict[str, Any]:
    """Check if any pending tool calls are high-risk and require human approval.

    Uses LangGraph interrupt() to pause execution and wait for user decision.

    Args:
        state: Current graph state.

    Returns:
        State update with rejection messages for denied operations,
        or empty dict if all operations are approved.
    """
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    rejected_messages = []
    log_entries = []
    remaining_tool_calls = []

    for tool_call in last_message.tool_calls:
        if tool_call["name"] in HIGH_RISK_TOOLS:
            decision = interrupt(
                {
                    "question": f"高风险操作需要确认：{tool_call['name']}",
                    "tool_call": {
                        "name": tool_call["name"],
                        "args": tool_call["args"],
                        "id": tool_call["id"],
                    },
                }
            )
            if not decision:
                rejected_messages.append(
                    ToolMessage(
                        content=f"用户拒绝了操作：{tool_call['name']}",
                        tool_call_id=tool_call["id"],
                    )
                )
                log_entries.append(f"REJECTED: {tool_call['name']}")
            else:
                remaining_tool_calls.append(tool_call)
                log_entries.append(f"APPROVED: {tool_call['name']}")
        else:
            remaining_tool_calls.append(tool_call)

    if rejected_messages:
        updated_ai = AIMessage(
            content=last_message.content,
            tool_calls=remaining_tool_calls,
            id=last_message.id,
        )
        return {
            "messages": [updated_ai] + rejected_messages,
            "execution_log": state.get("execution_log", []) + log_entries,
        }

    return {}


def tool_node(state: MaintenanceState) -> dict[str, Any]:
    """Execute tool calls from the last AI message and return results.

    Args:
        state: Current graph state.

    Returns:
        State update with tool results and execution log entries.
    """
    tools_by_name = {t.name: t for t in _get_tools()}
    last_message = state["messages"][-1]

    results = []
    log_entries = []

    for tool_call in last_message.tool_calls:
        tool_fn = tools_by_name.get(tool_call["name"])
        if tool_fn is None:
            results.append(
                ToolMessage(
                    content=f"Unknown tool: {tool_call['name']}",
                    tool_call_id=tool_call["id"],
                )
            )
            continue

        try:
            observation = tool_fn.invoke(tool_call["args"])
            log_entry = f"TOOL: {tool_call['name']}"
        except Exception as e:
            logger.error(f"Tool {tool_call['name']} failed: {e}")
            observation = f"Error: {e}"
            log_entry = f"TOOL_ERROR: {tool_call['name']} - {e}"

        results.append(
            ToolMessage(content=str(observation), tool_call_id=tool_call["id"])
        )
        log_entries.append(log_entry)

    return {
        "messages": results,
        "execution_log": state.get("execution_log", []) + log_entries,
    }


def should_continue(state: MaintenanceState) -> Literal["tools", "__end__"]:
    """Route to tool execution if the LLM made tool calls, otherwise end.

    Args:
        state: Current graph state.

    Returns:
        "tools" if there are pending tool calls, END otherwise.
    """
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return END


def build_graph() -> StateGraph:
    """Build the maintenance agent StateGraph.

    Returns:
        Uncompiled StateGraph with agent, approval, and tools nodes.
    """
    graph = StateGraph(MaintenanceState)

    graph.add_node("agent", agent_node)
    graph.add_node("approval", approval_node)
    graph.add_node("tools", tool_node)

    graph.add_edge(START, "agent")
    graph.add_conditional_edges(
        "agent", should_continue, {"tools": "approval", END: END}
    )
    graph.add_edge("approval", "tools")
    graph.add_edge("tools", "agent")

    return graph


def compile_agent(checkpointer=None):
    """Compile the maintenance agent graph with an optional checkpointer.

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence.
            Defaults to None (no persistence).

    Returns:
        Compiled graph ready for invocation.
    """
    graph = build_graph()
    return graph.compile(checkpointer=checkpointer)
