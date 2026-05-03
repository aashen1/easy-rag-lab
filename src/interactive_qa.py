from __future__ import annotations

import contextlib
from typing import Any

from loguru import logger

from src.case_collector import (
    CASE_TYPE_BAD,
    CASE_TYPE_GOOD,
    DEDUP_STATUS_DUPLICATE,
    DEDUP_STATUS_TYPE_CHANGED,
    save_case_with_dedup,
)
from src.pipeline import RAGPipeline
from src.utils import load_config


def _build_chat_history(messages: list[dict[str, Any]]) -> list[dict[str, str]]:
    """Extract chat_history in Anthropic API format from message list.

    Converts the internal message format (with result dicts) to the
    simple ``[{"role": ..., "content": ...}]`` format expected by
    ``Generator.generate()``.

    Args:
        messages: Internal message list from the interactive session.

    Returns:
        List of dicts with ``role`` and ``content`` keys.
    """
    history: list[dict[str, str]] = []
    for msg in messages:
        role = msg.get("role", "")
        if role == "user":
            history.append({"role": "user", "content": msg.get("content", "")})
        elif role == "assistant":
            result = msg.get("result", {})
            answer = result.get("answer", "")
            if answer:
                history.append({"role": "assistant", "content": answer})
    return history


def _get_assistant_messages(messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return assistant messages from the message list.

    Args:
        messages: Internal message list from the interactive session.

    Returns:
        List of assistant message dicts.
    """
    return [m for m in messages if m.get("role") == "assistant"]


def _parse_case_command(
    raw: str,
) -> tuple[str | None, int | None]:
    """Parse a slash command for case collection.

    Args:
        raw: Raw user input string (e.g. ``/badcase``, ``/goodcase 3``).

    Returns:
        Tuple of (case_type, index_1based). case_type is
        ``CASE_TYPE_BAD`` or ``CASE_TYPE_GOOD``, or None if not a case
        command. index_1based is the 1-based assistant message index, or
        None meaning "latest".
    """
    parts = raw.strip().split()
    cmd = parts[0].lower()

    if cmd == "/badcase":
        case_type = CASE_TYPE_BAD
    elif cmd == "/goodcase":
        case_type = CASE_TYPE_GOOD
    else:
        return None, None

    index = None
    if len(parts) > 1:
        with contextlib.suppress(ValueError):
            index = int(parts[1])

    return case_type, index


def _resolve_assistant_msg(
    messages: list[dict[str, Any]],
    index_1based: int | None,
) -> tuple[dict[str, Any] | None, int | None, str]:
    """Resolve an assistant message by 1-based index or latest.

    Args:
        messages: Full message list from the interactive session.
        index_1based: 1-based index among assistant messages, or None
            for the latest.

    Returns:
        Tuple of (msg_dict, msg_global_index, error_message).
        msg_dict is None on error with error_message set.
    """
    assistant_msgs = _get_assistant_messages(messages)

    if not assistant_msgs:
        return None, None, "还没有查询记录，请先提问"

    if index_1based is not None:
        if index_1based < 1 or index_1based > len(assistant_msgs):
            return (
                None,
                None,
                f"无效的轮次编号，当前共 {len(assistant_msgs)} 轮对话（范围 1-{len(assistant_msgs)}）",
            )
        target = assistant_msgs[index_1based - 1]
    else:
        target = assistant_msgs[-1]

    global_index = messages.index(target)
    return target, global_index, ""


def _print_history(messages: list[dict[str, Any]]) -> None:
    """Print a summary of the conversation history.

    Args:
        messages: Internal message list from the interactive session.
    """
    assistant_msgs = _get_assistant_messages(messages)

    if not assistant_msgs:
        print("📝 暂无对话历史\n")
        return

    print(f"\n📝 对话历史（共 {len(assistant_msgs)} 轮）：")
    print("─" * 60)

    for i, msg in enumerate(assistant_msgs, 1):
        result = msg.get("result", {})
        question = result.get("question", "")
        preview = question[:40] + "..." if len(question) > 40 else question
        saved = msg.get("saved_case_type")
        if saved == CASE_TYPE_BAD:
            status = "🚨 bad"
        elif saved == CASE_TYPE_GOOD:
            status = "✅ good"
        else:
            status = "—"
        print(f"  [{i}] {preview:<44} {status}")

    print("─" * 60)
    print("使用 /badcase N 或 /goodcase N 标记指定轮次\n")


def _print_help() -> None:
    """Print available slash commands."""
    print(
        "\n📖 可用命令：\n"
        "  /badcase [N]   保存最近一条（或第 N 条）回答为 Badcase\n"
        "  /goodcase [N]  保存最近一条（或第 N 条）回答为 Goodcase\n"
        "  /history       显示对话历史摘要\n"
        "  /clear         清空对话历史\n"
        "  /help          显示此帮助\n"
        "  quit / exit    退出\n"
    )


def interactive_qa(pipeline: RAGPipeline, meal_name: str | None = None) -> None:
    """Run an interactive Q&A session with multi-turn and case collection.

    Continuously prompts for questions and displays answers until
    the user types 'quit' or 'exit'. Supports multi-turn conversation
    by maintaining chat history and passing it to the pipeline. Supports
    ``/badcase`` and ``/goodcase`` slash commands with deduplication
    logic shared with the Web UI.

    Args:
        pipeline: RAGPipeline instance for query execution.
        meal_name: Optional meal name to display in the welcome message.
    """
    collection_info = pipeline.indexer.get_collection_info()
    if meal_name:
        print(f"\n🤖 RAG 问答系统已启动（meal: {meal_name}）")
    else:
        print("\n🤖 RAG 问答系统已启动")

    if collection_info:
        chunks_count = collection_info.get("points_count", 0)
        print(f"📝 数据库中已有 {chunks_count} 个文档片段")
    else:
        print(
            "⚠️  数据库为空，请先构建索引：pixi run python main.py --build-index --meal <name>"
        )

    print("输入问题开始对话，输入 /help 查看可用命令\n")

    messages: list[dict[str, Any]] = []

    while True:
        try:
            question = input("💬 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！\n")
            break

        if not question:
            continue

        if question.lower() in ("quit", "exit", "q"):
            tracker = pipeline.token_tracker
            if tracker and tracker.record_count > 0:
                total = tracker.get_total()
                print(
                    f"\n📊 Session Token Usage: in={total.input_tokens:,} "
                    f"out={total.output_tokens:,} total={total.total_tokens:,}"
                )
            print("👋 再见！\n")
            break

        if question.lower() == "/help":
            _print_help()
            continue

        if question.lower() == "/clear":
            messages = []
            print("🗑️  对话历史已清空\n")
            continue

        if question.lower() == "/history":
            _print_history(messages)
            continue

        case_type, index_1based = _parse_case_command(question)
        if case_type is not None:
            target_msg, _, err = _resolve_assistant_msg(messages, index_1based)
            if err:
                print(f"⚠️  {err}\n")
                continue

            result = target_msg.get("result", {})
            config_overrides = target_msg.get("config_overrides", {})
            msg_meal_name = target_msg.get("meal_name")
            question_text = result.get("question", "")
            saved_case_type = target_msg.get("saved_case_type")
            saved_case_id = target_msg.get("saved_case_id")

            icon = "🚨" if case_type == CASE_TYPE_BAD else "✅"
            label = "Badcase" if case_type == CASE_TYPE_BAD else "Goodcase"

            try:
                base_config = load_config()
                meal_config = getattr(pipeline, "meal_config", None)
                chat_history = _build_chat_history(messages)

                case_dir, status = save_case_with_dedup(
                    case_type=case_type,
                    question=question_text,
                    result=result,
                    config_overrides=config_overrides,
                    base_config=base_config,
                    meal_config=meal_config,
                    meal_name=msg_meal_name,
                    chat_history=chat_history,
                    saved_case_type=saved_case_type,
                    saved_case_id=saved_case_id,
                )

                if status == DEDUP_STATUS_DUPLICATE:
                    print(f"{icon} 已标记为 {label}，无需重复保存\n")
                elif status == DEDUP_STATUS_TYPE_CHANGED:
                    old_label = (
                        "Badcase" if saved_case_type == CASE_TYPE_BAD else "Goodcase"
                    )
                    print(
                        f"{icon} 已将 {old_label} 转换为 {label}: {case_dir.name}\n"
                        f"   原 {old_label} ({saved_case_id}) 已删除\n"
                    )
                    target_msg["saved_case_type"] = case_type
                    target_msg["saved_case_id"] = case_dir.name
                else:
                    print(f"{icon} {label} 已保存: {case_dir.name}\n")
                    target_msg["saved_case_type"] = case_type
                    target_msg["saved_case_id"] = case_dir.name

            except Exception as e:
                logger.error(f"Failed to save case: {e}")
                print(f"❌ 保存失败: {e}\n")
            continue

        try:
            chat_history = _build_chat_history(messages)
            result = pipeline.query(question, chat_history=chat_history)

            messages.append({"role": "user", "content": question})
            messages.append(
                {
                    "role": "assistant",
                    "result": result,
                    "config_overrides": None,
                    "meal_name": meal_name,
                    "saved_case_type": None,
                    "saved_case_id": None,
                }
            )

            turn_num = len(_get_assistant_messages(messages))
            print(f"\n🤖 Assistant [Q{turn_num}]: {result['answer']}\n")

            if "token_usage" in result and result["token_usage"]:
                tu = result["token_usage"]
                print(
                    f"📊 Tokens: in={tu['input_tokens']:,} out={tu['output_tokens']:,} "
                    f"total={tu['total_tokens']:,}\n"
                )

            if "sources" in result and result["sources"]:
                print("📚 参考来源：")
                for i, (source, score) in enumerate(
                    zip(result["sources"][:3], result["scores"][:3], strict=False), 1
                ):
                    source_name = source.split("\\")[-1] if "\\" in source else source
                    print(f"   {i}. {source_name} (相关度: {score:.4f})")
                print()
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            print(f"\n❌ 处理问题时出错: {str(e)}\n")
