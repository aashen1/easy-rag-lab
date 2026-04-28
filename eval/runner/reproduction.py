from __future__ import annotations

import json
import tempfile
from pathlib import Path
from typing import Any

import yaml
from loguru import logger

from eval.runner.asset_verifier import verify_experiment_assets
from src.exceptions import ConfigurationError, EvaluationError
from src.utils import load_config


def reproduce_experiment(
    exp_dir: str,
    system_config_path: str = "config.yaml",
    skip_verification: bool = False,
    verify_pdf_hashes: bool = True,
    output_dir: str | None = None,
) -> dict[str, Any]:
    """
    Reproduce an experiment from its saved configuration.

    This function:
    1. Verifies the experiment assets (manifest, config, meal snapshot)
    2. Verifies PDF files exist and match SHA256 hashes
    3. Loads the saved configuration
    4. Re-runs the experiment with the same configuration

    Args:
        exp_dir: Path to the experiment directory.
        system_config_path: Path to system configuration file.
        skip_verification: If True, skip asset verification.
        verify_pdf_hashes: If True, verify PDF file SHA256 hashes.
        output_dir: Optional output directory for reproduced experiment.
                   If not specified, a new experiment directory will be created.

    Returns:
        Dictionary containing reproduction result and new experiment info.

    Raises:
        FileNotFoundError: If experiment directory or required files not found.
        ValueError: If asset verification fails and skip_verification is False.
    """
    from eval.runner.core import run_experiment

    exp_path = Path(exp_dir)

    if not exp_path.exists():
        raise ConfigurationError(f"Experiment directory not found: {exp_dir}")

    system_config = load_config(system_config_path)

    if not skip_verification:
        logger.info("Verifying experiment assets...")
        verification_result = verify_experiment_assets(
            exp_dir=exp_path,
            system_config=system_config,
            verify_pdf_hashes=verify_pdf_hashes,
        )

        if not verification_result.valid:
            logger.error("Asset verification failed!")
            print("\n" + "=" * 60)
            print("ASSET VERIFICATION FAILED")
            print("=" * 60)

            if verification_result.missing_files:
                print("\nMissing files:")
                for f in verification_result.missing_files:
                    print(f"  - {f}")

            if verification_result.invalid_files:
                print("\nInvalid files:")
                for f in verification_result.invalid_files:
                    print(f"  - {f}")

            if verification_result.pdf_issues:
                print("\nPDF issues:")
                for pdf_path, issue in verification_result.pdf_issues.items():
                    print(f"  - {pdf_path}: {issue}")

            print("\nUse --skip-verification to bypass this check.")
            print("=" * 60 + "\n")
            raise EvaluationError("Asset verification failed. See details above.")
    else:
        logger.warning("Skipping asset verification (--skip-verification)")

    config_path = exp_path / "config_snapshot.yaml"
    if not config_path.exists():
        raise ConfigurationError(f"Configuration snapshot not found: {config_path}")

    logger.info(f"Reproducing experiment from: {exp_dir}")
    logger.info("Note: Results may differ due to LLM randomness.")

    with open(config_path, encoding="utf-8") as f:
        config_snapshot = yaml.safe_load(f)

    manifest_path = exp_path / "manifest.json"
    with open(manifest_path, encoding="utf-8") as f:
        manifest = json.load(f)

    original_variants = manifest.get("variants", [])
    if original_variants:
        variants = []
        for v_name in original_variants:
            result_path = (
                exp_path
                / "results"
                / f"{v_name.lower().replace(' ', '_').replace('-', '_')}.json"
            )
            variant_config = {"name": v_name, "config_overrides": {}}

            if result_path.exists():
                try:
                    with open(result_path, encoding="utf-8") as f:
                        result_data = json.load(f)
                    if (
                        "config_snapshot" in result_data
                        and "variant" in result_data["config_snapshot"]
                    ):
                        variant_config["config_overrides"] = result_data[
                            "config_snapshot"
                        ]["variant"].get("config_overrides", {})
                        variant_config["description"] = result_data["config_snapshot"][
                            "variant"
                        ].get("description", "")
                except Exception as e:
                    logger.warning(
                        f"Failed to load variant config from {result_path}: {str(e)}"
                    )

            variants.append(variant_config)
    else:
        variants = [{"name": "reproduced", "config_overrides": {}}]

    exp_config_dict = {
        "name": f"{manifest.get('name', 'reproduced')}_reproduced",
        "description": f"Reproduced from {exp_path.name}. Original: {manifest.get('description', '')}",
        "data": config_snapshot.get("data", {}),
        "test_sets": config_snapshot.get("test_sets", []),
        "variants": variants,
        "evaluation": config_snapshot.get("evaluation", {}),
        "llm": config_snapshot.get("llm", {}),
    }

    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        yaml.dump(exp_config_dict, f)
        temp_config_path = f.name

    try:
        result = run_experiment(
            config_path=temp_config_path,
            skip_preprocessing=False,
            use_llm_report=False,
            system_config_path=system_config_path,
        )

        logger.success(f"Experiment reproduced successfully: {result['experiment_id']}")
        logger.info(f"Original experiment: {exp_path.name}")
        logger.info(f"Reproduced experiment: {result['experiment_id']}")

        return {
            "original_exp_dir": str(exp_path),
            "reproduced_exp_id": result["experiment_id"],
            "reproduced_exp_dir": result["exp_dir"],
            "verification_passed": not skip_verification,
            "result": result,
        }
    except Exception as e:
        logger.error(f"Failed to reproduce experiment: {str(e)}")
        raise
    finally:
        Path(temp_config_path).unlink()
