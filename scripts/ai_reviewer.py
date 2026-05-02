"""AI-powered pre-review module for golden test set questions.

Uses LLM to evaluate question quality across multiple dimensions,
producing scores and tier classifications that enable smart filtering
before human review.

Usage:
    from scripts.ai_reviewer import AIReviewer

    reviewer = AIReviewer(config)
    results = reviewer.review_questions(questions)
    tier = reviewer.classify_tier(results[0])
"""

from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

from loguru import logger

from src.llm_retry import call_with_retry
from src.utils import create_llm_client, get_llm_config

REVIEW_PROMPT_TEMPLATE = """你是一个金融研报问答系统的质量审核专家。请评估以下问答对的质量。

评估维度（每项1-5分）：
1. question_clarity: 问题是否清晰、无歧义、可独立理解
2. answer_accuracy: 答案是否与提供的原文片段(ground_truth_excerpt)一致
3. answer_completeness: 答案是否充分回答了问题
4. source_consistency: 原文片段是否真正支撑了答案

题目信息：
- 问题类型: {question_type}
- 问题: {question}
- 答案: {answer}
- 原文片段: {ground_truth_excerpt}

请以JSON格式返回评分和理由：
{{
  "question_clarity": {{"score": X, "reason": "..."}},
  "answer_accuracy": {{"score": X, "reason": "..."}},
  "answer_completeness": {{"score": X, "reason": "..."}},
  "source_consistency": {{"score": X, "reason": "..."}},
  "overall_comment": "一句话总结",
  "suggested_action": "approve/review/reject"
}}"""

TIER_A_THRESHOLD = 4.0
TIER_B_THRESHOLD = 3.0
BATCH_SIZE = 5


