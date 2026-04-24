import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.generate_golden_testset import (
    GOLDEN_QUESTION_TYPES,
    GOLDEN_TYPE_DISTRIBUTION,
    calculate_type_counts,
    distribute_across_documents,
    extract_excerpt_core,
    extract_key_terms_from_excerpt,
    locate_source_chunks,
    parse_question_response,
    validate_question_quality,
    verify_excerpt_in_document,
)
from src.exceptions import TestSetError
from src.test_set_manager import TestSetManager


class TestGoldenSchema:
    def test_golden_question_types_defined(self):
        assert "adversarial" in GOLDEN_QUESTION_TYPES
        assert len(GOLDEN_QUESTION_TYPES) == 7

    def test_golden_type_distribution_sums_approximately_to_one(self):
        total = sum(GOLDEN_TYPE_DISTRIBUTION.values())
        assert abs(total - 1.0) < 0.05

    def test_golden_type_distribution_has_all_types(self):
        for q_type in GOLDEN_QUESTION_TYPES:
            assert q_type in GOLDEN_TYPE_DISTRIBUTION

    def test_type_counts_sum_to_target(self):
        counts = calculate_type_counts(150, GOLDEN_TYPE_DISTRIBUTION)
        assert sum(counts.values()) == 150

    def test_type_counts_all_types_present(self):
        counts = calculate_type_counts(150, GOLDEN_TYPE_DISTRIBUTION)
        for q_type in GOLDEN_QUESTION_TYPES:
            assert q_type in counts
            assert counts[q_type] >= 0

    def test_type_counts_small_number(self):
        counts = calculate_type_counts(10, GOLDEN_TYPE_DISTRIBUTION)
        assert sum(counts.values()) == 10


class TestDistributeAcrossDocuments:
    def test_basic_distribution(self):
        docs = [
            {"name": "doc_a", "content": "a"},
            {"name": "doc_b", "content": "b"},
            {"name": "doc_c", "content": "c"},
        ]
        type_counts = {"single_fact": 6, "reasoning": 3}
        result = distribute_across_documents(type_counts, docs)
        total = sum(len(v) for v in result.values())
        assert total == 9

    def test_single_document(self):
        docs = [{"name": "doc_a", "content": "a"}]
        type_counts = {"single_fact": 5}
        result = distribute_across_documents(type_counts, docs)
        assert len(result["doc_a"]) == 5

    def test_more_questions_than_docs(self):
        docs = [{"name": "doc_a", "content": "a"}, {"name": "doc_b", "content": "b"}]
        type_counts = {"single_fact": 10}
        result = distribute_across_documents(type_counts, docs)
        total = sum(len(v) for v in result.values())
        assert total == 10


class TestParseQuestionResponse:
    def test_valid_response(self):
        response = '{"question": "营收多少？", "answer": "100亿", "question_type": "single_fact", "ground_truth_excerpt": "公司营收100亿元", "difficulty": "easy"}'
        result = parse_question_response(response)
        assert result is not None
        assert result["question"] == "营收多少？"
        assert result["answer"] == "100亿"
        assert result["ground_truth_excerpt"] == "公司营收100亿元"

    def test_missing_required_field(self):
        response = '{"question": "营收多少？", "answer": "100亿"}'
        result = parse_question_response(response)
        assert result is None

    def test_empty_question(self):
        response = '{"question": "", "answer": "100亿", "question_type": "single_fact", "ground_truth_excerpt": "xxx"}'
        result = parse_question_response(response)
        assert result is None

    def test_markdown_wrapped_response(self):
        response = '```json\n{"question": "营收多少？", "answer": "100亿", "question_type": "single_fact", "ground_truth_excerpt": "xxx"}\n```'
        result = parse_question_response(response)
        assert result is not None

    def test_defaults_populated(self):
        response = '{"question": "营收多少？", "answer": "100亿", "question_type": "single_fact", "ground_truth_excerpt": "xxx"}'
        result = parse_question_response(response)
        assert result["difficulty"] == "medium"
        assert result["key_entities"] == []
        assert result["target_failure_mode"] == ""


class TestValidateQuestionQuality:
    def test_valid_question(self):
        q = {
            "question": "营收多少？",
            "answer": "100亿",
            "ground_truth_excerpt": "公司营收100亿元",
            "question_type": "single_fact",
        }
        assert validate_question_quality(q) is True

    def test_too_short_question(self):
        q = {
            "question": "啥",
            "answer": "100亿",
            "ground_truth_excerpt": "xxx",
            "question_type": "single_fact",
        }
        assert validate_question_quality(q) is False

    def test_too_long_question(self):
        q = {
            "question": "x" * 201,
            "answer": "100亿",
            "ground_truth_excerpt": "xxx",
            "question_type": "single_fact",
        }
        assert validate_question_quality(q) is False

    def test_academic_pattern_rejected(self):
        q = {
            "question": "根据文档，营收多少？",
            "answer": "100亿",
            "ground_truth_excerpt": "xxx",
            "question_type": "single_fact",
        }
        assert validate_question_quality(q) is False

    def test_irrelevant_without_excerpt_ok(self):
        q = {
            "question": "新能源汽车怎么样？",
            "answer": "无关",
            "ground_truth_excerpt": "",
            "question_type": "irrelevant",
        }
        assert validate_question_quality(q) is True

    def test_non_irrelevant_without_excerpt_rejected(self):
        q = {
            "question": "营收多少？",
            "answer": "100亿",
            "ground_truth_excerpt": "",
            "question_type": "single_fact",
        }
        assert validate_question_quality(q) is False


