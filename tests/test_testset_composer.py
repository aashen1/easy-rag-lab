from __future__ import annotations

from src.testset_composer import TestSetComposer


def _make_question(
    q_id: str,
    question: str,
    question_type: str = "single_fact",
    category: str = "hybrid",
    difficulty: str = "medium",
    review_status: str = "approved",
    source_files: list[str] | None = None,
) -> dict:
    return {
        "id": q_id,
        "question": question,
        "question_type": question_type,
        "category": category,
        "difficulty": difficulty,
        "source_files": source_files or ["reports/report_0.pdf"],
        "source_chunks": [f"chunk_{q_id}"],
        "answer": f"Answer for {question}",
        "ground_truth_excerpt": f"Excerpt for {q_id}",
        "expect_retrieval": True,
        "expect_no_answer": False,
        "metadata": {"review_status": review_status},
    }


def _make_test_set(
    name: str,
    questions: list[dict],
    meal_id: str = "test_meal",
) -> dict:
    return {
        "metadata": {
            "name": name,
            "meal_id": meal_id,
            "created_at": "2026-01-01T00:00:00",
            "updated_at": "2026-01-01T00:00:00",
            "generation": {"strategy": "hybrid", "num_questions": len(questions)},
            "user_defined": False,
            "invalid_policy": None,
            "audit_log": [],
            "suppress_warnings": False,
            "composition": {},
            "quality_status": "draft",
            "review_progress": {},
            "portable": False,
            "data_coverage": "partial",
        },
        "quality_metrics": {},
        "questions": questions,
    }


class TestComposeMerge:
    def test_merge_basic(self):
        composer = TestSetComposer()
        ts1 = _make_test_set(
            "set_a",
            [
                _make_question("q001", "What is risk?"),
                _make_question("q002", "What is return?"),
            ],
        )
        ts2 = _make_test_set(
            "set_b",
            [
                _make_question("q003", "What is liquidity?"),
            ],
        )

        result = composer.compose_merge([ts1, ts2], name="merged", meal_id="test_meal")

        assert len(result["questions"]) == 3
        assert result["metadata"]["name"] == "merged"
        assert result["metadata"]["composition"]["type"] == "merged"
        assert len(result["metadata"]["composition"]["sources"]) == 2

    def test_merge_dedup(self):
        composer = TestSetComposer()
        ts1 = _make_test_set(
            "set_a",
            [
                _make_question("q001", "What is risk?"),
            ],
        )
        ts2 = _make_test_set(
            "set_b",
            [
                _make_question("q001", "What is risk?"),
            ],
        )

        result = composer.compose_merge([ts1, ts2], name="merged", meal_id="test_meal")

        assert len(result["questions"]) == 1
        assert result["metadata"]["composition"]["duplicates_removed"] == 1

    def test_merge_empty_source(self):
        composer = TestSetComposer()
        ts1 = _make_test_set("set_a", [])
        ts2 = _make_test_set("set_b", [_make_question("q001", "Test?")])

        result = composer.compose_merge([ts1, ts2], name="merged", meal_id="test_meal")
        assert len(result["questions"]) == 1

    def test_merge_similar_not_identical(self):
        composer = TestSetComposer()
        ts1 = _make_test_set(
            "set_a",
            [
                _make_question("q001", "What is financial risk management?"),
            ],
        )
        ts2 = _make_test_set(
            "set_b",
            [
                _make_question("q002", "How does financial risk affect management?"),
            ],
        )

        result = composer.compose_merge([ts1, ts2], name="merged", meal_id="test_meal")
        assert len(result["questions"]) == 2


class TestComposeFilter:
    def test_filter_by_type(self):
        composer = TestSetComposer()
        ts = _make_test_set(
            "source",
            [
                _make_question("q001", "Q1?", question_type="single_fact"),
                _make_question("q002", "Q2?", question_type="multi_hop"),
                _make_question("q003", "Q3?", question_type="single_fact"),
            ],
        )

        result = composer.compose_filter(
            ts, question_types=["single_fact"], name="filtered"
        )
        assert len(result["questions"]) == 2
        for q in result["questions"]:
            assert q["question_type"] == "single_fact"

    def test_filter_by_review_status(self):
        composer = TestSetComposer()
        ts = _make_test_set(
            "source",
            [
                _make_question("q001", "Q1?", review_status="approved"),
                _make_question("q002", "Q2?", review_status="rejected"),
                _make_question("q003", "Q3?", review_status="approved"),
            ],
        )

        result = composer.compose_filter(
            ts, review_statuses=["approved"], name="filtered"
        )
        assert len(result["questions"]) == 2

    def test_filter_limit(self):
        composer = TestSetComposer()
        ts = _make_test_set(
            "source",
            [
                _make_question("q001", "Q1?"),
                _make_question("q002", "Q2?"),
                _make_question("q003", "Q3?"),
            ],
        )

        result = composer.compose_filter(ts, max_questions=2, name="limited")
        assert len(result["questions"]) == 2

    def test_filter_empty_result(self):
        composer = TestSetComposer()
        ts = _make_test_set(
            "source",
            [
                _make_question("q001", "Q1?", question_type="single_fact"),
            ],
        )

        result = composer.compose_filter(
            ts, question_types=["multi_hop"], name="filtered"
        )
        assert len(result["questions"]) == 0


class TestComposeIncremental:
    def test_incremental_basic(self):
        composer = TestSetComposer()
        base = _make_test_set(
            "base",
            [
                _make_question("q001", "What is risk?"),
            ],
        )
        new_qs = [
            _make_question("q002", "What is return?"),
            _make_question("q003", "What is liquidity?"),
        ]

        result = composer.compose_incremental(
            base, new_qs, name="extended", meal_id="test_meal"
        )

        assert len(result["questions"]) == 3
        assert result["metadata"]["composition"]["type"] == "incremental"

    def test_incremental_duplicate_new(self):
        composer = TestSetComposer()
        base = _make_test_set(
            "base",
            [
                _make_question("q001", "What is risk?"),
            ],
        )
        new_qs = [
            _make_question("q001", "What is risk?"),
        ]

        result = composer.compose_incremental(
            base, new_qs, name="extended", meal_id="test_meal"
        )
        assert len(result["questions"]) == 1
        assert result["metadata"]["composition"]["duplicates_removed"] == 1

    def test_incremental_preserves_base_review_status(self):
        composer = TestSetComposer()
        base = _make_test_set(
            "base",
            [
                _make_question("q001", "Q1?", review_status="approved"),
            ],
        )
        new_qs = [
            _make_question("q002", "Q2?", review_status="pending"),
        ]

        result = composer.compose_incremental(
            base, new_qs, name="extended", meal_id="test_meal"
        )
        assert len(result["questions"]) == 2
        statuses = {
            q["id"]: q["metadata"]["review_status"] for q in result["questions"]
        }
        assert statuses["q001"] == "approved"
        assert statuses["q002"] == "pending"
