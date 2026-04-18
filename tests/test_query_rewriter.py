from unittest.mock import MagicMock, patch

import pytest

from src.query_rewriter import QueryRewriter


@pytest.mark.unit
class TestQueryRewriter:
    def test_invalid_strategy_raises(self):
        with pytest.raises(ValueError, match="strategy must be"):
            QueryRewriter(strategy="invalid")

    def test_empty_query_raises(self):
        rewriter = object.__new__(QueryRewriter)
        with pytest.raises(ValueError, match="Query must be a non-empty string"):
            rewriter.rewrite("")

    def test_non_string_query_raises(self):
        rewriter = object.__new__(QueryRewriter)
        with pytest.raises(ValueError, match="Query must be a non-empty string"):
            rewriter.rewrite(123)

    @patch("src.query_rewriter.QueryRewriter._call_llm")
    def test_hyde_rewrite(self, mock_call_llm):
        mock_call_llm.return_value = (
            "贵州茅台2023年营业收入约为1500亿元，同比增长16.5%。",
            None,
        )

        rewriter = QueryRewriter(strategy="hyde")
        result = rewriter.rewrite("茅台2023年营收多少？")

        assert result["strategy"] == "hyde"
        assert result["original_query"] == "茅台2023年营收多少？"
        assert "rewritten" in result
        assert isinstance(result["rewritten"], str)
        assert len(result["rewritten"]) > 0

    @patch("src.query_rewriter.QueryRewriter._call_llm")
    def test_multi_query_rewrite(self, mock_call_llm):
        mock_call_llm.return_value = (
            "贵州茅台2023年营业收入\n茅台股份年度收入数据\n茅台集团营收增长情况",
            None,
        )

        rewriter = QueryRewriter(strategy="multi_query", num_queries=3)
        result = rewriter.rewrite("茅台2023年营收多少？")

        assert result["strategy"] == "multi_query"
        assert result["original_query"] == "茅台2023年营收多少？"
        assert isinstance(result["rewritten"], list)
        assert len(result["rewritten"]) <= 3

    @patch("src.query_rewriter.QueryRewriter._call_llm")
    def test_multi_query_strips_numbering(self, mock_call_llm):
        mock_call_llm.return_value = (
            "1. 贵州茅台2023年营业收入\n2. 茅台股份年度收入\n3. 茅台集团营收",
            None,
        )

        rewriter = QueryRewriter(strategy="multi_query", num_queries=3)
        result = rewriter.rewrite("茅台营收")

        for q in result["rewritten"]:
            assert not q[0].isdigit() or "." not in q[:3]

    @patch("src.query_rewriter.QueryRewriter._call_llm")
    def test_hyde_uses_correct_prompt(self, mock_call_llm):
        mock_call_llm.return_value = ("test answer", None)

        rewriter = QueryRewriter(strategy="hyde")
        rewriter.rewrite("茅台营收")

        call_args = mock_call_llm.call_args
        prompt = call_args[0][0]
        assert "茅台营收" in prompt
        assert "详细的回答" in prompt

    @patch("src.query_rewriter.QueryRewriter._call_llm")
    def test_multi_query_uses_correct_prompt(self, mock_call_llm):
        mock_call_llm.return_value = ("子问题1\n子问题2\n子问题3", None)

        rewriter = QueryRewriter(strategy="multi_query", num_queries=3)
        rewriter.rewrite("茅台营收")

        call_args = mock_call_llm.call_args
        prompt = call_args[0][0]
        assert "茅台营收" in prompt
        assert "3" in prompt
        assert "子问题" in prompt or "改写" in prompt

    @patch("src.query_rewriter.QueryRewriter._call_llm")
    def test_rewrite_with_token_tracker(self, mock_call_llm):
        from src.token_tracker import DetailedTokenUsage, TokenTracker

        mock_usage = DetailedTokenUsage(input_tokens=100, output_tokens=50)
        mock_call_llm.return_value = ("test answer", mock_usage.to_dict())

        tracker = TokenTracker()
        rewriter = QueryRewriter(strategy="hyde", token_tracker=tracker)
        result = rewriter.rewrite("茅台营收")

        assert "token_usage" in result

    @patch("src.query_rewriter.QueryRewriter._call_llm")
    def test_multi_query_limits_num_queries(self, mock_call_llm):
        mock_call_llm.return_value = (
            "问题1\n问题2\n问题3\n问题4\n问题5",
            None,
        )

        rewriter = QueryRewriter(strategy="multi_query", num_queries=2)
        result = rewriter.rewrite("茅台营收")

        assert len(result["rewritten"]) <= 2

    @patch("src.query_rewriter.QueryRewriter._call_llm")
    def test_llm_failure_raises(self, mock_call_llm):
        mock_call_llm.side_effect = Exception("API error")

        rewriter = QueryRewriter(strategy="hyde")
        with pytest.raises(Exception, match="Failed to rewrite query"):
            rewriter.rewrite("茅台营收")
