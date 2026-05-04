from __future__ import annotations

import pytest


class TestEvaluateSingle:
    def test_basic_metrics_returned(self):
        from src.core.ops.evaluate import evaluate_single

        result = evaluate_single(
            question="What is ROE?",
            answer="ROE is Return on Equity.",
            contexts=["ROE measures profitability."],
        )

        assert "context_relevance" in result
        assert "answer_relevancy" in result
        assert 0.0 <= result["context_relevance"] <= 1.0
        assert 0.0 <= result["answer_relevancy"] <= 1.0

    def test_hit_rate_with_expected_sources(self):
        from src.core.ops.evaluate import evaluate_single

        result = evaluate_single(
            question="What is ROE?",
            answer="ROE is Return on Equity.",
            contexts=["Source: annual_report.pdf. ROE is..."],
            expected_sources=["annual_report.pdf"],
        )

        assert "hit_rate" in result
        assert result["hit_rate"] == 1.0

    def test_hit_rate_miss(self):
        from src.core.ops.evaluate import evaluate_single

        result = evaluate_single(
            question="What is ROE?",
            answer="ROE is Return on Equity.",
            contexts=["Some unrelated text."],
            expected_sources=["annual_report.pdf"],
        )

        assert "hit_rate" in result
        assert result["hit_rate"] == 0.0

    def test_hit_rate_not_computed_without_expected_sources(self):
        from src.core.ops.evaluate import evaluate_single

        result = evaluate_single(
            question="What is ROE?",
            answer="ROE is Return on Equity.",
            contexts=["Some context."],
        )

        assert "hit_rate" not in result

    def test_empty_question_raises(self):
        from src.core.ops.evaluate import evaluate_single

        with pytest.raises(ValueError, match="question must be a non-empty string"):
            evaluate_single(question="", answer="ans", contexts=[])

    def test_empty_answer_raises(self):
        from src.core.ops.evaluate import evaluate_single

        with pytest.raises(ValueError, match="answer must be a non-empty string"):
            evaluate_single(question="q", answer="", contexts=[])

    def test_metrics_filter(self):
        from src.core.ops.evaluate import evaluate_single

        result = evaluate_single(
            question="What is ROE?",
            answer="ROE is Return on Equity.",
            contexts=["ROE context."],
            metrics=["answer_relevancy"],
        )

        assert "answer_relevancy" in result
        assert "context_relevance" not in result

    def test_perfect_overlap(self):
        from src.core.ops.evaluate import evaluate_single

        result = evaluate_single(
            question="ROE equity return",
            answer="ROE equity return",
            contexts=["ROE equity return"],
        )

        assert result["answer_relevancy"] == 1.0

    def test_no_overlap(self):
        from src.core.ops.evaluate import evaluate_single

        result = evaluate_single(
            question="alpha beta gamma",
            answer="delta epsilon zeta",
            contexts=["delta epsilon zeta"],
        )

        assert result["answer_relevancy"] == 0.0
