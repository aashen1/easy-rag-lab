from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path


def _infer_equivalence_groups(pdf_files: list[str]) -> dict[str, list[str]]:
    """Infer equivalence groups from PDF file paths by stripping common suffixes.

    For each file path, extracts the filename stem (without extension) and
    removes common suffixes such as "摘要", "_摘要", "_英文版_", "_修订版_".
    The group key is formed as ``parent_dir/stripped_stem`` to distinguish
    files with the same stem residing in different directories (e.g. different
    companies' annual reports). If the file has no parent directory, the
    stripped stem alone is used as the group key.

    Args:
        pdf_files: List of relative PDF file paths.

    Returns:
        Dictionary mapping group keys to lists of POSIX-formatted file paths.
    """
    suffix_pattern = re.compile(r"(摘要|_摘要|_英文版_|_修订版_)$")
    groups: dict[str, list[str]] = {}
    for file_path in pdf_files:
        p = Path(file_path)
        stripped_stem = suffix_pattern.sub("", p.stem)
        parent_name = p.parent.name
        group_key = f"{parent_name}/{stripped_stem}" if parent_name else stripped_stem
        posix_path = p.as_posix()
        groups.setdefault(group_key, []).append(posix_path)
    return groups


def validate_meal_name(name: str) -> bool:
    """Validate that a meal name contains only allowed characters.

    Args:
        name: Proposed meal name string.

    Returns:
        True if the name matches the pattern of alphanumeric characters,
        underscores, and hyphens; False otherwise.
    """
    if not name:
        return False
    pattern = r"^[a-zA-Z0-9_-]+$"
    return bool(re.match(pattern, name))


def generate_timestamp_name() -> str:
    """Generate a meal name based on the current timestamp.

    Returns:
        Meal name string in the format 'meal_YYYYMMDD_HHMMSS'.
    """
    return f"meal_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
