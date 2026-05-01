import copy
import os
import sys
from pathlib import Path
from typing import Any

import yaml
from dotenv import load_dotenv
from loguru import logger

from src.exceptions import ConfigurationError

load_dotenv()


def load_config(config_path: str = "config.yaml") -> dict[str, Any]:
    """Load YAML configuration file and return its contents as a dictionary.

    If the config contains a top-level ``data_dir`` key, all path values
    that start with ``"data/"`` are rewritten to be relative to that
    directory.  This allows users to point the entire data tree at a
    different location (e.g. a separate drive) without using symlinks.

    Args:
        config_path: Path to the YAML configuration file. Defaults to "config.yaml".

    Returns:
        Parsed configuration as a dictionary.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        yaml.YAMLError: If the file contains invalid YAML.
    """
    if config_path is None:
        config_path = "config.yaml"
    with open(config_path, encoding="utf-8") as f:
        config = yaml.safe_load(f)

    data_dir = config.get("data_dir", "data")
    if data_dir != "data":
        config = _resolve_data_paths(config, data_dir)

    logger.info(f"Configuration loaded from {config_path}")
    return config


def _resolve_data_paths(config: dict[str, Any], data_dir: str) -> dict[str, Any]:
    """Rewrite path values starting with ``data/`` to use the given data_dir.

    Walks the config dict recursively.  For every string value that starts
    with ``"data/"``, the ``"data"`` prefix is replaced with *data_dir*.

    Args:
        config: Configuration dictionary (modified in-place).
        data_dir: Replacement for the ``"data"`` prefix.

    Returns:
        The modified config dictionary (same object as input).
    """
    prefix = "data/"
    for key, value in config.items():
        if isinstance(value, str) and value.startswith(prefix):
            config[key] = value.replace(prefix, data_dir + "/", 1)
        elif isinstance(value, dict):
            _resolve_data_paths(value, data_dir)
    return config


