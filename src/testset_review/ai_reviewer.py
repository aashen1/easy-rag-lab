from __future__ import annotations

import json
import re
import time
from datetime import datetime
from typing import Any

from loguru import logger

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


class AIReviewer:
    def __init__(
        self,
        config: dict[str, Any],
        llm_preset: str | None = None,
    ) -> None:
        self.config = config
        self._llm_preset = llm_preset
        self._llm_config: dict[str, Any] | None = None
        self._client: Any = None

    @property
    def llm_config(self) -> dict[str, Any]:
        if self._llm_config is None:
            self._llm_config = get_llm_config(self.config, preset=self._llm_preset)
            test_gen = self.config.get("test_generation", {})
            self._llm_config.setdefault("temperature", test_gen.get("temperature", 0.3))
            self._llm_config.setdefault("max_tokens", test_gen.get("max_tokens", 1024))
        return self._llm_config

    @property
    def client(self) -> Any:
        if self._client is None:
            self._client = create_llm_client(self.llm_config, mode="sdk")
        return self._client

    def _call_llm(self, prompt: str) -> str:
        response = self.client.messages.create(
            model=self.llm_config["model_name"],
            max_tokens=self.llm_config["max_tokens"],
            temperature=self.llm_config["temperature"],
            messages=[{"role": "user", "content": prompt}],
        )
        return response.content[0].text

    def review_question(self, question: dict[str, Any]) -> dict[str, Any]:
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
            raw_text = self._call_llm(prompt)
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
        results = []
        total = len(questions)
        for i, question in enumerate(questions):
            q_id = question.get("id", f"unknown_{i}")
            if skip_reviewed and question.get("metadata", {}).get("ai_review"):
                logger.debug(f"Skipping already-reviewed {q_id}")
                results.append(question["metadata"]["ai_review"])
                continue

            logger.info(
                f"AI reviewing {i + 1}/{total}: {q_id} "
                f"[{question.get('question_type', '?')}]"
            )
            start = time.time()
            review_result = self.review_question(question)
            elapsed = time.time() - start

            metadata = question.setdefault("metadata", {})
            metadata["ai_review"] = review_result

            score = review_result.get("overall_score", 0.0)
            tier = review_result.get("tier", "?")
            logger.info(f"  -> score={score:.1f} tier={tier} ({elapsed:.1f}s)")
            results.append(review_result)

        return results

    def classify_tier(self, review_result: dict[str, Any]) -> str:
        if "tier" in review_result:
            return review_result["tier"]
        score = review_result.get("overall_score", 0.0)
        if score >= TIER_A_THRESHOLD:
            return "A"
        elif score >= TIER_B_THRESHOLD:
            return "B"
        return "C"

    def get_tier_summary(self, questions: list[dict[str, Any]]) -> dict[str, list[str]]:
        summary: dict[str, list[str]] = {"A": [], "B": [], "C": []}
        for q in questions:
            review = q.get("metadata", {}).get("ai_review")
            if not review:
                continue
            tier = self.classify_tier(review)
            q_id = q.get("id", "unknown")
            summary[tier].append(q_id)
        return summary

    @staticmethod
    def _parse_review_response(raw_text: str) -> dict[str, Any]:
        json_match = re.search(r"\{.*\}", raw_text, re.DOTALL)
        if not json_match:
            return {
                "error": "No JSON found in response",
                "raw_response": raw_text[:500],
                "overall_score": 0.0,
                "tier": "C",
                "suggested_action": "review",
            }

        try:
            parsed = json.loads(json_match.group())
        except json.JSONDecodeError:
            return {
                "error": "Failed to parse JSON",
                "raw_response": raw_text[:500],
                "overall_score": 0.0,
                "tier": "C",
                "suggested_action": "review",
            }

        scores = []
        for dim in [
            "question_clarity",
            "answer_accuracy",
            "answer_completeness",
            "source_consistency",
        ]:
            dim_data = parsed.get(dim, {})
            score = dim_data.get("score", 0) if isinstance(dim_data, dict) else 0
            scores.append(score)

        overall_score = sum(scores) / len(scores) if scores else 0.0
        tier = (
            "A"
            if overall_score >= TIER_A_THRESHOLD
            else ("B" if overall_score >= TIER_B_THRESHOLD else "C")
        )

        return {
            **parsed,
            "overall_score": round(overall_score, 1),
            "tier": tier,
        }
