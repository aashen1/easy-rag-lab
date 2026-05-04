from __future__ import annotations

import functools
from typing import Any, Literal

from langchain_core.messages import AIMessage, SystemMessage, ToolMessage
from langgraph.graph import END, START, StateGraph
from langgraph.types import interrupt
from loguru import logger

from src.agent.config import get_delete_count_threshold
from src.agent.prompt import build_system_prompt
from src.agent.state import MaintenanceState
from src.agent.tools import FORBIDDEN_OPERATIONS, HIGH_RISK_TOOLS

_agent_store = None

DIAGNOSIS_TOOLS = {
    "list_meals",
    "get_meal_detail",
    "query_rag_tool",
    "get_index_info",
    "evaluate_answer_tool",
    "list_pdfs",
    "list_issues",
}

REPAIR_TOOLS = {
    "rebuild_index",
    "delete_source",
    "delete_and_reindex_tool",
    "update_meal",
}


@functools.lru_cache(maxsize=1)
def _get_tools():
    from src.agent.tools import (
        chunk_parsed_tool,
        close_issue,
        create_curated_meal,
        create_issue,
        delete_and_reindex_tool,
        delete_source,
        embed_chunks_tool,
        enhance_page_tool,
        evaluate_answer_tool,
        generate_comparison_report_tool,
        generate_maintenance_report_tool,
        get_index_info,
        get_meal_detail,
        index_chunks_tool,
        list_issues,
        list_meals,
        list_pdfs,
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
        embed_chunks_tool,
        index_chunks_tool,
        delete_and_reindex_tool,
        create_curated_meal,
        list_pdfs,
        create_issue,
        list_issues,
        close_issue,
        rebuild_index,
        delete_source,
        update_meal,
        generate_maintenance_report_tool,
        generate_comparison_report_tool,
    ]


@functools.lru_cache(maxsize=1)
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


def _infer_pdf_type(source: str) -> str:
    source_lower = source.lower()
    if "年报" in source_lower or "annual" in source_lower:
        return "annual_report"
    if "研报" in source_lower or "research" in source_lower:
        return "research_report"
    return "generic"


def agent_node(state: MaintenanceState) -> dict[str, Any]:
    """LLM decision node: invoke the model with tools bound.

    If a tool is locked (``locked_tool`` is set), skip LLM decision and
    construct an AIMessage with the specified tool_call directly. The lock
    is cleared after being consumed.

    Args:
        state: Current graph state.

    Returns:
        State update with the LLM's response message.
    """
    locked_tool = state.get("locked_tool")
    locked_tool_args = state.get("locked_tool_args")

    if locked_tool:
        import uuid

        tool_call = {
            "name": locked_tool,
            "args": locked_tool_args or {},
            "id": f"locked_{uuid.uuid4().hex[:8]}",
        }
        ai_message = AIMessage(content="", tool_calls=[tool_call])
        return {
            "messages": [ai_message],
            "locked_tool": None,
            "locked_tool_args": None,
        }

    llm = _get_llm()
    tools = _get_tools()
    llm_with_tools = llm.bind_tools(tools)

    experiences = None
    if _agent_store is not None:
        try:
            from src.agent.memory.experience_store import ExperienceStore

            exp_store = ExperienceStore(_agent_store)
            current_source = state.get("current_source")
            if current_source:
                pdf_type = _infer_pdf_type(current_source)
                namespace = ("default", "maintenance_experience", pdf_type)
                experiences = exp_store.get_all_experiences(namespace)
        except Exception as e:
            logger.warning(f"Failed to retrieve experiences: {e}")

    system_content = build_system_prompt(
        stage_history=state.get("stage_history"),
        experiences=experiences,
        mode=state.get("mode", "light"),
    )
    messages = [SystemMessage(content=system_content)] + state["messages"]
    response = llm_with_tools.invoke(messages)

    return {"messages": [response]}


