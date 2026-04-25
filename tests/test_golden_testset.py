import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.generate_golden_testset import (
    GOLDEN_QUESTION_TYPES,
    GOLDEN_TYPE_DISTRIBUTION,
    _round_allocations,
    build_primary_pool,
    calculate_type_counts,
    detect_content_overlaps,
    distribute_across_documents,
    extract_excerpt_core,
    extract_key_terms_from_excerpt,
    locate_source_chunks,
    parse_question_response,
    validate_answer_numerical_accuracy,
    validate_question_quality,
    verify_excerpt_in_document,
)
from scripts.review_golden_testset import audit_testset
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
            {"doc_id": "doc_a", "name": "A", "content": "a" * 1000},
            {"doc_id": "doc_b", "name": "B", "content": "b" * 1000},
            {"doc_id": "doc_c", "name": "C", "content": "c" * 1000},
        ]
        type_counts = {"single_fact": 6, "reasoning": 3}
        result = distribute_across_documents(type_counts, docs)
        total = sum(len(v) for v in result.values())
        assert total == 9

    def test_single_document(self):
        docs = [{"doc_id": "doc_a", "name": "A", "content": "a" * 1000}]
        type_counts = {"single_fact": 5}
        result = distribute_across_documents(type_counts, docs)
        assert len(result["doc_a"]) == 5

    def test_more_questions_than_docs(self):
        docs = [
            {"doc_id": "doc_a", "name": "A", "content": "a" * 1000},
            {"doc_id": "doc_b", "name": "B", "content": "b" * 1000},
        ]
        type_counts = {"single_fact": 10}
        result = distribute_across_documents(type_counts, docs)
        total = sum(len(v) for v in result.values())
        assert total == 10

    def test_doc_id_as_key_not_name(self):
        docs = [
            {"doc_id": "path/a/report", "name": "same_name", "content": "a" * 1000},
            {"doc_id": "path/b/report", "name": "same_name", "content": "b" * 1000},
        ]
        type_counts = {"single_fact": 4}
        result = distribute_across_documents(type_counts, docs)
        assert "path/a/report" in result
        assert "path/b/report" in result
        total = sum(len(v) for v in result.values())
        assert total == 4

    def test_r_less_than_one_selects_subset(self):
        docs = [
            {"doc_id": f"doc_{i}", "name": f"D{i}", "content": f"c{i}" * 100}
            for i in range(10)
        ]
        type_counts = {"single_fact": 3}
        result = distribute_across_documents(type_counts, docs, seed=42)
        total = sum(len(v) for v in result.values())
        assert total == 3
        docs_with_types = {k: v for k, v in result.items() if v}
        assert len(docs_with_types) == 3
        for types in docs_with_types.values():
            assert len(types) == 1

    def test_r_equals_one_equal_allocation(self):
        docs = [
            {"doc_id": f"doc_{i}", "name": f"D{i}", "content": f"c{i}" * 100}
            for i in range(5)
        ]
        type_counts = {"single_fact": 5}
        result = distribute_across_documents(type_counts, docs, seed=42)
        total = sum(len(v) for v in result.values())
        assert total == 5

    def test_r_large_proportional_allocation(self):
        big_doc = {"doc_id": "big", "name": "Big", "content": "x" * 50000}
        small_doc = {"doc_id": "small", "name": "Small", "content": "y" * 1000}
        docs = [big_doc, small_doc]
        type_counts = {"single_fact": 10, "reasoning": 10}
        result = distribute_across_documents(type_counts, docs, seed=42)
        big_count = len(result.get("big", []))
        small_count = len(result.get("small", []))
        assert big_count > small_count

    def test_min_per_doc(self):
        docs = [
            {"doc_id": f"doc_{i}", "name": f"D{i}", "content": f"c{i}" * 100}
            for i in range(3)
        ]
        type_counts = {"single_fact": 3}
        result = distribute_across_documents(
            type_counts,
            docs,
            min_per_doc=1,
            seed=42,
        )
        for doc_id in ["doc_0", "doc_1", "doc_2"]:
            assert len(result.get(doc_id, [])) >= 1

    def test_max_per_doc_safety_cap(self):
        docs = [
            {"doc_id": "big", "name": "Big", "content": "x" * 50000},
            {"doc_id": "small", "name": "Small", "content": "y" * 1000},
        ]
        type_counts = {"single_fact": 10, "reasoning": 10}
        result = distribute_across_documents(
            type_counts,
            docs,
            max_per_doc=5,
            seed=42,
        )
        for _doc_id, types in result.items():
            assert len(types) <= 5

    def test_seed_reproducibility(self):
        docs = [
            {"doc_id": f"doc_{i}", "name": f"D{i}", "content": f"c{i}" * 1000}
            for i in range(5)
        ]
        type_counts = {"single_fact": 5, "reasoning": 5}
        result1 = distribute_across_documents(type_counts, docs, seed=123)
        result2 = distribute_across_documents(type_counts, docs, seed=123)
        for doc_id in result1:
            assert result1[doc_id] == result2[doc_id]

    def test_type_diversity_per_doc(self):
        docs = [
            {"doc_id": f"doc_{i}", "name": f"D{i}", "content": f"c{i}" * 1000}
            for i in range(3)
        ]
        type_counts = {"single_fact": 3, "reasoning": 3, "comparative": 3}
        result = distribute_across_documents(type_counts, docs, seed=42)
        for _doc_id, types in result.items():
            if len(types) >= 2:
                assert len(set(types)) >= 2

    def test_empty_documents(self):
        result = distribute_across_documents({"single_fact": 5}, [])
        assert result == {}


