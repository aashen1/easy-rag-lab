from __future__ import annotations

import sqlite3
from collections.abc import Generator
from contextlib import contextmanager
from typing import TYPE_CHECKING

from loguru import logger

from src.agent.db_utils import resolve_db_path

if TYPE_CHECKING:
    from src.agent.session_manager import SessionManager


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

    db_path_obj = resolve_db_path(db_path)

    logger.info(f"Initializing SqliteSaver at {db_path_obj}")
    with SqliteSaver.from_conn_string(str(db_path_obj)) as checkpointer:
        yield checkpointer


def get_checkpointer_direct(db_path: str | None = None):
    from langgraph.checkpoint.sqlite import SqliteSaver

    db_path_obj = resolve_db_path(db_path)

    logger.info(f"Initializing SqliteSaver (direct) at {db_path_obj}")
    try:
        conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
        conn.execute("PRAGMA journal_mode=WAL")
        return SqliteSaver(conn)
    except sqlite3.Error as e:
        logger.error(f"Failed to initialize SqliteSaver at {db_path_obj}: {e}")
        raise


def get_session_manager(db_path: str | None = None) -> SessionManager:
    """Create a SessionManager instance for session metadata management.

    Uses the same database file as the checkpointer
    (``data/agent_checkpoints.db`` by default).

    Args:
        db_path: Path to the SQLite database file. If None, reads from
            config.yaml agent.checkpoint.db_path, falling back to
            ``data/agent_checkpoints.db``.

    Returns:
        A SessionManager instance ready for session CRUD operations.
    """
    from src.agent.session_manager import SessionManager

    db_path_obj = resolve_db_path(db_path)
    return SessionManager(str(db_path_obj))
