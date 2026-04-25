import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.review_golden_testset import audit_testset
from src.exceptions import TestSetError
from src.test_generator import TestSetGenerator
from src.test_set_manager import TestSetManager


class TestGoldenSchema:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_adversarial_in_question_types(self):
        assert "adversarial" in self.generator.QUESTION_TYPES

    def test_golden_type_distribution_sums_approximately_to_one(self):
        total = sum(self.generator.GOLDEN_TYPE_DISTRIBUTION.values())
        assert abs(total - 1.0) < 0.05

    def test_golden_type_distribution_has_all_types(self):
        for q_type in self.generator.QUESTION_TYPES:
            assert q_type in self.generator.GOLDEN_TYPE_DISTRIBUTION

    def test_failure_modes_has_all_types(self):
        for q_type in self.generator.QUESTION_TYPES:
            assert q_type in self.generator.FAILURE_MODES


class TestDetectContentOverlaps:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_summary_subset_of_annual_report(self):
        base_text = "A" * 5000
        summary_text = base_text[:2000]
        docs = [
            {"doc_id": "annual_report", "content": base_text},
            {"doc_id": "summary", "content": summary_text},
        ]
        overlaps = self.generator._detect_content_overlaps(docs)
        assert len(overlaps) == 1
        assert overlaps[0][0] == "summary"
        assert overlaps[0][1] == "annual_report"

    def test_no_overlap(self):
        docs = [
            {"doc_id": "doc_a", "content": "Alpha beta gamma delta " * 200},
            {"doc_id": "doc_b", "content": "One two three four five " * 200},
        ]
        overlaps = self.generator._detect_content_overlaps(docs)
        assert len(overlaps) == 0

    def test_short_document_skipped(self):
        docs = [
            {"doc_id": "doc_a", "content": "Short text"},
            {"doc_id": "doc_b", "content": "Long text " * 200},
        ]
        overlaps = self.generator._detect_content_overlaps(docs)
        assert len(overlaps) == 0


class TestBuildPrimaryPool:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_supplementary_excluded(self):
        docs = [
            {"doc_id": "annual_report", "content": "A" * 5000},
            {"doc_id": "summary", "content": "A" * 2000},
        ]
        overlaps = [("summary", "annual_report", 1.0)]
        pool = self.generator._build_primary_pool(docs, overlaps)
        assert len(pool) == 1
        assert pool[0]["doc_id"] == "annual_report"

    def test_no_overlaps_all_kept(self):
        docs = [
            {"doc_id": "doc_a", "content": "A" * 1000},
            {"doc_id": "doc_b", "content": "B" * 1000},
        ]
        pool = self.generator._build_primary_pool(docs, [])
        assert len(pool) == 2


class TestValidateAnswerNumericalAccuracy:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_10x_error_detected(self):
        q = {
            "answer": "净利润从2268.9亿元降至1216.3亿元",
            "ground_truth_excerpt": "净利润|12,162,684,368.86|22,617,778,516.45",
        }
        is_valid, correction = self.generator._validate_numerical_accuracy(q)
        assert not is_valid
        assert correction is not None
        assert any(e["type"] == "10x_error" for e in correction["errors"])

    def test_correct_values_pass(self):
        q = {
            "answer": "净利润为121.63亿元",
            "ground_truth_excerpt": "净利润12,162,684,368.86元",
        }
        is_valid, correction = self.generator._validate_numerical_accuracy(q)
        assert is_valid
        assert correction is None

    def test_no_large_numbers_pass(self):
        q = {
            "answer": "公司主营光模块业务",
            "ground_truth_excerpt": "公司主营业务为光模块研发",
        }
        is_valid, correction = self.generator._validate_numerical_accuracy(q)
        assert is_valid

    def test_no_yi_unit_pass(self):
        q = {
            "answer": "净利润为12162684368.86元",
            "ground_truth_excerpt": "净利润12,162,684,368.86元",
        }
        is_valid, correction = self.generator._validate_numerical_accuracy(q)
        assert is_valid

    def test_empty_answer_pass(self):
        q = {"answer": "", "ground_truth_excerpt": "some text"}
        is_valid, correction = self.generator._validate_numerical_accuracy(q)
        assert is_valid

    def test_empty_excerpt_pass(self):
        q = {"answer": "净利润100亿", "ground_truth_excerpt": ""}
        is_valid, correction = self.generator._validate_numerical_accuracy(q)
        assert is_valid


class TestVerifyExcerptInDocument:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_exact_match(self):
        doc = "公司2024年营收达到100亿元，同比增长15%。"
        excerpt = "营收达到100亿元"
        assert self.generator._verify_excerpt_in_document(excerpt, doc) is True

    def test_no_match(self):
        doc = "公司2024年利润达到50亿元。"
        excerpt = "营收达到100亿元，同比增长15%"
        assert self.generator._verify_excerpt_in_document(excerpt, doc) is False

    def test_whitespace_ignored(self):
        doc = "公司 2024年 营收 达到 100亿元"
        excerpt = "公司2024年营收达到100亿元"
        assert self.generator._verify_excerpt_in_document(excerpt, doc) is True

    def test_partial_overlap(self):
        doc = "公司2024年营收达到100亿元，同比增长15%。"
        excerpt = "营收达到100亿元，同比增长15%，利润也有所提升"
        assert self.generator._verify_excerpt_in_document(excerpt, doc) is True

    def test_empty_excerpt(self):
        assert self.generator._verify_excerpt_in_document("", "some doc") is False


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