class AIReviewer:
    """AI-powered question quality reviewer using LLM.

    Evaluates golden test set questions across four dimensions:
    question clarity, answer accuracy, answer completeness,
    and source consistency. Produces tier classifications
    (A/B/C) for smart filtering before human review.

    Args:
        config: Application configuration dictionary.
        llm_preset: Name of the LLM preset to use. Defaults to None
            (uses active_mode from config).
    """

    def __init__(self, config: dict[str, Any], llm_preset: str | None = None) -> None:
        self.config = config
        self.llm_preset = llm_preset
        self._client = None
        self._llm_config = None

    @property
    def llm_config(self) -> dict[str, Any]:
        """Resolved LLM configuration dictionary.

        Returns:
            Dictionary with model_name, temperature, max_tokens, api_key, base_url.
        """
        if self._llm_config is None:
            self._llm_config = get_llm_config(self.config, self.llm_preset)
            test_gen = self.config.get("test_generation", {})
            self._llm_config["temperature"] = test_gen.get("temperature", 0.3)
            self._llm_config["max_tokens"] = test_gen.get("max_tokens", 1024)
        return self._llm_config

    @property
    def client(self) -> Any:
        """Lazy-initialized Anthropic SDK client.

        Returns:
            Configured Anthropic client instance.
        """
        if self._client is None:
            self._client = create_llm_client(self.llm_config, mode="sdk")
        return self._client

    def review_question(self, question: dict[str, Any]) -> dict[str, Any]:
        """Review a single question using LLM.

        Args:
            question: Question dictionary from golden test set.

        Returns:
            Review result dictionary with dimension scores, overall score,
            tier classification, and suggested action.
        """
        metadata = question.get("metadata", {})
        cached = metadata.get("ai_review")
        if cached:
            logger.debug(f"Using cached AI review for {question.get('id', 'unknown')}")
            return cached

        prompt = REVIEW_PROMPT_TEMPLATE.format(
            question_type=question.get("question_type", "unknown"),
            question=question.get("question", ""),
            answer=question.get("answer", ""),
            ground_truth_excerpt=question.get("ground_truth_excerpt", ""),
        )

        try:
            response = call_with_retry(
                self.client.messages.create,
                model=self.llm_config["model_name"],
                max_tokens=self.llm_config["max_tokens"],
                temperature=self.llm_config["temperature"],
                messages=[{"role": "user", "content": prompt}],
            )
            raw_text = response.content[0].text
            result = self._parse_review_response(raw_text)
            result["reviewed_at"] = datetime.now().isoformat()
            return result
        except Exception as e:
            logger.error(f"AI review failed for {question.get('id', 'unknown')}: {e}")
            return {
                "error": str(e),
                "overall_score": 0.0,
                "tier": "C",
                "suggested_action": "review",
                "overall_comment": f"AI review failed: {e}",
                "reviewed_at": datetime.now().isoformat(),
            }

    def review_questions(
        self,
        questions: list[dict[str, Any]],
        skip_reviewed: bool = True,
    ) -> list[dict[str, Any]]:
        """Review a list of questions, with caching and batch progress.

        Args:
            questions: List of question dictionaries.
            skip_reviewed: If True, skip questions that already have
                ai_review in metadata.

        Returns:
            List of review result dictionaries, one per question.
        """
        results = []
        total = len(questions)
        for i, question in enumerate(questions):
            q_id = question.get("id", f"unknown_{i}")
            metadata = question.get("metadata", {})

            if skip_reviewed and metadata.get("ai_review"):
                logger.info(f"[{i + 1}/{total}] Skipping {q_id} (already reviewed)")
                results.append(metadata["ai_review"])
                continue

            logger.info(f"[{i + 1}/{total}] Reviewing {q_id}...")
            result = self.review_question(question)
            results.append(result)

            question.setdefault("metadata", {})
            question["metadata"]["ai_review"] = result

            if (i + 1) % BATCH_SIZE == 0:
                logger.info(
                    f"Progress: {i + 1}/{total} reviewed ({(i + 1) / total * 100:.0f}%)"
                )
                time.sleep(0.5)

        return results

    def classify_tier(self, review_result: dict[str, Any]) -> str:
        """Classify a review result into a tier (A/B/C).

        Args:
            review_result: Review result dictionary from review_question().

        Returns:
            Tier string: "A" (auto-approve), "B" (needs review), or "C" (likely reject).
        """
        score = review_result.get("overall_score", 0.0)
        if score >= TIER_A_THRESHOLD:
            return "A"
        elif score >= TIER_B_THRESHOLD:
            return "B"
        return "C"

    def get_tier_summary(self, questions: list[dict[str, Any]]) -> dict[str, list[str]]:
        """Summarize question IDs by tier classification.

        Args:
            questions: List of question dictionaries with ai_review in metadata.

        Returns:
            Dictionary with keys "A", "B", "C" mapping to lists of question IDs.
        """
        summary: dict[str, list[str]] = {"A": [], "B": [], "C": []}
        for q in questions:
            review = q.get("metadata", {}).get("ai_review", {})
            if review:
                tier = self.classify_tier(review)
                summary[tier].append(q.get("id", "unknown"))
        return summary

    def _parse_review_response(self, raw_text: str) -> dict[str, Any]:
        """Parse LLM response text into structured review result.

        Args:
            raw_text: Raw text response from LLM.

        Returns:
            Structured review result dictionary.
        """
        json_str = self._extract_json(raw_text)
        if not json_str:
            logger.warning("Failed to extract JSON from LLM response, using defaults")
            return self._default_review_result()

        try:
            parsed = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.warning(f"JSON parse error: {e}, using defaults")
            return self._default_review_result()

        dimensions = [
            "question_clarity",
            "answer_accuracy",
            "answer_completeness",
            "source_consistency",
        ]
        scores = {}
        for dim in dimensions:
            dim_data = parsed.get(dim, {})
            if isinstance(dim_data, dict):
                scores[dim] = {
                    "score": self._clamp_score(dim_data.get("score", 3)),
                    "reason": dim_data.get("reason", ""),
                }
            elif isinstance(dim_data, int | float):
                scores[dim] = {"score": self._clamp_score(dim_data), "reason": ""}

        overall_score = (
            sum(s["score"] for s in scores.values()) / len(scores) if scores else 0.0
        )
        suggested_action = parsed.get("suggested_action", "review")
        if suggested_action not in ("approve", "review", "reject"):
            suggested_action = "review"

        result = {
            "dimensions": scores,
            "overall_score": round(overall_score, 2),
            "tier": self.classify_tier({"overall_score": overall_score}),
            "overall_comment": parsed.get("overall_comment", ""),
            "suggested_action": suggested_action,
        }
        return result

    @staticmethod
    def _extract_json(text: str) -> str | None:
        """Extract JSON object from text that may contain markdown fences.

        Args:
            text: Raw text potentially containing JSON.

        Returns:
            Extracted JSON string, or None if not found.
        """
        fence_match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
        if fence_match:
            return fence_match.group(1).strip()

        brace_match = re.search(r"\{.*\}", text, re.DOTALL)
        if brace_match:
            return brace_match.group(0)

        return None

    @staticmethod
    def _clamp_score(value: Any) -> float:
        """Clamp a score value to the 1-5 range.

        Args:
            value: Raw score value from LLM response.

        Returns:
            Clamped float score between 1.0 and 5.0.
        """
        try:
            score = float(value)
        except (TypeError, ValueError):
            return 3.0
        return max(1.0, min(5.0, score))

    @staticmethod
    def _default_review_result() -> dict[str, Any]:
        """Return a default review result for error cases.

        Returns:
            Dictionary with default scores and neutral tier.
        """
        return {
            "dimensions": {
                "question_clarity": {"score": 3.0, "reason": "parse failed"},
                "answer_accuracy": {"score": 3.0, "reason": "parse failed"},
                "answer_completeness": {"score": 3.0, "reason": "parse failed"},
                "source_consistency": {"score": 3.0, "reason": "parse failed"},
            },
            "overall_score": 3.0,
            "tier": "B",
            "overall_comment": "Failed to parse LLM response",
            "suggested_action": "review",
        }
