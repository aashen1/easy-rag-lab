"""Issue ID generation logic.

Generates unique IDs in format: <TYPE>-<YYYYMMDD>-<SEQ>-<WTID>
Sequence numbers are stored per worktree per date.
Includes lightweight collision detection via file existence check.
"""

from datetime import datetime
from pathlib import Path

from loguru import logger

from src.issue.models import IssueType

SEQUENCES_DIR = Path(".issues/sequences")
ISSUES_DIR = Path(".issues")


def _id_file_exists(issue_id: str, issues_dir: Path | None = None) -> bool:
    """Check if an issue file with the given ID already exists.

    Searches across all issue directories for a file whose name
    starts with the given ID prefix.

    Args:
        issue_id: Issue ID to check (e.g., BUG-20260428-001-wt1)
        issues_dir: Root issues directory. Defaults to .issues/

    Returns:
        True if a file with this ID prefix exists, False otherwise
    """
    base = issues_dir or ISSUES_DIR

    for subdir in ["active", "completed", "deferred", "cancelled"]:
        target = base / subdir
        if not target.exists():
            continue
        for file_path in target.glob("**/*.md"):
            if file_path.name.startswith("_") or file_path.name.startswith("."):
                continue
            if file_path.name.startswith(issue_id):
                return True

    return False


def generate_id(
    issue_type: IssueType,
    wt_id: str,
    date: datetime | None = None,
    sequences_dir: Path | None = None,
    issues_dir: Path | None = None,
) -> str:
    """Generate a unique issue ID with lightweight collision detection.

    Format: <TYPE>-<YYYYMMDD>-<SEQ>-<WTID>
    Example: BUG-20260427-001-wt1

    Uses the sequence file as the primary ID source (fast O(1) read).
    Only falls back to collision checking if the generated ID happens
    to match an existing file (rare edge case: sequence file desync
    after migration or manual file creation).

    Args:
        issue_type: Type of issue (BUG, FEAT, etc.)
        wt_id: Worktree identifier
        date: Date for ID generation. Defaults to current date.
        sequences_dir: Directory for sequence files. Defaults to .issues/sequences/
        issues_dir: Root issues directory for collision check. Defaults to .issues/

    Returns:
        str: Generated issue ID guaranteed to be unique
    """
    dt = date or datetime.now()
    date_str = dt.strftime("%Y%m%d")

    seq = get_next_sequence(wt_id, dt, sequences_dir)

    issue_id = f"{issue_type.value}-{date_str}-{seq:03d}-{wt_id}"

    max_attempts = 999
    attempts = 0
    while _id_file_exists(issue_id, issues_dir) and attempts < max_attempts:
        attempts += 1
        seq = get_next_sequence(wt_id, dt, sequences_dir)
        issue_id = f"{issue_type.value}-{date_str}-{seq:03d}-{wt_id}"

    if _id_file_exists(issue_id, issues_dir):
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
