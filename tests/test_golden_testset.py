import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from scripts.review_golden_testset import audit_testset
from src.exceptions import TestSetError
from src.test_generator import MISSING_INDEPENDENT_PROMPT, TestSetGenerator
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


class TestProperNounSuffixStripping:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_suffix_stripped_match_when_core_in_evidence(self):
        evidence_list = [{"quote": "电子领域发展迅速，相关企业增长显著"}]
        is_valid, issues = self.generator._validate_answer_evidence_consistency(
            "电子行业前景广阔", evidence_list
        )
        assert is_valid
        assert len(issues) == 0

    def test_no_match_when_core_not_in_evidence(self):
        evidence_list = [{"quote": "传统制造业面临转型压力"}]
        is_valid, issues = self.generator._validate_answer_evidence_consistency(
            "量子计算行业前景广阔", evidence_list
        )
        assert not is_valid
        assert any("量子计算行业" in i for i in issues)

    def test_exact_match_still_works(self):
        evidence_list = [{"quote": "华为技术在5G领域处于领先地位"}]
        is_valid, issues = self.generator._validate_answer_evidence_consistency(
            "华为技术在5G领域处于领先地位", evidence_list
        )
        assert is_valid
        assert len(issues) == 0


class TestFilterAdversarialIssues:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_proper_noun_issues_filtered_out(self):
        issues = [
            "专有名词 '量子计算行业' 未在证据中找到",
            "数值 '2268.9亿元' 未在证据中找到",
        ]
        question = "公司2024年营收2268.9亿元，实际增长如何？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 1
        assert result[0].startswith("数值")

    def test_number_in_question_kept(self):
        issues = [
            "数值 '2268.9亿元' 未在证据中找到",
        ]
        question = "公司2024年营收2268.9亿元，实际增长如何？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 1
        assert "2268.9" in result[0]

    def test_computed_number_not_in_question_filtered(self):
        issues = [
            "数值 '15.5个百分点' 未在证据中找到",
        ]
        question = "公司2024年营收2268.9亿元，实际增长如何？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 0

    def test_small_number_below_threshold_kept(self):
        issues = [
            "数值 '5.3%' 未在证据中找到",
        ]
        question = "公司2024年营收2268.9亿元，实际增长如何？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 1

    def test_integer_in_question_kept(self):
        issues = [
            "数值 '100亿元' 未在证据中找到",
        ]
        question = "营收达到100亿的公司有哪些？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 1

    def test_computed_integer_not_in_question_filtered(self):
        issues = [
            "数值 '200亿元' 未在证据中找到",
        ]
        question = "营收达到100亿的公司有哪些？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 0

    def test_mixed_issues_filtered_correctly(self):
        issues = [
            "专有名词 '新兴技术行业' 未在证据中找到",
            "数值 '2268.9亿元' 未在证据中找到",
            "数值 '15.5个百分点' 未在证据中找到",
            "专有名词 '量子计算集团' 未在证据中找到",
        ]
        question = "公司2024年营收2268.9亿元，实际增长如何？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 1
        assert "2268.9" in result[0]

    def test_empty_issues_returns_empty(self):
        result = self.generator._filter_adversarial_issues([], "some question")
        assert result == []

    def test_number_with_comma_in_question_kept(self):
        issues = [
            "数值 '1,216.3亿元' 未在证据中找到",
        ]
        question = "净利润为1216.3亿，同比下降多少？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 1

    def test_non_number_non_proper_noun_issue_kept(self):
        issues = [
            "其他类型的问题描述",
        ]
        question = "公司2024年营收如何？"
        result = self.generator._filter_adversarial_issues(issues, question)
        assert len(result) == 1


