from __future__ import annotations

import json
from pathlib import Path

import yaml
from loguru import logger

from eval.experiment_reporter import ExperimentReporter
from src.exceptions import ConfigurationError, EvaluationError
from src.experiment import ExperimentManager
from src.token_tracker import TokenTracker
from src.utils import get_llm_config, load_config, setup_logger


def generate_llm_report_only(
    exp_dir: str, system_config_path: str = "config.yaml"
) -> None:
    """Generate LLM report for an already-completed experiment.

    Loads the experiment results from the given directory and generates
    an LLM-enhanced report without re-running the experiment.

    Args:
        exp_dir: Path to the experiment directory.
        system_config_path: Path to system configuration file.

    Raises:
        ConfigurationError: If the experiment directory or required files are missing.
    """
    exp_path = Path(exp_dir)
    if not exp_path.exists():
        raise ConfigurationError(f"Experiment directory not found: {exp_dir}")

    manifest_path = exp_path / "manifest.json"
    if not manifest_path.exists():
        raise ConfigurationError(f"Manifest file not found: {manifest_path}")

    system_config = load_config(system_config_path)
    setup_logger(system_config)

    exp_manager = ExperimentManager(system_config)
    exp_result = exp_manager.load_experiment_result(exp_path)

    variant_results = []
    results_dir = exp_path / "results"
    if results_dir.exists():
        for result_file in sorted(results_dir.glob("*.json")):
            try:
                with open(result_file, encoding="utf-8") as f:
                    variant_results.append(json.load(f))
            except json.JSONDecodeError as e:
                logger.warning(f"Failed to load variant result {result_file}: {str(e)}")

    if not variant_results:
        raise ConfigurationError(f"No variant results found in {exp_dir}")

    meal_info = {"config": exp_result.config} if exp_result.config else {}

    config_snapshot = {}
    config_path = exp_path / "config_snapshot.yaml"
    if config_path.exists():
        try:
            with open(config_path, encoding="utf-8") as f:
                config_snapshot = yaml.safe_load(f) or {}
        except yaml.YAMLError as e:
            logger.warning(f"Failed to load config snapshot: {str(e)}")

    llm_preset_name = config_snapshot.get("evaluation", {}).get("llm_preset", "default")
    llm_config = get_llm_config(system_config, llm_preset_name)

    token_tracker = TokenTracker()

    reporter = ExperimentReporter(
        llm_api_key=llm_config.get("api_key"),
        llm_base_url=llm_config.get("base_url"),
        llm_model_name=llm_config.get("model_name"),
        token_tracker=token_tracker,
    )

    logger.info("Generating LLM-enhanced report...")
    try:
        reporter.generate_variant_comparison_report(
            exp_dir=exp_path,
            variant_results=variant_results,
            meal_info=meal_info,
            config_snapshot=config_snapshot,
            output_filename="experiment_report_llm.md",
            use_llm=True,
        )
        logger.success("LLM-enhanced report generated successfully")
    except Exception as e:
        logger.error(f"Failed to generate LLM report: {str(e)}")
        raise EvaluationError(f"Failed to generate LLM report: {str(e)}") from e
