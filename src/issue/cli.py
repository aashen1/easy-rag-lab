"""CLI entry point for issue management.

Usage:
    pixi run issue --help
    pixi run issue version
"""

from __future__ import annotations

import sys
from typing import TYPE_CHECKING

import click
from loguru import logger

if TYPE_CHECKING:
    from pathlib import Path

    from src.issue.models import IssueStatus


def _setup_cli_logger(level: str = "INFO") -> None:
    """Setup logger for CLI with simple console output.

    Args:
        level: Log level (DEBUG, INFO, WARNING, ERROR)
    """
    logger.remove()
    logger.add(
        sink=lambda msg: sys.stderr.write(msg),
        format="<level>{level: <8}</level> | <level>{message}</level>",
        level=level,
        colorize=True,
    )


@click.group()
@click.option("-v", "--verbose", is_flag=True, help="Enable verbose logging")
@click.pass_context
def cli(ctx: click.Context, verbose: bool) -> None:
    """Issue management CLI for worktree-based issue tracking.

    Manage issues across multiple git worktrees with automatic ID generation
    and status tracking.
    """
    ctx.ensure_object(dict)
    ctx.obj["verbose"] = verbose

    if verbose:
        _setup_cli_logger(level="DEBUG")
        logger.debug("Verbose mode enabled")
    else:
        _setup_cli_logger(level="WARNING")


@cli.command()
def version() -> None:
    """Show version information."""
    click.echo("Issue CLI v0.1.0")
    click.echo("Issue management system ready")


@cli.command()
@click.pass_context
def status(ctx: click.Context) -> None:
    """Show current issue system status."""
    from src.issue.config import get_worktree_id, load_config

    config = load_config()
    wt_id = get_worktree_id(config)

    click.echo("Issue System Status:")
    click.echo(f"  Config version: {config.version}")
    click.echo(f"  Registered worktrees: {len(config.worktree_mapping)}")

    if wt_id:
        click.echo(f"  Current worktree: {wt_id}")
        if wt_id in config.worktree_names:
            click.echo(f"  Worktree name: {config.worktree_names[wt_id]}")
    else:
        click.echo("  Current worktree: (not detected)")


@cli.group()
def worktree() -> None:
    """Manage worktree mappings.

    Commands for adding, removing, and listing worktree path mappings.
    """
    pass


@worktree.command()
@click.pass_context
def show(ctx: click.Context) -> None:
    """Show current worktree information.

    Automatically detects the current directory and displays matching
    worktree ID and name. If not mapped, suggests adding a mapping.
    """
    from pathlib import Path

    from src.issue.config import get_worktree_id, load_config

    config = load_config()
    wt_id = get_worktree_id(config)
    cwd = Path.cwd().resolve()

    click.echo(f"Current path: {cwd}")

    if wt_id:
        click.echo(f"Worktree ID: {wt_id}")
        if wt_id in config.worktree_names:
            click.echo(f"Name: {config.worktree_names[wt_id]}")
        else:
            click.echo("Name: (not set)")
    else:
        click.echo("Worktree ID: (not mapped)")
        click.echo("\nThis path is not mapped to any worktree.")
        click.echo(
            "Use 'pixi run issue worktree add <path_key> <wt_id>' to add a mapping."
        )


@worktree.command()
@click.argument("path_key")
@click.argument("wt_id")
@click.pass_context
def add(ctx: click.Context, path_key: str, wt_id: str) -> None:
    """Add a worktree mapping.

    PATH_KEY is a key part of the path (e.g., 'w1-easy-rag-feature-x').
    WT_ID is a short identifier (e.g., 'wt2').
    """
    from src.issue.config import load_config, save_config

    config = load_config()

    if path_key in config.worktree_mapping:
        click.echo(
            f"Error: path_key '{path_key}' already mapped to '{config.worktree_mapping[path_key]}'"
        )
        return

    for existing_path, existing_id in config.worktree_mapping.items():
        if existing_id == wt_id:
            click.echo(f"Error: wt_id '{wt_id}' already used by path '{existing_path}'")
            return

    config.worktree_mapping[path_key] = wt_id
    save_config(config)

    click.echo(f"Added mapping: {path_key} -> {wt_id}")


@worktree.command()
@click.argument("wt_id")
@click.pass_context
def remove(ctx: click.Context, wt_id: str) -> None:
    """Remove a worktree mapping by WT_ID."""
    from src.issue.config import load_config, save_config

    config = load_config()

    path_to_remove = None
    for path, wid in config.worktree_mapping.items():
        if wid == wt_id:
            path_to_remove = path
            break

    if path_to_remove is None:
        click.echo(f"Error: wt_id '{wt_id}' not found in mappings")
        return

    del config.worktree_mapping[path_to_remove]

    if wt_id in config.worktree_names:
        del config.worktree_names[wt_id]

    save_config(config)
    click.echo(f"Removed mapping: {path_to_remove} -> {wt_id}")