class TestValidateAnswerConsistency:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_positive_number_described_as_negative(self):
        q = {
            "answer": "经营性现金流短期债务比为778.37倍，这个数值为负值",
            "ground_truth_excerpt": "均为负值，其中酒鬼酒778.37倍",
        }
        is_consistent, warning = self.generator._validate_answer_consistency(q)
        assert not is_consistent
        assert "negative" in warning.lower() or "负" in warning

    def test_consistent_answer_passes(self):
        q = {
            "answer": "经营性现金流短期债务比为-778.37倍，为负值",
            "ground_truth_excerpt": "均为负值，其中酒鬼酒-778.37倍",
        }
        is_consistent, warning = self.generator._validate_answer_consistency(q)
        assert is_consistent

    def test_no_negative_description_passes(self):
        q = {
            "answer": "营收增长15.3%，达到100亿元",
            "ground_truth_excerpt": "营收同比增长15.3%，达到100亿元",
        }
        is_consistent, warning = self.generator._validate_answer_consistency(q)
        assert is_consistent

    def test_empty_answer_passes(self):
        q = {"answer": "", "ground_truth_excerpt": "some text"}
        is_consistent, warning = self.generator._validate_answer_consistency(q)
        assert is_consistent


class TestValidateEvidenceMinQuoteLength:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_short_quote_rejected(self):
        segments = [
            {"text": "即时型消费成为增量引擎，推动行业增长", "segment_index": 0}
        ]
        evidence = [{"segment_index": 0, "quote": "即时型消费", "relevance": "test"}]
        result = self.generator._validate_evidence(evidence, segments)
        assert result["verified_evidence"][0]["verified"] is False
        assert "too short" in result["invalid_quotes"][0]["reason"].lower()

    def test_long_quote_accepted(self):
        segments = [
            {
                "text": "即时零售推动了即时型消费成为增量引擎，2025年B级城市增速达70%",
                "segment_index": 0,
            }
        ]
        evidence = [
            {
                "segment_index": 0,
                "quote": "即时零售推动了即时型消费成为增量引擎，2025年B级城市增速达70%",
                "relevance": "test",
            }
        ]
        result = self.generator._validate_evidence(evidence, segments)
        assert result["verified_evidence"][0]["verified"] is True


class TestValidateEvidenceAdaptiveQuoteLength:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_cjk_quote_at_cjk_threshold_passes(self):
        cjk_15 = "即时零售推动消费增长引擎新趋势"
        assert len(cjk_15) == 15
        segments = [{"text": cjk_15, "segment_index": 0}]
        evidence = [{"segment_index": 0, "quote": cjk_15, "relevance": "test"}]
        result = self.generator._validate_evidence(evidence, segments)
        assert result["verified_evidence"][0]["verified"] is True

    def test_cjk_quote_above_cjk_threshold_passes(self):
        cjk_20 = "即时零售推动了即时型消费增长引擎加速发展"
        assert len(cjk_20) == 20
        segments = [{"text": cjk_20, "segment_index": 0}]
        evidence = [{"segment_index": 0, "quote": cjk_20, "relevance": "test"}]
        result = self.generator._validate_evidence(evidence, segments)
        assert result["verified_evidence"][0]["verified"] is True

    def test_english_quote_below_default_threshold_fails(self):
        eng_25 = "a" * 25
        segments = [{"text": eng_25, "segment_index": 0}]
        evidence = [{"segment_index": 0, "quote": eng_25, "relevance": "test"}]
        result = self.generator._validate_evidence(evidence, segments)
        assert result["verified_evidence"][0]["verified"] is False
        assert "too short" in result["invalid_quotes"][0]["reason"].lower()

    def test_english_quote_at_default_threshold_passes(self):
        eng_30 = "a" * 30
        segments = [{"text": eng_30, "segment_index": 0}]
        evidence = [{"segment_index": 0, "quote": eng_30, "relevance": "test"}]
        result = self.generator._validate_evidence(evidence, segments)
        assert result["verified_evidence"][0]["verified"] is True