class TestVerifyExcerptInDocument:
    def test_exact_match(self):
        doc = "公司2024年营收达到100亿元，同比增长15%。"
        excerpt = "营收达到100亿元"
        assert verify_excerpt_in_document(excerpt, doc) is True

    def test_no_match(self):
        doc = "公司2024年利润达到50亿元。"
        excerpt = "营收达到100亿元，同比增长15%"
        assert verify_excerpt_in_document(excerpt, doc) is False

    def test_whitespace_ignored(self):
        doc = "公司 2024年 营收 达到 100亿元"
        excerpt = "公司2024年营收达到100亿元"
        assert verify_excerpt_in_document(excerpt, doc) is True

    def test_partial_overlap(self):
        doc = "公司2024年营收达到100亿元，同比增长15%。"
        excerpt = "营收达到100亿元，同比增长15%，利润也有所提升"
        assert verify_excerpt_in_document(excerpt, doc) is True

    def test_empty_excerpt(self):
        assert verify_excerpt_in_document("", "some doc") is False


class TestExtractExcerptCore:
    def test_long_excerpt(self):
        excerpt = "公司2024年营收达到100亿元，同比增长15%，利润也有所提升"
        core = extract_excerpt_core(excerpt)
        assert len(core) >= 20

    def test_short_excerpt(self):
        excerpt = "营收100亿"
        core = extract_excerpt_core(excerpt, min_length=5)
        assert len(core) >= 5 or core == ""

    def test_sentence_based(self):
        excerpt = "第一句话。第二句营收达到100亿元。第三句话。"
        core = extract_excerpt_core(excerpt, min_length=10)
        assert "营收" in core or len(core) >= 10


class TestExtractKeyTerms:
    def test_chinese_terms(self):
        excerpt = "光模块市场规模达到200亿元"
        terms = extract_key_terms_from_excerpt(excerpt)
        assert len(terms) > 0
        assert any("200" in t for t in terms)

    def test_percentage(self):
        excerpt = "同比增长15.5%"
        terms = extract_key_terms_from_excerpt(excerpt)
        assert any("15" in t for t in terms)


class TestLocateSourceChunks:
    def test_no_excerpt_returns_empty(self, tmp_path):
        result = locate_source_chunks("", "doc.md", tmp_path)
        assert result == []

    def test_no_source_returns_empty(self, tmp_path):
        result = locate_source_chunks("some excerpt", "", tmp_path)
        assert result == []

    def test_nonexistent_dir_returns_empty(self):
        result = locate_source_chunks("excerpt", "doc.md", Path("/nonexistent"))
        assert result == []

    def test_matching_chunk_found(self, tmp_path):
        jsonl_content = (
            json.dumps(
                {
                    "chunk_id": "chunk_001",
                    "text": "公司2024年营收达到100亿元，同比增长15%。",
                    "metadata": {"source": "reports/doc.md", "chunk_index": 0},
                }
            )
            + "\n"
        )
        jsonl_file = tmp_path / "doc.jsonl"
        jsonl_file.write_text(jsonl_content, encoding="utf-8")

        result = locate_source_chunks(
            "营收达到100亿元",
            "reports/doc.md",
            tmp_path,
        )
        assert "chunk_001" in result

    def test_no_matching_chunk(self, tmp_path):
        jsonl_content = (
            json.dumps(
                {
                    "chunk_id": "chunk_001",
                    "text": "公司利润达到50亿元。",
                    "metadata": {"source": "reports/doc.md", "chunk_index": 0},
                }
            )
            + "\n"
        )
        jsonl_file = tmp_path / "doc.jsonl"
        jsonl_file.write_text(jsonl_content, encoding="utf-8")

        result = locate_source_chunks(
            "营收达到100亿元同比增长15%",
            "reports/doc.md",
            tmp_path,
        )
        assert result == []


