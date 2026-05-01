from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from loguru import logger

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
        """Check if two fingerprints match on all mandatory fields.

        Mandatory fields (must be identical):
        - meal_name (same data source)
        - chunker_config_hash (same chunking strategy)
        - embedding_config_hash (same embedding model)
        - retrieval_method (same retrieval approach)
        - test_set_strategy (same evaluation strategy)

        Returns:
            True if all mandatory fields match.
        """
        return (
            self.meal_name == other.meal_name
            and self.chunker_config_hash == other.chunker_config_hash
            and self.embedding_config_hash == other.embedding_config_hash
            and self.retrieval_method == other.retrieval_method
            and self.test_set_strategy == other.test_set_strategy
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