class TestValidateEvidenceDocumentFallback:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_invalid_segment_index_found_in_doc(self):
        segments = [{"text": "some other text", "segment_index": 0}]
        doc_content = "即时零售推动了即时型消费成为增量引擎，2025年B级城市增速达70%"
        evidence = [
            {
                "segment_index": 5,
                "quote": "即时零售推动了即时型消费成为增量引擎，2025年B级城市增速达70%",
                "relevance": "test",
            }
        ]
        result = self.generator._validate_evidence(
            evidence, segments, "unknown", doc_content
        )
        assert result["verified_evidence"][0]["verified"] is True
        assert result["verified_evidence"][0]["match_type"] == "document_fuzzy"

    def test_invalid_segment_index_not_in_doc(self):
        segments = [{"text": "some other text", "segment_index": 0}]
        doc_content = "完全不同的文档内容，没有任何关联信息"
        evidence = [
            {
                "segment_index": 5,
                "quote": "即时零售推动了即时型消费成为增量引擎，2025年B级城市增速达70%",
                "relevance": "test",
            }
        ]
        result = self.generator._validate_evidence(
            evidence, segments, "unknown", doc_content
        )
        assert result["verified_evidence"][0]["verified"] is False

    def test_quote_not_in_segment_but_in_doc(self):
        segments = [{"text": "这是片段0的内容，关于市场概况", "segment_index": 0}]
        doc_content = "这是片段0的内容，关于市场概况。即时零售推动了即时型消费成为增量引擎，2025年增速达70%"
        evidence = [
            {
                "segment_index": 0,
                "quote": "即时零售推动了即时型消费成为增量引擎，2025年增速达70%",
                "relevance": "test",
            }
        ]
        result = self.generator._validate_evidence(
            evidence, segments, "unknown", doc_content
        )
        assert result["verified_evidence"][0]["verified"] is True
        assert result["verified_evidence"][0]["match_type"] == "document_fuzzy"


class TestChineseToTypeKey:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_known_type(self):
        assert self.generator._chinese_to_type_key("单知识点查询") == "single_fact"

    def test_multi_fact(self):
        assert self.generator._chinese_to_type_key("多知识点综合") == "multi_fact"

    def test_unknown_type(self):
        assert self.generator._chinese_to_type_key("未知类型") is None


class TestEvidenceMaxTokens:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_evidence_max_tokens_has_expected_types(self):
        for q_type in ["comparative", "reasoning", "multi_fact"]:
            assert q_type in self.generator.EVIDENCE_MAX_TOKENS

    def test_evidence_max_tokens_values_are_2048(self):
        for q_type in ["comparative", "reasoning", "multi_fact"]:
            assert self.generator.EVIDENCE_MAX_TOKENS[q_type] == 2048

    def test_evidence_max_tokens_falls_back_to_default(self):
        default_max_tokens = self.generator.test_gen_max_tokens
        for q_type in ["single_fact", "missing", "irrelevant", "adversarial"]:
            assert (
                self.generator.EVIDENCE_MAX_TOKENS.get(q_type, default_max_tokens)
                == default_max_tokens
            )

    def test_effective_max_tokens_dynamic_selection(self):
        default_max_tokens = self.generator.test_gen_max_tokens
        for q_type in ["comparative", "reasoning", "multi_fact"]:
            effective = self.generator.EVIDENCE_MAX_TOKENS.get(
                q_type, default_max_tokens
            )
            assert effective == 2048
        for q_type in ["single_fact", "missing", "irrelevant", "adversarial"]:
            effective = self.generator.EVIDENCE_MAX_TOKENS.get(
                q_type, default_max_tokens
            )
            assert effective == default_max_tokens


class TestFormatProgressBar:
    def test_zero_total(self):
        from scripts.review_golden_testset import format_progress_bar

        result = format_progress_bar(0, 0)
        assert "0/0" in result

    def test_half_progress(self):
        from scripts.review_golden_testset import format_progress_bar

        result = format_progress_bar(5, 10)
        assert "5/10" in result
        assert "50%" in result

    def test_full_progress(self):
        from scripts.review_golden_testset import format_progress_bar

        result = format_progress_bar(10, 10)
        assert "10/10" in result
        assert "100%" in result


class TestFormatAITierBadge:
    def test_no_review(self):
        from scripts.review_golden_testset import format_ai_tier_badge

        assert format_ai_tier_badge(None) == ""

    def test_tier_a(self):
        from scripts.review_golden_testset import format_ai_tier_badge

        result = format_ai_tier_badge({"tier": "A", "overall_score": 4.5})
        assert "A(4.5)" in result

    def test_tier_b(self):
        from scripts.review_golden_testset import format_ai_tier_badge

        result = format_ai_tier_badge({"tier": "B", "overall_score": 3.2})
        assert "B(3.2)" in result

    def test_tier_c(self):
        from scripts.review_golden_testset import format_ai_tier_badge

        result = format_ai_tier_badge({"tier": "C", "overall_score": 2.0})
        assert "C(2.0)" in result


