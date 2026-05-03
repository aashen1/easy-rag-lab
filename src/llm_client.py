from typing import Any

from anthropic import Anthropic
from loguru import logger

from src.exceptions import GenerationError


def create_anthropic_client(
    api_key: str,
    base_url: str | None = None,
) -> Anthropic:
    """Create an Anthropic client with the project's standard authentication pattern.

    The API proxy expects the real API key in the Authorization: Bearer
    header rather than the x-api-key header that the Anthropic SDK uses by
    default. This function encapsulates that pattern so it doesn't need to be
    repeated across the codebase.

    Args:
        api_key: API key for authentication (passed via Authorization header).
        base_url: Base URL for the API endpoint. Must be provided explicitly
            or resolved from config/env before calling this function.

    Returns:
        Configured Anthropic client instance.

    Raises:
        ValueError: If api_key is empty or None, or if base_url is not provided.
        Exception: If client creation fails.
    """
    if not api_key:
        raise GenerationError("API key is required for Anthropic client creation")

    if not base_url:
        raise GenerationError(
            "base_url is required for Anthropic client creation; "
            "set LLM_BASE_URL in .env"
        )

    try:
        client = Anthropic(
            api_key="dummy",
            base_url=base_url,
            default_headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json",
            },
        )
        return client
    except Exception as e:
        error_msg = f"Failed to create Anthropic client: {str(e)}"
        logger.error(error_msg)
        raise


def create_langchain_anthropic_client(
    api_key: str,
    base_url: str | None = None,
    model_name: str | None = None,
    temperature: float = 0.0,
    max_tokens: int = 1024,
) -> Any:
    """Create a LangChain ChatAnthropic client with the project's standard authentication pattern.

    The API proxy expects the real API key in the Authorization: Bearer
    header rather than the x-api-key header that the Anthropic SDK uses by
    default. This function encapsulates that pattern for LangChain-based
    workflows.

    Args:
        api_key: API key for authentication (passed via Authorization header).
        base_url: Base URL for the API endpoint. Must be provided explicitly
            or resolved from config/env before calling this function.
        model_name: Model identifier to use. Defaults to
            "claude-sonnet-4-20250514" if not provided.
        temperature: Sampling temperature for generation. Defaults to 0.0.
        max_tokens: Maximum number of tokens to generate. Defaults to 1024.

    Returns:
        Configured ChatAnthropic instance.

    Raises:
        GenerationError: If api_key is empty or base_url is not provided.
        Exception: If client creation fails.
    """
    if not api_key:
        raise GenerationError(
            "API key is required for LangChain Anthropic client creation"
        )

    if not base_url:
        raise GenerationError(
            "base_url is required for LangChain Anthropic client creation; "
            "set LLM_BASE_URL in .env"
        )

    try:
        from langchain_anthropic import ChatAnthropic

        resolved_model = model_name or "claude-sonnet-4-20250514"

        client = ChatAnthropic(
            anthropic_api_key="dummy",
            anthropic_api_url=base_url,
            model=resolved_model,
            temperature=temperature,
            max_tokens=max_tokens,
            default_headers={
                "Authorization": f"Bearer {api_key}",
            },
        )
        return client
    except Exception as e:
        error_msg = f"Failed to create LangChain Anthropic client: {str(e)}"
        logger.error(error_msg)
        raise
