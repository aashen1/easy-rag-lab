from unittest.mock import MagicMock, patch

import pytest

from src.exceptions import GenerationError
from src.generator import Generator, clean_source_name
from src.token_tracker import TokenTracker

_TEST_BASE_URL = "https://api.test.example.com"
_TEST_MODEL_NAME = "test-model"


def _make_generator(**kwargs):
    kwargs.setdefault("api_key", "test-key")
    kwargs.setdefault("base_url", _TEST_BASE_URL)
    kwargs.setdefault("model_name", _TEST_MODEL_NAME)
    return Generator(**kwargs)


@pytest.mark.unit
class TestGenerator:
    @patch("src.llm_client.Anthropic")
    def test_generate_success(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        answer = generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        assert answer == "This is a test answer from the LLM."
        mock_anthropic_client.messages.create.assert_called_once()

    @patch("src.llm_client.Anthropic")
    def test_generate_empty_query(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with pytest.raises(GenerationError, match="Query must be a non-empty string"):
            generator.generate(query="", contexts=["some context"])

    @patch("src.llm_client.Anthropic")
    def test_generate_non_string_query(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with pytest.raises(GenerationError, match="Query must be a non-empty string"):
            generator.generate(query=123, contexts=["some context"])

    @patch("src.llm_client.Anthropic")
    def test_generate_empty_contexts_warning(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with patch("src.generator.logger") as mock_logger:
            answer = generator.generate(query="What is the revenue?", contexts=[])
            mock_logger.warning.assert_any_call("No contexts provided for generation")
        assert answer == "This is a test answer from the LLM."

    @patch("src.llm_client.Anthropic")
    def test_generate_api_error(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_client.messages.create.side_effect = Exception("API timeout")
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with pytest.raises(GenerationError, match="Failed to generate answer"):
            generator.generate(query="What is the revenue?", contexts=["some context"])


@pytest.mark.unit
class TestGeneratorChatHistory:
    @patch("src.llm_client.Anthropic")
    def test_chat_history_prepended_to_messages(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        chat_history = [
            {"role": "user", "content": "What is the revenue?"},
            {"role": "assistant", "content": "Revenue was 100 billion."},
        ]
        generator.generate(
            query="What about profit?",
            contexts=["Profit was 50 billion."],
            chat_history=chat_history,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 3
        assert messages[0]["role"] == "user"
        assert "revenue" in messages[0]["content"].lower()
        assert messages[1]["role"] == "assistant"
        assert messages[1]["content"] == "Revenue was 100 billion."
        assert messages[2]["role"] == "user"
        assert "profit" in messages[2]["content"].lower()

    @patch("src.llm_client.Anthropic")
    def test_no_chat_history_single_message(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 1
        assert messages[0]["role"] == "user"

    @patch("src.llm_client.Anthropic")
    def test_empty_chat_history_same_as_none(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
            chat_history=[],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert len(messages) == 1

    @patch("src.llm_client.Anthropic")
    def test_chat_history_starts_with_assistant_auto_fixes(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        chat_history = [
            {"role": "assistant", "content": "Hello"},
            {"role": "user", "content": "What is the revenue?"},
        ]
        generator.generate(
            query="What about profit?",
            contexts=["Profit was 50 billion."],
            chat_history=chat_history,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["role"] == "user"

    @patch("src.llm_client.Anthropic")
    def test_chat_history_consecutive_same_role_merged(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        chat_history = [
            {"role": "user", "content": "Question 1"},
            {"role": "user", "content": "Question 2"},
            {"role": "assistant", "content": "Answer"},
        ]
        generator.generate(
            query="Question 3",
            contexts=["Some context."],
            chat_history=chat_history,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert messages[0]["role"] == "user"
        assert "Question 1" in messages[0]["content"]
        assert "Question 2" in messages[0]["content"]
        assert messages[1]["role"] == "assistant"
        assert messages[2]["role"] == "user"

    @patch("src.llm_client.Anthropic")
    def test_chat_history_invalid_roles_filtered(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        chat_history = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "What is the revenue?"},
            {"role": "tool", "content": "Some tool output"},
        ]
        generator.generate(
            query="What about profit?",
            contexts=["Profit was 50 billion."],
            chat_history=chat_history,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        messages = call_kwargs.kwargs["messages"]
        assert all(m["role"] in ("user", "assistant") for m in messages)

    @patch("src.llm_client.Anthropic")
    def test_generate_custom_system_prompt(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        custom_prompt = "You are a helpful assistant."
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
            system_prompt=custom_prompt,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == custom_prompt

    @patch("src.llm_client.Anthropic")
    def test_constructor_system_prompt_used_as_default(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        constructor_prompt = "You are a financial analyst."
        generator = _make_generator(system_prompt=constructor_prompt)
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == constructor_prompt

    @patch("src.llm_client.Anthropic")
    def test_null_system_prompt_falls_back_to_hardcoded(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(system_prompt=None)
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == Generator.DEFAULT_SYSTEM_PROMPT

    @patch("src.llm_client.Anthropic")
    def test_no_system_prompt_falls_back_to_hardcoded(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == Generator.DEFAULT_SYSTEM_PROMPT

    @patch("src.llm_client.Anthropic")
    def test_generate_param_overrides_constructor_default(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        constructor_prompt = "You are a financial analyst."
        override_prompt = "You are a helpful assistant."
        generator = _make_generator(system_prompt=constructor_prompt)
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
            system_prompt=override_prompt,
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        assert call_kwargs.kwargs["system"] == override_prompt

    @patch("src.llm_client.Anthropic")
    def test_generate_token_tracker_records(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        tracker = TokenTracker()
        generator = _make_generator(token_tracker=tracker)
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
        assert record.model_name == _TEST_MODEL_NAME
        assert record.usage.input_tokens == 100
        assert record.usage.output_tokens == 50
        assert record.metadata["question_id"] == "q1"

    @patch("src.llm_client.Anthropic")
    def test_sources_included_in_context_format(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion.", "Profit was 50 billion."],
            sources=[
                "research_reports/2026年光伏行业分析.md",
                "annual_reports/贵州茅台2023年报.pages.json",
            ],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "参考资料 1（来源：2026年光伏行业分析）:" in user_content
        assert "参考资料 2（来源：贵州茅台2023年报）:" in user_content

    @patch("src.llm_client.Anthropic")
    def test_sources_none_preserves_old_format(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
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
    def test_sources_empty_list_preserves_old_format(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
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
    def test_sources_fewer_than_contexts_uses_unknown(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
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
    def test_truncate_contexts_removes_tail_chunks(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=250, max_tokens=10)
        contexts = ["short", "word " * 200, "another " * 200]
        result = generator._truncate_contexts(contexts, "system", "query")
        assert len(result) < len(contexts)
        assert result[0] == "short"

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_no_limit_when_null(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=None)
        contexts = ["a" * 10000, "b" * 10000, "c" * 10000]
        result = generator._truncate_contexts(contexts, "system", "query")
        assert result == contexts

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_fits_within_limit(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=100000, max_tokens=1024)
        contexts = ["short context", "another short context"]
        result = generator._truncate_contexts(contexts, "system", "query")
        assert result == contexts

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_overhead_exceeds_returns_empty(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=50, max_tokens=10)
        long_system = "x" * 500
        result = generator._truncate_contexts(["some context"], long_system, "query")
        assert result == []

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_logs_warning(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=250, max_tokens=10)
        with patch("src.generator.logger") as mock_logger:
            long_contexts = ["word " * 200, "another " * 200]
            generator._truncate_contexts(long_contexts, "system", "query")
            warning_calls = [str(c) for c in mock_logger.warning.call_args_list]
            assert any("Context truncated" in c for c in warning_calls)

    @patch("src.llm_client.Anthropic")
    def test_truncate_contexts_available_zero_returns_empty(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=200, max_tokens=1024)
        result = generator._truncate_contexts(["context"], "system", "query")
        assert result == []

    @patch("src.llm_client.Anthropic")
    def test_generate_with_truncation_uses_truncated_contexts(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=100, max_tokens=10)
        with patch.object(
            generator, "_truncate_contexts", return_value=["truncated"]
        ) as mock_truncate:
            generator.generate(
                query="What is the revenue?",
                contexts=["Revenue was 100 billion.", "Profit was 50 billion."],
            )
            mock_truncate.assert_called_once()
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "truncated" in user_content
        assert "Profit was 50 billion" not in user_content


@pytest.mark.unit
class TestCleanSourceName:
    def test_pages_json_extension(self):
        assert (
            clean_source_name(
                "research_reports/2026现代女性精力管理现状报告.pages.json"
            )
            == "2026现代女性精力管理现状报告"
        )

    def test_md_extension(self):
        assert (
            clean_source_name("annual_reports/2023/贵州茅台2023年年度报告.md")
            == "贵州茅台2023年年度报告"
        )

    def test_json_extension(self):
        assert (
            clean_source_name("annual_reports/2023/贵州茅台2023年年度报告.json")
            == "贵州茅台2023年年度报告"
        )

    def test_simple_txt_extension(self):
        assert clean_source_name("simple_name.txt") == "simple_name"

    def test_pages_json_with_annual_reports(self):
        assert (
            clean_source_name("annual_reports/2023/贵州茅台2023年年度报告.pages.json")
            == "贵州茅台2023年年度报告"
        )

    def test_filename_only(self):
        assert clean_source_name("report.pages.json") == "report"

    def test_no_extension(self):
        assert (
            clean_source_name("annual_reports/2023/贵州茅台2023年年度报告")
            == "贵州茅台2023年年度报告"
        )


@pytest.mark.unit
class TestGeneratorBoundaryConditions:
    @patch("src.llm_client.Anthropic")
    def test_allow_no_contexts_no_warning(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with patch("src.generator.logger") as mock_logger:
            generator.generate(
                query="What is the revenue?", contexts=[], allow_no_contexts=True
            )
            assert not any(
                "No contexts provided" in str(c)
                for c in mock_logger.warning.call_args_list
            )

    @patch("src.llm_client.Anthropic")
    def test_none_contexts_raises(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with pytest.raises(GenerationError, match="Failed to generate answer"):
            generator.generate(query="What is the revenue?", contexts=None)

    @patch("src.llm_client.Anthropic")
    def test_max_context_tokens_exactly_overhead(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=20, max_tokens=10)
        result = generator._truncate_contexts(["some context"], "system", "query")
        assert result == []

    @patch("src.llm_client.Anthropic")
    def test_single_context_exceeds_limit(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=250, max_tokens=10)
        long_context = ["word " * 500]
        result = generator._truncate_contexts(long_context, "system", "query")
        assert result == []

    @patch("src.llm_client.Anthropic")
    def test_all_contexts_exceed_limit(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(max_context_tokens=250, max_tokens=10)
        contexts = ["word " * 300, "another " * 300]
        result = generator._truncate_contexts(contexts, "system", "query")
        assert result == []

    @patch("src.llm_client.Anthropic")
    def test_sources_longer_than_contexts(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
            sources=[
                "research_reports/2026年光伏行业分析.md",
                "annual_reports/贵州茅台2023年报.md",
            ],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "参考资料 1（来源：2026年光伏行业分析）:" in user_content

    @patch("src.llm_client.Anthropic")
    def test_sources_contains_empty_string(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion.", "Profit was 50 billion."],
            sources=["", "annual_reports/贵州茅台2023年报.md"],
        )
        call_kwargs = mock_anthropic_client.messages.create.call_args
        user_content = call_kwargs.kwargs["messages"][0]["content"]
        assert "参考资料 1（来源：）:" in user_content
        assert "参考资料 2（来源：贵州茅台2023年报）:" in user_content

    @patch("src.llm_client.Anthropic")
    def test_no_token_tracker_no_error(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator(token_tracker=None)
        answer = generator.generate(
            query="What is the revenue?", contexts=["Revenue was 100 billion."]
        )
        assert answer == "This is a test answer from the LLM."
        assert generator.token_tracker is None

    @patch("src.llm_client.Anthropic")
    def test_generate_returns_answer(self, mock_anthropic_cls, mock_anthropic_client):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        answer = generator.generate(
            query="What is the revenue?",
            contexts=["Revenue was 100 billion."],
        )
        assert isinstance(answer, str)
        assert len(answer) > 0


@pytest.mark.unit
class TestGeneratorExceptionPaths:
    @patch("src.llm_client.Anthropic")
    def test_api_timeout_raises_generation_error(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_client.messages.create.side_effect = TimeoutError(
            "Connection timed out"
        )
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with pytest.raises(GenerationError, match="Failed to generate answer"):
            generator.generate(query="What is the revenue?", contexts=["some context"])

    @patch("src.llm_client.Anthropic")
    def test_auth_failure_raises_generation_error(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_client.messages.create.side_effect = Exception(
            "Authentication failed: invalid API key"
        )
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with pytest.raises(GenerationError, match="Failed to generate answer"):
            generator.generate(query="What is the revenue?", contexts=["some context"])

    @patch("src.llm_client.Anthropic")
    def test_empty_response_content_raises_generation_error(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_content = MagicMock()
        mock_content.text = ""
        mock_message = MagicMock()
        mock_message.content = [mock_content]
        mock_message.usage.input_tokens = 50
        mock_message.usage.output_tokens = 0
        mock_anthropic_client.messages.create.return_value = mock_message
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        answer = generator.generate(
            query="What is the revenue?", contexts=["some context"]
        )
        assert answer == ""

    @patch("src.llm_client.Anthropic")
    def test_none_query_raises_generation_error(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with pytest.raises(GenerationError, match="Query must be a non-empty string"):
            generator.generate(query=None, contexts=["some context"])

    @patch("src.llm_client.Anthropic")
    def test_whitespace_only_query_proceeds(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        answer = generator.generate(query="   ", contexts=["some context"])
        assert answer == "This is a test answer from the LLM."

    @patch("src.llm_client.Anthropic")
    def test_rate_limit_raises_generation_error(
        self, mock_anthropic_cls, mock_anthropic_client
    ):
        mock_anthropic_client.messages.create.side_effect = Exception(
            "Rate limit exceeded: 429 Too Many Requests"
        )
        mock_anthropic_cls.return_value = mock_anthropic_client
        generator = _make_generator()
        with pytest.raises(GenerationError, match="Failed to generate answer"):
            generator.generate(query="What is the revenue?", contexts=["some context"])