def approval_node(state: MaintenanceState) -> dict[str, Any]:
    """Check if any pending tool calls are high-risk and require human approval.

    Uses LangGraph interrupt() to pause execution and wait for user decision.

    For each high-risk tool call, the user is prompted to approve or reject.
    - Approved calls are kept in the AI message's tool_calls for execution.
    - Rejected calls are replaced with ToolMessage responses indicating rejection.

    If all tool calls are rejected, the node returns rejection messages so the
    graph routes back to the agent node for re-evaluation instead of proceeding
    to tool execution.

    Args:
        state: Current graph state.

    Returns:
        State update dict. If any rejections occurred, includes a modified
        AIMessage (with only approved tool_calls) and rejection ToolMessages.
        If all operations are approved, returns empty dict (no state change).
    """
    last_message = state["messages"][-1]
    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {}

    rejected_messages = []
    log_entries = []
    remaining_tool_calls = []

    for tool_call in last_message.tool_calls:
        if tool_call["name"] in FORBIDDEN_OPERATIONS:
            rejected_messages.append(
                ToolMessage(
                    content=f"禁止的操作：{tool_call['name']} 不允许执行（安全策略）",
                    tool_call_id=tool_call["id"],
                )
            )
            log_entries.append(f"FORBIDDEN: {tool_call['name']}")
            logger.warning(f"Forbidden operation blocked: {tool_call['name']}")
        elif tool_call["name"] in HIGH_RISK_TOOLS:
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
            content=last_message.content or "",
            tool_calls=remaining_tool_calls,
            id=last_message.id,
        )
        return {
            "messages": [updated_ai] + rejected_messages,
            "execution_log": state.get("execution_log", []) + log_entries,
        }

    return {}


def _route_after_approval(state: MaintenanceState) -> Literal["tools", "agent"]:
    """Route after approval: if there are approved tool calls, execute them;
    otherwise go back to agent for re-evaluation.

    After approval_node, the last message could be:
    - A ToolMessage (rejection) if all tools were rejected -> go to agent
    - An AIMessage with remaining tool_calls if some were approved -> go to tools
    - The original AIMessage if no high-risk tools were present -> go to tools

    Args:
        state: Current graph state.

    Returns:
        "tools" if there are pending tool calls to execute, "agent" otherwise.
    """
    last_message = state["messages"][-1]
    if isinstance(last_message, AIMessage) and last_message.tool_calls:
        return "tools"
    return "agent"