def setup_logger(config: dict[str, Any], force: bool = False) -> None:
    """Configure loguru logger with console and file sinks based on config.

    Args:
        config: Application configuration dictionary. Expected to contain
            a "logging" key with optional sub-keys: log_dir, level, format,
            rotation, and retention.
        force: If True, remove all existing handlers before setup.
               If False, only add handlers if not already configured.
               Default is False to preserve existing handlers (e.g., experiment.log).

    Returns:
        None
    """
    log_config = config.get("logging", {})
    log_dir = Path(log_config.get("log_dir", "logs"))
    log_dir.mkdir(parents=True, exist_ok=True)

    log_level = log_config.get("level", "INFO")
    log_format = log_config.get(
        "format",
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    rotation = log_config.get("rotation", "10 MB")
    retention = log_config.get("retention", "7 days")

    if force:
        logger.remove()

    logger.add(
        sink=lambda msg: sys.stdout.write(msg),
        format=log_format,
        level=log_level,
        colorize=True,
    )

    logger.add(
        sink=log_dir / "app_{time:YYYY-MM-DD}.log",
        format=log_format,
        level=log_level,
        rotation=rotation,
        retention=retention,
        encoding="utf-8",
    )

    logger.info("Logger initialized")


def get_llm_config(config: dict[str, Any], preset_name: str = None) -> dict[str, Any]:
    """Resolve LLM configuration from a named preset, reading secrets from environment variables.

    Args:
        config: Application configuration dictionary containing "llm_presets"
            and optionally "active_mode".
        preset_name: Name of the LLM preset to use. If None, falls back to
            the "active_mode" value in config, then "default".

    Returns:
        Dictionary with keys: model_name, temperature, max_tokens, api_key,
        and base_url (with "/anthropic" suffix appended).
    """
    if preset_name is None:
        preset_name = config.get("active_mode", "default")

    llm_presets = config.get("llm_presets", {})
    preset_config = llm_presets.get(preset_name)

    if not preset_config:
        logger.warning(f"LLM preset '{preset_name}' not found, using default")
        preset_config = llm_presets.get("default", {})

    model_name_env = preset_config.get("model_name")
    if model_name_env:
        model_name = get_env_var(model_name_env)
    else:
        model_name = get_env_var("LLM_MODEL_ID")

    if not model_name:
        logger.warning(
            "LLM_MODEL_ID not set and no model_name in preset; set LLM_MODEL_ID in .env"
        )

    api_key_env = preset_config.get("api_key", "LLM_API_KEY")
    api_key = get_env_var(api_key_env)
    if not api_key:
        api_key = get_env_var("LLM_API_KEY", required=True)

    base_url_env = preset_config.get("base_url", "LLM_BASE_URL")
    base_url = get_env_var(base_url_env)
    if not base_url:
        base_url = get_env_var("LLM_BASE_URL")

    if not base_url:
        logger.warning(
            "LLM_BASE_URL not set and no base_url in preset; set LLM_BASE_URL in .env"
        )

    return {
        "model_name": model_name,
        "temperature": preset_config.get("temperature", 0.0),
        "max_tokens": preset_config.get("max_tokens", 1024),
        "api_key": api_key,
        "base_url": base_url.rstrip("/") + "/anthropic",
    }


def create_llm_client(
    llm_config: dict[str, Any],
    mode: str = "sdk",
) -> Any:
    """Create an LLM client with LongCat API adaptation.

    Supports two modes:
    - "sdk": Returns an Anthropic SDK client (for direct API calls)
    - "langchain": Returns a LangchainLLMWrapper with ChatAnthropic (for RAGAS)

    Both modes use the same LongCat API adaptation pattern:
    api_key="dummy" with real key passed via Authorization: Bearer header.

    Args:
        llm_config: Dictionary containing api_key, base_url, model_name,
            and optionally max_tokens, temperature.
        mode: Client mode - "sdk" for Anthropic SDK, "langchain" for LangChain.

    Returns:
        LLM client instance (Anthropic or LangchainLLMWrapper).

    Raises:
        ValueError: If mode is not "sdk" or "langchain".
        ImportError: If required dependencies are not installed.
    """
    base_url = llm_config["base_url"].rstrip("/")
    if not base_url.endswith("/anthropic"):
        base_url = f"{base_url}/anthropic"

    if mode == "sdk":
        from anthropic import Anthropic

        return Anthropic(
            api_key="dummy",
            base_url=base_url,
            default_headers={
                "Authorization": f"Bearer {llm_config['api_key']}",
                "Content-Type": "application/json",
            },
        )
    elif mode == "langchain":
        from langchain_anthropic import ChatAnthropic
        from ragas.llms import LangchainLLMWrapper

        chat_model = ChatAnthropic(
            model=llm_config["model_name"],
            api_key="dummy",
            base_url=base_url,
            default_headers={
                "Authorization": f"Bearer {llm_config['api_key']}",
                "Content-Type": "application/json",
            },
            max_tokens=llm_config.get("max_tokens", 4096),
            temperature=llm_config.get("temperature", 0.0),
        )
        return LangchainLLMWrapper(chat_model)
    else:
        raise ConfigurationError(
            f"Unsupported LLM client mode: {mode}. Use 'sdk' or 'langchain'."
        )


def get_env_var(key: str, default: str = None, required: bool = False) -> str:
    """Retrieve an environment variable value with optional default and required check.

    Args:
        key: Name of the environment variable.
        default: Default value to use if the variable is not set. Defaults to None.
        required: If True and the variable is not set (and no default), raises ValueError.

    Returns:
        The environment variable value, or the default if not set.

    Raises:
        ValueError: If required is True and the variable is not set with no default.
    """
    value = os.getenv(key, default)

    if required and value is None:
        error_msg = f"Required environment variable '{key}' is not set"
        logger.error(error_msg)
        raise ConfigurationError(error_msg)

    if value is None:
        logger.warning(
            f"Environment variable '{key}' not set, using default: {default}"
        )

    return value


def ensure_dir(path: str) -> Path:
    """Ensure a directory exists, creating it and parents if necessary.

    Args:
        path: Filesystem path to the directory.

    Returns:
        Path object representing the ensured directory.
    """
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured directory exists: {dir_path}")
    return dir_path


def sanitize_name(name: str) -> str:
    """Sanitize a name for use as a file system path component.

    Converts to lowercase, replaces spaces and hyphens with underscores,
    and removes all characters except alphanumeric and underscore.

    Args:
        name: The raw name string to sanitize.

    Returns:
        A sanitized string safe for use in file paths.
    """
    safe = name.lower().replace(" ", "_").replace("-", "_")
    return "".join(c for c in safe if c.isalnum() or c == "_")


DEFAULT_CATEGORY_MAPPING: dict[str, str] = {
    "annual_report": "annual_report",
    "年报": "annual_report",
    "research_report": "research_report",
    "研报": "research_report",
}


def deep_merge(base: dict[str, Any], override: dict[str, Any]) -> dict[str, Any]:
    """Deep merge two dictionaries.

    Values from override dictionary take precedence over base dictionary.
    Nested dictionaries are merged recursively.

    Args:
        base: Base dictionary to merge into.
        override: Dictionary with values to override.

    Returns:
        Merged dictionary.
    """
    result = copy.deepcopy(base)

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)

    return result


def detect_document_category(
    file_path: str,
    category_mapping: dict[str, str] | None = None,
) -> str:
    """Detect the document category based on the file path string.

    If a custom category_mapping is provided, it takes priority: each key
    is checked against the file path and the first matching key's value
    is returned.  When no mapping is supplied the built-in default mapping
    is used, which recognises annual-report and research-report keywords
    in both English and Chinese.

    Args:
        file_path: Path string of the document file.
        category_mapping: Optional dict mapping path substrings to category
            names.  Keys are matched against the file path using ``in``.

    Returns:
        The detected category string, or ``"unknown"`` if no keyword
        matches.
    """
    mapping = (
        category_mapping if category_mapping is not None else DEFAULT_CATEGORY_MAPPING
    )
    for key, category in mapping.items():
        if key in str(file_path):
            return category
    return "unknown"
