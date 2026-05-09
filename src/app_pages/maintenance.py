from __future__ import annotations

import json
from pathlib import Path
from typing import Any

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
    import sqlite3

    from langgraph.checkpoint.sqlite import SqliteSaver
    from langgraph.store.sqlite import SqliteStore

    from src.agent.config import get_checkpoint_config
    from src.agent.graph import compile_agent
    from src.agent.memory.experience_store import ExperienceStore

    ckpt_config = get_checkpoint_config()
    db_path = ckpt_config.get("db_path", "data/agent_checkpoints.db")

    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.execute("PRAGMA journal_mode=WAL")
    conn.autocommit = True

    checkpointer = SqliteSaver(conn)
    store = SqliteStore(conn)
    store.setup()

    ExperienceStore._migrate_from_json(store, "data/agent_experience.json")

    from src.agent.tools import save_experience_tool

    save_experience_tool._store = store

    return compile_agent(checkpointer=checkpointer, store=store)


@st.cache_resource
def _get_session_manager():
    from src.agent.checkpoint import get_session_manager

    return get_session_manager()


_TOOL_DISPLAY_NAMES = {
    "list_meals": "📋 列出 Meals",
    "get_meal_detail": "📊 查看 Meal 详情",
    "query_rag_tool": "🔍 测试 RAG 查询",
    "get_index_info": "📈 查看索引信息",
    "evaluate_answer_tool": "📝 评估答案质量",
    "list_pdfs": "📄 列出 PDF 文件",
    "list_issues": "🚨 列出问题",
    "parse_pdf_tool": "📑 解析 PDF",
    "enhance_page_tool": "✨ 增强页面",
    "chunk_parsed_tool": "✂️ 分块",
    "embed_chunks_tool": "🔢 向量化",
    "index_chunks_tool": "🗂️ 索引构建",
    "delete_and_reindex_tool": "🗑️ 删除并重建索引",
    "create_curated_meal": "🍱 创建精选 Meal",
    "rebuild_index": "🔨 重建索引",
    "delete_source": "🗑️ 删除数据源",
    "update_meal": "🔄 更新 Meal",
    "create_issue": "📝 创建 Issue",
    "close_issue": "✅ 关闭 Issue",
    "generate_maintenance_report_tool": "📋 生成维修报告",
    "generate_comparison_report_tool": "📊 生成对比报告",
}


def _format_tool_name(tool_name: str) -> str:
    return _TOOL_DISPLAY_NAMES.get(tool_name, f"🔧 {tool_name}")


def _extract_text_from_content(content: str | list) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                parts.append(item.get("text", ""))
            elif isinstance(item, str):
                parts.append(item)
        return "\n".join(parts)
    return str(content)


def _initialize_session():
    session_mgr = _get_session_manager()
    sessions = session_mgr.list_sessions()
    if sessions:
        sess = sessions[0]
        st.session_state.maintenance_session_id = sess["session_id"]
        st.session_state.maintenance_thread_id = sess["thread_id"]
    else:
        sess = session_mgr.create_session()
        st.session_state.maintenance_session_id = sess["session_id"]
        st.session_state.maintenance_thread_id = sess["thread_id"]


