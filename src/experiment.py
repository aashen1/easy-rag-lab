import copy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

import yaml
from loguru import logger


@dataclass
class ExperimentConfig:
    """
    Experiment configuration.

    Args:
        name: Experiment name, used for identification and result storage.
        description: Detailed description of the experiment purpose.
        data: Data configuration, including meal settings.
        test_sets: List of test set configurations.
        variants: List of hyperparameter variants to test.
        evaluation: Evaluation configuration.
        llm: LLM configuration for different tasks.

    Returns:
        ExperimentConfig instance.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    name: str
    description: str
    data: Dict[str, Any]
    test_sets: List[Dict[str, Any]]
    variants: List[Dict[str, Any]]
    evaluation: Dict[str, Any]
    llm: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert ExperimentConfig to dictionary.

        Returns:
            Dictionary representation of the config.
        """
        return {
            "name": self.name,
            "description": self.description,
            "data": self.data,
            "test_sets": self.test_sets,
            "variants": self.variants,
            "evaluation": self.evaluation,
            "llm": self.llm,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentConfig":
        """
        Create ExperimentConfig from dictionary.

        Args:
            data: Dictionary containing experiment configuration.

        Returns:
            ExperimentConfig instance.

        Raises:
            ValueError: If required fields are missing.
        """
        required_fields = ["name", "description", "data", "test_sets", "variants", "evaluation"]
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        return cls(
            name=data["name"],
            description=data["description"],
            data=data["data"],
            test_sets=data["test_sets"],
            variants=data["variants"],
            evaluation=data["evaluation"],
            llm=data.get("llm", {}),
        )

    def validate(self) -> List[str]:
        """
        Validate the experiment configuration.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors = []

        if not self.name or not self.name.strip():
            errors.append("Experiment name cannot be empty")

        if not self.description or not self.description.strip():
            errors.append("Experiment description cannot be empty")

        if "meal" not in self.data:
            errors.append("Data configuration must include 'meal' field")

        if not self.test_sets:
            errors.append("At least one test set must be defined")
        else:
            for i, test_set in enumerate(self.test_sets):
                if "strategy" not in test_set:
                    errors.append(f"Test set {i} missing 'strategy' field")
                if "num_questions" not in test_set:
                    errors.append(f"Test set {i} missing 'num_questions' field")

        if not self.variants:
            errors.append("At least one variant must be defined")
        else:
            for i, variant in enumerate(self.variants):
                if "name" not in variant:
                    errors.append(f"Variant {i} missing 'name' field")

        if "metrics" not in self.evaluation:
            errors.append("Evaluation configuration must include 'metrics' field")

        return errors


def deep_merge(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """
    Deep merge two dictionaries.

    Values from override dictionary take precedence over base dictionary.
    Nested dictionaries are merged recursively.

    Args:
        base: Base dictionary to merge into.
        override: Dictionary with values to override.

    Returns:
        Merged dictionary.
    """
    result = copy.deepcopy(base)

    for key, value in override.items():
        if key in result and isinstance(result[key], dict) and isinstance(value, dict):
            result[key] = deep_merge(result[key], value)
        else:
            result[key] = copy.deepcopy(value)

    return result


def merge_config(
    system_config: Dict[str, Any],
    experiment_config: ExperimentConfig,
    variant: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    Merge system configuration with experiment configuration.

    The merging process:
    1. Start with a copy of system_config
    2. Apply experiment-level overrides (if any)
    3. Apply variant-specific config_overrides

    Args:
        system_config: Base system configuration from config.yaml.
        experiment_config: Experiment configuration.
        variant: Optional variant configuration with config_overrides.

    Returns:
        Merged configuration dictionary.
    """
    result = copy.deepcopy(system_config)

    if variant and "config_overrides" in variant:
        config_overrides = variant["config_overrides"]
        result = deep_merge(result, config_overrides)

    return result


def load_experiment_config(config_path: str) -> ExperimentConfig:
    """
    Load experiment configuration from YAML file.

    Args:
        config_path: Path to the experiment configuration YAML file.

    Returns:
        ExperimentConfig instance.

    Raises:
        FileNotFoundError: If the configuration file does not exist.
        ValueError: If the configuration is invalid or missing required fields.
        yaml.YAMLError: If the YAML file is malformed.
    """
    path = Path(config_path)

    if not path.exists():
        raise FileNotFoundError(f"Experiment configuration file not found: {config_path}")

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f)
    except yaml.YAMLError as e:
        logger.error(f"Failed to parse YAML file {config_path}: {str(e)}")
        raise

    if data is None:
        raise ValueError(f"Empty configuration file: {config_path}")

    if not isinstance(data, dict):
        raise ValueError(f"Configuration must be a dictionary, got {type(data).__name__}")

    try:
        config = ExperimentConfig.from_dict(data)
    except ValueError as e:
        logger.error(f"Invalid experiment configuration: {str(e)}")
        raise

    validation_errors = config.validate()
    if validation_errors:
        error_msg = "; ".join(validation_errors)
        logger.error(f"Experiment configuration validation failed: {error_msg}")
        raise ValueError(f"Configuration validation failed: {error_msg}")

    logger.info(f"Experiment configuration loaded: {config.name}")
    return config


