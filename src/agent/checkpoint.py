from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger


def _resolve_db_path(db_path: str | None = None) -> Path:
    if db_path is None:
        from src.agent.config import get_checkpoint_config

        ckpt_config = get_checkpoint_config()
        db_path = ckpt_config.get("db_path", "data/agent_checkpoints.db")

    db_path_obj = Path(db_path)
    try:
        db_path_obj.parent.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        logger.error(f"Failed to create checkpoint directory {db_path_obj.parent}: {e}")
        raise
    return db_path_obj


@contextmanager
def get_checkpointer(db_path: str | None = None) -> Generator:
    """Create a SqliteSaver checkpointer for agent session persistence.

    This is a context manager that yields a SqliteSaver instance and
    properly manages the database connection lifecycle.

    Args:
        db_path: Path to the SQLite database file. If None, reads from
            config.yaml agent.checkpoint.db_path, falling back to
            ``data/agent_checkpoints.db``.

    Yields:
        A SqliteSaver instance ready for use with compile_agent().
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path_obj = _resolve_db_path(db_path)

    logger.info(f"Initializing SqliteSaver at {db_path_obj}")
    with SqliteSaver.from_conn_string(str(db_path_obj)) as checkpointer:
        yield checkpointer


def get_checkpointer_direct(db_path: str | None = None):
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path_obj = _resolve_db_path(db_path)

    logger.info(f"Initializing SqliteSaver (direct) at {db_path_obj}")
    try:
        conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return SqliteSaver(conn)
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize SqliteSaver at {db_path_obj}: {e}")
        raise