def _switch_to_session(session_id: str):
    from langchain_core.messages import AIMessage, HumanMessage

    session_mgr = _get_session_manager()
    sess = session_mgr.get_session(session_id)
    if sess is None:
        logger.warning(f"Session {session_id} not found")
        return

    st.session_state.maintenance_session_id = sess["session_id"]
    st.session_state.maintenance_thread_id = sess["thread_id"]

    try:
        agent = _get_compiled_agent()
        config = {"configurable": {"thread_id": sess["thread_id"]}}
        graph_state = agent.get_state(config)

        if graph_state and graph_state.values:
            messages = graph_state.values.get("messages", [])
            ui_messages = []
            for msg in messages:
                if isinstance(msg, HumanMessage):
                    ui_messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage) and msg.content:
                    ui_messages.append(
                        {
                            "role": "assistant",
                            "content": _extract_text_from_content(msg.content),
                            "thinking_parts": [],
                            "thinking_expanded": False,
                        }
                    )
            st.session_state.maintenance_messages = ui_messages

            for key in (
                "current_meal",
                "current_source",
                "diagnosis",
                "execution_log",
                "stage_history",
                "delete_count",
            ):
                if key in graph_state.values:
                    st.session_state.maintenance_current_state[key] = (
                        graph_state.values[key]
                    )

            if graph_state.values.get("__interrupt__"):
                for interrupt_info in graph_state.values.get("__interrupt__", []):
                    payload = interrupt_info.value
                    if isinstance(payload, dict) and "question" in payload:
                        st.session_state.maintenance_interrupted = True
                        st.session_state.maintenance_interrupt_payload = payload
                        break
            else:
                st.session_state.maintenance_interrupted = False
                st.session_state.maintenance_interrupt_payload = None
        else:
            st.session_state.maintenance_messages = []
            st.session_state.maintenance_interrupted = False
            st.session_state.maintenance_interrupt_payload = None
    except Exception as e:
        logger.warning(f"Failed to rebuild messages from checkpoint: {e}")
        st.session_state.maintenance_messages = []

    session_mgr.touch_session(session_id)


def _resend_from_message(editing_idx: int, new_content: str):
    from langchain_core.messages import HumanMessage

    st.session_state.maintenance_editing_msg_idx = None

    try:
        agent = _get_compiled_agent()
        thread_id = st.session_state.maintenance_thread_id
        config = {"configurable": {"thread_id": thread_id}}

        history = list(agent.get_state_history(config))
        user_msg_count = 0
        for snap in history:
            msgs = snap.values.get("messages", [])
            for msg in msgs:
                if isinstance(msg, HumanMessage):
                    user_msg_count += 1

        st.session_state.maintenance_messages = st.session_state.maintenance_messages[
            :editing_idx
        ]
        st.session_state.maintenance_messages.append(
            {"role": "user", "content": new_content}
        )

        state = {
            "messages": [{"role": "user", "content": new_content}],
            "current_meal": st.session_state.maintenance_current_state.get(
                "current_meal"
            ),
            "current_source": st.session_state.maintenance_current_state.get(
                "current_source"
            ),
            "diagnosis": st.session_state.maintenance_current_state.get(
                "diagnosis", []
            ),
            "pending_action": None,
            "approved": None,
            "execution_log": st.session_state.maintenance_current_state.get(
                "execution_log", []
            ),
            "stage_history": st.session_state.maintenance_current_state.get(
                "stage_history", []
            ),
            "auto_review": st.session_state.maintenance_auto_review,
            "locked_tool": None,
            "locked_tool_args": None,
            "delete_count": st.session_state.maintenance_current_state.get(
                "delete_count", 0
            ),
            "mode": st.session_state.maintenance_mode,
        }

        with st.chat_message("assistant"):
            _render_streaming_agent(agent, state, config)

    except Exception as e:
        logger.error(f"Resend from message error: {e}")
        st.session_state.maintenance_streaming = False
        st.error(f"重发出错: {e}")
        st.rerun()


