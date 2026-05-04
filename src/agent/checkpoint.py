from __future__ import annotations

from collections.abc import Generator
from contextlib import contextmanager
from pathlib import Path

from loguru import logger


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

    if db_path is None:
        from src.agent.config import get_checkpoint_config

        ckpt_config = get_checkpoint_config()
        db_path = ckpt_config.get("db_path", "data/agent_checkpoints.db")

    db_path_obj = Path(db_path)
    db_path_obj.parent.mkdir(parents=True, exist_ok=True)

    logger.info(f"Initializing SqliteSaver at {db_path}")
    with SqliteSaver.from_conn_string(str(db_path_obj)) as checkpointer:
        yield checkpointer
