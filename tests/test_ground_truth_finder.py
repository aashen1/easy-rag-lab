import json

import pytest

from src.ground_truth_finder import find_chunks_by_source_page


def _write_jsonl(path, chunks):
    lines = [json.dumps(c, ensure_ascii=False) for c in chunks]
    path.write_text("\n".join(lines), encoding="utf-8")


@pytest.mark.unit
class TestFindChunksBySourcePage:
    def test_exact_match(self, tmp_path):
        chunks = [
            {
                "chunk_id": "test_001",
                "text": "revenue data on page 5",
                "metadata": {
                    "source": "annual_reports/2023/test.pdf",
                    "page_numbers": [5, 6],
                },
            },
            {
                "chunk_id": "test_002",
                "text": "unrelated chunk",
                "metadata": {
                    "source": "annual_reports/2023/other.pdf",
                    "page_numbers": [5, 6],
                },
            },
        ]
        jsonl_path = tmp_path / "chunks.jsonl"
        _write_jsonl(jsonl_path, chunks)

        results = find_chunks_by_source_page("test.pdf", 5, tmp_path)

        assert len(results) == 1
        assert results[0]["chunk_id"] == "test_001"
        assert results[0]["text"] == "revenue data on page 5"

    def test_no_match(self, tmp_path):
        chunks = [
            {
                "chunk_id": "test_001",
                "text": "some text",
                "metadata": {
                    "source": "annual_reports/2023/test.pdf",
                    "page_numbers": [5, 6],
                },
            },
        ]
        jsonl_path = tmp_path / "chunks.jsonl"
        _write_jsonl(jsonl_path, chunks)

        results = find_chunks_by_source_page("test.pdf", 99, tmp_path)

        assert results == []

    def test_fuzzy_match(self, tmp_path):
        chunks = [
            {
                "chunk_id": "test_001",
                "text": "spans pages 5-8",
                "metadata": {
                    "source": "annual_reports/2023/test.pdf",
                    "page_numbers": [5, 8],
                },
            },
        ]
        jsonl_path = tmp_path / "chunks.jsonl"
        _write_jsonl(jsonl_path, chunks)

        results = find_chunks_by_source_page("test.pdf", 7, tmp_path)

        assert len(results) == 1
        assert results[0]["chunk_id"] == "test_001"

    def test_multiple_matches(self, tmp_path):
        chunks = [
            {
                "chunk_id": "test_001",
                "text": "first chunk",
                "metadata": {
                    "source": "annual_reports/2023/test.pdf",
                    "page_numbers": [5, 6],
                },
            },
            {
                "chunk_id": "test_002",
                "text": "second chunk",
                "metadata": {
                    "source": "annual_reports/2023/test.pdf",
                    "page_numbers": [4, 5],
                },
            },
            {
                "chunk_id": "test_003",
                "text": "wrong pdf",
                "metadata": {
                    "source": "annual_reports/2023/other.pdf",
                    "page_numbers": [5],
                },
            },
        ]
        jsonl_path = tmp_path / "chunks.jsonl"
        _write_jsonl(jsonl_path, chunks)

        results = find_chunks_by_source_page("test.pdf", 5, tmp_path)

        assert len(results) == 2
        chunk_ids = {r["chunk_id"] for r in results}
        assert chunk_ids == {"test_001", "test_002"}

    def test_missing_dir(self, tmp_path):
        nonexistent = tmp_path / "no_such_dir"

        results = find_chunks_by_source_page("test.pdf", 1, nonexistent)

        assert results == []

    def test_io_error(self, tmp_path):
        corrupt_line = "{invalid json content"
        jsonl_path = tmp_path / "chunks.jsonl"
        jsonl_path.write_text(corrupt_line, encoding="utf-8")

        results = find_chunks_by_source_page("test.pdf", 1, tmp_path)

        assert results == []
