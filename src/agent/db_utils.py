from __future__ import annotations

from pathlib import Path

from loguru import logger


def resolve_db_path(db_path: str | None = None) -> Path:
    if db_path is None:
        from src.agent.config import get_checkpoint_config

        ckpt_config = get_checkpoint_config()
        db_path = ckpt_config.get("db_path", "data/agent_checkpoints.db")

    db_path_obj = Path(db_path)
    try:
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create database directory {db_path_obj.parent}: {e}")
        raise
    return db_path_obj
