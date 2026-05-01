from __future__ import annotations

from datetime import datetime
from typing import Any

from loguru import logger


class TestSetComposer:
    def __init__(self, manager=None, config: dict[str, Any] | None = None) -> None:
        self.manager = manager
        self.config = config or {}

    def compose_merge(
        self,
        sources: list[dict[str, Any]],
        name: str,
        meal_id: str = "",
    ) -> dict[str, Any]:
        deduped, duplicates = self._deduplicate_questions(
            [q for src in sources for q in src.get("questions", [])]
        )

        if duplicates:
            logger.info(f"Removed {len(duplicates)} duplicate questions during merge")

        now = datetime.now().isoformat()
        composition = {
            "type": "merged",
            "sources": [
                {
                    "name": src.get("metadata", {}).get("name", "unknown"),
                    "meal_id": src.get("metadata", {}).get("meal_id", ""),
                    "num_questions": len(src.get("questions", [])),
                }
                for src in sources
            ],
            "merged_at": now,
            "duplicates_removed": len(duplicates),
        }

        return {
            "metadata": {
                "name": name,
                "meal_id": meal_id,
                "created_at": now,
                "updated_at": now,
                "generation": None,
                "user_defined": False,
                "invalid_policy": None,
                "audit_log": [
                    {
                        "event": "composed",
                        "timestamp": now,
                        "composition_type": "merged",
                        "source_count": len(sources),
                    }
                ],
                "suppress_warnings": False,
                "composition": composition,
                "quality_status": "draft",
                "review_progress": {},
                "portable": False,
                "data_coverage": "partial",
            },
            "quality_metrics": {},
            "questions": deduped,
        }

    def compose_filter(
        self,
        test_set: dict[str, Any],
        question_types: list[str] | None = None,
        categories: list[str] | None = None,
        difficulties: list[str] | None = None,
        review_statuses: list[str] | None = None,
        max_questions: int | None = None,
        name: str = "",
    ) -> dict[str, Any]:
        questions = test_set.get("questions", [])
        filtered = questions

        if question_types:
            filtered = [q for q in filtered if q.get("question_type") in question_types]
        if categories:
            filtered = [q for q in filtered if q.get("category") in categories]
        if difficulties:
            filtered = [q for q in filtered if q.get("difficulty") in difficulties]
        if review_statuses:
            filtered = [
                q
                for q in filtered
                if q.get("metadata", {}).get("review_status") in review_statuses
            ]
        if max_questions and len(filtered) > max_questions:
            filtered = filtered[:max_questions]

        if not filtered:
            logger.warning("Filter returned zero questions")

        now = datetime.now().isoformat()
        source_name = test_set.get("metadata", {}).get("name", "unknown")
        output_name = name or f"{source_name}_filtered"

        composition = {
            "type": "filtered",
            "source": {"name": source_name},
            "filtered_at": now,
            "filters_applied": {
                "question_types": question_types,
                "categories": categories,
                "difficulties": difficulties,
                "review_statuses": review_statuses,
                "max_questions": max_questions,
            },
        }

        return {
            "metadata": {
                "name": output_name,
                "meal_id": test_set.get("metadata", {}).get("meal_id", ""),
                "created_at": now,
                "updated_at": now,
                "generation": test_set.get("metadata", {}).get("generation"),
                "user_defined": False,
                "invalid_policy": None,
                "audit_log": [
                    {
                        "event": "composed",
                        "timestamp": now,
                        "composition_type": "filtered",
                    }
                ],
                "suppress_warnings": False,
                "composition": composition,
                "quality_status": "draft",
                "review_progress": {},
                "portable": False,
                "data_coverage": test_set.get("metadata", {}).get(
                    "data_coverage", "partial"
                ),
            },
            "quality_metrics": {},
            "questions": filtered,
        }

    def compose_incremental(
        self,
        base_test_set: dict[str, Any],
        new_questions: list[dict[str, Any]],
        name: str = "",
        meal_id: str = "",
    ) -> dict[str, Any]:
        base_questions = base_test_set.get("questions", [])
        all_questions = base_questions + new_questions
        deduped, duplicates = self._deduplicate_questions(all_questions)

        if duplicates:
            logger.info(
                f"Removed {len(duplicates)} duplicate questions "
                f"(possibly overlapping with base set)"
            )

        base_name = base_test_set.get("metadata", {}).get("name", "unknown")
        now = datetime.now().isoformat()
        output_name = name or f"{base_name}_extended"

        composition = {
            "type": "incremental",
            "base": {"name": base_name, "num_questions": len(base_questions)},
            "supplement": {"num_generated": len(new_questions)},
            "composed_at": now,
            "duplicates_removed": len(duplicates),
        }

        return {
            "metadata": {
                "name": output_name,
                "meal_id": meal_id
                or base_test_set.get("metadata", {}).get("meal_id", ""),
                "created_at": now,
                "updated_at": now,
                "generation": base_test_set.get("metadata", {}).get("generation"),
                "user_defined": False,
                "invalid_policy": None,
                "audit_log": [
                    {
                        "event": "composed",
                        "timestamp": now,
                        "composition_type": "incremental",
                    }
                ],
                "suppress_warnings": False,
                "composition": composition,
                "quality_status": "draft",
                "review_progress": {},
                "portable": False,
                "data_coverage": base_test_set.get("metadata", {}).get(
                    "data_coverage", "partial"
                ),
            },
            "quality_metrics": {},
            "questions": deduped,
        }

    def _deduplicate_questions(
        self, questions: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        seen_texts: set[str] = set()
        deduped: list[dict[str, Any]] = []
        duplicates: list[dict[str, Any]] = []

        for q in questions:
            text = (q.get("question", "") or "").strip().lower()
            source_files = set(q.get("source_files", []) or [])

            is_dup = False
            for seen_text in seen_texts:
                if self._texts_similar(text, seen_text, threshold=0.85):
                    existing = next(
                        (
                            dq
                            for dq in deduped
                            if dq.get("question", "").strip().lower() == seen_text
                        ),
                        None,
                    )
                    if existing:
                        existing_files = set(existing.get("source_files", []) or [])
                        if source_files & existing_files:
                            is_dup = True
                            break

            if not is_dup:
                seen_texts.add(text)
                deduped.append(q)
            else:
                duplicates.append(q)

        return deduped, duplicates

    @staticmethod
    def _texts_similar(text1: str, text2: str, threshold: float = 0.85) -> bool:
        if text1 == text2:
            return True

        shorter = text1 if len(text1) < len(text2) else text2
        longer = text2 if len(text1) < len(text2) else text1

        if len(longer) == 0:
            return False

        common = sum(1 for c in shorter if c in longer)
        similarity = common / len(longer)
        return similarity >= threshold
