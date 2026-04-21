import json
import re
from pathlib import Path
from typing import Any

import tiktoken
from loguru import logger

from src.utils import detect_document_category, ensure_dir


def _extract_page_markers(text: str) -> list[tuple[int, int]]:
    """Extract page marker positions from text.

    Finds all <!-- page: N --> markers and returns their positions
    as (page_number, char_offset) tuples.

    Args:
        text: Input text with optional page markers.

    Returns:
        List of (page_number, char_offset) tuples, sorted by offset.
    """
    markers = []
    for match in re.finditer(r'<!--\s*page:\s*(\d+)\s*-->', text):
        page_num = int(match.group(1))
        markers.append((page_num, match.start()))
    return markers


def _extract_headings(text: str) -> list[str]:
    """Extract Markdown headings from text.

    Args:
        text: Input text with optional Markdown headings.

    Returns:
        List of heading strings (e.g., ['# Title', '## Subtitle']).
    """
    headings = []
    for line in text.split('\n'):
        stripped = line.strip()
        if stripped.startswith('#'):
            headings.append(stripped)
    return headings


def _get_page_range(
    chunk_text: str,
    page_markers: list[tuple[int, int]],
    full_text: str,
) -> tuple[int | None, int | None]:
    """Determine page range for a chunk based on page markers.

    Args:
        chunk_text: The chunk's text content.
        page_markers: List of (page_number, char_offset) from full text.
        full_text: The full document text.

    Returns:
        Tuple of (page_start, page_end) or (None, None) if no markers.
    """
    if not page_markers:
        return (None, None)

    search_prefix = chunk_text[:50] if len(chunk_text) >= 50 else chunk_text
    chunk_start = full_text.find(search_prefix)
    if chunk_start == -1:
        chunk_start = 0

    chunk_end = chunk_start + len(chunk_text)

    page_start = None
    page_end = None

    for page_num, offset in page_markers:
        if offset <= chunk_start:
            page_start = page_num
        if offset <= chunk_end:
            page_end = page_num

    if page_start is not None and page_end is None:
        page_end = page_start

    return (page_start, page_end)


def chunk_text(
    text: str,
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
) -> list[dict[str, Any]]:
    """Split text into fixed-size chunks based on token count.

    Uses the specified tiktoken encoding to tokenize the input text, then
    slices the token sequence into overlapping or non-overlapping chunks.

    Args:
        text: The input text to chunk.
        chunk_size: Maximum number of tokens per chunk. Defaults to 512.
        overlap: Number of tokens to overlap between consecutive chunks.
            Must be less than chunk_size. Defaults to 0.
        encoding_name: Name of the tiktoken encoding to use. Defaults to
            "cl100k_base".

    Returns:
        List of dictionaries, each with a "text" key containing the decoded
        chunk and a "metadata" key with chunk_index, char_count, token_count,
        start_token, and end_token.

    Raises:
        ValueError: If overlap is greater than or equal to chunk_size.
        Exception: If the tiktoken encoding cannot be loaded.
    """
    if not text or not text.strip():
        logger.warning("Empty text provided for chunking")
        return []

    if overlap >= chunk_size:
        error_msg = f"Overlap ({overlap}) must be less than chunk_size ({chunk_size})"
        logger.error(error_msg)
        raise ValueError(error_msg)

    try:
        encoding = tiktoken.get_encoding(encoding_name)
    except Exception as e:
        error_msg = f"Failed to load tiktoken encoding {encoding_name}: {str(e)}"
        logger.error(error_msg)
        raise Exception(error_msg)

    tokens = encoding.encode(text)
    total_tokens = len(tokens)

    if total_tokens == 0:
        logger.warning("Text encoded to zero tokens")
        return []

    logger.debug(f"Text has {total_tokens} tokens")

    chunks = []
    chunk_index = 0
    start = 0

    while start < total_tokens:
        end = min(start + chunk_size, total_tokens)
        chunk_tokens = tokens[start:end]
        chunk_text_decoded = encoding.decode(chunk_tokens)

        char_count = len(chunk_text_decoded)
        token_count = len(chunk_tokens)

        chunks.append(
            {
                "text": chunk_text_decoded,
                "metadata": {
                    "chunk_index": chunk_index,
                    "char_count": char_count,
                    "token_count": token_count,
                    "start_token": start,
                    "end_token": end,
                },
            }
        )

        chunk_index += 1

        if end >= total_tokens:
            break

        start = end - overlap if overlap > 0 else end

    logger.info(f"Created {len(chunks)} chunks from text with {total_tokens} tokens")
    return chunks