@worktree.command("list")
@click.pass_context
def list_mappings(ctx: click.Context) -> None:
    """List all worktree mappings in table format."""
    from src.issue.config import load_config

    config = load_config()

    if not config.worktree_mapping:
        click.echo("No worktree mappings configured.")
        return

    header_path = "PATH_KEY"
    header_wt = "WT_ID"
    header_name = "NAME"

    max_path_len = max(len(str(p)) for p in config.worktree_mapping)
    max_path_len = max(max_path_len, len(header_path))

    max_wt_len = max(len(wid) for wid in config.worktree_mapping.values())
    max_wt_len = max(max_wt_len, len(header_wt))

    max_name_len = len(header_name)
    for wid in config.worktree_mapping.values():
        name = config.worktree_names.get(wid, "-")
        max_name_len = max(max_name_len, len(name))

    click.echo(
        f"{header_path:<{max_path_len}}  {header_wt:<{max_wt_len}}  {header_name}"
    )
    click.echo("-" * (max_path_len + max_wt_len + max_name_len + 4))

    for path, wt_id in config.worktree_mapping.items():
        name = config.worktree_names.get(wt_id, "-")
        click.echo(f"{path:<{max_path_len}}  {wt_id:<{max_wt_len}}  {name}")


@worktree.command()
@click.argument("wt_id")
@click.argument("name")
@click.pass_context
def name(ctx: click.Context, wt_id: str, name: str) -> None:
    """Set a human-readable name for a worktree.

    WT_ID is the worktree identifier (e.g., 'wt1').
    NAME is a human-readable name (e.g., 'main-dev').
    """
    from src.issue.config import load_config, save_config

    config = load_config()

    wt_exists = any(wid == wt_id for wid in config.worktree_mapping.values())
    if not wt_exists:
        click.echo(f"Error: wt_id '{wt_id}' not found in mappings")
        return

    config.worktree_names[wt_id] = name
    save_config(config)

    click.echo(f"Set name for {wt_id}: {name}")


@cli.command()
@click.option(
    "--type",
    "-t",
    "issue_type",
    type=click.Choice(
        ["bug", "feat", "rf", "opt", "inv", "test"], case_sensitive=False
    ),
    required=True,
    help="Issue type (bug/feat/rf/opt/inv/test)",
)
@click.option("--title", "-T", required=True, help="Issue title")
@click.option(
    "--priority",
    "-p",
    type=click.Choice(["high", "medium", "low"], case_sensitive=False),
    default="medium",
    help="Issue priority (default: medium)",
)
@click.option("--labels", "-l", help="Comma-separated labels")
@click.option("--milestone", "-m", help="Target milestone")
@click.option("--source", "-s", help="Source file path")
@click.pass_context
def create(
    ctx: click.Context,
    issue_type: str,
    title: str,
    priority: str,
    labels: str | None,
    milestone: str | None,
    source: str | None,
) -> None:
    """Create a new issue.

    Creates an issue file in .issues/active/ with auto-generated ID and template.

    Example:
        pixi run issue create --type bug --title "Fix login error"
        pixi run issue create -t feat -T "Add dark mode" -p high -l "ui,urgent"
    """
    from pathlib import Path

    from src.issue.manager import IssueManager
    from src.issue.models import IssuePriority, IssueType

    type_map = {
        "bug": IssueType.BUG,
        "feat": IssueType.FEAT,
        "rf": IssueType.RF,
        "opt": IssueType.OPT,
        "inv": IssueType.INV,
        "test": IssueType.TEST,
    }

    priority_map = {
        "high": IssuePriority.HIGH,
        "medium": IssuePriority.MEDIUM,
        "low": IssuePriority.LOW,
    }

    parsed_type = type_map[issue_type.lower()]
    parsed_priority = priority_map[priority.lower()]

    parsed_labels: list[str] = []
    if labels:
        parsed_labels = [label.strip() for label in labels.split(",") if label.strip()]

    manager = IssueManager(issues_dir=Path(".issues"))

    try:
        issue = manager.create_issue(
            type=parsed_type,
            title=title,
            priority=parsed_priority,
            labels=parsed_labels,
            milestone=milestone,
            source=source,
        )

        click.echo(click.style("✓ Issue created successfully!", fg="green", bold=True))
        click.echo(f"  ID: {issue.id}")
        click.echo(f"  Title: {issue.title}")
        click.echo(f"  Type: {issue.type.value}")
        click.echo(f"  Priority: {issue.priority.value}")
        click.echo(f"  Status: {issue.status.value}")
        if issue.labels:
            click.echo(f"  Labels: {', '.join(issue.labels)}")
        if issue.milestone:
            click.echo(f"  Milestone: {issue.milestone}")
        click.echo(
            f"  File: .issues/active/{issue.id}-{title.lower().replace(' ', '-')[:30]}.md"
        )

    except ValueError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1) from None
    except OSError as e:
        click.echo(click.style(f"Failed to create issue: {e}", fg="red"), err=True)
        raise SystemExit(1) from None


