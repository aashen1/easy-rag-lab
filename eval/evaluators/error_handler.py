from __future__ import annotations

from collections.abc import Callable
from typing import Any

from loguru import logger


def execute_metric_safely(
    metric_name: str,
    calc_func: Callable,
    result_dict: dict[str, Any],
    question_id: str = "",
    *args: Any,
    **kwargs: Any,
) -> Any:
    try:
        result = calc_func(*args, **kwargs)
        result_dict[metric_name] = result
        return result
    except Exception as e:
        logger.error(f"Failed to calculate {metric_name} for {question_id}: {str(e)}")
        result_dict[metric_name] = None
        return None


def log_evaluation_error(
    operation: str,
    question_id: str,
    exception: Exception,
) -> str:
    error_msg = str(exception)
    logger.error(f"{operation} failed for {question_id}: {error_msg}")
    return error_msg
