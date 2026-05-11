from __future__ import annotations

import hashlib
import json
import shutil
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from loguru import logger

from src.exceptions import ReuseError

VALID_REUSE_MODES = {"in_place", "copy_migrate", "none"}

DEFAULT_FINGERPRINT_KEYS = [
    "data.meal",
    "chunker",
    "embedding",
    "retrieval.method",
    "retrieval.top_k",
    "retrieval.reranker",
    "retrieval.query_rewrite",
]


@dataclass
class ReportReuseConfig:
    """Configuration for experiment report reuse.

    Args:
        mode: Reuse mode — "in_place" (append to target dir),
            "copy_migrate" (copy from source dir), or "none" (disabled).
        target_dir: Target experiment directory for in-place mode.
        source_dir: Source experiment directory for copy-migrate mode.
        backup_before_append: If True, create a full snapshot backup of the
            target directory before appending new variants.  Only applies to
            in-place mode; copy-migrate is inherently safe (original untouched).
        fingerprint_keys: Config key paths used to compute experiment
            fingerprints for matching.

    Returns:
        ReportReuseConfig instance.
    """

    mode: Literal["in_place", "copy_migrate", "none"] = "none"
    target_dir: str | None = None
    source_dir: str | None = None
    backup_before_append: bool = True
    fingerprint_keys: list[str] = field(
        default_factory=lambda: list(DEFAULT_FINGERPRINT_KEYS)
    )

    def to_dict(self) -> dict[str, Any]:
        return {
            "mode": self.mode,
            "target_dir": self.target_dir,
            "source_dir": self.source_dir,
            "backup_before_append": self.backup_before_append,
            "fingerprint_keys": self.fingerprint_keys,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any] | None) -> ReportReuseConfig:
        if data is None:
            return cls()
        return cls(
            mode=data.get("mode", "none"),
            target_dir=data.get("target_dir"),
            source_dir=data.get("source_dir"),
            backup_before_append=data.get("backup_before_append", True),
            fingerprint_keys=data.get(
                "fingerprint_keys", list(DEFAULT_FINGERPRINT_KEYS)
            ),
        )

    def is_enabled(self) -> bool:
        return self.mode != "none"

    def is_in_place(self) -> bool:
        return self.mode == "in_place"

    def is_copy_migrate(self) -> bool:
        return self.mode == "copy_migrate"

    def validate(self) -> list[str]:
        """Validate reuse configuration and return error messages.

        Returns:
            List of validation error messages. Empty list if valid.
        """
        errors: list[str] = []

        if self.mode not in VALID_REUSE_MODES:
            errors.append(
                f"Invalid reuse mode: '{self.mode}'. "
                f"Valid options: {sorted(VALID_REUSE_MODES)}"
            )

        if self.is_in_place() and not self.target_dir:
            errors.append("In-place mode requires 'target_dir' to be specified")

        if self.is_copy_migrate() and not self.source_dir:
            errors.append("Copy-migrate mode requires 'source_dir' to be specified")

        if self.is_in_place() and self.source_dir:
            logger.warning(
                "source_dir is ignored in in-place mode; use target_dir instead"
            )

        if self.is_copy_migrate() and self.target_dir:
            logger.warning(
                "target_dir is ignored in copy-migrate mode; use source_dir instead"
            )

        return errors


