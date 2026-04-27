"""Issue management core functionality.

Provides IssueManager class for creating, loading, saving, and managing issues.
"""

import re
from datetime import datetime
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from src.issue.config import get_worktree_id, load_config
from src.issue.id_generator import generate_id
from src.issue.models import Issue, IssuePriority, IssueStatus, IssueType

STATUS_TRANSITIONS: dict[IssueStatus, list[IssueStatus]] = {
    IssueStatus.TODO: [
        IssueStatus.IN_PROGRESS,
        IssueStatus.DEFERRED,
        IssueStatus.CANCELLED,
    ],
    IssueStatus.IN_PROGRESS: [
        IssueStatus.REVIEW,
        IssueStatus.TODO,
        IssueStatus.DEFERRED,
        IssueStatus.CANCELLED,
    ],
    IssueStatus.REVIEW: [
        IssueStatus.DONE,
        IssueStatus.IN_PROGRESS,
        IssueStatus.DEFERRED,
        IssueStatus.CANCELLED,
    ],
    IssueStatus.DONE: [],
    IssueStatus.DEFERRED: [IssueStatus.TODO, IssueStatus.CANCELLED],
    IssueStatus.CANCELLED: [IssueStatus.TODO],
}


class InvalidTransitionError(Exception):
    """Raised when an invalid status transition is attempted."""

    def __init__(
        self, current: IssueStatus, target: IssueStatus, allowed: list[IssueStatus]
    ) -> None:
        self.current = current
        self.target = target
        self.allowed = allowed
        super().__init__(
            f"Invalid transition from '{current.value}' to '{target.value}'. "
            f"Allowed transitions: {[s.value for s in allowed]}"
        )


def generate_slug(title: str, max_length: int = 30) -> str:
    """Generate a URL-friendly slug from title.

    Converts title to lowercase, replaces spaces and special chars with hyphens,
    and truncates to max_length.

    Args:
        title: Issue title to convert
        max_length: Maximum slug length

    Returns:
        URL-friendly slug string
    """
    slug = title.lower().strip()
    slug = re.sub(r"[^\w\s-]", "", slug)
    slug = re.sub(r"[\s_]+", "-", slug)
    slug = re.sub(r"-+", "-", slug)
    slug = slug.strip("-")

    if len(slug) > max_length:
        slug = slug[:max_length].rstrip("-")

    return slug or "issue"


def get_template_for_type(issue_type: IssueType) -> str:
    """Get the body template for a specific issue type.

    Args:
        issue_type: Type of issue

    Returns:
        Markdown template string
    """
    templates = {
        IssueType.BUG: """## 问题描述

（待填写）

## 根因分析

（待填写）

## 修复方向

（待填写）

## 更新记录

- {date}：创建
""",
        IssueType.FEAT: """## 功能描述

（待填写）

## 实现方案

（待填写）

## 验收标准

（待填写）

## 更新记录

- {date}：创建
""",
        IssueType.RF: """## 重构目标

（待填写）

## 重构范围

（待填写）

## 重构步骤

（待填写）

## 更新记录

- {date}：创建
""",
        IssueType.OPT: """## 优化目标

（待填写）

## 当前问题

（待填写）

## 优化方案

（待填写）

## 更新记录

- {date}：创建
""",
        IssueType.INV: """## 调研目标

（待填写）

## 调研范围

（待填写）

## 调研结果

（待填写）

## 更新记录

- {date}：创建
""",
        IssueType.TEST: """## 测试目标

（待填写）

## 测试范围

（待填写）

## 测试方案

（待填写）

## 更新记录

- {date}：创建
""",
    }
    return templates.get(issue_type, templates[IssueType.BUG])


def issue_to_markdown(issue: Issue) -> str:
    """Convert Issue object to markdown with YAML front matter.

    Args:
        issue: Issue object to convert

    Returns:
        Markdown string with YAML front matter
    """
    front_matter = {
        "id": issue.id,
        "title": issue.title,
        "type": issue.type.value,
        "status": issue.status.value,
        "priority": issue.priority.value,
        "labels": issue.labels,
        "assignee": issue.assignee,
        "milestone": issue.milestone,
        "created_at": issue.created_at.isoformat(),
        "updated_at": issue.updated_at.isoformat(),
        "source": issue.source,
        "legacy_id": issue.legacy_id,
    }

    yaml_str = yaml.dump(
        front_matter,
        default_flow_style=False,
        allow_unicode=True,
        sort_keys=False,
    )

    return f"---\n{yaml_str}---\n{issue.body}"


