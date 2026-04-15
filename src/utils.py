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
