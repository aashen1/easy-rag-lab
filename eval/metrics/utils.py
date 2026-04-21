from pathlib import Path
from typing import Any


def normalize_source(source: str) -> str:
    """Normalize source path to a comparable form.

    Extracts the filename stem (without extension and directory),
    so that paths like "annual_report/贵州茅台2023年年度报告.md"
    and "贵州茅台2023年年度报告.pdf" both become "贵州茅台2023年年度报告".

    Args:
        source: Source path string.

    Returns:
        Normalized source stem string.
    """
    return Path(source).stem


def normalize_source_with_equivalence(
    source: str,
    equivalence_groups: dict[str, list[str]] | None = None,
) -> str:
    """Normalize source path with equivalence group matching.

    First normalizes the source to its stem using normalize_source,
    then checks if the stem belongs to any equivalence group. If it
    does, returns the group key (the primary member's stem) so that
    equivalent documents map to the same identifier.

    This allows documents like "中国建筑2023年年度报告" and
    "中国建筑2023年年度报告摘要" to be treated as the same document
    for retrieval evaluation purposes.

    Args:
        source: Source path string.
        equivalence_groups: Optional dict mapping group keys to lists of
            file paths. The group key is the primary member's stem, and
            the value contains all equivalent file paths. If None or
            empty, behaves like normalize_source.

    Returns:
        Group key if the source belongs to an equivalence group,
        otherwise the normalized stem.
    """
    stem = normalize_source(source)
    if not equivalence_groups:
        return stem
    for group_key, members in equivalence_groups.items():
        for member in members:
            if normalize_source(member) == stem:
                return group_key
    return stem


def _parse_chunk_id(chunk_id: str) -> tuple:
    """Parse chunk_id into (doc_stem, chunk_index).

    Chunk IDs are expected to follow the format "{doc_stem}_{index:03d}",
    where the suffix after the last underscore is a zero-padded integer
    representing the chunk index within the document.

    Args:
        chunk_id: Chunk identifier string to parse.

    Returns:
        Tuple of (doc_stem, chunk_index) where doc_stem is the document
        stem string and chunk_index is the integer chunk index.
        Returns (chunk_id, -1) if the suffix cannot be parsed as an integer.
    """
    last_underscore = chunk_id.rfind("_")
    if last_underscore == -1:
        return (chunk_id, -1)
    doc_stem = chunk_id[:last_underscore]
    suffix = chunk_id[last_underscore + 1:]
    try:
        chunk_index = int(suffix)
        return (doc_stem, chunk_index)
    except ValueError:
        return (chunk_id, -1)


def _create_llm_client(
    api_key: str,
    base_url: str,
) -> Any:
    """Create an Anthropic LLM client with LongCat API adaptation.

    Args:
        api_key: API key for authentication.
        base_url: Base URL for the API endpoint.

    Returns:
        Anthropic client instance.
    """
    from src.utils import create_llm_client

    return create_llm_client(
        llm_config={"api_key": api_key, "base_url": base_url, "model_name": ""},
        mode="sdk",
    )