def process_parsed_files(
    input_dir: str,
    output_dir: str,
    chunk_size: int = 512,
    overlap: int = 0,
    encoding_name: str = "cl100k_base",
    source_filter: set | None = None,
) -> list[dict[str, Any]]:
    """Read parsed Markdown files, chunk them, and save results as JSONL.

    Scans the input directory for .md files, applies optional source
    filtering, chunks each file's text, and writes the chunked output
    to JSONL files in the output directory.

    Args:
        input_dir: Directory containing parsed Markdown files.
        output_dir: Directory where chunked JSONL files will be saved.
        chunk_size: Maximum number of tokens per chunk. Defaults to 512.
        overlap: Number of overlapping tokens between consecutive chunks.
            Defaults to 0.
        encoding_name: Name of the tiktoken encoding to use. Defaults to
            "cl100k_base".
        source_filter: Optional set of relative path strings; only files
            whose relative path is in this set will be processed.

    Returns:
        List of result dictionaries, each containing source, output,
        category, chunk_count, and status keys (plus error on failure).

    Raises:
        FileNotFoundError: If input_dir does not exist.
    """
    input_path = Path(input_dir)

    if not input_path.exists():
        error_msg = f"Input directory not found: {input_dir}"
        logger.error(error_msg)
        raise FileNotFoundError(error_msg)

    output_path = ensure_dir(output_dir)

    md_files = list(input_path.rglob("*.md"))

    if not md_files:
        logger.warning(f"No Markdown files found in {input_dir}")
        return []

    if source_filter is not None:
        original_count = len(md_files)
        md_files = [
            f for f in md_files if str(f.relative_to(input_path)) in source_filter
        ]
        logger.info(
            f"Source filter applied: {len(md_files)}/{original_count} files matched"
        )

    logger.info(f"Found {len(md_files)} Markdown files to process")

    all_results = []

    for md_file in md_files:
        try:
            with open(md_file, encoding="utf-8") as f:
                text = f.read()

            chunks = chunk_text(text, chunk_size, overlap, encoding_name)

            page_markers = _extract_page_markers(text)

            relative_path = md_file.relative_to(input_path)
            source_name = relative_path.stem

            category = detect_document_category(str(md_file))

            output_file = output_path / relative_path.with_suffix(".jsonl")

            output_file.parent.mkdir(parents=True, exist_ok=True)

            with open(output_file, "w", encoding="utf-8") as f:
                for chunk in chunks:
                    chunk_id = f"{source_name}::chunk::{chunk['metadata']['chunk_index']:03d}"

                    chunk_page_start, chunk_page_end = _get_page_range(
                        chunk["text"], page_markers, text
                    )
                    chunk_headings = _extract_headings(chunk["text"])

                    chunk_data = {
                        "chunk_id": chunk_id,
                        "text": chunk["text"],
                        "metadata": {
                            "source": str(relative_path),
                            "category": category,
                            "chunk_index": chunk["metadata"]["chunk_index"],
                            "char_count": chunk["metadata"]["char_count"],
                            "token_count": chunk["metadata"]["token_count"],
                            "start_token": chunk["metadata"]["start_token"],
                            "end_token": chunk["metadata"]["end_token"],
                            "page_start": chunk_page_start,
                            "page_end": chunk_page_end,
                            "headings": chunk_headings,
                        },
                    }

                    f.write(json.dumps(chunk_data, ensure_ascii=False) + "\n")

            all_results.append(
                {
                    "source": str(md_file),
                    "output": str(output_file),
                    "category": category,
                    "chunk_count": len(chunks),
                    "status": "success",
                }
            )

            logger.success(
                f"Processed {md_file.name}: {len(chunks)} chunks -> {output_file.name}"
            )

        except Exception as e:
            logger.error(f"Failed to process {md_file}: {str(e)}")
            all_results.append(
                {
                    "source": str(md_file),
                    "output": None,
                    "category": None,
                    "chunk_count": 0,
                    "status": "failed",
                    "error": str(e),
                }
            )

    success_count = sum(1 for r in all_results if r["status"] == "success")
    failed_count = sum(1 for r in all_results if r["status"] == "failed")
    total_chunks = sum(r.get("chunk_count", 0) for r in all_results)

    logger.info(
        f"Chunking completed: {success_count} succeeded, {failed_count} failed, {total_chunks} total chunks"
    )

    return all_results


if __name__ == "__main__":
    from src.utils import load_config, setup_logger

    config = load_config()
    setup_logger(config)

    chunker_config = config["chunker"]
    results = process_parsed_files(
        input_dir=chunker_config["input_dir"],
        output_dir=chunker_config["output_dir"],
        chunk_size=chunker_config["chunk_size"],
        overlap=chunker_config["chunk_overlap"],
    )

    for result in results:
        logger.info(f"Result: {result}")
