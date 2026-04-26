from __future__ import annotations

import argparse
import json
import sys
import time
import warnings
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import yaml
from loguru import logger

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

import contextlib  # noqa: E402

from eval.evaluators.base import BaseEvaluator  # noqa: E402
from eval.evaluators.builtin_evaluator import BuiltinEvaluator  # noqa: E402
from eval.evaluators.ragas_evaluator import RagasEvaluator  # noqa: E402
from eval.experiment_reporter import ExperimentReporter  # noqa: E402
from eval.metrics.metric_resolver import MetricResolver  # noqa: E402
from eval.pipeline_profiler import PipelineProfiler  # noqa: E402
from eval.visualize_profiler import generate_profiler_charts  # noqa: E402
from src.exceptions import (  # noqa: E402
    ConfigurationError,
    EvaluationError,
    TestSetError,
)
from src.experiment import (  # noqa: E402
    ExperimentConfig,
    ExperimentManager,
    is_new_format,
    load_experiment_config,
    merge_config,
)
from src.generator import Generator  # noqa: E402
from src.hybrid_retriever import HybridRetriever  # noqa: E402
from src.meal import (  # noqa: E402
    ArtifactCache,
    MealManager,
    MealStatus,
    build_chunks_if_needed,
    build_index_from_chunks,
    compute_chunker_config_hash,
    compute_file_sha256,
    compute_index_key,
    generate_collection_name,
)
from src.pipeline import RAGPipeline  # noqa: E402
from src.sampler import SamplingConfig  # noqa: E402
from src.test_generator import TestSetGenerator  # noqa: E402
from src.test_set_manager import TestSetManager  # noqa: E402
from src.token_tracker import TokenTracker  # noqa: E402
from src.utils import get_llm_config, load_config, setup_logger  # noqa: E402

if TYPE_CHECKING:
    from src.indexer import VectorIndexer
    from src.meal import MealConfig


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
                        data = json.load(f)
                        if "pdf_files" not in data:
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

    meal_snapshot_path = exp_dir / "meal_snapshot.json"
    if meal_snapshot_path.exists():
        try:
            with open(meal_snapshot_path, encoding="utf-8") as f:
                meal_snapshot = json.load(f)

            pdf_files = meal_snapshot.get("pdf_files", [])
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
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse meal_snapshot.json: {str(e)}")
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
            "pymupdf4llllm",
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


def prepare_meal(
    system_config: dict[str, Any],
    exp_config: ExperimentConfig,
    skip_preprocessing: bool = False,
    force_meal: bool = False,
    force_parse: bool = False,
    force_chunk: bool = False,
) -> dict[str, Any]:
    """
    Prepare meal for experiment.

    Checks if the specified meal exists. If not and create_if_missing is configured,
    creates the meal automatically.

    Args:
        system_config: System configuration dictionary.
        exp_config: Experiment configuration.
        skip_preprocessing: If True, skip preprocessing even if meal doesn't exist.
        force_meal: If True, delete existing meal and recreate from scratch.
        force_parse: If True, re-parse PDFs even if cached parsed artifacts exist.
        force_chunk: If True, re-chunk documents even if cached chunk artifacts exist.

    Returns:
        Dictionary containing meal configuration and status.

    Raises:
        FileNotFoundError: If meal doesn't exist and create_if_missing is not configured.
        ValueError: If meal creation fails.
    """
    meal_manager = MealManager(system_config)
    meal_name = exp_config.data.get("meal")

    if not meal_name:
        raise ConfigurationError(
            "Experiment configuration must specify a meal name in data.meal field"
        )

    if force_meal and meal_manager.meal_exists(meal_name):
        logger.warning(
            f"Force overwrite: deleting existing meal '{meal_name}' and recreating"
        )
        import shutil

        meal_dir = meal_manager.get_meal_dir(meal_name)
        trashbin = Path(project_root) / ".trashbin"
        trashbin.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trashed_name = f"{meal_name}_{timestamp}"
        trashed_path = trashbin / trashed_name
        shutil.move(str(meal_dir), str(trashed_path))
        logger.info(f"Moved existing meal to trashbin: {trashed_path}")

    if meal_manager.meal_exists(meal_name):
        logger.info(f"Meal '{meal_name}' found, loading...")
        meal_config = meal_manager.load_meal(meal_name)

        status, issues = meal_manager.check_meal_status(meal_name)
        if status != MealStatus.AVAILABLE:
            logger.warning(
                f"Meal '{meal_name}' status: {status.value}. "
                f"Issues: {len(issues)} files affected."
            )
            for issue in issues[:5]:
                logger.warning(f"  - {issue}")
            if len(issues) > 5:
                logger.warning(f"  ... and {len(issues) - 5} more issues")
        else:
            logger.success(f"Meal '{meal_name}' is available and valid")

        return {
            "name": meal_name,
            "config": meal_config,
            "status": status,
            "issues": issues,
            "data_id": meal_config.data_id,
            "collection_name": meal_config.collection_name,
        }

    create_config = exp_config.data.get("create_if_missing")
    if not create_config:
        raise ConfigurationError(
            f"Meal '{meal_name}' not found and create_if_missing is not configured. "
            "Please create the meal first or add create_if_missing configuration."
        )

    if skip_preprocessing:
        raise ConfigurationError(
            f"Meal '{meal_name}' not found and skip_preprocessing is enabled. "
            "Cannot create meal in skip_preprocessing mode."
        )

    logger.info(f"Meal '{meal_name}' not found, creating with configuration...")

    sample_mode = None
    sample_value = None
    if "sample_count" in create_config:
        sample_mode = "count"
        sample_value = create_config["sample_count"]
    elif "sample_pages" in create_config:
        sample_mode = "pages"
        sample_value = create_config["sample_pages"]
    elif "sample_ratio" in create_config:
        sample_mode = "ratio"
        sample_value = create_config["sample_ratio"]
    else:
        sample_mode = "ratio"
        sample_value = 1.0
        logger.warning(
            "No sampling configuration found, using full dataset (ratio=1.0)"
        )

    sampling_config = SamplingConfig(mode=sample_mode, value=sample_value)
    seed = create_config.get("seed")

    try:
        meal_config = meal_manager.create_meal(
            name=meal_name,
            sampling_config=sampling_config,
            seed=seed,
            force_parse=force_parse,
            force_chunk=force_chunk,
        )
        logger.success(f"Meal '{meal_name}' created successfully")

        return {
            "name": meal_name,
            "config": meal_config,
            "status": MealStatus.AVAILABLE,
            "issues": [],
            "data_id": meal_config.data_id,
            "collection_name": meal_config.collection_name,
        }
    except Exception as e:
        logger.error(f"Failed to create meal '{meal_name}': {str(e)}")
        raise


def _prepare_legacy_test_set(
    system_config: dict[str, Any],
    meal_name: str,
    test_set_config: dict[str, Any],
    meal_manager: MealManager,
    generator: TestSetGenerator,
    llm_preset: str,
    skip_preprocessing: bool,
    token_tracker: TokenTracker | None,
) -> dict[str, Any]:
    """
    Legacy test set preparation for old format configs.

    Args:
        system_config: System configuration dictionary.
        meal_name: Name of the meal.
        test_set_config: Test set configuration dictionary (old format).
        meal_manager: MealManager instance.
        generator: TestSetGenerator instance.
        llm_preset: LLM preset name.
        skip_preprocessing: If True, skip generation even if test sets don't exist.
        token_tracker: Optional token tracker.

    Returns:
        Test set dictionary.

    Raises:
        FileNotFoundError: If test set doesn't exist and skip_preprocessing is True.
    """
    meal_dir = meal_manager.get_meal_dir(meal_name)
    test_sets_dir = meal_dir / "test_sets"

    strategy = test_set_config.get("strategy", "document")
    num_questions = test_set_config.get("num_questions", 20)
    seed = test_set_config.get("seed")
    type_distribution = test_set_config.get("type_distribution")

    if strategy == "document":
        filename = f"document_level_n{num_questions}"
    else:
        filename = f"auto_{strategy}_n{num_questions}"
    test_set_path = test_sets_dir / f"{filename}.json"

    if test_set_path.exists():
        logger.info(f"Test set '{filename}' found, loading...")
        try:
            with open(test_set_path, encoding="utf-8") as f:
                test_set_data = json.load(f)

            existing_count = len(test_set_data.get("questions", []))
            if existing_count < num_questions:
                logger.warning(
                    f"Existing test set has {existing_count} questions, "
                    f"but {num_questions} requested. Supplementing "
                    f"{num_questions - existing_count} more questions."
                )
                if skip_preprocessing:
                    raise TestSetError(
                        f"Test set '{filename}' has insufficient questions "
                        f"({existing_count}/{num_questions}) and "
                        f"skip_preprocessing is enabled. "
                        f"Cannot supplement in skip_preprocessing mode."
                    )
                try:
                    if strategy == "document":
                        test_set_data = generator.supplement_document_based_questions(
                            meal_name=meal_name,
                            existing_test_set=test_set_data,
                            target_count=num_questions,
                            llm_preset=llm_preset,
                            token_tracker=token_tracker,
                        )
                    else:
                        logger.warning(
                            f"Supplement not supported for strategy "
                            f"'{strategy}', regenerating from scratch"
                        )
                        test_set_path.unlink()
                        test_set_data = None

                    if test_set_data is not None:
                        final_count = len(test_set_data.get("questions", []))
                        logger.success(
                            f"Test set '{filename}' supplemented ({final_count} questions)"
                        )
                        return test_set_data
                except Exception as e:
                    logger.error(
                        f"Failed to supplement test set '{filename}': {str(e)}"
                    )
                    logger.warning("Falling back to full regeneration")
                    test_set_path.unlink()
            elif existing_count > num_questions:
                logger.warning(
                    f"Existing test set has {existing_count} questions, "
                    f"but {num_questions} requested. Truncating to "
                    f"{num_questions}."
                )
                test_set_data["questions"] = test_set_data["questions"][:num_questions]
                logger.success(
                    f"Test set '{filename}' truncated ({num_questions} questions)"
                )
                return test_set_data
            else:
                logger.success(
                    f"Test set '{filename}' loaded ({existing_count} questions)"
                )
                return test_set_data
        except FileNotFoundError:
            raise
        except Exception as e:
            logger.warning(
                f"Failed to load test set '{filename}': {str(e)}, will regenerate"
            )

    if skip_preprocessing:
        raise TestSetError(
            f"Test set '{filename}' not found and skip_preprocessing is enabled. "
            "Cannot generate test set in skip_preprocessing mode."
        )

    logger.info(
        f"Generating test set '{filename}' ({strategy}, {num_questions} questions)..."
    )

    try:
        if strategy == "document":
            test_set_data = generator.generate_document_based_questions(
                meal_name=meal_name,
                num_questions=num_questions,
                type_distribution=type_distribution,
                llm_preset=llm_preset,
                token_tracker=token_tracker,
            )
        else:
            test_set_data = generator.generate_test_set(
                meal_name=meal_name,
                strategy=strategy,
                num_questions=num_questions,
                llm_preset=llm_preset,
                seed=seed,
                token_tracker=token_tracker,
            )

        logger.success(
            f"Test set '{filename}' generated ({len(test_set_data.get('questions', []))} questions)"
        )
        return test_set_data
    except Exception as e:
        logger.error(f"Failed to generate test set '{filename}': {str(e)}")
        raise