@cli.command("show")
@click.argument("issue_id")
@click.pass_context
def show_issue(ctx: click.Context, issue_id: str) -> None:
    """Show details of a specific issue.

    ISSUE_ID can be a full ID (e.g., BUG-20260428-001-wt1) or partial ID
    (e.g., BUG-20260428 or 001-wt1). Displays full YAML front matter and body.

    Example:
        pixi run issue show BUG-20260428-001-wt1
        pixi run issue show BUG-20260428
        pixi run issue show 001-wt1
    """
    from pathlib import Path

    from src.issue.manager import IssueManager

    manager = IssueManager(issues_dir=Path(".issues"))

    try:
        issue = manager.load_issue(issue_id)

        click.echo(click.style(f"Issue: {issue.id}", fg="cyan", bold=True))
        click.echo(click.style("=" * 60, fg="cyan"))
        click.echo()
        click.echo(click.style("YAML Front Matter:", fg="yellow", bold=True))
        click.echo(click.style("---", fg="yellow"))
        click.echo(f"id: {issue.id}")
        click.echo(f"title: {issue.title}")
        click.echo(f"type: {issue.type.value}")
        click.echo(f"status: {issue.status.value}")
        click.echo(f"priority: {issue.priority.value}")
        if issue.labels:
            click.echo(f"labels: {issue.labels}")
        else:
            click.echo("labels: []")
        click.echo(f"assignee: {issue.assignee or '-'}")
        click.echo(f"milestone: {issue.milestone or '-'}")
        click.echo(f"created_at: {issue.created_at.isoformat()}")
        click.echo(f"updated_at: {issue.updated_at.isoformat()}")
        click.echo(f"source: {issue.source or '-'}")
        click.echo(f"legacy_id: {issue.legacy_id or '-'}")
        click.echo(click.style("---", fg="yellow"))
        click.echo()
        click.echo(click.style("Body:", fg="yellow", bold=True))
        click.echo(issue.body if issue.body else "(empty)")

    except FileNotFoundError:
        click.echo(
            click.style(f"Error: Issue '{issue_id}' not found", fg="red"), err=True
        )
        raise SystemExit(1) from None
    except ValueError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1) from None


@cli.command("list")
@click.option(
    "--status",
    "-s",
    "status_filter",
    type=click.Choice(
        ["todo", "in_progress", "review", "done", "deferred", "cancelled"],
        case_sensitive=False,
    ),
    help="Filter by status",
)
@click.option(
    "--type",
    "-t",
    "type_filter",
    type=click.Choice(
        ["bug", "feat", "rf", "opt", "inv", "test"], case_sensitive=False
    ),
    help="Filter by type",
)
@click.option(
    "--priority",
    "-p",
    "priority_filter",
    type=click.Choice(["high", "medium", "low"], case_sensitive=False),
    help="Filter by priority",
)
@click.option(
    "--labels",
    "-l",
    "labels_filter",
    help="Filter by labels (comma-separated, AND logic)",
)
@click.option(
    "--all",
    "-a",
    "all_dirs",
    is_flag=True,
    help="Include issues from all directories (active, completed, deferred, cancelled)",
)
@click.pass_context
def list_issues(
    ctx: click.Context,
    status_filter: str | None,
    type_filter: str | None,
    priority_filter: str | None,
    labels_filter: str | None,
    all_dirs: bool,
) -> None:
    """List issues in table format.

    By default, shows only active issues. Use --all to include completed,
    deferred, and cancelled issues.

    Example:
        pixi run issue list
        pixi run issue list --all
        pixi run issue list --status in_progress
        pixi run issue list --type bug --priority high
        pixi run issue list --labels "ui,urgent"
    """
    from pathlib import Path

    from src.issue.manager import IssueManager
    from src.issue.models import IssuePriority, IssueStatus, IssueType

    type_map = {
        "bug": IssueType.BUG,
        "feat": IssueType.FEAT,
        "rf": IssueType.RF,
        "opt": IssueType.OPT,
        "inv": IssueType.INV,
        "test": IssueType.TEST,
    }

    priority_map = {
        "high": IssuePriority.HIGH,
        "medium": IssuePriority.MEDIUM,
        "low": IssuePriority.LOW,
    }

    status_map = {
        "todo": IssueStatus.TODO,
        "in_progress": IssueStatus.IN_PROGRESS,
        "review": IssueStatus.REVIEW,
        "done": IssueStatus.DONE,
        "deferred": IssueStatus.DEFERRED,
        "cancelled": IssueStatus.CANCELLED,
    }

    parsed_status = status_map[status_filter.lower()] if status_filter else None
    parsed_type = type_map[type_filter.lower()] if type_filter else None
    parsed_priority = priority_map[priority_filter.lower()] if priority_filter else None

    parsed_labels: list[str] | None = None
    if labels_filter:
        parsed_labels = [
            label.strip() for label in labels_filter.split(",") if label.strip()
        ]

    manager = IssueManager(issues_dir=Path(".issues"))

    issues = manager.list_issues(
        status=parsed_status,
        type=parsed_type,
        priority=parsed_priority,
        labels=parsed_labels,
        all=all_dirs,
    )

    if not issues:
        click.echo("No issues found.")
        return

    col_id_width = 22
    col_type_width = 6
    col_status_width = 12
    col_priority_width = 8
    col_title_max = 40

    header = (
        f"{'ID':<{col_id_width}}  "
        f"{'Type':<{col_type_width}}  "
        f"{'Status':<{col_status_width}}  "
        f"{'Priority':<{col_priority_width}}  "
        f"Title"
    )
    click.echo(click.style(header, bold=True))
    click.echo(
        "-"
        * (col_id_width + col_type_width + col_status_width + col_priority_width + 42)
    )

    for issue in issues:
        title = issue.title
        if len(title) > col_title_max:
            title = title[: col_title_max - 3] + "..."

        id_str = issue.id
        if len(id_str) > col_id_width:
            id_str = id_str[: col_id_width - 3] + "..."

        status_str = issue.status.value
        priority_str = issue.priority.value
        type_str = issue.type.value

        priority_color = {
            "high": "red",
            "medium": "yellow",
            "low": "green",
        }.get(priority_str, "white")

        status_color = {
            "todo": "white",
            "in_progress": "blue",
            "review": "magenta",
            "done": "green",
            "deferred": "yellow",
            "cancelled": "dim",
        }.get(status_str, "white")

        click.echo(
            f"{id_str:<{col_id_width}}  "
            f"{type_str:<{col_type_width}}  "
            f"{click.style(status_str, fg=status_color):<{col_status_width}}  "
            f"{click.style(priority_str, fg=priority_color):<{col_priority_width}}  "
            f"{title}"
        )

    click.echo()
    click.echo(f"Total: {len(issues)} issue(s)")


