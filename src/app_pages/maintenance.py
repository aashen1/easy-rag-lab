from __future__ import annotations

import json
from pathlib import Path

import streamlit as st
from loguru import logger

from src.app_pages.about import _render_mermaid


@st.cache_data
def _get_agent_graph_mermaid() -> str:
    from src.agent.graph import build_graph

    graph = build_graph()
    compiled = graph.compile()
    return compiled.get_graph().draw_mermaid()


def _get_tool_names() -> list[str]:
    from src.agent.graph import _get_tools

    tools = _get_tools()
    names = ["自动"] + [t.name for t in tools]
    return names


@st.cache_resource
def _get_compiled_agent():
    from langgraph.store.memory import InMemoryStore

    from src.agent.checkpoint import get_checkpointer_direct
    from src.agent.config import get_agent_default
    from src.agent.graph import compile_agent
    from src.agent.memory.experience_store import ExperienceStore

    store = InMemoryStore()
    persist_path = get_agent_default(
        "experience_persist_path", "data/agent_experience.json"
    )
    ExperienceStore(store, persist_path=persist_path)
    checkpointer = get_checkpointer_direct()
    return compile_agent(checkpointer=checkpointer, store=store)


def render_maintenance():
    st.subheader("🔧 RAG 维修工")

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
            "delete_count": 0,
        }
    if "maintenance_mode" not in st.session_state:
        st.session_state.maintenance_mode = "light"
    if "maintenance_interrupted" not in st.session_state:
        st.session_state.maintenance_interrupted = False
    if "maintenance_interrupt_payload" not in st.session_state:
        st.session_state.maintenance_interrupt_payload = None
    if "maintenance_thread_id" not in st.session_state:
        import uuid

        st.session_state.maintenance_thread_id = f"maintenance-{uuid.uuid4().hex[:8]}"

    with st.sidebar:
        st.markdown("### 🔧 维修工控制面板")

        st.session_state.maintenance_mode = st.selectbox(
            "模式",
            options=["light", "full"],
            format_func=lambda x: "轻量模式" if x == "light" else "全量模式",
            index=0 if st.session_state.maintenance_mode == "light" else 1,
        )

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

        if st.button("🗑️ 清空对话", key="btn_clear_chat"):
            st.session_state.maintenance_messages = []
            st.session_state.maintenance_current_state = {
                "current_meal": None,
                "current_source": None,
                "diagnosis": [],
                "execution_log": [],
                "stage_history": [],
                "delete_count": 0,
            }
            st.session_state.maintenance_interrupted = False
            st.session_state.maintenance_interrupt_payload = None
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

        with st.chat_message("assistant"), st.spinner("维修工思考中..."):
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
                    "delete_count": current.get("delete_count", 0),
                    "mode": st.session_state.maintenance_mode,
                }

                result = agent.invoke(state, config=config)

                if result.get("__interrupt__"):
                    st.session_state.maintenance_interrupted = True
                    for interrupt_info in result.get("__interrupt__", []):
                        payload = interrupt_info.value
                        if isinstance(payload, dict) and "question" in payload:
                            st.session_state.maintenance_interrupt_payload = payload
                            st.warning(f"⚠️ {payload['question']}")
                            tool_info = payload.get("tool_call", {})
                            if tool_info:
                                st.info(
                                    f"工具: {tool_info.get('name')} | 参数: {tool_info.get('args', {})}"
                                )
                            col_a, col_b = st.columns(2)
                            with col_a:
                                if st.button("✅ 批准", key="approve_btn"):
                                    _resume_interrupt(agent, True, config)
                            with col_b:
                                if st.button("❌ 拒绝", key="reject_btn"):
                                    _resume_interrupt(agent, False, config)
                else:
                    response_text = _extract_response_text(result)
                    st.markdown(response_text)
                    st.session_state.maintenance_messages.append(
                        {"role": "assistant", "content": response_text}
                    )
                    report_data = _try_extract_report(response_text)
                    if report_data:
                        st.session_state.maintenance_latest_report = report_data
                    for key in (
                        "current_meal",
                        "current_source",
                        "diagnosis",
                        "execution_log",
                        "stage_history",
                        "delete_count",
                    ):
                        if key in result:
                            st.session_state.maintenance_current_state[key] = result[
                                key
                            ]
                    st.session_state.maintenance_locked_tool = None

            except Exception as e:
                logger.error(f"Maintenance agent error: {e}")
                st.error(f"维修工出错: {e}")

    if (
        st.session_state.maintenance_interrupted
        and st.session_state.maintenance_interrupt_payload is not None
    ):
        payload = st.session_state.maintenance_interrupt_payload
        with st.chat_message("assistant"):
            st.warning(f"⚠️ {payload.get('question', '等待确认')}")
            tool_info = payload.get("tool_call", {})
            if tool_info:
                st.info(
                    f"工具: {tool_info.get('name')} | 参数: {tool_info.get('args', {})}"
                )
            col_a, col_b = st.columns(2)
            with col_a:
                if st.button("✅ 批准", key="approve_btn_persist"):
                    agent = _get_compiled_agent()
                    config = {
                        "configurable": {
                            "thread_id": st.session_state.maintenance_thread_id
                        }
                    }
                    _resume_interrupt(agent, True, config)
            with col_b:
                if st.button("❌ 拒绝", key="reject_btn_persist"):
                    agent = _get_compiled_agent()
                    config = {
                        "configurable": {
                            "thread_id": st.session_state.maintenance_thread_id
                        }
                    }
                    _resume_interrupt(agent, False, config)

    current = st.session_state.maintenance_current_state
    col_log, col_hist = st.columns(2)
    with col_log, st.expander("📋 执行日志", expanded=False):
        exec_log = current.get("execution_log", [])
        if exec_log:
            for entry in exec_log:
                st.text(entry)
        else:
            st.text("暂无执行日志")
    with col_hist, st.expander("📊 阶段历史", expanded=False):
        stage_history = current.get("stage_history", [])
        if stage_history:
            for i, step in enumerate(stage_history):
                st.text(f"{i + 1}. {step}")
        else:
            st.text("暂无阶段历史")

    latest_report = st.session_state.get("maintenance_latest_report")
    if latest_report:
        with st.expander("📄 维修报告", expanded=True):
            st.markdown(latest_report["report_content"])
            report_path = latest_report.get("report_path", "report.md")
            filename = Path(report_path).name if report_path else "report.md"
            st.download_button(
                "⬇️ 下载报告",
                data=latest_report["report_content"],
                file_name=filename,
                mime="text/markdown",
                key="download_maintenance_report",
            )

    st.markdown("---")
    st.markdown("### 🗺️ 维修工架构图")
    st.caption("由 LangGraph 自动生成，修改 graph.py 后重启应用即可更新")
    try:
        mermaid_chart = _get_agent_graph_mermaid()
        _render_mermaid(mermaid_chart, key="agent_graph")
    except Exception as e:
        logger.warning(f"Failed to render agent graph: {e}")
        st.info("架构图渲染失败，请检查 LangGraph 依赖是否完整")


