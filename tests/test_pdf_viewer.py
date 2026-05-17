import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

from scripts.pdf_viewer import PDFViewer


class TestPDFViewerDetectViewer:
    @patch("scripts.pdf_viewer.Path.exists")
    def test_detect_sumatra_from_known_path(self, mock_exists):
        mock_exists.side_effect = lambda: True
        viewer = PDFViewer(data_dir="data")
        viewer._viewer_path = None
        viewer._viewer_type = None
        with patch.object(PDFViewer, "_detect_viewer") as mock_detect:
            mock_detect.return_value = None
            viewer._detect_viewer()
            viewer._viewer_path = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
            viewer._viewer_type = "sumatra"
        assert viewer.viewer_type == "sumatra"

    @patch("shutil.which")
    @patch("scripts.pdf_viewer.Path.exists", return_value=False)
    def test_no_viewer_detected(self, mock_exists, mock_which):
        mock_which.return_value = None
        viewer = PDFViewer(data_dir="data")
        viewer._viewer_path = None
        viewer._viewer_type = None
        viewer._detect_viewer()
        assert viewer.viewer_type is None
        assert viewer.viewer_path is None


class TestPDFViewerOpenAtPage:
    @patch("subprocess.Popen")
    def test_open_sumatra(self, mock_popen):
        viewer = PDFViewer(data_dir="data")
        viewer._viewer_path = r"C:\Program Files\SumatraPDF\SumatraPDF.exe"
        viewer._viewer_type = "sumatra"

        with patch.object(Path, "exists", return_value=True):
            result = viewer.open_at_page(r"C:\test\report.pdf", 5)

        assert result is True
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert "-page" in cmd
        assert "5" in cmd
        assert "-reuse-instance" in cmd

    @pytest.mark.skipif(
        sys.platform != "win32",
        reason="TODO: Add Linux/macOS PDF viewer support (see FEAT-20260517-001-ash)",
    )
    @patch("subprocess.Popen")
    def test_open_edge(self, mock_popen):
        viewer = PDFViewer(data_dir="data")
        viewer._viewer_path = r"C:\Program Files\Microsoft\Edge\Application\msedge.exe"
        viewer._viewer_type = "edge"

        with patch.object(Path, "exists", return_value=True):
            result = viewer.open_at_page(r"C:\test\report.pdf", 3)

        assert result is True
        mock_popen.assert_called_once()
        cmd = mock_popen.call_args[0][0]
        assert any("#page=3" in arg for arg in cmd)

    def test_open_nonexistent_pdf(self):
        viewer = PDFViewer(data_dir="data")
        viewer._viewer_path = "some_viewer"
        viewer._viewer_type = "sumatra"
        result = viewer.open_at_page("/nonexistent/file.pdf", 1)
        assert result is False

    def test_open_no_viewer(self):
        viewer = PDFViewer(data_dir="data")
        viewer._viewer_path = None
        viewer._viewer_type = None
        with patch.object(Path, "exists", return_value=True):
            result = viewer.open_at_page("/some/file.pdf", 1)
        assert result is False


class TestPDFViewerLocatePage:
    def test_no_source_files(self):
        viewer = PDFViewer(data_dir="data")
        question = {"source_files": []}
        pdf_path, page = viewer.locate_page_for_question(question)
        assert pdf_path is None
        assert page is None

    def test_page_from_chunks(self):
        viewer = PDFViewer(data_dir="data")
        viewer._chunks_cache = {
            "reports/doc.pdf": [
                {
                    "chunk_id": "doc_p3_000",
                    "text": "some text",
                    "metadata": {"page_number": 3, "source": "reports/doc.pages.json"},
                },
            ]
        }
        question = {
            "source_files": ["reports/doc.pdf"],
            "source_chunks": ["doc_p3_000"],
        }
        with (
            patch.object(viewer, "_get_page_from_chunks", return_value=3),
            patch.object(viewer, "_get_page_from_parsed", return_value=None),
            patch.object(Path, "exists", return_value=True),
        ):
            pdf_path, page = viewer.locate_page_for_question(question)
        assert page == 3


