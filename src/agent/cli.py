from __future__ import annotations

import argparse
import contextlib
import sqlite3
import sys
from typing import Any

from langchain_core.messages import AIMessage
from langgraph.store.sqlite import SqliteStore
from langgraph.types import Command
from loguru import logger

from src.agent.state_utils import build_agent_state, build_initial_state


def _sanitize_text(text: str) -> str:
    try:
        text.encode("utf-8", errors="strict")
        return text
    except UnicodeEncodeError:
        return text.encode("utf-8", errors="surrogatepass").decode(
            "utf-8", errors="replace"
        )


def _format_agent_response(result: dict) -> None:
    """Print the agent's final response and execution log to the console.

    Args:
        result: The final graph execution result dict.
    """
    messages = result.get("messages", [])
    for msg in reversed(messages):
        if isinstance(msg, AIMessage) and msg.content:
            print(f"\n🤖 维修工: {msg.content}")
            break

    exec_log = result.get("execution_log", [])
    if exec_log:
        print(f"\n📋 执行日志: {len(exec_log)} 条记录")
        for entry in exec_log[-5:]:
            print(f"   - {entry}")


def _parse_cli_args(argv: list[str] | None = None) -> argparse.Namespace:
    """Parse CLI arguments for the maintenance agent.

    Args:
        argv: Optional argument list (defaults to sys.argv[1:]).

    Returns:
        Parsed namespace with session_id and pdf attributes.
    """
    parser = argparse.ArgumentParser(description="RAG 维修工 Agent")
    parser.add_argument(
        "--session-id",
        default=None,
        help="恢复历史会话的 thread_id（默认从 config 读取）",
    )
    parser.add_argument(
        "--pdf",
        default=None,
        help="指定目标 PDF 路径，注入到会话的 current_source",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        default=False,
        help="启用全量模式（默认为轻量模式）",
    )
    parser.add_argument(
        "--list-sessions",
        action="store_true",
        default=False,
        help="列出历史会话",
    )
    parser.add_argument(
        "--new-session",
        default=None,
        help="新建会话并指定标题",
    )
    return parser.parse_args(argv)


def _handle_cli_command(user_input: str, auto_review: bool) -> str | None:
    """Handle special CLI commands that start with ':'.

    Returns the translated natural language message, or None if the
    input is not a recognized command (meaning it should be treated as
    regular user input).

    Args:
        user_input: The raw user input string.
        auto_review: Current auto_review state (for :status display).

    Returns:
        Translated message string, or None if not a CLI command.
    """
    if not user_input.startswith(":"):
        return None

    parts = user_input.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    command_map = {
        ":parse": f"请用 {arg} 解析当前 PDF" if arg else "请解析当前 PDF",
        ":back": f"回到{arg}阶段重新做" if arg else "回到上一步重新做",
        ":compare": "生成对比报告",
        ":report": "生成维修报告",
    }

    if cmd in command_map:
        return command_map[cmd]

    if cmd == ":history":
        return "__show_history__"
    if cmd == ":status":
        return "__show_status__"
    if cmd == ":mode":
        return "__set_mode__"
    if cmd == ":sessions":
        return "__list_sessions__"
    if cmd == ":switch":
        return f"__switch_session__{arg}"
    if cmd == ":new":
        return f"__new_session__{arg}"
    if cmd == ":copy":
        return f"__copy_session__{arg}"

    return None


def _initialize_database_and_store() -> tuple[sqlite3.Connection, SqliteStore]:
    """Initialize SQLite database and SqliteStore for agent.

    Returns:
        Tuple of (connection, store).
    """
    from src.agent.config import get_agent_default

    db_path = get_agent_default("checkpoint_db_path", "data/agent_checkpoints.db")
    conn = sqlite3.connect(db_path, check_same_thread=False)
    conn.autocommit = True
    conn.execute("PRAGMA journal_mode=WAL")
    store = SqliteStore(conn)
    store.setup()
    return conn, store


