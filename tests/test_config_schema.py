import pytest
import yaml
from pydantic import ValidationError

from src.config_schema import (
    AppConfig,
    ChunkerConfig,
    LLMRetryConfig,
    LoggingConfig,
    RetrievalConfig,
)
from src.exceptions import ConfigurationError
from src.utils import load_config


def _minimal_config() -> dict:
    return {
        "active_mode": "default",
        "llm_presets": {
            "default": {
                "model_name": "LLM_MODEL_ID",
                "temperature": 0.0,
                "max_tokens": 1024,
                "api_key": "LLM_API_KEY",
                "base_url": "LLM_BASE_URL",
            }
        },
    }


@pytest.mark.unit
class TestAppConfigBasic:
    def test_minimal_config_passes(self):
        config = _minimal_config()
        result = AppConfig(**config)
        assert result.active_mode == "default"
        assert "default" in result.llm_presets

    def test_empty_config_uses_defaults(self):
        result = AppConfig()
        assert result.active_mode == "default"
        assert result.chunker.chunk_size == 512
        assert result.embedding.model_name == "BAAI/bge-large-zh-v1.5"
        assert result.vector_store.type == "qdrant"
        assert result.retrieval.method == "vector"
        assert result.logging.level == "INFO"

    def test_extra_fields_allowed(self):
        config = _minimal_config()
        config["custom_field"] = "custom_value"
        config["custom_nested"] = {"a": 1}
        result = AppConfig(**config)
        assert result.active_mode == "default"

    def test_model_dump_returns_dict(self):
        result = AppConfig()
        dumped = result.model_dump()
        assert isinstance(dumped, dict)
        assert isinstance(dumped["chunker"], dict)
        assert isinstance(dumped["chunker"]["semantic"], dict)


@pytest.mark.unit
class TestActiveModeValidation:
    def test_active_mode_in_presets(self):
        config = _minimal_config()
        config["llm_presets"]["custom"] = {
            "model_name": "CUSTOM_MODEL",
            "temperature": 0.5,
            "max_tokens": 2048,
            "api_key": "CUSTOM_KEY",
            "base_url": "CUSTOM_URL",
        }
        config["active_mode"] = "custom"
        result = AppConfig(**config)
        assert result.active_mode == "custom"

    def test_active_mode_not_in_presets_raises(self):
        config = _minimal_config()
        config["active_mode"] = "nonexistent"
        with pytest.raises(ValidationError, match="active_mode.*not found"):
            AppConfig(**config)


@pytest.mark.unit
class TestChunkerValidation:
    def test_valid_chunker(self):
        result = ChunkerConfig(chunk_size=512, chunk_overlap=64)
        assert result.chunk_size == 512
        assert result.chunk_overlap == 64

    def test_chunk_size_zero_raises(self):
        with pytest.raises(ValidationError, match="chunk_size"):
            ChunkerConfig(chunk_size=0)

    def test_chunk_size_negative_raises(self):
        with pytest.raises(ValidationError, match="chunk_size"):
            ChunkerConfig(chunk_size=-1)

    def test_chunk_overlap_negative_raises(self):
        with pytest.raises(ValidationError, match="chunk_overlap"):
            ChunkerConfig(chunk_size=512, chunk_overlap=-1)

    def test_chunk_overlap_equals_chunk_size_raises(self):
        with pytest.raises(ValidationError, match="chunk_overlap.*must be less than"):
            ChunkerConfig(chunk_size=512, chunk_overlap=512)

    def test_chunk_overlap_greater_than_chunk_size_raises(self):
        with pytest.raises(ValidationError, match="chunk_overlap.*must be less than"):
            ChunkerConfig(chunk_size=100, chunk_overlap=200)

    def test_invalid_strategy_raises(self):
        with pytest.raises(ValidationError, match="strategy"):
            ChunkerConfig(strategy="invalid")

    def test_invalid_encoding_raises(self):
        with pytest.raises(ValidationError, match="encoding"):
            ChunkerConfig(encoding="invalid")

    def test_semantic_config_defaults(self):
        result = ChunkerConfig(strategy="semantic")
        assert result.semantic.similarity_threshold == 0.5
        assert result.semantic.min_chunk_size == 100