def _render_streaming_agent(agent, state: dict, config: dict) -> dict | None:
    from langchain_core.messages import AIMessage, ToolMessage

    collapse = st.session_state.get("maintenance_collapse_thinking", True)
    st.session_state.maintenance_streaming = True
    st.session_state.maintenance_thinking_parts = []
    thinking_parts = st.session_state.maintenance_thinking_parts
    final_result: dict | None = None
    interrupt_payload = None

    thinking_container = st.container()

    for event in agent.stream(state, config=config, stream_mode="updates"):
        for node_name, node_output in event.items():
            if node_name == "agent":
                messages = node_output.get("messages", [])
                for msg in messages:
                    if isinstance(msg, AIMessage):
                        if msg.content and msg.tool_calls:
                            text = _extract_text_from_content(msg.content)
                            if text:
                                thinking_parts.append(
                                    {"type": "thinking", "content": text}
                                )
                        if hasattr(msg, "tool_calls") and msg.tool_calls:
                            for tc in msg.tool_calls:
                                thinking_parts.append(
                                    {
                                        "type": "tool_call",
                                        "tool": tc["name"],
                                        "args": tc.get("args", {}),
                                    }
                                )

            elif node_name == "tools":
                messages = node_output.get("messages", [])
                for msg in messages:
                    if isinstance(msg, ToolMessage):
                        content_preview = str(msg.content)[:300]
                        thinking_parts.append(
                            {
                                "type": "tool_result",
                                "tool_id": msg.tool_call_id,
                                "content": content_preview,
                            }
                        )
                for key in (
                    "execution_log",
                    "stage_history",
                ):
                    if key in node_output:
                        st.session_state.maintenance_current_state[key] = node_output[
                            key
                        ]
                if "delete_count" in node_output:
                    st.session_state.maintenance_current_state["delete_count"] = (
                        node_output["delete_count"]
                    )

            elif node_name == "approval":
                pass

        with thinking_container:
            thinking_container.empty()
            if thinking_parts:
                if collapse:
                    with st.expander(
                        f"💭 思考与工具调用过程 ({len(thinking_parts)} 步)",
                        expanded=False,
                    ):
                        _render_thinking_parts(thinking_parts)
                else:
                    _render_thinking_parts(thinking_parts)

    try:
        graph_state = agent.get_state(config)
        final_result = graph_state.values if graph_state else None
    except Exception:
        final_result = None

    if final_result is not None:
        if final_result.get("__interrupt__"):
            for interrupt_info in final_result.get("__interrupt__", []):
                payload = interrupt_info.value
                if isinstance(payload, dict) and "question" in payload:
                    interrupt_payload = payload
        else:
            response_text = _extract_response_text(final_result)
            if response_text:
                st.markdown("---")
                st.markdown(response_text)
                st.session_state.maintenance_messages.append(
                    {
                        "role": "assistant",
                        "content": response_text,
                        "thinking_parts": list(
                            st.session_state.maintenance_thinking_parts
                        ),
                        "thinking_expanded": not collapse,
                    }
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
                if key in final_result:
                    st.session_state.maintenance_current_state[key] = final_result[key]
            st.session_state.maintenance_locked_tool = None

    st.session_state.maintenance_streaming = False

    if interrupt_payload is not None:
        st.session_state.maintenance_interrupted = True
        st.session_state.maintenance_interrupt_payload = interrupt_payload

    st.rerun()


def _render_thinking_parts(parts: list[dict[str, Any]]) -> None:
    for part in parts:
        if part["type"] == "thinking":
            st.markdown(f"**💭 思考：** {part['content']}")
        elif part["type"] == "tool_call":
            tool_display = _format_tool_name(part["tool"])
            args_display = ""
            if part.get("args"):
                args_str = json.dumps(part["args"], ensure_ascii=False)
                if len(args_str) > 200:
                    args_str = args_str[:200] + "..."
                args_display = f" | 参数: `{args_str}`"
            st.markdown(f"**{tool_display}**{args_display}")
        elif part["type"] == "tool_result":
            content = part.get("content", "")
            st.markdown(
                f"<div style='background:#3d3d3d;padding:6px 10px;border-radius:4px;"
                f"font-size:0.85em;margin:2px 0;'>↳ {content}</div>",
                unsafe_allow_html=True,
            )


def _on_chat_submit():
    st.session_state.maintenance_pending_prompt = (
        st.session_state.maintenance_chat_input
    )
    st.session_state.maintenance_streaming = True


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
    if "maintenance_session_id" not in st.session_state:
        st.session_state.maintenance_session_id = None
    if "maintenance_editing_msg_idx" not in st.session_state:
        st.session_state.maintenance_editing_msg_idx = None
    if "maintenance_show_archived" not in st.session_state:
        st.session_state.maintenance_show_archived = False
    if (
        "maintenance_thread_id" not in st.session_state
        or st.session_state.maintenance_session_id is None
    ):
        _initialize_session()
    if "maintenance_collapse_thinking" not in st.session_state:
        st.session_state.maintenance_collapse_thinking = True
    if "maintenance_thinking_parts" not in st.session_state:
        st.session_state.maintenance_thinking_parts = []
    if "maintenance_streaming" not in st.session_state:
        st.session_state.maintenance_streaming = False
    if "maintenance_pending_prompt" not in st.session_state:
        st.session_state.maintenance_pending_prompt = None
    if "maintenance_scan_pending" not in st.session_state:
        st.session_state.maintenance_scan_pending = False
    if "maintenance_scan_candidates" not in st.session_state:
        st.session_state.maintenance_scan_candidates = []

    is_streaming = st.session_state.get("maintenance_streaming", False)

    if not st.session_state.maintenance_interrupted:
        try:
            agent = _get_compiled_agent()
            config = {
                "configurable": {"thread_id": st.session_state.maintenance_thread_id}
            }
            graph_state = agent.get_state(config)
            if (
                graph_state
                and graph_state.values
                and graph_state.values.get("__interrupt__")
            ):
                for interrupt_info in graph_state.values.get("__interrupt__", []):
                    payload = interrupt_info.value
                    if isinstance(payload, dict) and "question" in payload:
                        st.session_state.maintenance_interrupted = True
                        st.session_state.maintenance_interrupt_payload = payload
                        for key in (
                            "current_meal",
                            "current_source",
                            "diagnosis",
                            "execution_log",
                            "stage_history",
                            "delete_count",
                        ):
                            if key in graph_state.values:
                                st.session_state.maintenance_current_state[key] = (
                                    graph_state.values[key]
                                )
                        break
        except Exception as e:
            logger.warning(f"Failed to restore interrupt state from checkpointer: {e}")

    with st.sidebar:
        st.markdown("### 💬 对话历史")

        if st.button(
            "➕ 新对话",
            key="btn_new_session",
            use_container_width=True,
            disabled=is_streaming,
        ):
            session_mgr = _get_session_manager()
            new_sess = session_mgr.create_session()
            _switch_to_session(new_sess["session_id"])
            st.rerun()

        session_mgr = _get_session_manager()
        sessions = session_mgr.list_sessions(
            include_archived=st.session_state.maintenance_show_archived
        )

        for sess in sessions:
            is_current = sess["session_id"] == st.session_state.maintenance_session_id
            col_title, col_menu = st.columns([5, 1])
            with col_title:
                label = f"{'▶ ' if is_current else ''}{sess['title']}"
                btn_type = "primary" if is_current else "secondary"
                if (
                    st.button(
                        label,
                        key=f"sess_{sess['session_id']}",
                        type=btn_type,
                        use_container_width=True,
                        disabled=is_streaming,
                    )
                    and not is_current
                ):
                    _switch_to_session(sess["session_id"])
                    st.rerun()
            with col_menu:
                menu = st.popover("⋯", key=f"menu_{sess['session_id']}")
                if menu.button(
                    "📋 复制",
                    key=f"dup_{sess['session_id']}",
                    disabled=is_streaming,
                ):
                    new_sess = session_mgr.duplicate_session(sess["session_id"])
                    if new_sess:
                        _switch_to_session(new_sess["session_id"])
                        st.rerun()
                if sess["is_archived"]:
                    if menu.button(
                        "📤 取消归档",
                        key=f"unarch_{sess['session_id']}",
                        disabled=is_streaming,
                    ):
                        session_mgr.unarchive_session(sess["session_id"])
                        st.rerun()
                else:
                    if menu.button(
                        "📦 归档",
                        key=f"arch_{sess['session_id']}",
                        disabled=is_streaming,
                    ):
                        session_mgr.archive_session(sess["session_id"])
                        st.rerun()
                if menu.button(
                    "✏️ 改标题",
                    key=f"rename_{sess['session_id']}",
                    disabled=is_streaming,
                ):
                    st.session_state.maintenance_editing_session_id = sess["session_id"]
                    st.rerun()

        show_archived = st.toggle(
            "显示已归档",
            value=st.session_state.maintenance_show_archived,
            key="maintenance_show_archived_toggle",
            disabled=is_streaming,
        )
        st.session_state.maintenance_show_archived = show_archived

        editing_sess_id = st.session_state.get("maintenance_editing_session_id")
        if editing_sess_id:
            sess = session_mgr.get_session(editing_sess_id)
            if sess:
                new_title = st.text_input(
                    "新标题",
                    value=sess["title"],
                    key=f"rename_input_{editing_sess_id}",
                )
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("💾 保存", key=f"save_title_{editing_sess_id}"):
                        session_mgr.update_session(editing_sess_id, title=new_title)
                        st.session_state.maintenance_editing_session_id = None
                        st.rerun()
                with col_cancel:
                    if st.button("取消", key=f"cancel_title_{editing_sess_id}"):
                        st.session_state.maintenance_editing_session_id = None
                        st.rerun()

        st.markdown("---")
        st.markdown("### 🔧 维修工控制面板")

        if is_streaming:
            st.caption("⏳ Agent 正在思考中，控件暂时禁用...")

        st.session_state.maintenance_mode = st.selectbox(
            "模式",
            options=["light", "full"],
            format_func=lambda x: "轻量模式" if x == "light" else "全量模式",
            index=0 if st.session_state.maintenance_mode == "light" else 1,
            disabled=is_streaming,
        )

        tool_names = _get_tool_names()
        selected_tool = st.selectbox(
            "工具链锁定",
            tool_names,
            index=0,
            key="maintenance_tool_lock",
            disabled=is_streaming,
        )
        if selected_tool == "自动":
            st.session_state.maintenance_locked_tool = None
        else:
            st.session_state.maintenance_locked_tool = selected_tool

        auto_review = st.toggle(
            "自动审查",
            value=st.session_state.maintenance_auto_review,
            key="maintenance_auto_review_toggle",
            disabled=is_streaming,
        )
        st.session_state.maintenance_auto_review = auto_review

        collapse_thinking = st.toggle(
            "折叠思考过程",
            value=st.session_state.maintenance_collapse_thinking,
            key="maintenance_collapse_toggle",
            disabled=is_streaming,
        )
        st.session_state.maintenance_collapse_thinking = collapse_thinking

        col_expand, col_collapse = st.columns(2)
        with col_expand:
            if st.button(
                "📂 展开所有", key="btn_expand_all_thinking", disabled=is_streaming
            ):
                for msg in st.session_state.maintenance_messages:
                    if msg["role"] == "assistant" and msg.get("thinking_parts"):
                        msg["thinking_expanded"] = True
                keys_to_clear = [
                    k for k in st.session_state if k.startswith("thinking_expander_")
                ]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.rerun()
        with col_collapse:
            if st.button(
                "📁 折叠所有", key="btn_collapse_all_thinking", disabled=is_streaming
            ):
                for msg in st.session_state.maintenance_messages:
                    if msg["role"] == "assistant" and msg.get("thinking_parts"):
                        msg["thinking_expanded"] = False
                keys_to_clear = [
                    k for k in st.session_state if k.startswith("thinking_expander_")
                ]
                for k in keys_to_clear:
                    del st.session_state[k]
                st.rerun()

        st.markdown("#### 快捷操作")
        col1, col2 = st.columns(2)
        with col1:
            if st.button(
                "📋 生成维修报告", key="btn_maint_report", disabled=is_streaming
            ):
                st.session_state.maintenance_messages.append(
                    {"role": "user", "content": "生成维修报告"}
                )
                st.rerun()
        with col2:
            if st.button(
                "📊 生成对比报告", key="btn_comp_report", disabled=is_streaming
            ):
                st.session_state.maintenance_messages.append(
                    {"role": "user", "content": "生成对比报告"}
                )
                st.rerun()

        if st.button("🗑️ 清空对话", key="btn_clear_chat", disabled=is_streaming):
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

        st.markdown("---")
        st.markdown("### 🧠 经验库")

        if st.button("🔍 扫描经验", key="btn_scan_experience", disabled=is_streaming):
            st.session_state.maintenance_scan_pending = True
            st.rerun()

        try:
            from src.agent.memory.experience_store import ExperienceStore

            agent = _get_compiled_agent()
            if hasattr(agent, "store") and agent.store is not None:
                exp_store = ExperienceStore(agent.store)
                experiences = exp_store.list_experiences(limit=20)
                for exp in experiences:
                    value = exp.get("value", exp)
                    summary = value.get("summary", "未知经验")
                    category = value.get("category", "")
                    details = value.get("details", "")
                    namespace = exp.get("namespace", ())
                    key = exp.get("key", "")
                    with st.expander(f"💡 {summary}", expanded=False):
                        st.markdown(f"**类别**: {category}")
                        st.markdown(details)
                        if (
                            st.button("🗑️ 删除", key=f"del_exp_{key}")
                            and namespace
                            and key
                        ):
                            exp_store.delete_experience(
                                tuple(namespace)
                                if isinstance(namespace, list)
                                else namespace,
                                key,
                            )
                            st.rerun()
        except Exception as e:
            logger.warning(f"Failed to render experience list: {e}")

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

    editing_idx = st.session_state.get("maintenance_editing_msg_idx")

    for i, msg in enumerate(st.session_state.maintenance_messages):
        if editing_idx is not None and editing_idx == i:
            with st.chat_message(msg["role"]):
                new_content = st.text_area(
                    "编辑消息", value=msg["content"], key=f"edit_area_{i}"
                )
                col_save, col_cancel = st.columns(2)
                with col_save:
                    if st.button("🔄 重发", key=f"resend_msg_{i}"):
                        _resend_from_message(i, new_content)
                with col_cancel:
                    if st.button("取消", key=f"cancel_edit_{i}"):
                        st.session_state.maintenance_editing_msg_idx = None
                        st.rerun()
            continue

        with st.chat_message(msg["role"]):
            if msg["role"] == "user":
                col_content, col_edit = st.columns([6, 1])
                with col_content:
                    st.markdown(msg["content"])
                with col_edit:
                    if st.button("✏️", key=f"edit_msg_{i}", disabled=is_streaming):
                        st.session_state.maintenance_editing_msg_idx = i
                        st.rerun()
            elif msg["role"] == "assistant" and msg.get("thinking_parts"):
                expanded = msg.get("thinking_expanded", True)
                with st.expander(
                    f"💭 思考与工具调用过程 ({len(msg['thinking_parts'])} 步)",
                    expanded=expanded,
                    key=f"thinking_expander_{i}",
                ):
                    _render_thinking_parts(msg["thinking_parts"])
                st.markdown(msg["content"])
            else:
                st.markdown(msg["content"])

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
                    _resume_interrupt_streaming(agent, True, config)
            with col_b:
                if st.button("❌ 拒绝", key="reject_btn_persist"):
                    agent = _get_compiled_agent()
                    config = {
                        "configurable": {
                            "thread_id": st.session_state.maintenance_thread_id
                        }
                    }
                    _resume_interrupt_streaming(agent, False, config)

    if st.session_state.get("maintenance_scan_pending"):
        st.session_state.maintenance_scan_pending = False
        try:
            agent = _get_compiled_agent()
            from src.agent.config import get_experience_config

            exp_config = get_experience_config()
            max_candidates = exp_config.get("scan_max_candidates", 5)

            scan_prompt = (
                f"请扫描以下对话，提取可能有价值的维修经验。每条经验包含 summary、category、details。"
                f"只提取真正有价值的技巧性知识，不要提取临时性信息。最多提取 {max_candidates} 条。"
                f'请用 JSON 数组格式返回，每条格式为: {{"summary": "...", "category": "...", "details": "..."}}'
            )

            messages_text = []
            for msg in st.session_state.maintenance_messages:
                role = msg["role"]
                content = msg.get("content", "")
                messages_text.append(f"{role}: {content}")

            scan_input = scan_prompt + "\n\n对话内容:\n" + "\n".join(messages_text)

            config = {
                "configurable": {"thread_id": st.session_state.maintenance_thread_id}
            }
            state = {
                "messages": [{"role": "user", "content": scan_input}],
                "current_meal": st.session_state.maintenance_current_state.get(
                    "current_meal"
                ),
                "current_source": st.session_state.maintenance_current_state.get(
                    "current_source"
                ),
                "diagnosis": st.session_state.maintenance_current_state.get(
                    "diagnosis", []
                ),
                "pending_action": None,
                "approved": None,
                "execution_log": st.session_state.maintenance_current_state.get(
                    "execution_log", []
                ),
                "stage_history": st.session_state.maintenance_current_state.get(
                    "stage_history", []
                ),
                "auto_review": False,
                "locked_tool": None,
                "locked_tool_args": None,
                "delete_count": st.session_state.maintenance_current_state.get(
                    "delete_count", 0
                ),
                "mode": st.session_state.maintenance_mode,
            }

            with st.spinner("🔍 正在扫描经验..."):
                result = agent.invoke(state, config)

            response_text = ""
            if result and "messages" in result:
                from langchain_core.messages import AIMessage

                for msg in reversed(result["messages"]):
                    if isinstance(msg, AIMessage) and msg.content:
                        response_text = _extract_text_from_content(msg.content)
                        break

            import re

            json_match = re.search(r"\[.*\]", response_text, re.DOTALL)
            if json_match:
                candidates = json.loads(json_match.group())
                st.session_state.maintenance_scan_candidates = candidates
            else:
                st.session_state.maintenance_scan_candidates = []
                st.info("未发现可提取的经验")

        except Exception as e:
            logger.error(f"Experience scan error: {e}")
            st.error(f"扫描经验出错: {e}")
            st.session_state.maintenance_scan_candidates = []

    scan_candidates = st.session_state.get("maintenance_scan_candidates", [])
    if scan_candidates:
        st.markdown("### 🔍 候选经验")
        confirmed = []
        for idx, cand in enumerate(scan_candidates):
            col_info, col_action = st.columns([4, 1])
            with col_info:
                st.markdown(
                    f"**{cand.get('summary', '')}** ({cand.get('category', '')})"
                )
                st.caption(cand.get("details", "")[:200])
            with col_action:
                if st.button("✅", key=f"confirm_exp_{idx}"):
                    confirmed.append(cand)
                if st.button("❌", key=f"reject_exp_{idx}"):
                    scan_candidates.pop(idx)
                    st.session_state.maintenance_scan_candidates = scan_candidates
                    st.rerun()

        for cand in confirmed:
            try:
                from src.agent.memory.experience_store import ExperienceStore

                agent = _get_compiled_agent()
                if hasattr(agent, "store") and agent.store is not None:
                    exp_store = ExperienceStore(agent.store)
                    exp_store.save_experience(
                        summary=cand.get("summary", ""),
                        category=cand.get("category", "other"),
                        details=cand.get("details", ""),
                        session_id=st.session_state.maintenance_session_id,
                    )
                    scan_candidates.remove(cand)
                    st.session_state.maintenance_scan_candidates = scan_candidates
                    st.rerun()
            except Exception as e:
                logger.error(f"Failed to save confirmed experience: {e}")

        if st.button("清除候选", key="btn_clear_candidates"):
            st.session_state.maintenance_scan_candidates = []
            st.rerun()

    pending = st.session_state.pop("maintenance_pending_prompt", None)
    if pending:
        st.session_state.maintenance_messages.append(
            {"role": "user", "content": pending}
        )

        session_mgr = _get_session_manager()
        sess = session_mgr.get_session(st.session_state.maintenance_session_id)
        if sess and sess["title"] == "新对话" and sess["message_count"] == 0:
            session_mgr.auto_title(st.session_state.maintenance_session_id, pending)
        session_mgr.touch_session(st.session_state.maintenance_session_id)

        with st.chat_message("user"):
            st.markdown(pending)

        with st.chat_message("assistant"):
            try:
                agent = _get_compiled_agent()
                config = {
                    "configurable": {
                        "thread_id": st.session_state.maintenance_thread_id
                    }
                }
                current = st.session_state.maintenance_current_state
                state = {
                    "messages": [{"role": "user", "content": pending}],
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

                from src.agent.tools import save_experience_tool

                save_experience_tool._session_id = (
                    st.session_state.maintenance_session_id
                )
                save_experience_tool._source_path = (
                    st.session_state.maintenance_current_state.get("current_source")
                )
                from src.agent.graph import _infer_pdf_type

                current_source = st.session_state.maintenance_current_state.get(
                    "current_source"
                )
                save_experience_tool._pdf_type = (
                    _infer_pdf_type(current_source) if current_source else None
                )

                _render_streaming_agent(agent, state, config)

            except Exception as e:
                logger.error(f"Maintenance agent error: {e}")
                st.session_state.maintenance_streaming = False
                st.error(f"维修工出错: {e}")

    st.chat_input(
        "输入问题进行诊断...",
        key="maintenance_chat_input",
        on_submit=_on_chat_submit,
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


def _resume_interrupt_streaming(agent, decision, config):
    from langchain_core.messages import AIMessage
    from langgraph.types import Command

    collapse = st.session_state.get("maintenance_collapse_thinking", True)
    st.session_state.maintenance_streaming = True
    st.session_state.maintenance_thinking_parts = []
    thinking_parts = st.session_state.maintenance_thinking_parts

    try:
        for event in agent.stream(
            Command(resume=decision), config=config, stream_mode="updates"
        ):
            for node_name, node_output in event.items():
                if node_name == "agent":
                    messages = node_output.get("messages", [])
                    for msg in messages:
                        if isinstance(msg, AIMessage):
                            if msg.content and msg.tool_calls:
                                text = _extract_text_from_content(msg.content)
                                if text:
                                    thinking_parts.append(
                                        {"type": "thinking", "content": text}
                                    )
                            if hasattr(msg, "tool_calls") and msg.tool_calls:
                                for tc in msg.tool_calls:
                                    thinking_parts.append(
                                        {
                                            "type": "tool_call",
                                            "tool": tc["name"],
                                            "args": tc.get("args", {}),
                                        }
                                    )
                elif node_name == "tools":
                    from langchain_core.messages import ToolMessage

                    messages = node_output.get("messages", [])
                    for msg in messages:
                        if isinstance(msg, ToolMessage):
                            content_preview = str(msg.content)[:300]
                            thinking_parts.append(
                                {
                                    "type": "tool_result",
                                    "tool_id": msg.tool_call_id,
                                    "content": content_preview,
                                }
                            )
                    for key in ("execution_log", "stage_history"):
                        if key in node_output:
                            st.session_state.maintenance_current_state[key] = (
                                node_output[key]
                            )
                    if "delete_count" in node_output:
                        st.session_state.maintenance_current_state["delete_count"] = (
                            node_output["delete_count"]
                        )

        result = agent.get_state(config)
        final_values = result.values if result else {}

        st.session_state.maintenance_interrupted = False
        st.session_state.maintenance_interrupt_payload = None

        if final_values and not final_values.get("__interrupt__"):
            response_text = _extract_response_text(final_values)
            if response_text:
                st.session_state.maintenance_messages.append(
                    {
                        "role": "assistant",
                        "content": response_text,
                        "thinking_parts": list(
                            st.session_state.maintenance_thinking_parts
                        ),
                        "thinking_expanded": not collapse,
                    }
                )
            for key in (
                "current_meal",
                "current_source",
                "diagnosis",
                "execution_log",
                "stage_history",
                "delete_count",
            ):
                if key in final_values:
                    st.session_state.maintenance_current_state[key] = final_values[key]
            st.session_state.maintenance_locked_tool = None
        st.session_state.maintenance_streaming = False
        st.rerun()
    except Exception as e:
        logger.error(f"Resume interrupt error: {e}")
        st.session_state.maintenance_interrupted = False
        st.session_state.maintenance_interrupt_payload = None
        st.session_state.maintenance_streaming = False
        st.error(f"恢复中断出错: {e}")
        st.rerun()


def _extract_response_text(result: dict) -> str:
    from langchain_core.messages import AIMessage

    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            return _extract_text_from_content(msg.content)
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
