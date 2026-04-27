"""Data models for issue management.

Defines Pydantic models for issue types, statuses, priorities, and configurations.
"""

from datetime import datetime
from enum import Enum
from typing import Any

from pydantic import BaseModel, Field, field_validator


class IssueType(str, Enum):
    """Issue type enumeration.

    Attributes:
        BUG: Bug report or fix
        FEAT: New feature request or implementation
        RF: Refactoring task
        OPT: Optimization or performance improvement
        INV: Investigation or research task
        TEST: Testing-related task
    """

    BUG = "BUG"
    FEAT = "FEAT"
    RF = "RF"
    OPT = "OPT"
    INV = "INV"
    TEST = "TEST"


class IssueStatus(str, Enum):
    """Issue status enumeration.

    Attributes:
        todo: Not yet started
        in_progress: Currently being worked on
        review: Ready for review
        done: Completed
        deferred: Postponed
        cancelled: Cancelled
    """

    TODO = "todo"
    IN_PROGRESS = "in_progress"
    REVIEW = "review"
    DONE = "done"
    DEFERRED = "deferred"
    CANCELLED = "cancelled"


class IssuePriority(str, Enum):
    """Issue priority enumeration.

    Attributes:
        high: High priority, urgent
        medium: Medium priority, normal
        low: Low priority, can wait
    """

    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class WorktreeMapping(BaseModel):
    """Mapping between worktree ID and path.

    Attributes:
        wt_id: Worktree identifier (e.g., 'wt1', 'wt2')
        path: Absolute path to the worktree directory
        branch: Git branch name for this worktree
    """

    wt_id: str = Field(..., description="Worktree identifier")
    path: str = Field(..., description="Absolute path to worktree directory")
    branch: str | None = Field(None, description="Git branch name")


class SummaryConfig(BaseModel):
    """Configuration for issue summary generation.

    Attributes:
        auto_generate: Whether to auto-generate summary on issue changes
        output_file: Output file name for summary
        max_length: Maximum characters for summary
        include_labels: Whether to include labels in summary
        include_milestone: Whether to include milestone in summary
    """

    auto_generate: bool = Field(
        default=False, description="Auto-generate summary on issue changes"
    )
    output_file: str = Field(default="_summary.md", description="Output file name")
    max_length: int = Field(default=80, description="Maximum summary length")
    include_labels: bool = Field(default=True, description="Include labels in summary")
    include_milestone: bool = Field(
        default=True, description="Include milestone in summary"
    )


class IssueConfig(BaseModel):
    """Root configuration for issue management.

    The config file format is:
        worktree_mapping: {path: wt_id, ...}  # path -> wt_id mapping
        worktree_names: {wt_id: name, ...}    # human-readable names
        summary: {auto_generate, output_file, ...}
        status_flow: [todo, in_progress, ...]  # list of valid statuses

    Attributes:
        version: Config file version
        worktree_mapping: Dict mapping path to wt_id (as in config file)
        worktree_names: Human-readable names for worktrees
        summary: Summary generation configuration
        status_flow: List of valid statuses
    """

    version: str = Field(default="1.0", description="Config file version")
    worktree_mapping: dict[str, str] = Field(
        default_factory=dict,
        description="Path to worktree ID mapping (path -> wt_id)",
    )
    worktree_names: dict[str, str] = Field(
        default_factory=dict, description="Human-readable worktree names"
    )
    summary: SummaryConfig = Field(
        default_factory=SummaryConfig, description="Summary configuration"
    )
    status_flow: list[str] = Field(
        default_factory=lambda: [
            "todo",
            "in_progress",
            "review",
            "done",
            "deferred",
            "cancelled",
        ],
        description="List of valid statuses",
    )

    @field_validator("worktree_mapping", mode="before")
    @classmethod
    def validate_worktree_mapping(cls, v: Any) -> dict[str, str]:
        """Validate and normalize worktree_mapping.

        Accepts both:
        - {path: wt_id} format (from config file)
        - {wt_id: WorktreeMapping} format (internal)

        Args:
            v: Input value to validate

        Returns:
            Normalized {path: wt_id} dictionary
        """
        if isinstance(v, dict):
            normalized: dict[str, str] = {}
            for key, value in v.items():
                if isinstance(value, str):
                    normalized[key] = value
                elif isinstance(value, dict):
                    if "wt_id" in value:
                        normalized[key] = value["wt_id"]
                    elif "path" in value:
                        normalized[value["path"]] = key
            return normalized
        return {}

    @field_validator("status_flow", mode="before")
    @classmethod
    def validate_status_flow(cls, v: Any) -> list[str]:
        """Validate and normalize status_flow.

        Accepts both:
        - List of status strings
        - StatusFlow-like dict with allowed_transitions

        Args:
            v: Input value to validate

        Returns:
            List of valid status strings
        """
        if isinstance(v, list):
            return v
        if isinstance(v, dict) and "allowed_transitions" in v:
            return list(v["allowed_transitions"].keys())
        return [
            "todo",
            "in_progress",
            "review",
            "done",
            "deferred",
            "cancelled",
        ]

    def get_wt_id_by_path(self, path: str) -> str | None:
        """Get worktree ID by path.

        Args:
            path: Path to look up

        Returns:
            Worktree ID if found, None otherwise
        """
        return self.worktree_mapping.get(path)

    def get_path_by_wt_id(self, wt_id: str) -> str | None:
        """Get path by worktree ID.

        Args:
            wt_id: Worktree ID to look up

        Returns:
            Path if found, None otherwise
        """
        for path, wid in self.worktree_mapping.items():
            if wid == wt_id:
                return path
        return None


class Issue(BaseModel):
    """Issue data model.

    Attributes:
        id: Unique issue identifier (format: <TYPE>-<YYYYMMDD>-<SEQ>-<WTID>)
        title: Issue title
        type: Issue type (BUG, FEAT, etc.)
        status: Current status
        priority: Issue priority
        labels: List of labels/tags
        assignee: Assigned person (optional)
        milestone: Target milestone (optional)
        created_at: Creation timestamp
        updated_at: Last update timestamp
        source: Source file path (relative to .issues/)
        legacy_id: Legacy issue ID for migration (optional)
        body: Issue body content (markdown)
    """

    id: str = Field(..., description="Unique issue identifier")
    title: str = Field(..., description="Issue title")
    type: IssueType = Field(..., description="Issue type")
    status: IssueStatus = Field(default=IssueStatus.TODO, description="Current status")
    priority: IssuePriority = Field(
        default=IssuePriority.MEDIUM, description="Issue priority"
    )
    labels: list[str] = Field(default_factory=list, description="Labels/tags")
    assignee: str | None = Field(None, description="Assigned person")
    milestone: str | None = Field(None, description="Target milestone")
    created_at: datetime = Field(
        default_factory=datetime.now, description="Creation timestamp"
    )
    updated_at: datetime = Field(
        default_factory=datetime.now, description="Last update timestamp"
    )
    source: str | None = Field(None, description="Source file path")
    legacy_id: str | None = Field(None, description="Legacy issue ID")
    body: str = Field(default="", description="Issue body content")