def get_variant_config(
    system_config: Dict[str, Any],
    experiment_config: ExperimentConfig,
    variant_name: str
) -> Dict[str, Any]:
    """
    Get merged configuration for a specific variant.

    Args:
        system_config: Base system configuration from config.yaml.
        experiment_config: Experiment configuration.
        variant_name: Name of the variant to get configuration for.

    Returns:
        Merged configuration dictionary for the variant.

    Raises:
        ValueError: If variant with given name is not found.
    """
    variant = None
    for v in experiment_config.variants:
        if v.get("name") == variant_name:
            variant = v
            break

    if variant is None:
        raise ValueError(f"Variant '{variant_name}' not found in experiment configuration")

    return merge_config(system_config, experiment_config, variant)


def list_variants(experiment_config: ExperimentConfig) -> List[str]:
    """
    List all variant names in the experiment configuration.

    Args:
        experiment_config: Experiment configuration.

    Returns:
        List of variant names.
    """
    return [v.get("name", "unnamed") for v in experiment_config.variants]


def get_test_set_config(
    experiment_config: ExperimentConfig,
    index: int = 0
) -> Dict[str, Any]:
    """
    Get test set configuration by index.

    Args:
        experiment_config: Experiment configuration.
        index: Index of the test set (default: 0).

    Returns:
        Test set configuration dictionary.

    Raises:
        IndexError: If index is out of range.
    """
    if index < 0 or index >= len(experiment_config.test_sets):
        raise IndexError(
            f"Test set index {index} out of range "
            f"(0-{len(experiment_config.test_sets) - 1})"
        )

    return experiment_config.test_sets[index]


@dataclass
class ExperimentResult:
    """
    Experiment result containing all evaluation data.

    Args:
        experiment_id: Unique identifier for the experiment.
        name: Experiment name.
        description: Experiment description.
        created_at: Timestamp when the experiment was created.
        status: Current status of the experiment (running, completed, failed).
        config: Experiment configuration.
        meal_snapshot: Snapshot of the meal manifest.
        test_set_snapshots: List of test set snapshots.
        variant_results: List of evaluation results for each variant.
        config_snapshot: Snapshot of the merged configuration.

    Returns:
        ExperimentResult instance.

    Raises:
        ValueError: If required fields are missing or invalid.
    """
    experiment_id: str
    name: str
    description: str
    created_at: str
    status: str
    config: ExperimentConfig
    meal_snapshot: Dict[str, Any] = field(default_factory=dict)
    test_set_snapshots: List[Dict[str, Any]] = field(default_factory=list)
    variant_results: List[Dict[str, Any]] = field(default_factory=list)
    config_snapshot: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, Any]:
        """
        Convert ExperimentResult to dictionary.

        Returns:
            Dictionary representation of the result.
        """
        return {
            "experiment_id": self.experiment_id,
            "name": self.name,
            "description": self.description,
            "created_at": self.created_at,
            "status": self.status,
            "config": self.config.to_dict(),
            "meal_snapshot": self.meal_snapshot,
            "test_set_snapshots": self.test_set_snapshots,
            "variant_results": self.variant_results,
            "config_snapshot": self.config_snapshot,
        }

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ExperimentResult":
        """
        Create ExperimentResult from dictionary.

        Args:
            data: Dictionary containing experiment result data.

        Returns:
            ExperimentResult instance.

        Raises:
            ValueError: If required fields are missing.
        """
        required_fields = ["experiment_id", "name", "description", "created_at", "status", "config"]
        missing_fields = [f for f in required_fields if f not in data]
        if missing_fields:
            raise ValueError(f"Missing required fields: {missing_fields}")

        config = ExperimentConfig.from_dict(data["config"])

        return cls(
            experiment_id=data["experiment_id"],
            name=data["name"],
            description=data["description"],
            created_at=data["created_at"],
            status=data["status"],
            config=config,
            meal_snapshot=data.get("meal_snapshot", {}),
            test_set_snapshots=data.get("test_set_snapshots", []),
            variant_results=data.get("variant_results", []),
            config_snapshot=data.get("config_snapshot", {}),
        )