@dataclass
class ExperimentFingerprint:
    """Deterministic fingerprint of an experiment's core configuration.

    Used to determine whether two experiments are "substantively the same"
    — i.e., they differ only in variant-level overrides but share the same
    data source, chunking, embedding, and retrieval setup.

    Args:
        meal_name: Name of the meal (data source).
        chunker_config_hash: Hash of chunker configuration.
        embedding_config_hash: Hash of embedding configuration.
        retrieval_method: Retrieval method (vector/bm25/hybrid).
        retrieval_top_k: Top-K retrieval parameter.
        reranker_enabled: Whether reranker is enabled.
        query_rewrite_enabled: Whether query rewrite is enabled.
        test_set_strategy: Primary test set generation strategy.
        test_set_count: Total number of questions across test sets.

    Returns:
        ExperimentFingerprint instance.
    """

    meal_name: str
    chunker_config_hash: str
    embedding_config_hash: str
    retrieval_method: str
    retrieval_top_k: int
    reranker_enabled: bool
    query_rewrite_enabled: bool
    test_set_strategy: str
    test_set_count: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "meal_name": self.meal_name,
            "chunker_config_hash": self.chunker_config_hash,
            "embedding_config_hash": self.embedding_config_hash,
            "retrieval_method": self.retrieval_method,
            "retrieval_top_k": self.retrieval_top_k,
            "reranker_enabled": self.reranker_enabled,
            "query_rewrite_enabled": self.query_rewrite_enabled,
            "test_set_strategy": self.test_set_strategy,
            "test_set_count": self.test_set_count,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ExperimentFingerprint:
        return cls(
            meal_name=data["meal_name"],
            chunker_config_hash=data["chunker_config_hash"],
            embedding_config_hash=data["embedding_config_hash"],
            retrieval_method=data["retrieval_method"],
            retrieval_top_k=data["retrieval_top_k"],
            reranker_enabled=data["reranker_enabled"],
            query_rewrite_enabled=data["query_rewrite_enabled"],
            test_set_strategy=data["test_set_strategy"],
            test_set_count=data["test_set_count"],
        )

    def matches(self, other: ExperimentFingerprint) -> bool:
        """Check if two fingerprints are identical on all fields.

        All 9 fields must match for two fingerprints to be considered
        the same experiment configuration.

        Returns:
            True if all fields match.
        """
        return (
            self.meal_name == other.meal_name
            and self.chunker_config_hash == other.chunker_config_hash
            and self.embedding_config_hash == other.embedding_config_hash
            and self.retrieval_method == other.retrieval_method
            and self.retrieval_top_k == other.retrieval_top_k
            and self.reranker_enabled == other.reranker_enabled
            and self.query_rewrite_enabled == other.query_rewrite_enabled
            and self.test_set_strategy == other.test_set_strategy
            and self.test_set_count == other.test_set_count
        )

    def diff(self, other: ExperimentFingerprint) -> dict[str, tuple[str, str]]:
        """Compute differences between two fingerprints.

        Returns:
            Dict mapping field name to (self_value, other_value) for fields
            that differ.
        """
        differences: dict[str, tuple[str, str]] = {}
        for key in [
            "meal_name",
            "chunker_config_hash",
            "embedding_config_hash",
            "retrieval_method",
            "retrieval_top_k",
            "reranker_enabled",
            "query_rewrite_enabled",
            "test_set_strategy",
            "test_set_count",
        ]:
            self_val = getattr(self, key)
            other_val = getattr(other, key)
            if self_val != other_val:
                differences[key] = (str(self_val), str(other_val))
        return differences

    def compute_hash(self) -> str:
        """Compute a deterministic hash of the fingerprint.

        Returns:
            First 12 characters of the SHA-256 hex digest.
        """
        payload = json.dumps(self.to_dict(), sort_keys=True)
        return hashlib.sha256(payload.encode()).hexdigest()[:12]


