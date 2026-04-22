import json
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.chunker import (
    BGETokenizerEncoder,
    _extract_headings,
    _get_bge_encoder,
    _get_encoding,
    chunk_text,
    chunk_text_page_aware,
    process_parsed_files,
    process_parsed_files_page_aware,
)


class TestExtractHeadings:
    def test_no_headings(self):
        text = "Just plain text.\nNo headings."
        assert _extract_headings(text) == []

    def test_single_heading(self):
        text = "# Main Title\n\nSome content."
        headings = _extract_headings(text)
        assert headings == ["# Main Title"]

    def test_multiple_headings(self):
        text = "# Title\n## Subtitle\n### Sub-subtitle\nContent"
        headings = _extract_headings(text)
        assert len(headings) == 3

    def test_heading_levels(self):
        text = "# H1\n## H2\n### H3\n#### H4"
        headings = _extract_headings(text)
        assert headings[0] == "# H1"
        assert headings[1] == "## H2"
        assert headings[2] == "### H3"
        assert headings[3] == "#### H4"


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

        with open(output_file, encoding="utf-8") as f:
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
        with open(output_file, encoding="utf-8") as f:
            first_line = f.readline()
            chunk_data = json.loads(first_line)
            assert chunk_data["chunk_id"].startswith("test_document::chunk::")
            assert "::chunk::000" in chunk_data["chunk_id"]

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

        with open(actual_output, encoding="utf-8") as f:
            first_line = f.readline()
            chunk_data = json.loads(first_line)
            assert "source" in chunk_data["metadata"]
            expected_source_parts = ["annual_reports", "2023", "五粮液", "2023年度报告_英文_.md"]
            expected_source = Path(*expected_source_parts).as_posix()
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

        source_filter_posix = {Path("subdir/keep.md").as_posix()}
        results = process_parsed_files(
            str(input_dir), str(output_dir), source_filter=source_filter_posix
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


class TestChunkTextPageAware:
    def test_empty_page_chunks(self):
        result = chunk_text_page_aware([], source_name="test")
        assert result == []

    def test_single_page_short_text(self):
        page_chunks = [
            {
                "text": "Short text on page one.",
                "metadata": {"page_number": 1, "page_count": 1, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            }
        ]
        result = chunk_text_page_aware(page_chunks, source_name="test", chunk_size=512)
        assert len(result) == 1
        assert result[0]["metadata"]["page_number"] == 1

    def test_single_page_long_text(self):
        page_chunks = [
            {
                "text": "This is a test sentence. " * 200,
                "metadata": {"page_number": 3, "page_count": 1, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            }
        ]
        result = chunk_text_page_aware(
            page_chunks, source_name="test", chunk_size=50
        )
        assert len(result) > 1
        for chunk in result:
            assert chunk["metadata"]["page_number"] == 3

    def test_multiple_pages(self):
        page_chunks = [
            {
                "text": "Content for page one. " * 20,
                "metadata": {"page_number": 1, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "Content for page two. " * 20,
                "metadata": {"page_number": 2, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "Content for page three. " * 20,
                "metadata": {"page_number": 3, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
        ]
        result = chunk_text_page_aware(page_chunks, source_name="test", chunk_size=50)
        page_numbers = {chunk["metadata"]["page_number"] for chunk in result}
        assert 1 in page_numbers
        assert 2 in page_numbers
        assert 3 in page_numbers

    def test_empty_page_skipped(self):
        page_chunks = [
            {
                "text": "",
                "metadata": {"page_number": 1, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "   ",
                "metadata": {"page_number": 2, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "Non-empty page content. " * 10,
                "metadata": {"page_number": 3, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
        ]
        result = chunk_text_page_aware(page_chunks, source_name="test", chunk_size=512)
        assert len(result) >= 1
        for chunk in result:
            assert chunk["metadata"]["page_number"] == 3

    def test_chunk_id_format(self):
        page_chunks = [
            {
                "text": "Some text for chunking. " * 10,
                "metadata": {"page_number": 5, "page_count": 1, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            }
        ]
        result = chunk_text_page_aware(page_chunks, source_name="test", chunk_size=512)
        assert len(result) >= 1
        chunk_index = result[0]["metadata"]["chunk_index"]
        assert chunk_index.startswith("p5_")
        assert result[0]["metadata"]["page_number"] == 5

    def test_overlap_validation(self):
        page_chunks = [
            {
                "text": "Some text.",
                "metadata": {"page_number": 1, "page_count": 1, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            }
        ]
        with pytest.raises(ValueError, match="Overlap"):
            chunk_text_page_aware(
                page_chunks, source_name="test", chunk_size=50, overlap=50
            )


class TestChunkTextPageAwareCrossPageOverlap:
    def _make_multi_page_chunks(self):
        return [
            {
                "text": "Alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu. " * 10,
                "metadata": {"page_number": 1, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "Nu xi omicron pi rho sigma tau upsilon phi chi psi omega end. " * 10,
                "metadata": {"page_number": 2, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "One two three four five six seven eight nine ten eleven twelve. " * 10,
                "metadata": {"page_number": 3, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
        ]

    def test_cross_page_overlap_zero_backward_compatible(self):
        pages = self._make_multi_page_chunks()
        result_no_cpo = chunk_text_page_aware(
            pages, source_name="test", chunk_size=50, cross_page_overlap=0
        )
        result_default = chunk_text_page_aware(
            pages, source_name="test", chunk_size=50
        )
        assert len(result_no_cpo) == len(result_default)
        for c1, c2 in zip(result_no_cpo, result_default, strict=False):
            assert c1["text"] == c2["text"]
            assert c1["metadata"]["page_number"] == c2["metadata"]["page_number"]

    def test_cross_page_overlap_zero_no_cross_page_metadata(self):
        pages = self._make_multi_page_chunks()
        result = chunk_text_page_aware(
            pages, source_name="test", chunk_size=50, cross_page_overlap=0
        )
        for chunk in result:
            assert "cross_page" not in chunk["metadata"]
            assert "overlap_from_page" not in chunk["metadata"]

    def test_cross_page_overlap_positive_first_page_no_overlap(self):
        pages = self._make_multi_page_chunks()
        result = chunk_text_page_aware(
            pages, source_name="test", chunk_size=50, cross_page_overlap=20
        )
        page1_chunks = [c for c in result if c["metadata"]["page_number"] == 1]
        for chunk in page1_chunks:
            assert "cross_page" not in chunk["metadata"]

    def test_cross_page_overlap_positive_second_page_has_overlap(self):
        pages = self._make_multi_page_chunks()
        result = chunk_text_page_aware(
            pages, source_name="test", chunk_size=50, cross_page_overlap=20
        )
        page2_chunks = [c for c in result if c["metadata"]["page_number"] == 2]
        cross_page_chunks = [c for c in page2_chunks if c["metadata"].get("cross_page")]
        assert len(cross_page_chunks) >= 1
        for chunk in cross_page_chunks:
            assert chunk["metadata"]["cross_page"] is True
            assert chunk["metadata"]["overlap_from_page"] == 1

    def test_cross_page_overlap_positive_third_page_overlap_from_page_two(self):
        pages = self._make_multi_page_chunks()
        result = chunk_text_page_aware(
            pages, source_name="test", chunk_size=50, cross_page_overlap=20
        )
        page3_chunks = [c for c in result if c["metadata"]["page_number"] == 3]
        cross_page_chunks = [c for c in page3_chunks if c["metadata"].get("cross_page")]
        assert len(cross_page_chunks) >= 1
        for chunk in cross_page_chunks:
            assert chunk["metadata"]["overlap_from_page"] == 2

    def test_cross_page_overlap_tail_tokens_appear_in_next_page(self):
        page1_text = "UniqueAlphaWord " * 30
        page2_text = "UniqueBetaWord " * 30
        pages = [
            {
                "text": page1_text,
                "metadata": {"page_number": 1, "page_count": 2, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": page2_text,
                "metadata": {"page_number": 2, "page_count": 2, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
        ]
        result = chunk_text_page_aware(
            pages, source_name="test", chunk_size=100, cross_page_overlap=20
        )
        page2_chunks = [c for c in result if c["metadata"]["page_number"] == 2]
        cross_page_chunks = [c for c in page2_chunks if c["metadata"].get("cross_page")]
        assert len(cross_page_chunks) >= 1
        assert "UniqueAlphaWord" in cross_page_chunks[0]["text"]

    def test_cross_page_overlap_negative_raises(self):
        pages = self._make_multi_page_chunks()
        with pytest.raises(ValueError, match="non-negative"):
            chunk_text_page_aware(
                pages, source_name="test", chunk_size=50, cross_page_overlap=-1
            )

    def test_cross_page_overlap_ge_chunk_size_raises(self):
        pages = self._make_multi_page_chunks()
        with pytest.raises(ValueError, match="less than"):
            chunk_text_page_aware(
                pages, source_name="test", chunk_size=50, cross_page_overlap=50
            )

    def test_cross_page_overlap_with_empty_page_skipped(self):
        pages = [
            {
                "text": "Alpha beta gamma delta. " * 30,
                "metadata": {"page_number": 1, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "",
                "metadata": {"page_number": 2, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "One two three four five. " * 30,
                "metadata": {"page_number": 3, "page_count": 3, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
        ]
        result = chunk_text_page_aware(
            pages, source_name="test", chunk_size=100, cross_page_overlap=20
        )
        page3_chunks = [c for c in result if c["metadata"]["page_number"] == 3]
        cross_page_chunks = [c for c in page3_chunks if c["metadata"].get("cross_page")]
        assert len(cross_page_chunks) >= 1
        assert cross_page_chunks[0]["metadata"]["overlap_from_page"] == 1

    def test_cross_page_overlap_with_intra_page_overlap(self):
        pages = self._make_multi_page_chunks()
        result = chunk_text_page_aware(
            pages,
            source_name="test",
            chunk_size=50,
            overlap=10,
            cross_page_overlap=20,
        )
        assert len(result) > 0
        page2_chunks = [c for c in result if c["metadata"]["page_number"] == 2]
        cross_page_chunks = [c for c in page2_chunks if c["metadata"].get("cross_page")]
        assert len(cross_page_chunks) >= 1


class TestProcessParsedFilesPageAware:
    def _make_pages_data(self):
        return [
            {
                "text": "Page 1 content with enough text to chunk. " * 20,
                "metadata": {"page_number": 1, "page_count": 2, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "Page 2 content with enough text to chunk. " * 20,
                "metadata": {"page_number": 2, "page_count": 2, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
        ]

    def test_input_dir_not_found(self):
        with pytest.raises(FileNotFoundError) as exc_info:
            process_parsed_files_page_aware("nonexistent_dir", "output_dir")
        assert "Input directory not found" in str(exc_info.value)

    def test_no_pages_json_files(self, tmp_path):
        results = process_parsed_files_page_aware(str(tmp_path), str(tmp_path / "output"))
        assert results == []

    def test_process_pages_json(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pages_file = input_dir / "test.pages.json"
        pages_file.write_text(json.dumps(self._make_pages_data()), encoding="utf-8")

        results = process_parsed_files_page_aware(
            str(input_dir), str(output_dir), chunk_size=50
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert results[0]["chunk_count"] > 0

        output_file = Path(results[0]["output"])
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            lines = f.readlines()
            for line in lines:
                chunk_data = json.loads(line)
                assert "page_number" in chunk_data["metadata"]
                assert chunk_data["metadata"]["strategy"] == "page_aware_fixed"

    def test_source_filter(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pages_file1 = input_dir / "keep.pages.json"
        pages_file1.write_text(json.dumps(self._make_pages_data()), encoding="utf-8")

        pages_file2 = input_dir / "skip.pages.json"
        pages_file2.write_text(json.dumps(self._make_pages_data()), encoding="utf-8")

        source_filter = {"keep.pages.json"}
        results = process_parsed_files_page_aware(
            str(input_dir), str(output_dir), source_filter=source_filter
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"
        assert "keep" in results[0]["source"]

    def test_output_chunk_id_format(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pages_file = input_dir / "mydoc.pages.json"
        pages_file.write_text(json.dumps(self._make_pages_data()), encoding="utf-8")

        results = process_parsed_files_page_aware(
            str(input_dir), str(output_dir), chunk_size=50
        )

        output_file = Path(results[0]["output"])
        with open(output_file, encoding="utf-8") as f:
            first_line = f.readline()
            chunk_data = json.loads(first_line)
            chunk_id = chunk_data["chunk_id"]
            page_number = chunk_data["metadata"]["page_number"]
            assert chunk_id.startswith("mydoc_")
            assert f"_p{page_number}_" in chunk_id

    def test_process_pages_json_with_cross_page_overlap(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pages_data = [
            {
                "text": "Alpha beta gamma delta epsilon. " * 30,
                "metadata": {"page_number": 1, "page_count": 2, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
            {
                "text": "Nu xi omicron pi rho sigma. " * 30,
                "metadata": {"page_number": 2, "page_count": 2, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            },
        ]
        pages_file = input_dir / "test.pages.json"
        pages_file.write_text(json.dumps(pages_data), encoding="utf-8")

        results = process_parsed_files_page_aware(
            str(input_dir), str(output_dir), chunk_size=100, cross_page_overlap=20
        )

        assert len(results) == 1
        assert results[0]["status"] == "success"

        output_file = Path(results[0]["output"])
        assert output_file.exists()

        with open(output_file, encoding="utf-8") as f:
            lines = f.readlines()
            cross_page_found = False
            for line in lines:
                chunk_data = json.loads(line)
                if chunk_data["metadata"].get("cross_page"):
                    cross_page_found = True
                    assert "overlap_from_page" in chunk_data["metadata"]
                    assert chunk_data["metadata"]["overlap_from_page"] == 1
                    assert chunk_data["metadata"]["page_number"] == 2
            assert cross_page_found

    def test_process_pages_json_cross_page_overlap_zero_no_metadata(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        pages_file = input_dir / "test.pages.json"
        pages_file.write_text(json.dumps(self._make_pages_data()), encoding="utf-8")

        results = process_parsed_files_page_aware(
            str(input_dir), str(output_dir), chunk_size=50, cross_page_overlap=0
        )

        output_file = Path(results[0]["output"])
        with open(output_file, encoding="utf-8") as f:
            for line in f:
                chunk_data = json.loads(line)
                assert "cross_page" not in chunk_data["metadata"]
                assert "overlap_from_page" not in chunk_data["metadata"]


class TestBGETokenizerEncoder:
    @pytest.mark.unit
    def test_encode_returns_token_ids(self):
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [101, 202, 303]

        encoder = BGETokenizerEncoder("test-model")
        encoder._tokenizer = mock_tokenizer

        result = encoder.encode("测试文本")
        mock_tokenizer.encode.assert_called_once_with("测试文本", add_special_tokens=False)
        assert result == [101, 202, 303]

    @pytest.mark.unit
    def test_decode_returns_text(self):
        mock_tokenizer = MagicMock()
        mock_tokenizer.decode.return_value = "测试文本"

        encoder = BGETokenizerEncoder("test-model")
        encoder._tokenizer = mock_tokenizer

        result = encoder.decode([101, 202, 303])
        mock_tokenizer.decode.assert_called_once_with([101, 202, 303], skip_special_tokens=True)
        assert result == "测试文本"

    @pytest.mark.unit
    def test_lazy_loading_on_first_encode(self):
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [1, 2, 3]

        with patch("src.embedder.Embedder.get_tokenizer", return_value=mock_tokenizer):
            encoder = BGETokenizerEncoder("test-model")
            assert encoder._tokenizer is None

            encoder.encode("hello")

            assert encoder._tokenizer is mock_tokenizer

    @pytest.mark.unit
    def test_lazy_loading_on_first_decode(self):
        mock_tokenizer = MagicMock()
        mock_tokenizer.decode.return_value = "hello"

        with patch("src.embedder.Embedder.get_tokenizer", return_value=mock_tokenizer):
            encoder = BGETokenizerEncoder("test-model")
            encoder.decode([1, 2, 3])

    @pytest.mark.unit
    def test_tokenizer_cached_after_first_load(self):
        mock_tokenizer = MagicMock()
        mock_tokenizer.encode.return_value = [1]

        with patch("src.embedder.Embedder.get_tokenizer", return_value=mock_tokenizer) as mock_get:
            encoder = BGETokenizerEncoder("test-model")
            encoder.encode("a")
            encoder.encode("b")

            mock_get.assert_called_once_with("test-model")

    @pytest.mark.unit
    def test_load_failure_raises_exception(self):
        with patch("src.embedder.Embedder.get_tokenizer", side_effect=Exception("load failed")):
            encoder = BGETokenizerEncoder("bad-model")
            with pytest.raises(Exception, match="Failed to load BGE tokenizer"):
                encoder.encode("test")


class TestGetEncoding:
    @pytest.mark.unit
    def test_bge_encoding_returns_bge_encoder(self):
        with patch("src.chunker._get_bge_encoder") as mock_get_bge:
            mock_encoder = MagicMock()
            mock_get_bge.return_value = mock_encoder

            result = _get_encoding("bge", model_name="BAAI/bge-large-zh-v1.5")
            mock_get_bge.assert_called_once_with("BAAI/bge-large-zh-v1.5")
            assert result is mock_encoder

    @pytest.mark.unit
    def test_bge_encoding_without_model_name_raises(self):
        with pytest.raises(ValueError, match="model_name is required"):
            _get_encoding("bge", model_name=None)

    @pytest.mark.unit
    def test_tiktoken_encoding_returns_tiktoken_encoder(self):
        result = _get_encoding("cl100k_base")
        assert hasattr(result, "encode")
        assert hasattr(result, "decode")

    @pytest.mark.unit
    def test_invalid_tiktoken_encoding_raises(self):
        with pytest.raises(Exception, match="Failed to load tiktoken encoding"):
            _get_encoding("nonexistent_encoding")


class TestGetBGEEncoder:
    @pytest.mark.unit
    def test_caches_encoder_by_model_name(self):
        with patch.object(BGETokenizerEncoder, "_ensure_tokenizer"):
            encoder1 = _get_bge_encoder("model-a")
            encoder2 = _get_bge_encoder("model-a")
            assert encoder1 is encoder2

    @pytest.mark.unit
    def test_different_models_get_different_encoders(self):
        with patch.object(BGETokenizerEncoder, "_ensure_tokenizer"):
            encoder_a = _get_bge_encoder("model-a")
            encoder_b = _get_bge_encoder("model-b")
            assert encoder_a is not encoder_b


class TestChunkTextBGE:
    @pytest.mark.unit
    def test_chunk_text_with_bge_encoding(self):
        mock_encoding = MagicMock()
        mock_encoding.encode.return_value = list(range(100))
        mock_encoding.decode.side_effect = lambda tokens: f"chunk_{tokens[0]}_{tokens[-1]}"

        with patch("src.chunker._get_encoding", return_value=mock_encoding):
            result = chunk_text(
                "Some text", chunk_size=50, overlap=0,
                encoding_name="bge", model_name="BAAI/bge-large-zh-v1.5",
            )

            assert len(result) == 2
            assert result[0]["metadata"]["token_count"] == 50
            assert result[1]["metadata"]["token_count"] == 50

    @pytest.mark.unit
    def test_chunk_text_bge_passes_model_name(self):
        mock_encoding = MagicMock()
        mock_encoding.encode.return_value = [1, 2, 3]
        mock_encoding.decode.return_value = "text"

        with patch("src.chunker._get_encoding") as mock_get:
            mock_get.return_value = mock_encoding
            chunk_text(
                "text", encoding_name="bge", model_name="BAAI/bge-large-zh-v1.5",
            )
            mock_get.assert_called_once_with("bge", "BAAI/bge-large-zh-v1.5")

    @pytest.mark.unit
    def test_chunk_text_bge_without_model_name_raises(self):
        with pytest.raises(ValueError, match="model_name is required"):
            chunk_text("text", encoding_name="bge", model_name=None)

    @pytest.mark.unit
    def test_chunk_text_cl100k_base_backward_compatible(self):
        text = "This is a test sentence. " * 20
        result = chunk_text(text, chunk_size=50, overlap=0, encoding_name="cl100k_base")

        assert len(result) > 1
        for chunk in result:
            assert chunk["metadata"]["token_count"] <= 50

    @pytest.mark.unit
    def test_chunk_text_default_encoding_still_works(self):
        text = "This is a test sentence."
        result = chunk_text(text, chunk_size=100, overlap=0)

        assert len(result) == 1
        assert result[0]["text"] == text


class TestChunkTextPageAwareBGE:
    @pytest.mark.unit
    def test_page_aware_passes_model_name_to_chunk_text(self):
        page_chunks = [
            {
                "text": "Some text. " * 50,
                "metadata": {"page_number": 1, "page_count": 1, "file_path": "test.pdf"},
                "toc_items": [],
                "tables": [],
            }
        ]

        with patch("src.chunker.chunk_text") as mock_chunk:
            mock_chunk.return_value = [
                {
                    "text": "chunk",
                    "metadata": {
                        "chunk_index": 0,
                        "char_count": 5,
                        "token_count": 2,
                        "start_token": 0,
                        "end_token": 2,
                    },
                }
            ]

            chunk_text_page_aware(
                page_chunks, source_name="test",
                encoding_name="bge", model_name="BAAI/bge-large-zh-v1.5",
            )

            mock_chunk.assert_called_once()
            call_kwargs = mock_chunk.call_args
            assert call_kwargs[1].get("model_name") == "BAAI/bge-large-zh-v1.5" or \
                   call_kwargs[0][4] == "BAAI/bge-large-zh-v1.5" if len(call_kwargs[0]) > 4 else \
                   call_kwargs.kwargs.get("model_name") == "BAAI/bge-large-zh-v1.5"


class TestProcessParsedFilesBGE:
    @pytest.mark.unit
    def test_process_parsed_files_passes_encoding_and_model(self, tmp_path):
        input_dir = tmp_path / "input"
        output_dir = tmp_path / "output"
        input_dir.mkdir()

        md_file = input_dir / "test.md"
        md_file.write_text("# Test\n\n" + "Content " * 50)

        with patch("src.chunker.chunk_text") as mock_chunk:
            mock_chunk.return_value = [
                {
                    "text": "chunk text",
                    "metadata": {
                        "chunk_index": 0,
                        "char_count": 10,
                        "token_count": 5,
                        "start_token": 0,
                        "end_token": 5,
                    },
                }
            ]

            process_parsed_files(
                str(input_dir), str(output_dir),
                encoding_name="bge", model_name="BAAI/bge-large-zh-v1.5",
            )

            mock_chunk.assert_called()
            call_kwargs = mock_chunk.call_args
            assert call_kwargs.kwargs.get("encoding_name") == "bge" or \
                   (len(call_kwargs.args) > 3 and call_kwargs.args[3] == "bge")
            assert call_kwargs.kwargs.get("model_name") == "BAAI/bge-large-zh-v1.5" or \
                   (len(call_kwargs.args) > 4 and call_kwargs.args[4] == "BAAI/bge-large-zh-v1.5")
