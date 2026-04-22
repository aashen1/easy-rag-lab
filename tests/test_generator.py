from unittest.mock import patch

import pytest

from src.generator import Generator
from src.token_tracker import TokenTracker


@pytest.mark.unit
class TestGenerator:

    @patch("src.llm_client.Anthropic")
    def test_generate_success(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        answer = generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        assert answer == "This is a test answer from the LLM."
        mock_anthropic_client.messages.create.assert_called_once()

    @patch("src.llm_client.Anthropic")
    def test_generate_empty_query(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        with pytest.raises(ValueError, match="Query must be a non-empty string"):
            generator.generate(query="", contexts=["some context"])

    @patch("src.llm_client.Anthropic")
    def test_generate_non_string_query(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        with pytest.raises(ValueError, match="Query must be a non-empty string"):
            generator.generate(query=123, contexts=["some context"])

    @patch("src.llm_client.Anthropic")
    def test_generate_empty_contexts_warning(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        with patch("src.generator.logger") as mock_logger:
            answer = generator.generate(query="What is the revenue?", contexts=[])
            mock_logger.warning.assert_any_call("No contexts provided for generation")
        assert answer == "This is a test answer from the LLM."

    @patch("src.llm_client.Anthropic")
    def test_generate_api_error(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_client.messages.create.side_effect = Exception("API timeout")
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        with pytest.raises(Exception, match="Failed to generate answer"):
            generator.generate(query="What is the revenue?", contexts=["some context"])

    @patch("src.llm_client.Anthropic")
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

    @patch("src.llm_client.Anthropic")
    def test_constructor_system_prompt_used_as_default(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        constructor_prompt = "You are a financial analyst."
        generator = Generator(api_key="test-key", system_prompt=constructor_prompt)
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == constructor_prompt

    @patch("src.llm_client.Anthropic")
    def test_null_system_prompt_falls_back_to_hardcoded(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key", system_prompt=None)
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == Generator.DEFAULT_SYSTEM_PROMPT

    @patch("src.llm_client.Anthropic")
    def test_no_system_prompt_falls_back_to_hardcoded(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == Generator.DEFAULT_SYSTEM_PROMPT

    @patch("src.llm_client.Anthropic")
    def test_generate_param_overrides_constructor_default(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        constructor_prompt = "You are a financial analyst."
        override_prompt = "You are a helpful assistant."
        generator = Generator(api_key="test-key", system_prompt=constructor_prompt)
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
            system_prompt=override_prompt,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == override_prompt

    @patch("src.llm_client.Anthropic")
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

    @patch("src.llm_client.Anthropic")
    def test_sources_included_in_context_format(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion.", "Profit was 50 billion."],
            sources=[
                "research_reports/2026年光伏行业分析.md",
                "annual_reports/贵州茅台2023年报.md",
            ],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "参考资料 1（来源：2026年光伏行业分析）:" in user_content
        assert "参考资料 2（来源：贵州茅台2023年报）:" in user_content

    @patch("src.llm_client.Anthropic")
    def test_sources_none_preserves_old_format(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion.", "Profit was 50 billion."],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "参考资料 1:\n" in user_content
        assert "参考资料 2:\n" in user_content
        assert "来源" not in user_content

    @patch("src.llm_client.Anthropic")
    def test_sources_empty_list_preserves_old_format(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
            sources=[],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "参考资料 1:\n" in user_content
        assert "来源" not in user_content

    @patch("src.llm_client.Anthropic")
    def test_sources_fewer_than_contexts_uses_unknown(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key")
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion.", "Profit was 50 billion."],
            sources=["research_reports/2026年光伏行业分析.md"],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "参考资料 1（来源：2026年光伏行业分析）:" in user_content
        assert "参考资料 2（来源：未知）:" in user_content


@pytest.mark.unit
class TestTruncateContexts:

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_removes_tail_chunks(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key", max_context_tokens=250, max_tokens=10)
        contexts = ["short", "word " * 200, "another " * 200]
        result = generator._truncate_contexts(contexts, "system", "query")
        assert len(result) < len(contexts)
        assert result[0] == "short"

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_no_limit_when_null(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key", max_context_tokens=None)
        contexts = ["a" * 10000, "b" * 10000, "c" * 10000]
        result = generator._truncate_contexts(contexts, "system", "query")
        assert result == contexts

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_fits_within_limit(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key", max_context_tokens=100000, max_tokens=1024)
        contexts = ["short context", "another short context"]
        result = generator._truncate_contexts(contexts, "system", "query")
        assert result == contexts

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_overhead_exceeds_returns_empty(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key", max_context_tokens=50, max_tokens=10)
        long_system = "x" * 500
        result = generator._truncate_contexts(["some context"], long_system, "query")
        assert result == []

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_logs_warning(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key", max_context_tokens=250, max_tokens=10)
        with patch("src.generator.logger") as mock_logger:
            long_contexts = ["word " * 200, "another " * 200]
            generator._truncate_contexts(long_contexts, "system", "query")
            warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
            assert any("Context truncated" in c for c in warning_calls)

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_available_zero_returns_empty(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key", max_context_tokens=200, max_tokens=1024)
        result = generator._truncate_contexts(["context"], "system", "query")
        assert result == []

    @patch("src.llm_client.Anthropic")
    def test_generate_with_truncation_uses_truncated_contexts(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = Generator(api_key="test-key", max_context_tokens=100, max_tokens=10)
        with patch.object(generator, "_truncate_contexts", return_value=["truncated"]) as mock_truncate:
            generator.generate(
                query="What is the revenue?",
                contexts=["Revenue was 100 billion.", "Profit was 50 billion."],
            )
            mock_truncate.assert_called_once()
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "truncated" in user_content
        assert "Profit was 50 billion" not in user_content
