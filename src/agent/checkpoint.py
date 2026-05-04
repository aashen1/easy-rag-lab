from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger


def _resolve_db_path(db_path: str | None = None) -> Path:
    """Resolve the checkpoint database path from config if not provided.

    Args:
        db_path: Explicit database path, or None to read from config.

    Returns:
        Resolved Path object with parent directories created.
    """
    if db_path is None:
        from src.agent.config import get_checkpoint_config

        ckpt_config = get_checkpoint_config()
        db_path = ckpt_config.get("db_path", "data/agent_checkpoints.db")

    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)
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
    """Create a SqliteSaver with a persistent connection (no context manager).

    Suitable for long-lived applications like Streamlit where the
    checkpointer needs to stay alive across multiple invocations.
    The caller is responsible for closing the underlying connection
    when no longer needed.

    Args:
        db_path: Path to the SQLite database file. If None, reads from
            config.yaml agent.checkpoint.db_path, falling back to
            ``data/agent_checkpoints.db``.

    Returns:
        A SqliteSaver instance with an open connection.
    """
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path_obj = _resolve_db_path(db_path)

    logger.info(f"Initializing SqliteSaver (direct) at {db_path_obj}")
    conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
    return SqliteSaver(conn)
