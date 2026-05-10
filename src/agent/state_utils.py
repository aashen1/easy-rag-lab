from __future__ import annotations

from typing import Any


def build_agent_state(
    message_content: str,
    current_state: dict[str, Any],
    auto_review: bool = False,
    mode: str = "full",
    locked_tool: str | None = None,
    locked_tool_args: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "messages": [{"role": "user", "content": message_content}],
        "current_meal": current_state.get("current_meal"),
        "current_source": current_state.get("current_source"),
        "diagnosis": current_state.get("diagnosis", []),
        "pending_action": None,
        "approved": None,
        "execution_log": current_state.get("execution_log", []),
        "stage_history": current_state.get("stage_history", []),
        "auto_review": auto_review,
        "locked_tool": locked_tool,
        "locked_tool_args": locked_tool_args,
        "delete_count": current_state.get("delete_count", 0),
        "mode": mode,
    }


def build_initial_state(
    current_source: str | None = None,
    auto_review: bool = False,
    mode: str = "full",
) -> dict[str, Any]:
    return {
        "current_meal": None,
        "current_source": current_source,
        "diagnosis": [],
        "pending_action": None,
        "approved": None,
        "execution_log": [],
        "stage_history": [],
        "auto_review": auto_review,
        "delete_count": 0,
        "mode": mode,
    }
