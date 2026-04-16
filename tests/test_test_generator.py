import json
from pathlib import Path
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
