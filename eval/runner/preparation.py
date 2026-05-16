from __future__ import annotations

import json
import warnings
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from loguru import logger

from src.exceptions import ConfigurationError, TestSetError
from src.experiment import ExperimentConfig, is_new_format
from src.meal import (
    MealManager,
    MealStatus,
    build_chunks_if_needed,
    compute_chunker_config_hash,
    compute_embedding_config_hash,
    compute_parser_config_hash,
    create_artifact_cache,
)
from src.sampler import SamplingConfig
from src.test_generator import TestSetGenerator
from src.test_set_manager import TestSetManager
from src.token_tracker import TokenTracker

if TYPE_CHECKING:
    from src.indexer import VectorIndexer
    from src.meal import MealConfig

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _build_parser_section(parser_config: dict) -> dict:
    if "primary" in parser_config:
        return {
            "primary": parser_config.get("primary", "pymupdf4llm"),
            "enhancer": parser_config.get("table_enhancer"),
            "primary_config": parser_config.get(
                parser_config.get("primary", "pymupdf4llm"), {}
            ),
            "enhancer_config": parser_config.get(
                parser_config.get("table_enhancer", ""), {}
            ),
        }
    algorithm = parser_config.get("algorithm", "pymupdf4llm")
    return {
        "algorithm": algorithm,
        "options": parser_config.get(algorithm, {}),
    }


def prepare_meal(
    system_config: dict[str, Any],
    exp_config: ExperimentConfig,
    skip_preprocessing: bool = False,
    force_meal: bool = False,
    force_parse: bool = False,
    force_chunk: bool = False,
    profiler: Any | None = None,
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
        profiler: Optional PipelineProfiler for stage tracking.

    Returns:
        Dictionary containing meal configuration and status.

    Raises:
        FileNotFoundError: If meal doesn't exist and create_if_missing is not configured.
        ValueError: If meal creation fails.
    """
    meal_manager = MealManager(system_config, profiler=profiler)
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
        trashbin = Path(_PROJECT_ROOT) / ".trashbin"
        trashbin.mkdir(parents=True, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        trashed_name = f"{meal_name}_{timestamp}"
        trashed_path = trashbin / trashed_name
        shutil.move(str(meal_dir), str(trashed_path))
        logger.info(f"Moved existing meal to trashbin: {trashed_path}")

    if meal_manager.meal_exists(meal_name):
        meal_config = meal_manager.load_meal(meal_name)

        _, current_hashes = meal_manager._build_config_snapshot_and_hashes()
        if meal_config.config_hashes != current_hashes:
            import shutil

            logger.warning(
                f"Meal '{meal_name}' has stale config_hashes. "
                f"Stored: {meal_config.config_hashes}, "
                f"Current: {current_hashes}. "
                f"Backing up and recreating with current configuration."
            )
            meal_dir = meal_manager.get_meal_dir(meal_name)
            meals_dir = meal_dir.parent
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_name = f"{meal_name}_backup_{timestamp}"
            backup_path = meals_dir / backup_name
            shutil.copytree(str(meal_dir), str(backup_path))
            logger.info(f"Backed up stale meal to: {backup_path}")
            shutil.rmtree(str(meal_dir))
            logger.info(f"Removed stale meal directory: {meal_dir}")
        else:
            logger.info(f"Meal '{meal_name}' found, loading...")

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


def prepare_legacy_test_set(
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

    .. deprecated:: v0.2.0
        This function handles deprecated test set configuration format.
        Use :func:`prepare_test_sets` instead, which supports the new format.
        This function will be removed in v0.3.0.

    TODO: Remove in v0.3.0 after all experiments migrated to new config format.

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
    import warnings

    warnings.warn(
        "prepare_legacy_test_set is deprecated and will be removed in v0.3.0. "
        "Use prepare_test_sets with the new config format instead.",
        DeprecationWarning,
        stacklevel=2,
    )
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
                type_distribution=type_distribution,
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
            test_set_data = prepare_legacy_test_set(
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

    cache = create_artifact_cache(merged_config)

    parser_section = _build_parser_section(merged_config.get("parser", {}))
    current_parser_hash = compute_parser_config_hash(parser_section)
    parsed_dir = cache.get_parsed_dir(
        meal_config.data_id,
        parser_hash=current_parser_hash,
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
    profiler: Any | None = None,
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
        profiler: Optional PipelineProfiler for stage tracking.

    Returns:
        Configured VectorIndexer instance.
    """
    from src.indexer import VectorIndexer

    chunker_config = merged_config.get("chunker", {})
    embedding_config = merged_config.get("embedding", {})
    vector_store_config = merged_config.get("vector_store", {})

    chunker_hash = compute_chunker_config_hash(chunker_config)
    parser_section = _build_parser_section(merged_config.get("parser", {}))
    current_parser_hash = compute_parser_config_hash(parser_section)
    current_embedding_hash = compute_embedding_config_hash(embedding_config)
    config_hashes = {
        "parser": current_parser_hash,
        "chunker": chunker_hash,
        "embedding": current_embedding_hash,
    }
    from src.meal import compute_index_key, generate_collection_name

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

        cache = create_artifact_cache(merged_config)

        parsed_dir = cache.get_parsed_dir(
            meal_config.data_id,
            parser_hash=current_parser_hash,
        )
        chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)

        build_chunks_if_needed(
            parsed_dir,
            chunks_dir,
            chunker_config,
            model_name=chunker_config.get("model_name")
            or embedding_config.get("model_name"),
        )

        from src.meal import build_index_from_chunks

        indexer = build_index_from_chunks(
            chunks_dir=chunks_dir,
            embedding_config=embedding_config,
            vector_store_config=vector_store_config,
            collection_name=collection_name,
            profiler=profiler,
        )

        logger.success(f"Index built for variant '{variant_name}'")
    else:
        logger.info(
            f"Index already exists for variant '{variant_name}' "
            f"({collection_info.get('points_count')} points)"
        )

    return indexer