@cli.command()
@click.argument("issue_id")
@click.option(
    "--status",
    "-s",
    "new_status",
    type=click.Choice(
        ["todo", "in_progress", "review", "done", "deferred", "cancelled"],
        case_sensitive=False,
    ),
    help="Update status",
)
@click.option(
    "--priority",
    "-p",
    "new_priority",
    type=click.Choice(["high", "medium", "low"], case_sensitive=False),
    help="Update priority",
)
@click.option("--title", "-T", "new_title", help="Update title")
@click.option(
    "--add-label",
    "-a",
    "add_labels",
    multiple=True,
    help="Add label (can be used multiple times)",
)
@click.option(
    "--remove-label",
    "-r",
    "remove_labels",
    multiple=True,
    help="Remove label (can be used multiple times)",
)
@click.pass_context
def update(
    ctx: click.Context,
    issue_id: str,
    new_status: str | None,
    new_priority: str | None,
    new_title: str | None,
    add_labels: tuple[str, ...],
    remove_labels: tuple[str, ...],
) -> None:
    """Update an issue's properties.

    Updates one or more properties of an issue. Automatically updates the
    updated_at timestamp.

    Examples:
        pixi run issue update BUG-001 --status in_progress
        pixi run issue update BUG-001 -p high -T "New title"
        pixi run issue update BUG-001 -a urgent -a backend
        pixi run issue update BUG-001 -r urgent
    """
    from pathlib import Path

    from src.issue.manager import IssueManager
    from src.issue.models import IssuePriority, IssueStatus

    manager = IssueManager(issues_dir=Path(".issues"))

    try:
        issue = manager.load_issue(issue_id)
    except FileNotFoundError:
        click.echo(
            click.style(f"Error: Issue '{issue_id}' not found", fg="red"), err=True
        )
        raise SystemExit(1) from None
    except ValueError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1) from None

    updates: dict = {}

    if new_status:
        status_map = {
            "todo": IssueStatus.TODO,
            "in_progress": IssueStatus.IN_PROGRESS,
            "review": IssueStatus.REVIEW,
            "done": IssueStatus.DONE,
            "deferred": IssueStatus.DEFERRED,
            "cancelled": IssueStatus.CANCELLED,
        }
        updates["status"] = status_map[new_status.lower()]

    if new_priority:
        priority_map = {
            "high": IssuePriority.HIGH,
            "medium": IssuePriority.MEDIUM,
            "low": IssuePriority.LOW,
        }
        updates["priority"] = priority_map[new_priority.lower()]

    if new_title:
        updates["title"] = new_title

    if add_labels or remove_labels:
        current_labels = set(issue.labels)
        current_labels.update(add_labels)
        current_labels.difference_update(remove_labels)
        updates["labels"] = list(current_labels)

    if not updates:
        click.echo(
            "No updates specified. Use --status, --priority, --title, --add-label, or --remove-label."
        )
        return

    updated_issue = manager.update_issue(issue_id, **updates)

    click.echo(click.style("✓ Issue updated successfully!", fg="green", bold=True))
    click.echo(f"  ID: {updated_issue.id}")
    for key in updates:
        if key == "status":
            click.echo(f"  Status: {updated_issue.status.value}")
        elif key == "priority":
            click.echo(f"  Priority: {updated_issue.priority.value}")
        elif key == "title":
            click.echo(f"  Title: {updated_issue.title}")
        elif key == "labels":
            click.echo(
                f"  Labels: {', '.join(updated_issue.labels) if updated_issue.labels else '(none)'}"
            )


