"""Migration module for importing issues from backlog.md.

Parses Markdown tables and generates issue files with new ID format.
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.issue.manager import IssueManager, generate_slug, issue_to_markdown
from src.issue.models import Issue, IssuePriority, IssueStatus, IssueType


@dataclass
class ParsedIssue:
    """Parsed issue data from backlog.md table row.

    Attributes:
        legacy_id: Original issue ID (e.g., BUG-032)
        title: Issue description/title
        source: Source reference
        status: Status emoji text
        note: Additional notes
        issue_type: Issue type derived from table section
        scale: Scale field (optional, for Feature/Refactor)
        priority: Priority field (optional, for Test)
        complete_date: Completion date (for completed issues)
        is_deferred: Whether issue is in deferred section
    """

    legacy_id: str
    title: str
    source: str = ""
    status: str = "📋 待处理"
    note: str = ""
    issue_type: IssueType = IssueType.BUG
    scale: str | None = None
    priority: str | None = None
    complete_date: str | None = None
    is_deferred: bool = False


@dataclass
class MigrationStats:
    """Statistics for migration run.

    Attributes:
        total_parsed: Total issues parsed from backlog
        created: Issues successfully created
        skipped: Issues skipped (already exist)
        errors: Issues with errors
        by_type: Count by issue type
        by_status: Count by status
    """

    total_parsed: int = 0
    created: int = 0
    skipped: int = 0
    errors: int = 0
    by_type: dict[str, int] = field(default_factory=dict)
    by_status: dict[str, int] = field(default_factory=dict)


STATUS_MAP: dict[str, IssueStatus] = {
    "📋 待处理": IssueStatus.TODO,
    "🔄 进行中": IssueStatus.IN_PROGRESS,
    "✅ 已完成": IssueStatus.DONE,
    "⏳ 已延期": IssueStatus.DEFERRED,
    "⏳ 待定": IssueStatus.DEFERRED,
}

TYPE_MAP: dict[str, IssueType] = {
    "Bug": IssueType.BUG,
    "Feature": IssueType.FEAT,
    "Refactor": IssueType.RF,
    "Optimization": IssueType.OPT,
    "Investigation": IssueType.INV,
    "Test": IssueType.TEST,
}

TYPE_PREFIX_MAP: dict[str, IssueType] = {
    "BUG": IssueType.BUG,
    "FEAT": IssueType.FEAT,
    "RF": IssueType.RF,
    "OPT": IssueType.OPT,
    "INV": IssueType.INV,
    "TEST": IssueType.TEST,
    "FEAT-DONE": IssueType.FEAT,
    "RF-DONE": IssueType.RF,
}


def parse_markdown_table(content: str) -> list[dict[str, str]]:
    """Parse a Markdown table into list of row dictionaries.

    Args:
        content: Markdown table content

    Returns:
        List of dictionaries with column names as keys
    """
    lines = content.strip().split("\n")
    if len(lines) < 2:
        return []

    header_line = lines[0]
    headers = [h.strip() for h in header_line.split("|") if h.strip()]

    rows: list[dict[str, str]] = []
    for line in lines[2:]:
        if not line.strip() or line.strip().startswith("|---"):
            continue

        cells_raw = line.split("|")
        cells_cleaned = []
        for cell in cells_raw:
            cell = cell.strip()
            if cell:
                cells_cleaned.append(cell)

        if len(cells_cleaned) != len(headers):
            cells_cleaned = cells_cleaned[: len(headers)]
            while len(cells_cleaned) < len(headers):
                cells_cleaned.append("")

        row = dict(zip(headers, cells_cleaned, strict=False))
        rows.append(row)

    return rows


def extract_link_text(text: str) -> str:
    """Extract text from Markdown link format.

    Args:
        text: Text that may contain Markdown link

    Returns:
        Extracted link text or original text
    """
    match = re.search(r"\[([^\]]+)\]\([^)]+\)", text)
    if match:
        return match.group(1)
    return text


def determine_issue_type(legacy_id: str, section_type: IssueType) -> IssueType:
    """Determine issue type from legacy ID and section.

    Args:
        legacy_id: Original issue ID
        section_type: Issue type from section header

    Returns:
        Determined IssueType
    """
    for prefix, issue_type in TYPE_PREFIX_MAP.items():
        if legacy_id.startswith(prefix):
            return issue_type
    return section_type


def parse_status_from_text(status_text: str) -> IssueStatus:
    """Parse status from emoji text.

    Args:
        status_text: Status text with emoji

    Returns:
        IssueStatus enum value
    """
    for pattern, status in STATUS_MAP.items():
        if pattern in status_text:
            return status
    return IssueStatus.TODO


def parse_backlog_file(backlog_path: Path) -> list[ParsedIssue]:
    """Parse backlog.md file and extract all issues.

    Args:
        backlog_path: Path to backlog.md file

    Returns:
        List of ParsedIssue objects
    """
    content = backlog_path.read_text(encoding="utf-8")
    issues: list[ParsedIssue] = []

    current_type: IssueType = IssueType.BUG
    in_deferred_section = False
    in_completed_section = False

    lines = content.split("\n")
    current_table_lines: list[str] = []
    in_table = False

    for line in lines:
        if line.startswith("## 已完成"):
            in_completed_section = True
            in_deferred_section = False
            continue

        if line.startswith("### 🟡 已延期"):
            in_deferred_section = True
            continue

        if line.startswith("### "):
            in_deferred_section = "已延期" in line
            continue

        if (
            line.startswith("## ")
            and not line.startswith("## 统计")
            and not line.startswith("## 状态")
            and not line.startswith("## ID")
        ):
            section_name = line[3:].strip()
            current_type = TYPE_MAP.get(section_name, IssueType.BUG)
            in_deferred_section = False
            in_completed_section = False
            continue

        if line.startswith("|") and "|" in line[1:]:
            if not in_table:
                in_table = True
                current_table_lines = []
            current_table_lines.append(line)
        else:
            if in_table and current_table_lines:
                table_content = "\n".join(current_table_lines)
                rows = parse_markdown_table(table_content)

                for row in rows:
                    issue = parse_table_row(
                        row, current_type, in_deferred_section, in_completed_section
                    )
                    if issue:
                        issues.append(issue)

                current_table_lines = []
                in_table = False

    if in_table and current_table_lines:
        table_content = "\n".join(current_table_lines)
        rows = parse_markdown_table(table_content)

        for row in rows:
            issue = parse_table_row(
                row, current_type, in_deferred_section, in_completed_section
            )
            if issue:
                issues.append(issue)

    return issues


def parse_table_row(
    row: dict[str, str],
    issue_type: IssueType,
    is_deferred: bool,
    is_completed: bool,
) -> ParsedIssue | None:
    """Parse a table row into ParsedIssue.

    Args:
        row: Dictionary of column values
        issue_type: Issue type from section
        is_deferred: Whether in deferred section
        is_completed: Whether in completed section

    Returns:
        ParsedIssue or None if invalid
    """
    legacy_id = row.get("ID", "").strip()
    if not legacy_id or not re.match(
        r"^(BUG|FEAT|RF|OPT|INV|TEST|FEAT-DONE|RF-DONE)-\d+", legacy_id
    ):
        return None

    title = row.get("描述", row.get("标题", "")).strip()
    source = extract_link_text(row.get("来源", "").strip())
    note = row.get("备注", "").strip()
    scale = row.get("规模")
    priority = row.get("优先级")
    complete_date = row.get("完成日期")

    status_text = row.get("状态", "📋 待处理").strip()

    actual_type = determine_issue_type(legacy_id, issue_type)

    return ParsedIssue(
        legacy_id=legacy_id,
        title=title,
        source=source,
        status=status_text,
        note=note,
        issue_type=actual_type,
        scale=scale,
        priority=priority,
        complete_date=complete_date,
        is_deferred=is_deferred,
    )


def generate_new_issue(
    parsed: ParsedIssue,
    wt_id: str,
    sequence: int,
    date: datetime,
) -> Issue:
    """Generate new Issue object from parsed data.

    Args:
        parsed: ParsedIssue data
        wt_id: Worktree ID
        sequence: Sequence number
        date: Date for ID

    Returns:
        Issue object with new ID format
    """
    date_str = date.strftime("%Y%m%d")
    new_id = f"{parsed.issue_type.value}-{date_str}-{sequence:03d}-{wt_id}"

    if parsed.complete_date:
        status = IssueStatus.DONE
    elif parsed.is_deferred:
        status = IssueStatus.DEFERRED
    else:
        status = STATUS_MAP.get(parsed.status, IssueStatus.TODO)

    body = generate_migration_body(parsed)

    priority = IssuePriority.MEDIUM
    if parsed.priority:
        priority_map = {
            "高": IssuePriority.HIGH,
            "中": IssuePriority.MEDIUM,
            "低": IssuePriority.LOW,
            "high": IssuePriority.HIGH,
            "medium": IssuePriority.MEDIUM,
            "low": IssuePriority.LOW,
        }
        priority = priority_map.get(parsed.priority.lower(), IssuePriority.MEDIUM)

    return Issue(
        id=new_id,
        title=parsed.title,
        type=parsed.issue_type,
        status=status,
        priority=priority,
        labels=[],
        created_at=date,
        updated_at=date,
        source=parsed.source,
        legacy_id=parsed.legacy_id,
        body=body,
    )


def generate_migration_body(parsed: ParsedIssue) -> str:
    """Generate issue body from parsed data.

    Args:
        parsed: ParsedIssue data

    Returns:
        Markdown body content
    """
    lines: list[str] = []
    lines.append(f"## {parsed.issue_type.value} 描述")
    lines.append("")
    lines.append(parsed.title)
    lines.append("")

    if parsed.source:
        lines.append("## 来源")
        lines.append("")
        lines.append(parsed.source)
        lines.append("")

    if parsed.note:
        lines.append("## 备注")
        lines.append("")
        lines.append(parsed.note)
        lines.append("")

    if parsed.scale:
        lines.append("## 规模")
        lines.append("")
        lines.append(parsed.scale)
        lines.append("")

    if parsed.complete_date:
        lines.append("## 完成日期")
        lines.append("")
        lines.append(parsed.complete_date)
        lines.append("")

    lines.append("## 迁移信息")
    lines.append("")
    lines.append(f"- 原始 ID: {parsed.legacy_id}")
    lines.append(f"- 迁移时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    return "\n".join(lines)


class BacklogMigrator:
    """Migrator for converting backlog.md to issue files.

    Attributes:
        backlog_path: Path to backlog.md
        issues_dir: Root directory for issues
        wt_id: Worktree ID for new issues
        dry_run: If True, don't write files
    """

    def __init__(
        self,
        backlog_path: Path,
        issues_dir: Path,
        wt_id: str = "wt1",
        dry_run: bool = False,
    ):
        """Initialize migrator.

        Args:
            backlog_path: Path to backlog.md
            issues_dir: Root directory for issues
            wt_id: Worktree ID for new issues
            dry_run: If True, don't write files
        """
        self.backlog_path = backlog_path
        self.issues_dir = issues_dir
        self.wt_id = wt_id
        self.dry_run = dry_run
        self.stats = MigrationStats()
        self.manager = IssueManager(issues_dir=issues_dir)
        self._global_sequence = 0

    def migrate(self) -> MigrationStats:
        """Run migration from backlog.md to issue files.

        Uses a global sequence counter (shared across all types) to match
        the normal ID generation behavior. Sequence numbers are derived
        from existing files, so no post-migration state update is needed.

        Returns:
            MigrationStats with results
        """
        if not self.backlog_path.exists():
            logger.error(f"Backlog file not found: {self.backlog_path}")
            return self.stats

        parsed_issues = parse_backlog_file(self.backlog_path)
        self.stats.total_parsed = len(parsed_issues)

        logger.info(f"Parsed {len(parsed_issues)} issues from backlog")

        migration_date = datetime.now()

        for parsed in parsed_issues:
            try:
                self._global_sequence += 1
                seq = self._global_sequence

                issue = generate_new_issue(parsed, self.wt_id, seq, migration_date)

                type_key = parsed.issue_type.value
                self.stats.by_type[type_key] = self.stats.by_type.get(type_key, 0) + 1

                status_key = issue.status.value
                self.stats.by_status[status_key] = (
                    self.stats.by_status.get(status_key, 0) + 1
                )

                if self.dry_run:
                    logger.info(
                        f"[DRY-RUN] Would create: {issue.id} (from {parsed.legacy_id})"
                    )
                    self.stats.created += 1
                else:
                    self._save_issue_file(issue)
                    self.stats.created += 1

            except Exception as e:
                logger.error(f"Failed to migrate {parsed.legacy_id}: {e}")
                self.stats.errors += 1

        return self.stats

    def _save_issue_file(self, issue: Issue) -> Path:
        """Save issue to appropriate directory.

        Args:
            issue: Issue to save

        Returns:
            Path to saved file
        """
        if issue.status == IssueStatus.DONE:
            month_dir = issue.updated_at.strftime("%Y-%m")
            target_dir = self.manager.completed_dir / month_dir
        elif issue.status == IssueStatus.DEFERRED:
            target_dir = self.manager.deferred_dir
        elif issue.status == IssueStatus.CANCELLED:
            target_dir = self.manager.cancelled_dir
        else:
            target_dir = self.manager.active_dir

        target_dir.mkdir(parents=True, exist_ok=True)

        slug = generate_slug(issue.title)
        filename = f"{issue.id}-{slug}.md"
        file_path = target_dir / filename

        issue.source = str(file_path.relative_to(self.issues_dir))

        content = issue_to_markdown(issue)
        file_path.write_text(content, encoding="utf-8")

        logger.debug(f"Saved issue to {file_path}")
        return file_path

    def verify(self) -> dict[str, Any]:
        """Verify migration results.

        Returns:
            Dictionary with verification results
        """
        results: dict[str, Any] = {
            "backlog_path": str(self.backlog_path),
            "issues_dir": str(self.issues_dir),
            "parsed_count": self.stats.total_parsed,
            "created_count": self.stats.created,
            "error_count": self.stats.errors,
            "by_type": dict(self.stats.by_type),
            "by_status": dict(self.stats.by_status),
            "issues": [],
        }

        for directory in [
            self.manager.active_dir,
            self.manager.completed_dir,
            self.manager.deferred_dir,
            self.manager.cancelled_dir,
        ]:
            if not directory.exists():
                continue

            for file_path in directory.glob("**/*.md"):
                if file_path.name.startswith("_"):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8")
                    if content.startswith("---"):
                        parts = content.split("---", 2)
                        if len(parts) >= 2:
                            import yaml

                            front_matter = yaml.safe_load(parts[1])
                            results["issues"].append(
                                {
                                    "id": front_matter.get("id"),
                                    "legacy_id": front_matter.get("legacy_id"),
                                    "title": front_matter.get("title"),
                                    "status": front_matter.get("status"),
                                    "file": str(file_path.relative_to(self.issues_dir)),
                                }
                            )
                except Exception as e:
                    logger.warning(f"Failed to read {file_path}: {e}")

        return results


def run_migration(
    backlog_path: Path,
    issues_dir: Path,
    wt_id: str = "wt1",
    dry_run: bool = False,
) -> MigrationStats:
    """Run migration from backlog.md to issue files.

    Args:
        backlog_path: Path to backlog.md
        issues_dir: Root directory for issues
        wt_id: Worktree ID for new issues
        dry_run: If True, don't write files

    Returns:
        MigrationStats with results
    """
    migrator = BacklogMigrator(
        backlog_path=backlog_path,
        issues_dir=issues_dir,
        wt_id=wt_id,
        dry_run=dry_run,
    )
    return migrator.migrate()


def run_verification(
    backlog_path: Path,
    issues_dir: Path,
    wt_id: str = "wt1",
) -> dict[str, Any]:
    """Run migration verification.

    Args:
        backlog_path: Path to backlog.md
        issues_dir: Root directory for issues
        wt_id: Worktree ID for new issues

    Returns:
        Verification results dictionary
    """
    migrator = BacklogMigrator(
        backlog_path=backlog_path,
        issues_dir=issues_dir,
        wt_id=wt_id,
        dry_run=True,
    )
    migrator.migrate()
    return migrator.verify()
