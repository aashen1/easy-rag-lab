from __future__ import annotations

import functools
from typing import Any


@functools.lru_cache(maxsize=1)
def get_agent_config() -> dict[str, Any]:
    from src.utils import load_config

    config = load_config()
    return config.get("agent", {})


def get_agent_default(key: str, fallback: Any = None) -> Any:
    agent_config = get_agent_config()
    defaults = agent_config.get("defaults", {})
    return defaults.get(key, fallback)


def get_checkpoint_config() -> dict[str, Any]:
    """Return the agent checkpoint configuration section.

    Returns:
        Dict with checkpoint settings (e.g., ``db_path``).
    """
    agent_config = get_agent_config()
    return agent_config.get("checkpoint", {})
