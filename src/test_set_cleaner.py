from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.exceptions import TestSetError

if TYPE_CHECKING:
    from src.meal import MealConfig
    from src.test_set_manager import TestSetManager


class TestSetCleaner:
    __test__ = False

    def __init__(self, manager: TestSetManager) -> None:
        """Initialize the TestSetCleaner with a reference to TestSetManager.

        Args:
            manager: TestSetManager instance for I/O operations
                (save_test_set, _create_archive_backup).
        """
        self._manager = manager

    @staticmethod
    def filter_rejected_questions(test_set_data: dict[str, Any]) -> dict[str, Any]:
        """Filter out rejected questions from a test set.

        Questions with metadata.review_status == "rejected" are excluded
        from evaluation. This method modifies the test_set_data in place
        and returns it for chaining.

        Args:
            test_set_data: Test set dictionary with a "questions" key.

        Returns:
            The same test_set_data dict with rejected questions removed.
        """
        questions = test_set_data.get("questions", [])
        original_count = len(questions)
        if original_count == 0:
            return test_set_data

        filtered = [
            q
            for q in questions
            if q.get("metadata", {}).get("review_status") != "rejected"
        ]
        rejected_count = original_count - len(filtered)
        if rejected_count > 0:
            test_set_data["questions"] = filtered
            logger.info(
                f"Filtered {rejected_count} rejected question(s) "
                f"from test set '{test_set_data.get('metadata', {}).get('name', 'unknown')}' "
                f"({original_count} -> {len(filtered)})"
            )
        return test_set_data

    def clean_immutable(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Clean a test set with immutable policy.

        For invalid_policy: "immutable":
        - If no invalid questions (only meal_id changed), just update meal_id and return
        - If any invalid questions, raise TestSetError with message about immutable policy

        Args:
            test_set_data: Test set dictionary to clean.
            meal_config: MealConfig for the current meal.
            invalid_questions: List of questions that are invalid.

        Returns:
            Cleaned test set dictionary with updated meal_id.

        Raises:
            TestSetError: If any invalid questions exist.
        """
        if invalid_questions:
            invalid_ids = [q.get("id", "?") for q in invalid_questions]
            raise TestSetError(
                f"Test set has immutable policy but contains {len(invalid_questions)} "
                f"invalid questions with IDs: {invalid_ids}. "
                "Cannot modify immutable test set."
            )

        test_set_data["metadata"]["meal_id"] = meal_config.data_id
        test_set_data["metadata"]["updated_at"] = datetime.now().isoformat()
        return test_set_data

    def clean_trim(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Clean a test set with trim policy.

        For invalid_policy: "trim":
        1. If all questions are invalid, raise TestSetError
        2. Create archive backup
        3. Remove invalid questions
        4. Update metadata (meal_id, updated_at, audit_log)
        5. Save and return

        Args:
            test_set_data: Test set dictionary to clean.
            meal_config: MealConfig for the current meal.
            invalid_questions: List of questions that are invalid.

        Returns:
            Cleaned test set dictionary.

        Raises:
            TestSetError: If all questions are invalid.
        """
        total_questions = len(test_set_data.get("questions", []))

        if len(invalid_questions) == total_questions:
            raise TestSetError(
                f"Cannot trim test set: all {total_questions} questions are invalid. "
                "No valid questions remain."
            )

        meal_name = meal_config.name
        self._manager._create_archive_backup(test_set_data, meal_name)

        invalid_ids = {q.get("id") for q in invalid_questions}
        test_set_data["questions"] = [
            q
            for q in test_set_data.get("questions", [])
            if q.get("id") not in invalid_ids
        ]

        test_set_data["metadata"]["meal_id"] = meal_config.data_id
        test_set_data["metadata"]["updated_at"] = datetime.now().isoformat()

        audit_entry = {
            "action": "trimmed",
            "timestamp": datetime.now().isoformat(),
            "removed_count": len(invalid_questions),
            "removed_ids": list(invalid_ids),
        }
        test_set_data["metadata"]["audit_log"].append(audit_entry)

        self._manager.save_test_set(meal_name, test_set_data)

        logger.info(
            f"Trimmed {len(invalid_questions)} invalid questions from test set "
            f"'{test_set_data['metadata']['name']}'"
        )

        return test_set_data

    def clean_regenerate(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
        generator: Any | None,
        llm_preset: str,
        token_tracker: Any | None,
        chunks_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Clean a test set with regenerate policy.

        For invalid_policy: "regenerate":
        1. Check that generation config exists in metadata, else raise TestSetError
        2. Create archive backup
        3. Remove invalid questions
        4. If generator provided, supplement questions to restore count
        5. Update metadata (meal_id, updated_at, audit_log)
        6. If all questions were replaced, add full_regeneration to audit_log
        7. Save and return

        Args:
            test_set_data: Test set dictionary to clean.
            meal_config: MealConfig for the current meal.
            invalid_questions: List of questions that are invalid.
            generator: Optional TestSetGenerator for regeneration.
            llm_preset: LLM preset for generation.
            token_tracker: Optional token tracker.
            chunks_dir: Optional path to chunks directory.

        Returns:
            Cleaned test set dictionary.

        Raises:
            TestSetError: If generation config is missing.
        """
        generation_config = test_set_data["metadata"].get("generation")
        if not generation_config:
            raise TestSetError(
                "Test set has regenerate policy but no generation config in metadata. "
                "Cannot regenerate questions without generation configuration."
            )

        meal_name = meal_config.name
        self._manager._create_archive_backup(test_set_data, meal_name)

        original_count = len(test_set_data.get("questions", []))
        invalid_ids = {q.get("id") for q in invalid_questions}
        all_were_invalid = len(invalid_questions) == original_count

        test_set_data["questions"] = [
            q
            for q in test_set_data.get("questions", [])
            if q.get("id") not in invalid_ids
        ]

        if generator is not None and invalid_questions:
            num_to_generate = len(invalid_questions)
            try:
                new_questions = generator.generate_questions(
                    meal_config=meal_config,
                    num_questions=num_to_generate,
                    llm_preset=llm_preset,
                    token_tracker=token_tracker,
                )
                test_set_data["questions"].extend(new_questions)
                logger.info(
                    f"Regenerated {len(new_questions)} questions for test set "
                    f"'{test_set_data['metadata']['name']}'"
                )
            except Exception as e:
                logger.error(f"Failed to regenerate questions: {str(e)}")

        test_set_data["metadata"]["meal_id"] = meal_config.data_id
        test_set_data["metadata"]["updated_at"] = datetime.now().isoformat()

        audit_entry = {
            "action": "regenerated",
            "timestamp": datetime.now().isoformat(),
            "removed_count": len(invalid_questions),
            "removed_ids": list(invalid_ids),
        }
        if all_were_invalid:
            audit_entry["full_regeneration"] = True

        test_set_data["metadata"]["audit_log"].append(audit_entry)

        self._manager.save_test_set(meal_name, test_set_data)

        return test_set_data

    def clean_user_test_set(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
        generator: Any | None = None,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
        chunks_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Clean a user-defined test set according to its invalid_policy.

        Args:
            test_set_data: Test set dictionary to clean.
            meal_config: MealConfig for the current meal.
            invalid_questions: List of questions that are invalid.
            generator: Optional TestSetGenerator for regenerate policy.
            llm_preset: LLM preset for generation.
            token_tracker: Optional token tracker.
            chunks_dir: Optional path to chunks directory.

        Returns:
            Cleaned test set dictionary.

        Raises:
            TestSetError: If cleaning fails according to invalid_policy.
        """
        invalid_policy = test_set_data["metadata"].get("invalid_policy")

        if invalid_policy == "immutable":
            return self.clean_immutable(test_set_data, meal_config, invalid_questions)
        elif invalid_policy == "trim":
            return self.clean_trim(test_set_data, meal_config, invalid_questions)
        elif invalid_policy == "regenerate":
            return self.clean_regenerate(
                test_set_data,
                meal_config,
                invalid_questions,
                generator,
                llm_preset,
                token_tracker,
                chunks_dir=chunks_dir,
            )
        else:
            raise TestSetError(f"Unknown invalid_policy: {invalid_policy}")

    def clean_machine_test_set(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
        generation_config: dict[str, Any] | None = None,
        generator: Any | None = None,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
        chunks_dir: Path | None = None,
    ) -> dict[str, Any]:
        """Clean a machine-generated test set by removing invalid questions
        and supplementing new ones.

        Args:
            test_set_data: Test set dictionary to clean.
            meal_config: MealConfig for the current meal.
            invalid_questions: List of questions to remove.
            generation_config: Optional generation config from experiment.
                If provided, overrides the test set's generation config.
            generator: TestSetGenerator for supplementing questions.
            llm_preset: LLM preset for generation.
            token_tracker: Optional token tracker.
            chunks_dir: Optional path to chunks directory.

        Returns:
            Cleaned test set dictionary.
        """
        original_count = len(test_set_data.get("questions", []))

        invalid_ids = {q.get("id") for q in invalid_questions}
        test_set_data["questions"] = [
            q
            for q in test_set_data.get("questions", [])
            if q.get("id") not in invalid_ids
        ]

        stored_generation_config = test_set_data["metadata"].get("generation")

        if (
            generation_config is not None
            and stored_generation_config != generation_config
        ):
            logger.warning(
                f"Generation config mismatch for test set '{test_set_data['metadata']['name']}'. "
                f"Using experiment config instead of stored config."
            )
            config_change_entry = {
                "event": "generation_config_changed",
                "old_config": stored_generation_config,
                "new_config": generation_config,
                "timestamp": datetime.now().isoformat(),
            }
            test_set_data["metadata"]["audit_log"].append(config_change_entry)

        added_count = 0
        if generator is not None and invalid_questions:
            len(invalid_questions)
            try:
                test_set_data = generator.supplement_document_based_questions(
                    meal_name=meal_config.name,
                    existing_test_set=test_set_data,
                    target_count=original_count,
                    llm_preset=llm_preset,
                    token_tracker=token_tracker,
                    chunks_dir=chunks_dir,
                )
                added_count = len(test_set_data.get("questions", [])) - (
                    original_count - len(invalid_questions)
                )
                if added_count < 0:
                    added_count = 0
                logger.info(
                    f"Supplemented {added_count} questions for test set "
                    f"'{test_set_data['metadata']['name']}'"
                )
            except Exception as e:
                logger.error(f"Failed to supplement questions: {str(e)}")

        from_meal_id = test_set_data["metadata"].get("meal_id", "")
        test_set_data["metadata"]["meal_id"] = meal_config.data_id
        test_set_data["metadata"]["updated_at"] = datetime.now().isoformat()

        audit_entry = {
            "event": "cleaned",
            "from_meal": from_meal_id,
            "to_meal": meal_config.data_id,
            "removed_count": len(invalid_questions),
            "added_count": added_count,
            "timestamp": datetime.now().isoformat(),
        }
        test_set_data["metadata"]["audit_log"].append(audit_entry)

        self._manager.save_test_set(meal_config.name, test_set_data)

        logger.info(
            f"Cleaned machine test set '{test_set_data['metadata']['name']}': "
            f"removed {len(invalid_questions)}, added {added_count}"
        )

        return test_set_data

    def should_warn_about_cleaning(
        self,
        test_set_data: dict[str, Any],
    ) -> tuple[bool, str]:
        """Check if a warning should be emitted about previous cleaning.

        Args:
            test_set_data: Test set dictionary.

        Returns:
            Tuple of (should_warn, warning_message).
        """
        metadata = test_set_data.get("metadata", {})

        if metadata.get("suppress_warnings", False):
            return (False, "")

        audit_log = metadata.get("audit_log", [])

        for entry in audit_log:
            action = entry.get("action", "")
            if action == "trimmed":
                removed_count = entry.get("removed_count", 0)
                timestamp = entry.get("timestamp", "unknown time")
                return (
                    True,
                    f"Test set was previously trimmed at {timestamp}. "
                    f"{removed_count} questions were removed.",
                )
            elif action == "regenerated":
                timestamp = entry.get("timestamp", "unknown time")
                if entry.get("full_regeneration"):
                    return (
                        True,
                        f"Test set underwent full regeneration at {timestamp}. "
                        "All questions were replaced.",
                    )
                else:
                    removed_count = entry.get("removed_count", 0)
                    return (
                        True,
                        f"Test set was previously regenerated at {timestamp}. "
                        f"{removed_count} questions were replaced.",
                    )

        return (False, "")
