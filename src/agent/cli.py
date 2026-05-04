from __future__ import annotations

import argparse
import sys

from langchain_core.messages import AIMessage
from langgraph.types import Command
from loguru import logger


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

    return None


def run_agent(argv: list[str] | None = None):
    """Run the maintenance agent in interactive CLI mode.

    Args:
        argv: Optional CLI argument list for testing.

    Returns:
        Exit code (0 for normal exit).
    """
    from langgraph.store.memory import InMemoryStore

    from src.agent.checkpoint import get_checkpointer
    from src.agent.config import get_agent_default
    from src.agent.graph import compile_agent

    args = _parse_cli_args(argv)

    store = InMemoryStore()

    with get_checkpointer() as checkpointer:
        agent = compile_agent(checkpointer=checkpointer, store=store)

        thread_id = args.session_id or get_agent_default(
            "thread_id", "maintenance-session"
        )
        config = {"configurable": {"thread_id": thread_id}}

        print("🔧 RAG 维修工 Agent 已启动")
        print(f"   会话 ID: {thread_id}")
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
        print("-" * 50)

        auto_review = False
        current_mode = "full" if args.full else "light"
        current_state = {
            "current_meal": None,
            "current_source": args.pdf,
            "diagnosis": [],
            "pending_action": None,
            "approved": None,
            "execution_log": [],
            "stage_history": [],
            "auto_review": auto_review,
            "delete_count": 0,
            "mode": current_mode,
        }

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

            if user_input == ":review on":
                auto_review = True
                current_state["auto_review"] = True
                print("📋 自动审查已开启")
                continue
            if user_input == ":review off":
                auto_review = False
                current_state["auto_review"] = False
                print("📋 自动审查已关闭")
                continue

            if user_input.startswith(":mode"):
                parts = user_input.strip().split()
                if len(parts) >= 2 and parts[1] in ("light", "full"):
                    current_mode = parts[1]
                    current_state["mode"] = current_mode
                    print(
                        f"🔧 已切换到{'全量' if current_mode == 'full' else '轻量'}模式"
                    )
                else:
                    print(f"当前模式: {current_mode} (用法: :mode light/full)")
                continue

            cli_result = _handle_cli_command(user_input, auto_review)
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
                continue
            if cli_result == "__show_status__":
                print("\n📊 当前状态:")
                print(f"   会话 ID: {thread_id}")
                print(f"   当前 Meal: {current_state.get('current_meal', '未设置')}")
                print(f"   当前 PDF: {current_state.get('current_source', '未设置')}")
                print(f"   自动审查: {'开启' if auto_review else '关闭'}")
                print(f"   阶段历史: {len(current_state.get('stage_history', []))} 步")
                continue

            message_content = cli_result if cli_result is not None else user_input

            state = {
                "messages": [{"role": "user", "content": message_content}],
                "current_meal": current_state.get("current_meal"),
                "current_source": current_state.get("current_source"),
                "diagnosis": current_state.get("diagnosis", []),
                "pending_action": None,
                "approved": None,
                "execution_log": current_state.get("execution_log", []),
                "stage_history": current_state.get("stage_history", []),
                "auto_review": auto_review,
                "delete_count": current_state.get("delete_count", 0),
                "mode": current_mode,
            }

            while True:
                result = agent.invoke(state, config=config)

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
