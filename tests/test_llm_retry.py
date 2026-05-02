from unittest.mock import MagicMock

import pytest

from src.llm_retry import _is_retryable_error, call_with_retry


class _RateLimitError(Exception):
    def __init__(self, status_code=429, message="rate_limit_error"):
        super().__init__(message)
        self.status_code = status_code


class _OverloadedError(Exception):
    def __init__(self):
        super().__init__("Overloaded")
        self.status_code = 529


class _ServerError(Exception):
    def __init__(self):
        super().__init__("Internal Server Error")
        self.status_code = 500


class _AuthError(Exception):
    def __init__(self):
        super().__init__("Invalid API key")
        self.status_code = 401


@pytest.mark.unit
class TestIsRetryableError:
    def test_429_is_retryable(self):
        assert _is_retryable_error(_RateLimitError(429)) is True

    def test_529_is_retryable(self):
        assert _is_retryable_error(_OverloadedError()) is True

    def test_503_is_retryable(self):
        exc = Exception("service unavailable")
        exc.status_code = 503
        assert _is_retryable_error(exc) is True

    def test_401_not_retryable(self):
        assert _is_retryable_error(_AuthError()) is False

    def test_500_not_retryable(self):
        assert _is_retryable_error(_ServerError()) is False

    def test_rate_limit_substring(self):
        assert _is_retryable_error(Exception("rate limit exceeded")) is True

    def test_throttled_substring(self):
        assert _is_retryable_error(Exception("request was throttled")) is True

    def test_overload_substring(self):
        assert _is_retryable_error(Exception("API is overloaded")) is True

    def test_generic_error_not_retryable(self):
        assert _is_retryable_error(Exception("something else")) is False


@pytest.mark.unit
class TestCallWithRetry:
    def test_success_on_first_try(self):
        fn = MagicMock(return_value="ok")
        result = call_with_retry(fn, max_retries=3)
        assert result == "ok"
        assert fn.call_count == 1

    def test_retries_on_429_then_succeeds(self):
        fn = MagicMock(side_effect=[_RateLimitError(429), _RateLimitError(429), "ok"])
        result = call_with_retry(fn, max_retries=3, base_delay=0.01, max_delay=0.1)
        assert result == "ok"
        assert fn.call_count == 3

    def test_raises_after_max_retries(self):
        fn = MagicMock(side_effect=_RateLimitError(429))
        with pytest.raises(_RateLimitError):
            call_with_retry(fn, max_retries=2, base_delay=0.01, max_delay=0.1)
        assert fn.call_count == 3

    def test_non_retryable_error_raised_immediately(self):
        fn = MagicMock(side_effect=_AuthError())
        with pytest.raises(_AuthError):
            call_with_retry(fn, max_retries=3, base_delay=0.01)
        assert fn.call_count == 1

    def test_passes_args_and_kwargs(self):
        fn = MagicMock(return_value="result")
        call_with_retry(fn, "arg1", "arg2", key1="val1", max_retries=0)
        fn.assert_called_once_with("arg1", "arg2", key1="val1")

    def test_overloaded_error_is_retryable(self):
        fn = MagicMock(side_effect=[_OverloadedError(), "ok"])
        result = call_with_retry(fn, max_retries=1, base_delay=0.01, max_delay=0.1)
        assert result == "ok"
        assert fn.call_count == 2
