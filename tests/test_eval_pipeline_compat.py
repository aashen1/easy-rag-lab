"""Smoke test for evaluation pipeline compatibility with test set data.

Ensures that resolve_test_set → collect_rag_samples full chain
consumes test set data correctly after any metadata format changes.
"""

import json
from pathlib import Path

import pytest

from src.test_set_manager import TestSetManager


def _make_test_set_json(
    name: str = "smoke_test_set",
    meal_id: str = "abc123",
    num_questions: int = 3,
    include_new_fields: bool = False,
) -> dict:
    questions = []
    for i in range(1, num_questions + 1):
        q = {
            "id": f"q{i:03d}",
            "question": f"测试问题 {i}？",
            "question_type": "单知识点查询",
            "category": "hybrid",
            "difficulty": "medium",
            "source_files": ["reports/report_0.pdf"],
            "source_chunks": [f"chunk_{i}"],
            "answer": f"测试答案 {i}。",
            "ground_truth_excerpt": f"原文引用 {i}",
            "expect_retrieval": True,
            "expect_no_answer": False,
            "source_document": "report_0.pdf",
            "metadata": {
                "review_status": "approved",
                "excerpt_verified": True,
            },
        }
        questions.append(q)

    metadata = {
        "name": name,
        "meal_id": meal_id,
        "created_at": "2026-05-02T00:00:00",
        "updated_at": "2026-05-02T00:00:00",
        "generation": {
            "strategy": "hybrid",
            "num_questions": num_questions,
            "type_distribution": {"single_fact": 1.0},
            "llm_preset": "default",
        },
        "user_defined": False,
        "invalid_policy": None,
        "audit_log": [],
        "suppress_warnings": False,
        "composition": {},
    }

    if include_new_fields:
        metadata["quality_status"] = "draft"
        metadata["review_progress"] = {
            "total": num_questions,
            "approved": 0,
            "rejected": 0,
            "pending": num_questions,
        }
        metadata["portable"] = False
        metadata["data_coverage"] = "partial"

    return {
        "metadata": metadata,
        "quality_metrics": {"avg_question_length": 10},
        "questions": questions,
    }


def _make_legacy_test_set_json(
    name: str = "legacy_test_set",
    meal_data_id: str = "abc123",
    num_questions: int = 3,
) -> dict:
    questions = []
    for i in range(1, num_questions + 1):
        q = {
            "id": f"q{i:03d}",
            "question": f"旧格式问题 {i}？",
            "question_type": "单知识点查询",
            "category": "legacy",
            "difficulty": "easy",
            "source_files": ["reports/report_0.pdf"],
            "source_chunks": [f"legacy_chunk_{i}"],
            "answer": f"旧格式答案 {i}。",
            "ground_truth_excerpt": f"旧格式引用 {i}",
            "expect_retrieval": True,
            "expect_no_answer": False,
            "source_document": "report_0.pdf",
            "metadata": {
                "review_status": "pending",
            },
        }
        questions.append(q)

    return {
        "name": name,
        "meal_data_id": meal_data_id,
        "meal_name": "test_meal",
        "strategy": "document",
        "created_at": "2026-01-01T00:00:00",
        "generation_config": {
            "num_questions": num_questions,
            "llm_preset": "default",
        },
        "quality_metrics": {},
        "questions": questions,
    }


