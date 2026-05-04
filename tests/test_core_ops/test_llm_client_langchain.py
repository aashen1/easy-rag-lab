from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest


class TestCreateLangchainAnthropicClient:
    def test_raises_on_empty_api_key(self):
        from src.exceptions import GenerationError
        from src.llm_client import create_langchain_anthropic_client

        with pytest.raises(GenerationError, match="API key is required"):
            create_langchain_anthropic_client(api_key="")

    def test_raises_on_missing_base_url(self):
        from src.exceptions import GenerationError
        from src.llm_client import create_langchain_anthropic_client

        with pytest.raises(GenerationError, match="base_url is required"):
            create_langchain_anthropic_client(api_key="test-key", base_url=None)

    def test_creates_client_with_bearer_auth(self):
        from src.llm_client import create_langchain_anthropic_client

        mock_instance = MagicMock()
        mock_chat_cls = MagicMock(return_value=mock_instance)

        with patch.dict(
            "sys.modules",
            {"langchain_anthropic": MagicMock(ChatAnthropic=mock_chat_cls)},
        ):
            result = create_langchain_anthropic_client(
                api_key="my-secret-key",
                base_url="https://api.example.com",
                model_name="claude-sonnet-4-20250514",
            )

        assert result is mock_instance
        mock_chat_cls.assert_called_once_with(
            anthropic_api_key="dummy",
            anthropic_api_url="https://api.example.com",
            model="claude-sonnet-4-20250514",
            temperature=0.0,
            max_tokens=1024,
            default_headers={"Authorization": "Bearer my-secret-key"},
        )

    def test_default_model_name(self):
        from src.llm_client import create_langchain_anthropic_client

        mock_instance = MagicMock()
        mock_chat_cls = MagicMock(return_value=mock_instance)

        with patch.dict(
            "sys.modules",
            {"langchain_anthropic": MagicMock(ChatAnthropic=mock_chat_cls)},
        ):
            create_langchain_anthropic_client(
                api_key="key",
                base_url="https://api.example.com",
            )

        call_kwargs = mock_chat_cls.call_args[1]
        assert call_kwargs["model"] == "claude-sonnet-4-20250514"

    def test_custom_temperature_and_max_tokens(self):
        from src.llm_client import create_langchain_anthropic_client

        mock_instance = MagicMock()
        mock_chat_cls = MagicMock(return_value=mock_instance)

        with patch.dict(
            "sys.modules",
            {"langchain_anthropic": MagicMock(ChatAnthropic=mock_chat_cls)},
        ):
            create_langchain_anthropic_client(
                api_key="key",
                base_url="https://api.example.com",
                temperature=0.5,
                max_tokens=2048,
            )

        call_kwargs = mock_chat_cls.call_args[1]
        assert call_kwargs["temperature"] == 0.5
        assert call_kwargs["max_tokens"] == 2048
