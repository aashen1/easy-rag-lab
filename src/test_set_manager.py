from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.exceptions import TestSetError
from src.meal import MealConfig, MealManager
from src.utils import ensure_dir

if TYPE_CHECKING:
    from src.test_generator import TestSetGenerator


@dataclass
class TestSetMetadata:
    name: str
    meal_id: str
    created_at: str
    updated_at: str
    generation: dict[str, Any] | None = None
    user_defined: bool = False
    invalid_policy: str | None = None
    audit_log: list[dict[str, Any]] = field(default_factory=list)
    suppress_warnings: bool = False
    composition: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> TestSetMetadata:
        return cls(
            name=data["name"],
            meal_id=data["meal_id"],
            created_at=data["created_at"],
            updated_at=data["updated_at"],
            generation=data.get("generation"),
            user_defined=data.get("user_defined", False),
            invalid_policy=data.get("invalid_policy"),
            audit_log=data.get("audit_log", []),
            suppress_warnings=data.get("suppress_warnings", False),
            composition=data.get("composition", {}),
        )


class TestSetManager:
    __test__ = False

    def __init__(self, config: dict[str, Any]):
        """Initialize the TestSetManager with application configuration.

        Args:
            config: Application configuration dictionary containing 'meals'
                section used to resolve meal directories.
        """
        self.config = config
        self.meal_manager = MealManager(config)

    def get_test_sets_dir(self, meal_name: str) -> Path:
        """Get the test_sets directory path for a meal.

        Args:
            meal_name: Name of the meal.

        Returns:
            Path to the test_sets directory under the meal directory.
        """
        return self.meal_manager.get_meal_dir(meal_name) / "test_sets"

    def find_by_name(self, meal_name: str, test_set_name: str) -> dict[str, Any] | None:
        """Find a test set by name in a meal's test_sets directory.

        Archive files (containing '.archive.') are excluded from results.

        Args:
            meal_name: Name of the meal to search in.
            test_set_name: Name of the test set to find.

        Returns:
            Parsed test set dictionary if found, None otherwise.
        """
        test_sets_dir = self.get_test_sets_dir(meal_name)
        file_path = test_sets_dir / f"{test_set_name}.json"

        if not file_path.exists():
            return None

        if ".archive." in file_path.name:
            return None

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return self._migrate_test_set(data)
        except Exception as e:
            logger.error(f"Failed to load test set '{test_set_name}' from meal '{meal_name}': {str(e)}")
            return None

    def save_test_set(self, meal_name: str, test_set_data: dict[str, Any]) -> Path:
        """Save a test set JSON file to a meal's test_sets directory.

        The filename is derived from test_set_data["metadata"]["name"].
        Creates the test_sets directory if it does not exist.

        Args:
            meal_name: Name of the meal to save the test set under.
            test_set_data: Dictionary containing the test set data with a
                'metadata' key that has a 'name' field.

        Returns:
            Path to the saved test set JSON file.

        Raises:
            KeyError: If test_set_data lacks 'metadata' or 'name' within it.
            IOError: If the file cannot be written.
        """
        test_sets_dir = self.get_test_sets_dir(meal_name)
        ensure_dir(str(test_sets_dir))

        test_set_name = test_set_data["metadata"]["name"]
        file_path = test_sets_dir / f"{test_set_name}.json"

        try:
            with open(file_path, "w", encoding="utf-8") as f:
                json.dump(test_set_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved test set '{test_set_name}' to meal '{meal_name}'")
            return file_path
        except Exception as e:
            logger.error(f"Failed to save test set '{test_set_name}' to meal '{meal_name}': {str(e)}")
            raise

    def load_test_set(self, meal_name: str, test_set_name: str) -> dict[str, Any]:
        """Load a test set by name from a meal's test_sets directory.

        Args:
            meal_name: Name of the meal to load from.
            test_set_name: Name of the test set to load.

        Returns:
            Parsed test set dictionary.

        Raises:
            FileNotFoundError: If the test set file does not exist.
        """
        test_sets_dir = self.get_test_sets_dir(meal_name)
        file_path = test_sets_dir / f"{test_set_name}.json"

        if not file_path.exists():
            raise TestSetError(
                f"Test set '{test_set_name}' not found in meal '{meal_name}'"
            )

        try:
            with open(file_path, encoding="utf-8") as f:
                data = json.load(f)
            return self._migrate_test_set(data)
        except Exception as e:
            logger.error(f"Failed to load test set '{test_set_name}' from meal '{meal_name}': {str(e)}")
            raise

    def _migrate_test_set(self, test_set_data: dict[str, Any]) -> dict[str, Any]:
        """Migrate old format test set to new format.

        Args:
            test_set_data: Test set dictionary that may be in old or new format.

        Returns:
            Test set dictionary in new format with 'metadata' key.
        """
        if "metadata" in test_set_data:
            return test_set_data

        return {
            "metadata": {
                "name": test_set_data.get("name", "unknown"),
                "meal_id": test_set_data.get("meal_data_id", ""),
                "created_at": test_set_data.get("created_at", ""),
                "updated_at": test_set_data.get("created_at", ""),
                "generation": test_set_data.get("generation_config", {}),
                "user_defined": False,
                "invalid_policy": None,
                "audit_log": [],
                "suppress_warnings": False,
                "composition": {},
            },
            "quality_metrics": test_set_data.get("quality_metrics", {}),
            "questions": test_set_data.get("questions", []),
        }

    def list_test_sets(self, meal_name: str) -> list[dict[str, Any]]:
        """List all test sets in a meal's test_sets directory.

        Archive files (containing '.archive.') are excluded from results.

        Args:
            meal_name: Name of the meal to list test sets for.

        Returns:
            List of dictionaries with 'name' and 'metadata' keys for each
            non-archive test set found.
        """
        test_sets_dir = self.get_test_sets_dir(meal_name)

        if not test_sets_dir.exists():
            return []

        results = []
        for json_file in sorted(test_sets_dir.glob("*.json")):
            if ".archive." in json_file.name:
                continue

            try:
                with open(json_file, encoding="utf-8") as f:
                    data = json.load(f)
                results.append({
                    "name": data.get("metadata", {}).get("name", json_file.stem),
                    "metadata": data.get("metadata", {}),
                })
            except Exception as e:
                logger.warning(f"Failed to load test set from {json_file}: {str(e)}")

        return results

    def delete_test_set(self, meal_name: str, test_set_name: str) -> None:
        """Delete a test set by name from a meal's test_sets directory.

        Args:
            meal_name: Name of the meal the test set belongs to.
            test_set_name: Name of the test set to delete.

        Raises:
            FileNotFoundError: If the test set file does not exist.
        """
        test_sets_dir = self.get_test_sets_dir(meal_name)
        file_path = test_sets_dir / f"{test_set_name}.json"

        if not file_path.exists():
            raise TestSetError(
                f"Test set '{test_set_name}' not found in meal '{meal_name}'"
            )

        try:
            file_path.unlink()
            logger.info(f"Deleted test set '{test_set_name}' from meal '{meal_name}'")
        except Exception as e:
            logger.error(f"Failed to delete test set '{test_set_name}' from meal '{meal_name}': {str(e)}")
            raise

    def test_set_exists(self, meal_name: str, test_set_name: str) -> bool:
        """Check whether a test set exists in a meal's test_sets directory.

        Args:
            meal_name: Name of the meal to check in.
            test_set_name: Name of the test set to check for.

        Returns:
            True if the test set JSON file exists, False otherwise.
        """
        test_sets_dir = self.get_test_sets_dir(meal_name)
        file_path = test_sets_dir / f"{test_set_name}.json"
        return file_path.exists()

    def validate_test_set(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """
        Validate a test set against a meal configuration.

        A test set is valid if all questions reference data sources that exist
        in the current meal's sample.

        Args:
            test_set_data: Test set dictionary with 'metadata' and 'questions'.
            meal_config: MealConfig instance for the current meal.

        Returns:
            Tuple of (is_valid, invalid_questions):
            - is_valid: True if all questions are valid
            - invalid_questions: List of questions with missing data sources
        """
        meal_id = test_set_data["metadata"]["meal_id"]
        if meal_id == meal_config.data_id:
            return (True, [])
        invalid_questions = self._check_questions_validity(
            test_set_data.get("questions", []),
            meal_config,
        )
        return (len(invalid_questions) == 0, invalid_questions)

    def _check_questions_validity(
        self,
        questions: list[dict[str, Any]],
        meal_config: MealConfig,
    ) -> list[dict[str, Any]]:
        """
        Check each question's data sources against the meal's PDF files.

        Args:
            questions: List of question dictionaries.
            meal_config: MealConfig instance for the current meal.

        Returns:
            List of questions that have missing data sources.
        """
        meal_pdf_paths = {mf.path for mf in meal_config.pdf_files}
        invalid_questions: list[dict[str, Any]] = []

        for question in questions:
            question_type = question.get("question_type", "")
            source_files = question.get("source_files", [])

            if question_type == "irrelevant":
                continue
            if not source_files:
                continue

            if not all(sf in meal_pdf_paths for sf in source_files):
                invalid_questions.append(question)

        return invalid_questions

    def _update_meal_id(
        self,
        test_set_data: dict[str, Any],
        new_meal_id: str,
    ) -> dict[str, Any]:
        """
        Update the meal_id in test set metadata.

        Args:
            test_set_data: Test set dictionary.
            new_meal_id: New meal_id to set.

        Returns:
            Updated test set dictionary.
        """
        test_set_data["metadata"]["meal_id"] = new_meal_id
        test_set_data["metadata"]["updated_at"] = datetime.now().isoformat()
        return test_set_data

    def update_meal_id(
        self,
        meal_name: str,
        test_set_name: str,
        new_meal_id: str,
    ) -> dict[str, Any]:
        """Update the meal_id in a test set's metadata and save.

        Args:
            meal_name: Name of the meal.
            test_set_name: Name of the test set.
            new_meal_id: New meal data_id to set.

        Returns:
            Updated test set dictionary.
        """
        test_set_data = self.load_test_set(meal_name, test_set_name)
        test_set_data["metadata"]["meal_id"] = new_meal_id
        test_set_data["metadata"]["updated_at"] = datetime.now().isoformat()
        self.save_test_set(meal_name, test_set_data)
        return test_set_data

    def _create_archive_backup(
        self,
        test_set_data: dict[str, Any],
        meal_name: str,
    ) -> Path:
        """Create an archive backup of a test set before modification.

        Args:
            test_set_data: Test set dictionary to backup.
            meal_name: Name of the meal.

        Returns:
            Path to the archive file.
        """
        test_sets_dir = self.get_test_sets_dir(meal_name)
        ensure_dir(str(test_sets_dir))

        name = test_set_data["metadata"]["name"]
        timestamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
        archive_name = f"{name}.archive.{timestamp}.json"
        archive_path = test_sets_dir / archive_name

        with open(archive_path, "w", encoding="utf-8") as f:
            json.dump(test_set_data, f, ensure_ascii=False, indent=2)

        logger.info(f"Created archive backup at {archive_path}")
        return archive_path

    def _clean_user_test_set(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
        generator: Any | None = None,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
    ) -> dict[str, Any]:
        """Clean a user-defined test set according to its invalid_policy.

        Args:
            test_set_data: Test set dictionary to clean.
            meal_config: MealConfig for the current meal.
            invalid_questions: List of questions that are invalid.
            generator: Optional TestSetGenerator for regenerate policy.
            llm_preset: LLM preset for generation.
            token_tracker: Optional token tracker.

        Returns:
            Cleaned test set dictionary.

        Raises:
            ValueError: If cleaning fails according to invalid_policy.
        """
        invalid_policy = test_set_data["metadata"].get("invalid_policy")

        if invalid_policy == "immutable":
            return self._clean_immutable_policy(
                test_set_data, meal_config, invalid_questions
            )
        elif invalid_policy == "trim":
            return self._clean_trim_policy(
                test_set_data, meal_config, invalid_questions
            )
        elif invalid_policy == "regenerate":
            return self._clean_regenerate_policy(
                test_set_data,
                meal_config,
                invalid_questions,
                generator,
                llm_preset,
                token_tracker,
            )
        else:
            raise TestSetError(f"Unknown invalid_policy: {invalid_policy}")

    def _clean_immutable_policy(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Clean a test set with immutable policy.

        For invalid_policy: "immutable":
        - If no invalid questions (only meal_id changed), just update meal_id and return
        - If any invalid questions, raise ValueError with message about immutable policy

        Args:
            test_set_data: Test set dictionary to clean.
            meal_config: MealConfig for the current meal.
            invalid_questions: List of questions that are invalid.

        Returns:
            Cleaned test set dictionary with updated meal_id.

        Raises:
            ValueError: If any invalid questions exist.
        """
        if invalid_questions:
            invalid_ids = [q.get("id", "?") for q in invalid_questions]
            raise TestSetError(
                f"Test set has immutable policy but contains {len(invalid_questions)} "
                f"invalid questions with IDs: {invalid_ids}. "
                "Cannot modify immutable test set."
            )

        test_set_data = self._update_meal_id(test_set_data, meal_config.data_id)
        return test_set_data

    def _clean_trim_policy(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
    ) -> dict[str, Any]:
        """Clean a test set with trim policy.

        For invalid_policy: "trim":
        1. If all questions are invalid, raise ValueError
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
            ValueError: If all questions are invalid.
        """
        total_questions = len(test_set_data.get("questions", []))

        if len(invalid_questions) == total_questions:
            raise TestSetError(
                f"Cannot trim test set: all {total_questions} questions are invalid. "
                "No valid questions remain."
            )

        meal_name = meal_config.name
        self._create_archive_backup(test_set_data, meal_name)

        invalid_ids = {q.get("id") for q in invalid_questions}
        test_set_data["questions"] = [
            q for q in test_set_data.get("questions", [])
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

        self.save_test_set(meal_name, test_set_data)

        logger.info(
            f"Trimmed {len(invalid_questions)} invalid questions from test set "
            f"'{test_set_data['metadata']['name']}'"
        )

        return test_set_data

    def _clean_regenerate_policy(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
        generator: Any | None,
        llm_preset: str,
        token_tracker: Any | None,
    ) -> dict[str, Any]:
        """Clean a test set with regenerate policy.

        For invalid_policy: "regenerate":
        1. Check that generation config exists in metadata, else raise ValueError
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

        Returns:
            Cleaned test set dictionary.

        Raises:
            ValueError: If generation config is missing.
        """
        generation_config = test_set_data["metadata"].get("generation")
        if not generation_config:
            raise TestSetError(
                "Test set has regenerate policy but no generation config in metadata. "
                "Cannot regenerate questions without generation configuration."
            )

        meal_name = meal_config.name
        self._create_archive_backup(test_set_data, meal_name)

        original_count = len(test_set_data.get("questions", []))
        invalid_ids = {q.get("id") for q in invalid_questions}
        all_were_invalid = len(invalid_questions) == original_count

        test_set_data["questions"] = [
            q for q in test_set_data.get("questions", [])
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

        self.save_test_set(meal_name, test_set_data)

        return test_set_data

    def _should_warn_about_cleaning(
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
                    f"{removed_count} questions were removed."
                )
            elif action == "regenerated":
                timestamp = entry.get("timestamp", "unknown time")
                if entry.get("full_regeneration"):
                    return (
                        True,
                        f"Test set underwent full regeneration at {timestamp}. "
                        "All questions were replaced."
                    )
                else:
                    removed_count = entry.get("removed_count", 0)
                    return (
                        True,
                        f"Test set was previously regenerated at {timestamp}. "
                        f"{removed_count} questions were replaced."
                    )

        return (False, "")

    def _derive_test_set_name(
        self,
        generation_config: dict[str, Any] | None,
    ) -> str:
        """Derive a test set name from generation config when name is not specified.

        The naming convention follows strategy + num_questions pattern:
        - With generation config: "{strategy}_n{num_questions}"
        - Without generation config: "document_n{default_num}"

        This enables cache hitting: the same generation config will always
        produce the same test set name, allowing reuse of previously generated sets.

        Args:
            generation_config: Generation config from the test set specification.
                May be None if no generation parameters are specified.

        Returns:
            Auto-derived test set name string.
        """
        if generation_config is None:
            return f"document_n{self.config.get('test_generator', {}).get('default_num_questions', 10)}"

        strategy = generation_config.get("strategy", "document")
        num_questions = generation_config.get("num_questions", 10)
        return f"{strategy}_n{num_questions}"

    def resolve_test_set(
        self,
        meal_name: str,
        test_set_config: dict[str, Any],
        meal_config: MealConfig,
        generator: TestSetGenerator | None = None,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
    ) -> dict[str, Any]:
        """
        Resolve a test set according to the experiment configuration.

        This method implements the on_missing routing logic:
        - auto: Use/clean existing, or generate if not found
        - clean_only: Use/clean existing, error if not found
        - strict: Only use valid existing, error otherwise

        If the test set name is not specified, it will be auto-derived from
        the generation config (strategy + num_questions) to enable cache
        hitting without explicit naming.

        Args:
            meal_name: Name of the meal.
            test_set_config: Test set configuration from experiment.
            meal_config: MealConfig for the current meal.
            generator: Optional TestSetGenerator for generating/supplementing.
            llm_preset: LLM preset for generation.
            token_tracker: Optional token tracker.

        Returns:
            Resolved test set dictionary.

        Raises:
            ValueError: If resolution fails according to on_missing policy.
        """
        name = test_set_config.get("name")
        on_missing = test_set_config.get("on_missing", "auto")
        generation_config = test_set_config.get("generation")

        if name is None:
            name = self._derive_test_set_name(generation_config)
            logger.info(f"Auto-derived test set name: '{name}'")

        test_set_data = self.find_by_name(meal_name, name)

        if test_set_data is not None:
            is_valid, invalid_questions = self.validate_test_set(
                test_set_data, meal_config
            )

            if is_valid:
                return test_set_data

            if on_missing == "strict":
                raise TestSetError(
                    f'Test set "{name}" is invalid (some data sources missing) '
                    f'and on_missing is "strict".'
                )

            user_defined = test_set_data["metadata"].get("user_defined", False)

            if user_defined:
                return self._clean_user_test_set(
                    test_set_data,
                    meal_config,
                    invalid_questions,
                    generator,
                    llm_preset,
                    token_tracker,
                )
            else:
                return self._clean_machine_test_set(
                    test_set_data,
                    meal_config,
                    invalid_questions,
                    generation_config,
                    generator,
                    llm_preset,
                    token_tracker,
                )

        if on_missing == "clean_only":
            raise TestSetError(
                f'Test set "{name}" not found and on_missing is "clean_only". '
                f'Please create the test set first or change on_missing to "auto".'
            )

        if on_missing == "strict":
            raise TestSetError(
                f'Test set "{name}" not found and on_missing is "strict".'
            )

        if generator is None:
            raise TestSetError(
                f'Test set "{name}" not found and no generator provided for auto generation.'
            )

        if generation_config is not None:
            strategy = generation_config.get("strategy", "document")
            num_questions = generation_config.get("num_questions", 20)
            logger.info(
                f"Generating test set '{name}' with strategy={strategy}, "
                f"num_questions={num_questions}"
            )
            return generator.generate_document_based_questions(
                meal_name=meal_name,
                num_questions=num_questions,
                name=name,
                llm_preset=llm_preset,
                token_tracker=token_tracker,
            )

        logger.info(
            f"Generating test set '{name}' with defaults (10 document questions) - "
            f"no generation config provided"
        )
        return generator.generate_document_based_questions(
            meal_name=meal_name,
            num_questions=10,
            name=name,
            llm_preset=llm_preset,
            token_tracker=token_tracker,
        )

    def _clean_machine_test_set(
        self,
        test_set_data: dict[str, Any],
        meal_config: MealConfig,
        invalid_questions: list[dict[str, Any]],
        generation_config: dict[str, Any] | None = None,
        generator: TestSetGenerator | None = None,
        llm_preset: str = "default",
        token_tracker: Any | None = None,
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

        Returns:
            Cleaned test set dictionary.
        """
        original_count = len(test_set_data.get("questions", []))

        invalid_ids = {q.get("id") for q in invalid_questions}
        test_set_data["questions"] = [
            q for q in test_set_data.get("questions", [])
            if q.get("id") not in invalid_ids
        ]

        stored_generation_config = test_set_data["metadata"].get("generation")

        if generation_config is not None and stored_generation_config != generation_config:
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
                )
                added_count = len(test_set_data.get("questions", [])) - (original_count - len(invalid_questions))
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

        self.save_test_set(meal_config.name, test_set_data)

        logger.info(
            f"Cleaned machine test set '{test_set_data['metadata']['name']}': "
            f"removed {len(invalid_questions)}, added {added_count}"
        )

        return test_set_data

    def merge_test_sets(
        self,
        source_specs: list[dict[str, str]],
        target_meal_name: str,
        target_meal_config: MealConfig,
        name: str | None = None,
    ) -> dict[str, Any]:
        """Merge multiple test sets into a new test set.

        This method loads multiple source test sets, merges their questions,
        removes duplicates based on question text, validates source files
        against the target meal's PDF list, and creates a new merged test set.

        Args:
            source_specs: List of source test set specifications, each being
                a dict with "meal" and "test_set" keys.
            target_meal_name: Name of the target meal to save the merged test set.
            target_meal_config: MealConfig object for the target meal.
            name: Name for the new merged test set. If None, auto-generates
                a name based on the first source test set name with "_merged" suffix.

        Returns:
            The merged test set dictionary.

        Raises:
            ValueError: If a source test set does not exist or target meal is invalid.
        """
        if not source_specs:
            raise TestSetError("source_specs cannot be empty")

        all_questions: list[dict[str, Any]] = []
        loaded_sources: list[dict[str, str]] = []

        for spec in source_specs:
            source_meal = spec.get("meal")
            source_test_set = spec.get("test_set")

            if not source_meal or not source_test_set:
                raise TestSetError(
                    f"Invalid source spec: {spec}. Must have 'meal' and 'test_set' keys."
                )

            try:
                test_set_data = self.load_test_set(source_meal, source_test_set)
                questions = test_set_data.get("questions", [])
                all_questions.extend(questions)
                loaded_sources.append({"meal": source_meal, "test_set": source_test_set})
                logger.info(
                    f"Loaded {len(questions)} questions from "
                    f"meal='{source_meal}', test_set='{source_test_set}'"
                )
            except FileNotFoundError:
                raise TestSetError(
                    f"Source test set '{source_test_set}' not found in meal '{source_meal}'"
                ) from None
            except Exception as e:
                logger.error(
                    f"Failed to load test set '{source_test_set}' from meal '{source_meal}': {str(e)}"
                )
                raise

        original_count = len(all_questions)

        seen_texts: set[str] = set()
        deduped_questions: list[dict[str, Any]] = []
        dedup_count = 0

        for question in all_questions:
            question_text = question.get("question", "")
            if question_text in seen_texts:
                dedup_count += 1
                logger.debug(f"Skipping duplicate question: {question_text[:50]}...")
                continue
            seen_texts.add(question_text)
            deduped_questions.append(question)

        meal_pdf_paths = {mf.path for mf in target_meal_config.pdf_files}
        valid_questions: list[dict[str, Any]] = []
        invalid_count = 0
        invalid_questions_log: list[dict[str, Any]] = []

        for question in deduped_questions:
            question_type = question.get("question_type", "")
            source_files = question.get("source_files", [])

            if question_type == "irrelevant":
                valid_questions.append(question)
                continue

            if not source_files:
                valid_questions.append(question)
                continue

            if all(sf in meal_pdf_paths for sf in source_files):
                valid_questions.append(question)
            else:
                invalid_count += 1
                invalid_questions_log.append(question)
                logger.warning(
                    f"Question has invalid source_files: {source_files}, "
                    f"not in target meal PDFs: {meal_pdf_paths}"
                )

        final_questions: list[dict[str, Any]] = []
        for idx, question in enumerate(valid_questions, start=1):
            new_question = dict(question)
            new_question["id"] = f"q{idx:03d}"
            final_questions.append(new_question)

        final_count = len(final_questions)

        if name is None:
            first_source = source_specs[0]
            name = f"{first_source['test_set']}_merged"

        now = datetime.now().isoformat()

        composition = {
            "type": "merged",
            "sources": loaded_sources,
            "dedup_count": dedup_count,
            "original_count": original_count,
            "final_count": final_count,
        }

        audit_entry = {
            "event": "merged",
            "sources": loaded_sources,
            "dedup_count": dedup_count,
            "invalid_count": invalid_count,
            "timestamp": now,
        }

        merged_test_set = {
            "metadata": {
                "name": name,
                "meal_id": target_meal_config.data_id,
                "created_at": now,
                "updated_at": now,
                "generation": None,
                "user_defined": False,
                "invalid_policy": None,
                "audit_log": [audit_entry],
                "suppress_warnings": False,
                "composition": composition,
            },
            "quality_metrics": {},
            "questions": final_questions,
        }

        self.save_test_set(target_meal_name, merged_test_set)

        logger.success(
            f"Merged {len(loaded_sources)} test sets into '{name}': "
            f"original={original_count}, dedup={dedup_count}, "
            f"invalid={invalid_count}, final={final_count}"
        )

        return merged_test_set
