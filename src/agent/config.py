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


def get_delete_count_threshold(mode: str | None = None) -> int:
    if mode == "full":
        return get_agent_config().get("full_mode_delete_threshold", 10)
    return get_agent_config().get("delete_count_threshold", 3)


def get_session_config() -> dict[str, Any]:
    """Return the agent session configuration section.

    Returns:
        Dict with session settings (e.g., ``auto_title_max_length``,
        ``default_title``, ``list_limit``).
    """
    agent_config = get_agent_config()
    return agent_config.get("session", {})


def get_experience_config() -> dict[str, Any]:
    """Return the agent experience configuration section.

    Returns:
        Dict with experience settings (e.g., ``scan_max_candidates``,
        ``categories``).
    """
    agent_config = get_agent_config()
    return agent_config.get("experience", {})
