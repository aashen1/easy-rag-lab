from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import yaml

from src.utils import create_llm_client, detect_document_category, ensure_dir, get_env_var, get_llm_config, load_config


@pytest.mark.unit
class TestLoadConfig:
    def test_load_valid_config(self, tmp_path):
        config_file = tmp_path / "test_config.yaml"
        config_data = {"key": "value", "nested": {"inner": 42}}
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_config(str(config_file))

        assert isinstance(result, dict)
        assert result["key"] == "value"
        assert result["nested"]["inner"] == 42

    def test_load_config_file_not_found(self):
        with pytest.raises(FileNotFoundError):
            load_config("/nonexistent/path/config.yaml")

    def test_load_config_invalid_yaml(self, tmp_path):
        config_file = tmp_path / "bad_config.yaml"
        config_file.write_text(":\n  - [invalid: yaml: content:", encoding="utf-8")

        with pytest.raises(yaml.YAMLError):
            load_config(str(config_file))


@pytest.mark.unit
class TestGetLlmConfig:
    @patch("src.utils.os.getenv")
    def test_default_preset(self, mock_getenv):
        mock_getenv.side_effect = lambda key, default=None: {
            "LLM_MODEL_ID": "test-model",
            "LLM_API_KEY": "test-key",
            "LLM_BASE_URL": "https://api.test.com/",
        }.get(key, default)
        config = {
            "llm_presets": {
                "default": {
                    "temperature": 0.5,
                    "max_tokens": 2048,
                }
            }
        }

        result = get_llm_config(config)

        assert result["model_name"] == "test-model"
        assert result["temperature"] == 0.5
        assert result["max_tokens"] == 2048
        assert result["api_key"] == "test-key"
        assert result["base_url"] == "https://api.test.com/anthropic"

    @patch("src.utils.os.getenv")
    def test_named_preset(self, mock_getenv):
        mock_getenv.side_effect = lambda key, default=None: {
            "CUSTOM_MODEL": "custom-model-name",
            "CUSTOM_API_KEY": "custom-key",
            "CUSTOM_BASE_URL": "https://custom.api.com/",
        }.get(key, default)
        config = {
            "llm_presets": {
                "custom": {
                    "model_name": "CUSTOM_MODEL",
                    "api_key": "CUSTOM_API_KEY",
                    "base_url": "CUSTOM_BASE_URL",
                    "temperature": 0.7,
                    "max_tokens": 4096,
                }
            }
        }

        result = get_llm_config(config, preset_name="custom")

        assert result["model_name"] == "custom-model-name"
        assert result["api_key"] == "custom-key"
        assert result["base_url"] == "https://custom.api.com/anthropic"
        assert result["temperature"] == 0.7
        assert result["max_tokens"] == 4096

    @patch("src.utils.os.getenv")
    def test_preset_not_found_fallback(self, mock_getenv):
        mock_getenv.side_effect = lambda key, default=None: {
            "LLM_MODEL_ID": "fallback-model",
            "LLM_API_KEY": "fallback-key",
            "LLM_BASE_URL": "https://fallback.api.com/",
        }.get(key, default)
        config = {
            "llm_presets": {
                "default": {
                    "temperature": 0.0,
                    "max_tokens": 1024,
                }
            }
        }

        result = get_llm_config(config, preset_name="nonexistent")

        assert result["model_name"] == "fallback-model"
        assert result["temperature"] == 0.0
        assert result["max_tokens"] == 1024

    @patch("src.utils.os.getenv")
    def test_env_var_resolution(self, mock_getenv):
        mock_getenv.side_effect = lambda key, default=None: {
            "MY_MODEL": "env-model",
            "MY_KEY": "env-key",
            "MY_URL": "https://env.url.com/",
        }.get(key, default)
        config = {
            "llm_presets": {
                "default": {
                    "model_name": "MY_MODEL",
                    "api_key": "MY_KEY",
                    "base_url": "MY_URL",
                    "temperature": 0.3,
                    "max_tokens": 512,
                }
            }
        }

        result = get_llm_config(config)

        assert result["model_name"] == "env-model"
        assert result["api_key"] == "env-key"
        assert result["base_url"] == "https://env.url.com/anthropic"

    @patch("src.utils.os.getenv")
    def test_api_key_missing_raises_error(self, mock_getenv):
        mock_getenv.side_effect = lambda key, default=None: {
            "LLM_MODEL_ID": "test-model",
            "LLM_BASE_URL": "https://api.test.com/",
        }.get(key, default)
        config = {"llm_presets": {"default": {"temperature": 0.5, "max_tokens": 2048}}}
        with pytest.raises(ValueError, match="Required environment variable"):
            get_llm_config(config)


