"""Issue ID generation logic.

Generates unique IDs in format: <TYPE>-<YYYYMMDD>-<SEQ>-<WTID>
Sequence numbers are derived dynamically from existing issue files,
eliminating the need for external sequence state files.
"""

import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.issue.models import IssueType

ISSUES_DIR = Path(".issues")

_ID_PATTERN = re.compile(r"^(?:BUG|FEAT|RF|OPT|INV|TEST)-(\d{8})-(\d{3})-(\w+)")


def _find_max_sequence(
    date_str: str,
    wt_id: str,
    issues_dir: Path | None = None,
) -> int:
    """Find the maximum sequence number for a given date and worktree.

    Scans all issue directories and extracts sequence numbers from
    filenames matching the pattern *-YYYYMMDD-NNN-WTID*.

    Args:
        date_str: Date string in YYYYMMDD format
        wt_id: Worktree identifier
        issues_dir: Root issues directory. Defaults to .issues/

    Returns:
        Maximum sequence number found, or 0 if no matching issues exist
    """
    base = issues_dir or ISSUES_DIR
    max_seq = 0

    for subdir in ["active", "completed", "deferred", "cancelled"]:
        target = base / subdir
        if not target.exists():
            continue
        for file_path in target.glob("**/*.md"):
            if file_path.name.startswith("_") or file_path.name.startswith("."):
                continue
            match = _ID_PATTERN.match(file_path.name)
            if not match:
                continue
            file_date, file_seq, file_wt = (
                match.group(1),
                int(match.group(2)),
                match.group(3),
            )
            if file_date == date_str and file_wt == wt_id:
                max_seq = max(max_seq, file_seq)

    return max_seq


def generate_id(
    issue_type: IssueType,
    wt_id: str,
    date: datetime | None = None,
    issues_dir: Path | None = None,
) -> str:
    """Generate a unique issue ID derived from existing files.

    Format: <TYPE>-<YYYYMMDD>-<SEQ>-<WTID>
    Example: BUG-20260427-001-wt1

    Scans existing issue files to find the max sequence for the given
    date and worktree, then increments by 1. No external state files
    are needed — the truth is always in the issue files themselves.

    Args:
        issue_type: Type of issue (BUG, FEAT, etc.)
        wt_id: Worktree identifier
        date: Date for ID generation. Defaults to current date.
        issues_dir: Root issues directory. Defaults to .issues/

    Returns:
        str: Generated issue ID guaranteed to be unique
    """
    dt = date or datetime.now()
    date_str = dt.strftime("%Y%m%d")

    max_seq = _find_max_sequence(date_str, wt_id, issues_dir)
    next_seq = max_seq + 1

    issue_id = f"{issue_type.value}-{date_str}-{next_seq:03d}-{wt_id}"
    logger.debug(f"Generated issue ID: {issue_id} (max existing seq: {max_seq})")
    return issue_id
