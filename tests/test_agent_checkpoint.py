from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.agent


class TestGetCheckpointer:
    def test_get_checkpointer_creates_sqlite_saver(self, tmp_path):
        from src.agent.checkpoint import get_checkpointer

        db_path = str(tmp_path / "test_checkpoints.db")
        with get_checkpointer(db_path=db_path) as checkpointer:
            assert checkpointer is not None

    def test_get_checkpointer_creates_directory(self, tmp_path):
        from src.agent.checkpoint import get_checkpointer

        db_path = str(tmp_path / "subdir" / "checkpoints.db")
        with get_checkpointer(db_path=db_path) as checkpointer:
            assert checkpointer is not None

    def test_get_checkpointer_reads_config(self):
        from unittest.mock import patch

        from src.agent.checkpoint import get_checkpointer

        with (
            patch(
                "src.agent.config.get_checkpoint_config",
                return_value={"db_path": "data/test_agent_checkpoints.db"},
            ),
            patch("langgraph.checkpoint.sqlite.SqliteSaver") as mock_saver_cls,
        ):
            mock_saver = MagicMock()
            mock_saver_cls.from_conn_string.return_value.__enter__ = MagicMock(
                return_value=mock_saver
            )
            mock_saver_cls.from_conn_string.return_value.__exit__ = MagicMock(
                return_value=False
            )
            with get_checkpointer() as checkpointer:
                assert checkpointer is not None


class TestGetCheckpointerDirect:
    def test_get_checkpointer_direct_creates_sqlite_saver(self, tmp_path):
        from src.agent.checkpoint import get_checkpointer_direct

        db_path = str(tmp_path / "test_direct.db")
        checkpointer = get_checkpointer_direct(db_path=db_path)
        assert checkpointer is not None
        assert checkpointer.conn is not None
        checkpointer.conn.close()

    def test_get_checkpointer_direct_creates_directory(self, tmp_path):
        from src.agent.checkpoint import get_checkpointer_direct

        db_path = str(tmp_path / "subdir" / "direct_checkpoints.db")
        checkpointer = get_checkpointer_direct(db_path=db_path)
        assert checkpointer is not None
        checkpointer.conn.close()

    def test_get_checkpointer_direct_reads_config(self):
        from unittest.mock import patch

        from src.agent.checkpoint import get_checkpointer_direct

        with patch(
            "src.agent.config.get_checkpoint_config",
            return_value={"db_path": "data/test_direct_checkpoints.db"},
        ):
            checkpointer = get_checkpointer_direct()
            assert checkpointer is not None
            checkpointer.conn.close()

    def test_get_checkpointer_direct_connection_alive_after_return(self, tmp_path):
        from src.agent.checkpoint import get_checkpointer_direct

        db_path = str(tmp_path / "test_alive.db")
        checkpointer = get_checkpointer_direct(db_path=db_path)
        cursor = checkpointer.conn.cursor()
        cursor.execute("SELECT 1")
        result = cursor.fetchone()
        assert result == (1,)
        checkpointer.conn.close()


class TestCheckpointConfig:
    def test_get_checkpoint_config_returns_section(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_config, get_checkpoint_config

        get_agent_config.cache_clear()
        with patch(
            "src.utils.load_config",
            return_value={"agent": {"checkpoint": {"db_path": "data/test.db"}}},
        ):
            result = get_checkpoint_config()
            assert result == {"db_path": "data/test.db"}

    def test_get_checkpoint_config_returns_empty_when_missing(self):
        from unittest.mock import patch

        from src.agent.config import get_agent_config, get_checkpoint_config

        get_agent_config.cache_clear()
        with patch("src.utils.load_config", return_value={"agent": {}}):
            result = get_checkpoint_config()
            assert result == {}


class TestSessionPersistence:
    def test_sqlite_saver_persists_across_invocations(self, tmp_path):
        from langgraph.checkpoint.sqlite import SqliteSaver

        from src.agent.graph import compile_agent

        db_path = str(tmp_path / "test_session.db")
        with SqliteSaver.from_conn_string(db_path) as checkpointer:
            agent = compile_agent(checkpointer=checkpointer)

            config = {"configurable": {"thread_id": "test-session-1"}}

            checkpoint_before = agent.get_state(config)
            assert checkpoint_before is not None

    def test_session_id_from_cli_args(self):
        from src.agent.cli import _parse_cli_args

        args = _parse_cli_args(["--session-id", "my-session"])
        assert args.session_id == "my-session"

    def test_pdf_from_cli_args(self):
        from src.agent.cli import _parse_cli_args

        args = _parse_cli_args(["--pdf", "data/raw/test.pdf"])
        assert args.pdf == "data/raw/test.pdf"

    def test_default_cli_args(self):
        from src.agent.cli import _parse_cli_args

        args = _parse_cli_args([])
        assert args.session_id is None
        assert args.pdf is None