@cli.command()
@click.argument("issue_id")
@click.pass_context
def start(ctx: click.Context, issue_id: str) -> None:
    """Start working on an issue (todo → in_progress).

    Transitions an issue from 'todo' to 'in_progress' status.

    Example:
        pixi run issue start BUG-001
    """
    from src.issue.models import IssueStatus

    _transition_issue(ctx, issue_id, IssueStatus.IN_PROGRESS, "start", IssueStatus.TODO)


@cli.command()
@click.argument("issue_id")
@click.pass_context
def review(ctx: click.Context, issue_id: str) -> None:
    """Submit an issue for review (in_progress → review).

    Transitions an issue from 'in_progress' to 'review' status.

    Example:
        pixi run issue review BUG-001
    """
    from src.issue.models import IssueStatus

    _transition_issue(
        ctx, issue_id, IssueStatus.REVIEW, "review", IssueStatus.IN_PROGRESS
    )


@cli.command()
@click.argument("issue_id")
@click.pass_context
def done(ctx: click.Context, issue_id: str) -> None:
    """Mark an issue as done (review → done).

    Transitions an issue from 'review' to 'done' status.
    The issue file is moved to .issues/completed/YYYY-MM/ directory.

    Example:
        pixi run issue done BUG-001
    """
    from src.issue.models import IssueStatus

    _transition_issue(ctx, issue_id, IssueStatus.DONE, "done", IssueStatus.REVIEW)


@cli.command()
@click.argument("issue_id")
@click.pass_context
def defer(ctx: click.Context, issue_id: str) -> None:
    """Defer an issue.

    Moves an issue to .issues/deferred/ directory.
    Allowed from: todo, in_progress, review.

    Example:
        pixi run issue defer BUG-001
    """
    from src.issue.models import IssueStatus

    _transition_issue(ctx, issue_id, IssueStatus.DEFERRED, "defer")


@cli.command("cancel")
@click.argument("issue_id")
@click.pass_context
def cancel_issue(ctx: click.Context, issue_id: str) -> None:
    """Cancel an issue.

    Moves an issue to .issues/cancelled/ directory.
    Allowed from: todo, in_progress, review, deferred.

    Example:
        pixi run issue cancel BUG-001
    """
    from src.issue.models import IssueStatus

    _transition_issue(ctx, issue_id, IssueStatus.CANCELLED, "cancel")


def _transition_issue(
    ctx: click.Context,
    issue_id: str,
    target_status: IssueStatus,
    action_name: str,
    expected_current: IssueStatus | None = None,
) -> None:
    """Helper function to transition an issue with proper error handling.

    Args:
        ctx: Click context
        issue_id: Issue ID to transition
        target_status: Target status
        action_name: Action name for display (e.g., 'start', 'done')
        expected_current: Expected current status for display (optional)
    """
    from pathlib import Path

    from src.issue.manager import InvalidTransitionError, IssueManager
    from src.issue.models import IssueStatus

    manager = IssueManager(issues_dir=Path(".issues"))

    try:
        manager.load_issue(issue_id)
    except FileNotFoundError:
        click.echo(
            click.style(f"Error: Issue '{issue_id}' not found", fg="red"), err=True
        )
        raise SystemExit(1) from None
    except ValueError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1) from None

    try:
        updated_issue = manager.transition_issue(issue_id, target_status)

        click.echo(
            click.style(f"✓ Issue {action_name} successfully!", fg="green", bold=True)
        )
        click.echo(f"  ID: {updated_issue.id}")
        click.echo(f"  Status: {updated_issue.status.value}")

        if target_status == IssueStatus.DONE:
            click.echo(
                f"  Location: .issues/completed/{updated_issue.updated_at.strftime('%Y-%m')}/"
            )

    except InvalidTransitionError as e:
        click.echo(
            click.style(
                f"Error: Cannot {action_name} issue in '{e.current.value}' status.",
                fg="red",
            ),
            err=True,
        )
        if expected_current:
            click.echo(f"  Expected current status: {expected_current.value}")
        click.echo(f"  Current status: {e.current.value}")
        click.echo(f"  Allowed transitions: {[s.value for s in e.allowed]}")
        raise SystemExit(1) from None


