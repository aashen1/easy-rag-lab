from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from loguru import logger


def find_chunks_by_source_page(
    source_pdf: str,
    page_number: int,
    chunks_dir: str | Path,
) -> list[dict[str, Any]]:
    """Find chunks that belong to a specific source PDF and page number.

    Searches through JSONL chunk files in the given directory, matching
    chunks whose metadata.source contains the source_pdf filename and
    whose metadata.page_numbers contains the page_number.

    Args:
        source_pdf: PDF filename to match (matched against metadata.source
            using substring match on the filename part).
        page_number: Page number to search for within chunk page_numbers.
        chunks_dir: Path to the directory containing JSONL chunk files.

    Returns:
        List of matching chunk dictionaries, each containing chunk_id,
        text, and metadata. Empty list if no matches found.
    """
    chunks_dir = Path(chunks_dir)
    if not chunks_dir.exists():
        logger.warning(f"Chunks directory does not exist: {chunks_dir}")
        return []

    pdf_name = Path(source_pdf).name
    exact_matches: list[dict[str, Any]] = []
    fuzzy_matches: list[dict[str, Any]] = []

    try:
        jsonl_files = sorted(chunks_dir.glob("*.jsonl"))
    except OSError as e:
        logger.warning(f"Failed to list JSONL files in {chunks_dir}: {e}")
        return []

    for jsonl_path in jsonl_files:
        try:
            lines = jsonl_path.read_text(encoding="utf-8").splitlines()
        except OSError as e:
            logger.warning(f"Failed to read {jsonl_path}: {e}")
            continue

        for line in lines:
            line = line.strip()
            if not line:
                continue
            try:
                chunk = json.loads(line)
            except json.JSONDecodeError as e:
                logger.warning(f"Corrupt JSON in {jsonl_path}: {e}")
                continue

            metadata = chunk.get("metadata", {})
            source = metadata.get("source", "")
            page_numbers = metadata.get("page_numbers", [])

            if pdf_name not in source:
                continue

            if not isinstance(page_numbers, list):
                continue

            if page_number in page_numbers:
                exact_matches.append(
                    {
                        "chunk_id": chunk.get("chunk_id", ""),
                        "text": chunk.get("text", ""),
                        "metadata": metadata,
                    }
                )
            elif page_numbers and min(page_numbers) <= page_number <= max(page_numbers):
                fuzzy_matches.append(
                    {
                        "chunk_id": chunk.get("chunk_id", ""),
                        "text": chunk.get("text", ""),
                        "metadata": metadata,
                    }
                )

    if exact_matches:
        return exact_matches

    if fuzzy_matches:
        logger.info(
            f"No exact page match for page {page_number}, "
            f"returning {len(fuzzy_matches)} fuzzy match(es)"
        )
        return fuzzy_matches

    return []
