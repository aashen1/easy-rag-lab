from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.exceptions import ParsingError
from src.meal import (
    ArtifactCache,
    MealFile,
    compute_data_id,
    compute_parser_config_hash,
)
from src.parsers.registry import ParserRegistry
from src.utils import detect_document_category


def _collect_pdf_files(raw_dir: Path) -> list[MealFile]:
    """Collect all PDF files in raw_dir with their metadata.

    Args:
        raw_dir: Root directory containing PDF files.

    Returns:
        List of MealFile objects with path, sha256, and size_bytes.
    """
    all_pdfs = sorted(raw_dir.rglob("*.pdf"))
    if not all_pdfs:
        raise ParsingError(f"No PDF files found in {raw_dir}")

    pdf_files = []
    for pdf_path in all_pdfs:
        try:
            rel_path = pdf_path.relative_to(raw_dir).as_posix()
            sha256_hash = _compute_file_sha256(pdf_path)
            size_bytes = pdf_path.stat().st_size
            pdf_files.append(
                MealFile(
                    path=rel_path,
                    sha256=sha256_hash,
                    size_bytes=size_bytes,
                )
            )
        except Exception as e:
            logger.warning(f"Skipping {pdf_path}: {str(e)}")

    if not pdf_files:
        raise ParsingError("No PDF files could be processed")

    return pdf_files


def _compute_file_sha256(file_path: Path, chunk_size: int = 8192) -> str:
    """Compute SHA-256 hash of a file.

    Args:
        file_path: Path to the file to hash.
        chunk_size: Number of bytes to read per iteration.

    Returns:
        Hexadecimal SHA-256 digest string.
    """
    import hashlib

    sha256 = hashlib.sha256()
    with open(file_path, "rb") as f:
        while True:
            chunk = f.read(chunk_size)
            if not chunk:
                break
            sha256.update(chunk)
    return sha256.hexdigest()