@cli.command()
@click.option("--save", "-s", is_flag=True, help="Save summary to .issues/_summary.md")
@click.option(
    "--output",
    "-o",
    "output_file",
    type=click.Path(),
    help="Save summary to specified file",
)
@click.pass_context
def summary(ctx: click.Context, save: bool, output_file: str | None) -> None:
    """Generate issue statistics summary.

    Scans all issues and generates a markdown summary table grouped by
    type and status.

    Examples:
        pixi run issue summary
        pixi run issue summary --save
        pixi run issue summary -o docs/issue-summary.md
    """
    from collections import defaultdict
    from datetime import datetime
    from pathlib import Path

    from src.issue.manager import IssueManager
    from src.issue.models import IssueStatus, IssueType

    manager = IssueManager(issues_dir=Path(".issues"))
    issues = manager.list_issues(all=True)

    type_status_count: dict[IssueType, dict[IssueStatus, int]] = defaultdict(
        lambda: defaultdict(int)
    )
    pending_by_type: dict[IssueType, list] = defaultdict(list)

    for issue in issues:
        type_status_count[issue.type][issue.status] += 1
        if issue.status == IssueStatus.TODO:
            pending_by_type[issue.type].append(issue)

    status_columns = [
        IssueStatus.TODO,
        IssueStatus.IN_PROGRESS,
        IssueStatus.REVIEW,
        IssueStatus.DONE,
        IssueStatus.DEFERRED,
        IssueStatus.CANCELLED,
    ]

    status_headers = {
        IssueStatus.TODO: "待处理",
        IssueStatus.IN_PROGRESS: "进行中",
        IssueStatus.REVIEW: "评审中",
        IssueStatus.DONE: "已完成",
        IssueStatus.DEFERRED: "已延期",
        IssueStatus.CANCELLED: "已取消",
    }

    type_names = {
        IssueType.BUG: "Bug",
        IssueType.FEAT: "Feature",
        IssueType.RF: "Refactor",
        IssueType.OPT: "Optimize",
        IssueType.INV: "Investigate",
        IssueType.TEST: "Test",
    }

    type_order = [
        IssueType.BUG,
        IssueType.FEAT,
        IssueType.RF,
        IssueType.OPT,
        IssueType.INV,
        IssueType.TEST,
    ]

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append("# Issue 统计概览")
    lines.append("")
    lines.append(f"> 生成时间：{now_str}")
    lines.append("")
    lines.append("## 统计概览")
    lines.append("")

    header = "| 类型 | " + " | ".join(status_headers[s] for s in status_columns) + " |"
    lines.append(header)

    separator = "|------|" + "|".join("--------" for _ in status_columns) + "|"
    lines.append(separator)

    for issue_type in type_order:
        if issue_type not in type_status_count:
            continue

        row_parts = [f"| {type_names[issue_type]} "]
        for status in status_columns:
            count = type_status_count[issue_type].get(status, 0)
            row_parts.append(f" {count} |")
        lines.append("".join(row_parts))

    total_row = ["| **总计** "]
    for status in status_columns:
        total = sum(type_status_count[t].get(status, 0) for t in type_status_count)
        total_row.append(f" **{total}** |")
    lines.append("".join(total_row))

    has_pending = any(pending_by_type.values())
    if has_pending:
        lines.append("")
        lines.append("## 待处理 Issue 列表")
        lines.append("")

        for issue_type in type_order:
            pending = pending_by_type.get(issue_type, [])
            if not pending:
                continue

            lines.append(f"### {type_names[issue_type]}")
            lines.append("")
            lines.append("| ID | 标题 | 优先级 | 创建时间 |")
            lines.append("|----|------|--------|----------|")

            for issue in sorted(pending, key=lambda i: i.created_at, reverse=True):
                created_date = issue.created_at.strftime("%Y-%m-%d")
                lines.append(
                    f"| {issue.id} | {issue.title} | {issue.priority.value} | {created_date} |"
                )

            lines.append("")

    content = "\n".join(lines)

    if output_file:
        output_path = Path(output_file)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(content, encoding="utf-8")
        click.echo(click.style(f"✓ Summary saved to {output_file}", fg="green"))
    elif save:
        summary_path = Path(".issues/_summary.md")
        summary_path.parent.mkdir(parents=True, exist_ok=True)
        summary_path.write_text(content, encoding="utf-8")
        click.echo(click.style("✓ Summary saved to .issues/_summary.md", fg="green"))
    else:
        click.echo(content)


def _parse_focused_ids_from_context(context_path: Path) -> list[str]:
    """Parse focused issue IDs from context.md file.

    Args:
        context_path: Path to context.md file

    Returns:
        List of issue IDs that are manually focused
    """
    focused_ids: list[str] = []
    if not context_path.exists():
        return focused_ids

    try:
        content = context_path.read_text(encoding="utf-8")
        for line in content.split("\n"):
            if line.startswith("- [ ]") and ":" in line:
                issue_id_part = line.split(":")[0].replace("- [ ]", "").strip()
                if issue_id_part.startswith("☆ ") or issue_id_part.startswith("★ "):
                    issue_id_part = issue_id_part[2:]
                if issue_id_part:
                    focused_ids.append(issue_id_part)
    except OSError:
        pass

    return focused_ids


