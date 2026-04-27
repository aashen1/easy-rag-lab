"""CLI entry point for issue management.

Usage:
    pixi run issue --help
    pixi run issue version
"""

import sys

import click
from loguru import logger


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


if __name__ == "__main__":
    cli()
