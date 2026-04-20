import json
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.meal import MealConfig, MealFile, MealManager
from src.utils import ensure_dir


@dataclass
class TestSetMetadata:
    name: str
    meal_id: str
    created_at: str
    updated_at: str
    generation: Optional[Dict[str, Any]] = None
    user_defined: bool = False
    invalid_policy: Optional[str] = None
    audit_log: List[Dict[str, Any]] = field(default_factory=list)
    suppress_warnings: bool = False

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TestSetMetadata":
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
        )


class TestSetManager:
    __test__ = False

    def __init__(self, config: Dict[str, Any]):
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

    def find_by_name(self, meal_name: str, test_set_name: str) -> Optional[Dict[str, Any]]:
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
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._migrate_test_set(data)
        except Exception as e:
            logger.error(f"Failed to load test set '{test_set_name}' from meal '{meal_name}': {str(e)}")
            return None

    def save_test_set(self, meal_name: str, test_set_data: Dict[str, Any]) -> Path:
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

    def load_test_set(self, meal_name: str, test_set_name: str) -> Dict[str, Any]:
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
            raise FileNotFoundError(
                f"Test set '{test_set_name}' not found in meal '{meal_name}'"
            )

        try:
            with open(file_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return self._migrate_test_set(data)
        except Exception as e:
            logger.error(f"Failed to load test set '{test_set_name}' from meal '{meal_name}': {str(e)}")
            raise

    def _migrate_test_set(self, test_set_data: Dict[str, Any]) -> Dict[str, Any]:
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
            },
            "quality_metrics": test_set_data.get("quality_metrics", {}),
            "questions": test_set_data.get("questions", []),
        }

    def list_test_sets(self, meal_name: str) -> List[Dict[str, Any]]:
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
                with open(json_file, "r", encoding="utf-8") as f:
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
            raise FileNotFoundError(
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
        test_set_data: Dict[str, Any],
        meal_config: "MealConfig",
    ) -> tuple[bool, List[Dict[str, Any]]]:
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
        questions: List[Dict[str, Any]],
        meal_config: "MealConfig",
    ) -> List[Dict[str, Any]]:
        """
        Check each question's data sources against the meal's PDF files.

        Args:
            questions: List of question dictionaries.
            meal_config: MealConfig instance for the current meal.

        Returns:
            List of questions that have missing data sources.
        """
        meal_pdf_paths = {mf.path for mf in meal_config.pdf_files}
        invalid_questions: List[Dict[str, Any]] = []

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
        test_set_data: Dict[str, Any],
        new_meal_id: str,
    ) -> Dict[str, Any]:
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
    ) -> Dict[str, Any]:
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
        test_set_data: Dict[str, Any],
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
        test_set_data: Dict[str, Any],
        meal_config: "MealConfig",
        invalid_questions: List[Dict[str, Any]],
        generator: Optional[Any] = None,
        llm_preset: str = "default",
        token_tracker: Optional[Any] = None,
    ) -> Dict[str, Any]:
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
            raise ValueError(f"Unknown invalid_policy: {invalid_policy}")

    def _clean_immutable_policy(
        self,
        test_set_data: Dict[str, Any],
        meal_config: "MealConfig",
        invalid_questions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
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
            raise ValueError(
                f"Test set has immutable policy but contains {len(invalid_questions)} "
                f"invalid questions with IDs: {invalid_ids}. "
                "Cannot modify immutable test set."
            )

        test_set_data = self._update_meal_id(test_set_data, meal_config.data_id)
        return test_set_data

    def _clean_trim_policy(
        self,
        test_set_data: Dict[str, Any],
        meal_config: "MealConfig",
        invalid_questions: List[Dict[str, Any]],
    ) -> Dict[str, Any]:
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
            raise ValueError(
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
        test_set_data: Dict[str, Any],
        meal_config: "MealConfig",
        invalid_questions: List[Dict[str, Any]],
        generator: Optional[Any],
        llm_preset: str,
        token_tracker: Optional[Any],
    ) -> Dict[str, Any]:
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
            raise ValueError(
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
        test_set_data: Dict[str, Any],
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