@cli.command()
@click.pass_context
def context(ctx: click.Context) -> None:
    """Show current focused issues context.

    Displays issues that are either in_progress or manually focused.
    Generates a concise summary for AI context.

    Example:
        pixi run issue context
    """
    from datetime import datetime
    from pathlib import Path

    from src.issue.manager import IssueManager
    from src.issue.models import IssueStatus

    manager = IssueManager(issues_dir=Path(".issues"))
    context_path = Path(".issues/context.md")

    focused_ids = _parse_focused_ids_from_context(context_path)

    in_progress_issues = manager.list_issues(status=IssueStatus.IN_PROGRESS)

    focused_issues = []
    for issue_id in focused_ids:
        try:
            issue = manager.load_issue(issue_id)
            if issue not in focused_issues and issue not in in_progress_issues:
                focused_issues.append(issue)
        except FileNotFoundError:
            pass

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append("# 当前聚焦 Issue")
    lines.append("")
    lines.append(f"> 更新时间：{now_str}")
    lines.append("")

    if not in_progress_issues and not focused_issues:
        lines.append("暂无进行中的 Issue。")
    else:
        if in_progress_issues:
            lines.append("## 进行中")
            lines.append("")
            for issue in in_progress_issues:
                lines.append(
                    f"- [ ] ★ {issue.id}: {issue.title} ({issue.priority.value})"
                )
            lines.append("")

        if focused_issues:
            lines.append("## 手动聚焦")
            lines.append("")
            for issue in focused_issues:
                lines.append(
                    f"- [ ] ☆ {issue.id}: {issue.title} ({issue.priority.value})"
                )

    content = "\n".join(lines)

    context_path.parent.mkdir(parents=True, exist_ok=True)
    context_path.write_text(content, encoding="utf-8")

    click.echo(content)


@cli.command()
@click.argument("issue_id")
@click.pass_context
def focus(ctx: click.Context, issue_id: str) -> None:
    """Add an issue to the focus list.

    Adds the specified issue to .issues/context.md for AI context tracking.
    The issue will appear in 'pixi run issue context' output.

    Example:
        pixi run issue focus BUG-20260428-001-wt1
    """
    from datetime import datetime
    from pathlib import Path

    from src.issue.manager import IssueManager
    from src.issue.models import IssueStatus

    manager = IssueManager(issues_dir=Path(".issues"))

    try:
        issue = manager.load_issue(issue_id)
    except FileNotFoundError:
        click.echo(
            click.style(f"Error: Issue '{issue_id}' not found", fg="red"), err=True
        )
        raise SystemExit(1) from None
    except ValueError as e:
        click.echo(click.style(f"Error: {e}", fg="red"), err=True)
        raise SystemExit(1) from None

    context_path = Path(".issues/context.md")
    context_path.parent.mkdir(parents=True, exist_ok=True)

    focused_ids = _parse_focused_ids_from_context(context_path)

    if issue.id in focused_ids:
        click.echo(f"Issue {issue.id} is already in focus list.")
        return

    if issue.status == IssueStatus.IN_PROGRESS:
        click.echo(
            f"Issue {issue.id} is already in progress (shown in context automatically)."
        )
        return

    focused_ids.append(issue.id)

    in_progress_issues = manager.list_issues(status=IssueStatus.IN_PROGRESS)

    focused_issues = []
    for fid in focused_ids:
        try:
            fissue = manager.load_issue(fid)
            if fissue not in focused_issues and fissue not in in_progress_issues:
                focused_issues.append(fissue)
        except FileNotFoundError:
            pass

    now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    lines: list[str] = []
    lines.append("# 当前聚焦 Issue")
    lines.append("")
    lines.append(f"> 更新时间：{now_str}")
    lines.append("")

    if in_progress_issues:
        lines.append("## 进行中")
        lines.append("")
        for i in in_progress_issues:
            lines.append(f"- [ ] ★ {i.id}: {i.title} ({i.priority.value})")
        lines.append("")

    if focused_issues:
        lines.append("## 手动聚焦")
        lines.append("")
        for i in focused_issues:
            lines.append(f"- [ ] ☆ {i.id}: {i.title} ({i.priority.value})")

    content = "\n".join(lines)
    context_path.write_text(content, encoding="utf-8")

    click.echo(content)
    click.echo(click.style(f"✓ Issue {issue.id} added to focus list", fg="green"))


@cli.command("unfocus")
@click.argument("issue_id")
@click.pass_context
def unfocus_issue(ctx: click.Context, issue_id: str) -> None:
    """Remove an issue from the focus list.

    Removes the specified issue from .issues/context.md.

    Example:
        pixi run issue unfocus BUG-20260428-001-wt1
    """
    from pathlib import Path

    from src.issue.manager import IssueManager

    manager = IssueManager(issues_dir=Path(".issues"))

    try:
        issue = manager.load_issue(issue_id)
        actual_id = issue.id
    except FileNotFoundError:
        actual_id = issue_id
    except ValueError:
        actual_id = issue_id

    context_path = Path(".issues/context.md")

    if not context_path.exists():
        click.echo("No context file found. Nothing to unfocus.")
        return

    try:
        content = context_path.read_text(encoding="utf-8")
    except OSError as e:
        click.echo(click.style(f"Error reading context file: {e}", fg="red"), err=True)
        raise SystemExit(1) from None

    lines = content.split("\n")
    new_lines: list[str] = []
    removed = False

    for line in lines:
        if line.startswith("- [ ]") and ":" in line:
            issue_id_part = line.split(":")[0].replace("- [ ]", "").strip()
            if issue_id_part.startswith("☆ ") or issue_id_part.startswith("★ "):
                issue_id_part = issue_id_part[2:]

            if actual_id == issue_id_part or issue_id == issue_id_part:
                removed = True
                continue

        new_lines.append(line)

    if not removed:
        click.echo(f"Issue {issue_id} not found in focus list.")
        return

    while new_lines and new_lines[-1] == "":
        new_lines.pop()

    context_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    click.echo(click.style(f"✓ Issue {actual_id} removed from focus list", fg="green"))


