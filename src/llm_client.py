from typing import Optional

from anthropic import Anthropic
from loguru import logger


def create_anthropic_client(
    api_key: str,
    base_url: str = "https://api.longcat.chat/anthropic",
) -> Anthropic:
    """Create an Anthropic client with the project's standard authentication pattern.

    The LongCat API proxy expects the real API key in the Authorization: Bearer
    header rather than the x-api-key header that the Anthropic SDK uses by
    default. This function encapsulates that pattern so it doesn't need to be
    repeated across the codebase.

    Args:
        api_key: API key for authentication (passed via Authorization header).
        base_url: Base URL for the API endpoint.

    Returns:
        Configured Anthropic client instance.

    Raises:
        ValueError: If api_key is empty or None.
        Exception: If client creation fails.
    """
    if not api_key:
        raise ValueError("API key is required for Anthropic client creation")

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
