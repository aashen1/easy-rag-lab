from __future__ import annotations

import sys

from langgraph.checkpoint.memory import MemorySaver
from langgraph.types import Command
from loguru import logger


def run_agent():
    """Run the maintenance agent in interactive CLI mode.

    Returns:
        Exit code (0 for normal exit).
    """
    from src.agent.graph import compile_agent

    checkpointer = MemorySaver()
    agent = compile_agent(checkpointer=checkpointer)

    config = {"configurable": {"thread_id": "maintenance-session"}}

    print("🔧 RAG 维修工 Agent 已启动")
    print("输入问题进行诊断，输入 'quit' 或 'exit' 退出")
    print("-" * 50)

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

        state = {
            "messages": [{"role": "user", "content": user_input}],
            "current_meal": None,
            "current_source": None,
            "diagnosis": [],
            "pending_action": None,
            "approved": None,
            "execution_log": [],
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
                            args = tool_info.get("args", {})
                            if args:
                                print(f"   参数: {args}")
                        confirm = input("   确认执行？(y/n): ").strip().lower()
                        decision = confirm in ("y", "yes", "是")
                        state = Command(resume=decision)
                    else:
                        state = Command(resume=True)
            else:
                last_message = (
                    result.get("messages", [])[-1] if result.get("messages") else None
                )
                if last_message and hasattr(last_message, "content"):
                    print(f"\n🤖 维修工: {last_message.content}")

                exec_log = result.get("execution_log", [])
                if exec_log:
                    print(f"\n📋 执行日志: {len(exec_log)} 条记录")
                    for entry in exec_log[-5:]:
                        print(f"   - {entry}")

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
