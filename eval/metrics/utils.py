from pathlib import Path
from typing import Any

DEFAULT_EVAL_BASE_CONFIG = {
    "model_name": "LongCat-Flash-Lite",
    "base_url": "https://api.longcat.chat/anthropic",
}


def get_eval_config(user_config: dict | None, default_config: dict) -> dict:
    """Get LLM evaluator config, merging user config into defaults.

    Merges in order: DEFAULT_EVAL_BASE_CONFIG → default_config →
    user_config["llm_evaluator"].  This ensures that model_name and
    base_url always fall back to DEFAULT_EVAL_BASE_CONFIG values when
    not overridden.

    Args:
        user_config: Optional config dict that may contain an
            'llm_evaluator' section.
        default_config: Domain-specific default config dict (e.g.
            generation or retrieval sub-configs).

    Returns:
        Merged config dict.
    """
    merged = {**DEFAULT_EVAL_BASE_CONFIG, **default_config}
    if user_config and "llm_evaluator" in user_config:
        merged.update(user_config["llm_evaluator"])
    return merged


def normalize_source(source: str, include_parent: bool = False) -> str:
    """Normalize source path to a comparable form.

    By default, extracts the filename stem (without extension and directory),
    so that paths like "annual_report/贵州茅台2023年年度报告.md"
    and "贵州茅台2023年年度报告.pdf" both become "贵州茅台2023年年度报告".

    When include_parent is True, includes the immediate parent directory
    name in the result, producing "annual_report/贵州茅台2023年年度报告".
    This prevents different directories with same-named documents from
    being conflated.

    Internally converts the input path to POSIX format (forward slashes)
    before processing, ensuring consistent output regardless of whether
    the input uses Windows backslashes or POSIX forward slashes.

    Args:
        source: Source path string. May use Windows backslashes or POSIX
            forward slashes; both are normalized to the same output.
        include_parent: If True, include the parent directory name in the
            normalized result as "{parent}/{stem}". If the path has no
            parent (or the parent is "."), only the stem is returned.
            Defaults to False for backward compatibility.

    Returns:
        Normalized source string — either the stem alone or
        "{parent}/{stem}" when include_parent is True and a parent
        directory exists.
    """
    p = Path(Path(source).as_posix())
    stem = p.stem
    if include_parent and p.parent != Path("."):
        parent_name = p.parent.name
        if parent_name:
            return f"{parent_name}/{stem}"
    return stem


def normalize_source_with_equivalence(
    source: str,
    equivalence_groups: dict[str, list[str]] | None = None,
    include_parent: bool = False,
) -> str:
    """Normalize source path with equivalence group matching.

    First normalizes the source using normalize_source (optionally
    including the parent directory), then checks if the result belongs
    to any equivalence group. If it does, returns the group key (the
    primary member's normalized form) so that equivalent documents map
    to the same identifier.

    This allows documents like "中国建筑2023年年度报告" and
    "中国建筑2023年年度报告摘要" to be treated as the same document
    for retrieval evaluation purposes.

    Args:
        source: Source path string.
        equivalence_groups: Optional dict mapping group keys to lists of
            file paths. The group key is the primary member's stem, and
            the value contains all equivalent file paths. If None or
            empty, behaves like normalize_source.
        include_parent: If True, include the parent directory name in
            the normalized result. Passed through to normalize_source.
            Defaults to False for backward compatibility.

    Returns:
        Group key if the source belongs to an equivalence group,
        otherwise the normalized stem (with optional parent).
    """
    stem = normalize_source(source, include_parent=include_parent)
    if not equivalence_groups:
        return stem
    for group_key, members in equivalence_groups.items():
        for member in members:
            if normalize_source(member, include_parent=include_parent) == stem:
                return group_key
    return stem


def _parse_chunk_id(chunk_id: str) -> tuple:
    """Parse chunk_id into (doc_stem, chunk_index).

    Supports two formats:
    - New format: "{doc_stem}::chunk::{index}" — splits by "::chunk::".
    - Old format: "{doc_stem}_{index:03d}" — falls back to rfind("_").

    Args:
        chunk_id: Chunk identifier string to parse.

    Returns:
        Tuple of (doc_stem, chunk_index) where doc_stem is the document
        stem string and chunk_index is the integer chunk index.
        Returns (chunk_id, -1) if parsing fails.
    """
    separator = "::chunk::"
    if separator in chunk_id:
        parts = chunk_id.split(separator)
        doc_stem = parts[0]
        try:
            chunk_index = int(parts[1])
            return (doc_stem, chunk_index)
        except (ValueError, IndexError):
            return (chunk_id, -1)
    last_underscore = chunk_id.rfind("_")
    if last_underscore == -1:
        return (chunk_id, -1)
    doc_stem = chunk_id[:last_underscore]
    suffix = chunk_id[last_underscore + 1 :]
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