@pytest.mark.unit
class TestRetrievalValidation:
    def test_valid_retrieval(self):
        result = RetrievalConfig()
        assert result.method == "vector"
        assert result.top_k == 5

    def test_invalid_method_raises(self):
        with pytest.raises(ValidationError, match="method"):
            RetrievalConfig(method="invalid")

    def test_top_k_zero_raises(self):
        with pytest.raises(ValidationError, match="top_k"):
            RetrievalConfig(top_k=0)

    def test_score_threshold_range(self):
        with pytest.raises(ValidationError, match="score_threshold"):
            RetrievalConfig(score_threshold=1.5)

    def test_reranker_defaults(self):
        result = RetrievalConfig()
        assert result.reranker.enabled is False
        assert result.reranker.top_n == 3

    def test_query_rewrite_defaults(self):
        result = RetrievalConfig()
        assert result.query_rewrite.enabled is False
        assert result.query_rewrite.strategy == "hyde"


@pytest.mark.unit
class TestLLMRetryValidation:
    def test_valid_retry(self):
        result = LLMRetryConfig()
        assert result.max_retries == 5

    def test_max_retries_negative_raises(self):
        with pytest.raises(ValidationError, match="max_retries"):
            LLMRetryConfig(max_retries=-1)

    def test_base_delay_zero_raises(self):
        with pytest.raises(ValidationError, match="base_delay"):
            LLMRetryConfig(base_delay=0)

    def test_base_delay_greater_than_max_delay_raises(self):
        with pytest.raises(ValidationError, match="base_delay.*must not exceed"):
            LLMRetryConfig(base_delay=100, max_delay=10)


@pytest.mark.unit
class TestLoggingValidation:
    def test_valid_levels(self):
        for level in ["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"]:
            result = LoggingConfig(level=level)
            assert result.level == level

    def test_invalid_level_raises(self):
        with pytest.raises(ValidationError, match="level"):
            LoggingConfig(level="VERBOSE")


@pytest.mark.unit
class TestTypeValidation:
    def test_chunk_size_string_raises(self):
        with pytest.raises(ValidationError):
            ChunkerConfig(chunk_size="not_a_number")

    def test_temperature_out_of_range_raises(self):
        config = _minimal_config()
        config["llm_presets"]["default"]["temperature"] = 3.0
        with pytest.raises(ValidationError, match="temperature"):
            AppConfig(**config)

    def test_batch_size_zero_raises(self):
        config = _minimal_config()
        config["embedding"] = {"model_name": "test", "batch_size": 0}
        with pytest.raises(ValidationError, match="batch_size"):
            AppConfig(**config)


@pytest.mark.unit
class TestDefaultFilling:
    def test_missing_chunker_gets_defaults(self):
        config = _minimal_config()
        result = AppConfig(**config)
        assert result.chunker.chunk_size == 512
        assert result.chunker.strategy == "fixed"

    def test_missing_retrieval_gets_defaults(self):
        config = _minimal_config()
        result = AppConfig(**config)
        assert result.retrieval.method == "vector"
        assert result.retrieval.top_k == 5

    def test_missing_logging_gets_defaults(self):
        config = _minimal_config()
        result = AppConfig(**config)
        assert result.logging.level == "INFO"
        assert result.logging.log_dir == "logs"

    def test_partial_override_preserves_defaults(self):
        config = _minimal_config()
        config["chunker"] = {"chunk_size": 256}
        result = AppConfig(**config)
        assert result.chunker.chunk_size == 256
        assert result.chunker.strategy == "fixed"
        assert result.chunker.chunk_overlap == 0


@pytest.mark.unit
class TestLoadConfigIntegration:
    def test_load_config_validates_and_returns_dict(self, tmp_path):
        config_file = tmp_path / "test_config.yaml"
        config_data = _minimal_config()
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_config(str(config_file))

        assert isinstance(result, dict)
        assert result["active_mode"] == "default"

    def test_load_config_invalid_raises_configuration_error(self, tmp_path):
        config_file = tmp_path / "bad_config.yaml"
        config_data = _minimal_config()
        config_data["chunker"] = {"chunk_size": 0}
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            load_config(str(config_file))

    def test_load_config_active_mode_mismatch_raises(self, tmp_path):
        config_file = tmp_path / "mode_mismatch.yaml"
        config_data = _minimal_config()
        config_data["active_mode"] = "nonexistent_preset"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        with pytest.raises(ConfigurationError, match="Invalid configuration"):
            load_config(str(config_file))

    def test_load_config_extra_fields_allowed(self, tmp_path):
        config_file = tmp_path / "extra.yaml"
        config_data = _minimal_config()
        config_data["custom_top_level"] = "hello"
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_config(str(config_file))
        assert result["active_mode"] == "default"

    def test_load_config_backward_compatible_simple_dict(self, tmp_path):
        config_file = tmp_path / "simple.yaml"
        config_data = {"key": "value", "nested": {"inner": 42}}
        config_file.write_text(yaml.dump(config_data), encoding="utf-8")

        result = load_config(str(config_file))

        assert isinstance(result, dict)
        assert result["key"] == "value"