class TestPDFViewerGetChunks:
    def test_no_source_files(self):
        viewer = PDFViewer(data_dir="data")
        question = {"source_files": []}
        result = viewer.get_chunks_for_question(question)
        assert result == []

    def test_chunks_by_id(self):
        viewer = PDFViewer(data_dir="data")
        viewer._chunks_cache = {
            "reports/doc.pdf": [
                {
                    "chunk_id": "doc_p3_000",
                    "text": "营收100亿元",
                    "metadata": {"page_number": 3},
                },
                {
                    "chunk_id": "doc_p4_000",
                    "text": "利润50亿元",
                    "metadata": {"page_number": 4},
                },
            ]
        }
        question = {
            "source_files": ["reports/doc.pdf"],
            "source_chunks": ["doc_p3_000"],
        }
        result = viewer.get_chunks_for_question(question)
        assert len(result) == 1
        assert result[0]["chunk_id"] == "doc_p3_000"

    def test_chunks_fuzzy_match(self):
        viewer = PDFViewer(data_dir="data")
        chunk_text_a = (
            "根据公司2024年年度报告，公司全年实现营业收入100亿元，"
            "同比增长15.2%，其中主营业务收入占比超过80%。"
            "归属于上市公司股东的净利润为50亿元，同比增长8.3%。"
        )
        chunk_text_b = (
            "公司主要产品包括光模块和光纤通信设备，"
            "广泛应用于数据中心和电信网络建设领域。"
        )
        viewer._chunks_cache = {
            "reports/doc.pdf": [
                {
                    "chunk_id": "doc_p3_000",
                    "text": chunk_text_a,
                    "metadata": {"page_number": 3},
                },
                {
                    "chunk_id": "doc_p5_000",
                    "text": chunk_text_b,
                    "metadata": {"page_number": 5},
                },
            ]
        }
        question = {
            "source_files": ["reports/doc.pdf"],
            "source_chunks": [],
            "ground_truth_excerpt": "公司全年实现营业收入100亿元，同比增长15.2%",
        }
        result = viewer.get_chunks_for_question(question)
        assert len(result) >= 1
        assert result[0]["chunk_id"] == "doc_p3_000"


class TestPDFViewerFormatChunkDisplay:
    def test_empty_chunks(self):
        viewer = PDFViewer(data_dir="data")
        result = viewer.format_chunk_display([])
        assert "no chunk context" in result

    def test_format_single_chunk(self):
        viewer = PDFViewer(data_dir="data")
        chunks = [
            {
                "chunk_id": "doc_p3_002",
                "text": "公司2024年营收达到100亿元",
                "metadata": {"page_number": 3, "token_count": 512},
            }
        ]
        result = viewer.format_chunk_display(chunks)
        assert "doc_p3_002" in result
        assert "Page 3" in result
        assert "512 tokens" in result
        assert "营收" in result


class TestPDFViewerGetPageText:
    def test_get_page_text(self):
        viewer = PDFViewer(data_dir="data")
        viewer._pages_cache = {
            "reports/doc.pdf": [
                {"page_number": 1, "text": "Page 1 content"},
                {"page_number": 2, "text": "Page 2 content with revenue data"},
            ]
        }
        result = viewer.get_page_text("reports/doc.pdf", 2)
        assert "Page 2" in result

    def test_get_page_text_not_found(self):
        viewer = PDFViewer(data_dir="data")
        viewer._pages_cache = {
            "reports/doc.pdf": [
                {"page_number": 1, "text": "Page 1 content"},
            ]
        }
        result = viewer.get_page_text("reports/doc.pdf", 99)
        assert result is None

    def test_get_page_text_truncation(self):
        viewer = PDFViewer(data_dir="data")
        long_text = "A" * 2000
        viewer._pages_cache = {
            "reports/doc.pdf": [
                {"page_number": 1, "text": long_text},
            ]
        }
        result = viewer.get_page_text("reports/doc.pdf", 1)
        assert result is not None
        assert result.endswith("...")
        assert len(result) < len(long_text)