class TestDisplayAIDetail:
    def test_display_shows_dimensions(self, capsys):
        from scripts.review_golden_testset import display_ai_detail

        ai_review = {
            "dimensions": {
                "question_clarity": {"score": 4, "reason": "清晰"},
                "answer_accuracy": {"score": 3, "reason": "一般"},
            },
            "overall_score": 3.5,
            "tier": "B",
            "overall_comment": "中等质量",
            "suggested_action": "review",
        }
        display_ai_detail(ai_review)
        captured = capsys.readouterr()
        assert "question_clarity" in captured.out
        assert "answer_accuracy" in captured.out
        assert "3.5" in captured.out
        assert "中等质量" in captured.out


class TestMissingIndependentPrompt:
    def test_prompt_is_non_empty_string(self):
        assert isinstance(MISSING_INDEPENDENT_PROMPT, str)
        assert len(MISSING_INDEPENDENT_PROMPT.strip()) > 0

    def test_prompt_contains_segments_placeholder(self):
        assert "{segments_text}" in MISSING_INDEPENDENT_PROMPT

    def test_prompt_mentions_empty_evidence(self):
        assert "[]" in MISSING_INDEPENDENT_PROMPT

    def test_prompt_mentions_missing_answer(self):
        assert "文档未提及该信息" in MISSING_INDEPENDENT_PROMPT

    def test_prompt_format_succeeds(self):
        result = MISSING_INDEPENDENT_PROMPT.format(segments_text="测试片段内容")
        assert "测试片段内容" in result
        assert "{segments_text}" not in result


class TestGenerateMissingQuestion:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_returns_qa_when_evidence_empty(self):
        mock_generator = MagicMock()
        mock_generator.generate.return_value = json.dumps(
            {
                "question": "ESG评级怎么样？",
                "answer": "文档未提及该信息。",
                "question_type": "缺失知识点",
                "difficulty": "medium",
                "evidence": [],
                "selected_segments": [],
            }
        )

        segments = [{"text": "光模块市场2024年增长12.5%", "segment_index": 0}]
        result = self.generator._generate_missing_question(segments, mock_generator)

        assert result is not None
        assert result["question_type"] == "缺失知识点"
        assert result["evidence"] == []
        assert result["ground_truth_excerpt"] == ""

    def test_retries_when_evidence_non_empty(self):
        response_with_evidence = json.dumps(
            {
                "question": "ESG评级怎么样？",
                "answer": "文档未提及该信息。",
                "question_type": "缺失知识点",
                "difficulty": "medium",
                "evidence": [
                    {"segment_index": 0, "quote": "光模块市场增长", "relevance": "test"}
                ],
                "selected_segments": [],
            }
        )
        response_without_evidence = json.dumps(
            {
                "question": "ESG评级怎么样？",
                "answer": "文档未提及该信息。",
                "question_type": "缺失知识点",
                "difficulty": "medium",
                "evidence": [],
                "selected_segments": [],
            }
        )

        mock_generator = MagicMock()
        mock_generator.generate.side_effect = [
            response_with_evidence,
            response_without_evidence,
        ]

        segments = [{"text": "光模块市场2024年增长12.5%", "segment_index": 0}]
        result = self.generator._generate_missing_question(segments, mock_generator)

        assert result is not None
        assert result["evidence"] == []
        assert mock_generator.generate.call_count == 2

    def test_returns_none_on_all_failures(self):
        mock_generator = MagicMock()
        mock_generator.generate.side_effect = Exception("LLM error")

        segments = [{"text": "光模块市场2024年增长12.5%", "segment_index": 0}]
        result = self.generator._generate_missing_question(segments, mock_generator)

        assert result is None

    def test_returns_none_on_unparseable_response(self):
        mock_generator = MagicMock()
        mock_generator.generate.return_value = "not valid json"

        segments = [{"text": "光模块市场2024年增长12.5%", "segment_index": 0}]
        result = self.generator._generate_missing_question(segments, mock_generator)

        assert result is None

    def test_uses_missing_independent_prompt(self):
        mock_generator = MagicMock()
        mock_generator.generate.return_value = json.dumps(
            {
                "question": "ESG评级怎么样？",
                "answer": "文档未提及该信息。",
                "question_type": "缺失知识点",
                "difficulty": "medium",
                "evidence": [],
                "selected_segments": [],
            }
        )

        segments = [{"text": "光模块市场2024年增长12.5%", "segment_index": 0}]
        self.generator._generate_missing_question(segments, mock_generator)

        call_args = mock_generator.generate.call_args
        prompt_used = call_args.kwargs.get("query", call_args[1].get("query", ""))
        assert "文档中明显没有答案" in prompt_used