def compute_experiment_fingerprint(
    config_snapshot: dict[str, Any],
    manifest: dict[str, Any],
) -> ExperimentFingerprint:
    """Compute an experiment fingerprint from its config snapshot and manifest.

    Args:
        config_snapshot: Merged configuration snapshot dictionary.
        manifest: Experiment manifest dictionary.

    Returns:
        ExperimentFingerprint instance.

    Raises:
        ConfigurationError: If required fields are missing.
    """
    data = config_snapshot.get("data", {})
    meal_name = data.get("meal", "unknown")

    chunker_config = config_snapshot.get("chunker", {})
    chunker_hash = _hash_config(chunker_config)

    embedding_config = config_snapshot.get("embedding", {})
    embedding_hash = _hash_config(embedding_config)

    retrieval_config = config_snapshot.get("retrieval", {})
    retrieval_method = retrieval_config.get("method", "vector")
    retrieval_top_k = retrieval_config.get("top_k", 5)
    reranker_enabled = retrieval_config.get("reranker", {}).get("enabled", False)
    query_rewrite_enabled = retrieval_config.get("query_rewrite", {}).get(
        "enabled", False
    )

    test_sets = config_snapshot.get("test_sets", [])
    if test_sets and isinstance(test_sets, list):
        first_ts = test_sets[0] if test_sets else {}
        if "generation" in first_ts:
            test_set_strategy = first_ts["generation"].get("strategy", "unknown")
        else:
            test_set_strategy = first_ts.get("strategy", "unknown")
        test_set_count = sum(
            ts.get("generation", {}).get("num_questions", ts.get("num_questions", 0))
            for ts in test_sets
            if isinstance(ts, dict)
        )
    else:
        test_set_strategy = "unknown"
        test_set_count = 0

    return ExperimentFingerprint(
        meal_name=meal_name,
        chunker_config_hash=chunker_hash,
        embedding_config_hash=embedding_hash,
        retrieval_method=retrieval_method,
        retrieval_top_k=retrieval_top_k,
        reranker_enabled=reranker_enabled,
        query_rewrite_enabled=query_rewrite_enabled,
        test_set_strategy=test_set_strategy,
        test_set_count=test_set_count,
    )


def _hash_config(config: dict[str, Any]) -> str:
    """Compute a short deterministic hash of a config dict.

    Args:
        config: Configuration dictionary.

    Returns:
        First 8 characters of the SHA-256 hex digest.
    """
    payload = json.dumps(config, sort_keys=True, default=str)
    return hashlib.sha256(payload.encode()).hexdigest()[:8]


def scan_matching_experiments(
    target_fingerprint: ExperimentFingerprint,
    exp_dir: Path,
) -> list[dict[str, Any]]:
    """Scan experiment directory for experiments matching a given fingerprint.

    Args:
        target_fingerprint: The fingerprint to match against.
        exp_dir: Root directory containing experiment folders.

    Returns:
        List of dicts with keys: experiment_id, name, path, fingerprint,
        matches (bool).
    """
    matches: list[dict[str, Any]] = []

    if not exp_dir.exists():
        return matches

    for exp_path in sorted(exp_dir.iterdir(), key=lambda p: p.name, reverse=True):
        if not exp_path.is_dir():
            continue

        manifest_path = exp_path / "manifest.json"
        config_snapshot_path = exp_path / "config_snapshot.yaml"

        if not manifest_path.exists() or not config_snapshot_path.exists():
            continue

        try:
            import yaml

            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
            with open(config_snapshot_path, encoding="utf-8") as f:
                config_snapshot = yaml.safe_load(f) or {}

            fp = compute_experiment_fingerprint(config_snapshot, manifest)
            is_match = fp.matches(target_fingerprint)

            matches.append(
                {
                    "experiment_id": manifest.get("experiment_id", exp_path.name),
                    "name": manifest.get("name", "unknown"),
                    "path": str(exp_path),
                    "fingerprint": fp.to_dict(),
                    "matches": is_match,
                }
            )
        except Exception as e:
            logger.warning(f"Failed to scan experiment {exp_path}: {str(e)}")

    return matches


@dataclass
class ReuseHistoryEntry:
    """A single entry in the reuse history log.

    Args:
        timestamp: ISO format timestamp of the operation.
        action: Type of action performed (append_variant, migrate, etc.).
        variant: Name of the variant involved (if applicable).
        backup_snapshot: Path to the backup snapshot created (if any).
        details: Additional details about the operation.

    Returns:
        ReuseHistoryEntry instance.
    """

    timestamp: str
    action: str
    variant: str | None = None
    backup_snapshot: str | None = None
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        result: dict[str, Any] = {
            "timestamp": self.timestamp,
            "action": self.action,
        }
        if self.variant is not None:
            result["variant"] = self.variant
        if self.backup_snapshot is not None:
            result["backup_snapshot"] = self.backup_snapshot
        if self.details:
            result["details"] = self.details
        return result

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> ReuseHistoryEntry:
        return cls(
            timestamp=data["timestamp"],
            action=data["action"],
            variant=data.get("variant"),
            backup_snapshot=data.get("backup_snapshot"),
            details=data.get("details", {}),
        )