@pytest.mark.unit
class TestGetEnvVar:
    @patch("src.utils.os.getenv")
    def test_existing_var(self, mock_getenv):
        mock_getenv.return_value = "some_value"

        result = get_env_var("EXISTING_VAR")

        assert result == "some_value"
        mock_getenv.assert_called_once_with("EXISTING_VAR", None)

    @patch("src.utils.os.getenv")
    def test_missing_var_with_default(self, mock_getenv):
        mock_getenv.return_value = "default_val"

        result = get_env_var("MISSING_VAR", default="default_val")

        assert result == "default_val"
        mock_getenv.assert_called_once_with("MISSING_VAR", "default_val")

    @patch("src.utils.os.getenv")
    def test_required_var_missing(self, mock_getenv):
        mock_getenv.return_value = None

        with pytest.raises(ValueError, match="Required environment variable 'REQUIRED_VAR' is not set"):
            get_env_var("REQUIRED_VAR", required=True)


@pytest.mark.unit
class TestEnsureDir:
    def test_create_new_dir(self, tmp_path):
        new_dir = tmp_path / "new_directory"

        result = ensure_dir(str(new_dir))

        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_dir()

    def test_existing_dir(self, tmp_path):
        existing_dir = tmp_path / "existing"
        existing_dir.mkdir()

        result = ensure_dir(str(existing_dir))

        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_dir()

    def test_nested_dir(self, tmp_path):
        nested_path = tmp_path / "a" / "b" / "c" / "deep"

        result = ensure_dir(str(nested_path))

        assert isinstance(result, Path)
        assert result.exists()
        assert result.is_dir()


@pytest.mark.unit
class TestDetectDocumentCategory:
    def test_annual_report_from_english_path(self):
        result = detect_document_category("data/raw/annual_report/company_a.pdf")

        assert result == "annual_report"

    def test_annual_report_from_chinese_path(self):
        result = detect_document_category("data/raw/年报/company_a.pdf")

        assert result == "annual_report"

    def test_research_report_from_english_path(self):
        result = detect_document_category("data/raw/research_report/industry_b.pdf")

        assert result == "research_report"

    def test_research_report_from_chinese_path(self):
        result = detect_document_category("data/raw/研报/industry_b.pdf")

        assert result == "research_report"

    def test_unknown_category(self):
        result = detect_document_category("data/raw/other/document.pdf")

        assert result == "unknown"

    def test_custom_category_mapping(self):
        custom_mapping = {"financial": "financial_report", "ESG": "esg_report"}

        result = detect_document_category("data/raw/financial/company_c.pdf", custom_mapping)

        assert result == "financial_report"

    def test_custom_mapping_priority_over_default(self):
        custom_mapping = {"annual_report": "custom_annual"}

        result = detect_document_category("data/raw/annual_report/company_a.pdf", custom_mapping)

        assert result == "custom_annual"

    def test_custom_mapping_no_match_returns_unknown(self):
        custom_mapping = {"financial": "financial_report"}

        result = detect_document_category("data/raw/annual_report/company_a.pdf", custom_mapping)

        assert result == "unknown"


