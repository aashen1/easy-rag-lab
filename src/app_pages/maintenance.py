from __future__ import annotations

import streamlit as st
from loguru import logger

from src.agent.config import get_agent_default


def _get_tool_names() -> list[str]:
    """Return list of available tool names for the lock dropdown."""
    from src.agent.graph import _get_tools

    _get_tools.cache_clear()
    tools = _get_tools()
    names = ["自动"] + [t.name for t in tools]
    _get_tools.cache_clear()
    return names


@st.cache_resource
def _get_compiled_agent():
    """Compile the agent with SqliteSaver and InMemoryStore, cached."""
    from langgraph.store.memory import InMemoryStore

    from src.agent.checkpoint import get_checkpointer
    from src.agent.graph import compile_agent

    store = InMemoryStore()
    with get_checkpointer() as checkpointer:
        return compile_agent(checkpointer=checkpointer, store=store)


def render_maintenance():
    """Render the maintenance agent tab in the Streamlit app."""
    st.subheader("🔧 RAG 维修工")

    if "maintenance_thread_id" not in st.session_state:
        default_tid = get_agent_default("thread_id", "maintenance-session")
        st.session_state.maintenance_thread_id = default_tid
    if "maintenance_messages" not in st.session_state:
        st.session_state.maintenance_messages = []
    if "maintenance_auto_review" not in st.session_state:
        st.session_state.maintenance_auto_review = False
    if "maintenance_locked_tool" not in st.session_state:
        st.session_state.maintenance_locked_tool = None
    if "maintenance_current_state" not in st.session_state:
        st.session_state.maintenance_current_state = {
            "current_meal": None,
            "current_source": None,
            "diagnosis": [],
            "execution_log": [],
            "stage_history": [],
        }

    with st.sidebar:
        st.markdown("### 🔧 维修工控制面板")

        tool_names = _get_tool_names()
        selected_tool = st.selectbox(
            "工具链锁定",
            tool_names,
            index=0,
            key="maintenance_tool_lock",
        )
        if selected_tool == "自动":
            st.session_state.maintenance_locked_tool = None
        else:
            st.session_state.maintenance_locked_tool = selected_tool

        auto_review = st.toggle(
            "自动审查",
            value=st.session_state.maintenance_auto_review,
            key="maintenance_auto_review_toggle",
        )
        st.session_state.maintenance_auto_review = auto_review

        st.markdown("#### 快捷操作")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("📋 生成维修报告", key="btn_maint_report"):
                st.session_state.maintenance_messages.append(
                    {"role": "user", "content": "生成维修报告"}
                )
                st.rerun()
        with col2:
            if st.button("📊 生成对比报告", key="btn_comp_report"):
                st.session_state.maintenance_messages.append(
                    {"role": "user", "content": "生成对比报告"}
                )
                st.rerun()

    for msg in st.session_state.maintenance_messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    if prompt := st.chat_input("输入问题进行诊断...", key="maintenance_chat_input"):
        st.session_state.maintenance_messages.append(
            {"role": "user", "content": prompt}
        )
        with st.chat_message("user"):
            st.markdown(prompt)

        with st.chat_message("assistant"):  # noqa: SIM117
            with st.spinner("维修工思考中..."):
                try:
                    agent = _get_compiled_agent()
                    config = {
                        "configurable": {
                            "thread_id": st.session_state.maintenance_thread_id
                        }
                    }
                    current = st.session_state.maintenance_current_state
                    state = {
                        "messages": [{"role": "user", "content": prompt}],
                        "current_meal": current.get("current_meal"),
                        "current_source": current.get("current_source"),
                        "diagnosis": current.get("diagnosis", []),
                        "pending_action": None,
                        "approved": None,
                        "execution_log": current.get("execution_log", []),
                        "stage_history": current.get("stage_history", []),
                        "auto_review": st.session_state.maintenance_auto_review,
                        "locked_tool": st.session_state.maintenance_locked_tool,
                        "locked_tool_args": None,
                    }

                    result = agent.invoke(state, config=config)

                    if result.get("__interrupt__"):
                        for interrupt_info in result.get("__interrupt__", []):
                            payload = interrupt_info.value
                            if isinstance(payload, dict) and "question" in payload:
                                st.warning(f"⚠️ {payload['question']}")
                                tool_info = payload.get("tool_call", {})
                                if tool_info:
                                    st.info(
                                        f"工具: {tool_info.get('name')} | 参数: {tool_info.get('args', {})}"
                                    )
                                col_a, col_b = st.columns(2)
                                with col_a:
                                    if st.button("✅ 批准", key="approve_btn"):
                                        _resume_interrupt(agent, config, True, result)
                                        st.rerun()
                                with col_b:
                                    if st.button("❌ 拒绝", key="reject_btn"):
                                        _resume_interrupt(agent, config, False, result)
                                        st.rerun()
                    else:
                        response_text = _extract_response_text(result)
                        st.markdown(response_text)
                        st.session_state.maintenance_messages.append(
                            {"role": "assistant", "content": response_text}
                        )
                        for key in (
                            "current_meal",
                            "current_source",
                            "diagnosis",
                            "execution_log",
                            "stage_history",
                        ):
                            if key in result:
                                st.session_state.maintenance_current_state[key] = (
                                    result[key]
                                )
                        st.session_state.maintenance_locked_tool = None

                except Exception as e:
                    logger.error(f"Maintenance agent error: {e}")
                    st.error(f"维修工出错: {e}")

    current = st.session_state.maintenance_current_state
    col_log, col_hist = st.columns(2)
    with col_log:  # noqa: SIM117
        with st.expander("📋 执行日志", expanded=False):
            exec_log = current.get("execution_log", [])
            if exec_log:
                for entry in exec_log:
                    st.text(entry)
            else:
                st.text("暂无执行日志")
    with col_hist:  # noqa: SIM117
        with st.expander("📊 阶段历史", expanded=False):
            stage_history = current.get("stage_history", [])
            if stage_history:
                for i, step in enumerate(stage_history):
                    st.text(f"{i + 1}. {step}")
            else:
                st.text("暂无阶段历史")


def _resume_interrupt(agent, config, decision, result):
    """Resume an interrupted agent execution with a decision.

    Args:
        agent: The compiled agent graph.
        config: The thread config dict.
        decision: True to approve, False to reject.
        result: The previous result containing the interrupt.
    """
    from langgraph.types import Command

    agent.invoke(Command(resume=decision), config=config)


def _extract_response_text(result: dict) -> str:
    """Extract the assistant's text response from the graph result.

    Args:
        result: The graph execution result dict.

    Returns:
        The assistant's text content, or a default message.
    """
    from langchain_core.messages import AIMessage

    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "（维修工已完成操作，无文字回复）"