def _get_or_create_session(args: argparse.Namespace) -> tuple[str, dict]:
    """Get or create a session based on CLI args.

    Args:
        args: Parsed CLI arguments.

    Returns:
        Tuple of (thread_id, session_dict).
    """
    from src.agent.checkpoint import get_session_manager

    session_mgr = get_session_manager()

    if args.session_id:
        sess = session_mgr.get_session(args.session_id)
        if sess:
            thread_id = sess["thread_id"]
        else:
            sess_by_thread = session_mgr.get_session_by_thread_id(args.session_id)
            if sess_by_thread:
                thread_id = sess_by_thread["thread_id"]
            else:
                thread_id = args.session_id
    else:
        sessions = session_mgr.list_sessions()
        if sessions:
            sess = sessions[0]
            thread_id = sess["thread_id"]
        else:
            sess = session_mgr.create_session()
            thread_id = sess["thread_id"]

    return thread_id, sess


def _print_help() -> None:
    """Print CLI help message."""
    print("🔧 RAG 维修工 Agent 已启动")
    print("   会话 ID: 见下方")
    print("输入问题进行诊断，输入 'quit' 或 'exit' 退出")
    print()
    print("快捷指令:")
    print("  :parse <parser>  - 指定解析器解析 PDF")
    print("  :back <stage>    - 回到指定阶段")
    print("  :compare         - 生成对比报告")
    print("  :report          - 生成维修报告")
    print("  :history         - 显示执行历史")
    print("  :status          - 显示当前状态")
    print("  :review on/off   - 切换自动审查")
    print("  :mode light/full - 切换轻量/全量模式")
    print("  :sessions        - 列出历史会话")
    print("  :switch <id>     - 切换到指定会话")
    print("  :new [title]     - 新建会话")
    print("  :copy [id]       - 复制会话")
    print("-" * 50)


def _handle_mode_command(
    user_input: str, current_mode: str, current_state: dict[str, Any]
) -> tuple[bool, str]:
    """Handle :mode and :review commands.

    Args:
        user_input: User input string.
        current_mode: Current mode string.
        current_state: Current state dictionary.

    Returns:
        Tuple of (handled, current_mode). If handled is True, the command was processed.
    """
    if user_input == ":review on":
        current_state["auto_review"] = True
        print("📋 自动审查已开启")
        return True, current_mode
    if user_input == ":review off":
        current_state["auto_review"] = False
        print("📋 自动审查已关闭")
        return True, current_mode

    if user_input.startswith(":mode"):
        parts = user_input.strip().split()
        if len(parts) >= 2 and parts[1] in ("light", "full"):
            current_mode = parts[1]
            current_state["mode"] = current_mode
            print(f"🔧 已切换到{'全量' if current_mode == 'full' else '轻量'}模式")
        else:
            print(f"当前模式: {current_mode} (用法: :mode light/full)")
        return True, current_mode

    return False, current_mode


