from __future__ import annotations

from typing import Any


def get_agent_config() -> dict[str, Any]:
    from src.utils import load_config

    config = load_config()
    return config.get("agent", {})


def get_agent_default(key: str, fallback: Any = None) -> Any:
    agent_config = get_agent_config()
    defaults = agent_config.get("defaults", {})
    return defaults.get(key, fallback)
