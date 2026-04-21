import json
from unittest.mock import MagicMock, patch

import pytest

from src.test_generator import TestSetGenerator


class TestGroupChunksBySource:
    def setup_method(self):
        self.config = {
            "chunker": {"output_dir": "data/chunks"},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_group_single_source(self):
        chunks = [
            {"text": "chunk 0", "metadata": {"source": "doc_a.md", "chunk_index": 0}},
            {"text": "chunk 1", "metadata": {"source": "doc_a.md", "chunk_index": 1}},
            {"text": "chunk 2", "metadata": {"source": "doc_a.md", "chunk_index": 2}},
        ]
        grouped = self.generator._group_chunks_by_source(chunks)
        assert len(grouped) == 1
        assert "doc_a.md" in grouped
        assert len(grouped["doc_a.md"]) == 3

    def test_group_multiple_sources(self):
        chunks = [
            {"text": "a0", "metadata": {"source": "doc_a.md", "chunk_index": 0}},
            {"text": "b0", "metadata": {"source": "doc_b.md", "chunk_index": 0}},
            {"text": "a1", "metadata": {"source": "doc_a.md", "chunk_index": 1}},
        ]
        grouped = self.generator._group_chunks_by_source(chunks)
        assert len(grouped) == 2
        assert len(grouped["doc_a.md"]) == 2
        assert len(grouped["doc_b.md"]) == 1

    def test_group_sorted_by_index(self):
        chunks = [
            {"text": "chunk 2", "metadata": {"source": "doc.md", "chunk_index": 2}},
            {"text": "chunk 0", "metadata": {"source": "doc.md", "chunk_index": 0}},
            {"text": "chunk 1", "metadata": {"source": "doc.md", "chunk_index": 1}},
        ]
        grouped = self.generator._group_chunks_by_source(chunks)
        indices = [c["metadata"]["chunk_index"] for c in grouped["doc.md"]]
        assert indices == [0, 1, 2]

    def test_group_empty(self):
        grouped = self.generator._group_chunks_by_source([])
        assert grouped == {}


class TestSelectChunksForFactual:
    def setup_method(self):
        self.config = {
            "chunker": {"output_dir": "data/chunks"},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_select_factual(self):
        grouped = {
            "doc_a.md": [
                {"text": f"chunk {i}", "metadata": {"source": "doc_a.md", "chunk_index": i}}
                for i in range(10)
            ],
        }
        result = self.generator._select_chunks_for_factual(grouped, 3)
        assert len(result) == 3
        for group in result:
            assert len(group) == 1

    def test_select_factual_more_than_available(self):
        grouped = {
            "doc_a.md": [
                {"text": f"chunk {i}", "metadata": {"source": "doc_a.md", "chunk_index": i}}
                for i in range(2)
            ],
        }
        result = self.generator._select_chunks_for_factual(grouped, 5)
        assert len(result) == 2

    def test_select_factual_empty(self):
        result = self.generator._select_chunks_for_factual({}, 5)
        assert result == []


class TestSelectChunksForBoundary:
    def setup_method(self):
        self.config = {
            "chunker": {"output_dir": "data/chunks"},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_select_boundary(self):
        grouped = {
            "doc_a.md": [
                {"text": f"chunk {i}", "metadata": {"source": "doc_a.md", "chunk_index": i}}
                for i in range(10)
            ],
        }
        result = self.generator._select_chunks_for_boundary(grouped, 3)
        assert len(result) == 3
        for group in result:
            assert len(group) == 2
            idx0 = group[0]["metadata"]["chunk_index"]
            idx1 = group[1]["metadata"]["chunk_index"]
            assert idx1 == idx0 + 1

    def test_select_boundary_no_pairs(self):
        grouped = {
            "doc_a.md": [
                {"text": "only chunk", "metadata": {"source": "doc_a.md", "chunk_index": 0}},
            ],
        }
        result = self.generator._select_chunks_for_boundary(grouped, 3)
        assert result == []


class TestSelectChunksForMultiHop:
    def setup_method(self):
        self.config = {
            "chunker": {"output_dir": "data/chunks"},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_select_multi_hop(self):
        grouped = {
            "doc_a.md": [
                {"text": f"chunk {i}", "metadata": {"source": "doc_a.md", "chunk_index": i}}
                for i in range(10)
            ],
        }
        result = self.generator._select_chunks_for_multi_hop(grouped, 3)
        assert len(result) == 3
        for group in result:
            assert len(group) == 2
            idx0 = group[0]["metadata"]["chunk_index"]
            idx1 = group[1]["metadata"]["chunk_index"]
            assert abs(idx1 - idx0) >= 2

    def test_select_multi_hop_not_enough_chunks(self):
        grouped = {
            "doc_a.md": [
                {"text": f"chunk {i}", "metadata": {"source": "doc_a.md", "chunk_index": i}}
                for i in range(2)
            ],
        }
        result = self.generator._select_chunks_for_multi_hop(grouped, 3)
        assert result == []


class TestParseLlmResponse:
    def setup_method(self):
        self.config = {
            "chunker": {"output_dir": "data/chunks"},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_parse_valid_json(self):
        response = '{"question": "营收多少？", "answer": "100亿", "difficulty": "easy"}'
        result = self.generator._parse_llm_response(response)
        assert result is not None
        assert result["question"] == "营收多少？"
        assert result["answer"] == "100亿"

    def test_parse_json_with_surrounding_text(self):
        response = '好的，这是生成的问题：\n{"question": "营收多少？", "answer": "100亿"}\n希望对你有帮助。'
        result = self.generator._parse_llm_response(response)
        assert result is not None
        assert result["question"] == "营收多少？"

    def test_parse_json_in_code_block(self):
        response = '```json\n{"question": "营收多少？", "answer": "100亿"}\n```'
        result = self.generator._parse_llm_response(response)
        assert result is not None
        assert result["question"] == "营收多少？"

    def test_parse_missing_question(self):
        response = '{"answer": "100亿"}'
        result = self.generator._parse_llm_response(response)
        assert result is None

    def test_parse_missing_answer(self):
        response = '{"question": "营收多少？"}'
        result = self.generator._parse_llm_response(response)
        assert result is None

    def test_parse_invalid_json(self):
        response = "this is not json"
        result = self.generator._parse_llm_response(response)
        assert result is None

    def test_parse_empty_question(self):
        response = '{"question": "", "answer": "100亿"}'
        result = self.generator._parse_llm_response(response)
        assert result is None

    def test_parse_default_difficulty(self):
        response = '{"question": "营收多少？", "answer": "100亿"}'
        result = self.generator._parse_llm_response(response)
        assert result is not None
        assert result["difficulty"] == "medium"


class TestLoadMealChunks:
    def test_load_chunks_with_source_filter(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        reports_dir = chunks_dir / "reports"
        reports_dir.mkdir()

        chunk_data = [
            {"chunk_id": "report_0_000", "text": "chunk text 0", "metadata": {"source": "reports/report_0.md", "chunk_index": 0}},
            {"chunk_id": "report_0_001", "text": "chunk text 1", "metadata": {"source": "reports/report_0.md", "chunk_index": 1}},
        ]
        jsonl_file = reports_dir / "report_0.jsonl"
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for chunk in chunk_data:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        other_data = [
            {"chunk_id": "other_000", "text": "other chunk", "metadata": {"source": "reports/other.md", "chunk_index": 0}},
        ]
        other_file = reports_dir / "other.jsonl"
        with open(other_file, "w", encoding="utf-8") as f:
            for chunk in other_data:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        from src.meal import MealConfig, MealFile
        meal_config = MealConfig(
            data_id="abc123" + "0" * 58,
            name="test_meal",
            created_at="2026-04-16T14:30:00",
            sampling_config=None,
            collection_name="m_test1234567",
            pdf_files=[
                MealFile(path="reports/report_0.pdf", sha256="abc", size_bytes=100)
            ],
            stats={"total_pdfs": 1, "total_pages": 50, "total_chunks": 2},
        )

        config = {
            "chunker": {"output_dir": str(chunks_dir)},
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)
        chunks = generator._load_meal_chunks(meal_config)

        assert len(chunks) == 2
        assert all(c["metadata"]["source"] == "reports/report_0.md" for c in chunks)


class TestCalculateQuestionDistribution:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_distribution_basic(self):
        distribution = {
            "single_fact": 0.30,
            "multi_fact": 0.25,
            "reasoning": 0.15,
            "comparative": 0.15,
            "missing": 0.10,
            "irrelevant": 0.05,
        }
        result = self.generator._calculate_question_distribution(20, distribution)
        total = sum(result.values())
        assert total == 20

    def test_distribution_single_type(self):
        distribution = {"single_fact": 1.0}
        result = self.generator._calculate_question_distribution(10, distribution)
        assert result["single_fact"] == 10

    def test_distribution_rounding(self):
        distribution = {
            "type_a": 0.33,
            "type_b": 0.33,
            "type_c": 0.34,
        }
        result = self.generator._calculate_question_distribution(10, distribution)
        total = sum(result.values())
        assert total == 10

    def test_distribution_small_count(self):
        distribution = {
            "single_fact": 0.30,
            "multi_fact": 0.25,
            "reasoning": 0.15,
        }
        result = self.generator._calculate_question_distribution(2, distribution)
        total = sum(result.values())
        assert total == 2

    def test_distribution_default_distribution(self):
        result = self.generator._calculate_question_distribution(
            20, self.generator.TYPE_DISTRIBUTION
        )
        total = sum(result.values())
        assert total == 20
        assert result["single_fact"] == 6


class TestParseDocumentQuestionResponse:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_parse_valid_response(self):
        response = '''{
            "question": "2024年光模块市场规模多少？",
            "answer": "2024年光模块市场规模约为100亿美元。",
            "question_type": "single_fact",
            "difficulty": "easy",
            "reasoning": "这是一个直接的数据查询问题",
            "key_entities": ["光模块", "市场规模"],
            "answer_sources": ["第3段"]
        }'''
        result = self.generator._parse_document_question_response(response)
        assert result is not None
        assert result["question"] == "2024年光模块市场规模多少？"
        assert result["question_type"] == "single_fact"
        assert result["difficulty"] == "easy"

    def test_parse_response_in_code_block(self):
        response = '''```json
        {
            "question": "CPO的全称是什么？",
            "answer": "CPO的全称是Co-packaged Optics。",
            "question_type": "single_fact"
        }
        ```'''
        result = self.generator._parse_document_question_response(response)
        assert result is not None
        assert result["question"] == "CPO的全称是什么？"

    def test_parse_response_with_surrounding_text(self):
        response = '''好的，这是生成的问题：
        {"question": "营收增长原因？", "answer": "主要因为新产品销售增长。", "question_type": "reasoning"}
        希望对你有帮助。'''
        result = self.generator._parse_document_question_response(response)
        assert result is not None
        assert result["question"] == "营收增长原因？"

    def test_parse_missing_required_field(self):
        response = '{"question": "问题？", "answer": "答案"}'
        result = self.generator._parse_document_question_response(response)
        assert result is None

    def test_parse_empty_question_type(self):
        response = '{"question": "问题？", "answer": "答案", "question_type": ""}'
        result = self.generator._parse_document_question_response(response)
        assert result is None

    def test_parse_default_values(self):
        response = '{"question": "问题？", "answer": "答案", "question_type": "single_fact"}'
        result = self.generator._parse_document_question_response(response)
        assert result is not None
        assert result["difficulty"] == "medium"
        assert result["reasoning"] == ""
        assert result["key_entities"] == []
        assert result["answer_sources"] == []

    def test_parse_invalid_json(self):
        response = "this is not valid json"
        result = self.generator._parse_document_question_response(response)
        assert result is None


class TestValidateQuestionQuality:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_valid_question(self):
        question_data = {
            "question": "2024年光模块市场规模多少？",
            "answer": "100亿美元",
            "question_type": "single_fact",
        }
        assert self.generator._validate_question_quality(question_data) is True

    def test_question_too_short(self):
        question_data = {
            "question": "啊？",
            "answer": "答案",
            "question_type": "single_fact",
        }
        assert self.generator._validate_question_quality(question_data) is False

    def test_question_too_long(self):
        question_data = {
            "question": "这是一个非常长的问题，" * 50,
            "answer": "答案",
            "question_type": "single_fact",
        }
        assert self.generator._validate_question_quality(question_data) is False

    def test_question_with_academic_pattern(self):
        question_data = {
            "question": "根据文档，2024年光模块市场规模多少？",
            "answer": "100亿美元",
            "question_type": "single_fact",
        }
        assert self.generator._validate_question_quality(question_data) is False

    def test_question_with_template_start(self):
        question_data = {
            "question": "请分析光模块市场的发展趋势",
            "answer": "发展趋势是...",
            "question_type": "reasoning",
        }
        assert self.generator._validate_question_quality(question_data) is False

    def test_question_exactly_min_length(self):
        question_data = {
            "question": "营收多少？",
            "answer": "100亿",
            "question_type": "single_fact",
        }
        assert self.generator._validate_question_quality(question_data) is True

    def test_question_exactly_max_length(self):
        question_data = {
            "question": "a" * 100,
            "answer": "答案",
            "question_type": "single_fact",
        }
        assert self.generator._validate_question_quality(question_data) is True


class TestCheckAuthenticityRules:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_authentic_question(self):
        question = "2024年光模块市场规模多少？"
        result = self.generator._check_authenticity_rules(question)
        assert result["is_authentic"] is True
        assert result["has_issues"] is False
        assert result["issues"] == []

    def test_question_with_academic_pattern_根据文档(self):
        question = "根据文档，光模块市场规模是多少？"
        result = self.generator._check_authenticity_rules(question)
        assert result["is_authentic"] is False
        assert result["has_issues"] is True
        assert any("根据文档" in issue for issue in result["issues"])

    def test_question_with_academic_pattern_请分析(self):
        question = "请分析光模块市场的发展趋势"
        result = self.generator._check_authenticity_rules(question)
        assert result["is_authentic"] is False
        assert any("请分析" in issue for issue in result["issues"])

    def test_question_with_template_start_请问(self):
        question = "请问光模块市场规模是多少？"
        result = self.generator._check_authenticity_rules(question)
        assert result["is_authentic"] is False
        assert any("请问" in issue for issue in result["issues"])

    def test_question_too_long(self):
        question = "这是一个非常长的问题，" * 20
        result = self.generator._check_authenticity_rules(question)
        assert result["is_authentic"] is False
        assert any("过长" in issue for issue in result["issues"])

    def test_multiple_issues(self):
        question = "根据文档，请分析光模块市场的发展趋势，这是一个很长的问题" * 5
        result = self.generator._check_authenticity_rules(question)
        assert result["is_authentic"] is False
        assert len(result["issues"]) >= 2

    def test_all_academic_patterns(self):
        patterns = [
            "根据文档，营收多少？",
            "根据提供的信息，利润是多少？",
            "请分析市场趋势",
            "请说明技术原理",
            "请对比两种方案",
            "请总结主要观点",
            "文档中提到的关键数据是什么？",
            "片段中提到的核心观点是什么？",
        ]
        for question in patterns:
            result = self.generator._check_authenticity_rules(question)
            assert result["is_authentic"] is False, f"Pattern should be detected: {question}"

    def test_all_template_starts(self):
        starts = [
            "请问市场规模是多少？",
            "请解释技术原理",
            "请描述产品特点",
        ]
        for question in starts:
            result = self.generator._check_authenticity_rules(question)
            assert result["is_authentic"] is False, f"Template start should be detected: {question}"


class TestCalculateQualityMetrics:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_empty_questions(self):
        result = self.generator._calculate_quality_metrics([])
        assert result["format_correct_rate"] == 0.0
        assert result["authenticity_pass_rate"] == 0.0
        assert result["type_distribution"] == {}

    def test_single_question(self):
        questions = [
            {
                "question": "市场规模多少？",
                "answer": "100亿",
                "question_type": "single_fact",
            }
        ]
        result = self.generator._calculate_quality_metrics(questions)
        assert result["format_correct_rate"] == 1.0
        assert result["authenticity_pass_rate"] == 1.0
        assert result["type_distribution"]["single_fact"] == 1

    def test_multiple_questions_same_type(self):
        questions = [
            {
                "question": "市场规模多少？",
                "answer": "100亿",
                "question_type": "single_fact",
            },
            {
                "question": "营收增长多少？",
                "answer": "20%",
                "question_type": "single_fact",
            },
        ]
        result = self.generator._calculate_quality_metrics(questions)
        assert result["type_distribution"]["single_fact"] == 2

    def test_multiple_questions_different_types(self):
        questions = [
            {
                "question": "市场规模多少？",
                "answer": "100亿",
                "question_type": "single_fact",
            },
            {
                "question": "为什么增长这么快？",
                "answer": "因为新产品销售增长",
                "question_type": "reasoning",
            },
            {
                "question": "A公司和B公司哪个更好？",
                "answer": "A公司更好",
                "question_type": "comparative",
            },
        ]
        result = self.generator._calculate_quality_metrics(questions)
        assert result["type_distribution"]["single_fact"] == 1
        assert result["type_distribution"]["reasoning"] == 1
        assert result["type_distribution"]["comparative"] == 1

    def test_authenticity_pass_rate_with_issues(self):
        questions = [
            {
                "question": "市场规模多少？",
                "answer": "100亿",
                "question_type": "single_fact",
            },
            {
                "question": "根据文档，营收增长多少？",
                "answer": "20%",
                "question_type": "single_fact",
            },
        ]
        result = self.generator._calculate_quality_metrics(questions)
        assert result["authenticity_pass_rate"] == 0.5

    def test_authenticity_pass_rate_all_pass(self):
        questions = [
            {
                "question": "市场规模多少？",
                "answer": "100亿",
                "question_type": "single_fact",
            },
            {
                "question": "营收增长多少？",
                "answer": "20%",
                "question_type": "single_fact",
            },
        ]
        result = self.generator._calculate_quality_metrics(questions)
        assert result["authenticity_pass_rate"] == 1.0

    def test_authenticity_pass_rate_none_pass(self):
        questions = [
            {
                "question": "根据文档，市场规模多少？",
                "answer": "100亿",
                "question_type": "single_fact",
            },
            {
                "question": "请分析营收增长原因",
                "answer": "因为新产品销售增长",
                "question_type": "reasoning",
            },
        ]
        result = self.generator._calculate_quality_metrics(questions)
        assert result["authenticity_pass_rate"] == 0.0


class TestQuestionTypes:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_question_types_defined(self):
        assert "single_fact" in self.generator.QUESTION_TYPES
        assert "multi_fact" in self.generator.QUESTION_TYPES
        assert "reasoning" in self.generator.QUESTION_TYPES
        assert "comparative" in self.generator.QUESTION_TYPES
        assert "missing" in self.generator.QUESTION_TYPES
        assert "irrelevant" in self.generator.QUESTION_TYPES

    def test_type_distribution_defined(self):
        assert "single_fact" in self.generator.TYPE_DISTRIBUTION
        assert "multi_fact" in self.generator.TYPE_DISTRIBUTION
        assert "reasoning" in self.generator.TYPE_DISTRIBUTION
        assert "comparative" in self.generator.TYPE_DISTRIBUTION
        assert "missing" in self.generator.TYPE_DISTRIBUTION
        assert "irrelevant" in self.generator.TYPE_DISTRIBUTION

    def test_type_distribution_sums_to_one(self):
        total = sum(self.generator.TYPE_DISTRIBUTION.values())
        assert abs(total - 1.0) < 0.001

    def test_question_type_chinese_names(self):
        assert self.generator.QUESTION_TYPES["single_fact"] == "单知识点查询"
        assert self.generator.QUESTION_TYPES["multi_fact"] == "多知识点综合"
        assert self.generator.QUESTION_TYPES["reasoning"] == "推理型问题"
        assert self.generator.QUESTION_TYPES["comparative"] == "对比分析"
        assert self.generator.QUESTION_TYPES["missing"] == "缺失知识点"
        assert self.generator.QUESTION_TYPES["irrelevant"] == "无关问题"


class TestDistributeQuestionsAcrossDocs:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_total_questions_equals_num_questions(self):
        type_counts = {"single_fact": 15, "multi_fact": 12, "reasoning": 7,
                       "comparative": 7, "missing": 5, "irrelevant": 4}
        doc_names = ["doc_a", "doc_b", "doc_c"]
        result = self.generator._distribute_questions_across_docs(
            type_counts, doc_names
        )
        total = sum(len(v) for v in result.values())
        assert total == 50

    def test_no_questions_per_doc_multiplier(self):
        type_counts = {"single_fact": 15, "multi_fact": 12}
        doc_names = [f"doc_{i}" for i in range(35)]
        result = self.generator._distribute_questions_across_docs(
            type_counts, doc_names
        )
        total = sum(len(v) for v in result.values())
        assert total == 27

    def test_single_document_gets_all_questions(self):
        type_counts = {"single_fact": 10, "multi_fact": 5}
        doc_names = ["only_doc"]
        result = self.generator._distribute_questions_across_docs(
            type_counts, doc_names
        )
        assert len(result["only_doc"]) == 15
        total = sum(len(v) for v in result.values())
        assert total == 15

    def test_round_robin_distribution(self):
        type_counts = {"type_a": 3, "type_b": 3}
        doc_names = ["doc_1", "doc_2"]
        result = self.generator._distribute_questions_across_docs(
            type_counts, doc_names
        )
        assert len(result["doc_1"]) == 3
        assert len(result["doc_2"]) == 3

    def test_more_docs_than_questions(self):
        type_counts = {"single_fact": 2}
        doc_names = ["doc_a", "doc_b", "doc_c", "doc_d"]
        result = self.generator._distribute_questions_across_docs(
            type_counts, doc_names
        )
        total = sum(len(v) for v in result.values())
        assert total == 2
        non_empty = [name for name, types in result.items() if types]
        assert len(non_empty) == 2

    def test_preserves_type_proportions_globally(self):
        type_counts = {"single_fact": 15, "multi_fact": 12, "reasoning": 7,
                       "comparative": 7, "missing": 5, "irrelevant": 4}
        doc_names = [f"doc_{i}" for i in range(5)]
        result = self.generator._distribute_questions_across_docs(
            type_counts, doc_names
        )
        all_types = []
        for types in result.values():
            all_types.extend(types)
        from collections import Counter
        counts = Counter(all_types)
        assert counts["single_fact"] == 15
        assert counts["multi_fact"] == 12
        assert counts["reasoning"] == 7


class TestLoadFullDocuments:
    def setup_method(self):
        self.config = {
            "parser": {"output_dir": "data/parsed"},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_returns_dict_with_content_and_source_path(self, tmp_path):
        parsed_dir = tmp_path / "parsed"
        sub_dir = parsed_dir / "research_reports"
        sub_dir.mkdir(parents=True)
        md_file = sub_dir / "2026年光伏行业分析.md"
        md_file.write_text("光伏行业分析内容", encoding="utf-8")

        meal_config = MagicMock()
        meal_config.data_id = None
        meal_config.pdf_files = [
            MagicMock(path="research_reports/2026年光伏行业分析.pdf")
        ]

        with patch.object(
            self.generator, "_resolve_parsed_dir", return_value=parsed_dir
        ):
            result = self.generator._load_full_documents(meal_config)

        assert "2026年光伏行业分析" in result
        doc_data = result["2026年光伏行业分析"]
        assert "content" in doc_data
        assert "source_path" in doc_data
        assert doc_data["content"] == "光伏行业分析内容"
        assert doc_data["source_path"] == "research_reports/2026年光伏行业分析.md"

    def test_empty_when_no_parsed_dir(self):
        meal_config = MagicMock()
        meal_config.data_id = None
        meal_config.pdf_files = []

        with patch.object(
            self.generator, "_resolve_parsed_dir", return_value=None
        ):
            result = self.generator._load_full_documents(meal_config)

        assert result == {}


class TestDocumentBasedQuestionsSourceFiles:
    def setup_method(self):
        self.config = {
            "parser": {"output_dir": "data/parsed"},
            "test_generation": {"max_retries": 3, "default_num_questions": 20},
        }
        self.generator = TestSetGenerator(self.config)

    def test_source_files_set_in_generated_questions(self, tmp_path):
        parsed_dir = tmp_path / "parsed"
        sub_dir = parsed_dir / "research_reports"
        sub_dir.mkdir(parents=True)
        md_file = sub_dir / "光模块行业分析.md"
        md_file.write_text("光模块行业内容" * 100, encoding="utf-8")

        meal_config = MagicMock()
        meal_config.data_id = "test_data_id"
        meal_config.pdf_files = [
            MagicMock(path="research_reports/光模块行业分析.pdf")
        ]

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        mock_generator = MagicMock()
        mock_generator.generate.return_value = json.dumps({
            "question": "光模块市场规模多少？",
            "answer": "约100亿美元",
            "question_type": "single_fact",
            "difficulty": "easy",
            "reasoning": "测试",
            "key_entities": ["光模块"],
            "answer_sources": ["第1段"],
        })

        with patch.object(
            self.generator, "_resolve_parsed_dir", return_value=parsed_dir
        ), patch(
            "src.test_generator.MealManager", return_value=mock_meal_manager
        ), patch(
            "src.test_generator.Generator", return_value=mock_generator
        ), patch(
            "src.test_generator.get_llm_config",
            return_value={
                "model_name": "test",
                "api_key": "test",
                "base_url": "http://test",
            },
        ):
            result = self.generator.generate_document_based_questions(
                meal_name="test_meal",
                num_questions=1,
                type_distribution={"single_fact": 1.0},
            )

        questions = result["questions"]
        assert len(questions) >= 1
        for q in questions:
            assert "source_files" in q
            assert isinstance(q["source_files"], list)
            assert len(q["source_files"]) > 0
            assert q["source_files"][0] == "research_reports/光模块行业分析.md"


class TestGenerateDocumentBasedQuestionsSupplemental:
    def setup_method(self):
        self.config = {
            "parser": {"output_dir": "data/parsed"},
            "test_generation": {"max_retries": 3, "default_num_questions": 20},
        }
        self.generator = TestSetGenerator(self.config)

    def _make_meal_config(self):
        meal_config = MagicMock()
        meal_config.data_id = "test_data_id"
        meal_config.pdf_files = [
            MagicMock(path="research_reports/doc_a.pdf"),
            MagicMock(path="research_reports/doc_b.pdf"),
        ]
        return meal_config

    def _make_parsed_dir(self, tmp_path):
        parsed_dir = tmp_path / "parsed"
        sub_dir = parsed_dir / "research_reports"
        sub_dir.mkdir(parents=True)
        (sub_dir / "doc_a.md").write_text("文档A内容" * 100, encoding="utf-8")
        (sub_dir / "doc_b.md").write_text("文档B内容" * 100, encoding="utf-8")
        return parsed_dir

    def test_supplemental_loop_fills_gap(self, tmp_path):
        parsed_dir = self._make_parsed_dir(tmp_path)
        meal_config = self._make_meal_config()

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        call_count = 0

        def mock_generate(query, contexts, system_prompt, category):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return "invalid json"
            return json.dumps({
                "question": "营收增长多少？",
                "answer": "20%",
                "question_type": "single_fact",
                "difficulty": "easy",
                "reasoning": "",
                "key_entities": [],
                "answer_sources": [],
            })

        mock_llm_generator = MagicMock()
        mock_llm_generator.generate.side_effect = mock_generate

        with patch.object(
            self.generator, "_resolve_parsed_dir", return_value=parsed_dir
        ), patch(
            "src.test_generator.MealManager", return_value=mock_meal_manager
        ), patch(
            "src.test_generator.Generator", return_value=mock_llm_generator
        ), patch(
            "src.test_generator.get_llm_config",
            return_value={
                "model_name": "test",
                "api_key": "test",
                "base_url": "http://test",
            },
        ):
            result = self.generator.generate_document_based_questions(
                meal_name="test_meal",
                num_questions=3,
                type_distribution={"single_fact": 1.0},
            )

        assert len(result["questions"]) == 3

    def test_supplemental_loop_respects_max_attempts(self, tmp_path):
        parsed_dir = self._make_parsed_dir(tmp_path)
        meal_config = self._make_meal_config()

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        mock_llm_generator = MagicMock()
        mock_llm_generator.generate.return_value = "invalid json"

        with patch.object(
            self.generator, "_resolve_parsed_dir", return_value=parsed_dir
        ), patch(
            "src.test_generator.MealManager", return_value=mock_meal_manager
        ), patch(
            "src.test_generator.Generator", return_value=mock_llm_generator
        ), patch(
            "src.test_generator.get_llm_config",
            return_value={
                "model_name": "test",
                "api_key": "test",
                "base_url": "http://test",
            },
        ):
            with pytest.raises(ValueError, match="No questions could be generated"):
                self.generator.generate_document_based_questions(
                    meal_name="test_meal",
                    num_questions=5,
                    type_distribution={"single_fact": 1.0},
                )


class TestSupplementDocumentBasedQuestions:
    def setup_method(self):
        self.config = {
            "parser": {"output_dir": "data/parsed"},
            "test_generation": {"max_retries": 3, "default_num_questions": 20},
        }
        self.generator = TestSetGenerator(self.config)

    def test_no_supplement_needed_when_count_matches(self):
        existing = {
            "metadata": {
                "name": "test_set",
                "meal_id": "test_id",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "generation": {"num_questions": 2},
                "user_defined": False,
                "audit_log": [],
            },
            "questions": [
                {"id": "q001", "question": "问题1？", "answer": "答案1", "question_type": "single_fact"},
                {"id": "q002", "question": "问题2？", "answer": "答案2", "question_type": "single_fact"},
            ],
            "quality_metrics": {},
        }
        result = self.generator.supplement_document_based_questions(
            meal_name="test_meal",
            existing_test_set=existing,
            target_count=2,
        )
        assert len(result["questions"]) == 2

    def test_no_supplement_needed_when_count_exceeds(self):
        existing = {
            "metadata": {
                "name": "test_set",
                "meal_id": "test_id",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "generation": {"num_questions": 3},
                "user_defined": False,
                "audit_log": [],
            },
            "questions": [
                {"id": "q001", "question": "问题1？", "answer": "答案1", "question_type": "single_fact"},
                {"id": "q002", "question": "问题2？", "answer": "答案2", "question_type": "single_fact"},
                {"id": "q003", "question": "问题3？", "answer": "答案3", "question_type": "single_fact"},
            ],
            "quality_metrics": {},
        }
        result = self.generator.supplement_document_based_questions(
            meal_name="test_meal",
            existing_test_set=existing,
            target_count=2,
        )
        assert len(result["questions"]) == 3

    def test_supplement_adds_deficit_questions(self, tmp_path):
        parsed_dir = tmp_path / "parsed"
        sub_dir = parsed_dir / "research_reports"
        sub_dir.mkdir(parents=True)
        (sub_dir / "doc_a.md").write_text("文档A内容" * 100, encoding="utf-8")

        meal_config = MagicMock()
        meal_config.data_id = "test_data_id"
        meal_config.pdf_files = [
            MagicMock(path="research_reports/doc_a.pdf")
        ]

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        mock_llm_generator = MagicMock()
        mock_llm_generator.generate.return_value = json.dumps({
            "question": "新增问题？",
            "answer": "新增答案",
            "question_type": "single_fact",
            "difficulty": "easy",
            "reasoning": "",
            "key_entities": [],
            "answer_sources": [],
        })

        existing = {
            "metadata": {
                "name": "document_level_n5",
                "meal_id": "test_data_id",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "generation": {
                    "strategy": "document",
                    "num_questions": 3,
                    "type_distribution": {},
                    "llm_preset": "default",
                },
                "user_defined": False,
                "audit_log": [],
            },
            "questions": [
                {"id": "q001", "question": "问题1？", "answer": "答案1", "question_type": "single_fact",
                 "source_document": "doc_a", "category": "document", "source_files": [], "source_chunks": []},
                {"id": "q002", "question": "问题2？", "answer": "答案2", "question_type": "single_fact",
                 "source_document": "doc_a", "category": "document", "source_files": [], "source_chunks": []},
                {"id": "q003", "question": "问题3？", "answer": "答案3", "question_type": "reasoning",
                 "source_document": "doc_a", "category": "document", "source_files": [], "source_chunks": []},
            ],
            "quality_metrics": {},
        }

        with patch.object(
            self.generator, "_resolve_parsed_dir", return_value=parsed_dir
        ), patch(
            "src.test_generator.MealManager", return_value=mock_meal_manager
        ), patch(
            "src.test_generator.Generator", return_value=mock_llm_generator
        ), patch(
            "src.test_generator.get_llm_config",
            return_value={
                "model_name": "test",
                "api_key": "test",
                "base_url": "http://test",
            },
        ):
            result = self.generator.supplement_document_based_questions(
                meal_name="test_meal",
                existing_test_set=existing,
                target_count=5,
            )

        assert len(result["questions"]) == 5
        assert result["questions"][0]["id"] == "q001"
        assert result["questions"][3]["id"] == "q004"
        assert result["questions"][4]["id"] == "q005"
        assert result["metadata"]["generation"]["num_questions"] == 5

    def test_supplement_returns_unchanged_on_all_failures(self, tmp_path):
        parsed_dir = tmp_path / "parsed"
        sub_dir = parsed_dir / "research_reports"
        sub_dir.mkdir(parents=True)
        (sub_dir / "doc_a.md").write_text("文档A内容" * 100, encoding="utf-8")

        meal_config = MagicMock()
        meal_config.data_id = "test_data_id"
        meal_config.pdf_files = [
            MagicMock(path="research_reports/doc_a.pdf")
        ]

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        mock_llm_generator = MagicMock()
        mock_llm_generator.generate.return_value = "invalid json"

        existing = {
            "metadata": {
                "name": "test_set",
                "meal_id": "test_id",
                "created_at": "2026-01-01T00:00:00",
                "updated_at": "2026-01-01T00:00:00",
                "generation": {"num_questions": 1},
                "user_defined": False,
                "audit_log": [],
            },
            "questions": [
                {"id": "q001", "question": "问题1？", "answer": "答案1", "question_type": "single_fact"},
            ],
            "quality_metrics": {},
        }

        with patch.object(
            self.generator, "_resolve_parsed_dir", return_value=parsed_dir
        ), patch(
            "src.test_generator.MealManager", return_value=mock_meal_manager
        ), patch(
            "src.test_generator.Generator", return_value=mock_llm_generator
        ), patch(
            "src.test_generator.get_llm_config",
            return_value={
                "model_name": "test",
                "api_key": "test",
                "base_url": "http://test",
            },
        ):
            result = self.generator.supplement_document_based_questions(
                meal_name="test_meal",
                existing_test_set=existing,
                target_count=3,
            )

        assert len(result["questions"]) == 1