def markdown_to_issue(content: str, source_path: str | None = None) -> Issue:
    """Parse markdown with YAML front matter to Issue object.

    Args:
        content: Markdown content with YAML front matter
        source_path: Optional source file path

    Returns:
        Issue object

    Raises:
        ValueError: If content format is invalid
    """
    if not content.startswith("---"):
        raise ValueError("Content must start with YAML front matter")

    parts = content.split("---", 2)
    if len(parts) < 3:
        raise ValueError("Invalid front matter format")

    yaml_content = parts[1].strip()
    body = parts[2].strip()

    try:
        data = yaml.safe_load(yaml_content)
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML in front matter: {e}") from e

    data["body"] = body
    if source_path:
        data["source"] = source_path

    return Issue(**data)


class IssueManager:
    """Core issue management class.

    Provides methods for creating, loading, saving, and managing issues
    in the .issues directory structure.

    Attributes:
        issues_dir: Root directory for issues (.issues/)
        active_dir: Directory for active issues
        completed_dir: Directory for completed issues
        cancelled_dir: Directory for cancelled issues
        deferred_dir: Directory for deferred issues
    """

    def __init__(self, issues_dir: Path | None = None):
        """Initialize IssueManager.

        Args:
            issues_dir: Root directory for issues. Defaults to .issues/
        """
        self.issues_dir = issues_dir or Path(".issues")
        self.active_dir = self.issues_dir / "active"
        self.completed_dir = self.issues_dir / "completed"
        self.cancelled_dir = self.issues_dir / "cancelled"
        self.deferred_dir = self.issues_dir / "deferred"

        self._ensure_directories()

    def _ensure_directories(self) -> None:
        """Ensure all required directories exist."""
        for dir_path in [
            self.active_dir,
            self.completed_dir,
            self.cancelled_dir,
            self.deferred_dir,
        ]:
            dir_path.mkdir(parents=True, exist_ok=True)

    def _get_status_dir(
        self, status: IssueStatus, for_date: datetime | None = None
    ) -> Path:
        """Get directory path for a given status.

        Args:
            status: Issue status
            for_date: Date for monthly organization (only for DONE status)

        Returns:
            Path to the appropriate directory
        """
        if status == IssueStatus.DONE and for_date:
            month_dir = for_date.strftime("%Y-%m")
            return self.completed_dir / month_dir
        status_dir_map = {
            IssueStatus.TODO: self.active_dir,
            IssueStatus.IN_PROGRESS: self.active_dir,
            IssueStatus.REVIEW: self.active_dir,
            IssueStatus.DONE: self.completed_dir,
            IssueStatus.CANCELLED: self.cancelled_dir,
            IssueStatus.DEFERRED: self.deferred_dir,
        }
        return status_dir_map.get(status, self.active_dir)

    def _find_issue_file(self, issue_id: str) -> Path | None:
        """Find issue file by ID across all directories.

        Args:
            issue_id: Issue ID to find

        Returns:
            Path to issue file if found, None otherwise
        """
        for directory in [
            self.active_dir,
            self.completed_dir,
            self.cancelled_dir,
            self.deferred_dir,
        ]:
            for file_path in directory.glob("*.md"):
                if file_path.stem.startswith(issue_id):
                    return file_path
        return None

    def create_issue(
        self,
        type: IssueType,
        title: str,
        priority: IssuePriority = IssuePriority.MEDIUM,
        labels: list[str] | None = None,
        milestone: str | None = None,
        source: str | None = None,
        legacy_id: str | None = None,
    ) -> Issue:
        """Create a new issue.

        Generates unique ID, creates markdown file with front matter and template.

        Args:
            type: Issue type (BUG, FEAT, etc.)
            title: Issue title
            priority: Issue priority. Defaults to MEDIUM.
            labels: List of labels/tags. Defaults to empty list.
            milestone: Target milestone. Defaults to None.
            source: Source file path. Defaults to None.
            legacy_id: Legacy issue ID for migration. Defaults to None.

        Returns:
            Created Issue object

        Raises:
            ValueError: If wt_id cannot be determined
        """
        config = load_config()
        wt_id = get_worktree_id(config)

        if not wt_id:
            raise ValueError(
                "Cannot determine worktree ID. "
                "Please ensure current directory is mapped in config."
            )

        issue_id = generate_id(type, wt_id)

        now = datetime.now()
        date_str = now.strftime("%Y-%m-%d")

        template = get_template_for_type(type)
        body = template.format(date=date_str)

        relative_source = source
        if source:
            source_path = Path(source)
            if source_path.is_absolute():
                try:
                    relative_source = str(source_path.relative_to(Path.cwd()))
                except ValueError:
                    relative_source = source

        issue = Issue(
            id=issue_id,
            title=title,
            type=type,
            status=IssueStatus.TODO,
            priority=priority,
            labels=labels or [],
            milestone=milestone,
            created_at=now,
            updated_at=now,
            source=relative_source,
            legacy_id=legacy_id,
            body=body,
        )

        self.save_issue(issue)

        logger.info(f"Created issue: {issue_id} - {title}")
        return issue

    def load_issue(self, id: str) -> Issue:
        """Load an issue by ID.

        Args:
            id: Issue ID to load

        Returns:
            Issue object

        Raises:
            FileNotFoundError: If issue file not found
            ValueError: If issue file format is invalid
        """
        file_path = self._find_issue_file(id)

        if not file_path:
            raise FileNotFoundError(f"Issue not found: {id}")

        try:
            content = file_path.read_text(encoding="utf-8")
            relative_path = str(file_path.relative_to(self.issues_dir))
            return markdown_to_issue(content, relative_path)
        except OSError as e:
            logger.error(f"Failed to read issue file {file_path}: {e}")
            raise

    def save_issue(self, issue: Issue) -> None:
        """Save an issue to file.

        Args:
            issue: Issue object to save

        Raises:
            OSError: If file cannot be written
        """
        status_dir = self._get_status_dir(issue.status)
        slug = generate_slug(issue.title)
        filename = f"{issue.id}-{slug}.md"
        file_path = status_dir / filename

        issue.source = str(file_path.relative_to(self.issues_dir))

        content = issue_to_markdown(issue)

        try:
            file_path.write_text(content, encoding="utf-8")
            logger.debug(f"Saved issue to {file_path}")
        except OSError as e:
            logger.error(f"Failed to save issue to {file_path}: {e}")
            raise

    def list_issues(
        self,
        status: IssueStatus | None = None,
        type: IssueType | None = None,
        priority: IssuePriority | None = None,
        labels: list[str] | None = None,
        all: bool = False,
    ) -> list[Issue]:
        """List issues with optional filters.

        Args:
            status: Filter by status. Defaults to None (all statuses).
            type: Filter by type. Defaults to None.
            priority: Filter by priority. Defaults to None.
            labels: Filter by labels (AND logic). Defaults to None.
            all: If True, search all directories. If False, only active.

        Returns:
            List of matching Issue objects
        """
        issues: list[Issue] = []

        directories = [self.active_dir]
        if all:
            directories = [
                self.active_dir,
                self.completed_dir,
                self.cancelled_dir,
                self.deferred_dir,
            ]
        elif status:
            directories = [self._get_status_dir(status)]

        for directory in directories:
            if not directory.exists():
                continue

            for file_path in directory.glob("*.md"):
                if file_path.name.startswith("."):
                    continue

                try:
                    content = file_path.read_text(encoding="utf-8")
                    relative_path = str(file_path.relative_to(self.issues_dir))
                    issue = markdown_to_issue(content, relative_path)

                    if status and issue.status != status:
                        continue
                    if type and issue.type != type:
                        continue
                    if priority and issue.priority != priority:
                        continue
                    if labels and not all(label in issue.labels for label in labels):
                        continue

                    issues.append(issue)
                except (ValueError, OSError) as e:
                    logger.warning(f"Failed to parse issue file {file_path}: {e}")
                    continue

        issues.sort(key=lambda i: i.created_at, reverse=True)
        return issues

    def update_issue(self, id: str, **kwargs: Any) -> Issue:
        """Update an issue's properties.

        Args:
            id: Issue ID to update
            **kwargs: Properties to update (title, status, priority, etc.)

        Returns:
            Updated Issue object

        Raises:
            FileNotFoundError: If issue not found
        """
        issue = self.load_issue(id)

        old_file_path = self._find_issue_file(id)

        for key, value in kwargs.items():
            if hasattr(issue, key):
                setattr(issue, key, value)

        issue.updated_at = datetime.now()

        if "title" in kwargs and old_file_path:
            new_slug = generate_slug(issue.title)
            new_filename = f"{issue.id}-{new_slug}.md"
            new_file_path = self._get_status_dir(issue.status) / new_filename

            if old_file_path != new_file_path:
                self.save_issue(issue)
                try:
                    old_file_path.unlink()
                    logger.debug(f"Removed old issue file: {old_file_path}")
                except OSError as e:
                    logger.warning(f"Failed to remove old file {old_file_path}: {e}")
            else:
                self.save_issue(issue)
        else:
            self.save_issue(issue)

        logger.info(f"Updated issue: {id}")
        return issue

    def move_issue(self, id: str, new_status: IssueStatus) -> Issue:
        """Move an issue to a new status.

        Args:
            id: Issue ID to move
            new_status: New status for the issue

        Returns:
            Updated Issue object

        Raises:
            FileNotFoundError: If issue not found
        """
        issue = self.load_issue(id)
        old_status = issue.status

        if old_status == new_status:
            logger.debug(f"Issue {id} already in status {new_status}")
            return issue

        old_file_path = self._find_issue_file(id)

        issue.status = new_status
        issue.updated_at = datetime.now()

        self.save_issue(issue)

        if old_file_path and old_file_path.exists():
            try:
                old_file_path.unlink()
                logger.debug(f"Removed old issue file: {old_file_path}")
            except OSError as e:
                logger.warning(f"Failed to remove old file {old_file_path}: {e}")

        logger.info(f"Moved issue {id} from {old_status} to {new_status}")
        return issue

    def validate_transition(self, current: IssueStatus, target: IssueStatus) -> bool:
        """Check if a status transition is valid.

        Args:
            current: Current status
            target: Target status

        Returns:
            True if transition is allowed, False otherwise
        """
        allowed = STATUS_TRANSITIONS.get(current, [])
        return target in allowed

    def get_allowed_transitions(self, current: IssueStatus) -> list[IssueStatus]:
        """Get list of allowed target statuses from current status.

        Args:
            current: Current status

        Returns:
            List of allowed target statuses
        """
        return STATUS_TRANSITIONS.get(current, [])

    def transition_issue(self, id: str, target: IssueStatus) -> Issue:
        """Transition an issue to a new status with validation.

        Args:
            id: Issue ID to transition
            target: Target status

        Returns:
            Updated Issue object

        Raises:
            FileNotFoundError: If issue not found
            InvalidTransitionError: If transition is not allowed
        """
        issue = self.load_issue(id)
        current = issue.status

        if current == target:
            logger.debug(f"Issue {id} already in status {target}")
            return issue

        if not self.validate_transition(current, target):
            allowed = self.get_allowed_transitions(current)
            raise InvalidTransitionError(current, target, allowed)

        old_file_path = self._find_issue_file(id)

        now = datetime.now()
        issue.status = target
        issue.updated_at = now

        if target == IssueStatus.DONE:
            target_dir = self._get_status_dir(target, for_date=now)
            target_dir.mkdir(parents=True, exist_ok=True)
            slug = generate_slug(issue.title)
            new_filename = f"{issue.id}-{slug}.md"
            new_file_path = target_dir / new_filename
            issue.source = str(new_file_path.relative_to(self.issues_dir))
            content = issue_to_markdown(issue)
            new_file_path.write_text(content, encoding="utf-8")
            logger.debug(f"Saved issue to {new_file_path}")
        else:
            self.save_issue(issue)

        if old_file_path and old_file_path.exists():
            try:
                old_file_path.unlink()
                logger.debug(f"Removed old issue file: {old_file_path}")
            except OSError as e:
                logger.warning(f"Failed to remove old file {old_file_path}: {e}")

        logger.info(f"Transitioned issue {id} from {current} to {target}")
        return issue