@pytest.mark.unit
class TestCreateLlmClient:
    def _make_llm_config(self, **overrides):
        base = {
            "api_key": "test-api-key",
            "base_url": "https://api.longcat.chat",
            "model_name": "test-model",
        }
        base.update(overrides)
        return base

    @patch("src.utils.Anthropic", create=True)
    def test_sdk_mode_creates_anthropic_client(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=mock_anthropic_cls)}):
            result = create_llm_client(
                llm_config=self._make_llm_config(),
                mode="sdk",
            )

        mock_anthropic_cls.assert_called_once_with(
            api_key="dummy",
            base_url="https://api.longcat.chat/anthropic",
            default_headers={
                "Authorization": "Bearer test-api-key",
                "Content-Type": "application/json",
            },
        )
        assert result == mock_client

    @patch("src.utils.Anthropic", create=True)
    def test_sdk_mode_base_url_already_has_anthropic_suffix(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=mock_anthropic_cls)}):
            create_llm_client(
                llm_config=self._make_llm_config(base_url="https://api.longcat.chat/anthropic"),
                mode="sdk",
            )

        mock_anthropic_cls.assert_called_once_with(
            api_key="dummy",
            base_url="https://api.longcat.chat/anthropic",
            default_headers={
                "Authorization": "Bearer test-api-key",
                "Content-Type": "application/json",
            },
        )

    @patch("src.utils.Anthropic", create=True)
    def test_sdk_mode_base_url_trailing_slash(self, mock_anthropic_cls):
        mock_client = MagicMock()
        mock_anthropic_cls.return_value = mock_client

        with patch.dict("sys.modules", {"anthropic": MagicMock(Anthropic=mock_anthropic_cls)}):
            create_llm_client(
                llm_config=self._make_llm_config(base_url="https://api.longcat.chat/"),
                mode="sdk",
            )

        mock_anthropic_cls.assert_called_once_with(
            api_key="dummy",
            base_url="https://api.longcat.chat/anthropic",
            default_headers={
                "Authorization": "Bearer test-api-key",
                "Content-Type": "application/json",
            },
        )

    def test_invalid_mode_raises_value_error(self):
        with pytest.raises(ValueError, match="Unsupported LLM client mode: invalid"):
            create_llm_client(
                llm_config=self._make_llm_config(),
                mode="invalid",
            )

    def test_langchain_mode_creates_wrapper(self):
        mock_chat_cls = MagicMock()
        mock_wrapper_cls = MagicMock()
        mock_chat_instance = MagicMock()
        mock_wrapper_instance = MagicMock()
        mock_chat_cls.return_value = mock_chat_instance
        mock_wrapper_cls.return_value = mock_wrapper_instance

        mock_lc_module = MagicMock(ChatAnthropic=mock_chat_cls)
        mock_ragas_llm_module = MagicMock(LangchainLLMWrapper=mock_wrapper_cls)

        with patch.dict("sys.modules", {
            "langchain_anthropic": mock_lc_module,
            "ragas": MagicMock(),
            "ragas.llms": mock_ragas_llm_module,
        }):
            result = create_llm_client(
                llm_config=self._make_llm_config(),
                mode="langchain",
            )

        mock_chat_cls.assert_called_once_with(
            model="test-model",
            api_key="dummy",
            base_url="https://api.longcat.chat/anthropic",
            default_headers={
                "Authorization": "Bearer test-api-key",
                "Content-Type": "application/json",
            },
            max_tokens=4096,
            temperature=0.0,
        )
        mock_wrapper_cls.assert_called_once_with(mock_chat_instance)
        assert result == mock_wrapper_instance

    def test_langchain_mode_custom_max_tokens_and_temperature(self):
        mock_chat_cls = MagicMock()
        mock_wrapper_cls = MagicMock()
        mock_chat_cls.return_value = MagicMock()
        mock_wrapper_cls.return_value = MagicMock()

        mock_lc_module = MagicMock(ChatAnthropic=mock_chat_cls)
        mock_ragas_llm_module = MagicMock(LangchainLLMWrapper=mock_wrapper_cls)

        with patch.dict("sys.modules", {
            "langchain_anthropic": mock_lc_module,
            "ragas": MagicMock(),
            "ragas.llms": mock_ragas_llm_module,
        }):
            create_llm_client(
                llm_config=self._make_llm_config(max_tokens=8192, temperature=0.5),
                mode="langchain",
            )

        mock_chat_cls.assert_called_once_with(
            model="test-model",
            api_key="dummy",
            base_url="https://api.longcat.chat/anthropic",
            default_headers={
                "Authorization": "Bearer test-api-key",
                "Content-Type": "application/json",
            },
            max_tokens=8192,
            temperature=0.5,
        )
