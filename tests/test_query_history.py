import json
from typing import Any

import pytest

from src.query_history import QueryHistory


def _make_result(
    question: str = "测试问题", answer: str = "测试答案"
) -> dict[str, Any]:
    return {
        "question": question,
        "answer": answer,
        "contexts": ["context1"],
        "scores": [0.9],
        "sources": ["source1.pdf"],
        "chunk_ids": ["c1"],
        "token_usage": {"input_tokens": 100, "output_tokens": 50, "total_tokens": 150},
    }


@pytest.mark.unit
class TestQueryHistoryAdd:
    def test_add_creates_history_file(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        rid = h.add("问题1", _make_result(), meal_name="test_meal")
        assert rid.startswith("qh_")
        assert (tmp_path / "history.json").exists()

    def test_add_creates_result_file(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        rid = h.add("问题1", _make_result(question="问题1"))
        result_path = tmp_path / f"{rid}_result.json"
        assert result_path.exists()
        data = json.loads(result_path.read_text(encoding="utf-8"))
        assert data["question"] == "问题1"

    def test_add_sequential_ids(self, tmp_path):
        h = QueryHistory(max_entries=10, history_dir=tmp_path)
        id1 = h.add("问题1", _make_result())
        id2 = h.add("问题2", _make_result())
        id3 = h.add("问题3", _make_result())
        assert id1 == "qh_0001"
        assert id2 == "qh_0002"
        assert id3 == "qh_0003"

    def test_add_stores_metadata(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        rid = h.add(
            "问题1",
            _make_result(),
            meal_name="my_meal",
            llm_preset="opus",
            config_overrides={"retrieval": {"top_k": 10}},
        )
        records = h._load_history()
        rec = records[0]
        assert rec["id"] == rid
        assert rec["question"] == "问题1"
        assert rec["meal_name"] == "my_meal"
        assert rec["llm_preset"] == "opus"
        assert rec["saved_case_type"] is None
        assert rec["config_overrides"] == {"retrieval": {"top_k": 10}}


@pytest.mark.unit
class TestQueryHistoryEviction:
    def test_evict_oldest_when_exceeds_max(self, tmp_path):
        h = QueryHistory(max_entries=3, history_dir=tmp_path)
        id1 = h.add("问题1", _make_result())
        h.add("问题2", _make_result())
        h.add("问题3", _make_result())
        id4 = h.add("问题4", _make_result())

        records = h._load_history()
        assert len(records) == 3
        ids = [r["id"] for r in records]
        assert id1 not in ids
        assert id4 in ids

    def test_evict_deletes_result_file(self, tmp_path):
        h = QueryHistory(max_entries=2, history_dir=tmp_path)
        id1 = h.add("问题1", _make_result())
        h.add("问题2", _make_result())
        h.add("问题3", _make_result())

        result_path = tmp_path / f"{id1}_result.json"
        assert not result_path.exists()

    def test_evict_keeps_latest_result_files(self, tmp_path):
        h = QueryHistory(max_entries=2, history_dir=tmp_path)
        h.add("问题1", _make_result())
        id2 = h.add("问题2", _make_result())
        id3 = h.add("问题3", _make_result())

        assert (tmp_path / f"{id2}_result.json").exists()
        assert (tmp_path / f"{id3}_result.json").exists()


@pytest.mark.unit
class TestQueryHistoryListRecent:
    def test_list_recent_returns_newest_first(self, tmp_path):
        h = QueryHistory(max_entries=10, history_dir=tmp_path)
        h.add("问题1", _make_result())
        h.add("问题2", _make_result())
        h.add("问题3", _make_result())

        recent = h.list_recent()
        assert len(recent) == 3
        assert recent[0]["question"] == "问题3"
        assert recent[2]["question"] == "问题1"

    def test_list_recent_with_limit(self, tmp_path):
        h = QueryHistory(max_entries=10, history_dir=tmp_path)
        h.add("问题1", _make_result())
        h.add("问题2", _make_result())
        h.add("问题3", _make_result())

        recent = h.list_recent(limit=2)
        assert len(recent) == 2

    def test_list_recent_empty(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        recent = h.list_recent()
        assert recent == []


@pytest.mark.unit
class TestQueryHistoryGet:
    def test_get_returns_full_record(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        rid = h.add("问题1", _make_result(answer="详细答案内容"))

        record = h.get(rid)
        assert record is not None
        assert record["id"] == rid
        assert record["query_result"] is not None
        assert record["query_result"]["answer"] == "详细答案内容"

    def test_get_returns_none_for_missing(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        assert h.get("qh_9999") is None


@pytest.mark.unit
class TestQueryHistoryMarkSaved:
    def test_mark_saved_updates_record(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        rid = h.add("问题1", _make_result())

        h.mark_saved(rid, "bad", "bc_20260503_143000_a1b2c3")

        saved_type, saved_id = h.check_saved(rid)
        assert saved_type == "bad"
        assert saved_id == "bc_20260503_143000_a1b2c3"

    def test_check_saved_returns_none_initially(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        rid = h.add("问题1", _make_result())

        saved_type, saved_id = h.check_saved(rid)
        assert saved_type is None
        assert saved_id is None

    def test_check_saved_missing_record(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        saved_type, saved_id = h.check_saved("qh_9999")
        assert saved_type is None
        assert saved_id is None

    def test_mark_saved_good_type(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        rid = h.add("问题1", _make_result())

        h.mark_saved(rid, "good", "gc_20260503_143500_d4e5f6")

        saved_type, saved_id = h.check_saved(rid)
        assert saved_type == "good"
        assert saved_id == "gc_20260503_143500_d4e5f6"


@pytest.mark.unit
class TestQueryHistoryClearSaved:
    def test_clear_saved_resets_marker(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        rid = h.add("问题1", _make_result())

        h.mark_saved(rid, "bad", "bc_20260503_143000_a1b2c3")
        h.clear_saved(rid)

        saved_type, saved_id = h.check_saved(rid)
        assert saved_type is None
        assert saved_id is None


@pytest.mark.unit
class TestQueryHistoryAnswerPreview:
    def test_long_answer_is_truncated(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        long_answer = "A" * 200
        h.add("问题1", _make_result(answer=long_answer))

        records = h._load_history()
        assert records[0]["answer_preview"].endswith("...")
        assert len(records[0]["answer_preview"]) < len(long_answer)

    def test_short_answer_not_truncated(self, tmp_path):
        h = QueryHistory(max_entries=5, history_dir=tmp_path)
        short_answer = "简短答案"
        h.add("问题1", _make_result(answer=short_answer))

        records = h._load_history()
        assert not records[0]["answer_preview"].endswith("...")
        assert records[0]["answer_preview"] == short_answer
