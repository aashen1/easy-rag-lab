from __future__ import annotations

from typing import Annotated, Any

from langgraph.graph.message import add_messages


class MaintenanceState(dict):
    messages: Annotated[list, add_messages]
    current_meal: str | None
    current_source: str | None
    diagnosis: list[dict[str, Any]]
    pending_action: dict[str, Any] | None
    approved: bool | None
    execution_log: list[str]
    stage_history: list[str]
    auto_review: bool
