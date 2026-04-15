import json
from pathlib import Path

import pytest

from src.chunker import chunk_text, process_parsed_files


class TestChunkText:
    def test_chunk_text_empty_string(self):
        result = chunk_text("")
        assert result == []

    def test_chunk_text_whitespace_only(self):
        result = chunk_text("   \n\t  ")
        assert result == []

    def test_chunk_text_short_text(self):
        text = "This is a short text."
        result = chunk_text(text, chunk_size=100, overlap=0)

        assert len(result) == 1
        assert result[0]["text"] == text
        assert result[0]["metadata"]["token_count"] > 0

    def test_chunk_text_long_text(self):
        text = "This is a test sentence. " * 100
        result = chunk_text(text, chunk_size=50, overlap=0)

        assert len(result) > 1

        for i, chunk in enumerate(result):
            assert "text" in chunk
            assert "metadata" in chunk
            assert chunk["metadata"]["chunk_index"] == i
            assert chunk["metadata"]["token_count"] <= 50

    def test_chunk_text_with_overlap(self):
        text = "This is a test sentence. " * 100
        result = chunk_text(text, chunk_size=50, overlap=10)

        assert len(result) > 1

        for i, chunk in enumerate(result):
            assert chunk["metadata"]["token_count"] <= 50

    def test_chunk_text_token_count_accuracy(self):
        text = "This is a test sentence."
        result = chunk_text(text, chunk_size=100, overlap=0)

        assert len(result) == 1
        assert result[0]["metadata"]["char_count"] == len(text)

    def test_chunk_text_custom_encoding(self):
        text = "This is a test sentence."
        result = chunk_text(text, chunk_size=100, overlap=0, encoding_name="cl100k_base")

        assert len(result) == 1
        assert result[0]["text"] == text


