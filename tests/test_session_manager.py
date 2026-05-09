from __future__ import annotations

import time
from unittest.mock import MagicMock

import pytest

from src.agent.session_manager import SessionManager

pytestmark = pytest.mark.unit


class TestCreateSession:
    def test_returns_dict_with_expected_keys(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session()
        assert set(session.keys()) == {
            "session_id",
            "thread_id",
            "title",
            "created_at",
            "updated_at",
            "message_count",
            "is_archived",
        }

    def test_session_id_format(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session()
        assert session["session_id"].startswith("sess_")
        assert len(session["session_id"]) == 17

    def test_thread_id_format(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session()
        assert session["thread_id"].startswith("maintenance-")
        assert len(session["thread_id"]) == 20

    def test_default_title(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session()
        assert session["title"] == "新对话"

    def test_custom_title(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session(title="测试对话")
        assert session["title"] == "测试对话"

    def test_default_message_count_is_zero(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session()
        assert session["message_count"] == 0

    def test_default_is_archived_is_zero(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session()
        assert session["is_archived"] == 0

    def test_created_at_equals_updated_at(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session()
        assert session["created_at"] == session["updated_at"]

    def test_persists_to_database(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        session = sm.create_session()
        retrieved = sm.get_session(session["session_id"])
        assert retrieved is not None
        assert retrieved["session_id"] == session["session_id"]

    def test_unique_session_ids(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        s1 = sm.create_session()
        s2 = sm.create_session()
        assert s1["session_id"] != s2["session_id"]
        assert s1["thread_id"] != s2["thread_id"]


class TestListSessions:
    def test_empty_list(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        assert sm.list_sessions() == []

    def test_returns_all_sessions(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        sm.create_session()
        sm.create_session()
        sessions = sm.list_sessions(include_archived=True)
        assert len(sessions) == 2

    def test_ordered_by_updated_at_desc(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        s1 = sm.create_session()
        time.sleep(1.1)
        s2 = sm.create_session()
        sessions = sm.list_sessions(include_archived=True)
        assert sessions[0]["session_id"] == s2["session_id"]
        assert sessions[1]["session_id"] == s1["session_id"]

    def test_excludes_archived_by_default(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        s1 = sm.create_session()
        s2 = sm.create_session()
        sm.archive_session(s2["session_id"])
        sessions = sm.list_sessions()
        assert len(sessions) == 1
        assert sessions[0]["session_id"] == s1["session_id"]

    def test_includes_archived_when_flag_set(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        sm.create_session()
        s2 = sm.create_session()
        sm.archive_session(s2["session_id"])
        sessions = sm.list_sessions(include_archived=True)
        assert len(sessions) == 2


class TestGetSession:
    def test_found(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        retrieved = sm.get_session(created["session_id"])
        assert retrieved is not None
        assert retrieved["session_id"] == created["session_id"]
        assert retrieved["thread_id"] == created["thread_id"]
        assert retrieved["title"] == created["title"]

    def test_not_found(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        assert sm.get_session("sess_nonexistent") is None

    def test_returns_dict(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        retrieved = sm.get_session(created["session_id"])
        assert isinstance(retrieved, dict)


class TestGetSessionByThreadId:
    def test_found(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        retrieved = sm.get_session_by_thread_id(created["thread_id"])
        assert retrieved is not None
        assert retrieved["session_id"] == created["session_id"]
        assert retrieved["thread_id"] == created["thread_id"]

    def test_not_found(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        assert sm.get_session_by_thread_id("maintenance-nonexist") is None

    def test_returns_dict(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        retrieved = sm.get_session_by_thread_id(created["thread_id"])
        assert isinstance(retrieved, dict)


class TestUpdateSession:
    def test_update_title(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.update_session(created["session_id"], title="新标题")
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["title"] == "新标题"

    def test_update_is_archived(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.update_session(created["session_id"], is_archived=1)
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["is_archived"] == 1

    def test_update_message_count(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.update_session(created["session_id"], message_count=5)
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["message_count"] == 5

    def test_updated_at_auto_updates(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        original_updated_at = created["updated_at"]
        time.sleep(0.05)
        sm.update_session(created["session_id"], title="changed")
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["updated_at"] != original_updated_at

    def test_raises_on_no_allowed_fields(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        with pytest.raises(ValueError, match="No updatable fields"):
            sm.update_session(created["session_id"], foo="bar")

    def test_ignores_disallowed_fields(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.update_session(created["session_id"], title="valid", created_at="hacked")
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["session_id"] == created["session_id"]
        assert retrieved["title"] == "valid"
        assert retrieved["created_at"] == created["created_at"]

    def test_multiple_fields_at_once(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.update_session(
            created["session_id"], title="combo", is_archived=1, message_count=3
        )
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["title"] == "combo"
        assert retrieved["is_archived"] == 1
        assert retrieved["message_count"] == 3


class TestDeleteSession:
    def test_delete_removes_session(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.delete_session(created["session_id"])
        assert sm.get_session(created["session_id"]) is None

    def test_delete_does_not_affect_other_sessions(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        s1 = sm.create_session()
        s2 = sm.create_session()
        sm.delete_session(s1["session_id"])
        assert sm.get_session(s1["session_id"]) is None
        assert sm.get_session(s2["session_id"]) is not None

    def test_delete_nonexistent_does_not_raise(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        sm.delete_session("sess_nonexistent")


class TestArchiveUnarchiveSession:
    def test_archive_sets_is_archived(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.archive_session(created["session_id"])
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["is_archived"] == 1

    def test_unarchive_clears_is_archived(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.archive_session(created["session_id"])
        sm.unarchive_session(created["session_id"])
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["is_archived"] == 0

    def test_archive_excludes_from_default_list(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.archive_session(created["session_id"])
        sessions = sm.list_sessions()
        assert len(sessions) == 0

    def test_unarchive_includes_in_default_list(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.archive_session(created["session_id"])
        sm.unarchive_session(created["session_id"])
        sessions = sm.list_sessions()
        assert len(sessions) == 1


class TestTouchSession:
    def test_updates_updated_at(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        original_updated_at = created["updated_at"]
        time.sleep(0.05)
        sm.touch_session(created["session_id"])
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["updated_at"] != original_updated_at

    def test_does_not_change_other_fields(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session(title="不变")
        sm.touch_session(created["session_id"])
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["title"] == "不变"
        assert retrieved["created_at"] == created["created_at"]
        assert retrieved["message_count"] == 0
        assert retrieved["is_archived"] == 0

    def test_touch_affects_list_ordering(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        s1 = sm.create_session()
        time.sleep(1.1)
        s2 = sm.create_session()
        sessions = sm.list_sessions(include_archived=True)
        assert sessions[0]["session_id"] == s2["session_id"]
        time.sleep(1.1)
        sm.touch_session(s1["session_id"])
        sessions = sm.list_sessions(include_archived=True)
        assert sessions[0]["session_id"] == s1["session_id"]


class TestAutoTitle:
    def test_short_message(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.auto_title(created["session_id"], "你好世界")
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["title"] == "你好世界"

    def test_long_message_truncated_to_20(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        long_msg = "这是一条非常长的消息用于测试自动标题截断功能应该只取前二十个字符"
        sm.auto_title(created["session_id"], long_msg)
        retrieved = sm.get_session(created["session_id"])
        assert len(retrieved["title"]) == 20
        assert retrieved["title"] == long_msg[:20]

    def test_exactly_20_chars(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        msg = "a" * 20
        sm.auto_title(created["session_id"], msg)
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["title"] == msg

    def test_empty_message(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm.auto_title(created["session_id"], "")
        retrieved = sm.get_session(created["session_id"])
        assert retrieved["title"] == ""


class TestDuplicateSession:
    def test_creates_new_session(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        original = sm.create_session(title="原始对话")
        duplicated = sm.duplicate_session(original["session_id"])
        assert duplicated is not None
        assert duplicated["session_id"] != original["session_id"]
        assert duplicated["thread_id"] != original["thread_id"]

    def test_default_title_has_copy_suffix(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        original = sm.create_session(title="原始对话")
        duplicated = sm.duplicate_session(original["session_id"])
        assert duplicated["title"] == "原始对话 (副本)"

    def test_custom_title(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        original = sm.create_session(title="原始对话")
        duplicated = sm.duplicate_session(
            original["session_id"], new_title="自定义标题"
        )
        assert duplicated["title"] == "自定义标题"

    def test_returns_none_for_nonexistent_source(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        result = sm.duplicate_session("sess_nonexistent")
        assert result is None

    def test_without_agent_does_not_call_agent(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        original = sm.create_session(title="测试")
        mock_agent = MagicMock()
        sm.duplicate_session(original["session_id"], agent=mock_agent)
        mock_agent.get_state.assert_called_once()
        mock_agent.update_state.assert_called_once()

    def test_without_agent_skips_state_seeding(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        original = sm.create_session(title="测试")
        mock_agent = MagicMock()
        mock_agent.get_state.return_value = MagicMock(values={"key": "val"})
        sm.duplicate_session(original["session_id"], agent=mock_agent)
        mock_agent.get_state.assert_called_once()
        mock_agent.update_state.assert_called_once()

    def test_agent_error_does_not_prevent_creation(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        original = sm.create_session(title="测试")
        mock_agent = MagicMock()
        mock_agent.get_state.side_effect = RuntimeError("agent error")
        duplicated = sm.duplicate_session(original["session_id"], agent=mock_agent)
        assert duplicated is not None
        assert duplicated["session_id"] != original["session_id"]

    def test_new_session_has_fresh_defaults(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        original = sm.create_session(title="原始")
        sm.update_session(original["session_id"], message_count=10, is_archived=1)
        duplicated = sm.duplicate_session(original["session_id"])
        assert duplicated["message_count"] == 0
        assert duplicated["is_archived"] == 0


class TestMigrateOrphanCheckpoints:
    def test_migrates_orphan_threads(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        mock_checkpointer = MagicMock()
        mock_tuple1 = MagicMock()
        mock_tuple1.config = {"configurable": {"thread_id": "maintenance-abc12345"}}
        mock_tuple2 = MagicMock()
        mock_tuple2.config = {"configurable": {"thread_id": "maintenance-def67890"}}
        mock_checkpointer.list.return_value = [mock_tuple1, mock_tuple2]
        count = sm._migrate_orphan_checkpoints(mock_checkpointer)
        assert count == 2

    def test_skips_if_sessions_not_empty(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        sm.create_session()
        mock_checkpointer = MagicMock()
        count = sm._migrate_orphan_checkpoints(mock_checkpointer)
        assert count == 0
        mock_checkpointer.list.assert_not_called()

    def test_skips_threads_without_thread_id(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        mock_checkpointer = MagicMock()
        mock_tuple = MagicMock()
        mock_tuple.config = {"configurable": {}}
        mock_checkpointer.list.return_value = [mock_tuple]
        count = sm._migrate_orphan_checkpoints(mock_checkpointer)
        assert count == 0

    def test_skips_already_existing_thread(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        created = sm.create_session()
        sm._conn.execute("DELETE FROM sessions")
        sm._conn.commit()
        sm2 = SessionManager(str(tmp_path / "test2.db"))
        sm2.create_session()
        mock_checkpointer = MagicMock()
        mock_tuple = MagicMock()
        mock_tuple.config = {"configurable": {"thread_id": created["thread_id"]}}
        mock_checkpointer.list.return_value = [mock_tuple]
        sm._conn.execute("DELETE FROM sessions")
        sm._conn.commit()
        count = sm._migrate_orphan_checkpoints(mock_checkpointer)
        assert count == 1

    def test_migrated_session_title(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        mock_checkpointer = MagicMock()
        mock_tuple = MagicMock()
        mock_tuple.config = {"configurable": {"thread_id": "maintenance-xyz99999"}}
        mock_checkpointer.list.return_value = [mock_tuple]
        sm._migrate_orphan_checkpoints(mock_checkpointer)
        session = sm.get_session_by_thread_id("maintenance-xyz99999")
        assert session is not None
        assert session["title"] == "已迁移对话"

    def test_migrated_session_id_format(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        mock_checkpointer = MagicMock()
        mock_tuple = MagicMock()
        mock_tuple.config = {"configurable": {"thread_id": "maintenance-test1234"}}
        mock_checkpointer.list.return_value = [mock_tuple]
        sm._migrate_orphan_checkpoints(mock_checkpointer)
        session = sm.get_session_by_thread_id("maintenance-test1234")
        assert session is not None
        assert session["session_id"].startswith("sess_")

    def test_empty_checkpointer_returns_zero(self, tmp_path):
        sm = SessionManager(str(tmp_path / "test.db"))
        mock_checkpointer = MagicMock()
        mock_checkpointer.list.return_value = []
        count = sm._migrate_orphan_checkpoints(mock_checkpointer)
        assert count == 0


class TestDatabaseIsolation:
    def test_separate_databases_are_independent(self, tmp_path):
        sm1 = SessionManager(str(tmp_path / "db1.db"))
        sm2 = SessionManager(str(tmp_path / "db2.db"))
        s1 = sm1.create_session(title="DB1")
        assert sm2.list_sessions() == []
        assert sm1.get_session(s1["session_id"]) is not None
        assert sm2.get_session(s1["session_id"]) is None

    def test_table_created_automatically(self, tmp_path):
        db_path = str(tmp_path / "auto_create.db")
        sm = SessionManager(db_path)
        sm.create_session()
        import sqlite3

        conn = sqlite3.connect(db_path)
        cursor = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='sessions'"
        )
        assert cursor.fetchone() is not None
        conn.close()