def parse_all_pdfs_unified(
    input_dir: str,
    artifacts_dir: str,
    algorithm: str = "pymupdf4llm",
    parser_options: dict | None = None,
    force: bool = False,
) -> list[dict[str, str]]:
    """Parse all PDF files using the unified ArtifactCache system.

    Computes full data_id from all PDFs, uses parser_hash to distinguish
    configurations, and validates cache against source file SHA-256 hashes.

    Args:
        input_dir: Directory containing PDF files to parse.
        artifacts_dir: Root directory for storing cached artifacts.
        algorithm: Parser algorithm name (e.g., "pymupdf4llm").
        parser_options: Options passed to the parser constructor.
        force: If True, re-parse files even if valid cache exists.

    Returns:
        List of result dictionaries with source, output, category, and status.

    Raises:
        FileNotFoundError: If input_dir does not exist.
    """
    raw_dir = Path(input_dir)
    if not raw_dir.exists():
        raise ParsingError(f"Input directory not found: {input_dir}")

    artifacts_path = Path(artifacts_dir)
    cache = ArtifactCache(artifacts_path, raw_dir)

    pdf_files = _collect_pdf_files(raw_dir)
    data_id = compute_data_id(pdf_files)

    parser_config_for_hash = {"algorithm": algorithm, "options": parser_options or {}}
    parser_hash = compute_parser_config_hash(parser_config_for_hash)

    parsed_dir = cache.get_parsed_dir(data_id, parser_hash)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    use_page_chunks = bool(parser_options and parser_options.get("page_chunks", False))

    if not force:
        manifest = cache.load_manifest(data_id)
        cache_valid = (
            manifest is not None
            and "pdf_inventory" in manifest
            and cache.is_full_parsed_valid(parser_hash, use_page_chunks=use_page_chunks)
        )
    else:
        cache_valid = False

    if cache_valid and not force:
        logger.info(
            f"Cache HIT: Valid parsed artifacts exist for data_id={data_id[:12]}"
        )
        results = []
        for meal_file in pdf_files:
            if use_page_chunks:
                output_file = parsed_dir / Path(meal_file.path).with_suffix(
                    ".pages.json"
                )
            else:
                output_file = parsed_dir / Path(meal_file.path).with_suffix(".md")

            results.append(
                {
                    "source": meal_file.path,
                    "output": str(output_file),
                    "category": detect_document_category(meal_file.path),
                    "status": "skipped",
                }
            )

        logger.info(f"Skipped {len(results)} files (valid cache found)")
        return results

    parser = ParserRegistry.get(algorithm, parser_options or {})
    results = []

    for meal_file in pdf_files:
        pdf_path = raw_dir / meal_file.path
        if use_page_chunks:
            output_file = parsed_dir / Path(meal_file.path).with_suffix(".pages.json")
        else:
            output_file = parsed_dir / Path(meal_file.path).with_suffix(".md")

        if (
            not force
            and output_file.exists()
            and manifest
            and "pdf_inventory" in manifest
        ):
            current_sha = _compute_file_sha256(pdf_path)
            if current_sha == manifest["pdf_inventory"].get(meal_file.path):
                logger.info(f"Skipping (already parsed): {meal_file.path}")
                results.append(
                    {
                        "source": meal_file.path,
                        "output": str(output_file),
                        "category": detect_document_category(meal_file.path),
                        "status": "skipped",
                    }
                )
                continue

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            result = parser.parse(str(pdf_path))

            if use_page_chunks:
                pages_data = [
                    {
                        "page_number": page.page_number,
                        "text": page.text,
                        "metadata": page.metadata,
                    }
                    for page in result.pages
                ]
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(pages_data, f, ensure_ascii=False, indent=2)
            else:
                with open(output_file, "w", encoding="utf-8") as f:
                    for page in result.pages:
                        f.write(page.text)
                        f.write("\n\n")

            category = detect_document_category(meal_file.path)
            results.append(
                {
                    "source": meal_file.path,
                    "output": str(output_file),
                    "category": category,
                    "status": "success",
                    "format": "pages_json" if use_page_chunks else "markdown",
                }
            )
            logger.success(f"Parsed: {meal_file.path} -> {output_file.name}")

        except Exception as e:
            logger.error(f"Failed to parse {meal_file.path}: {str(e)}")
            results.append(
                {
                    "source": meal_file.path,
                    "output": None,
                    "category": None,
                    "status": "failed",
                    "error": str(e),
                }
            )

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    skipped_count = sum(1 for r in results if r["status"] == "skipped")

    success_files = [
        f
        for f in pdf_files
        if any(r["source"] == f.path and r["status"] == "success" for r in results)
    ]
    failed_files = [
        f
        for f in pdf_files
        if any(r["source"] == f.path and r["status"] == "failed" for r in results)
    ]

    artifact_manifest = {
        "data_id": data_id,
        "pdf_count": len(pdf_files),
        "chunk_count": 0,
        "page_count": 0,
        "created_at": datetime.now().isoformat(),
        "config_hashes": {"parser": parser_hash},
        "pdf_inventory": {f.path: f.sha256 for f in success_files},
        "failed_inventory": {f.path: f.sha256 for f in failed_files},
    }
    cache.save_manifest(data_id, artifact_manifest)

    relative_parsed = f"{data_id[:16]}/parsed_{parser_hash}"
    cache.save_pointer("full_parsed", relative_parsed)

    logger.info(
        f"Parsing completed: {success_count} succeeded, {skipped_count} skipped, "
        f"{failed_count} failed out of {len(pdf_files)} total"
    )

    return results