@cli.command()
@click.option(
    "--from-backlog",
    "backlog_file",
    type=click.Path(exists=True),
    default="docs/backlog.md",
    help="Path to backlog.md file (default: docs/backlog.md)",
)
@click.option("--dry-run", is_flag=True, help="Print actions without executing")
@click.option("--verify", "verify_only", is_flag=True, help="Verify migration results")
@click.option(
    "--wt-id", default="wt1", help="Worktree ID for new issues (default: wt1)"
)
@click.pass_context
def migrate(
    ctx: click.Context,
    backlog_file: str,
    dry_run: bool,
    verify_only: bool,
    wt_id: str,
) -> None:
    """Migrate issues from backlog.md to issue files.

    Parses the backlog.md file and creates individual issue files
    with new ID format: <TYPE>-<YYYYMMDD>-<SEQ>-<WTID>

    Examples:
        pixi run issue migrate --from-backlog docs/backlog.md
        pixi run issue migrate --dry-run
        pixi run issue migrate --verify
    """
    from pathlib import Path

    from src.issue.migrate import BacklogMigrator, run_verification

    backlog_path = Path(backlog_file)
    issues_dir = Path(".issues")

    if not backlog_path.exists():
        click.echo(
            click.style(f"Error: Backlog file not found: {backlog_path}", fg="red"),
            err=True,
        )
        raise SystemExit(1)

    if verify_only:
        click.echo(click.style("Verifying migration results...", fg="cyan", bold=True))
        click.echo()

        results = run_verification(
            backlog_path=backlog_path,
            issues_dir=issues_dir,
            wt_id=wt_id,
        )

        click.echo(f"Backlog path: {results['backlog_path']}")
        click.echo(f"Issues directory: {results['issues_dir']}")
        click.echo(f"Parsed from backlog: {results['parsed_count']}")
        click.echo(f"Created issues: {results['created_count']}")
        click.echo(f"Errors: {results['error_count']}")
        click.echo()

        if results["by_type"]:
            click.echo("By type:")
            for type_name, count in sorted(results["by_type"].items()):
                click.echo(f"  {type_name}: {count}")
            click.echo()

        if results["by_status"]:
            click.echo("By status:")
            for status_name, count in sorted(results["by_status"].items()):
                click.echo(f"  {status_name}: {count}")
            click.echo()

        if results["issues"]:
            click.echo(f"Found {len(results['issues'])} issue files:")
            for issue_info in results["issues"][:10]:
                legacy = issue_info.get("legacy_id", "-")
                click.echo(
                    f"  {issue_info['id']} (from {legacy}): {issue_info['title'][:50]}"
                )
            if len(results["issues"]) > 10:
                click.echo(f"  ... and {len(results['issues']) - 10} more")

        return

    click.echo(click.style("Migrating issues from backlog.md...", fg="cyan", bold=True))
    click.echo(f"  Source: {backlog_path}")
    click.echo(f"  Target: {issues_dir}")
    click.echo(f"  Worktree ID: {wt_id}")
    if dry_run:
        click.echo(
            click.style("  Mode: DRY-RUN (no files will be created)", fg="yellow")
        )
    click.echo()

    migrator = BacklogMigrator(
        backlog_path=backlog_path,
        issues_dir=issues_dir,
        wt_id=wt_id,
        dry_run=dry_run,
    )

    stats = migrator.migrate()

    click.echo(click.style("Migration completed!", fg="green", bold=True))
    click.echo()
    click.echo("Statistics:")
    click.echo(f"  Total parsed: {stats.total_parsed}")
    click.echo(f"  Created: {stats.created}")
    click.echo(f"  Skipped: {stats.skipped}")
    click.echo(f"  Errors: {stats.errors}")
    click.echo()

    if stats.by_type:
        click.echo("By type:")
        for type_name, count in sorted(stats.by_type.items()):
            click.echo(f"  {type_name}: {count}")
        click.echo()

    if stats.by_status:
        click.echo("By status:")
        for status_name, count in sorted(stats.by_status.items()):
            click.echo(f"  {status_name}: {count}")

    if dry_run:
        click.echo()
        click.echo(
            click.style(
                "This was a dry-run. Run without --dry-run to create files.",
                fg="yellow",
            )
        )


if __name__ == "__main__":
    cli()