def prepare_test_sets(
    system_config: dict[str, Any],
    exp_config: ExperimentConfig,
    meal_info: dict[str, Any],
    skip_preprocessing: bool = False,
    token_tracker: TokenTracker | None = None,
    chunks_dir: Path | None = None,
    force_testset: bool = False,
) -> list[dict[str, Any]]:
    """
    Prepare test sets for experiment.

    For new format (has 'name' field): uses TestSetManager.resolve_test_set()
    For old format: uses legacy logic with deprecation warning

    Args:
        system_config: System configuration dictionary.
        exp_config: Experiment configuration.
        meal_info: Meal information dictionary from prepare_meal.
        skip_preprocessing: If True, skip generation even if test sets don't exist.
        token_tracker: Optional token tracker.
        chunks_dir: Optional path to chunks directory for answer chunk location.
        force_testset: If True, force regeneration of test sets, ignoring cache.

    Returns:
        List of test set dictionaries.

    Raises:
        FileNotFoundError: If test set doesn't exist and skip_preprocessing is True.
        ValueError: If test set resolution fails.
    """
    meal_name = meal_info["name"]
    meal_manager = MealManager(system_config)
    meal_config = meal_manager.load_meal(meal_name)

    test_set_manager = TestSetManager(system_config)
    generator = TestSetGenerator(system_config)
    llm_preset = exp_config.evaluation.get("llm_preset", "default")

    test_sets = []

    for test_set_config in exp_config.test_sets:
        if is_new_format(test_set_config):
            if skip_preprocessing:
                name = test_set_config.get("name")
                test_set_data = test_set_manager.find_by_name(meal_name, name)
                if test_set_data is None:
                    raise TestSetError(
                        f"Test set '{name}' not found and skip_preprocessing is enabled."
                    )
                is_valid, invalid_qs = test_set_manager.validate_test_set(
                    test_set_data, meal_config
                )
                if not is_valid:
                    raise TestSetError(
                        f"Test set '{name}' is invalid and skip_preprocessing is enabled."
                    )
            else:
                test_set_data = test_set_manager.resolve_test_set(
                    meal_name=meal_name,
                    test_set_config=test_set_config,
                    meal_config=meal_config,
                    generator=generator,
                    llm_preset=llm_preset,
                    token_tracker=token_tracker,
                    chunks_dir=chunks_dir,
                    force_regenerate=force_testset,
                )
            test_sets.append(test_set_data)
        else:
            warnings.warn(
                "test_sets uses deprecated configuration format. "
                "The experiment will run normally, but please consider migrating to the new format:\n"
                "  test_sets:\n"
                '    - name: "<custom_name>"\n'
                '      on_missing: "auto"\n'
                "      generation:\n"
                '        strategy: "document"\n'
                "        num_questions: 10",
                DeprecationWarning,
                stacklevel=2,
            )
            test_set_data = _prepare_legacy_test_set(
                system_config=system_config,
                meal_name=meal_name,
                test_set_config=test_set_config,
                meal_manager=meal_manager,
                generator=generator,
                llm_preset=llm_preset,
                skip_preprocessing=skip_preprocessing,
                token_tracker=token_tracker,
            )
            test_sets.append(test_set_data)

    return test_sets


def prepare_variant_chunks(
    merged_config: dict[str, Any],
    meal_config: MealConfig,
    variant_name: str,
    force_chunk: bool = False,
) -> Path:
    """Build chunks for a variant if not already cached.

    This function ensures chunks are available before test set generation,
    so that _locate_answer_chunks() can find the correct chunk files.

    Args:
        merged_config: Merged configuration dictionary.
        meal_config: Meal configuration object.
        variant_name: Name of the variant.
        force_chunk: If True, delete existing chunks and rebuild from scratch.

    Returns:
        Path to the chunks directory for this variant.
    """
    chunker_config = merged_config.get("chunker", {})
    embedding_config = merged_config.get("embedding", {})

    chunker_hash = compute_chunker_config_hash(chunker_config)

    artifacts_config = merged_config.get("artifacts") or {}
    artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
    raw_dir = Path(merged_config.get("parser", {}).get("input_dir", "data/raw"))
    cache = ArtifactCache(artifacts_dir, raw_dir)

    parsed_dir = cache.get_parsed_dir(
        meal_config.data_id,
        parser_hash=meal_config.config_hashes.get("parser"),
    )
    chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)

    build_chunks_if_needed(
        parsed_dir,
        chunks_dir,
        chunker_config,
        model_name=chunker_config.get("model_name")
        or embedding_config.get("model_name"),
        force=force_chunk,
    )

    logger.info(f"Chunks ready for variant '{variant_name}': {chunks_dir}")
    return chunks_dir


def prepare_index_for_variant(
    merged_config: dict[str, Any],
    meal_config: MealConfig,
    variant_name: str,
    force_index: bool = False,
) -> VectorIndexer:
    """
    Prepare or retrieve index for a variant.

    Checks if the index already exists for the variant's configuration.
    If not, builds chunks and index from scratch.

    Args:
        merged_config: Merged configuration dictionary.
        meal_config: Meal configuration object.
        variant_name: Name of the variant.
        force_index: If True, delete existing index and rebuild from scratch.

    Returns:
        Configured VectorIndexer instance.
    """
    from src.indexer import VectorIndexer

    chunker_config = merged_config.get("chunker", {})
    embedding_config = merged_config.get("embedding", {})
    vector_store_config = merged_config.get("vector_store", {})

    chunker_hash = compute_chunker_config_hash(chunker_config)
    config_hashes = {
        "parser": meal_config.config_hashes.get("parser", ""),
        "chunker": chunker_hash,
        "embedding": meal_config.config_hashes.get("embedding", ""),
    }
    index_key = compute_index_key(meal_config.data_id, config_hashes)
    collection_name = generate_collection_name(
        index_key,
        merged_config.get("meals", {}).get("collection_prefix", "m_"),
    )

    logger.info(f"Using collection: {collection_name}")

    indexer = VectorIndexer(
        persist_dir=vector_store_config.get("persist_dir", "data/vector_store"),
        collection_name=collection_name,
        distance=vector_store_config.get("distance", "Cosine"),
    )

    collection_info = indexer.get_collection_info()
    index_exists = (
        collection_info is not None and collection_info.get("points_count", 0) > 0
    )

    if force_index and index_exists:
        logger.info(
            f"Force overwrite: deleting existing index for variant '{variant_name}'"
        )
        indexer.delete_collection()
        indexer.close()
        index_exists = False

    if not index_exists:
        logger.info(f"Building index for variant '{variant_name}'...")

        if not force_index:
            indexer.close()

        artifacts_config = merged_config.get("artifacts") or {}
        artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
        raw_dir = Path(merged_config.get("parser", {}).get("input_dir", "data/raw"))
        cache = ArtifactCache(artifacts_dir, raw_dir)

        parsed_dir = cache.get_parsed_dir(
            meal_config.data_id,
            parser_hash=meal_config.config_hashes.get("parser"),
        )
        chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)

        build_chunks_if_needed(
            parsed_dir,
            chunks_dir,
            chunker_config,
            model_name=chunker_config.get("model_name")
            or embedding_config.get("model_name"),
        )

        indexer = build_index_from_chunks(
            chunks_dir=chunks_dir,
            embedding_config=embedding_config,
            vector_store_config=vector_store_config,
            collection_name=collection_name,
        )

        logger.success(f"Index built for variant '{variant_name}'")
    else:
        logger.info(
            f"Index already exists for variant '{variant_name}' "
            f"({collection_info.get('points_count')} points)"
        )

    return indexer


def _create_evaluators(
    exp_config: ExperimentConfig,
    system_config: dict[str, Any],
) -> dict[str, BaseEvaluator]:
    """
    Create evaluator instances based on experiment configuration.

    Args:
        exp_config: Experiment configuration.
        system_config: System configuration dictionary.

    Returns:
        Dictionary mapping backend name to evaluator instance.
    """
    backends = exp_config.evaluation.get("backends", ["builtin"])
    evaluators: dict[str, BaseEvaluator] = {}

    for backend in backends:
        if backend == "builtin":
            evaluators["builtin"] = BuiltinEvaluator(config=system_config)
        elif backend == "ragas":
            ragas_config = system_config.get("evaluation", {}).get("ragas", {})
            evaluators["ragas"] = RagasEvaluator(
                config={**system_config, "ragas": ragas_config}
            )
        else:
            logger.warning(f"Unknown evaluation backend: {backend}")

    return evaluators


