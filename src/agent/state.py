from __future__ import annotations

from typing import Annotated, Any, TypedDict

from langgraph.graph.message import add_messages


class MaintenanceState(TypedDict, total=False):
    messages: Annotated[list, add_messages]
    current_meal: str
    current_source: str
    diagnosis: list[dict[str, Any]]
    pending_action: dict[str, Any]
    approved: bool
    execution_log: list[str]
    stage_history: list[str]
    auto_review: bool
    locked_tool: str
    locked_tool_args: dict[str, Any]
    delete_count: int
    mode: str
