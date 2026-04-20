import json
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

from src.meal import MealManager
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
                return json.load(f)
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
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load test set '{test_set_name}' from meal '{meal_name}': {str(e)}")
            raise

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