class ExperimentManager:
    """
    Experiment manager for creating, loading, and managing experiments.

    This class handles experiment directory creation, snapshot saving,
    and loading experiment results.

    Args:
        config: System configuration dictionary containing experiment settings.

    Returns:
        ExperimentManager instance.

    Raises:
        ValueError: If required configuration fields are missing.
    """

    def __init__(self, config: Dict[str, Any]):
        """
        Initialize ExperimentManager.

        Args:
            config: System configuration dictionary.
        """
        self._config = config
        experiments_config = config.get("experiments", {})
        self._exp_dir = Path(experiments_config.get("dir", "data/exp_reports"))
        self._configs_dir = Path(experiments_config.get("configs_dir", "exp_configs"))

    @property
    def exp_dir(self) -> Path:
        """Get the experiment reports directory."""
        return self._exp_dir

    @property
    def configs_dir(self) -> Path:
        """Get the experiment configs directory."""
        return self._configs_dir

    def generate_experiment_id(self, config: ExperimentConfig) -> str:
        """
        Generate a unique experiment ID based on timestamp and experiment name.

        Args:
            config: Experiment configuration.

        Returns:
            Experiment ID string in format 'exp_YYYYMMDD_HHMMSS_{name}'.
        """
        from datetime import datetime

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        safe_name = config.name.lower().replace(" ", "_").replace("-", "_")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
        return f"exp_{timestamp}_{safe_name}"

    def create_experiment_dir(self, config: ExperimentConfig) -> Path:
        """
        Create experiment directory structure.

        Creates the following structure:
        - exp_YYYYMMDD_HHMMSS_name/
          - manifest.json
          - config_snapshot.yaml
          - meal_snapshot.json
          - test_sets/
          - results/

        Args:
            config: Experiment configuration.

        Returns:
            Path to the created experiment directory.

        Raises:
            OSError: If directory creation fails.
        """
        exp_id = self.generate_experiment_id(config)
        exp_dir = self._exp_dir / exp_id

        try:
            exp_dir.mkdir(parents=True, exist_ok=True)
            (exp_dir / "test_sets").mkdir(exist_ok=True)
            (exp_dir / "results").mkdir(exist_ok=True)
            logger.info(f"Created experiment directory: {exp_dir}")
        except OSError as e:
            logger.error(f"Failed to create experiment directory: {str(e)}")
            raise

        return exp_dir

    def save_snapshots(
        self,
        exp_dir: Path,
        config: ExperimentConfig,
        meal_snapshot: Dict[str, Any],
        test_set_snapshots: List[Dict[str, Any]],
        config_snapshot: Dict[str, Any]
    ) -> None:
        """
        Save configuration and test set snapshots to the experiment directory.

        Args:
            exp_dir: Path to the experiment directory.
            config: Experiment configuration.
            meal_snapshot: Meal manifest snapshot dictionary.
            test_set_snapshots: List of test set snapshot dictionaries.
            config_snapshot: Merged configuration snapshot dictionary.

        Raises:
            OSError: If file writing fails.
        """
        try:
            config_snapshot_path = exp_dir / "config_snapshot.yaml"
            with open(config_snapshot_path, "w", encoding="utf-8") as f:
                yaml.dump(config_snapshot, f, default_flow_style=False, allow_unicode=True)
            logger.info(f"Saved config snapshot to {config_snapshot_path}")

            meal_snapshot_path = exp_dir / "meal_snapshot.json"
            with open(meal_snapshot_path, "w", encoding="utf-8") as f:
                import json
                json.dump(meal_snapshot, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved meal snapshot to {meal_snapshot_path}")

            test_sets_dir = exp_dir / "test_sets"
            for i, snapshot in enumerate(test_set_snapshots):
                strategy = snapshot.get("strategy", f"test_set_{i}")
                snapshot_path = test_sets_dir / f"{strategy}.json"
                with open(snapshot_path, "w", encoding="utf-8") as f:
                    import json
                    json.dump(snapshot, f, ensure_ascii=False, indent=2)
                logger.info(f"Saved test set snapshot to {snapshot_path}")

            manifest = self._create_manifest(exp_dir, config, test_set_snapshots)
            manifest_path = exp_dir / "manifest.json"
            with open(manifest_path, "w", encoding="utf-8") as f:
                import json
                json.dump(manifest, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved manifest to {manifest_path}")

        except OSError as e:
            logger.error(f"Failed to save snapshots: {str(e)}")
            raise

    def _create_manifest(
        self,
        exp_dir: Path,
        config: ExperimentConfig,
        test_set_snapshots: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """
        Create manifest dictionary for the experiment.

        Args:
            exp_dir: Path to the experiment directory.
            config: Experiment configuration.
            test_set_snapshots: List of test set snapshot dictionaries.

        Returns:
            Manifest dictionary.
        """
        from datetime import datetime

        exp_id = exp_dir.name
        test_set_strategies = [s.get("strategy", f"test_set_{i}") for i, s in enumerate(test_set_snapshots)]
        variant_names = [v.get("name", f"variant_{i}") for i, v in enumerate(config.variants)]

        return {
            "experiment_id": exp_id,
            "name": config.name,
            "description": config.description,
            "created_at": datetime.now().isoformat(),
            "status": "running",
            "variants": variant_names,
            "test_sets": test_set_strategies,
        }

    def load_experiment_result(self, exp_dir: Path) -> ExperimentResult:
        """
        Load experiment result from an existing experiment directory.

        Args:
            exp_dir: Path to the experiment directory.

        Returns:
            ExperimentResult instance.

        Raises:
            FileNotFoundError: If required files are missing.
            ValueError: If manifest or result files are invalid.
        """
        import json

        manifest_path = exp_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse manifest file: {str(e)}")
            raise ValueError(f"Invalid manifest file: {str(e)}")

        config_path = exp_dir / "config_snapshot.yaml"
        config_snapshot = {}
        if config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as f:
                    config_snapshot = yaml.safe_load(f) or {}
            except yaml.YAMLError as e:
                logger.warning(f"Failed to load config snapshot: {str(e)}")

        meal_snapshot_path = exp_dir / "meal_snapshot.json"
        meal_snapshot = {}
        if meal_snapshot_path.exists():
            try:
                with open(meal_snapshot_path, "r", encoding="utf-8") as f:
                    meal_snapshot = json.load(f)
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to load meal snapshot: {str(e)}")

        test_sets_dir = exp_dir / "test_sets"
        test_set_snapshots = []
        if test_sets_dir.exists():
            for snapshot_file in test_sets_dir.glob("*.json"):
                try:
                    with open(snapshot_file, "r", encoding="utf-8") as f:
                        test_set_snapshots.append(json.load(f))
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to load test set snapshot {snapshot_file}: {str(e)}")

        results_dir = exp_dir / "results"
        variant_results = []
        if results_dir.exists():
            for result_file in sorted(results_dir.glob("*.json")):
                try:
                    with open(result_file, "r", encoding="utf-8") as f:
                        variant_results.append(json.load(f))
                except json.JSONDecodeError as e:
                    logger.warning(f"Failed to load variant result {result_file}: {str(e)}")

        config_dict = {
            "name": manifest.get("name", "unknown"),
            "description": manifest.get("description", ""),
            "data": config_snapshot.get("data", {"meal": "unknown"}),
            "test_sets": [s for s in test_set_snapshots if "strategy" in s] or [{"strategy": "unknown", "num_questions": 0}],
            "variants": [{"name": v} for v in manifest.get("variants", [])] or [{"name": "unknown"}],
            "evaluation": config_snapshot.get("evaluation", {"metrics": {}}),
        }

        config = ExperimentConfig.from_dict(config_dict)

        return ExperimentResult(
            experiment_id=manifest.get("experiment_id", exp_dir.name),
            name=manifest.get("name", "unknown"),
            description=manifest.get("description", ""),
            created_at=manifest.get("created_at", ""),
            status=manifest.get("status", "unknown"),
            config=config,
            meal_snapshot=meal_snapshot,
            test_set_snapshots=test_set_snapshots,
            variant_results=variant_results,
            config_snapshot=config_snapshot,
        )

    def list_experiments(self) -> List[Dict[str, Any]]:
        """
        List all experiments in the experiment directory.

        Returns:
            List of dictionaries containing experiment info.
        """
        import json

        experiments = []

        if not self._exp_dir.exists():
            return experiments

        for exp_path in sorted(self._exp_dir.iterdir(), key=lambda p: p.name, reverse=True):
            if not exp_path.is_dir():
                continue

            manifest_path = exp_path / "manifest.json"
            if manifest_path.exists():
                try:
                    with open(manifest_path, "r", encoding="utf-8") as f:
                        manifest = json.load(f)
                    experiments.append({
                        "experiment_id": manifest.get("experiment_id", exp_path.name),
                        "name": manifest.get("name", "unknown"),
                        "created_at": manifest.get("created_at", ""),
                        "status": manifest.get("status", "unknown"),
                        "path": str(exp_path),
                    })
                except (json.JSONDecodeError, OSError) as e:
                    logger.warning(f"Failed to read manifest for {exp_path}: {str(e)}")
                    experiments.append({
                        "experiment_id": exp_path.name,
                        "name": "unknown",
                        "created_at": "",
                        "status": "corrupted",
                        "path": str(exp_path),
                    })
            else:
                experiments.append({
                    "experiment_id": exp_path.name,
                    "name": "unknown",
                    "created_at": "",
                    "status": "incomplete",
                    "path": str(exp_path),
                })

        return experiments

    def get_experiment_info(self, exp_id: str) -> Dict[str, Any]:
        """
        Get detailed information about a specific experiment.

        Args:
            exp_id: Experiment ID or experiment directory name.

        Returns:
            Dictionary containing detailed experiment information.

        Raises:
            FileNotFoundError: If experiment directory does not exist.
        """
        exp_dir = self._exp_dir / exp_id
        if not exp_dir.exists():
            raise FileNotFoundError(f"Experiment not found: {exp_id}")

        result = self.load_experiment_result(exp_dir)
        return result.to_dict()

    def update_manifest_status(self, exp_dir: Path, status: str) -> None:
        """
        Update the status field in the manifest file.

        Args:
            exp_dir: Path to the experiment directory.
            status: New status value (running, completed, failed).

        Raises:
            FileNotFoundError: If manifest file does not exist.
            OSError: If file writing fails.
        """
        import json

        manifest_path = exp_dir / "manifest.json"
        if not manifest_path.exists():
            raise FileNotFoundError(f"Manifest file not found: {manifest_path}")

        try:
            with open(manifest_path, "r", encoding="utf-8") as f:
                manifest = json.load(f)

            manifest["status"] = status

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            logger.info(f"Updated experiment status to '{status}'")
        except (json.JSONDecodeError, OSError) as e:
            logger.error(f"Failed to update manifest status: {str(e)}")
            raise

    def save_variant_result(
        self,
        exp_dir: Path,
        variant_name: str,
        result: Dict[str, Any]
    ) -> Path:
        """
        Save evaluation result for a specific variant.

        Args:
            exp_dir: Path to the experiment directory.
            variant_name: Name of the variant.
            result: Evaluation result dictionary.

        Returns:
            Path to the saved result file.

        Raises:
            OSError: If file writing fails.
        """
        import json

        results_dir = exp_dir / "results"
        results_dir.mkdir(exist_ok=True)

        safe_name = variant_name.lower().replace(" ", "_").replace("-", "_")
        safe_name = "".join(c for c in safe_name if c.isalnum() or c == "_")
        result_path = results_dir / f"{safe_name}.json"

        try:
            with open(result_path, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)
            logger.info(f"Saved variant result to {result_path}")
        except OSError as e:
            logger.error(f"Failed to save variant result: {str(e)}")
            raise

        return result_path
