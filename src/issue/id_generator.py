"""Issue ID generation logic.

Generates unique IDs in format: <TYPE>-<YYYYMMDD>-<SEQ>-<WTID>
Sequence numbers are stored per worktree per date.
Includes collision detection against existing issue files.
"""

import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.issue.models import IssueType

SEQUENCES_DIR = Path(".issues/sequences")
ISSUES_DIR = Path(".issues")


def _scan_existing_ids(issues_dir: Path | None = None) -> set[str]:
    """Scan all issue files and collect existing IDs.

    Searches active/, completed/, deferred/, and cancelled/ directories
    for issue markdown files and extracts their IDs from filenames.

    Args:
        issues_dir: Root issues directory. Defaults to .issues/

    Returns:
        Set of existing issue ID strings
    """
    base = issues_dir or ISSUES_DIR
    existing_ids: set[str] = set()

    id_pattern = re.compile(r"^(BUG|FEAT|RF|OPT|INV|TEST)-\d{8}-\d{3}-\w+")

    for subdir in ["active", "completed", "deferred", "cancelled"]:
        target = base / subdir
        if not target.exists():
            continue
        for file_path in target.glob("**/*.md"):
            if file_path.name.startswith("_") or file_path.name.startswith("."):
                continue
            match = id_pattern.match(file_path.name)
            if match:
                existing_ids.add(match.group(0))

    return existing_ids


def generate_id(
    issue_type: IssueType,
    wt_id: str,
    date: datetime | None = None,
    sequences_dir: Path | None = None,
    issues_dir: Path | None = None,
) -> str:
    """Generate a unique issue ID with collision detection.

    Format: <TYPE>-<YYYYMMDD>-<SEQ>-<WTID>
    Example: BUG-20260427-001-wt1

    If the generated ID collides with an existing issue (e.g., after
    migration that bypassed the sequence file), the sequence is
    incremented until a unique ID is found.

    Args:
        issue_type: Type of issue (BUG, FEAT, etc.)
        wt_id: Worktree identifier
        date: Date for ID generation. Defaults to current date.
        sequences_dir: Directory for sequence files. Defaults to .issues/sequences/
        issues_dir: Root issues directory for collision scan. Defaults to .issues/

    Returns:
        str: Generated issue ID guaranteed to be unique
    """
    dt = date or datetime.now()
    date_str = dt.strftime("%Y%m%d")

    existing_ids = _scan_existing_ids(issues_dir)

    seq = get_next_sequence(wt_id, dt, sequences_dir)

    issue_id = f"{issue_type.value}-{date_str}-{seq:03d}-{wt_id}"

    max_attempts = 999
    attempts = 0
    while issue_id in existing_ids and attempts < max_attempts:
        attempts += 1
        seq = get_next_sequence(wt_id, dt, sequences_dir)
        issue_id = f"{issue_type.value}-{date_str}-{seq:03d}-{wt_id}"

    if issue_id in existing_ids:
        logger.error(f"Could not generate unique ID after {max_attempts} attempts")

    logger.debug(f"Generated issue ID: {issue_id}")
    return issue_id


def get_next_sequence(
    wt_id: str,
    date: datetime,
    sequences_dir: Path | None = None,
) -> int:
    """Get the next sequence number for a worktree on a given date.

    Reads and increments the sequence counter stored in:
    .issues/sequences/{wt_id}/{YYYYMMDD}.txt

    Args:
        wt_id: Worktree identifier
        date: Date for sequence lookup
        sequences_dir: Directory for sequence files. Defaults to .issues/sequences/

    Returns:
        int: Next sequence number (1-indexed)
    """
    base_dir = sequences_dir or SEQUENCES_DIR
    date_str = date.strftime("%Y%m%d")
    seq_file = base_dir / wt_id / f"{date_str}.txt"

    seq_file.parent.mkdir(parents=True, exist_ok=True)

    current_seq = 0
    if seq_file.exists():
        try:
            current_seq = int(seq_file.read_text(encoding="utf-8").strip())
        except (ValueError, OSError) as e:
            logger.warning(
                f"Failed to read sequence file {seq_file}: {e}, starting from 1"
            )
            current_seq = 0

    next_seq = current_seq + 1

    try:
        seq_file.write_text(str(next_seq), encoding="utf-8")
        logger.debug(f"Updated sequence for {wt_id}/{date_str}: {next_seq}")
    except OSError as e:
        logger.error(f"Failed to write sequence file {seq_file}: {e}")
        raise

    return next_seq


def peek_next_sequence(
    wt_id: str,
    date: datetime,
    sequences_dir: Path | None = None,
) -> int:
    """Peek at the next sequence number without incrementing.

    Args:
        wt_id: Worktree identifier
        date: Date for sequence lookup
        sequences_dir: Directory for sequence files. Defaults to .issues/sequences/

    Returns:
        int: Next sequence number that would be assigned
    """
    base_dir = sequences_dir or SEQUENCES_DIR
    date_str = date.strftime("%Y%m%d")
    seq_file = base_dir / wt_id / f"{date_str}.txt"

    if seq_file.exists():
        try:
            current_seq = int(seq_file.read_text(encoding="utf-8").strip())
            return current_seq + 1
        except (ValueError, OSError):
            pass

    return 1


def reset_sequence(
    wt_id: str,
    date: datetime,
    sequences_dir: Path | None = None,
) -> None:
    """Reset sequence counter for a worktree on a given date.

    Args:
        wt_id: Worktree identifier
        date: Date for sequence reset
        sequences_dir: Directory for sequence files. Defaults to .issues/sequences/
    """
    base_dir = sequences_dir or SEQUENCES_DIR
    date_str = date.strftime("%Y%m%d")
    seq_file = base_dir / wt_id / f"{date_str}.txt"

    if seq_file.exists():
        try:
            seq_file.unlink()
            logger.info(f"Reset sequence for {wt_id}/{date_str}")
        except OSError as e:
            logger.error(f"Failed to reset sequence file {seq_file}: {e}")
            raise