def parse_all_pdfs_composite(
    input_dir: str,
    artifacts_dir: str,
    primary: str = "pymupdf4llm",
    enhancer: str | None = None,
    primary_config: dict | None = None,
    enhancer_config: dict | None = None,
    force: bool = False,
) -> list[dict[str, str]]:
    """Parse all PDF files using the composite parser system.

    Uses the new primary/enhancer configuration format to create a parser
    via ``ParserRegistry.get_composite``.

    Args:
        input_dir: Directory containing PDF files to parse.
        artifacts_dir: Root directory for storing cached artifacts.
        primary: Primary parser name (e.g., "pymupdf4llm").
        enhancer: Optional table enhancer name (e.g., "pdfplumber").
        primary_config: Options passed to the primary parser constructor.
        enhancer_config: Options passed to the enhancer constructor.
        force: If True, re-parse files even if valid cache exists.

    Returns:
        List of result dictionaries with source, output, category, and status.

    Raises:
        FileNotFoundError: If input_dir does not exist.
    """
    raw_dir = Path(input_dir)
    if not raw_dir.exists():
        raise ParsingError(f"Input directory not found: {input_dir}")

    artifacts_path = Path(artifacts_dir)
    cache = ArtifactCache(artifacts_path, raw_dir)

    pdf_files = _collect_pdf_files(raw_dir)
    data_id = compute_data_id(pdf_files)

    parser_config_for_hash = {
        "primary": primary,
        "enhancer": enhancer,
        "primary_config": primary_config or {},
        "enhancer_config": enhancer_config or {},
    }
    parser_hash = compute_parser_config_hash(parser_config_for_hash)

    parsed_dir = cache.get_parsed_dir(data_id, parser_hash)
    parsed_dir.mkdir(parents=True, exist_ok=True)

    use_page_chunks = bool(primary_config and primary_config.get("page_chunks", False))

    if not force:
        manifest = cache.load_manifest(data_id)
        cache_valid = (
            manifest is not None
            and "pdf_inventory" in manifest
            and cache.is_full_parsed_valid(parser_hash, use_page_chunks=use_page_chunks)
        )
    else:
        cache_valid = False

    if cache_valid and not force:
        logger.info(
            f"Cache HIT: Valid parsed artifacts exist for data_id={data_id[:12]}"
        )
        results = []
        for meal_file in pdf_files:
            if use_page_chunks:
                output_file = parsed_dir / Path(meal_file.path).with_suffix(
                    ".pages.json"
                )
            else:
                output_file = parsed_dir / Path(meal_file.path).with_suffix(".md")

            results.append(
                {
                    "source": meal_file.path,
                    "output": str(output_file),
                    "category": detect_document_category(meal_file.path),
                    "status": "skipped",
                }
            )

        logger.info(f"Skipped {len(results)} files (valid cache found)")
        return results

    parser = ParserRegistry.get_composite(
        primary, enhancer, primary_config, enhancer_config
    )
    results = []

    for meal_file in pdf_files:
        pdf_path = raw_dir / meal_file.path
        if use_page_chunks:
            output_file = parsed_dir / Path(meal_file.path).with_suffix(".pages.json")
        else:
            output_file = parsed_dir / Path(meal_file.path).with_suffix(".md")

        if (
            not force
            and output_file.exists()
            and manifest
            and "pdf_inventory" in manifest
        ):
            current_sha = _compute_file_sha256(pdf_path)
            if current_sha == manifest["pdf_inventory"].get(meal_file.path):
                logger.info(f"Skipping (already parsed): {meal_file.path}")
                results.append(
                    {
                        "source": meal_file.path,
                        "output": str(output_file),
                        "category": detect_document_category(meal_file.path),
                        "status": "skipped",
                    }
                )
                continue

        try:
            output_file.parent.mkdir(parents=True, exist_ok=True)
            result = parser.parse(str(pdf_path))

            if use_page_chunks:
                pages_data = [
                    {
                        "page_number": page.page_number,
                        "text": page.text,
                        "metadata": page.metadata,
                    }
                    for page in result.pages
                ]
                with open(output_file, "w", encoding="utf-8") as f:
                    json.dump(pages_data, f, ensure_ascii=False, indent=2)
            else:
                with open(output_file, "w", encoding="utf-8") as f:
                    for page in result.pages:
                        f.write(page.text)
                        f.write("\n\n")

            category = detect_document_category(meal_file.path)
            results.append(
                {
                    "source": meal_file.path,
                    "output": str(output_file),
                    "category": category,
                    "status": "success",
                    "format": "pages_json" if use_page_chunks else "markdown",
                }
            )
            logger.success(f"Parsed: {meal_file.path} -> {output_file.name}")

        except Exception as e:
            logger.error(f"Failed to parse {meal_file.path}: {str(e)}")
            results.append(
                {
                    "source": meal_file.path,
                    "output": None,
                    "category": None,
                    "status": "failed",
                    "error": str(e),
                }
            )

    success_count = sum(1 for r in results if r["status"] == "success")
    failed_count = sum(1 for r in results if r["status"] == "failed")
    skipped_count = sum(1 for r in results if r["status"] == "skipped")

    success_files = [
        f
        for f in pdf_files
        if any(r["source"] == f.path and r["status"] == "success" for r in results)
    ]
    failed_files = [
        f
        for f in pdf_files
        if any(r["source"] == f.path and r["status"] == "failed" for r in results)
    ]

    artifact_manifest = {
        "data_id": data_id,
        "pdf_count": len(pdf_files),
        "chunk_count": 0,
        "page_count": 0,
        "created_at": datetime.now().isoformat(),
        "config_hashes": {"parser": parser_hash},
        "pdf_inventory": {f.path: f.sha256 for f in success_files},
        "failed_inventory": {f.path: f.sha256 for f in failed_files},
    }
    cache.save_manifest(data_id, artifact_manifest)

    relative_parsed = f"{data_id[:16]}/parsed_{parser_hash}"
    cache.save_pointer("full_parsed", relative_parsed)

    logger.info(
        f"Parsing completed: {success_count} succeeded, {skipped_count} skipped, "
        f"{failed_count} failed out of {len(pdf_files)} total"
    )

    return results