def _handle_session_commands(
    cli_result: str | None,
    thread_id: str,
    config: dict,
    current_state: dict[str, Any],
    auto_review: bool,
    current_mode: str,
) -> tuple[bool, str, dict]:
    """Handle session-related CLI commands.

    Args:
        cli_result: Result from _handle_cli_command.
        thread_id: Current thread ID.
        config: Agent config dict.
        current_state: Current state dictionary.
        auto_review: Auto review flag.
        current_mode: Current mode string.

    Returns:
        Tuple of (handled, new_thread_id, new_config).
    """
    from src.agent.checkpoint import get_session_manager

    if cli_result == "__show_history__":
        history = current_state.get("stage_history", [])
        exec_log = current_state.get("execution_log", [])
        if history:
            print("\n📋 阶段历史:")
            for i, step in enumerate(history):
                print(f"   {i + 1}. {step}")
        else:
            print("\n📋 暂无阶段历史")
        if exec_log:
            print(f"\n📋 执行日志 ({len(exec_log)} 条):")
            for entry in exec_log:
                print(f"   - {entry}")
        return True, thread_id, config

    if cli_result == "__show_status__":
        print("\n📊 当前状态:")
        print(f"   会话 ID: {thread_id}")
        print(f"   当前 Meal: {current_state.get('current_meal', '未设置')}")
        print(f"   当前 PDF: {current_state.get('current_source', '未设置')}")
        print(f"   自动审查: {'开启' if auto_review else '关闭'}")
        print(f"   阶段历史: {len(current_state.get('stage_history', []))} 步")
        return True, thread_id, config

    if cli_result == "__list_sessions__":
        session_mgr_local = get_session_manager()
        sessions = session_mgr_local.list_sessions(include_archived=True)
        if not sessions:
            print("\n暂无历史会话")
        else:
            print(f"\n{'会话ID':<20} {'标题':<20} {'更新时间':<16}")
            print("-" * 60)
            for s in sessions:
                marker = " ▶" if s["thread_id"] == thread_id else ""
                print(
                    f"{s['session_id']:<20} {s['title']:<20} {s['updated_at'][:16]}{marker}"
                )
        return True, thread_id, config

    if cli_result and cli_result.startswith("__switch_session__"):
        target_id = cli_result[len("__switch_session__") :]
        session_mgr_local = get_session_manager()
        target_sess = session_mgr_local.get_session(target_id)
        if target_sess:
            thread_id = target_sess["thread_id"]
            config = {"configurable": {"thread_id": thread_id}}
            current_state.update(
                {
                    "diagnosis": [],
                    "execution_log": [],
                    "stage_history": [],
                    "auto_review": auto_review,
                    "delete_count": 0,
                    "mode": current_mode,
                }
            )
            print(f"已切换到会话: {target_sess['title']} ({target_id})")
        else:
            print(f"会话 {target_id} 不存在")
        return True, thread_id, config

    if cli_result and cli_result.startswith("__new_session__"):
        title = cli_result[len("__new_session__") :] or "新对话"
        session_mgr_local = get_session_manager()
        new_sess = session_mgr_local.create_session(title=title)
        thread_id = new_sess["thread_id"]
        config = {"configurable": {"thread_id": thread_id}}
        current_state.update(
            {
                "diagnosis": [],
                "execution_log": [],
                "stage_history": [],
                "auto_review": auto_review,
                "delete_count": 0,
                "mode": current_mode,
            }
        )
        print(f"已创建新会话: {new_sess['title']} ({new_sess['session_id']})")
        return True, thread_id, config

    if cli_result and cli_result.startswith("__copy_session__"):
        source_id = cli_result[len("__copy_session__") :]
        session_mgr_local = get_session_manager()
        new_sess = session_mgr_local.duplicate_session(
            source_id
            or session_mgr_local.get_session_by_thread_id(thread_id)["session_id"]
        )
        if new_sess:
            thread_id = new_sess["thread_id"]
            config = {"configurable": {"thread_id": thread_id}}
            print(f"已复制会话: {new_sess['title']} ({new_sess['session_id']})")
        else:
            print("复制会话失败")
        return True, thread_id, config

    return False, thread_id, config


def _run_agent_interaction(
    agent,
    state: dict[str, Any],
    config: dict,
    store: SqliteStore,
    current_state: dict[str, Any],
) -> None:
    """Run agent interaction loop with interrupt handling.

    Args:
        agent: Compiled agent.
        state: Agent state dict.
        config: Agent config dict.
        store: SqliteStore instance.
        current_state: Current session state dict.
    """
    from src.agent.tools import save_experience_tool

    while True:
        try:
            result = agent.invoke(state, config=config)
        except UnicodeEncodeError as e:
            logger.error(f"Encoding error in agent invocation: {e}")
            print("⚠️ 编码错误，请重新输入问题")
            break

        if result.get("__interrupt__"):
            for interrupt_info in result["__interrupt__"]:
                payload = interrupt_info.value
                if isinstance(payload, dict) and "question" in payload:
                    print(f"\n⚠️  {payload['question']}")
                    tool_info = payload.get("tool_call", {})
                    if tool_info:
                        print(f"   工具: {tool_info.get('name')}")
                        args_dict = tool_info.get("args", {})
                        if args_dict:
                            print(f"   参数: {args_dict}")
                    confirm = input("   确认执行？(y/n): ").strip().lower()
                    decision = confirm in ("y", "yes", "是")
                    state = Command(resume=decision)
                else:
                    state = Command(resume=True)
        else:
            _format_agent_response(result)
            save_experience_tool._store = store
            for key in (
                "current_meal",
                "current_source",
                "diagnosis",
                "execution_log",
                "stage_history",
                "delete_count",
            ):
                if key in result:
                    current_state[key] = result[key]
            break


