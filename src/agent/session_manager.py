from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from uuid import uuid4

from loguru import logger

from src.agent.db_utils import resolve_db_path


class SessionManager:
    """Manage maintenance agent conversation sessions.

    Provides CRUD operations for session metadata stored in the same
    SQLite database used by the LangGraph checkpointer.

    Args:
        db_path: Path to the SQLite database file. If None, reads from
            config.yaml agent.checkpoint.db_path, falling back to
            ``data/agent_checkpoints.db``.

    Raises:
        sqlite3.Error: If the database connection or table creation fails.
    """

    def __init__(self, db_path: str | None = None) -> None:
        db_path_obj = resolve_db_path(db_path)
        logger.info(f"Initializing SessionManager at {db_path_obj}")
        try:
            self._conn = sqlite3.connect(str(db_path_obj), check_same_thread=False)
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.row_factory = sqlite3.Row
            self._ensure_table()
        except sqlite3.Error as e:
            logger.error(f"Failed to initialize SessionManager at {db_path_obj}: {e}")
            raise

    def _ensure_table(self) -> None:
        """Create the sessions table and indexes if they do not exist."""
        try:
            self._conn.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    session_id    TEXT PRIMARY KEY,
                    thread_id     TEXT NOT NULL UNIQUE,
                    title         TEXT NOT NULL DEFAULT '新对话',
                    created_at    TEXT NOT NULL,
                    updated_at    TEXT NOT NULL,
                    message_count INTEGER NOT NULL DEFAULT 0,
                    is_archived   INTEGER NOT NULL DEFAULT 0
                );
                CREATE INDEX IF NOT EXISTS idx_sessions_updated_at ON sessions(updated_at DESC);
                CREATE INDEX IF NOT EXISTS idx_sessions_is_archived ON sessions(is_archived);
                """
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to create sessions table: {e}")
            raise

    def create_session(self, title: str = "新对话") -> dict:
        """Create a new session and persist it to the database.

        Args:
            title: Display title for the session. Defaults to ``"新对话"``.

        Returns:
            A dict representing the newly created session row.

        Raises:
            sqlite3.Error: If the insert fails.
        """
        session_id = f"sess_{uuid4().hex[:12]}"
        thread_id = f"maintenance-{uuid4().hex[:8]}"
        now = datetime.now(UTC).isoformat()
        try:
            self._conn.execute(
                """
                INSERT INTO sessions (session_id, thread_id, title, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (session_id, thread_id, title, now, now),
            )
            self._conn.commit()
            logger.info(f"Created session {session_id} with thread {thread_id}")
            return {
                "session_id": session_id,
                "thread_id": thread_id,
                "title": title,
                "created_at": now,
                "updated_at": now,
                "message_count": 0,
                "is_archived": 0,
            }
        except sqlite3.Error as e:
            logger.error(f"Failed to create session: {e}")
            raise

    def list_sessions(self, include_archived: bool = False) -> list[dict]:
        """List sessions ordered by most recently updated first.

        Args:
            include_archived: If False, only return non-archived sessions.

        Returns:
            A list of session dicts.

        Raises:
            sqlite3.Error: If the query fails.
        """
        try:
            if include_archived:
                cursor = self._conn.execute(
                    "SELECT * FROM sessions ORDER BY updated_at DESC"
                )
            else:
                cursor = self._conn.execute(
                    "SELECT * FROM sessions WHERE is_archived = 0 ORDER BY updated_at DESC"
                )
            rows = cursor.fetchall()
            return [dict(row) for row in rows]
        except sqlite3.Error as e:
            logger.error(f"Failed to list sessions: {e}")
            raise

    def get_session(self, session_id: str) -> dict | None:
        """Retrieve a single session by its session_id.

        Args:
            session_id: The unique session identifier.

        Returns:
            A session dict if found, otherwise None.

        Raises:
            sqlite3.Error: If the query fails.
        """
        try:
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get session {session_id}: {e}")
            raise

    def get_session_by_thread_id(self, thread_id: str) -> dict | None:
        """Retrieve a session by its thread_id.

        Args:
            thread_id: The LangGraph thread identifier.

        Returns:
            A session dict if found, otherwise None.

        Raises:
            sqlite3.Error: If the query fails.
        """
        try:
            cursor = self._conn.execute(
                "SELECT * FROM sessions WHERE thread_id = ?",
                (thread_id,),
            )
            row = cursor.fetchone()
            return dict(row) if row else None
        except sqlite3.Error as e:
            logger.error(f"Failed to get session by thread_id {thread_id}: {e}")
            raise

    def update_session(self, session_id: str, **kwargs) -> None:
        """Update one or more fields of an existing session.

        Allowed fields: ``title``, ``is_archived``, ``message_count``.
        The ``updated_at`` field is always set to the current time.

        Args:
            session_id: The session to update.
            **kwargs: Field names and their new values.

        Raises:
            sqlite3.Error: If the update fails.
            ValueError: If no allowed fields are provided.
        """
        allowed = {"title", "is_archived", "message_count"}
        updates = {k: v for k, v in kwargs.items() if k in allowed}
        if not updates:
            raise ValueError("No updatable fields provided")
        updates["updated_at"] = datetime.now(UTC).isoformat()
        set_clause = ", ".join(f"{k} = ?" for k in updates)
        values = list(updates.values()) + [session_id]
        try:
            self._conn.execute(
                f"UPDATE sessions SET {set_clause} WHERE session_id = ?",
                values,
            )
            self._conn.commit()
            logger.info(f"Updated session {session_id}: {updates}")
        except sqlite3.Error as e:
            logger.error(f"Failed to update session {session_id}: {e}")
            raise

    def delete_session(self, session_id: str) -> None:
        """Delete a session metadata row from the database.

        Args:
            session_id: The session to delete.

        Raises:
            sqlite3.Error: If the delete fails.
        """
        try:
            self._conn.execute(
                "DELETE FROM sessions WHERE session_id = ?",
                (session_id,),
            )
            self._conn.commit()
            logger.info(f"Deleted session {session_id}")
        except sqlite3.Error as e:
            logger.error(f"Failed to delete session {session_id}: {e}")
            raise

    def archive_session(self, session_id: str) -> None:
        """Mark a session as archived.

        Args:
            session_id: The session to archive.

        Raises:
            sqlite3.Error: If the update fails.
        """
        self.update_session(session_id, is_archived=1)

    def unarchive_session(self, session_id: str) -> None:
        """Mark a session as not archived.

        Args:
            session_id: The session to unarchive.

        Raises:
            sqlite3.Error: If the update fails.
        """
        self.update_session(session_id, is_archived=0)

    def touch_session(self, session_id: str) -> None:
        """Update the updated_at timestamp of a session to the current time.

        Args:
            session_id: The session to touch.

        Raises:
            sqlite3.Error: If the update fails.
        """
        now = datetime.now(UTC).isoformat()
        try:
            self._conn.execute(
                "UPDATE sessions SET updated_at = ? WHERE session_id = ?",
                (now, session_id),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            logger.error(f"Failed to touch session {session_id}: {e}")
            raise

    def auto_title(self, session_id: str, first_message: str) -> None:
        """Derive a session title from the first user message.

        Extracts the first 20 characters of the message and sets it as
        the session title.

        Args:
            session_id: The session to rename.
            first_message: The first user message content.

        Raises:
            sqlite3.Error: If the update fails.
        """
        title = first_message[:20]
        self.update_session(session_id, title=title)

    def duplicate_session(
        self,
        source_session_id: str,
        new_title: str | None = None,
        agent=None,
    ) -> dict | None:
        """Create a new session duplicating metadata from an existing one.

        If an agent instance is provided, the source session's state is
        seeded into the new thread via ``agent.update_state()``.

        Args:
            source_session_id: The session to duplicate.
            new_title: Optional title for the new session. If None,
                uses ``"<原标题> (副本)"``.
            agent: Optional LangGraph agent with ``update_state()`` method.

        Returns:
            The new session dict, or None if the source session does
            not exist.

        Raises:
            sqlite3.Error: If the database operations fail.
        """
        source = self.get_session(source_session_id)
        if source is None:
            logger.warning(
                f"Source session {source_session_id} not found for duplication"
            )
            return None

        title = new_title or f"{source['title']} (副本)"
        new_session = self.create_session(title=title)

        if agent is not None:
            try:
                source_state = agent.get_state(
                    config={"configurable": {"thread_id": source["thread_id"]}}
                )
                agent.update_state(
                    config={"configurable": {"thread_id": new_session["thread_id"]}},
                    values=source_state.values,
                )
                logger.info(
                    f"Seeded new thread {new_session['thread_id']} "
                    f"from source {source['thread_id']}"
                )
            except Exception as e:
                logger.error(f"Failed to seed state for duplicated session: {e}")

        return new_session

    def _migrate_orphan_checkpoints(self, checkpointer) -> int:
        """Create session records for thread_ids that exist in the
        checkpointer but have no corresponding session row.

        This is typically called when the sessions table is empty but
        the checkpointer already has persisted checkpoints from earlier
        runs.

        Args:
            checkpointer: A LangGraph SqliteSaver or compatible
                checkpointer with a ``list()`` method.

        Returns:
            The number of newly created session records.

        Raises:
            sqlite3.Error: If the database operations fail.
        """
        try:
            cursor = self._conn.execute("SELECT COUNT(*) FROM sessions")
            count = cursor.fetchone()[0]
            if count > 0:
                logger.info("Sessions table not empty, skipping orphan migration")
                return 0
        except sqlite3.Error as e:
            logger.error(f"Failed to check sessions count: {e}")
            raise

        migrated = 0
        try:
            for checkpoint_tuple in checkpointer.list(None):
                thread_id = checkpoint_tuple.config.get("configurable", {}).get(
                    "thread_id"
                )
                if not thread_id:
                    continue
                existing = self.get_session_by_thread_id(thread_id)
                if existing is not None:
                    continue
                now = datetime.now(UTC).isoformat()
                session_id = f"sess_{uuid4().hex[:12]}"
                self._conn.execute(
                    """
                    INSERT INTO sessions (session_id, thread_id, title, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (session_id, thread_id, "已迁移对话", now, now),
                )
                migrated += 1
            if migrated > 0:
                self._conn.commit()
                logger.info(f"Migrated {migrated} orphan checkpoint(s) into sessions")
        except sqlite3.Error as e:
            logger.error(f"Failed during orphan checkpoint migration: {e}")
            raise

        return migrated
