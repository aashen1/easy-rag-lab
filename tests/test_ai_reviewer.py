import json
from unittest.mock import MagicMock, patch

from scripts.ai_reviewer import AIReviewer


class TestAIReviewerParseResponse:
    def setup_method(self):
        self.config = {"llm_presets": {"default": {}}, "active_mode": "default"}
        self.reviewer = AIReviewer(self.config)

    def test_parse_valid_json_response(self):
        raw = """```json
{
  "question_clarity": {"score": 4, "reason": "清晰"},
  "answer_accuracy": {"score": 5, "reason": "准确"},
  "answer_completeness": {"score": 4, "reason": "完整"},
  "source_consistency": {"score": 5, "reason": "一致"},
  "overall_comment": "高质量",
  "suggested_action": "approve"
}
```"""
        result = self.reviewer._parse_review_response(raw)
        assert result["overall_score"] == 4.5
        assert result["tier"] == "A"
        assert result["suggested_action"] == "approve"

    def test_parse_bare_json_response(self):
        raw = '{"question_clarity": {"score": 3, "reason": "一般"}, "answer_accuracy": {"score": 3, "reason": "一般"}, "answer_completeness": {"score": 3, "reason": "一般"}, "source_consistency": {"score": 3, "reason": "一般"}, "overall_comment": "中等", "suggested_action": "review"}'
        result = self.reviewer._parse_review_response(raw)
        assert result["overall_score"] == 3.0
        assert result["tier"] == "B"
        assert result["suggested_action"] == "review"

    def test_parse_low_score_tier_c(self):
        raw = '{"question_clarity": {"score": 2, "reason": "模糊"}, "answer_accuracy": {"score": 1, "reason": "错误"}, "answer_completeness": {"score": 2, "reason": "不完整"}, "source_consistency": {"score": 1, "reason": "不一致"}, "overall_comment": "低质量", "suggested_action": "reject"}'
        result = self.reviewer._parse_review_response(raw)
        assert result["overall_score"] == 1.5
        assert result["tier"] == "C"
        assert result["suggested_action"] == "reject"

    def test_parse_invalid_json_returns_default(self):
        raw = "This is not JSON at all"
        result = self.reviewer._parse_review_response(raw)
        assert result["overall_score"] == 3.0
        assert result["tier"] == "B"
        assert result["suggested_action"] == "review"

    def test_parse_partial_json(self):
        raw = '{"question_clarity": {"score": 4, "reason": "ok"}, "answer_accuracy": {"score": 4, "reason": "ok"}}'
        result = self.reviewer._parse_review_response(raw)
        assert "question_clarity" in result["dimensions"]
        assert "answer_accuracy" in result["dimensions"]
        assert result["overall_score"] == 3.5

    def test_parse_invalid_suggested_action_defaults_to_review(self):
        raw = '{"question_clarity": {"score": 4, "reason": ""}, "answer_accuracy": {"score": 4, "reason": ""}, "answer_completeness": {"score": 4, "reason": ""}, "source_consistency": {"score": 4, "reason": ""}, "suggested_action": "maybe"}'
        result = self.reviewer._parse_review_response(raw)
        assert result["suggested_action"] == "review"


class TestAIReviewerClassifyTier:
    def setup_method(self):
        self.config = {"llm_presets": {"default": {}}, "active_mode": "default"}
        self.reviewer = AIReviewer(self.config)

    def test_tier_a_high_score(self):
        result = {"overall_score": 4.5}
        assert self.reviewer.classify_tier(result) == "A"

    def test_tier_a_threshold(self):
        result = {"overall_score": 4.0}
        assert self.reviewer.classify_tier(result) == "A"

    def test_tier_b_mid_score(self):
        result = {"overall_score": 3.5}
        assert self.reviewer.classify_tier(result) == "B"

    def test_tier_b_threshold(self):
        result = {"overall_score": 3.0}
        assert self.reviewer.classify_tier(result) == "B"

    def test_tier_c_low_score(self):
        result = {"overall_score": 2.5}
        assert self.reviewer.classify_tier(result) == "C"

    def test_tier_c_zero_score(self):
        result = {"overall_score": 0.0}
        assert self.reviewer.classify_tier(result) == "C"


class TestAIReviewerClampScore:
    def test_normal_score(self):
        assert AIReviewer._clamp_score(3) == 3.0

    def test_score_below_minimum(self):
        assert AIReviewer._clamp_score(0) == 1.0

    def test_score_above_maximum(self):
        assert AIReviewer._clamp_score(6) == 5.0

    def test_negative_score(self):
        assert AIReviewer._clamp_score(-1) == 1.0

    def test_float_score(self):
        assert AIReviewer._clamp_score(3.7) == 3.7

    def test_string_score(self):
        assert AIReviewer._clamp_score("4") == 4.0

    def test_invalid_score(self):
        assert AIReviewer._clamp_score("abc") == 3.0

    def test_none_score(self):
        assert AIReviewer._clamp_score(None) == 3.0


