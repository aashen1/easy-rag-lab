from __future__ import annotations

from enum import Enum
from typing import Any


class ToolCategory(Enum):
    DIAGNOSIS = "diagnosis"
    REPAIR = "repair"


class ToolRiskLevel(Enum):
    SAFE = "safe"
    HIGH = "high"
    FORBIDDEN = "forbidden"


class ToolMetadata:
    __slots__ = ("name", "categories", "risk_level")

    def __init__(
        self,
        name: str,
        categories: set[ToolCategory],
        risk_level: ToolRiskLevel,
    ):
        self.name = name
        self.categories = categories
        self.risk_level = risk_level


_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    {
        "name": "list_meals",
        "categories": {ToolCategory.DIAGNOSIS},
        "risk_level": ToolRiskLevel.SAFE,
    },
    {
        "name": "get_meal_detail",
        "categories": {ToolCategory.DIAGNOSIS},
        "risk_level": ToolRiskLevel.SAFE,
    },
    {
        "name": "query_rag_tool",
        "categories": {ToolCategory.DIAGNOSIS},
        "risk_level": ToolRiskLevel.SAFE,
    },
    {
        "name": "get_index_info",
        "categories": {ToolCategory.DIAGNOSIS},
        "risk_level": ToolRiskLevel.SAFE,
    },
    {
        "name": "evaluate_answer_tool",
        "categories": {ToolCategory.DIAGNOSIS},
        "risk_level": ToolRiskLevel.SAFE,
    },
    {
        "name": "list_pdfs",
        "categories": {ToolCategory.DIAGNOSIS},
        "risk_level": ToolRiskLevel.SAFE,
    },
    {
        "name": "list_issues",
        "categories": {ToolCategory.DIAGNOSIS},
        "risk_level": ToolRiskLevel.SAFE,
    },
    {
        "name": "rebuild_index",
        "categories": {ToolCategory.REPAIR},
        "risk_level": ToolRiskLevel.HIGH,
    },
    {
        "name": "delete_source",
        "categories": {ToolCategory.REPAIR},
        "risk_level": ToolRiskLevel.HIGH,
    },
    {
        "name": "delete_and_reindex_tool",
        "categories": {ToolCategory.REPAIR},
        "risk_level": ToolRiskLevel.HIGH,
    },
    {
        "name": "update_meal",
        "categories": {ToolCategory.REPAIR},
        "risk_level": ToolRiskLevel.HIGH,
    },
    {
        "name": "delete_collection",
        "categories": set(),
        "risk_level": ToolRiskLevel.FORBIDDEN,
    },
    {
        "name": "drop_collection",
        "categories": set(),
        "risk_level": ToolRiskLevel.FORBIDDEN,
    },
    {"name": "delete_all", "categories": set(), "risk_level": ToolRiskLevel.FORBIDDEN},
    {"name": "drop_all", "categories": set(), "risk_level": ToolRiskLevel.FORBIDDEN},
    {"name": "delete_meal", "categories": set(), "risk_level": ToolRiskLevel.FORBIDDEN},
    {"name": "remove_meal", "categories": set(), "risk_level": ToolRiskLevel.FORBIDDEN},
]


class ToolRegistry:
    def __init__(self) -> None:
        self._tools: dict[str, ToolMetadata] = {}
        for entry in _TOOL_DEFINITIONS:
            self._tools[entry["name"]] = ToolMetadata(
                name=entry["name"],
                categories=entry["categories"],
                risk_level=entry["risk_level"],
            )

    def register_tool(
        self,
        name: str,
        categories: set[ToolCategory],
        risk_level: ToolRiskLevel,
    ) -> None:
        self._tools[name] = ToolMetadata(
            name=name, categories=categories, risk_level=risk_level
        )

    def get_tools_by_category(self, category: ToolCategory) -> set[str]:
        return {
            name for name, meta in self._tools.items() if category in meta.categories
        }

    def get_tools_by_risk_level(self, risk_level: ToolRiskLevel) -> set[str]:
        return {
            name for name, meta in self._tools.items() if meta.risk_level == risk_level
        }

    def is_high_risk(self, tool_name: str) -> bool:
        meta = self._tools.get(tool_name)
        return meta is not None and meta.risk_level == ToolRiskLevel.HIGH

    def is_forbidden(self, tool_name: str) -> bool:
        meta = self._tools.get(tool_name)
        return meta is not None and meta.risk_level == ToolRiskLevel.FORBIDDEN

    def is_repair(self, tool_name: str) -> bool:
        meta = self._tools.get(tool_name)
        return meta is not None and ToolCategory.REPAIR in meta.categories

    def is_diagnosis(self, tool_name: str) -> bool:
        meta = self._tools.get(tool_name)
        return meta is not None and ToolCategory.DIAGNOSIS in meta.categories


_registry = ToolRegistry()


def get_tool_registry() -> ToolRegistry:
    return _registry


def get_diagnosis_tools() -> set[str]:
    return _registry.get_tools_by_category(ToolCategory.DIAGNOSIS)


def get_repair_tools() -> set[str]:
    return _registry.get_tools_by_category(ToolCategory.REPAIR)


def get_high_risk_tools() -> set[str]:
    return _registry.get_tools_by_risk_level(ToolRiskLevel.HIGH)


def get_forbidden_operations() -> set[str]:
    return _registry.get_tools_by_risk_level(ToolRiskLevel.FORBIDDEN)


DIAGNOSIS_TOOLS = get_diagnosis_tools()
REPAIR_TOOLS = get_repair_tools()
HIGH_RISK_TOOLS = get_high_risk_tools()
FORBIDDEN_OPERATIONS = get_forbidden_operations()
