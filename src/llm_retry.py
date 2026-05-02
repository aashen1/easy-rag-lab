import random
import time
from collections.abc import Callable
from typing import Any

from loguru import logger

_RETRYABLE_STATUS_CODES = {429, 503, 529}
_RETRYABLE_SUBSTRINGS = [
    "rate_limit",
    "rate limit",
    "throttl",
    "overload",
    "too many requests",
    "capacity",
]


def _is_retryable_error(exc: Exception) -> bool:
    status = getattr(exc, "status_code", None)
    if status in _RETRYABLE_STATUS_CODES:
        return True
    msg = str(exc).lower()
    return any(s in msg for s in _RETRYABLE_SUBSTRINGS)


def call_with_retry(
    fn: Callable,
    *args,
    max_retries: int = 5,
    base_delay: float = 1.0,
    max_delay: float = 60.0,
    **kwargs,
) -> Any:
    """Call *fn* with exponential-backoff retry on rate-limit errors.

    Detects 429 / rate_limit / overloaded errors and retries automatically.
    Delay formula: ``min(base_delay * 2**attempt + jitter, max_delay)``

    Args:
        fn: Callable to invoke (typically ``client.messages.create``).
        *args: Positional arguments forwarded to *fn*.
        max_retries: Maximum number of retry attempts.
        base_delay: Base delay in seconds for the first retry.
        max_delay: Upper bound on delay between retries.
        **kwargs: Keyword arguments forwarded to *fn*.

    Returns:
        The return value of *fn* on success.

    Raises:
        Exception: The last exception if all retries are exhausted,
            or any non-retryable exception on first encounter.
    """
    last_exc: Exception | None = None
    for attempt in range(max_retries + 1):
        try:
            return fn(*args, **kwargs)
        except Exception as exc:
            if not _is_retryable_error(exc):
                raise
            last_exc = exc
            if attempt < max_retries:
                delay = min(base_delay * (2**attempt), max_delay)
                jitter = random.uniform(0, 0.1 * delay)
                wait = delay + jitter
                logger.warning(
                    f"Rate-limited (attempt {attempt + 1}/{max_retries}), "
                    f"retrying in {wait:.1f}s: {type(exc).__name__}: {exc}"
                )
                time.sleep(wait)
            else:
                logger.error(
                    f"Rate-limited after {max_retries} retries, giving up: "
                    f"{type(exc).__name__}: {exc}"
                )
    raise last_exc  # type: ignore[misc]