class TestAnswerLengthLimits:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_all_seven_types_present(self):
        expected_types = {
            "single_fact",
            "missing",
            "irrelevant",
            "adversarial",
            "multi_fact",
            "comparative",
            "reasoning",
        }
        assert set(self.generator.ANSWER_LENGTH_LIMITS.keys()) == expected_types

    def test_truncate_at_period(self):
        qa = {"id": "test_001", "answer": "这是一。这是二。这是三。"}
        self.generator._truncate_answer(qa, qa["answer"], 5)
        assert qa["answer"] == "这是一。"
        assert qa["metadata"]["answer_truncated"] is True

    def test_no_truncation_within_limit(self):
        qa = {"id": "test_002", "answer": "短答案。"}
        self.generator._truncate_answer(qa, qa["answer"], 200)
        assert qa["answer"] == "短答案。"
        assert "answer_truncated" not in qa.get("metadata", {})

    def test_hard_truncation_no_period(self):
        qa = {"id": "test_003", "answer": "abcdefghij"}
        self.generator._truncate_answer(qa, qa["answer"], 5)
        assert qa["answer"] == "abcde"
        assert qa["metadata"]["answer_truncated"] is True


class TestSupplementEvidenceForUncoveredNumbers:
    def test_supplement_when_number_found_in_doc(self):
        generator = TestSetGenerator({})
        answer = "营收达到500亿元"
        evidence = [{"quote": "公司业绩良好", "segment_index": 0}]
        issues = ["数值 '500亿' 未在证据中找到"]
        doc = "根据财报，公司营收达到500亿元，同比增长20%。"
        updated_ev, remaining = generator._supplement_evidence_for_uncovered_numbers(
            answer, evidence, issues, doc
        )
        assert len(updated_ev) == 2
        assert updated_ev[1]["match_type"] == "auto_supplemented"
        assert updated_ev[1]["segment_index"] == -1
        assert len(remaining) == 0

    def test_no_supplement_when_number_not_in_doc(self):
        generator = TestSetGenerator({})
        answer = "营收达到999亿元"
        evidence = [{"quote": "公司业绩良好", "segment_index": 0}]
        issues = ["数值 '999亿' 未在证据中找到"]
        doc = "根据财报，公司营收达到500亿元。"
        updated_ev, remaining = generator._supplement_evidence_for_uncovered_numbers(
            answer, evidence, issues, doc
        )
        assert len(updated_ev) == 1
        assert len(remaining) == 1

    def test_no_supplement_when_no_number_issues(self):
        generator = TestSetGenerator({})
        answer = "公司表现优秀"
        evidence = [{"quote": "公司业绩良好", "segment_index": 0}]
        issues = ["专有名词 '量子计算行业' 未在证据中找到"]
        doc = "公司业绩良好。"
        updated_ev, remaining = generator._supplement_evidence_for_uncovered_numbers(
            answer, evidence, issues, doc
        )
        assert len(updated_ev) == 1
        assert len(remaining) == 1

    def test_no_supplement_when_empty_doc(self):
        generator = TestSetGenerator({})
        answer = "营收达到500亿元"
        evidence = [{"quote": "公司业绩良好", "segment_index": 0}]
        issues = ["数值 '500亿' 未在证据中找到"]
        updated_ev, remaining = generator._supplement_evidence_for_uncovered_numbers(
            answer, evidence, issues, ""
        )
        assert len(updated_ev) == 1
        assert len(remaining) == 1