def _resume_interrupt(agent, decision, config):
    from langgraph.types import Command

    try:
        result = agent.invoke(Command(resume=decision), config=config)
        st.session_state.maintenance_interrupted = False
        st.session_state.maintenance_interrupt_payload = None
        if result and not result.get("__interrupt__"):
            response_text = _extract_response_text(result)
            st.session_state.maintenance_messages.append(
                {"role": "assistant", "content": response_text}
            )
            for key in (
                "current_meal",
                "current_source",
                "diagnosis",
                "execution_log",
                "stage_history",
                "delete_count",
            ):
                if key in result:
                    st.session_state.maintenance_current_state[key] = result[key]
            st.session_state.maintenance_locked_tool = None
        st.rerun()
    except Exception as e:
        logger.error(f"Resume interrupt error: {e}")
        st.session_state.maintenance_interrupted = False
        st.session_state.maintenance_interrupt_payload = None
        st.error(f"恢复中断出错: {e}")
        st.rerun()


def _extract_response_text(result: dict) -> str:
    from langchain_core.messages import AIMessage

    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return msg.content
    return "（维修工已完成操作，无文字回复）"


def _try_extract_report(text: str) -> dict | None:
    try:
        data = json.loads(text)
        if (
            isinstance(data, dict)
            and "report_path" in data
            and "report_content" in data
        ):
            return data
    except (json.JSONDecodeError, TypeError):
        pass
    return None