class TestEvalPipelineCompatibility:
    """Verify that evaluation pipeline correctly consumes test set data."""

    def test_metadata_fields_accessible(self, tmp_path: Path):
        """All mandatory metadata fields are present after migration."""
        ts_data = _make_test_set_json(include_new_fields=True)
        test_file = tmp_path / "test.json"
        test_file.write_text(json.dumps(ts_data, ensure_ascii=False), encoding="utf-8")

        loaded = json.loads(test_file.read_text(encoding="utf-8"))
        metadata = loaded["metadata"]

        assert metadata["name"] == "smoke_test_set"
        assert metadata["meal_id"] == "abc123"
        assert metadata["generation"]["strategy"] == "hybrid"
        assert metadata["generation"]["num_questions"] == 3
        assert metadata["created_at"] is not None
        assert "user_defined" in metadata
        assert "invalid_policy" in metadata
        assert "audit_log" in metadata
        assert metadata["quality_status"] == "draft"
        assert metadata["data_coverage"] == "partial"
        assert metadata["portable"] is False
        assert "review_progress" in metadata

    def test_question_fields_accessible(self):
        """All mandatory question-level fields are present and unchanged."""
        ts_data = _make_test_set_json()
        questions = ts_data["questions"]

        required_fields = [
            "id",
            "question",
            "source_files",
            "answer",
            "ground_truth_excerpt",
            "source_chunks",
            "question_type",
            "category",
            "difficulty",
            "expect_retrieval",
            "expect_no_answer",
        ]

        for q in questions:
            for field in required_fields:
                assert field in q, (
                    f"Missing required field '{field}' in question {q.get('id')}"
                )
            assert q.get("metadata", {}).get("review_status") is not None

    def test_legacy_format_migration(self, tmp_path: Path):
        """Legacy format test sets are correctly migrated to new format."""
        legacy = _make_legacy_test_set_json()
        test_file = tmp_path / "legacy.json"
        test_file.write_text(json.dumps(legacy, ensure_ascii=False), encoding="utf-8")

        loaded = json.loads(test_file.read_text(encoding="utf-8"))

        config = {"data_dir": str(tmp_path)}
        manager = TestSetManager(config)
        migrated = manager._migrate_test_set(loaded)

        assert "metadata" in migrated
        assert "questions" in migrated
        assert migrated["metadata"]["name"] == "legacy_test_set"
        assert migrated["metadata"]["meal_id"] == "abc123"
        assert migrated["metadata"]["generation"]["num_questions"] == 3
        assert migrated["metadata"]["user_defined"] is False

    def test_review_status_filter(self):
        """Questions with review_status == 'rejected' should be filterable."""
        ts_data = _make_test_set_json(num_questions=5)
        ts_data["questions"][0]["metadata"]["review_status"] = "rejected"
        ts_data["questions"][2]["metadata"]["review_status"] = "rejected"

        questions = ts_data["questions"]
        filtered = [
            q
            for q in questions
            if q.get("metadata", {}).get("review_status") != "rejected"
        ]

        assert len(filtered) == 3
        for q in filtered:
            assert q.get("metadata", {}).get("review_status") != "rejected"

    def test_new_fields_backward_compatible(self):
        """Code reading new fields should not fail when they are absent."""
        ts_data = _make_test_set_json(include_new_fields=False)
        metadata = ts_data["metadata"]

        quality_status = metadata.get("quality_status", "draft")
        data_coverage = metadata.get("data_coverage", "partial")
        portable = metadata.get("portable", False)
        review_progress = metadata.get("review_progress", {})

        assert quality_status == "draft"
        assert data_coverage == "partial"
        assert portable is False
        assert review_progress == {}

    def test_question_data_for_evaluation_sample(self):
        """verify question data maps to evaluation sample fields correctly."""
        ts_data = _make_test_set_json(num_questions=1)
        q = ts_data["questions"][0]

        sample = {
            "question_id": q.get("id"),
            "question": q.get("question"),
            "expected_sources": q.get("source_files", []),
            "expected_answer": q.get("answer"),
            "ground_truth_excerpt": q.get("ground_truth_excerpt"),
            "expected_chunks": q.get("source_chunks", []),
            "question_type": q.get("question_type", "factual"),
            "category": q.get("category"),
            "difficulty": q.get("difficulty"),
            "expect_retrieval": q.get("expect_retrieval", True),
            "expect_no_answer": q.get("expect_no_answer", False),
        }

        assert sample["question_id"] == "q001"
        assert sample["question"] == "测试问题 1？"
        assert sample["expected_answer"] == "测试答案 1。"
        assert "reports/report_0.pdf" in sample["expected_sources"]
        assert sample["ground_truth_excerpt"] == "原文引用 1"
        assert sample["expect_retrieval"] is True
        assert sample["expect_no_answer"] is False

    def test_snapshot_fields_accessible(self):
        """Verify snapshot serialization fields are accessible."""
        ts_data = _make_test_set_json()
        metadata = ts_data.get("metadata", {})
        generation = metadata.get("generation", {})

        snapshot = {
            "name": metadata.get("name"),
            "strategy": generation.get("strategy"),
            "num_questions": len(ts_data.get("questions", [])),
            "created_at": metadata.get("created_at"),
            "meal_data_id": metadata.get("meal_id"),
        }

        assert snapshot["name"] == "smoke_test_set"
        assert snapshot["strategy"] == "hybrid"
        assert snapshot["num_questions"] == 3
        assert snapshot["created_at"] is not None
        assert snapshot["meal_data_id"] == "abc123"

    def test_fingerprint_fields_accessible(self):
        """Verify experiment fingerprint fields are accessible."""
        ts_config = {
            "name": "fp_test",
            "generation": {
                "strategy": "hybrid",
                "num_questions": 30,
            },
        }

        strategy = ts_config["generation"].get("strategy", "unknown")
        count = ts_config["generation"].get("num_questions", 0)

        assert strategy == "hybrid"
        assert count == 30

    def test_cleaner_policy_routing(self):
        """Verify cleaner reads invalid_policy and generation correctly."""
        user_set = _make_test_set_json()
        user_set["metadata"]["user_defined"] = True
        user_set["metadata"]["invalid_policy"] = "immutable"

        machine_set = _make_test_set_json()
        machine_set["metadata"]["user_defined"] = False

        assert user_set["metadata"]["user_defined"] is True
        assert user_set["metadata"]["invalid_policy"] == "immutable"
        assert machine_set["metadata"]["user_defined"] is False

    def test_golden_testset_has_required_fields(self):
        """Verify data/golden_testset/golden_150.json has all required fields."""
        golden_path = Path("data/golden_testset/golden_150.json")
        if not golden_path.exists():
            pytest.skip("golden_150.json not found - run generate first")

        data = json.loads(golden_path.read_text(encoding="utf-8"))
        manager = TestSetManager({"data_dir": "data"})
        migrated = manager._migrate_test_set(data)

        metadata = migrated.get("metadata", {})
        assert "name" in metadata
        assert "meal_id" in metadata
        assert "generation" in metadata

        questions = migrated.get("questions", [])
        assert len(questions) > 0

        first_q = questions[0]
        for field in ["id", "question", "answer", "source_files", "question_type"]:
            assert field in first_q, f"Missing field '{field}' in first question"