@dataclass
class IncrementalPlan:
    """Plan for incremental variant execution.

    Args:
        to_run: Variants that need to be executed (new variants).
        to_reuse: Variants that can be reused from existing results.
        to_confirm: Variants that exist but have config changes,
            requiring user confirmation before overwriting.

    Returns:
        IncrementalPlan instance.
    """

    to_run: list[dict[str, Any]]
    to_reuse: list[dict[str, Any]]
    to_confirm: list[dict[str, Any]]

    @property
    def has_conflicts(self) -> bool:
        return len(self.to_confirm) > 0


class InPlaceReuseHandler:
    """Handler for in-place experiment report reuse mode.

    In-place mode appends new variant results to an existing experiment
    directory.  If backup_before_append is enabled, a full snapshot of the
    target directory is created before any modifications.

    Args:
        target_dir: Path to the target experiment directory.
        backup_before_append: Whether to create a full snapshot backup
            before appending new variants.

    Returns:
        InPlaceReuseHandler instance.
    """

    def __init__(self, target_dir: Path, backup_before_append: bool = True):
        self._target_dir = target_dir
        self._backup_before_append = backup_before_append

    @property
    def target_dir(self) -> Path:
        return self._target_dir

    @property
    def backup_root(self) -> Path:
        """Path to the backup root directory (sibling of target_dir)."""
        return self._target_dir.parent / f"{self._target_dir.name}_backup"

    def validate_target_dir(self) -> dict[str, Any]:
        """Validate that the target directory is a valid experiment directory.

        Returns:
            Manifest dictionary from the target directory.

        Raises:
            ReuseError: If the target directory is invalid.
        """
        if not self._target_dir.exists():
            raise ReuseError(f"Target directory does not exist: {self._target_dir}")

        if not self._target_dir.is_dir():
            raise ReuseError(f"Target path is not a directory: {self._target_dir}")

        manifest_path = self._target_dir / "manifest.json"
        if not manifest_path.exists():
            raise ReuseError(
                f"Target directory has no manifest.json: {self._target_dir}"
            )

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise ReuseError(f"Invalid manifest.json in target dir: {str(e)}") from e

        logger.info(f"Target directory validated: {self._target_dir}")
        return manifest

    def create_full_snapshot(self) -> Path | None:
        """Create a full snapshot backup of the target experiment directory.

        The snapshot is a complete recursive copy of the target directory,
        stored in a sibling directory named ``{target_name}_backup/{timestamp}/``.

        Returns:
            Path to the created snapshot directory, or None if backup is
            disabled.

        Raises:
            ReuseError: If snapshot creation fails.
        """
        if not self._backup_before_append:
            logger.info("Backup before append is disabled, skipping snapshot")
            return None

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        snapshot_dir = self.backup_root / timestamp

        if snapshot_dir.exists():
            suffix = 1
            while (self.backup_root / f"{timestamp}_{suffix}").exists():
                suffix += 1
            snapshot_dir = self.backup_root / f"{timestamp}_{suffix}"

        try:
            shutil.copytree(
                self._target_dir,
                snapshot_dir,
                ignore=shutil.ignore_patterns("_backup"),
            )
            logger.info(f"Full snapshot created: {snapshot_dir}")
            return snapshot_dir
        except OSError as e:
            raise ReuseError(f"Failed to create snapshot backup: {str(e)}") from e

    def restore_snapshot(self, snapshot_timestamp: str) -> None:
        """Restore the target directory from a backup snapshot.

        Args:
            snapshot_timestamp: Timestamp of the snapshot to restore
                (format: YYYYMMDD_HHMMSS or YYYYMMDD_HHMMSS_N).

        Raises:
            ReuseError: If the snapshot does not exist or restoration fails.
        """
        snapshot_dir = self.backup_root / snapshot_timestamp
        if not snapshot_dir.exists():
            raise ReuseError(f"Snapshot not found: {snapshot_dir}")

        try:
            for item in self._target_dir.iterdir():
                if item.name == f"{self._target_dir.name}_backup":
                    continue
                if item.is_dir():
                    shutil.rmtree(item)
                else:
                    item.unlink()

            for item in snapshot_dir.iterdir():
                if item.is_dir():
                    shutil.copytree(item, self._target_dir / item.name)
                else:
                    shutil.copy2(item, self._target_dir / item.name)

            logger.info(
                f"Restored experiment from snapshot: {snapshot_timestamp} -> {self._target_dir}"
            )
        except OSError as e:
            raise ReuseError(f"Failed to restore snapshot: {str(e)}") from e

    def list_snapshots(self) -> list[dict[str, Any]]:
        """List all available backup snapshots.

        Returns:
            List of dicts with keys: timestamp, path, created_at (mtime).
        """
        snapshots: list[dict[str, Any]] = []

        if not self.backup_root.exists():
            return snapshots

        for snapshot_dir in sorted(self.backup_root.iterdir()):
            if not snapshot_dir.is_dir():
                continue
            stat = snapshot_dir.stat()
            snapshots.append(
                {
                    "timestamp": snapshot_dir.name,
                    "path": str(snapshot_dir),
                    "created_at": datetime.fromtimestamp(stat.st_mtime).isoformat(),
                }
            )

        return snapshots

    def compute_incremental_updates(
        self,
        new_variants: list[dict[str, Any]],
        manifest: dict[str, Any],
        stored_hashes: dict[str, str],
        compute_variant_hash_fn: Any = None,
    ) -> IncrementalPlan:
        """Compute an incremental update plan for new variants.

        Args:
            new_variants: List of variant configurations from the new
                experiment config.
            manifest: Manifest dictionary from the target experiment.
            stored_hashes: Mapping of variant name -> config hash from
                the target experiment's manifest.
            compute_variant_hash_fn: Optional callable to compute variant
                config hashes.  If not provided, a simple name-based
                comparison is used.

        Returns:
            IncrementalPlan with to_run, to_reuse, and to_confirm lists.
        """
        completed_variants = set(manifest.get("completed_variants", []))
        all_existing_variants = set(manifest.get("variants", []))

        to_run: list[dict[str, Any]] = []
        to_reuse: list[dict[str, Any]] = []
        to_confirm: list[dict[str, Any]] = []

        for variant in new_variants:
            variant_name = variant.get("name", "unnamed")

            if variant_name not in all_existing_variants:
                to_run.append(variant)
                logger.info(f"New variant to run: {variant_name}")
            elif variant_name in completed_variants:
                if compute_variant_hash_fn and variant_name in stored_hashes:
                    current_hash = compute_variant_hash_fn(variant)
                    stored_hash = stored_hashes.get(variant_name)
                    if current_hash == stored_hash:
                        to_reuse.append(variant)
                        logger.info(
                            f"Existing variant to reuse (hash match): {variant_name}"
                        )
                    else:
                        to_confirm.append(variant)
                        logger.warning(
                            f"Existing variant with config change (hash mismatch): "
                            f"{variant_name} (stored={stored_hash[:8]}..., "
                            f"current={current_hash[:8]}...)"
                        )
                else:
                    to_reuse.append(variant)
                    logger.info(
                        f"Existing variant to reuse (no hash verification): {variant_name}"
                    )
            else:
                to_run.append(variant)
                logger.info(f"Existing but incomplete variant to run: {variant_name}")

        return IncrementalPlan(
            to_run=to_run,
            to_reuse=to_reuse,
            to_confirm=to_confirm,
        )

    def record_reuse_history(
        self,
        action: str,
        variant: str | None = None,
        backup_snapshot: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        """Record a reuse operation in the manifest's reuse_history.

        Args:
            action: Type of action performed.
            variant: Name of the variant involved (if applicable).
            backup_snapshot: Path to the backup snapshot created (if any).
            details: Additional details about the operation.

        Raises:
            ReuseError: If updating the manifest fails.
        """
        manifest_path = self._target_dir / "manifest.json"
        if not manifest_path.exists():
            logger.warning("Manifest not found, skipping reuse history record")
            return

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            entry = ReuseHistoryEntry(
                timestamp=datetime.now().isoformat(),
                action=action,
                variant=variant,
                backup_snapshot=backup_snapshot,
                details=details or {},
            )

            history = manifest.get("reuse_history", [])
            history.append(entry.to_dict())
            manifest["reuse_history"] = history

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            logger.info(f"Recorded reuse history: {action}")
        except (json.JSONDecodeError, OSError) as e:
            raise ReuseError(f"Failed to record reuse history: {str(e)}") from e

    def append_variant_to_manifest(
        self, variant_name: str, config_hash: str | None = None
    ) -> None:
        """Add a new variant to the manifest's variants list.

        Args:
            variant_name: Name of the variant to add.
            config_hash: Optional config hash for the variant.

        Raises:
            ReuseError: If updating the manifest fails.
        """
        manifest_path = self._target_dir / "manifest.json"
        if not manifest_path.exists():
            raise ReuseError("Manifest not found")

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            variants = manifest.get("variants", [])
            if variant_name not in variants:
                variants.append(variant_name)
                manifest["variants"] = variants

            if config_hash is not None:
                hashes = manifest.get("variant_config_hashes", {})
                hashes[variant_name] = config_hash
                manifest["variant_config_hashes"] = hashes

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            logger.info(f"Appended variant '{variant_name}' to manifest")
        except (json.JSONDecodeError, OSError) as e:
            raise ReuseError(f"Failed to append variant to manifest: {str(e)}") from e


class CopyMigrateHandler:
    """Handler for copy-migrate experiment report reuse mode.

    Copy-migrate mode copies an existing experiment's complete directory
    structure to a new location, then optionally runs additional variants.
    The original experiment is never modified.

    Args:
        source_dir: Path to the source experiment directory.
        exp_dir: Path to the new experiment directory (will be created).

    Returns:
        CopyMigrateHandler instance.
    """

    def __init__(self, source_dir: Path, exp_dir: Path):
        self._source_dir = source_dir
        self._exp_dir = exp_dir

    @property
    def source_dir(self) -> Path:
        return self._source_dir

    @property
    def exp_dir(self) -> Path:
        return self._exp_dir

    def validate_source_dir(self) -> dict[str, Any]:
        """Validate that the source directory is a valid experiment directory.

        Returns:
            Manifest dictionary from the source directory.

        Raises:
            ReuseError: If the source directory is invalid.
        """
        if not self._source_dir.exists():
            raise ReuseError(f"Source directory does not exist: {self._source_dir}")

        if not self._source_dir.is_dir():
            raise ReuseError(f"Source path is not a directory: {self._source_dir}")

        manifest_path = self._source_dir / "manifest.json"
        if not manifest_path.exists():
            raise ReuseError(
                f"Source directory has no manifest.json: {self._source_dir}"
            )

        config_snapshot_path = self._source_dir / "config_snapshot.yaml"
        if not config_snapshot_path.exists():
            raise ReuseError(
                f"Source directory has no config_snapshot.yaml: {self._source_dir}"
            )

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)
        except json.JSONDecodeError as e:
            raise ReuseError(f"Invalid manifest.json in source dir: {str(e)}") from e

        results_dir = self._source_dir / "results"
        if not results_dir.exists() or not any(results_dir.glob("*.json")):
            logger.warning(
                f"Source experiment has no variant results: {self._source_dir}"
            )

        logger.info(f"Source directory validated: {self._source_dir}")
        return manifest

    def copy_experiment(self) -> None:
        """Copy the complete source experiment directory to the new location.

        Raises:
            ReuseError: If the copy operation fails.
        """
        if self._exp_dir.exists():
            raise ReuseError(
                f"Target experiment directory already exists: {self._exp_dir}"
            )

        try:
            shutil.copytree(self._source_dir, self._exp_dir)
            logger.info(f"Copied experiment: {self._source_dir} -> {self._exp_dir}")
        except OSError as e:
            raise ReuseError(f"Failed to copy experiment: {str(e)}") from e

    def update_identifiers(self, new_experiment_id: str, source_exp_id: str) -> None:
        """Update experiment identifiers in the copied directory.

        Generates a new experiment_id with current timestamp, updates the
        manifest, and records the migration source.

        Args:
            new_experiment_id: New experiment ID for the migrated experiment.
            source_exp_id: Original experiment ID (recorded as migrated_from).

        Raises:
            ReuseError: If updating identifiers fails.
        """
        manifest_path = self._exp_dir / "manifest.json"
        if not manifest_path.exists():
            raise ReuseError("Manifest not found in migrated experiment")

        try:
            with open(manifest_path, encoding="utf-8") as f:
                manifest = json.load(f)

            manifest["experiment_id"] = new_experiment_id
            manifest["created_at"] = datetime.now().isoformat()
            manifest["migrated_from"] = {
                "experiment_id": source_exp_id,
                "path": str(self._source_dir),
                "migrated_at": datetime.now().isoformat(),
            }
            manifest["reuse_mode"] = "copy_migrate"
            manifest["completed_variants"] = []
            manifest["variant_config_hashes"] = {}

            with open(manifest_path, "w", encoding="utf-8") as f:
                json.dump(manifest, f, ensure_ascii=False, indent=2)

            logger.info(f"Updated identifiers: {new_experiment_id}")
        except (json.JSONDecodeError, OSError) as e:
            raise ReuseError(f"Failed to update identifiers: {str(e)}") from e

    def verify_migration(self) -> bool:
        """Verify that the migration was successful.

        Checks that all required files and directories exist in the
        migrated experiment directory.

        Returns:
            True if verification passes.

        Raises:
            ReuseError: If verification fails.
        """
        required_files = ["manifest.json", "config_snapshot.yaml", "meal_snapshot.json"]
        for fname in required_files:
            fpath = self._exp_dir / fname
            if not fpath.exists():
                raise ReuseError(f"Missing required file after migration: {fname}")

        required_dirs = ["results", "test_sets"]
        for dname in required_dirs:
            dpath = self._exp_dir / dname
            if not dpath.exists():
                raise ReuseError(f"Missing required directory after migration: {dname}")

        source_results = set(
            f.name for f in (self._source_dir / "results").glob("*.json")
        )
        migrated_results = set(
            f.name for f in (self._exp_dir / "results").glob("*.json")
        )

        missing = source_results - migrated_results
        if missing:
            raise ReuseError(f"Missing result files after migration: {sorted(missing)}")

        logger.info("Migration verification passed")
        return True

    def compute_fingerprint_diff(
        self,
        source_fingerprint: ExperimentFingerprint,
        target_fingerprint: ExperimentFingerprint,
    ) -> dict[str, tuple[str, str]]:
        """Compute fingerprint differences and warn about mismatches.

        Args:
            source_fingerprint: Fingerprint of the source experiment.
            target_fingerprint: Fingerprint of the target (new) experiment.

        Returns:
            Dict of field name -> (source_value, target_value) for differences.
        """
        diff = source_fingerprint.diff(target_fingerprint)
        if diff:
            logger.warning(
                f"Fingerprint mismatch between source and target experiments: "
                f"{list(diff.keys())}"
            )
            for field_name, (src_val, tgt_val) in diff.items():
                logger.warning(f"  {field_name}: {src_val} -> {tgt_val}")
        else:
            logger.info("Fingerprints match between source and target experiments")
        return diff
