from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from src.exceptions import ConfigurationError
from src.meal import compute_file_sha256


@dataclass
class AssetVerificationResult:
    """
    Result of experiment asset verification.

    Args:
        valid: Whether all assets are valid.
        missing_files: List of missing required files.
        invalid_files: List of files that exist but are invalid.
        pdf_issues: Dictionary mapping PDF paths to their issues.
        raw_dir: Path to the raw PDF directory.

    Returns:
        AssetVerificationResult instance.
    """

    valid: bool
    missing_files: list[str] = field(default_factory=list)
    invalid_files: list[str] = field(default_factory=list)
    pdf_issues: dict[str, str] = field(default_factory=dict)
    raw_dir: Path | None = None

    def to_dict(self) -> dict[str, Any]:
        """
        Convert to dictionary.

        Returns:
            Dictionary representation.
        """
        return {
            "valid": self.valid,
            "missing_files": self.missing_files,
            "invalid_files": self.invalid_files,
            "pdf_issues": self.pdf_issues,
            "raw_dir": str(self.raw_dir) if self.raw_dir else None,
        }


def sanitize_config(config: dict[str, Any]) -> dict[str, Any]:
    """
    Create a sanitized copy of configuration with sensitive fields masked.

    Removes api_key values from llm_presets to prevent credential leakage
    in experiment snapshots.

    Args:
        config: Configuration dictionary to sanitize.

    Returns:
        Deep-copied configuration with api_key values replaced by '***'.
    """
    import copy

    result = copy.deepcopy(config)
    llm_presets = result.get("llm_presets", {})
    for _preset_name, preset_config in llm_presets.items():
        if isinstance(preset_config, dict) and "api_key" in preset_config:
            preset_config["api_key"] = "***"
    return result


def verify_experiment_assets(
    exp_dir: Path,
    system_config: dict[str, Any],
    verify_pdf_hashes: bool = True,
) -> AssetVerificationResult:
    """
    Verify the integrity of experiment assets.

    This function checks:
    1. Required files exist (manifest.json, config_snapshot.yaml, meal_snapshot.json)
    2. PDF files exist in the raw directory
    3. PDF file SHA256 hashes match (if verify_pdf_hashes is True)

    Args:
        exp_dir: Path to the experiment directory.
        system_config: System configuration dictionary.
        verify_pdf_hashes: Whether to verify PDF file hashes. Set to False for faster
                          verification when hash verification is not critical.

    Returns:
        AssetVerificationResult containing verification status and any issues found.

    Raises:
        FileNotFoundError: If the experiment directory does not exist.
    """
    if not exp_dir.exists():
        raise ConfigurationError(f"Experiment directory not found: {exp_dir}")

    missing_files = []
    invalid_files = []
    pdf_issues: dict[str, str] = {}
    meal_snapshot_data: dict | None = None

    required_files = [
        "manifest.json",
        "config_snapshot.yaml",
        "meal_snapshot.json",
    ]

    for filename in required_files:
        file_path = exp_dir / filename
        if not file_path.exists():
            missing_files.append(filename)
            logger.warning(f"Missing required file: {filename}")
        else:
            try:
                if filename == "manifest.json":
                    with open(file_path, encoding="utf-8") as f:
                        data = json.load(f)
                        if not data.get("name"):
                            invalid_files.append(filename)
                            logger.warning(f"Invalid {filename}: missing 'name' field")
                elif filename == "config_snapshot.yaml":
                    import yaml

                    with open(file_path, encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if not data:
                            invalid_files.append(filename)
                            logger.warning(f"Invalid {filename}: empty or invalid YAML")
                elif filename == "meal_snapshot.json":
                    with open(file_path, encoding="utf-8") as f:
                        meal_snapshot_data = json.load(f)
                        if "pdf_files" not in meal_snapshot_data:
                            invalid_files.append(filename)
                            logger.warning(
                                f"Invalid {filename}: missing 'pdf_files' field"
                            )
            except json.JSONDecodeError as e:
                invalid_files.append(filename)
                logger.warning(f"Invalid {filename}: JSON decode error - {str(e)}")
            except yaml.YAMLError as e:
                invalid_files.append(filename)
                logger.warning(f"Invalid {filename}: YAML decode error - {str(e)}")
            except Exception as e:
                invalid_files.append(filename)
                logger.warning(f"Invalid {filename}: {str(e)}")

    raw_dir = Path(system_config.get("parser", {}).get("input_dir", "data/raw"))

    if meal_snapshot_data is not None:
        try:
            pdf_files = meal_snapshot_data.get("pdf_files", [])
            logger.info(f"Verifying {len(pdf_files)} PDF files...")

            for pdf_info in pdf_files:
                pdf_path = pdf_info.get("path", "")
                expected_sha256 = pdf_info.get("sha256", "")

                if not pdf_path:
                    pdf_issues[pdf_path or "unknown"] = "Missing path in meal snapshot"
                    continue

                full_pdf_path = raw_dir / pdf_path

                if not full_pdf_path.exists():
                    pdf_issues[pdf_path] = "File not found"
                    logger.warning(f"PDF not found: {pdf_path}")
                    continue

                if verify_pdf_hashes and expected_sha256:
                    try:
                        actual_sha256 = compute_file_sha256(full_pdf_path)
                        if actual_sha256 != expected_sha256:
                            pdf_issues[pdf_path] = (
                                f"SHA256 mismatch (expected: {expected_sha256[:12]}..., got: {actual_sha256[:12]}...)"
                            )
                            logger.warning(f"PDF SHA256 mismatch: {pdf_path}")
                        else:
                            logger.debug(f"PDF verified: {pdf_path}")
                    except Exception as e:
                        pdf_issues[pdf_path] = f"Hash computation error: {str(e)}"
                        logger.warning(
                            f"Failed to compute SHA256 for {pdf_path}: {str(e)}"
                        )
        except Exception as e:
            logger.warning(f"Failed to verify PDF files: {str(e)}")

    valid = len(missing_files) == 0 and len(invalid_files) == 0 and len(pdf_issues) == 0

    result = AssetVerificationResult(
        valid=valid,
        missing_files=missing_files,
        invalid_files=invalid_files,
        pdf_issues=pdf_issues,
        raw_dir=raw_dir,
    )

    if valid:
        logger.success("All experiment assets verified successfully")
    else:
        logger.warning(
            f"Asset verification found issues: "
            f"{len(missing_files)} missing, {len(invalid_files)} invalid, "
            f"{len(pdf_issues)} PDF issues"
        )

    return result


def collect_environment_info() -> dict[str, Any]:
    """Collect environment version information for reproducibility.

    Returns:
        Dictionary containing environment version information.
    """
    env_info = {
        "timestamp": datetime.now().isoformat(),
    }

    try:
        import platform

        env_info["os"] = platform.platform()
        env_info["python_version"] = platform.python_version()
    except Exception:
        pass

    try:
        import pkg_resources

        key_packages = [
            "torch",
            "transformers",
            "qdrant-client",
            "langchain",
            "langchain-community",
            "pymupdf",
            "pymupdf4llm",
            "sentence-transformers",
            "rank-bm25",
            "loguru",
        ]
        installed = {}
        for pkg in pkg_resources.working_set:
            if pkg.key.lower() in key_packages:
                installed[pkg.key] = pkg.version
        if installed:
            env_info["key_packages"] = installed
    except Exception:
        pass

    return env_info