class TestTestSetManagerGolden:
    def test_load_golden_testset_missing_file(self):
        config = {"data_dir": "data"}
        manager = TestSetManager(config)
        with pytest.raises(TestSetError, match="not found"):
            manager.load_golden_testset("nonexistent")

    def test_load_golden_testset_valid(self, tmp_path):
        golden_dir = tmp_path / "golden_testset"
        golden_dir.mkdir()
        golden_file = golden_dir / "golden_test.json"

        test_set = {
            "metadata": {
                "name": "golden_test",
                "meal_id": "",
                "created_at": "2026-04-25T10:00:00",
                "updated_at": "2026-04-25T10:00:00",
                "generation": {"strategy": "golden"},
                "user_defined": True,
                "invalid_policy": "immutable",
                "audit_log": [],
                "suppress_warnings": False,
                "composition": {},
            },
            "quality_metrics": {},
            "questions": [
                {
                    "id": "golden_001",
                    "question": "营收多少？",
                    "answer": "100亿",
                    "question_type": "single_fact",
                    "source_files": ["reports/doc.md"],
                    "ground_truth_excerpt": "营收100亿元",
                },
            ],
        }
        golden_file.write_text(
            json.dumps(test_set, ensure_ascii=False), encoding="utf-8"
        )

        config = {"data_dir": str(tmp_path)}
        manager = TestSetManager(config)
        result = manager.load_golden_testset("golden_test")
        assert result["metadata"]["name"] == "golden_test"
        assert len(result["questions"]) == 1

    def test_resolve_test_set_golden_flag(self, tmp_path):
        golden_dir = tmp_path / "golden_testset"
        golden_dir.mkdir()
        golden_file = golden_dir / "golden_150.json"

        test_set = {
            "metadata": {
                "name": "golden_150",
                "meal_id": "",
                "created_at": "2026-04-25T10:00:00",
                "updated_at": "2026-04-25T10:00:00",
                "generation": {"strategy": "golden"},
                "user_defined": True,
                "invalid_policy": "immutable",
                "audit_log": [],
                "suppress_warnings": False,
                "composition": {},
            },
            "quality_metrics": {},
            "questions": [],
        }
        golden_file.write_text(
            json.dumps(test_set, ensure_ascii=False), encoding="utf-8"
        )

        config = {"data_dir": str(tmp_path)}
        manager = TestSetManager(config)

        meal_config = MagicMock()
        meal_config.data_id = "test123"

        result = manager.resolve_test_set(
            meal_name="any_meal",
            test_set_config={"golden": True, "name": "golden_150"},
            meal_config=meal_config,
        )
        assert result["metadata"]["name"] == "golden_150"

    def test_resolve_test_set_golden_default_name(self, tmp_path):
        golden_dir = tmp_path / "golden_testset"
        golden_dir.mkdir()
        golden_file = golden_dir / "golden_150.json"

        test_set = {
            "metadata": {
                "name": "golden_150",
                "meal_id": "",
                "created_at": "2026-04-25T10:00:00",
                "updated_at": "2026-04-25T10:00:00",
                "generation": {"strategy": "golden"},
                "user_defined": True,
                "invalid_policy": "immutable",
                "audit_log": [],
                "suppress_warnings": False,
                "composition": {},
            },
            "quality_metrics": {},
            "questions": [],
        }
        golden_file.write_text(
            json.dumps(test_set, ensure_ascii=False), encoding="utf-8"
        )

        config = {"data_dir": str(tmp_path)}
        manager = TestSetManager(config)

        meal_config = MagicMock()
        meal_config.data_id = "test123"

        result = manager.resolve_test_set(
            meal_name="any_meal",
            test_set_config={"golden": True},
            meal_config=meal_config,
        )
        assert result["metadata"]["name"] == "golden_150"

    def test_get_golden_testset_dir_with_data_dir(self):
        config = {"data_dir": "/custom/data"}
        manager = TestSetManager(config)
        result = manager._get_golden_testset_dir()
        assert result == Path("/custom/data/golden_testset")

    def test_get_golden_testset_dir_default(self):
        config = {}
        manager = TestSetManager(config)
        result = manager._get_golden_testset_dir()
        assert result == Path("data/golden_testset")


class TestGoldenTestsetJsonValidation:
    def test_golden_qa_fixture_has_required_fields(self):
        fixture_path = Path("tests/fixtures/golden_qa.json")
        if not fixture_path.exists():
            pytest.skip("golden_qa.json fixture not found")

        with open(fixture_path, encoding="utf-8") as f:
            questions = json.load(f)

        for q in questions:
            assert "id" in q
            assert "question" in q
            assert "category" in q
            assert "expected_sources" in q

    def test_question_ids_unique(self):
        fixture_path = Path("tests/fixtures/golden_qa.json")
        if not fixture_path.exists():
            pytest.skip("golden_qa.json fixture not found")

        with open(fixture_path, encoding="utf-8") as f:
            questions = json.load(f)

        ids = [q["id"] for q in questions]
        assert len(ids) == len(set(ids))

    def test_question_texts_unique(self):
        fixture_path = Path("tests/fixtures/golden_qa.json")
        if not fixture_path.exists():
            pytest.skip("golden_qa.json fixture not found")

        with open(fixture_path, encoding="utf-8") as f:
            questions = json.load(f)

        texts = [q["question"] for q in questions]
        assert len(texts) == len(set(texts))
