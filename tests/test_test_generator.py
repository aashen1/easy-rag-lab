import hashlib
import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import TestSetError
from src.test_generator import TestSetGenerator


class TestGroupChunksBySource:
    def setup_method(self):
        self.config = {
            "chunker": {},
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
            "chunker": {},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_select_factual(self):
        grouped = {
            "doc_a.md": [
                {
                    "text": f"chunk {i}",
                    "metadata": {"source": "doc_a.md", "chunk_index": i},
                }
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
                {
                    "text": f"chunk {i}",
                    "metadata": {"source": "doc_a.md", "chunk_index": i},
                }
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
            "chunker": {},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_select_boundary(self):
        grouped = {
            "doc_a.md": [
                {
                    "text": f"chunk {i}",
                    "metadata": {"source": "doc_a.md", "chunk_index": i},
                }
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
                {
                    "text": "only chunk",
                    "metadata": {"source": "doc_a.md", "chunk_index": 0},
                },
            ],
        }
        result = self.generator._select_chunks_for_boundary(grouped, 3)
        assert result == []


class TestSelectChunksForMultiHop:
    def setup_method(self):
        self.config = {
            "chunker": {},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_select_multi_hop(self):
        grouped = {
            "doc_a.md": [
                {
                    "text": f"chunk {i}",
                    "metadata": {"source": "doc_a.md", "chunk_index": i},
                }
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
                {
                    "text": f"chunk {i}",
                    "metadata": {"source": "doc_a.md", "chunk_index": i},
                }
                for i in range(2)
            ],
        }
        result = self.generator._select_chunks_for_multi_hop(grouped, 3)
        assert result == []


class TestParseLlmResponse:
    def setup_method(self):
        self.config = {
            "chunker": {},
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
            {
                "chunk_id": "report_0::chunk::000",
                "text": "chunk text 0",
                "metadata": {"source": "reports/report_0.md", "chunk_index": 0},
            },
            {
                "chunk_id": "report_0::chunk::001",
                "text": "chunk text 1",
                "metadata": {"source": "reports/report_0.md", "chunk_index": 1},
            },
        ]
        jsonl_file = reports_dir / "report_0.jsonl"
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for chunk in chunk_data:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        other_data = [
            {
                "chunk_id": "other::chunk::000",
                "text": "other chunk",
                "metadata": {"source": "reports/other.md", "chunk_index": 0},
            },
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
            config_hashes={"chunker": "testchk1"},
        )

        artifacts_dir = tmp_path / "artifacts"
        group_dir = artifacts_dir / "abc1230000000000"
        artifact_chunks_dir = group_dir / "chunks_testchk1" / "reports"
        artifact_chunks_dir.mkdir(parents=True)

        import shutil

        shutil.copytree(str(reports_dir), str(artifact_chunks_dir), dirs_exist_ok=True)

        config = {
            "artifacts": {"dir": str(artifacts_dir)},
            "parser": {"input_dir": str(tmp_path / "raw")},
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)
        chunks = generator._load_meal_chunks(meal_config)

        assert len(chunks) == 2
        assert all(c["metadata"]["source"] == "reports/report_0.md" for c in chunks)


class TestLocateAnswerChunks:
    def setup_method(self):
        self.config = {
            "chunker": {},
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def _create_chunks_dir(self, tmp_path, chunks_data):
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        for source_path, chunks in chunks_data.items():
            source_dir = chunks_dir / Path(source_path).parent
            source_dir.mkdir(parents=True, exist_ok=True)
            jsonl_name = Path(source_path).stem + ".jsonl"
            jsonl_file = chunks_dir / source_path.replace(source_path, jsonl_name)
            jsonl_file = source_dir / jsonl_name
            with open(jsonl_file, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    f.write(json.dumps(chunk, ensure_ascii=False) + "\n")
        return chunks_dir

    def test_locate_with_meal_config_uses_artifact_cache(self, tmp_path):
        from src.meal import MealConfig, MealFile

        chunks_dir = tmp_path / "artifacts" / "abc1230000000000" / "chunks_hash123"
        chunks_dir.mkdir(parents=True)
        source_dir = chunks_dir / "reports"
        source_dir.mkdir()

        chunk_data = [
            {
                "chunk_id": "report_0::chunk::000",
                "text": "2024年营收增长9.53%，净利润增长12.75%",
                "metadata": {"source": "reports/report_0.pages.json", "chunk_index": 0},
            },
            {
                "chunk_id": "report_0::chunk::001",
                "text": "其他无关内容",
                "metadata": {"source": "reports/report_0.pages.json", "chunk_index": 1},
            },
        ]
        jsonl_file = source_dir / "report_0.jsonl"
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for chunk in chunk_data:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

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
            config_hashes={"chunker": "hash123"},
        )

        config = {
            "artifacts": {"dir": str(tmp_path / "artifacts")},
            "chunker": {},
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)

        with pytest.warns(
            DeprecationWarning, match="_locate_answer_chunks is deprecated"
        ):
            result = generator._locate_answer_chunks(
                answer="2024年营收增长9.53%",
                source_path="reports/report_0.pages.json",
                meal_config=meal_config,
            )

        assert len(result) > 0
        assert "report_0::chunk::000" in result

    def test_locate_with_explicit_chunks_dir(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        source_dir = chunks_dir / "reports"
        source_dir.mkdir()

        chunk_data = [
            {
                "chunk_id": "doc::chunk::000",
                "text": "净利润12.75%",
                "metadata": {"source": "reports/doc.pages.json", "chunk_index": 0},
            },
        ]
        jsonl_file = source_dir / "doc.jsonl"
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for chunk in chunk_data:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        config = {
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)

        with pytest.warns(
            DeprecationWarning, match="_locate_answer_chunks is deprecated"
        ):
            result = generator._locate_answer_chunks(
                answer="净利润12.75%",
                source_path="reports/doc.pages.json",
                chunks_dir=chunks_dir,
            )

        assert len(result) > 0

    def test_locate_returns_empty_when_no_chunks_dir(self):
        config = {
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)

        with pytest.warns(
            DeprecationWarning, match="_locate_answer_chunks is deprecated"
        ):
            result = generator._locate_answer_chunks(
                answer="some answer",
                source_path="reports/doc.md",
            )

        assert result == []

    def test_adjacent_tolerance_expands_matches(self, tmp_path):
        chunks_dir = tmp_path / "chunks"
        chunks_dir.mkdir()
        source_dir = chunks_dir / "reports"
        source_dir.mkdir()

        chunk_data = [
            {
                "chunk_id": "doc::chunk::000",
                "text": "无关内容0",
                "metadata": {"source": "reports/doc.md", "chunk_index": 0},
            },
            {
                "chunk_id": "doc::chunk::001",
                "text": "营收增长9.53%",
                "metadata": {"source": "reports/doc.md", "chunk_index": 1},
            },
            {
                "chunk_id": "doc::chunk::002",
                "text": "无关内容2",
                "metadata": {"source": "reports/doc.md", "chunk_index": 2},
            },
            {
                "chunk_id": "doc::chunk::003",
                "text": "无关内容3",
                "metadata": {"source": "reports/doc.md", "chunk_index": 3},
            },
        ]
        jsonl_file = source_dir / "doc.jsonl"
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for chunk in chunk_data:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        config = {
            "test_generation": {"max_retries": 3},
        }
        generator = TestSetGenerator(config)

        with pytest.warns(
            DeprecationWarning, match="_locate_answer_chunks is deprecated"
        ):
            result_no_expand = generator._locate_answer_chunks(
                answer="营收增长9.53%",
                source_path="reports/doc.md",
                chunks_dir=chunks_dir,
                adjacent_tolerance=0,
            )

        with pytest.warns(
            DeprecationWarning, match="_locate_answer_chunks is deprecated"
        ):
            result_expand = generator._locate_answer_chunks(
                answer="营收增长9.53%",
                source_path="reports/doc.md",
                chunks_dir=chunks_dir,
                adjacent_tolerance=1,
            )

        assert len(result_no_expand) == 1
        assert len(result_expand) == 3


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
        assert result["single_fact"] == 5

    def test_distribution_small_count_no_last_type_dominance(self):
        distribution = {
            "single_fact": 0.17,
            "multi_fact": 0.17,
            "reasoning": 0.17,
            "comparative": 0.17,
            "missing": 0.15,
            "irrelevant": 0.10,
            "adversarial": 0.07,
        }
        result = self.generator._calculate_question_distribution(6, distribution)
        total = sum(result.values())
        assert total == 6
        assert result["adversarial"] <= 2, (
            f"adversarial should not dominate, got {result['adversarial']}"
        )
        non_zero_types = sum(1 for v in result.values() if v > 0)
        assert non_zero_types >= 3, (
            f"at least 3 types should have questions, got {non_zero_types}"
        )

    def test_distribution_large_count_proportional(self):
        distribution = {
            "single_fact": 0.30,
            "multi_fact": 0.25,
            "reasoning": 0.15,
            "comparative": 0.15,
            "missing": 0.10,
            "irrelevant": 0.05,
        }
        result = self.generator._calculate_question_distribution(100, distribution)
        total = sum(result.values())
        assert total == 100
        assert result["single_fact"] == 30
        assert result["multi_fact"] == 25
        assert result["reasoning"] == 15
        assert result["comparative"] == 15
        assert result["missing"] == 10
        assert result["irrelevant"] == 5

    def test_distribution_one_question_multiple_types(self):
        distribution = {
            "type_a": 0.50,
            "type_b": 0.30,
            "type_c": 0.20,
        }
        result = self.generator._calculate_question_distribution(1, distribution)
        total = sum(result.values())
        assert total == 1
        non_zero = [k for k, v in result.items() if v > 0]
        assert len(non_zero) == 1

    def test_distribution_zero_proportion_type_excluded(self):
        distribution = {
            "single_fact": 0.50,
            "multi_fact": 0.50,
            "adversarial": 0.00,
        }
        result = self.generator._calculate_question_distribution(10, distribution)
        total = sum(result.values())
        assert total == 10
        assert result["adversarial"] == 0
        assert result["single_fact"] == 5
        assert result["multi_fact"] == 5

    def test_distribution_empty_distribution(self):
        result = self.generator._calculate_question_distribution(10, {})
        assert result == {}

    def test_distribution_zero_questions(self):
        distribution = {"single_fact": 0.50, "multi_fact": 0.50}
        result = self.generator._calculate_question_distribution(0, distribution)
        assert result == {}


class TestParseDocumentQuestionResponse:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_parse_valid_response(self):
        response = """{
            "question": "2024年光模块市场规模多少？",
            "answer": "2024年光模块市场规模约为100亿美元。",
            "question_type": "single_fact",
            "difficulty": "easy",
            "reasoning": "这是一个直接的数据查询问题",
            "key_entities": ["光模块", "市场规模"],
            "answer_sources": ["第3段"]
        }"""
        result = self.generator._parse_document_question_response(response)
        assert result is not None
        assert result["question"] == "2024年光模块市场规模多少？"
        assert result["question_type"] == "single_fact"
        assert result["difficulty"] == "easy"

    def test_parse_response_in_code_block(self):
        response = """```json
        {
            "question": "CPO的全称是什么？",
            "answer": "CPO的全称是Co-packaged Optics。",
            "question_type": "single_fact"
        }
        ```"""
        result = self.generator._parse_document_question_response(response)
        assert result is not None
        assert result["question"] == "CPO的全称是什么？"

    def test_parse_response_with_surrounding_text(self):
        response = """好的，这是生成的问题：
        {"question": "营收增长原因？", "answer": "主要因为新产品销售增长。", "question_type": "reasoning"}
        希望对你有帮助。"""
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
        response = (
            '{"question": "问题？", "answer": "答案", "question_type": "single_fact"}'
        )
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
            assert result["is_authentic"] is False, (
                f"Pattern should be detected: {question}"
            )

    def test_all_template_starts(self):
        starts = [
            "请问市场规模是多少？",
            "请解释技术原理",
            "请描述产品特点",
        ]
        for question in starts:
            result = self.generator._check_authenticity_rules(question)
            assert result["is_authentic"] is False, (
                f"Template start should be detected: {question}"
            )


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
        type_counts = {
            "single_fact": 15,
            "multi_fact": 12,
            "reasoning": 7,
            "comparative": 7,
            "missing": 5,
            "irrelevant": 4,
        }
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
        type_counts = {
            "single_fact": 15,
            "multi_fact": 12,
            "reasoning": 7,
            "comparative": 7,
            "missing": 5,
            "irrelevant": 4,
        }
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
            "parser": {},
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

        with patch(
            "src.test_generation.document_loader.resolve_parsed_dir",
            return_value=parsed_dir,
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

        with patch(
            "src.test_generation.document_loader.resolve_parsed_dir", return_value=None
        ):
            result = self.generator._load_full_documents(meal_config)

        assert result == {}


class TestDocumentBasedQuestionsSourceFiles:
    def setup_method(self):
        self.config = {
            "parser": {},
            "test_generation": {"max_retries": 3, "default_num_questions": 20},
        }
        self.generator = TestSetGenerator(self.config)

    def test_source_files_set_in_generated_questions(self, tmp_path):
        parsed_dir = tmp_path / "parsed"
        sub_dir = parsed_dir / "research_reports"
        sub_dir.mkdir(parents=True)
        md_file = sub_dir / "光模块行业分析.md"
        md_file.write_text("光模块行业内容" * 100, encoding="utf-8")

        chunks_dir = tmp_path / "chunks"
        chunks_source_dir = chunks_dir / "research_reports"
        chunks_source_dir.mkdir(parents=True)
        chunk_data = {
            "chunk_id": "光模块行业分析_000",
            "text": "光模块行业内容" * 100,
            "metadata": {
                "source": "research_reports/光模块行业分析.md",
                "chunk_index": 0,
            },
        }
        jsonl_file = chunks_source_dir / "光模块行业分析.jsonl"
        with open(jsonl_file, "w", encoding="utf-8") as f:
            f.write(json.dumps(chunk_data, ensure_ascii=False) + "\n")

        meal_config = MagicMock()
        meal_config.data_id = "test_data_id"
        meal_config.pdf_files = [MagicMock(path="research_reports/光模块行业分析.pdf")]

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        mock_generator = MagicMock()
        mock_generator.generate.return_value = json.dumps(
            {
                "question": "光模块市场规模多少？",
                "answer": "约100亿美元",
                "question_type": "single_fact",
                "difficulty": "easy",
                "reasoning": "测试",
                "key_entities": ["光模块"],
                "answer_sources": ["第1段"],
                "evidence": [
                    {
                        "quote": "光模块行业内容" * 10,
                        "source_segment": 0,
                        "match_type": "exact",
                    }
                ],
            }
        )

        with (
            patch(
                "src.test_generation.document_loader.resolve_parsed_dir",
                return_value=parsed_dir,
            ),
            patch(
                "src.test_generation.document_loader.resolve_chunks_dir",
                return_value=chunks_dir,
            ),
            patch(
                "src.test_generation.generator.MealManager",
                return_value=mock_meal_manager,
            ),
            patch(
                "src.test_generation.generator.Generator", return_value=mock_generator
            ),
            patch(
                "src.test_generation.generator.get_llm_config",
                return_value={
                    "model_name": "test",
                    "api_key": "test",
                    "base_url": "http://test",
                },
            ),
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
            "parser": {},
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
        questions_pool = [
            ("营收增长多少？", "20%"),
            ("利润率是多少？", "15%"),
            ("资产规模多大？", "500亿"),
            ("负债率多少？", "30%"),
            ("现金流情况如何？", "正增长"),
        ]

        def mock_generate(query, contexts, system_prompt, category, **kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 2:
                return "invalid json"
            idx = (call_count - 3) % len(questions_pool)
            q_text, a_text = questions_pool[idx]
            return json.dumps(
                {
                    "question": q_text,
                    "answer": a_text,
                    "question_type": "single_fact",
                    "difficulty": "easy",
                    "reasoning": "",
                    "key_entities": [],
                    "answer_sources": [],
                    "evidence": [
                        {
                            "quote": "文档内容营收增长数据分析",
                            "segment_index": 0,
                            "match_type": "exact",
                        }
                    ],
                }
            )

        mock_llm_generator = MagicMock()
        mock_llm_generator.generate.side_effect = mock_generate

        with (
            patch(
                "src.test_generation.document_loader.resolve_parsed_dir",
                return_value=parsed_dir,
            ),
            patch(
                "src.test_generation.generator.MealManager",
                return_value=mock_meal_manager,
            ),
            patch(
                "src.test_generation.generator.Generator",
                return_value=mock_llm_generator,
            ),
            patch(
                "src.test_generation.generator.get_llm_config",
                return_value={
                    "model_name": "test",
                    "api_key": "test",
                    "base_url": "http://test",
                },
            ),
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

        with (
            patch(
                "src.test_generation.document_loader.resolve_parsed_dir",
                return_value=parsed_dir,
            ),
            patch(
                "src.test_generation.generator.MealManager",
                return_value=mock_meal_manager,
            ),
            patch(
                "src.test_generation.generator.Generator",
                return_value=mock_llm_generator,
            ),
            patch(
                "src.test_generation.generator.get_llm_config",
                return_value={
                    "model_name": "test",
                    "api_key": "test",
                    "base_url": "http://test",
                },
            ),
            pytest.raises(TestSetError, match="No questions could be generated"),
        ):
            self.generator.generate_document_based_questions(
                meal_name="test_meal",
                num_questions=5,
                type_distribution={"single_fact": 1.0},
            )


class TestSupplementDocumentBasedQuestions:
    def setup_method(self):
        self.config = {
            "parser": {},
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
                {
                    "id": "q001",
                    "question": "问题1？",
                    "answer": "答案1",
                    "question_type": "single_fact",
                },
                {
                    "id": "q002",
                    "question": "问题2？",
                    "answer": "答案2",
                    "question_type": "single_fact",
                },
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
                {
                    "id": "q001",
                    "question": "问题1？",
                    "answer": "答案1",
                    "question_type": "single_fact",
                },
                {
                    "id": "q002",
                    "question": "问题2？",
                    "answer": "答案2",
                    "question_type": "single_fact",
                },
                {
                    "id": "q003",
                    "question": "问题3？",
                    "answer": "答案3",
                    "question_type": "single_fact",
                },
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
        meal_config.pdf_files = [MagicMock(path="research_reports/doc_a.pdf")]

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        mock_llm_generator = MagicMock()
        supplement_responses = [
            json.dumps(
                {
                    "question": "新增问题1？",
                    "answer": "新增答案1",
                    "question_type": "single_fact",
                    "difficulty": "easy",
                    "reasoning": "",
                    "key_entities": [],
                    "answer_sources": [],
                }
            ),
            json.dumps(
                {
                    "question": "新增问题2？",
                    "answer": "新增答案2",
                    "question_type": "single_fact",
                    "difficulty": "easy",
                    "reasoning": "",
                    "key_entities": [],
                    "answer_sources": [],
                }
            ),
        ]
        mock_llm_generator.generate.side_effect = supplement_responses * 10

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
                {
                    "id": "q001",
                    "question": "问题1？",
                    "answer": "答案1",
                    "question_type": "single_fact",
                    "source_document": "doc_a",
                    "category": "document",
                    "source_files": [],
                    "source_chunks": [],
                },
                {
                    "id": "q002",
                    "question": "问题2？",
                    "answer": "答案2",
                    "question_type": "single_fact",
                    "source_document": "doc_a",
                    "category": "document",
                    "source_files": [],
                    "source_chunks": [],
                },
                {
                    "id": "q003",
                    "question": "问题3？",
                    "answer": "答案3",
                    "question_type": "reasoning",
                    "source_document": "doc_a",
                    "category": "document",
                    "source_files": [],
                    "source_chunks": [],
                },
            ],
            "quality_metrics": {},
        }

        with (
            patch(
                "src.test_generation.document_loader.resolve_parsed_dir",
                return_value=parsed_dir,
            ),
            patch(
                "src.test_generation.generator.MealManager",
                return_value=mock_meal_manager,
            ),
            patch(
                "src.test_generation.generator.Generator",
                return_value=mock_llm_generator,
            ),
            patch(
                "src.test_generation.generator.get_llm_config",
                return_value={
                    "model_name": "test",
                    "api_key": "test",
                    "base_url": "http://test",
                },
            ),
            pytest.warns(
                DeprecationWarning, match="_locate_answer_chunks is deprecated"
            ),
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
        meal_config.pdf_files = [MagicMock(path="research_reports/doc_a.pdf")]

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
                {
                    "id": "q001",
                    "question": "问题1？",
                    "answer": "答案1",
                    "question_type": "single_fact",
                },
            ],
            "quality_metrics": {},
        }

        with (
            patch(
                "src.test_generation.document_loader.resolve_parsed_dir",
                return_value=parsed_dir,
            ),
            patch(
                "src.test_generation.generator.MealManager",
                return_value=mock_meal_manager,
            ),
            patch(
                "src.test_generation.generator.Generator",
                return_value=mock_llm_generator,
            ),
            patch(
                "src.test_generation.generator.get_llm_config",
                return_value={
                    "model_name": "test",
                    "api_key": "test",
                    "base_url": "http://test",
                },
            ),
        ):
            result = self.generator.supplement_document_based_questions(
                meal_name="test_meal",
                existing_test_set=existing,
                target_count=3,
            )

        assert len(result["questions"]) == 1


class TestDocTruncateCacheKeyStability:
    def test_doc_truncate_cache_key_stability(self):
        content = "A" * 2000
        key1 = hashlib.sha256(content[:1000].encode()).hexdigest()[:16]
        key2 = hashlib.sha256(content[:1000].encode()).hexdigest()[:16]
        assert key1 == key2
        different_content = "B" * 2000
        key3 = hashlib.sha256(different_content[:1000].encode()).hexdigest()[:16]
        assert key1 != key3


class TestSegmentDocument:
    def setup_method(self):
        self.config = {
            "test_generation": {"max_retries": 3},
        }
        self.generator = TestSetGenerator(self.config)

    def test_short_document_returns_single_segment(self):
        doc = "这是一个短文档。只有几百个字符。"
        segments = self.generator._segment_document(doc, segment_size=1000)
        assert len(segments) == 1
        assert segments[0]["text"] == doc
        assert segments[0]["start_char"] == 0
        assert segments[0]["end_char"] == len(doc)
        assert segments[0]["segment_index"] == 0

    def test_long_document_returns_multiple_segments(self):
        sentence = "这是一句话。"
        doc = sentence * 100
        segment_size = 50
        segments = self.generator._segment_document(doc, segment_size=segment_size)
        assert len(segments) > 1
        total_chars = sum(seg["end_char"] - seg["start_char"] for seg in segments)
        assert total_chars <= len(doc)

    def test_segments_end_at_sentence_boundaries(self):
        sentences = ["第一句话内容很长。", "第二句话也很长。", "第三句话继续。"]
        doc = "".join(sentences)
        segment_size = 15
        segments = self.generator._segment_document(doc, segment_size=segment_size)
        for seg in segments:
            text = seg["text"]
            if text and text[-1] not in [
                "。",
                "！",
                "？",
                "！",
                "?",
                "!",
                "\n",
                "；",
                ";",
            ]:
                raise AssertionError(
                    f"Segment does not end at sentence boundary: {text[-10:]}"
                )

    def test_empty_document_returns_empty_list(self):
        segments = self.generator._segment_document("", segment_size=1000)
        assert segments == []

    def test_document_exactly_segment_size(self):
        doc = "a" * 1000
        segments = self.generator._segment_document(doc, segment_size=1000)
        assert len(segments) == 1
        assert segments[0]["text"] == doc

    def test_segment_indices_are_sequential(self):
        sentence = "这是一句话。"
        doc = sentence * 50
        segments = self.generator._segment_document(doc, segment_size=50)
        for i, seg in enumerate(segments):
            assert seg["segment_index"] == i

    def test_segments_cover_entire_document(self):
        sentence = "这是一句话。"
        doc = sentence * 100
        segments = self.generator._segment_document(doc, segment_size=100)
        covered_chars = set()
        for seg in segments:
            for i in range(seg["start_char"], seg["end_char"]):
                covered_chars.add(i)
        expected_chars = set(range(len(doc)))
        assert covered_chars == expected_chars


class TestBuildSegmentsFromPages:
    def setup_method(self):
        self.config = {
            "test_generation": {
                "segment_size": 8000,
                "default_num_questions": 10,
            }
        }
        self.generator = TestSetGenerator(self.config)

    def test_empty_pages_returns_empty(self):
        segments = self.generator._build_segments_from_pages([])
        assert segments == []

    def test_single_short_page_returns_single_segment(self):
        pages = [{"page_number": 1, "text": "短文档内容"}]
        segments = self.generator._build_segments_from_pages(pages, target_chars=8000)
        assert len(segments) == 1
        assert segments[0]["page_numbers"] == [1]
        assert segments[0]["source_type"] == "pages_json"
        assert segments[0]["segment_index"] == 0

    def test_multiple_pages_aggregate_into_segment(self):
        pages = [
            {"page_number": 1, "text": "第一页内容"},
            {"page_number": 2, "text": "第二页内容"},
        ]
        segments = self.generator._build_segments_from_pages(pages, target_chars=8000)
        assert len(segments) == 1
        assert segments[0]["page_numbers"] == [1, 2]
        assert "第一页内容" in segments[0]["text"]
        assert "第二页内容" in segments[0]["text"]

    def test_large_pages_split_into_multiple_segments(self):
        pages = [
            {"page_number": 1, "text": "A" * 9000},
            {"page_number": 2, "text": "B" * 9000},
        ]
        segments = self.generator._build_segments_from_pages(pages, target_chars=8000)
        assert len(segments) == 2
        assert segments[0]["page_numbers"] == [1]
        assert segments[1]["page_numbers"] == [2]
        assert segments[0]["segment_index"] == 0
        assert segments[1]["segment_index"] == 1

    def test_pages_sorted_by_page_number(self):
        pages = [
            {"page_number": 3, "text": "第三页"},
            {"page_number": 1, "text": "第一页"},
            {"page_number": 2, "text": "第二页"},
        ]
        segments = self.generator._build_segments_from_pages(pages, target_chars=8000)
        assert len(segments) == 1
        assert segments[0]["page_numbers"] == [1, 2, 3]
        text = segments[0]["text"]
        assert text.index("第一页") < text.index("第二页")
        assert text.index("第二页") < text.index("第三页")

    def test_empty_pages_skipped(self):
        pages = [
            {"page_number": 1, "text": "有内容"},
            {"page_number": 2, "text": ""},
            {"page_number": 3, "text": "   "},
            {"page_number": 4, "text": "也有内容"},
        ]
        segments = self.generator._build_segments_from_pages(pages, target_chars=8000)
        assert len(segments) == 1
        assert segments[0]["page_numbers"] == [1, 4]

    def test_start_end_char_positions(self):
        pages = [
            {"page_number": 1, "text": "AAA"},
            {"page_number": 2, "text": "BBB"},
        ]
        segments = self.generator._build_segments_from_pages(pages, target_chars=8000)
        assert len(segments) == 1
        assert segments[0]["start_char"] == 0
        assert segments[0]["end_char"] == len(segments[0]["text"])


class TestLocateSourceChunks:
    def setup_method(self):
        self.config = {
            "test_generation": {
                "segment_size": 8000,
                "default_num_questions": 10,
            }
        }
        self.generator = TestSetGenerator(self.config)
        self.doc_chunks = [
            {
                "chunk_id": "doc_p1_000",
                "text": "这是第一页的内容，包含重要信息。",
                "metadata": {"page_number": 1},
            },
            {
                "chunk_id": "doc_p1_001",
                "text": "第一页的更多内容，关于市场分析。",
                "metadata": {"page_number": 1},
            },
            {
                "chunk_id": "doc_p2_000",
                "text": "第二页讨论了行业趋势和前景。",
                "metadata": {"page_number": 2},
            },
            {
                "chunk_id": "doc_p3_000",
                "text": "第三页包含财务数据和预测。",
                "metadata": {"page_number": 3},
            },
        ]

    def test_exact_quote_match(self):
        result = self.generator._locate_source_chunks(
            [1], "这是第一页的内容，包含重要信息。", self.doc_chunks
        )
        assert "doc_p1_000" in result

    def test_page_filter_narrows_candidates(self):
        result = self.generator._locate_source_chunks([2], "行业趋势", self.doc_chunks)
        assert "doc_p2_000" in result
        assert "doc_p1_000" not in result
        assert "doc_p3_000" not in result

    def test_multiple_pages_returns_chunks_from_all(self):
        result = self.generator._locate_source_chunks(
            [1, 2], "行业趋势", self.doc_chunks
        )
        assert "doc_p2_000" in result

    def test_empty_page_numbers_returns_empty(self):
        result = self.generator._locate_source_chunks([], "行业趋势", self.doc_chunks)
        assert result == []

    def test_no_matching_page_returns_empty(self):
        result = self.generator._locate_source_chunks([99], "行业趋势", self.doc_chunks)
        assert result == []

    def test_no_quote_returns_all_page_chunks(self):
        result = self.generator._locate_source_chunks([1], "", self.doc_chunks)
        assert len(result) == 2
        assert "doc_p1_000" in result
        assert "doc_p1_001" in result

    def test_quote_not_in_candidates_falls_back_to_page_level(self):
        result = self.generator._locate_source_chunks(
            [1], "这段话绝对不存在于任何chunk中", self.doc_chunks
        )
        assert len(result) == 2
        assert "doc_p1_000" in result
        assert "doc_p1_001" in result

    def test_cross_page_chunk_mapped(self):
        chunks = self.doc_chunks + [
            {
                "chunk_id": "doc_cross",
                "text": "跨页内容",
                "metadata": {
                    "page_number": 2,
                    "cross_page": True,
                    "overlap_from_page": 1,
                },
            },
        ]
        result = self.generator._locate_source_chunks([2], "跨页内容", chunks)
        assert "doc_cross" in result


class TestSelectSegmentsForQuestionType:
    def setup_method(self):
        self.config = {
            "test_generation": {
                "max_retries": 3,
                "segment_sampling_strategy": "random",
            },
        }
        self.generator = TestSetGenerator(self.config)
        self.segments = [
            {
                "text": f"段落{i}",
                "segment_index": i,
                "start_char": i * 100,
                "end_char": (i + 1) * 100,
            }
            for i in range(10)
        ]

    def test_single_fact_returns_one_segment(self):
        selected = self.generator._select_segments_for_question_type(
            self.segments, "single_fact"
        )
        assert len(selected) == 1

    def test_multi_fact_returns_two_to_three_segments(self):
        for _ in range(10):
            selected = self.generator._select_segments_for_question_type(
                self.segments, "multi_fact"
            )
            assert 2 <= len(selected) <= 3

    def test_reasoning_returns_two_to_three_segments(self):
        for _ in range(10):
            selected = self.generator._select_segments_for_question_type(
                self.segments, "reasoning"
            )
            assert 2 <= len(selected) <= 3

    def test_comparative_returns_two_to_three_segments(self):
        for _ in range(10):
            selected = self.generator._select_segments_for_question_type(
                self.segments, "comparative"
            )
            assert 2 <= len(selected) <= 3

    def test_missing_returns_one_segment(self):
        selected = self.generator._select_segments_for_question_type(
            self.segments, "missing"
        )
        assert len(selected) == 1

    def test_irrelevant_returns_empty_list(self):
        selected = self.generator._select_segments_for_question_type(
            self.segments, "irrelevant"
        )
        assert selected == []

    def test_empty_segments_returns_empty_list(self):
        selected = self.generator._select_segments_for_question_type([], "single_fact")
        assert selected == []

    def test_fewer_segments_than_requested(self):
        few_segments = self.segments[:2]
        selected = self.generator._select_segments_for_question_type(
            few_segments, "multi_fact"
        )
        assert len(selected) == 2

    def test_unknown_type_uses_num_segments_parameter(self):
        selected = self.generator._select_segments_for_question_type(
            self.segments, "unknown_type", num_segments=3
        )
        assert len(selected) == 3

    def test_sequential_strategy(self):
        config = {
            "test_generation": {
                "max_retries": 3,
                "segment_sampling_strategy": "sequential",
            },
        }
        generator = TestSetGenerator(config)
        selected = generator._select_segments_for_question_type(
            self.segments, "multi_fact"
        )
        assert 2 <= len(selected) <= 3
        indices = [s["segment_index"] for s in selected]
        for i in range(len(indices) - 1):
            assert indices[i + 1] == indices[i] + 1


class TestVerifyQuoteInSegment:
    def setup_method(self):
        self.config = {
            "test_generation": {
                "max_retries": 3,
                "quote_fuzzy_match_threshold": 0.85,
            },
        }
        self.generator = TestSetGenerator(self.config)

    def test_exact_match(self):
        segment = "这是一段文本，其中包含引用的内容。"
        quote = "包含引用"
        result = self.generator._verify_quote_in_segment(quote, segment)
        assert result["found"] is True
        assert result["match_type"] == "exact"
        assert result["position"] is not None

    def test_no_match(self):
        segment = "这是一段文本。"
        quote = "不存在的引用"
        result = self.generator._verify_quote_in_segment(quote, segment)
        assert result["found"] is False
        assert result["match_type"] is None
        assert result["position"] is None

    def test_fuzzy_match_minor_difference(self):
        segment = "这是一段文本，其中包含引用的内容。"
        quote = "包含引用的内容。"
        result = self.generator._verify_quote_in_segment(quote, segment)
        assert result["found"] is True
        assert result["match_type"] == "exact"

    def test_empty_quote_returns_not_found(self):
        segment = "这是一段文本。"
        result = self.generator._verify_quote_in_segment("", segment)
        assert result["found"] is False

    def test_empty_segment_returns_not_found(self):
        result = self.generator._verify_quote_in_segment("引用", "")
        assert result["found"] is False

    def test_both_empty_returns_not_found(self):
        result = self.generator._verify_quote_in_segment("", "")
        assert result["found"] is False

    def test_quote_longer_than_segment(self):
        segment = "短文本"
        quote = "这是一个非常长的引用内容，比段落本身还要长"
        result = self.generator._verify_quote_in_segment(quote, segment)
        assert result["found"] is False


class TestValidateEvidence:
    def setup_method(self):
        self.config = {
            "test_generation": {
                "max_retries": 3,
                "quote_fuzzy_match_threshold": 0.85,
            },
        }
        self.generator = TestSetGenerator(self.config)
        self.segments = [
            {
                "text": "第一段内容，包含营收数据及相关分析，同比增长显著，公司业绩表现优异，市场前景广阔。",
                "segment_index": 0,
            },
            {
                "text": "第二段内容，包含利润数据及趋势预测，环比有所改善，盈利能力持续增强，投资价值凸显。",
                "segment_index": 1,
            },
            {
                "text": "第三段内容，包含增长数据及市场前景，展望较为乐观，行业整体向好发展，未来可期。",
                "segment_index": 2,
            },
        ]

    def test_valid_evidence_all_quotes_found(self):
        evidence_list = [
            {
                "segment_index": 0,
                "quote": "包含营收数据及相关分析，同比增长显著，公司业绩表现优异，市场前景广阔",
            },
            {
                "segment_index": 1,
                "quote": "包含利润数据及趋势预测，环比有所改善，盈利能力持续增强，投资价值凸显",
            },
        ]
        result = self.generator._validate_evidence(evidence_list, self.segments)
        assert result["valid"] is True
        assert len(result["verified_evidence"]) == 2
        assert len(result["invalid_quotes"]) == 0
        for ev in result["verified_evidence"]:
            assert ev["verified"] is True

    def test_invalid_evidence_some_quotes_not_found(self):
        evidence_list = [
            {
                "segment_index": 0,
                "quote": "包含营收数据及相关分析，同比增长显著，公司业绩表现优异，市场前景广阔",
            },
            {
                "segment_index": 1,
                "quote": "这段完全不存在的数据内容无法匹配原文信息，虚构内容测试用例补充长度",
            },
        ]
        result = self.generator._validate_evidence(evidence_list, self.segments)
        assert result["valid"] is False
        assert len(result["invalid_quotes"]) == 1
        assert result["verified_evidence"][0]["verified"] is True
        assert result["verified_evidence"][1]["verified"] is False

    def test_invalid_segment_index(self):
        evidence_list = [
            {
                "segment_index": 99,
                "quote": "包含营收数据及相关分析，同比增长显著，公司业绩表现优异，市场前景广阔",
            },
        ]
        result = self.generator._validate_evidence(evidence_list, self.segments)
        assert result["valid"] is False
        assert len(result["invalid_quotes"]) == 1
        assert "Invalid segment_index" in result["invalid_quotes"][0]["reason"]

    def test_missing_segment_index(self):
        evidence_list = [
            {
                "quote": "包含营收数据及相关分析，同比增长显著，公司业绩表现优异，市场前景广阔"
            },
        ]
        result = self.generator._validate_evidence(evidence_list, self.segments)
        assert result["valid"] is False
        assert len(result["invalid_quotes"]) == 1
        assert "Missing segment_index" in result["invalid_quotes"][0]["reason"]

    def test_empty_evidence_list_returns_valid(self):
        result = self.generator._validate_evidence([], self.segments)
        assert result["valid"] is True
        assert result["verified_evidence"] == []
        assert result["invalid_quotes"] == []

    def test_evidence_with_fuzzy_match(self):
        evidence_list = [
            {
                "segment_index": 0,
                "quote": "包含营收数据及相关分析，同比增长显著，公司业绩表现优异，市场前景广阔。",
            },
        ]
        result = self.generator._validate_evidence(evidence_list, self.segments)
        assert result["verified_evidence"][0]["verified"] is True
        assert result["verified_evidence"][0]["match_type"] == "exact"


class TestLocateChunksByQuote:
    def setup_method(self):
        self.config = {
            "test_generation": {
                "max_retries": 3,
                "quote_fuzzy_match_threshold": 0.85,
            },
        }
        self.generator = TestSetGenerator(self.config)

    def test_quote_found_in_one_chunk(self):
        segments = [
            {
                "text": "营收增长9.53%，净利润增长12.75%。",
                "segment_index": 0,
                "start_char": 0,
                "end_char": 20,
            },
        ]
        segment_chunk_map = {0: ["chunk_001", "chunk_002"]}
        doc_chunks = [
            {"chunk_id": "chunk_001", "text": "营收增长9.53%，净利润增长12.75%。"},
            {"chunk_id": "chunk_002", "text": "其他内容。"},
        ]
        result = self.generator._locate_chunks_by_quote(
            "营收增长9.53%", segments, segment_chunk_map, doc_chunks
        )
        assert len(result) == 1
        assert "chunk_001" in result

    def test_quote_found_in_multiple_chunks(self):
        segments = [
            {
                "text": "营收增长9.53%，净利润增长12.75%。",
                "segment_index": 0,
                "start_char": 0,
                "end_char": 20,
            },
        ]
        segment_chunk_map = {0: ["chunk_001", "chunk_002"]}
        doc_chunks = [
            {"chunk_id": "chunk_001", "text": "营收增长9.53%"},
            {"chunk_id": "chunk_002", "text": "营收增长9.53%，净利润增长12.75%。"},
        ]
        result = self.generator._locate_chunks_by_quote(
            "营收增长9.53%", segments, segment_chunk_map, doc_chunks
        )
        assert len(result) == 2

    def test_quote_not_found(self):
        segments = [
            {
                "text": "营收增长9.53%。",
                "segment_index": 0,
                "start_char": 0,
                "end_char": 10,
            },
        ]
        segment_chunk_map = {0: ["chunk_001"]}
        doc_chunks = [
            {"chunk_id": "chunk_001", "text": "营收增长9.53%。"},
        ]
        result = self.generator._locate_chunks_by_quote(
            "不存在的引用", segments, segment_chunk_map, doc_chunks
        )
        assert result == []

    def test_empty_inputs(self):
        assert self.generator._locate_chunks_by_quote("", [], {}, []) == []
        assert self.generator._locate_chunks_by_quote("quote", [], {}, []) == []
        assert self.generator._locate_chunks_by_quote("quote", [{}], {}, []) == []

    def test_quote_not_in_mapped_chunks(self):
        segments = [
            {
                "text": "营收增长9.53%。",
                "segment_index": 0,
                "start_char": 0,
                "end_char": 10,
            },
        ]
        segment_chunk_map = {0: ["chunk_001"]}
        doc_chunks = [
            {"chunk_id": "chunk_001", "text": "其他不相关的内容。"},
        ]
        result = self.generator._locate_chunks_by_quote(
            "营收增长9.53%", segments, segment_chunk_map, doc_chunks
        )
        assert result == []


class TestSelectCandidateSegments:
    def setup_method(self):
        self.config = {
            "test_generation": {
                "max_retries": 3,
                "segment_sampling_strategy": "random",
            },
        }
        self.generator = TestSetGenerator(self.config)
        self.segments = [
            {
                "text": f"段落{i}",
                "segment_index": i,
                "start_char": i * 100,
                "end_char": (i + 1) * 100,
            }
            for i in range(20)
        ]

    def test_multi_hop_returns_diverse_segments(self):
        selected = self.generator._select_candidate_segments(
            self.segments, "multi_fact", num_candidates=4
        )
        assert len(selected) == 4
        indices = [s["segment_index"] for s in selected]
        assert len(set(indices)) == len(indices)

    def test_multi_hop_returns_correct_count(self):
        for count in [2, 3, 4]:
            selected = self.generator._select_candidate_segments(
                self.segments, "reasoning", num_candidates=count
            )
            assert len(selected) == count

    def test_comparative_returns_correct_count(self):
        selected = self.generator._select_candidate_segments(
            self.segments, "comparative", num_candidates=3
        )
        assert len(selected) == 3

    def test_single_fact_delegates_to_select_segments(self):
        selected = self.generator._select_candidate_segments(
            self.segments, "single_fact", num_candidates=4
        )
        assert len(selected) == 1

    def test_empty_segments_returns_empty(self):
        selected = self.generator._select_candidate_segments(
            [], "multi_fact", num_candidates=4
        )
        assert selected == []

    def test_fewer_segments_than_candidates(self):
        few_segments = self.segments[:2]
        selected = self.generator._select_candidate_segments(
            few_segments, "multi_fact", num_candidates=4
        )
        assert len(selected) == 2

    def test_sequential_strategy(self):
        config = {
            "test_generation": {
                "max_retries": 3,
                "segment_sampling_strategy": "sequential",
            },
        }
        generator = TestSetGenerator(config)
        selected = generator._select_candidate_segments(
            self.segments, "multi_fact", num_candidates=4
        )
        assert len(selected) == 4
        indices = [s["segment_index"] for s in selected]
        for i in range(len(indices) - 1):
            assert indices[i + 1] == indices[i] + 1


class TestHallucinationDetection:
    def setup_method(self):
        self.config = {
            "test_generation": {
                "max_retries": 3,
                "quote_fuzzy_match_threshold": 0.85,
            },
        }
        self.generator = TestSetGenerator(self.config)
        self.segments = [
            {
                "text": "第一段内容，包含营收数据及相关分析，同比增长显著，公司业绩表现优异，市场前景广阔。",
                "segment_index": 0,
            },
            {
                "text": "第二段内容，包含利润数据及趋势预测，环比有所改善，盈利能力持续增强，投资价值凸显。",
                "segment_index": 1,
            },
        ]

    def test_invalid_quote_detected_in_result(self):
        evidence_list = [
            {
                "segment_index": 0,
                "quote": "这段完全不存在的引用内容无法匹配原文信息，虚构内容测试用例补充长度",
            },
        ]
        result = self.generator._validate_evidence(evidence_list, self.segments)

        assert result["valid"] is False
        assert len(result["invalid_quotes"]) == 1
        assert "not found" in result["invalid_quotes"][0]["reason"].lower()

    def test_valid_quote_no_invalid_entries(self):
        evidence_list = [
            {
                "segment_index": 0,
                "quote": "包含营收数据及相关分析，同比增长显著，公司业绩表现优异，市场前景广阔",
            },
        ]
        result = self.generator._validate_evidence(evidence_list, self.segments)

        assert result["valid"] is True
        assert len(result["invalid_quotes"]) == 0

    def test_multiple_invalid_quotes_all_detected(self):
        evidence_list = [
            {
                "segment_index": 0,
                "quote": "这段完全不存在的引用内容一无法匹配原文，虚构内容测试用例补充长度一",
            },
            {
                "segment_index": 1,
                "quote": "这段完全不存在的引用内容二无法匹配原文，虚构内容测试用例补充长度二",
            },
        ]
        result = self.generator._validate_evidence(evidence_list, self.segments)

        assert result["valid"] is False
        assert len(result["invalid_quotes"]) == 2
        reasons = [q["reason"] for q in result["invalid_quotes"]]
        assert all("not found" in r.lower() for r in reasons)


class TestValidateNumericalAccuracy:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_valid_no_numerical_issues(self):
        qa = {
            "answer": "营收为121.63亿元",
            "ground_truth_excerpt": "营收12,162,684,368.86元",
        }
        is_valid, correction = self.generator._validate_numerical_accuracy(qa)
        assert is_valid is True
        assert correction is None

    def test_10x_error_detected(self):
        qa = {
            "answer": "营收为1216.3亿元",
            "ground_truth_excerpt": "营收12,162,684,368.86元",
        }
        is_valid, correction = self.generator._validate_numerical_accuracy(qa)
        assert is_valid is False
        assert correction is not None
        assert any(e["type"] == "10x_error" for e in correction["errors"])

    def test_empty_answer_returns_valid(self):
        qa = {"answer": "", "ground_truth_excerpt": "营收12,162,684,368.86元"}
        is_valid, correction = self.generator._validate_numerical_accuracy(qa)
        assert is_valid is True

    def test_no_large_numbers_returns_valid(self):
        qa = {"answer": "增长了5%", "ground_truth_excerpt": "增长率为5%"}
        is_valid, correction = self.generator._validate_numerical_accuracy(qa)
        assert is_valid is True


class TestVerifyExcerptInDocument:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_exact_match(self):
        doc = "公司2024年营收121.63亿元，同比增长12.5%。"
        excerpt = "营收121.63亿元"
        assert self.generator._verify_excerpt_in_document(excerpt, doc) is True

    def test_no_match(self):
        doc = "公司2024年营收121.63亿元。"
        excerpt = "净利润500亿元"
        assert self.generator._verify_excerpt_in_document(excerpt, doc) is False

    def test_fuzzy_match_with_whitespace(self):
        doc = "公司 2024 年 营收 121.63 亿元"
        excerpt = "公司2024年营收121.63亿元"
        assert self.generator._verify_excerpt_in_document(excerpt, doc) is True

    def test_empty_excerpt_returns_false(self):
        doc = "公司2024年营收121.63亿元。"
        assert self.generator._verify_excerpt_in_document("", doc) is False


class TestDetectContentOverlaps:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_no_overlap(self):
        docs = [
            {"doc_id": "a", "content": "光模块市场分析报告" * 50},
            {"doc_id": "b", "content": "新能源汽车行业研究" * 50},
        ]
        overlaps = self.generator._detect_content_overlaps(docs)
        assert len(overlaps) == 0

    def test_full_overlap_detected(self):
        base = "光模块市场分析报告内容填充" * 50
        long_content = base * 5
        short_content = base[:2000]
        docs = [
            {"doc_id": "full", "content": long_content},
            {"doc_id": "summary", "content": short_content},
        ]
        overlaps = self.generator._detect_content_overlaps(docs)
        assert len(overlaps) == 1
        assert overlaps[0][0] == "summary"
        assert overlaps[0][1] == "full"

    def test_short_documents_skipped(self):
        docs = [
            {"doc_id": "a", "content": "短"},
            {"doc_id": "b", "content": "短"},
        ]
        overlaps = self.generator._detect_content_overlaps(docs)
        assert len(overlaps) == 0


class TestBuildPrimaryPool:
    def setup_method(self):
        self.config = {"test_generation": {}}
        self.generator = TestSetGenerator(self.config)

    def test_excludes_supplementary(self):
        docs = [
            {"doc_id": "full", "content": "a" * 5000},
            {"doc_id": "summary", "content": "b" * 3000},
        ]
        overlaps = [("summary", "full", 0.9)]
        result = self.generator._build_primary_pool(docs, overlaps)
        assert len(result) == 1
        assert result[0]["doc_id"] == "full"

    def test_no_overlaps_returns_all(self):
        docs = [
            {"doc_id": "a", "content": "a" * 5000},
            {"doc_id": "b", "content": "b" * 5000},
        ]
        result = self.generator._build_primary_pool(docs, [])
        assert len(result) == 2


class TestQuestionDeduplication:
    def setup_method(self):
        self.config = {
            "parser": {},
            "test_generation": {"max_retries": 3, "default_num_questions": 20},
        }
        self.generator = TestSetGenerator(self.config)

    def test_supplement_skips_duplicate_question(self, tmp_path):
        parsed_dir = tmp_path / "parsed"
        sub_dir = parsed_dir / "research_reports"
        sub_dir.mkdir(parents=True)
        (sub_dir / "doc_a.md").write_text("文档A内容" * 100, encoding="utf-8")

        meal_config = MagicMock()
        meal_config.data_id = "test_data_id"
        meal_config.pdf_files = [MagicMock(path="research_reports/doc_a.pdf")]

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        mock_llm_generator = MagicMock()
        mock_llm_generator.generate.return_value = json.dumps(
            {
                "question": "美的集团2023年营业收入是多少？",
                "answer": "美的集团2023年营业收入为3737亿元",
                "question_type": "single_fact",
                "difficulty": "easy",
                "reasoning": "",
                "key_entities": [],
                "answer_sources": [],
            }
        )

        existing = {
            "metadata": {
                "name": "document_level_n3",
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
                {
                    "id": "q001",
                    "question": "美的集团2023年营业收入是多少？",
                    "answer": "答案1",
                    "question_type": "single_fact",
                    "source_document": "doc_a",
                    "category": "document",
                    "source_files": [],
                    "source_chunks": [],
                },
                {
                    "id": "q002",
                    "question": "格力电器2024年净利润是多少？",
                    "answer": "答案2",
                    "question_type": "single_fact",
                    "source_document": "doc_a",
                    "category": "document",
                    "source_files": [],
                    "source_chunks": [],
                },
            ],
            "quality_metrics": {},
        }

        with (
            patch(
                "src.test_generation.document_loader.resolve_parsed_dir",
                return_value=parsed_dir,
            ),
            patch(
                "src.test_generation.generator.MealManager",
                return_value=mock_meal_manager,
            ),
            patch(
                "src.test_generation.generator.Generator",
                return_value=mock_llm_generator,
            ),
            patch(
                "src.test_generation.generator.get_llm_config",
                return_value={
                    "model_name": "test",
                    "api_key": "test",
                    "base_url": "http://test",
                },
            ),
            pytest.warns(
                DeprecationWarning, match="_locate_answer_chunks is deprecated"
            ),
        ):
            result = self.generator.supplement_document_based_questions(
                meal_name="test_meal",
                existing_test_set=existing,
                target_count=5,
            )

        question_texts = [q["question"] for q in result["questions"]]
        assert question_texts.count("美的集团2023年营业收入是多少？") == 1

    def test_supplement_allows_different_questions(self, tmp_path):
        parsed_dir = tmp_path / "parsed"
        sub_dir = parsed_dir / "research_reports"
        sub_dir.mkdir(parents=True)
        (sub_dir / "doc_a.md").write_text("文档A内容" * 100, encoding="utf-8")

        meal_config = MagicMock()
        meal_config.data_id = "test_data_id"
        meal_config.pdf_files = [MagicMock(path="research_reports/doc_a.pdf")]

        mock_meal_manager = MagicMock()
        mock_meal_manager.load_meal.return_value = meal_config
        mock_meal_manager.get_meal_dir.return_value = tmp_path / "meals" / "test_meal"

        call_count = 0

        def mock_generate(query, contexts, system_prompt, category, **kwargs):
            nonlocal call_count
            call_count += 1
            return json.dumps(
                {
                    "question": f"第{call_count}个关于公司营收的新问题是什么？",
                    "answer": f"第{call_count}个新答案",
                    "question_type": "single_fact",
                    "difficulty": "easy",
                    "reasoning": "",
                    "key_entities": [],
                    "answer_sources": [],
                }
            )

        mock_llm_generator = MagicMock()
        mock_llm_generator.generate.side_effect = mock_generate

        existing = {
            "metadata": {
                "name": "document_level_n3",
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
                {
                    "id": "q001",
                    "question": "美的集团2023年营业收入是多少？",
                    "answer": "答案1",
                    "question_type": "single_fact",
                    "source_document": "doc_a",
                    "category": "document",
                    "source_files": [],
                    "source_chunks": [],
                },
            ],
            "quality_metrics": {},
        }

        with (
            patch(
                "src.test_generation.document_loader.resolve_parsed_dir",
                return_value=parsed_dir,
            ),
            patch(
                "src.test_generation.generator.MealManager",
                return_value=mock_meal_manager,
            ),
            patch(
                "src.test_generation.generator.Generator",
                return_value=mock_llm_generator,
            ),
            patch(
                "src.test_generation.generator.get_llm_config",
                return_value={
                    "model_name": "test",
                    "api_key": "test",
                    "base_url": "http://test",
                },
            ),
            pytest.warns(
                DeprecationWarning, match="_locate_answer_chunks is deprecated"
            ),
        ):
            result = self.generator.supplement_document_based_questions(
                meal_name="test_meal",
                existing_test_set=existing,
                target_count=3,
            )

        assert len(result["questions"]) == 3
        question_texts = [q["question"] for q in result["questions"]]
        assert len(set(question_texts)) == len(question_texts)