class TestProcessParsedFiles:
    def test_process_parsed_files_input_dir_not_found(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            process_parsed_files("nonexistent_dir", "output_dir")
        assert "Input directory not found" in str(exc_info.value)

    def test_process_parsed_files_no_md_files(self, tmp_path):
        results = process_parsed_files(str(tmp_path), str(tmp_path / "output"))
        assert results == []

    def test_process_parsed_files_with_md_files(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        md_file = input_dir / "test.md"
        md_file.write_text("# Test Document\n\nThis is test content for chunking.")

        results = process_parsed_files(
            str(input_dir), str(output_dir), chunk_size=50, overlap=0
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert results[0]["chunk_count"] > 0

        output_file = Path(results[0]["output"])
        assert output_file.exists()
        assert output_file.suffix == ".jsonl"

        with open(output_file, "r", encoding="utf-8") as f:
            lines = f.readlines()
            assert len(lines) == results[0]["chunk_count"]

            for line in lines:
                chunk_data = json.loads(line)
                assert "chunk_id" in chunk_data
                assert "text" in chunk_data
                assert "metadata" in chunk_data
                assert "source" in chunk_data["metadata"]
                assert "category" in chunk_data["metadata"]

    def test_process_parsed_files_auto_category_detection(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        annual_report_dir = input_dir / "annual_reports"
        annual_report_dir.mkdir()
        md_file1 = annual_report_dir / "test1.md"
        md_file1.write_text("# Annual Report\n\nTest content.")

        research_report_dir = input_dir / "research_reports"
        research_report_dir.mkdir()
        md_file2 = research_report_dir / "test2.md"
        md_file2.write_text("# Research Report\n\nTest content.")

        results = process_parsed_files(str(input_dir), str(output_dir))

        assert len(results) == 2
        categories = [r["category"] for r in results]
        assert "annual_report" in categories
        assert "research_report" in categories

    def test_process_parsed_files_with_overlap(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        md_file = input_dir / "test.md"
        md_file.write_text("This is a test sentence. " * 50)

        results_no_overlap = process_parsed_files(
            str(input_dir), str(output_dir / "no_overlap"), chunk_size=50, overlap=0
        )

        results_with_overlap = process_parsed_files(
            str(input_dir), str(output_dir / "with_overlap"), chunk_size=50, overlap=10
        )

        assert results_no_overlap[0]["chunk_count"] > 0
        assert results_with_overlap[0]["chunk_count"] > 0

    def test_process_parsed_files_with_failures(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        md_file1 = input_dir / "valid.md"
        md_file1.write_text("# Valid Document\n\nThis is valid content.")

        md_file2 = input_dir / "empty.md"
        md_file2.write_text("")

        results = process_parsed_files(str(input_dir), str(output_dir))

        assert len(results) == 2
        success_count = sum(1 for r in results if r["status"] == "success")
        assert success_count >= 1

    def test_process_parsed_files_chunk_id_format(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        md_file = input_dir / "test_document.md"
        md_file.write_text("# Test\n\n" + "Content " * 100)

        results = process_parsed_files(
            str(input_dir), str(output_dir), chunk_size=50, overlap=0
        )

        output_file = Path(results[0]["output"])
        with open(output_file, "r", encoding="utf-8") as f:
            first_line = f.readline()
            chunk_data = json.loads(first_line)
            assert chunk_data["chunk_id"].startswith("test_document_")
            assert "_000" in chunk_data["chunk_id"]

    def test_process_parsed_files_preserves_directory_structure(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        
        nested_dir = input_dir / "annual_reports" / "2023" / "五粮液"
        nested_dir.mkdir(parents=True)
        
        md_file = nested_dir / "2023年度报告_英文_.md"
        md_file.write_text("# Test Document\n\nThis is test content for chunking.")

        results = process_parsed_files(
            str(input_dir), str(output_dir), chunk_size=50, overlap=0
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"
        
        expected_output = output_dir / "annual_reports" / "2023" / "五粮液" / "2023年度报告_英文_.jsonl"
        actual_output = Path(results[0]["output"])
        
        assert actual_output == expected_output
        assert actual_output.exists()
        
        with open(actual_output, "r", encoding="utf-8") as f:
            first_line = f.readline()
            chunk_data = json.loads(first_line)
            assert "source" in chunk_data["metadata"]
            expected_source_parts = ["annual_reports", "2023", "五粮液", "2023年度报告_英文_.md"]
            expected_source = str(Path(*expected_source_parts))
            assert chunk_data["metadata"]["source"] == expected_source

    def test_process_parsed_files_with_source_filter(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        md_file1 = input_dir / "keep.md"
        md_file1.write_text("# Keep\n\nThis file should be kept.")

        md_file2 = input_dir / "skip.md"
        md_file2.write_text("# Skip\n\nThis file should be skipped.")

        source_filter = {"keep.md"}
        results = process_parsed_files(
            str(input_dir), str(output_dir), source_filter=source_filter
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert "keep" in results[0]["source"]

    def test_process_parsed_files_with_source_filter_nested(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"

        nested_dir = input_dir / "subdir"
        nested_dir.mkdir(parents=True)

        md_file1 = nested_dir / "keep.md"
        md_file1.write_text("# Keep\n\nThis file should be kept.")

        md_file2 = input_dir / "skip.md"
        md_file2.write_text("# Skip\n\nThis file should be skipped.")

        source_filter = {str(Path("subdir") / "keep.md")}
        results = process_parsed_files(
            str(input_dir), str(output_dir), source_filter=source_filter
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"

    def test_process_parsed_files_with_source_filter_no_match(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        md_file = input_dir / "test.md"
        md_file.write_text("# Test\n\nContent.")

        source_filter = {"nonexistent.md"}
        results = process_parsed_files(
            str(input_dir), str(output_dir), source_filter=source_filter
        )

        assert len(results) == 0

    def test_process_parsed_files_without_source_filter(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        md_file1 = input_dir / "file1.md"
        md_file1.write_text("# File 1\n\nContent 1.")

        md_file2 = input_dir / "file2.md"
        md_file2.write_text("# File 2\n\nContent 2.")

        results = process_parsed_files(str(input_dir), str(output_dir))

        assert len(results) == 2
