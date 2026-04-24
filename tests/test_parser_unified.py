from pathlib import Path

import pytest

from src.meal import ArtifactCache
from src.parser import parse_all_pdfs_unified


@pytest.fixture
def sample_pdf_dir(tmp_path):
    raw_dir = tmp_path / "raw"
    raw_dir.mkdir()

    company_dir = raw_dir / "annual_reports" / "2023" / "TestCompany"
    company_dir.mkdir(parents=True)

    pdf_path = company_dir / "2023_report.pdf"
    pdf_path.write_bytes(b"%PDF-1.4 fake pdf content for testing")

    return raw_dir


@pytest.fixture
def artifacts_dir(tmp_path):
    d = tmp_path / "artifacts"
    d.mkdir()
    return d


def test_unified_parser_creates_artifacts(sample_pdf_dir, artifacts_dir):
    results = parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
    )

    assert len(results) == 1
    assert results[0]["status"] in ("success", "failed")

    if results[0]["status"] == "success":
        output_path = Path(results[0]["output"])
        assert output_path.exists()
        assert output_path.suffix == ".md"


def test_unified_parser_caches_results(sample_pdf_dir, artifacts_dir):
    parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
    )

    second_run = parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
    )

    assert all(r["status"] == "skipped" for r in second_run)


def test_unified_parser_detects_config_change(sample_pdf_dir, artifacts_dir):
    parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
    )

    second_run = parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": True},
    )

    assert any(r["status"] == "success" for r in second_run)


def test_unified_parser_detects_source_change(sample_pdf_dir, artifacts_dir):
    parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
    )

    pdf_file = list(sample_pdf_dir.rglob("*.pdf"))[0]
    pdf_file.write_bytes(b"%PDF-1.4 modified content to invalidate cache")

    second_run = parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
    )

    assert any(r["status"] == "success" for r in second_run)


def test_unified_parser_manifest_structure(sample_pdf_dir, artifacts_dir):
    parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
    )

    cache = ArtifactCache(artifacts_dir, sample_pdf_dir)
    manifest = cache.load_full_manifest()

    assert manifest is not None
    assert "pdf_inventory" in manifest
    assert "config_hashes" in manifest
    assert "parser" in manifest["config_hashes"]

    for rel_path, sha256 in manifest["pdf_inventory"].items():
        assert isinstance(rel_path, str)
        assert isinstance(sha256, str)
        assert len(sha256) == 64


def test_unified_parser_force_flag(sample_pdf_dir, artifacts_dir):
    parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
    )

    second_run = parse_all_pdfs_unified(
        input_dir=str(sample_pdf_dir),
        artifacts_dir=str(artifacts_dir),
        algorithm="pymupdf4llm",
        parser_options={"page_chunks": False},
        force=True,
    )

    assert any(r["status"] == "success" for r in second_run)


def test_unified_parser_no_pdfs(tmp_path):
    raw_dir = tmp_path / "empty"
    raw_dir.mkdir()
    artifacts_dir = tmp_path / "artifacts"
    artifacts_dir.mkdir()

    from src.exceptions import ParsingError

    with pytest.raises(ParsingError, match="No PDF files"):
        parse_all_pdfs_unified(
            input_dir=str(raw_dir),
            artifacts_dir=str(artifacts_dir),
        )


def test_unified_parser_invalid_input_dir():
    from src.exceptions import ParsingError

    with pytest.raises(ParsingError, match="Input directory not found"):
        parse_all_pdfs_unified(
            input_dir="/nonexistent/path",
            artifacts_dir="/tmp/artifacts",
        )