class TestAIReviewerExtractJson:
    def test_extract_from_code_fence(self):
        text = '```json\n{"key": "value"}\n```'
        assert AIReviewer._extract_json(text) == '{"key": "value"}'

    def test_extract_from_bare_fence(self):
        text = '```\n{"key": "value"}\n```'
        assert AIReviewer._extract_json(text) == '{"key": "value"}'

    def test_extract_bare_json(self):
        text = 'Some text {"key": "value"} more text'
        assert AIReviewer._extract_json(text) == '{"key": "value"}'

    def test_no_json_returns_none(self):
        text = "No JSON here"
        assert AIReviewer._extract_json(text) is None


class TestAIReviewerGetTierSummary:
    def setup_method(self):
        self.config = {"llm_presets": {"default": {}}, "active_mode": "default"}
        self.reviewer = AIReviewer(self.config)

    def test_tier_summary(self):
        questions = [
            {"id": "q1", "metadata": {"ai_review": {"overall_score": 4.5}}},
            {"id": "q2", "metadata": {"ai_review": {"overall_score": 3.5}}},
            {"id": "q3", "metadata": {"ai_review": {"overall_score": 2.0}}},
        ]
        summary = self.reviewer.get_tier_summary(questions)
        assert "q1" in summary["A"]
        assert "q2" in summary["B"]
        assert "q3" in summary["C"]

    def test_tier_summary_no_review(self):
        questions = [
            {"id": "q1", "metadata": {}},
        ]
        summary = self.reviewer.get_tier_summary(questions)
        assert summary == {"A": [], "B": [], "C": []}


class TestAIReviewerReviewQuestion:
    def setup_method(self):
        self.config = {"llm_presets": {"default": {}}, "active_mode": "default"}

    def test_cached_review_returned(self):
        reviewer = AIReviewer(self.config)
        cached_result = {
            "overall_score": 4.0,
            "tier": "A",
            "suggested_action": "approve",
        }
        question = {
            "id": "q1",
            "question": "test",
            "answer": "test",
            "question_type": "single_fact",
            "ground_truth_excerpt": "test",
            "metadata": {"ai_review": cached_result},
        }
        result = reviewer.review_question(question)
        assert result == cached_result

    @patch("scripts.ai_reviewer.create_llm_client")
    @patch("scripts.ai_reviewer.get_llm_config")
    def test_review_question_llm_call(self, mock_get_config, mock_create_client):
        mock_config = {
            "model_name": "test-model",
            "temperature": 0.3,
            "max_tokens": 1024,
            "api_key": "test-key",
            "base_url": "https://api.test.com/anthropic",
        }
        mock_get_config.return_value = mock_config

        mock_response = MagicMock()
        mock_response.content = [
            MagicMock(
                text=json.dumps(
                    {
                        "question_clarity": {"score": 4, "reason": "清晰"},
                        "answer_accuracy": {"score": 4, "reason": "准确"},
                        "answer_completeness": {"score": 4, "reason": "完整"},
                        "source_consistency": {"score": 4, "reason": "一致"},
                        "overall_comment": "良好",
                        "suggested_action": "approve",
                    }
                )
            )
        ]
        mock_client = MagicMock()
        mock_client.messages.create.return_value = mock_response
        mock_create_client.return_value = mock_client

        reviewer = AIReviewer(self.config)
        question = {
            "id": "q1",
            "question": "营收多少？",
            "answer": "100亿",
            "question_type": "single_fact",
            "ground_truth_excerpt": "营收100亿元",
            "metadata": {},
        }
        result = reviewer.review_question(question)
        assert result["overall_score"] == 4.0
        assert result["tier"] == "A"
        assert "reviewed_at" in result

    @patch("scripts.ai_reviewer.create_llm_client")
    @patch("scripts.ai_reviewer.get_llm_config")
    def test_review_question_llm_error(self, mock_get_config, mock_create_client):
        mock_get_config.return_value = {
            "model_name": "test-model",
            "temperature": 0.3,
            "max_tokens": 1024,
            "api_key": "test-key",
            "base_url": "https://api.test.com/anthropic",
        }
        mock_client = MagicMock()
        mock_client.messages.create.side_effect = Exception("API error")
        mock_create_client.return_value = mock_client

        reviewer = AIReviewer(self.config)
        question = {
            "id": "q1",
            "question": "test",
            "answer": "test",
            "question_type": "single_fact",
            "ground_truth_excerpt": "test",
            "metadata": {},
        }
        result = reviewer.review_question(question)
        assert "error" in result
        assert result["tier"] == "C"
