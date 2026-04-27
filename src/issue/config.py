"""Configuration management for issue system.

Handles loading/saving config and automatic worktree ID detection.
"""

from pathlib import Path

import yaml
from loguru import logger

from src.issue.models import IssueConfig

DEFAULT_CONFIG_PATH = Path(".issues/config.yml")


def load_config(config_path: Path | None = None) -> IssueConfig:
    """Load issue configuration from YAML file.

    Args:
        config_path: Path to config file. Defaults to .issues/config.yml

    Returns:
        IssueConfig: Loaded configuration object

    Raises:
        FileNotFoundError: If config file does not exist
        yaml.YAMLError: If config file is invalid YAML
    """
    path = config_path or DEFAULT_CONFIG_PATH

    if not path.exists():
        logger.warning(f"Config file not found: {path}, creating default config")
        return IssueConfig()

    try:
        with open(path, encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        logger.debug(f"Loaded config from {path}")
        return IssueConfig(**data)
    except yaml.YAMLError as e:
        logger.error(f"Invalid YAML in config file {path}: {e}")
        raise


def save_config(config: IssueConfig, config_path: Path | None = None) -> None:
    """Save issue configuration to YAML file.

    Args:
        config: Configuration object to save
        config_path: Path to config file. Defaults to .issues/config.yml

    Raises:
        OSError: If file cannot be written
    """
    path = config_path or DEFAULT_CONFIG_PATH
    path.parent.mkdir(parents=True, exist_ok=True)

    try:
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(
                config.model_dump(mode="python"),
                f,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
        logger.debug(f"Saved config to {path}")
    except OSError as e:
        logger.error(f"Failed to save config to {path}: {e}")
        raise


def get_worktree_id(config: IssueConfig | None = None) -> str | None:
    """Detect worktree ID based on current working directory.

    Matches the current directory path against configured worktree mappings.
    Supports both absolute paths and path keys (substring matching).
    Returns the wt_id if a match is found, None otherwise.

    Args:
        config: Configuration object. If None, loads from default path.

    Returns:
        Optional[str]: Worktree ID if detected, None otherwise
    """
    cfg = config or load_config()
    cwd = Path.cwd().resolve()
    cwd_str = str(cwd)

    for path_str, wt_id in cfg.worktree_mapping.items():
        if Path(path_str).is_absolute():
            mapping_path = Path(path_str).resolve()
            try:
                cwd.relative_to(mapping_path)
                logger.debug(f"Detected worktree ID: {wt_id} (path: {mapping_path})")
                return wt_id
            except ValueError:
                continue
        else:
            if path_str in cwd_str:
                logger.debug(f"Detected worktree ID: {wt_id} (path_key: {path_str})")
                return wt_id

    logger.debug(f"No worktree ID detected for current path: {cwd}")
    return None


def register_worktree(
    wt_id: str,
    path: Path,
    branch: str | None = None,
    name: str | None = None,
    config: IssueConfig | None = None,
) -> IssueConfig:
    """Register a new worktree in configuration.

    Args:
        wt_id: Worktree identifier
        path: Path to worktree directory
        branch: Git branch name (optional)
        name: Human-readable name (optional)
        config: Existing config to update. If None, loads from default path.

    Returns:
        IssueConfig: Updated configuration object
    """
    cfg = config or load_config()

    cfg.worktree_mapping[str(path.resolve())] = wt_id

    if name:
        cfg.worktree_names[wt_id] = name

    logger.info(f"Registered worktree: {wt_id} -> {path}")
    return cfg