def _collect_rag_samples(
    pipeline: RAGPipeline,
    test_set: dict[str, Any],
    equivalence_groups: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Run pipeline queries and collect raw samples for evaluation.

    Args:
        pipeline: Configured RAG pipeline.
        test_set: Test set dictionary with questions.
        equivalence_groups: Optional dict mapping group keys to lists of
            equivalent file paths for dedup normalization.

    Returns:
        List of sample dictionaries with query results.
    """
    test_set_name = test_set.get("name") or test_set.get("metadata", {}).get(
        "name", "unknown"
    )
    questions = test_set.get("questions", [])
    questions = [
        q for q in questions if q.get("metadata", {}).get("review_status") != "rejected"
    ]

    logger.info(
        f"Collecting results for test set '{test_set_name}' ({len(questions)} questions)..."
    )

    samples = []
    for i, question_data in enumerate(questions, 1):
        question_id = question_data.get("id", f"q{i}")
        question_text = question_data.get("question", "")

        if not question_text:
            logger.warning(f"Question {question_id} has no text, skipping")
            continue

        logger.info(f"Processing question {i}/{len(questions)}: {question_id}")

        case_start_time = time.time()
        try:
            response = pipeline.query(question_text)
            case_time = time.time() - case_start_time

            sample = {
                "question_id": question_id,
                "question": question_text,
                "answer": response.get("answer", ""),
                "contexts": response.get("contexts", []),
                "expected_sources": question_data.get("source_files", []),
                "expected_answer": question_data.get("answer"),
                "ground_truth_excerpt": question_data.get("ground_truth_excerpt"),
                "retrieved_sources": response.get("sources", []),
                "chunk_ids": response.get("chunk_ids", []),
                "expected_chunks": question_data.get("source_chunks", []),
                "equivalence_groups": equivalence_groups,
                "question_type": question_data.get("question_type", "factual"),
                "time_seconds": case_time,
                "test_set": test_set_name,
                "category": question_data.get("category"),
                "difficulty": question_data.get("difficulty"),
                "token_usage": response.get("token_usage"),
                "expect_retrieval": question_data.get("expect_retrieval", True),
                "expect_no_answer": question_data.get("expect_no_answer", False),
            }

            logger.success(
                f"Question {question_id}: collected result ({case_time:.2f}s)"
            )

        except Exception as e:
            case_time = time.time() - case_start_time
            logger.error(f"Question {question_id} failed: {str(e)}")
            sample = {
                "question_id": question_id,
                "question": question_text,
                "answer": "",
                "contexts": [],
                "expected_sources": question_data.get("source_files", []),
                "expected_answer": question_data.get("answer"),
                "ground_truth_excerpt": question_data.get("ground_truth_excerpt"),
                "retrieved_sources": [],
                "chunk_ids": [],
                "expected_chunks": question_data.get("source_chunks", []),
                "equivalence_groups": equivalence_groups,
                "question_type": question_data.get("question_type", "factual"),
                "expect_retrieval": question_data.get("expect_retrieval", True),
                "expect_no_answer": question_data.get("expect_no_answer", False),
                "time_seconds": case_time,
                "test_set": test_set_name,
                "category": question_data.get("category"),
                "error": str(e),
            }

        samples.append(sample)

    return samples


def _evaluate_with_builtin(
    samples: list[dict[str, Any]],
    evaluator: BuiltinEvaluator,
    llm_config: dict[str, str] | None = None,
    retrieval_metrics: list[str] | None = None,
    generation_metrics: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate samples using the builtin evaluator.

    Args:
        samples: List of sample dictionaries from _collect_rag_samples.
        evaluator: BuiltinEvaluator instance.
        llm_config: Optional LLM configuration for generation metrics.
        retrieval_metrics: Optional list of retrieval metrics to compute.
        generation_metrics: Optional list of generation metrics to compute.

    Returns:
        List of evaluation result dictionaries.
    """
    results = []
    for sample in samples:
        question_id = sample["question_id"]

        if "error" in sample:
            result = {
                "id": question_id,
                "question": sample["question"],
                "answer": None,
                "error": sample["error"],
                "expected_sources": sample.get("expected_sources", []),
                "time_seconds": sample.get("time_seconds", 0),
                "test_set": sample.get("test_set", ""),
                "category": sample.get("category"),
            }
            results.append(result)
            continue

        expected_answer = sample.get("ground_truth_excerpt")
        if not expected_answer and sample.get("expect_retrieval", True):
            expected_answer = sample.get("expected_answer")

        eval_result = evaluator.evaluate_single(
            question_id=question_id,
            question=sample["question"],
            answer=sample["answer"],
            contexts=sample.get("contexts", []),
            expected_sources=sample.get("expected_sources"),
            expected_answer=expected_answer,
            llm_config=llm_config,
            retrieval_metrics=retrieval_metrics,
            generation_metrics=generation_metrics,
            chunk_ids=sample.get("chunk_ids"),
            expected_chunks=sample.get("expected_chunks"),
            equivalence_groups=sample.get("equivalence_groups"),
            expect_retrieval=sample.get("expect_retrieval", True),
            expect_no_answer=sample.get("expect_no_answer", False),
            retrieved_sources=sample.get("retrieved_sources", []),
            question_type=sample.get("question_type"),
        )

        raw_retrieval = eval_result.retrieval_metrics

        doc_metrics = {}
        chunk_metrics = {}
        dedup_metrics = {}
        fpr_value = None

        for k, v in raw_retrieval.items():
            if k.startswith("chunk_"):
                chunk_metrics[k.removeprefix("chunk_")] = v
            elif k.startswith("dedup_"):
                dedup_metrics[k.removeprefix("dedup_")] = v
            elif k == "false_positive_rate":
                fpr_value = v
            else:
                doc_metrics[k] = v

        result = {
            "id": question_id,
            "question": sample["question"],
            "answer": sample["answer"],
            "retrieval": doc_metrics,
            "chunk_retrieval": chunk_metrics if chunk_metrics else None,
            "dedup_retrieval": dedup_metrics if dedup_metrics else None,
            "false_positive_rate": fpr_value,
            "sources": sample.get("retrieved_sources", []),
            "expected_sources": sample.get("expected_sources", []),
            "time_seconds": sample.get("time_seconds", 0),
            "test_set": sample.get("test_set", ""),
            "category": sample.get("category"),
            "difficulty": sample.get("difficulty"),
            "question_type": sample.get("question_type"),
            "expect_retrieval": sample.get("expect_retrieval", True),
            "token_usage": sample.get("token_usage"),
        }

        if eval_result.generation_metrics:
            result["generation"] = eval_result.generation_metrics

        if eval_result.error:
            result["error"] = eval_result.error

        metric_parts = []
        for k, v in eval_result.retrieval_metrics.items():
            if v is not None:
                metric_parts.append(f"{k.upper()}={v:.4f}")
        for k, v in eval_result.generation_metrics.items():
            if v is not None:
                metric_parts.append(f"{k}={v:.4f}")
        metric_str = ", ".join(metric_parts) if metric_parts else "no metrics"
        logger.success(f"Question {question_id}: {metric_str}")

        results.append(result)

    return results


def _evaluate_with_ragas(
    samples: list[dict[str, Any]],
    evaluator: RagasEvaluator,
    llm_config: dict[str, str],
    generation_metrics: list[str] | None = None,
    retrieval_metrics: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate samples using the RAGAS evaluator.

    Args:
        samples: List of sample dictionaries from _collect_rag_samples.
        evaluator: RagasEvaluator instance.
        llm_config: LLM configuration for RAGAS.
        generation_metrics: Optional list of generation metrics to compute.
        retrieval_metrics: Optional list of retrieval metrics to compute
            (RAGAS-supported ones like context_precision, context_recall).

    Returns:
        List of evaluation result dictionaries.
    """
    valid_samples = [s for s in samples if "error" not in s]

    if not valid_samples:
        logger.warning("No valid samples for RAGAS evaluation")
        return []

    ragas_from_retrieval = [
        m
        for m in (retrieval_metrics or [])
        if m in evaluator.supported_generation_metrics
    ]

    all_ragas_metrics = list(
        dict.fromkeys((generation_metrics or []) + ragas_from_retrieval)
    )

    if not all_ragas_metrics:
        return []

    logger.info(f"Running RAGAS evaluation on {len(valid_samples)} samples...")

    ragas_results = evaluator.evaluate_batch(
        samples=valid_samples,
        llm_config=llm_config,
        generation_metrics=all_ragas_metrics,
    )

    retrieval_metric_names = set(ragas_from_retrieval)

    results = []
    for i, eval_result in enumerate(ragas_results):
        sample = valid_samples[i]

        generation_part = {}
        llm_retrieval_part = {}
        expect_retrieval = sample.get("expect_retrieval", True)

        for k, v in eval_result.generation_metrics.items():
            if k in retrieval_metric_names:
                if expect_retrieval:
                    llm_retrieval_part[k] = v
            else:
                if not expect_retrieval and k in (
                    "answer_correctness",
                    "semantic_similarity",
                ):
                    continue
                generation_part[k] = v

        result = {
            "id": sample["question_id"],
            "question": sample["question"],
            "answer": sample["answer"],
            "generation": generation_part,
            "sources": sample.get("retrieved_sources", []),
            "expected_sources": sample.get("expected_sources", []),
            "time_seconds": sample.get("time_seconds", 0),
            "test_set": sample.get("test_set", ""),
            "category": sample.get("category"),
            "difficulty": sample.get("difficulty"),
        }

        if llm_retrieval_part:
            result["llm_retrieval"] = llm_retrieval_part

        if eval_result.error:
            result["ragas_error"] = eval_result.error

        metric_parts = []
        for k, v in eval_result.generation_metrics.items():
            if v is not None:
                if k in retrieval_metric_names and not expect_retrieval:
                    continue
                metric_parts.append(f"{k}={v:.4f}")
        metric_str = ", ".join(metric_parts) if metric_parts else "no metrics"
        if not expect_retrieval:
            logger.success(
                f"Question {sample['question_id']} (RAGAS): {metric_str} (expect_retrieval=False, skipped LLM retrieval)"
            )
        else:
            logger.success(f"Question {sample['question_id']} (RAGAS): {metric_str}")

        results.append(result)

    return results


def evaluate_test_set(
    pipeline: RAGPipeline,
    test_set: dict[str, Any],
    exp_config: ExperimentConfig | None = None,
    system_config: dict[str, Any] | None = None,
    meal_info: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate a single test set against the pipeline.

    Uses MetricResolver to determine which metrics each backend should
    compute, based on the configured resolution strategy and metrics preset.

    Args:
        pipeline: Configured RAG pipeline.
        test_set: Test set dictionary with questions.
        exp_config: Experiment configuration for backend selection.
        system_config: System configuration for evaluator creation.
        meal_info: Optional meal information containing equivalence_groups.

    Returns:
        List of evaluation result dictionaries.

    Raises:
        ValueError: If exp_config or system_config is not provided.
    """
    if exp_config is None or system_config is None:
        raise ConfigurationError(
            "exp_config and system_config are required for evaluation. "
            "Please use run_experiment.py with a valid experiment configuration."
        )

    evaluators = _create_evaluators(exp_config, system_config)
    eval_config = exp_config.evaluation

    retrieval_metrics = eval_config.get("metrics", {}).get("retrieval")
    generation_metrics = eval_config.get("metrics", {}).get("generation")

    llm_preset = eval_config.get("llm_preset", "default")
    llm_config = get_llm_config(system_config, llm_preset)

    resolution_strategy = eval_config.get("resolution_strategy", "priority_fallback")
    backend_priority = eval_config.get("backend_priority", None)
    metrics_preset = eval_config.get("metrics_preset", None)
    custom_metrics = eval_config.get("custom_metrics", None)

    if metrics_preset and not retrieval_metrics and not generation_metrics:
        resolver = MetricResolver(
            evaluators=evaluators,
            strategy=resolution_strategy,
            backend_priority=backend_priority,
            metrics_preset=metrics_preset,
            custom_metrics=custom_metrics,
        )
    else:
        resolver = _build_legacy_resolver(
            evaluators, retrieval_metrics, generation_metrics
        )

    unresolvable = resolver.validate()
    if unresolvable:
        logger.warning(
            f"The following metrics cannot be computed by any backend: {unresolvable}"
        )

    allocation = resolver.resolve()

    equivalence_groups = meal_info.get("equivalence_groups") if meal_info else None
    samples = _collect_rag_samples(
        pipeline, test_set, equivalence_groups=equivalence_groups
    )

    all_results: dict[str, dict[str, Any]] = {}
    use_namespace = resolver.strategy == "comparison"

    for backend_name, metrics in allocation.items():
        if backend_name not in evaluators:
            logger.warning(f"Backend '{backend_name}' not available, skipping")
            continue

        evaluator = evaluators[backend_name]
        ret_metrics = metrics.get("retrieval", [])
        gen_metrics = metrics.get("generation", [])

        if not ret_metrics and not gen_metrics:
            continue

        needs_llm = bool(
            gen_metrics
            or any(m in ("context_precision", "context_recall") for m in ret_metrics)
        )

        if backend_name == "builtin":
            results = _evaluate_with_builtin(
                samples=samples,
                evaluator=evaluator,
                llm_config=llm_config if needs_llm else None,
                retrieval_metrics=ret_metrics or None,
                generation_metrics=gen_metrics or None,
            )
        elif backend_name == "ragas":
            results = _evaluate_with_ragas(
                samples=samples,
                evaluator=evaluator,
                llm_config=llm_config,
                generation_metrics=gen_metrics or None,
                retrieval_metrics=ret_metrics or None,
            )
        else:
            logger.warning(f"Unknown backend '{backend_name}', skipping")
            continue

        for r in results:
            if use_namespace:
                r = _namespace_result(r, backend_name)
            qid = r["id"]
            if qid in all_results:
                _merge_result(all_results[qid], r)
            else:
                all_results[qid] = r

    return list(all_results.values())


def _build_legacy_resolver(
    evaluators: dict[str, BaseEvaluator],
    retrieval_metrics: list[str] | None,
    generation_metrics: list[str] | None,
) -> MetricResolver:
    """Build a MetricResolver from legacy per-metric config.

    When the user specifies individual metrics via evaluation.metrics.retrieval
    and evaluation.metrics.generation (old style), convert to a custom preset.
    Uses comparison strategy for multi-backend and priority_fallback for
    single-backend to match the original namespace behavior.

    Args:
        evaluators: Available evaluators.
        retrieval_metrics: Legacy retrieval metric list.
        generation_metrics: Legacy generation metric list.

    Returns:
        MetricResolver configured with a custom preset matching legacy behavior.
    """
    custom = {
        "retrieval": retrieval_metrics or [],
        "generation": generation_metrics or [],
    }
    strategy = "comparison" if len(evaluators) > 1 else "priority_fallback"
    return MetricResolver(
        evaluators=evaluators,
        strategy=strategy,
        backend_priority=list(evaluators.keys()),
        metrics_preset="custom",
        custom_metrics=custom,
    )


def _namespace_result(result: dict[str, Any], backend_name: str) -> dict[str, Any]:
    """Add backend name prefix to metric keys for comparison mode.

    Args:
        result: Single evaluation result dict.
        backend_name: Backend name to use as prefix.

    Returns:
        Result dict with prefixed metric keys.
    """
    if "generation" in result and result["generation"]:
        result["generation"] = {
            f"{backend_name}_{k}": v for k, v in result["generation"].items()
        }
    if "llm_retrieval" in result and result["llm_retrieval"]:
        result["llm_retrieval"] = {
            f"{backend_name}_{k}": v for k, v in result["llm_retrieval"].items()
        }
    return result


def _merge_result(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Merge source result into target, combining metric dicts.

    Args:
        target: Target result dict to merge into (modified in place).
        source: Source result dict to merge from.
    """
    for key in ("generation", "llm_retrieval"):
        if key in source and source[key]:
            if key not in target:
                target[key] = {}
            target[key].update(source[key])
    if "ragas_error" in source:
        target["ragas_error"] = source["ragas_error"]


def compute_aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute aggregate metrics from evaluation results.

    Supports both retrieval and generation metrics. Includes chunk-level,
    dedup, FPR, diversity, hallucination rate, and per-question-type breakdown.

    Args:
        results: List of evaluation result dictionaries.

    Returns:
        Dictionary containing average metrics including hit_rate, mrr, ndcg,
        chunk_level_metrics, dedup_metrics, diversity, hallucination_rate,
        and by_question_type breakdown.
    """
    from eval.metrics import calculate_hallucination_rate

    metrics: dict[str, Any] = {}

    valid_retrieval = [
        r for r in results if r.get("retrieval", {}).get("hit_rate") is not None
    ]
    if valid_retrieval:
        for metric_name in ["hit_rate", "mrr", "ndcg"]:
            values = [
                r["retrieval"][metric_name]
                for r in valid_retrieval
                if metric_name in r["retrieval"]
                and r["retrieval"][metric_name] is not None
            ]
            if values:
                metrics[f"avg_{metric_name}"] = sum(values) / len(values)
            else:
                metrics[f"avg_{metric_name}"] = 0.0
    else:
        metrics["avg_hit_rate"] = 0.0
        metrics["avg_mrr"] = 0.0
        metrics["avg_ndcg"] = 0.0

    metrics["retrieval_applicable_questions"] = len(valid_retrieval)
    metrics["total_questions"] = len(results)

    valid_generation = [r for r in results if "generation" in r and r["generation"]]
    if valid_generation:
        generation_metrics_set = set()
        for r in valid_generation:
            generation_metrics_set.update(r["generation"].keys())

        generation_aggregate = {}
        for metric_name in sorted(generation_metrics_set):
            values = [
                r["generation"][metric_name]
                for r in valid_generation
                if metric_name in r["generation"]
                and r["generation"][metric_name] is not None
            ]
            if values:
                generation_aggregate[f"avg_{metric_name}"] = sum(values) / len(values)

        if generation_aggregate:
            metrics["generation_metrics"] = generation_aggregate

    chunk_results = [
        r
        for r in results
        if r.get("chunk_retrieval") is not None and r["chunk_retrieval"]
    ]
    if chunk_results:
        avg_chunk_hit_rate = sum(
            r["chunk_retrieval"].get("hit_rate", 0) for r in chunk_results
        ) / len(chunk_results)
        avg_chunk_mrr = sum(
            r["chunk_retrieval"].get("mrr", 0) for r in chunk_results
        ) / len(chunk_results)
        avg_chunk_ndcg = sum(
            r["chunk_retrieval"].get("ndcg", 0) for r in chunk_results
        ) / len(chunk_results)
    else:
        avg_chunk_hit_rate = None
        avg_chunk_mrr = None
        avg_chunk_ndcg = None

    dedup_results = [
        r
        for r in results
        if r.get("dedup_retrieval") is not None and r["dedup_retrieval"]
    ]
    if dedup_results:
        avg_dedup_hit_rate = sum(
            r["dedup_retrieval"].get("hit_rate", 0) for r in dedup_results
        ) / len(dedup_results)
        avg_dedup_mrr = sum(
            r["dedup_retrieval"].get("mrr", 0) for r in dedup_results
        ) / len(dedup_results)
        avg_dedup_ndcg = sum(
            r["dedup_retrieval"].get("ndcg", 0) for r in dedup_results
        ) / len(dedup_results)
    else:
        avg_dedup_hit_rate = None
        avg_dedup_mrr = None
        avg_dedup_ndcg = None

    fpr_results = [r for r in results if r.get("false_positive_rate") is not None]
    avg_false_positive_rate = (
        sum(r["false_positive_rate"] for r in fpr_results) / len(fpr_results)
        if fpr_results
        else None
    )

    metrics["chunk_level_metrics"] = {
        "avg_hit_rate": avg_chunk_hit_rate,
        "avg_mrr": avg_chunk_mrr,
        "avg_ndcg": avg_chunk_ndcg,
        "retrieval_applicable_questions": len(chunk_results),
    }
    metrics["dedup_metrics"] = {
        "avg_hit_rate": avg_dedup_hit_rate,
        "avg_mrr": avg_dedup_mrr,
        "avg_ndcg": avg_dedup_ndcg,
    }
    metrics["avg_false_positive_rate"] = avg_false_positive_rate
    metrics["irrelevant_questions_count"] = len(fpr_results)

    diversity_values = [
        r["retrieval"]["retrieval_diversity"]
        for r in valid_retrieval
        if "retrieval_diversity" in r.get("retrieval", {})
        and r["retrieval"]["retrieval_diversity"] is not None
    ]
    metrics["avg_retrieval_diversity"] = (
        sum(diversity_values) / len(diversity_values) if diversity_values else None
    )

    faithfulness_values = [
        r["generation"]["faithfulness"]
        for r in valid_generation
        if "faithfulness" in r.get("generation", {})
        and r["generation"]["faithfulness"] is not None
    ]
    metrics["hallucination_rate"] = (
        calculate_hallucination_rate(faithfulness_values)
        if faithfulness_values
        else None
    )

    type_groups: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        qtype = r.get("question_type", "unknown")
        if qtype not in type_groups:
            type_groups[qtype] = []
        type_groups[qtype].append(r)

    type_metrics: dict[str, dict[str, Any]] = {}
    for qtype, group in type_groups.items():
        type_entry: dict[str, Any] = {"count": len(group)}

        type_valid_retrieval = [
            r for r in group if r.get("retrieval", {}).get("hit_rate") is not None
        ]
        for mn in ["hit_rate", "mrr", "ndcg", "retrieval_diversity"]:
            vals = [
                r["retrieval"][mn]
                for r in type_valid_retrieval
                if mn in r["retrieval"] and r["retrieval"][mn] is not None
            ]
            if vals:
                type_entry[f"avg_{mn}"] = sum(vals) / len(vals)

        type_valid_gen = [r for r in group if "generation" in r and r["generation"]]
        for mn in ["faithfulness", "answer_relevancy"]:
            vals = []
            for r in type_valid_gen:
                gen = r["generation"]
                value = None
                for prefix in ["builtin_", "ragas_", ""]:
                    key = f"{prefix}{mn}" if prefix else mn
                    if key in gen and gen[key] is not None:
                        value = gen[key]
                        break
                if value is not None:
                    vals.append(value)
            if vals:
                type_entry[f"avg_{mn}"] = sum(vals) / len(vals)

        type_metrics[qtype] = type_entry

    if type_metrics:
        metrics["by_question_type"] = type_metrics

    llm_retrieval_results = [
        r for r in results if "llm_retrieval" in r and r["llm_retrieval"]
    ]
    llm_retrieval_from_generation = []
    for r in results:
        if "generation" in r and r["generation"]:
            gen = r["generation"]
            llm_keys = {
                k: v
                for k, v in gen.items()
                if k in {"context_precision", "context_recall"} and v is not None
            }
            if llm_keys:
                llm_retrieval_from_generation.append(llm_keys)

    all_llm_retrieval = []
    for r in llm_retrieval_results:
        all_llm_retrieval.append(r["llm_retrieval"])
    all_llm_retrieval.extend(llm_retrieval_from_generation)

    if all_llm_retrieval:
        cp_values = [
            lr["context_precision"]
            for lr in all_llm_retrieval
            if "context_precision" in lr and lr["context_precision"] is not None
        ]
        if cp_values:
            metrics["avg_context_precision"] = sum(cp_values) / len(cp_values)

        cr_values = [
            lr["context_recall"]
            for lr in all_llm_retrieval
            if "context_recall" in lr and lr["context_recall"] is not None
        ]
        if cr_values:
            metrics["avg_context_recall"] = sum(cr_values) / len(cr_values)

    return metrics


def run_variant_evaluation(
    system_config: dict[str, Any],
    exp_config: ExperimentConfig,
    variant: dict[str, Any],
    meal_info: dict[str, Any],
    test_sets: list[dict[str, Any]],
    exp_dir: Path,
    test_generation_tracker: TokenTracker | None = None,
    profiler: PipelineProfiler | None = None,
    force_index: bool = False,
) -> dict[str, Any]:
    """
    Run evaluation for a single variant.

    Args:
        system_config: System configuration dictionary.
        exp_config: Experiment configuration.
        variant: Variant configuration dictionary.
        meal_info: Meal information dictionary.
        test_sets: List of test set dictionaries.
        exp_dir: Experiment directory path.
        test_generation_tracker: TokenTracker from test set generation phase.
        profiler: Optional PipelineProfiler for performance tracking.
        force_index: If True, delete existing index and rebuild from scratch.

    Returns:
        Evaluation result dictionary.

    Raises:
        Exception: If evaluation fails.
    """
    variant_name = variant.get("name", "unnamed")
    logger.info(f"Running evaluation for variant: {variant_name}")

    merged_config = merge_config(system_config, exp_config, variant)

    meal_name = meal_info["name"]
    meal_config = meal_info["config"]

    config_snapshot = {
        "data": exp_config.data,
        "test_sets": exp_config.test_sets,
        "evaluation": exp_config.evaluation,
        "variant": variant,
        "merged": sanitize_config(merged_config),
    }

    llm_preset = exp_config.evaluation.get("llm_preset", "default")

    try:
        variant_tracker = TokenTracker()

        pipeline = RAGPipeline(
            config_path=None,
            llm_preset=llm_preset,
            meal_name=meal_name,
            token_tracker=variant_tracker,
            profiler=profiler,
        )
        pipeline.config = merged_config

        if hasattr(pipeline, "indexer") and pipeline.indexer is not None:
            pipeline.indexer.close()

        if profiler:
            profiler.begin_stage("S3")
        indexer = prepare_index_for_variant(
            merged_config, meal_config, variant_name, force_index=force_index
        )
        pipeline.indexer = indexer
        if profiler:
            profiler.end_stage()

        pipeline._setup_retrievers()

        llm_config_merged = get_llm_config(merged_config, llm_preset)
        pipeline.generator = Generator(
            model_name=llm_config_merged["model_name"],
            api_key=llm_config_merged["api_key"],
            base_url=llm_config_merged["base_url"],
            temperature=llm_config_merged["temperature"],
            max_tokens=llm_config_merged["max_tokens"],
            token_tracker=variant_tracker,
            system_prompt=merged_config.get("generation", {}).get("system_prompt"),
        )

        retrieval_method = merged_config.get("retrieval", {}).get("method", "vector")
        if (
            retrieval_method in ("bm25", "hybrid")
            and pipeline.bm25_retriever is not None
        ):
            if profiler:
                profiler.begin_stage("S4")
            from src.meal import ArtifactCache

            artifacts_config = merged_config.get("artifacts", {})
            artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
            raw_dir = Path(merged_config.get("parser", {}).get("input_dir", "data/raw"))
            cache = ArtifactCache(artifacts_dir, raw_dir)
            chunker_hash = meal_config.config_hashes.get("chunker", "")
            chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)
            if chunks_dir.exists():
                pipeline.bm25_retriever.build_index_from_chunks(str(chunks_dir))
            else:
                logger.warning(f"Chunks dir not found for BM25: {chunks_dir}")
            if profiler:
                profiler.end_stage()

            if retrieval_method == "hybrid" and pipeline.hybrid_retriever is not None:
                pipeline.hybrid_retriever = HybridRetriever(
                    vector_retriever=pipeline.retriever,
                    bm25_retriever=pipeline.bm25_retriever,
                    fusion_method=merged_config.get("retrieval", {})
                    .get("hybrid", {})
                    .get("fusion", "rrf"),
                    rrf_k=merged_config.get("retrieval", {})
                    .get("hybrid", {})
                    .get("rrf_k", 60),
                    vector_weight=merged_config.get("retrieval", {})
                    .get("hybrid", {})
                    .get("vector_weight", 0.7),
                    bm25_weight=merged_config.get("retrieval", {})
                    .get("hybrid", {})
                    .get("bm25_weight", 0.3),
                    top_k=merged_config.get("retrieval", {}).get("top_k", 5),
                )

        total_start_time = time.time()
        all_results = []

        llm_config = get_llm_config(merged_config, llm_preset)

        for test_set in test_sets:
            results = evaluate_test_set(
                pipeline,
                test_set,
                exp_config=exp_config,
                system_config=system_config,
                meal_info=meal_info,
            )
            all_results.extend(results)

        total_time = time.time() - total_start_time

        metrics = compute_aggregate_metrics(all_results)

        if profiler:
            s6_metrics = profiler.get_stage_metrics("S6")
            s7_metrics = profiler.get_stage_metrics("S7")
            rag_total = variant_tracker.get_total()
            if s7_metrics:
                gen_records = [
                    r for r in variant_tracker._records if r.category == "rag_qa"
                ]
                gen_input = sum(r.usage.input_tokens for r in gen_records)
                gen_output = sum(r.usage.output_tokens for r in gen_records)
                profiler.report_stage_tokens("S7", gen_input, gen_output)
                retr_input = rag_total.input_tokens - gen_input
                retr_output = rag_total.output_tokens - gen_output
                profiler.report_stage_tokens("S6", retr_input, retr_output)

        token_usage_data = variant_tracker.to_dict()
        if (
            test_generation_tracker is not None
            and test_generation_tracker.record_count > 0
        ):
            token_usage_data["test_generation"] = test_generation_tracker.to_dict()

        variant_result = {
            "variant_name": variant_name,
            "variant_description": variant.get("description", ""),
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(all_results),
            "total_time_seconds": total_time,
            "avg_time_per_question": total_time / len(all_results)
            if all_results
            else 0,
            "retrieval_metrics": {
                k: v for k, v in metrics.items() if k != "generation_metrics"
            },
            "config_snapshot": config_snapshot,
            "results": all_results,
            "token_usage": token_usage_data,
        }

        if "generation_metrics" in metrics:
            variant_result["generation_metrics"] = metrics["generation_metrics"]

        log_parts = [
            f"HR={metrics.get('avg_hit_rate', 0):.4f}",
            f"MRR={metrics.get('avg_mrr', 0):.4f}",
            f"NDCG={metrics.get('avg_ndcg', 0):.4f}",
        ]
        if "generation_metrics" in metrics:
            for gk, gv in metrics["generation_metrics"].items():
                log_parts.append(f"{gk}={gv:.4f}")

        if "avg_context_precision" in metrics:
            log_parts.append(f"CP={metrics['avg_context_precision']:.4f}")
        if "avg_context_recall" in metrics:
            log_parts.append(f"CR={metrics['avg_context_recall']:.4f}")

        logger.success(
            f"Variant '{variant_name}' evaluation completed: " + ", ".join(log_parts)
        )

        token_total = variant_tracker.get_total()
        logger.info(
            f"Token usage for variant '{variant_name}': "
            f"in={token_total.input_tokens:,}, out={token_total.output_tokens:,}, "
            f"total={token_total.total_tokens:,}"
        )

        pipeline.close()

        return variant_result

    except Exception as e:
        logger.error(f"Failed to evaluate variant '{variant_name}': {str(e)}")
        if "pipeline" in locals():
            with contextlib.suppress(Exception):
                pipeline.close()
        raise


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


def run_experiment(
    config_path: str,
    skip_preprocessing: bool = False,
    use_llm_report: bool = False,
    system_config_path: str = "config.yaml",
) -> dict[str, Any]:
    """
    Execute complete experiment workflow.

    Args:
        config_path: Path to experiment configuration YAML file.
        skip_preprocessing: If True, skip meal and test set creation if missing.
        use_llm_report: If True, use LLM to generate experiment report.
        system_config_path: Path to system configuration file.

    Returns:
        Dictionary containing complete experiment results.

    Raises:
        FileNotFoundError: If configuration files don't exist.
        ValueError: If configuration is invalid.
        Exception: If experiment execution fails.
    """
    logger.info(f"Loading experiment configuration from {config_path}")
    exp_config = load_experiment_config(config_path)

    logger.info(f"Experiment: {exp_config.name}")
    logger.info(f"Description: {exp_config.description}")
    logger.info(f"Variants: {len(exp_config.variants)}")
    logger.info(f"Test sets: {len(exp_config.test_sets)}")

    system_config = load_config(system_config_path)
    setup_logger(system_config)

    exp_manager = ExperimentManager(system_config)
    exp_dir = exp_manager.create_experiment_dir(exp_config)

    experiment_log_path = exp_dir / "experiment.log"
    logger.add(
        str(experiment_log_path),
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {message}",
        level="INFO",
        encoding="utf-8",
    )

    logger.info(f"Experiment directory: {exp_dir}")

    profiling_config = system_config.get("experiments", {}).get("profiling", {})
    profiling_enabled = profiling_config.get("enabled", True)

    if profiling_enabled:
        profiler = PipelineProfiler(
            experiment_name=exp_config.name,
            total_pages=0,
            total_questions=sum(
                ts.get("generation", {}).get(
                    "num_questions", ts.get("num_questions", 10)
                )
                for ts in exp_config.test_sets
            ),
            monitor_interval=profiling_config.get("monitor_interval", 0.5),
        )
        profiler.start_profiling()
        logger.info("Performance profiling enabled")
    else:
        profiler = None
        logger.info("Performance profiling disabled by config")

    try:
        force_meal = exp_config.should_force("meal")
        force_parsed = exp_config.should_force("parsed")
        force_chunk = exp_config.should_force("chunk")
        force_vector = exp_config.should_force("vector")
        force_testset = exp_config.should_force("testset")

        if exp_config.force_overwrite:
            stages = (
                "all"
                if exp_config.force_overwrite == "all"
                else ", ".join(exp_config.force_overwrite)
            )
            logger.info(f"Force overwrite enabled for: {stages}")

        logger.info("Step 1: Preparing meal...")
        with profiler.profile_stage("S1", {"meal_name": exp_config.data.get("meal")}):
            meal_info = prepare_meal(
                system_config,
                exp_config,
                skip_preprocessing,
                force_meal=force_meal,
                force_parse=force_parsed,
                force_chunk=force_chunk,
            )

        test_generation_tracker = TokenTracker()

        logger.info("Step 2: Preparing variant chunks...")
        first_chunks_dir = None
        with profiler.profile_stage("S2"):
            for i, variant in enumerate(exp_config.variants, 1):
                variant_name = variant.get("name", f"variant_{i}")
                merged_config = merge_config(system_config, exp_config, variant)
                chunks_dir = prepare_variant_chunks(
                    merged_config,
                    meal_info["config"],
                    variant_name,
                    force_chunk=force_chunk,
                )
                if first_chunks_dir is None:
                    first_chunks_dir = chunks_dir

        logger.info("Step 3: Preparing test sets...")
        with profiler.profile_stage("S5"):
            test_sets = prepare_test_sets(
                system_config,
                exp_config,
                meal_info,
                skip_preprocessing,
                token_tracker=test_generation_tracker,
                chunks_dir=first_chunks_dir,
                force_testset=force_testset,
            )

        if profiler:
            test_gen_total = test_generation_tracker.get_total()
            profiler.report_stage_tokens(
                "S5",
                test_gen_total.input_tokens,
                test_gen_total.output_tokens,
            )

        meal_snapshot = meal_info["config"].to_dict()

        test_set_snapshots = []
        for test_set in test_sets:
            metadata = test_set.get("metadata", {})
            generation = metadata.get("generation", {})
            test_set_snapshots.append(
                {
                    "name": test_set.get("name") or metadata.get("name"),
                    "strategy": test_set.get("strategy") or generation.get("strategy"),
                    "num_questions": len(test_set.get("questions", [])),
                    "created_at": test_set.get("created_at")
                    or metadata.get("created_at"),
                    "meal_data_id": test_set.get("meal_data_id")
                    or metadata.get("meal_id"),
                    "questions": test_set.get("questions", []),
                }
            )

        config_snapshot = {
            "data": exp_config.data,
            "test_sets": exp_config.test_sets,
            "evaluation": exp_config.evaluation,
            "llm": exp_config.llm,
            "system_config": sanitize_config(system_config),
            "environment": collect_environment_info(),
        }

        exp_manager.save_snapshots(
            exp_dir=exp_dir,
            config=exp_config,
            meal_snapshot=meal_snapshot,
            test_set_snapshots=test_set_snapshots,
            config_snapshot=config_snapshot,
        )

        logger.info("Step 4: Running variant evaluations...")
        all_variant_results = []
        experiment_tracker = TokenTracker()

        for i, variant in enumerate(exp_config.variants, 1):
            variant_name = variant.get("name", f"variant_{i}")
            logger.info(
                f"Evaluating variant {i}/{len(exp_config.variants)}: {variant_name}"
            )

            try:
                variant_result = run_variant_evaluation(
                    system_config=system_config,
                    exp_config=exp_config,
                    variant=variant,
                    meal_info=meal_info,
                    test_sets=test_sets,
                    exp_dir=exp_dir,
                    test_generation_tracker=test_generation_tracker,
                    profiler=profiler,
                    force_index=force_vector,
                )

                exp_manager.save_variant_result(exp_dir, variant_name, variant_result)
                all_variant_results.append(variant_result)

                if "token_usage" in variant_result:
                    variant_tracker = TokenTracker()
                    for rec_data in variant_result["token_usage"].get("records", []):
                        from src.token_tracker import DetailedTokenUsage

                        usage = DetailedTokenUsage(
                            input_tokens=rec_data["usage"]["input_tokens"],
                            output_tokens=rec_data["usage"]["output_tokens"],
                            system_prompt_tokens=rec_data["usage"].get(
                                "system_prompt_tokens", 0
                            ),
                            contexts_tokens=rec_data["usage"].get("contexts_tokens", 0),
                            query_tokens=rec_data["usage"].get("query_tokens", 0),
                        )
                        variant_tracker.record(
                            category=rec_data["category"],
                            model_name=rec_data["model_name"],
                            usage=usage,
                            variant_name=variant_name,
                        )
                    experiment_tracker.merge(variant_tracker)

            except Exception as e:
                logger.error(f"Variant '{variant_name}' failed: {str(e)}")
                error_result = {
                    "variant_name": variant_name,
                    "error": str(e),
                    "timestamp": datetime.now().isoformat(),
                }
                exp_manager.save_variant_result(exp_dir, variant_name, error_result)
                all_variant_results.append(error_result)

        experiment_tracker.merge(test_generation_tracker)

        logger.info("Step 4: Generating experiment report...")

        with profiler.profile_stage("S8"):
            if all_variant_results:
                llm_preset_name = exp_config.evaluation.get("llm_preset", "default")
                llm_config = get_llm_config(system_config, llm_preset_name)

                reporter = ExperimentReporter(
                    llm_api_key=llm_config.get("api_key"),
                    llm_base_url=llm_config.get("base_url"),
                    llm_model_name=llm_config.get("model_name"),
                    token_tracker=experiment_tracker,
                )

                reporter.generate_variant_comparison_report(
                    exp_dir=exp_dir,
                    variant_results=all_variant_results,
                    meal_info=meal_info,
                    config_snapshot=config_snapshot,
                    output_filename="experiment_report.md",
                    use_llm=False,
                )

                if use_llm_report or exp_config.evaluation.get("llm_report", False):
                    has_successful = any(
                        "retrieval_metrics" in v for v in all_variant_results
                    )
                    if not has_successful:
                        logger.warning(
                            "All variants failed — skipping LLM report generation"
                        )
                    else:
                        logger.info("Generating LLM-enhanced report...")
                        try:
                            reporter.generate_variant_comparison_report(
                                exp_dir=exp_dir,
                                variant_results=all_variant_results,
                                meal_info=meal_info,
                                config_snapshot=config_snapshot,
                                output_filename="experiment_report_llm.md",
                                use_llm=True,
                            )
                            logger.success("LLM-enhanced report generated successfully")
                        except Exception as e:
                            logger.warning(f"Failed to generate LLM report: {str(e)}")

        exp_manager.update_manifest_status(exp_dir, "completed")

        if profiler:
            profiler.stop_profiling()
            if meal_info.get("config") and hasattr(meal_info["config"], "stats"):
                profiler.total_pages = meal_info["config"].stats.get("total_pages", 0)

            profiling_dir = exp_dir / "profiling"
            profiler.save_report(profiling_dir, "profile_data.json")

            profile_md = profiler.generate_markdown_report()
            profile_md_path = profiling_dir / "profile_report.md"
            profile_md_path.parent.mkdir(parents=True, exist_ok=True)
            with open(profile_md_path, "w", encoding="utf-8") as f:
                f.write(profile_md)
            logger.success(f"Performance profile report saved to: {profile_md_path}")

            if profiling_config.get("generate_charts", True):
                try:
                    chart_files = generate_profiler_charts(
                        profiler, profiling_dir / "charts"
                    )
                    if chart_files:
                        logger.success(
                            f"Generated {len(chart_files)} performance charts"
                        )
                except Exception as e:
                    logger.warning(f"Failed to generate performance charts: {str(e)}")

        experiment_tracker.get_total()
        token_cost_config = system_config.get("token_cost", {})
        cost_info = experiment_tracker.estimate_cost(token_cost_config)

        try:
            token_summary_data = experiment_tracker.to_dict()
            token_summary_data["estimated_cost"] = cost_info
            token_summary_path = exp_dir / "token_summary.json"
            with open(token_summary_path, "w", encoding="utf-8") as f:
                json.dump(token_summary_data, f, ensure_ascii=False, indent=2)
            logger.info(f"Token summary saved to {token_summary_path}")

            token_table = experiment_tracker.get_detailed_table()
            if cost_info["total_cost"] > 0:
                token_table += f"\n\nEstimated Cost (model: {cost_info['model']}):\n"
                token_table += f"  Input:  ${cost_info['input_cost']:.4f}\n"
                token_table += f"  Output: ${cost_info['output_cost']:.4f}\n"
                token_table += f"  Total:  ${cost_info['total_cost']:.4f}\n"
            token_table_path = exp_dir / "token_summary.txt"
            with open(token_table_path, "w", encoding="utf-8") as f:
                f.write(token_table)
            logger.info(f"Token summary table saved to {token_table_path}")
        except Exception as e:
            logger.warning(f"Failed to save token summary: {str(e)}")

        print("\n" + experiment_tracker.get_detailed_table())

        if cost_info["total_cost"] > 0:
            print(f"\nEstimated Cost (model: {cost_info['model']}):")
            print(f"  Input:  ${cost_info['input_cost']:.4f}")
            print(f"  Output: ${cost_info['output_cost']:.4f}")
            print(f"  Total:  ${cost_info['total_cost']:.4f}")

        logger.success(f"Experiment completed successfully: {exp_dir}")

        return {
            "experiment_id": exp_dir.name,
            "exp_dir": str(exp_dir),
            "config": exp_config.to_dict(),
            "meal_info": {
                "name": meal_info["name"],
                "data_id": meal_info["data_id"],
                "status": meal_info["status"].value,
            },
            "test_sets": test_set_snapshots,
            "variant_results": all_variant_results,
            "token_usage": experiment_tracker.to_dict(),
            "estimated_cost": cost_info,
        }

    except Exception as e:
        exp_manager.update_manifest_status(exp_dir, "failed")
        logger.error(f"Experiment failed: {str(e)}")
        raise


def list_experiments(system_config_path: str = "config.yaml") -> None:
    """
    List all experiments.

    Args:
        system_config_path: Path to system configuration file.
    """
    system_config = load_config(system_config_path)
    exp_manager = ExperimentManager(system_config)

    experiments = exp_manager.list_experiments()

    if not experiments:
        print("No experiments found.")
        return

    print("\n" + "=" * 80)
    print("EXPERIMENTS")
    print("=" * 80)

    for exp in experiments:
        print(f"\nID: {exp['experiment_id']}")
        print(f"Name: {exp['name']}")
        print(f"Created: {exp['created_at']}")
        print(f"Status: {exp['status']}")
        print(f"Path: {exp['path']}")

    print("\n" + "=" * 80)


def show_experiment_info(exp_id: str, system_config_path: str = "config.yaml") -> None:
    """
    Show detailed information about an experiment.

    Args:
        exp_id: Experiment ID or directory name.
        system_config_path: Path to system configuration file.
    """
    system_config = load_config(system_config_path)
    exp_manager = ExperimentManager(system_config)

    try:
        info = exp_manager.get_experiment_info(exp_id)

        print("\n" + "=" * 80)
        print(f"EXPERIMENT: {info['name']}")
        print("=" * 80)

        print(f"\nID: {info['experiment_id']}")
        print(f"Description: {info['description']}")
        print(f"Created: {info['created_at']}")
        print(f"Status: {info['status']}")

        if info.get("meal_snapshot"):
            print(f"\nMeal: {info['meal_snapshot'].get('name', 'N/A')}")
            print(f"Data ID: {info['meal_snapshot'].get('data_id', 'N/A')[:12]}...")

        if info.get("test_set_snapshots"):
            print(f"\nTest Sets ({len(info['test_set_snapshots'])}):")
            for ts in info["test_set_snapshots"]:
                print(
                    f"  - {ts.get('strategy', 'unknown')}: {ts.get('num_questions', 0)} questions"
                )

        if info.get("variant_results"):
            print(f"\nVariant Results ({len(info['variant_results'])}):")
            for vr in info["variant_results"]:
                name = vr.get("variant_name", "unknown")
                if "retrieval_metrics" in vr:
                    metrics = vr["retrieval_metrics"]
                    print(
                        f"  - {name}: HR={metrics.get('avg_hit_rate', 0):.4f}, "
                        f"MRR={metrics.get('avg_mrr', 0):.4f}, "
                        f"NDCG={metrics.get('avg_ndcg', 0):.4f}"
                    )
                else:
                    print(f"  - {name}: {vr.get('error', 'No metrics')}")

        print("\n" + "=" * 80)

    except FileNotFoundError:
        print(f"Experiment not found: {exp_id}")
        sys.exit(1)


def compare_experiments(
    exp_ids: list[str],
    system_config_path: str = "config.yaml",
    output_format: str = "table",
    save_report: bool = False,
    report_path: str | None = None,
) -> dict[str, Any]:
    """
    Compare multiple experiments and generate a comparison report.

    This function loads multiple experiments and compares their:
    - Retrieval metrics (Hit Rate, MRR, NDCG)
    - Configuration differences
    - Test set characteristics
    - Performance by question category (if available)

    Args:
        exp_ids: List of experiment IDs to compare.
        system_config_path: Path to system configuration file.
        output_format: Output format, either 'table' or 'json'.
        save_report: If True, save the comparison report to a file.
        report_path: Path to save the report. If not specified, saves to
                    data/exp_reports/comparison_{timestamp}.md

    Returns:
        Dictionary containing comparison results.
    """
    system_config = load_config(system_config_path)
    exp_manager = ExperimentManager(system_config)

    results = []
    not_found = []

    for exp_id in exp_ids:
        try:
            info = exp_manager.get_experiment_info(exp_id)
            results.append(info)
        except FileNotFoundError:
            not_found.append(exp_id)
            logger.warning(f"Experiment not found: {exp_id}")

    if not results:
        print("No valid experiments to compare.")
        return {"error": "No valid experiments", "not_found": not_found}

    comparison_data = _build_comparison_data(results)

    if output_format == "table":
        _print_comparison_table(comparison_data, not_found)
    else:
        print(json.dumps(comparison_data, indent=2, ensure_ascii=False))

    if save_report:
        report_content = _generate_comparison_report(comparison_data, not_found)
        if report_path:
            report_file = Path(report_path)
        else:
            exp_dir = Path(
                system_config.get("experiments", {}).get("dir", "data/exp_reports")
            )
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            report_file = exp_dir / f"comparison_{timestamp}.md"

        report_file.parent.mkdir(parents=True, exist_ok=True)
        with open(report_file, "w", encoding="utf-8") as f:
            f.write(report_content)
        logger.success(f"Comparison report saved to: {report_file}")

    return {
        "experiments_compared": len(results),
        "not_found": not_found,
        "comparison_data": comparison_data,
    }


def _build_comparison_data(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Build structured comparison data from experiment results.

    Args:
        results: List of experiment info dictionaries.

    Returns:
        Structured comparison data dictionary.
    """
    experiments = []

    for info in results:
        exp_data = {
            "experiment_id": info.get("experiment_id", "unknown"),
            "name": info.get("name", "unknown"),
            "description": info.get("description", ""),
            "created_at": info.get("created_at", ""),
            "status": info.get("status", "unknown"),
            "variants": [],
            "meal_info": {},
            "test_sets": [],
        }

        if info.get("meal_snapshot"):
            meal = info["meal_snapshot"]
            exp_data["meal_info"] = {
                "name": meal.get("name", "N/A"),
                "data_id": meal.get("data_id", "N/A")[:12]
                if meal.get("data_id")
                else "N/A",
                "pdf_count": meal.get("stats", {}).get("total_pdfs", 0),
                "page_count": meal.get("stats", {}).get("total_pages", 0),
                "chunk_count": meal.get("stats", {}).get("total_chunks", 0),
            }

        if info.get("test_set_snapshots"):
            for ts in info["test_set_snapshots"]:
                exp_data["test_sets"].append(
                    {
                        "strategy": ts.get("strategy", "unknown"),
                        "num_questions": ts.get("num_questions", 0),
                    }
                )

        if info.get("variant_results"):
            for vr in info["variant_results"]:
                variant_data = {
                    "name": vr.get("variant_name", "unknown"),
                    "description": vr.get("variant_description", ""),
                    "total_questions": vr.get("total_questions", 0),
                    "total_time_seconds": vr.get("total_time_seconds", 0),
                    "avg_time_per_question": vr.get("avg_time_per_question", 0),
                }

                if "retrieval_metrics" in vr:
                    metrics = vr["retrieval_metrics"]
                    variant_data["metrics"] = {
                        "hit_rate": metrics.get("avg_hit_rate", 0),
                        "mrr": metrics.get("avg_mrr", 0),
                        "ndcg": metrics.get("avg_ndcg", 0),
                    }
                else:
                    variant_data["metrics"] = {
                        "hit_rate": 0,
                        "mrr": 0,
                        "ndcg": 0,
                    }
                    variant_data["error"] = vr.get("error", "No metrics available")

                if "config_snapshot" in vr:
                    config = vr["config_snapshot"]
                    if "merged" in config:
                        merged = config["merged"]
                        variant_data["config"] = {
                            "chunk_size": merged.get("chunker", {}).get(
                                "chunk_size", "N/A"
                            ),
                            "chunk_overlap": merged.get("chunker", {}).get(
                                "chunk_overlap", "N/A"
                            ),
                            "embedding_model": merged.get("embedding", {}).get(
                                "model_name", "N/A"
                            ),
                            "top_k": merged.get("retrieval", {}).get("top_k", "N/A"),
                        }

                category_metrics = _extract_category_metrics(vr)
                if category_metrics:
                    variant_data["category_metrics"] = category_metrics

                exp_data["variants"].append(variant_data)

        experiments.append(exp_data)

    best_variants = []
    for exp in experiments:
        best_variant = None
        best_hr = 0
        for v in exp["variants"]:
            if v["metrics"]["hit_rate"] > best_hr:
                best_hr = v["metrics"]["hit_rate"]
                best_variant = v
        if best_variant:
            best_variants.append(
                {
                    "experiment_name": exp["name"],
                    "variant_name": best_variant["name"],
                    "metrics": best_variant["metrics"],
                }
            )

    if best_variants:
        best_variants.sort(key=lambda x: x["metrics"]["hit_rate"], reverse=True)

    return {
        "experiments": experiments,
        "best_variants": best_variants,
        "summary": {
            "total_experiments": len(experiments),
            "total_variants": sum(len(e["variants"]) for e in experiments),
        },
    }


def _extract_category_metrics(
    variant_result: dict[str, Any],
) -> dict[str, dict[str, float]]:
    """
    Extract metrics grouped by question category from variant results.

    Args:
        variant_result: Variant result dictionary.

    Returns:
        Dictionary mapping category names to their metrics.
    """
    category_metrics: dict[str, dict[str, list[float]]] = {}

    for result in variant_result.get("results", []):
        category = result.get("category", "unknown")
        if category not in category_metrics:
            category_metrics[category] = {
                "hit_rates": [],
                "mrrs": [],
                "ndcgs": [],
            }

        if "retrieval" in result:
            category_metrics[category]["hit_rates"].append(
                result["retrieval"].get("hit_rate", 0)
            )
            category_metrics[category]["mrrs"].append(result["retrieval"].get("mrr", 0))
            category_metrics[category]["ndcgs"].append(
                result["retrieval"].get("ndcg", 0)
            )

    averaged_metrics = {}
    for category, values in category_metrics.items():
        if values["hit_rates"]:
            averaged_metrics[category] = {
                "hit_rate": sum(values["hit_rates"]) / len(values["hit_rates"]),
                "mrr": sum(values["mrrs"]) / len(values["mrrs"]),
                "ndcg": sum(values["ndcgs"]) / len(values["ndcgs"]),
                "count": len(values["hit_rates"]),
            }

    return averaged_metrics


def _print_comparison_table(
    comparison_data: dict[str, Any],
    not_found: list[str],
) -> None:
    """
    Print comparison results in table format.

    Args:
        comparison_data: Structured comparison data.
        not_found: List of experiment IDs that were not found.
    """
    print("\n" + "=" * 120)
    print("EXPERIMENT COMPARISON REPORT")
    print("=" * 120)

    if not_found:
        print(
            f"\nWarning: The following experiments were not found: {', '.join(not_found)}"
        )

    print("\n" + "-" * 120)
    print("SUMMARY: BEST VARIANT PER EXPERIMENT")
    print("-" * 120)
    print(
        f"{'Experiment':<35} {'Variant':<25} {'Hit Rate':>10} {'MRR':>10} {'NDCG':>10}"
    )
    print("-" * 120)

    for bv in comparison_data["best_variants"]:
        print(
            f"{bv['experiment_name'][:33]:<35} {bv['variant_name'][:23]:<25} "
            f"{bv['metrics']['hit_rate']:>10.4f} {bv['metrics']['mrr']:>10.4f} "
            f"{bv['metrics']['ndcg']:>10.4f}"
        )

    print("-" * 120)

    print("\n" + "-" * 120)
    print("DETAILED RESULTS: ALL VARIANTS")
    print("-" * 120)

    for exp in comparison_data["experiments"]:
        print(f"\nExperiment: {exp['name']} ({exp['experiment_id']})")
        print(f"Status: {exp['status']} | Created: {exp['created_at']}")

        if exp["meal_info"]:
            print(
                f"Meal: {exp['meal_info']['name']} ({exp['meal_info']['pdf_count']} PDFs, "
                f"{exp['meal_info']['page_count']} pages)"
            )

        if exp["test_sets"]:
            test_set_str = ", ".join(
                f"{ts['strategy']}({ts['num_questions']})" for ts in exp["test_sets"]
            )
            print(f"Test Sets: {test_set_str}")

        print(
            f"\n{'Variant':<30} {'Hit Rate':>10} {'MRR':>10} {'NDCG':>10} {'Time':>10}"
        )
        print("-" * 80)

        for v in exp["variants"]:
            time_str = (
                f"{v['avg_time_per_question']:.2f}s"
                if v.get("avg_time_per_question")
                else "N/A"
            )
            print(
                f"{v['name'][:28]:<30} {v['metrics']['hit_rate']:>10.4f} "
                f"{v['metrics']['mrr']:>10.4f} {v['metrics']['ndcg']:>10.4f} {time_str:>10}"
            )

            if "error" in v:
                print(f"  Error: {v['error']}")

            if "category_metrics" in v:
                print("  By Category:")
                for cat, metrics in v["category_metrics"].items():
                    print(
                        f"    {cat}: HR={metrics['hit_rate']:.4f}, "
                        f"MRR={metrics['mrr']:.4f}, NDCG={metrics['ndcg']:.4f} ({metrics['count']} questions)"
                    )

    print("\n" + "=" * 120 + "\n")


def _generate_comparison_report(
    comparison_data: dict[str, Any],
    not_found: list[str],
) -> str:
    """
    Generate a Markdown comparison report.

    Args:
        comparison_data: Structured comparison data.
        not_found: List of experiment IDs that were not found.

    Returns:
        Markdown formatted report string.
    """
    lines = []
    lines.append("# Experiment Comparison Report")
    lines.append("")
    lines.append(f"**Generated**: {datetime.now().isoformat()}")
    lines.append(
        f"**Experiments Compared**: {comparison_data['summary']['total_experiments']}"
    )
    lines.append(f"**Total Variants**: {comparison_data['summary']['total_variants']}")
    lines.append("")

    if not_found:
        lines.append("## Warnings")
        lines.append("")
        lines.append(
            f"The following experiments were not found: {', '.join(not_found)}"
        )
        lines.append("")

    lines.append("## Summary: Best Variants")
    lines.append("")
    lines.append("| Experiment | Variant | Hit Rate | MRR | NDCG |")
    lines.append("|------------|---------|----------|-----|------|")

    for bv in comparison_data["best_variants"]:
        lines.append(
            f"| {bv['experiment_name']} | {bv['variant_name']} | "
            f"{bv['metrics']['hit_rate']:.4f} | {bv['metrics']['mrr']:.4f} | "
            f"{bv['metrics']['ndcg']:.4f} |"
        )

    lines.append("")

    for exp in comparison_data["experiments"]:
        lines.append(f"## Experiment: {exp['name']}")
        lines.append("")
        lines.append(f"- **ID**: {exp['experiment_id']}")
        lines.append(f"- **Status**: {exp['status']}")
        lines.append(f"- **Created**: {exp['created_at']}")
        lines.append("")

        if exp["meal_info"]:
            lines.append("### Data Source")
            lines.append("")
            lines.append(f"- **Meal**: {exp['meal_info']['name']}")
            lines.append(f"- **PDFs**: {exp['meal_info']['pdf_count']}")
            lines.append(f"- **Pages**: {exp['meal_info']['page_count']}")
            lines.append(f"- **Chunks**: {exp['meal_info']['chunk_count']}")
            lines.append("")

        if exp["test_sets"]:
            lines.append("### Test Sets")
            lines.append("")
            for ts in exp["test_sets"]:
                lines.append(f"- {ts['strategy']}: {ts['num_questions']} questions")
            lines.append("")

        lines.append("### Variant Results")
        lines.append("")
        lines.append("| Variant | Hit Rate | MRR | NDCG | Avg Time |")
        lines.append("|---------|----------|-----|------|----------|")

        for v in exp["variants"]:
            time_str = (
                f"{v['avg_time_per_question']:.2f}s"
                if v.get("avg_time_per_question")
                else "N/A"
            )
            lines.append(
                f"| {v['name']} | {v['metrics']['hit_rate']:.4f} | "
                f"{v['metrics']['mrr']:.4f} | {v['metrics']['ndcg']:.4f} | {time_str} |"
            )

        lines.append("")

        for v in exp["variants"]:
            if "category_metrics" in v:
                lines.append(f"#### {v['name']} - By Category")
                lines.append("")
                lines.append("| Category | Hit Rate | MRR | NDCG | Count |")
                lines.append("|----------|----------|-----|------|-------|")
                for cat, metrics in v["category_metrics"].items():
                    lines.append(
                        f"| {cat} | {metrics['hit_rate']:.4f} | "
                        f"{metrics['mrr']:.4f} | {metrics['ndcg']:.4f} | {metrics['count']} |"
                    )
                lines.append("")

    return "\n".join(lines)


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

    import tempfile

    import yaml

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


def main():
    parser = argparse.ArgumentParser(
        description="RAG Experiment Runner",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run experiment
  pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml

  # Run with LLM-generated report
  pixi run python eval/run_experiment.py --config exp_configs/baseline.yaml --llm-report

  # List all experiments
  pixi run python eval/run_experiment.py --list

  # Show experiment details
  pixi run python eval/run_experiment.py --info exp_20250416_120000_baseline

  # Compare experiments
  pixi run python eval/run_experiment.py --compare exp_001 exp_002 exp_003

  # Compare experiments and save report
  pixi run python eval/run_experiment.py --compare exp_001 exp_002 --save-report

  # Reproduce experiment
  pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000_baseline

  # Reproduce experiment without hash verification
  pixi run python eval/run_experiment.py --reproduce data/exp_reports/exp_20250416_120000_baseline --skip-verification
        """,
    )

    parser.add_argument(
        "--config",
        type=str,
        help="Path to experiment configuration YAML file",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="List all experiments",
    )
    parser.add_argument(
        "--info",
        type=str,
        metavar="EXP_ID",
        help="Show detailed information about an experiment",
    )
    parser.add_argument(
        "--compare",
        nargs="+",
        metavar="EXP_ID",
        help="Compare multiple experiments",
    )
    parser.add_argument(
        "--reproduce",
        type=str,
        metavar="EXP_DIR",
        help="Reproduce an experiment from its saved configuration",
    )
    parser.add_argument(
        "--skip-preprocessing",
        action="store_true",
        help="Skip meal and test set creation if missing",
    )
    parser.add_argument(
        "--llm-report",
        action="store_true",
        help="Use LLM to generate experiment report",
    )
    parser.add_argument(
        "--system-config",
        type=str,
        default="config.yaml",
        help="Path to system configuration file (default: config.yaml)",
    )
    parser.add_argument(
        "--skip-verification",
        action="store_true",
        help="Skip asset verification when reproducing experiment",
    )
    parser.add_argument(
        "--skip-hash-verification",
        action="store_true",
        help="Skip PDF SHA256 hash verification (faster but less secure)",
    )
    parser.add_argument(
        "--output-format",
        type=str,
        choices=["table", "json"],
        default="table",
        help="Output format for comparison (default: table)",
    )
    parser.add_argument(
        "--save-report",
        action="store_true",
        help="Save comparison report to a Markdown file",
    )
    parser.add_argument(
        "--report-path",
        type=str,
        metavar="PATH",
        help="Path to save the comparison report (implies --save-report)",
    )

    args = parser.parse_args()

    if args.list:
        list_experiments(args.system_config)
    elif args.info:
        show_experiment_info(args.info, args.system_config)
    elif args.compare:
        save_report = args.save_report or args.report_path is not None
        compare_experiments(
            exp_ids=args.compare,
            system_config_path=args.system_config,
            output_format=args.output_format,
            save_report=save_report,
            report_path=args.report_path,
        )
    elif args.reproduce:
        try:
            result = reproduce_experiment(
                exp_dir=args.reproduce,
                system_config_path=args.system_config,
                skip_verification=args.skip_verification,
                verify_pdf_hashes=not args.skip_hash_verification,
            )
            print("\nExperiment reproduced successfully!")
            print(f"Original: {result['original_exp_dir']}")
            print(f"Reproduced: {result['reproduced_exp_dir']}")
        except ValueError as e:
            print(f"\nError: {str(e)}")
            sys.exit(1)
        except FileNotFoundError as e:
            print(f"\nError: {str(e)}")
            sys.exit(1)
    elif args.config:
        result = run_experiment(
            config_path=args.config,
            skip_preprocessing=args.skip_preprocessing,
            use_llm_report=args.llm_report,
            system_config_path=args.system_config,
        )
        print(f"\nExperiment completed: {result['experiment_id']}")
        print(f"Results saved to: {result['exp_dir']}")
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