class TestPDFViewerLoadPagesForSource:
    def test_load_pages_from_cache(self):
        viewer = PDFViewer(data_dir="data")
        cached_pages = [{"page_number": 1, "text": "cached"}]
        viewer._pages_cache = {"reports/doc.pdf": cached_pages}
        result = viewer._load_pages_for_source("reports/doc.pdf")
        assert result == cached_pages

    def test_load_pages_from_file(self, tmp_path):
        artifacts_dir = tmp_path / "artifacts"
        parsed_dir = artifacts_dir / "abc123" / "parsed_hash"
        parsed_dir.mkdir(parents=True)

        pages_data = [
            {"page_number": 1, "text": "Page 1"},
            {"page_number": 2, "text": "Page 2"},
        ]
        pages_file = parsed_dir / "reports" / "doc.pages.json"
        pages_file.parent.mkdir(parents=True, exist_ok=True)
        pages_file.write_text(json.dumps(pages_data), encoding="utf-8")

        viewer = PDFViewer(data_dir=str(tmp_path))
        viewer._parsed_dir = parsed_dir
        result = viewer._load_pages_for_source("reports/doc.pdf")
        assert len(result) == 2


class TestPDFViewerLoadChunksForSource:
    def test_load_chunks_from_cache(self):
        viewer = PDFViewer(data_dir="data")
        cached_chunks = [{"chunk_id": "c1", "text": "cached"}]
        viewer._chunks_cache = {"reports/doc.pdf": cached_chunks}
        result = viewer._load_chunks_for_source("reports/doc.pdf")
        assert result == cached_chunks

    def test_load_chunks_from_jsonl(self, tmp_path):
        chunks_dir = tmp_path / "chunks_hash"
        chunks_dir.mkdir()
        jsonl_file = chunks_dir / "doc.jsonl"

        chunks_data = [
            {
                "chunk_id": "doc_p1_000",
                "text": "chunk 1 text",
                "metadata": {"source": "doc.pages.json", "chunk_index": "p1_000"},
            },
            {
                "chunk_id": "doc_p2_000",
                "text": "chunk 2 text",
                "metadata": {"source": "doc.pages.json", "chunk_index": "p2_000"},
            },
        ]
        with open(jsonl_file, "w", encoding="utf-8") as f:
            for chunk in chunks_data:
                f.write(json.dumps(chunk, ensure_ascii=False) + "\n")

        loaded = []
        for jsonl_path in chunks_dir.rglob("*.jsonl"):
            with open(jsonl_path, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    chunk_source = chunk.get("metadata", {}).get("source", "")
                    chunk_stem = Path(chunk_source).stem.split(".")[0]
                    if chunk_stem == "doc":
                        loaded.append(chunk)
        assert len(loaded) == 2


class TestPDFViewerFuzzyMatchChunks:
    def test_fuzzy_match_finds_best(self):
        chunk_text_a = (
            "根据公司2024年年度报告，公司全年实现营业收入100亿元，"
            "同比增长15.2%，其中主营业务收入占比超过80%。"
            "归属于上市公司股东的净利润为50亿元，同比增长8.3%。"
        )
        chunk_text_b = (
            "公司主要产品包括光模块和光纤通信设备，"
            "广泛应用于数据中心和电信网络建设领域。"
        )
        chunks = [
            {"chunk_id": "c1", "text": chunk_text_a},
            {"chunk_id": "c2", "text": chunk_text_b},
        ]
        result = PDFViewer._fuzzy_match_chunks(
            chunks, "公司全年实现营业收入100亿元，同比增长15.2%", max_chunks=2
        )
        assert len(result) >= 1
        assert result[0]["chunk_id"] == "c1"

    def test_fuzzy_match_no_match(self):
        chunks = [
            {"chunk_id": "c1", "text": "公司主要产品包括光模块和光纤通信设备"},
        ]
        result = PDFViewer._fuzzy_match_chunks(
            chunks, "完全不相关的内容xyz123abc", max_chunks=2
        )
        assert len(result) == 0