class TestRoundAllocations:
    def test_basic_rounding(self):
        raw = {"a": 3.4, "b": 2.6}
        result = _round_allocations(raw, 6)
        assert sum(result.values()) == 6

    def test_min_per_doc_enforced(self):
        raw = {"a": 0.2, "b": 5.8}
        result = _round_allocations(raw, 6, min_per_doc=1)
        assert result["a"] >= 1

    def test_max_per_doc_enforced(self):
        raw = {"a": 5.8, "b": 0.2}
        result = _round_allocations(raw, 6, max_per_doc=4)
        assert result["a"] <= 4

    def test_total_matches_target(self):
        raw = {"a": 1.1, "b": 2.3, "c": 3.6}
        result = _round_allocations(raw, 7)
        assert sum(result.values()) == 7


class TestDetectContentOverlaps:
    def test_summary_subset_of_annual_report(self):
        base_text = "A" * 5000
        summary_text = base_text[:2000]
        docs = [
            {"doc_id": "annual_report", "content": base_text},
            {"doc_id": "summary", "content": summary_text},
        ]
        overlaps = detect_content_overlaps(docs)
        assert len(overlaps) == 1
        assert overlaps[0][0] == "summary"
        assert overlaps[0][1] == "annual_report"

    def test_no_overlap(self):
        docs = [
            {"doc_id": "doc_a", "content": "Alpha beta gamma delta " * 200},
            {"doc_id": "doc_b", "content": "One two three four five " * 200},
        ]
        overlaps = detect_content_overlaps(docs)
        assert len(overlaps) == 0

    def test_short_document_skipped(self):
        docs = [
            {"doc_id": "doc_a", "content": "Short text"},
            {"doc_id": "doc_b", "content": "Long text " * 200},
        ]
        overlaps = detect_content_overlaps(docs)
        assert len(overlaps) == 0


class TestBuildPrimaryPool:
    def test_supplementary_excluded(self):
        docs = [
            {"doc_id": "annual_report", "content": "A" * 5000},
            {"doc_id": "summary", "content": "A" * 2000},
        ]
        overlaps = [("summary", "annual_report", 1.0)]
        pool = build_primary_pool(docs, overlaps)
        assert len(pool) == 1
        assert pool[0]["doc_id"] == "annual_report"

    def test_no_overlaps_all_kept(self):
        docs = [
            {"doc_id": "doc_a", "content": "A" * 1000},
            {"doc_id": "doc_b", "content": "B" * 1000},
        ]
        pool = build_primary_pool(docs, [])
        assert len(pool) == 2


