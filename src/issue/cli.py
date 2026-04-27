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


if __name__ == "__main__":
    cli()
