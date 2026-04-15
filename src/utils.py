import os
from pathlib import Path
from typing import Any, Dict

import yaml
from dotenv import load_dotenv
from loguru import logger

load_dotenv()


def load_config(config_path: str = "config.yaml") -> Dict[str, Any]:
    with open(config_path, "r", encoding="utf-8") as f:
        config = yaml.safe_load(f)
    logger.info(f"Configuration loaded from {config_path}")
    return config


def setup_logger(config: Dict[str, Any]) -> None:
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

    logger.remove()

    logger.add(
        sink=lambda msg: print(msg, end=""),
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


def get_llm_config(config: Dict[str, Any], preset_name: str = None) -> Dict[str, Any]:
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
        model_name = get_env_var("LLM_MODEL_ID", "LongCat-Flash-Lite")

    api_key_env = preset_config.get("api_key", "LLM_API_KEY")
    api_key = get_env_var(api_key_env)
    if not api_key:
        api_key = get_env_var("LLM_API_KEY", required=True)

    base_url_env = preset_config.get("base_url", "LLM_BASE_URL")
    base_url = get_env_var(base_url_env)
    if not base_url:
        base_url = get_env_var("LLM_BASE_URL", "https://api.longcat.chat/")

    return {
        "model_name": model_name,
        "temperature": preset_config.get("temperature", 0.0),
        "max_tokens": preset_config.get("max_tokens", 1024),
        "api_key": api_key,
        "base_url": base_url.rstrip("/") + "/anthropic",
    }


def get_env_var(key: str, default: str = None, required: bool = False) -> str:
    value = os.getenv(key, default)

    if required and value is None:
        error_msg = f"Required environment variable '{key}' is not set"
        logger.error(error_msg)
        raise ValueError(error_msg)

    if value is None:
        logger.warning(f"Environment variable '{key}' not set, using default: {default}")

    return value


def ensure_dir(path: str) -> Path:
    dir_path = Path(path)
    dir_path.mkdir(parents=True, exist_ok=True)
    logger.debug(f"Ensured directory exists: {dir_path}")
    return dir_path