class TestValidateAnswerNumericalAccuracy:
    def test_10x_error_detected(self):
        q = {
            "answer": "净利润从2268.9亿元降至1216.3亿元",
            "ground_truth_excerpt": "净利润|12,162,684,368.86|22,617,778,516.45",
        }
        is_valid, correction = validate_answer_numerical_accuracy(q)
        assert not is_valid
        assert correction is not None
        assert any(e["type"] == "10x_error" for e in correction["errors"])

    def test_correct_values_pass(self):
        q = {
            "answer": "净利润为121.63亿元",
            "ground_truth_excerpt": "净利润12,162,684,368.86元",
        }
        is_valid, correction = validate_answer_numerical_accuracy(q)
        assert is_valid
        assert correction is None

    def test_no_large_numbers_pass(self):
        q = {
            "answer": "公司主营光模块业务",
            "ground_truth_excerpt": "公司主营业务为光模块研发",
        }
        is_valid, correction = validate_answer_numerical_accuracy(q)
        assert is_valid

    def test_no_yi_unit_pass(self):
        q = {
            "answer": "净利润为12162684368.86元",
            "ground_truth_excerpt": "净利润12,162,684,368.86元",
        }
        is_valid, correction = validate_answer_numerical_accuracy(q)
        assert is_valid

    def test_empty_answer_pass(self):
        q = {"answer": "", "ground_truth_excerpt": "some text"}
        is_valid, correction = validate_answer_numerical_accuracy(q)
        assert is_valid

    def test_empty_excerpt_pass(self):
        q = {"answer": "净利润100亿", "ground_truth_excerpt": ""}
        is_valid, correction = validate_answer_numerical_accuracy(q)
        assert is_valid


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


class TestAuditTestset:
    def test_audit_basic_structure(self, tmp_path):
        golden_dir = tmp_path / "golden_testset"
        golden_dir.mkdir()
        golden_file = golden_dir / "test_audit.json"

        test_set = {
            "metadata": {
                "name": "test_audit",
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
                    "key_entities": ["营收"],
                    "difficulty": "easy",
                    "metadata": {"excerpt_verified": True},
                },
                {
                    "id": "golden_002",
                    "question": "利润多少？",
                    "answer": "50亿",
                    "question_type": "single_fact",
                    "source_files": ["reports/doc.md"],
                    "ground_truth_excerpt": "利润50亿元",
                    "key_entities": ["利润"],
                    "difficulty": "easy",
                    "metadata": {"excerpt_verified": False},
                },
            ],
        }
        golden_file.write_text(
            json.dumps(test_set, ensure_ascii=False),
            encoding="utf-8",
        )

        report = audit_testset(golden_file)
        assert report["total_questions"] == 2
        assert "document_distribution" in report
        assert "numerical_accuracy" in report
        assert "difficulty_distribution" in report
        assert "excerpt_verification" in report

    def test_audit_detects_numerical_issues(self, tmp_path):
        golden_dir = tmp_path / "golden_testset"
        golden_dir.mkdir()
        golden_file = golden_dir / "test_num.json"

        test_set = {
            "metadata": {
                "name": "test_num",
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
                    "question": "净利润多少？",
                    "answer": "净利润2268.9亿元",
                    "question_type": "single_fact",
                    "source_files": ["reports/doc.md"],
                    "ground_truth_excerpt": "净利润22,689,000,000.00元",
                    "key_entities": [],
                    "difficulty": "easy",
                    "metadata": {},
                },
            ],
        }
        golden_file.write_text(
            json.dumps(test_set, ensure_ascii=False),
            encoding="utf-8",
        )

        report = audit_testset(golden_file)
        assert report["numerical_accuracy"]["issues_found"] >= 1