def tool_node(state: MaintenanceState) -> dict[str, Any]:
    """Execute tool calls from the last AI message and return results.

    Implements two safety mechanisms:

    1. **Stage guard**: If a REPAIR tool is called without any prior
       DIAGNOSIS tool in ``stage_history``, the call is rejected with a
       message telling the LLM to diagnose first.
    2. **Delete count**: Tracks how many ``delete_source`` calls have
       been made.  When the count reaches ``DELETE_COUNT_THRESHOLD``,
       an interrupt is triggered to warn the user about cumulative
       impact.

    Args:
        state: Current graph state.

    Returns:
        State update with tool results and execution log entries.
    """
    tools_by_name = {t.name: t for t in _get_tools()}
    last_message = state["messages"][-1]

    if not isinstance(last_message, AIMessage) or not last_message.tool_calls:
        return {"messages": []}

    stage_history = state.get("stage_history", [])
    has_diagnosis = bool(set(stage_history) & DIAGNOSIS_TOOLS)

    results = []
    log_entries = []
    executed_tools = []
    new_delete_count = state.get("delete_count", 0)

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

        if tool_call["name"] in REPAIR_TOOLS and not has_diagnosis:
            logger.info(f"GUARD: {tool_call['name']} blocked - no diagnosis performed")
            results.append(
                ToolMessage(
                    content=(
                        "操作被拒绝：请先进行诊断（查看 meal、检查索引、测试查询），"
                        "再执行修复操作。可用诊断工具：list_meals, get_meal_detail, "
                        "query_rag_tool, get_index_info, evaluate_answer_tool"
                    ),
                    tool_call_id=tool_call["id"],
                )
            )
            log_entries.append(f"GUARD: {tool_call['name']} blocked - no diagnosis")
            continue

        if (
            tool_call["name"] == "delete_source"
            and new_delete_count >= get_delete_count_threshold()
        ):
            interrupt(
                {
                    "question": (
                        f"⚠️ 累计删除警告：已执行 {new_delete_count} 次删除操作，"
                        f"继续删除可能严重影响数据完整性。请确认是否继续。"
                    ),
                    "tool_call": {
                        "name": tool_call["name"],
                        "args": tool_call["args"],
                        "id": tool_call["id"],
                    },
                }
            )

        try:
            tool_args = dict(tool_call["args"])
            if tool_call["name"] == "generate_maintenance_report_tool":
                tool_args.setdefault("current_source", state.get("current_source"))
                tool_args.setdefault("current_meal", state.get("current_meal"))
                tool_args.setdefault("execution_log", state.get("execution_log", []))
                tool_args.setdefault("stage_history", state.get("stage_history", []))
                tool_args.setdefault("diagnosis", state.get("diagnosis", []))
            observation = tool_fn.invoke(tool_args)
            log_entry = f"TOOL: {tool_call['name']}"
        except Exception as e:
            logger.error(f"Tool {tool_call['name']} failed: {e}")
            observation = f"Error: {e}"
            log_entry = f"TOOL_ERROR: {tool_call['name']} - {e}"

        results.append(
            ToolMessage(content=str(observation), tool_call_id=tool_call["id"])
        )
        log_entries.append(log_entry)
        executed_tools.append(tool_call["name"])

        if tool_call["name"] == "delete_source":
            new_delete_count += 1

    if _agent_store is not None and executed_tools:
        experience_tools = {"parse_pdf_tool", "chunk_parsed_tool"}
        if any(t in experience_tools for t in executed_tools):
            try:
                from src.agent.memory.experience_store import ExperienceStore

                exp_store = ExperienceStore(_agent_store)
                current_source = state.get("current_source")
                if current_source:
                    pdf_type = _infer_pdf_type(current_source)
                    namespace = ("default", "maintenance_experience", pdf_type)

                    best_parser = None
                    best_chunk_strategy = None
                    best_chunk_size = None
                    for tool_call in last_message.tool_calls:
                        args = tool_call.get("args", {})
                        if tool_call["name"] == "parse_pdf_tool":
                            best_parser = args.get("parser_name")
                        elif tool_call["name"] == "chunk_parsed_tool":
                            best_chunk_strategy = args.get("strategy")
                            chunk_size_val = args.get("chunk_size")
                            if chunk_size_val is not None:
                                best_chunk_size = chunk_size_val
                            if args.get("parser_name") and not best_parser:
                                best_parser = args.get("parser_name")

                    experience = {
                        "pdf_type": pdf_type,
                        "source": current_source,
                        "best_parser": best_parser,
                        "best_chunk_strategy": best_chunk_strategy,
                        "best_chunk_size": best_chunk_size,
                        "reason": f"Auto-saved after {', '.join(executed_tools)}",
                        "tools_used": executed_tools,
                    }
                    exp_store.save_experience(namespace, experience)
            except Exception as e:
                logger.warning(f"Failed to save experience: {e}")

    auto_review = state.get("auto_review", False)
    if auto_review and executed_tools:
        review_tools = {"parse_pdf_tool", "chunk_parsed_tool"}
        reviewable = [t for t in executed_tools if t in review_tools]
        if reviewable:
            interrupt(
                {
                    "question": f"自动审查：{', '.join(reviewable)} 执行完成，请检查结果",
                    "tools": reviewable,
                }
            )

    return {
        "messages": results,
        "execution_log": state.get("execution_log", []) + log_entries,
        "stage_history": state.get("stage_history", []) + executed_tools,
        "delete_count": new_delete_count,
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
    graph.add_conditional_edges(
        "approval",
        _route_after_approval,
        {"tools": "tools", "agent": "agent"},
    )
    graph.add_edge("tools", "agent")

    return graph


def compile_agent(checkpointer=None, store=None):
    """Compile the maintenance agent graph with an optional checkpointer.

    Args:
        checkpointer: Optional LangGraph checkpointer for persistence.
            Defaults to None (no persistence).
        store: Optional LangGraph store for experience persistence.
            Defaults to None (no experience store).

    Returns:
        Compiled graph ready for invocation.
    """
    global _agent_store
    _agent_store = store

    graph = build_graph()
    return graph.compile(checkpointer=checkpointer, store=store)