def run_agent(argv: list[str] | None = None):
    """Run the maintenance agent in interactive CLI mode.

    Args:
        argv: Optional CLI argument list for testing.

    Returns:
        Exit code (0 for normal exit).
    """
    from src.agent.checkpoint import get_checkpointer
    from src.agent.graph import compile_agent
    from src.agent.memory.experience_store import ExperienceStore

    for stream in (sys.stdin, sys.stdout, sys.stderr):
        if stream and hasattr(stream, "reconfigure"):
            with contextlib.suppress(Exception):
                stream.reconfigure(encoding="utf-8", errors="replace")

    args = _parse_cli_args(argv)

    if args.list_sessions:
        from src.agent.checkpoint import get_session_manager

        session_mgr = get_session_manager()
        sessions = session_mgr.list_sessions(include_archived=True)
        if not sessions:
            print("暂无历史会话")
        else:
            print(f"{'会话ID':<20} {'标题':<20} {'更新时间':<20} {'归档'}")
            print("-" * 70)
            for s in sessions:
                archived = "是" if s["is_archived"] else "否"
                print(
                    f"{s['session_id']:<20} {s['title']:<20} {s['updated_at'][:16]:<20} {archived}"
                )
        return 0

    if args.new_session is not None:
        from src.agent.checkpoint import get_session_manager

        session_mgr = get_session_manager()
        new_sess = session_mgr.create_session(title=args.new_session or "新对话")
        args.session_id = new_sess["session_id"]
        print(f"已创建新会话: {new_sess['session_id']} ({new_sess['title']})")

    conn, store = _initialize_database_and_store()
    ExperienceStore._migrate_from_json(store, "data/agent_experience.json")

    with get_checkpointer() as checkpointer:
        agent = compile_agent(checkpointer=checkpointer, store=store)
        thread_id, sess = _get_or_create_session(args)
        config = {"configurable": {"thread_id": thread_id}}

        _print_help()
        print(f"   会话 ID: {thread_id}")

        auto_review = False
        current_mode = "full" if args.full else "light"
        current_state = build_initial_state(
            current_source=args.pdf,
            auto_review=auto_review,
            mode=current_mode,
        )

        from src.agent.tools import save_experience_tool

        save_experience_tool._store = store

        while True:
            try:
                user_input = input("\n👤 你: ").strip()
            except (EOFError, KeyboardInterrupt):
                print("\n再见！")
                break

            if user_input.lower() in ("quit", "exit", "q"):
                print("再见！")
                break

            if not user_input:
                continue

            handled, current_mode = _handle_mode_command(
                user_input, current_mode, current_state
            )
            if handled:
                continue

            cli_result = _handle_cli_command(user_input, auto_review)
            handled, thread_id, config = _handle_session_commands(
                cli_result, thread_id, config, current_state, auto_review, current_mode
            )
            if handled:
                continue

            message_content = cli_result if cli_result is not None else user_input
            message_content = _sanitize_text(message_content)

            state = build_agent_state(
                message_content=message_content,
                current_state=current_state,
                auto_review=auto_review,
                mode=current_mode,
            )

            _run_agent_interaction(agent, state, config, store, current_state)

    return 0


def main():
    """Entry point for the maintenance agent CLI."""
    try:
        sys.exit(run_agent())
    except Exception as e:
        logger.error(f"Agent failed: {e}")
        print(f"错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
