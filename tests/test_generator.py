import pytest
from unittest.mock import MagicMock, patch

from src.generator import Generator
from src.token_tracker import TokenTracker


@pytest.mark.unit
class TestGenerator:

    @patch("src.generator.Anthropic")
    def test_generate_success(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        answer = generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        assert answer == "This is a test answer from the LLM."
        mock_anthropic_client.messages.create.assert_called_once()

    @patch("src.generator.Anthropic")
    def test_generate_empty_query(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        with pytest.raises(ValueError, match="Query must be a non-empty string"):
            generator.generate(query="", contexts=["some context"])

    @patch("src.generator.Anthropic")
    def test_generate_non_string_query(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        with pytest.raises(ValueError, match="Query must be a non-empty string"):
            generator.generate(query=123, contexts=["some context"])

    @patch("src.generator.Anthropic")
    def test_generate_empty_contexts_warning(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        with patch("src.generator.logger") as mock_logger:
            answer = generator.generate(query="What is the revenue?", contexts=[])
            mock_logger.warning.assert_any_call("No contexts provided for generation")
        assert answer == "This is a test answer from the LLM."

    @patch("src.generator.Anthropic")
    def test_generate_api_error(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_client.messages.create.side_effect = Exception("API timeout")
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        with pytest.raises(Exception, match="Failed to generate answer"):
            generator.generate(query="What is the revenue?", contexts=["some context"])

    @patch("src.generator.Anthropic")
    def test_generate_custom_system_prompt(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        custom_prompt = "You are a helpful assistant."
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
            system_prompt=custom_prompt,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == custom_prompt

    @patch("src.generator.Anthropic")
    def test_generate_token_tracker_records(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        tracker = TokenTracker()
        generator = Generator(api_key="test-key", token_tracker=tracker)
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
            category="rag_qa",
            question_id="q1",
        )
        assert tracker.record_count == 1
        records = tracker.get_records_by_category("rag_qa")
        assert len(records) == 1
        record = records[0]
        assert record.category == "rag_qa"
        assert record.model_name == "LongCat-Flash-Lite"
        assert record.usage.input_tokens == 100
        assert record.usage.output_tokens == 50
        assert record.metadata["question_id"] == "q1"
