import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from loguru import logger

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.experiment import (
    ExperimentConfig,
    ExperimentManager,
    load_experiment_config,
    merge_config,
)
from src.meal import MealManager, MealStatus, compute_file_sha256
from src.meal import (
    ArtifactCache,
    build_chunks_if_needed,
    build_index_from_chunks,
    compute_chunker_config_hash,
    compute_index_key,
    generate_collection_name,
)
from src.pipeline import RAGPipeline
from src.sampler import SamplingConfig
from src.test_generator import TestSetGenerator
from src.token_tracker import TokenTracker
from src.utils import get_llm_config, load_config, setup_logger
from eval.metrics import calculate_hit_rate, calculate_mrr, calculate_ndcg
from eval.experiment_reporter import ExperimentReporter


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
    missing_files: List[str] = field(default_factory=list)
    invalid_files: List[str] = field(default_factory=list)
    pdf_issues: Dict[str, str] = field(default_factory=dict)
    raw_dir: Optional[Path] = None

    def to_dict(self) -> Dict[str, Any]:
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


def verify_experiment_assets(
    exp_dir: Path,
    system_config: Dict[str, Any],
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
        raise FileNotFoundError(f"Experiment directory not found: {exp_dir}")

    missing_files = []
    invalid_files = []
    pdf_issues: Dict[str, str] = {}

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
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if not data.get("name"):
                            invalid_files.append(filename)
                            logger.warning(f"Invalid {filename}: missing 'name' field")
                elif filename == "config_snapshot.yaml":
                    import yaml
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = yaml.safe_load(f)
                        if not data:
                            invalid_files.append(filename)
                            logger.warning(f"Invalid {filename}: empty or invalid YAML")
                elif filename == "meal_snapshot.json":
                    with open(file_path, "r", encoding="utf-8") as f:
                        data = json.load(f)
                        if "pdf_files" not in data:
                            invalid_files.append(filename)
                            logger.warning(f"Invalid {filename}: missing 'pdf_files' field")
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
            with open(meal_snapshot_path, "r", encoding="utf-8") as f:
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
                            pdf_issues[pdf_path] = f"SHA256 mismatch (expected: {expected_sha256[:12]}..., got: {actual_sha256[:12]}...)"
                            logger.warning(f"PDF SHA256 mismatch: {pdf_path}")
                        else:
                            logger.debug(f"PDF verified: {pdf_path}")
                    except Exception as e:
                        pdf_issues[pdf_path] = f"Hash computation error: {str(e)}"
                        logger.warning(f"Failed to compute SHA256 for {pdf_path}: {str(e)}")
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


def prepare_meal(
    system_config: Dict[str, Any],
    exp_config: ExperimentConfig,
    skip_preprocessing: bool = False,
) -> Dict[str, Any]:
    """
    Prepare meal for experiment.

    Checks if the specified meal exists. If not and create_if_missing is configured,
    creates the meal automatically.

    Args:
        system_config: System configuration dictionary.
        exp_config: Experiment configuration.
        skip_preprocessing: If True, skip preprocessing even if meal doesn't exist.

    Returns:
        Dictionary containing meal configuration and status.

    Raises:
        FileNotFoundError: If meal doesn't exist and create_if_missing is not configured.
        ValueError: If meal creation fails.
    """
    meal_manager = MealManager(system_config)
    meal_name = exp_config.data.get("meal")

    if not meal_name:
        raise ValueError("Experiment configuration must specify a meal name in data.meal field")

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
        raise FileNotFoundError(
            f"Meal '{meal_name}' not found and create_if_missing is not configured. "
            "Please create the meal first or add create_if_missing configuration."
        )

    if skip_preprocessing:
        raise FileNotFoundError(
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
        logger.warning("No sampling configuration found, using full dataset (ratio=1.0)")

    sampling_config = SamplingConfig(mode=sample_mode, value=sample_value)
    seed = create_config.get("seed")

    try:
        meal_config = meal_manager.create_meal(
            name=meal_name,
            sampling_config=sampling_config,
            seed=seed,
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


def prepare_test_sets(
    system_config: Dict[str, Any],
    exp_config: ExperimentConfig,
    meal_info: Dict[str, Any],
    skip_preprocessing: bool = False,
    token_tracker: Optional[TokenTracker] = None,
) -> List[Dict[str, Any]]:
    """
    Prepare test sets for experiment.

    Checks if the specified test sets exist. If not, generates them automatically.

    Args:
        system_config: System configuration dictionary.
        exp_config: Experiment configuration.
        meal_info: Meal information dictionary from prepare_meal.
        skip_preprocessing: If True, skip generation even if test sets don't exist.

    Returns:
        List of test set dictionaries.

    Raises:
        FileNotFoundError: If test set doesn't exist and skip_preprocessing is True.
        ValueError: If test set generation fails.
    """
    meal_name = meal_info["name"]
    meal_manager = MealManager(system_config)
    meal_dir = meal_manager.get_meal_dir(meal_name)
    test_sets_dir = meal_dir / "test_sets"

    test_sets = []

    for test_set_config in exp_config.test_sets:
        strategy = test_set_config.get("strategy", "factual")
        num_questions = test_set_config.get("num_questions", 20)
        seed = test_set_config.get("seed")

        filename = f"auto_{strategy}_n{num_questions}"
        test_set_path = test_sets_dir / f"{filename}.json"

        if test_set_path.exists():
            logger.info(f"Test set '{filename}' found, loading...")
            try:
                with open(test_set_path, "r", encoding="utf-8") as f:
                    test_set_data = json.load(f)

                existing_count = len(test_set_data.get("questions", []))
                if existing_count != num_questions:
                    logger.warning(
                        f"Existing test set has {existing_count} questions, "
                        f"but {num_questions} requested. Regenerating."
                    )
                    test_set_path.unlink()
                else:
                    test_sets.append(test_set_data)
                    logger.success(f"Test set '{filename}' loaded ({existing_count} questions)")
                    continue
            except Exception as e:
                logger.warning(f"Failed to load test set '{filename}': {str(e)}, will regenerate")

        if skip_preprocessing:
            raise FileNotFoundError(
                f"Test set '{filename}' not found and skip_preprocessing is enabled. "
                "Cannot generate test set in skip_preprocessing mode."
            )

        logger.info(f"Generating test set '{filename}' ({strategy}, {num_questions} questions)...")

        try:
            generator = TestSetGenerator(system_config)
            llm_preset = exp_config.evaluation.get("llm_preset", "default")

            test_set_data = generator.generate_test_set(
                meal_name=meal_name,
                strategy=strategy,
                num_questions=num_questions,
                llm_preset=llm_preset,
                seed=seed,
                token_tracker=token_tracker,
            )

            test_sets.append(test_set_data)
            logger.success(f"Test set '{filename}' generated ({len(test_set_data.get('questions', []))} questions)")
        except Exception as e:
            logger.error(f"Failed to generate test set '{filename}': {str(e)}")
            raise

    return test_sets


def prepare_index_for_variant(
    merged_config: Dict[str, Any],
    meal_config: "MealConfig",
    variant_name: str,
) -> "VectorIndexer":
    """
    Prepare or retrieve index for a variant.

    Checks if the index already exists for the variant's configuration.
    If not, builds chunks and index from scratch.

    Args:
        merged_config: Merged configuration dictionary.
        meal_config: Meal configuration object.
        variant_name: Name of the variant.

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
    index_exists = collection_info is not None and collection_info.get("points_count", 0) > 0

    if not index_exists:
        logger.info(f"Building index for variant '{variant_name}'...")

        artifacts_config = merged_config.get("artifacts") or {}
        artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
        cache = ArtifactCache(artifacts_dir)

        parsed_dir = cache.get_parsed_dir(meal_config.data_id)
        chunks_dir = cache.get_chunks_dir(meal_config.data_id, chunker_hash)

        build_chunks_if_needed(parsed_dir, chunks_dir, chunker_config)

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


def evaluate_test_set(
    pipeline: RAGPipeline,
    test_set: Dict[str, Any],
) -> List[Dict[str, Any]]:
    """
    Evaluate a single test set against the pipeline.

    Args:
        pipeline: Configured RAG pipeline.
        test_set: Test set dictionary with questions.

    Returns:
        List of evaluation result dictionaries.
    """
    test_set_name = test_set.get("name", "unknown")
    questions = test_set.get("questions", [])

    logger.info(f"Evaluating test set '{test_set_name}' ({len(questions)} questions)...")

    results = []
    for i, question_data in enumerate(questions, 1):
        question_id = question_data.get("id", f"q{i}")
        question_text = question_data.get("question", "")
        expected_sources = question_data.get("source_files", [])

        if not question_text:
            logger.warning(f"Question {question_id} has no text, skipping")
            continue

        logger.info(f"Processing question {i}/{len(questions)}: {question_id}")

        case_start_time = time.time()
        try:
            response = pipeline.query(question_text)
            case_time = time.time() - case_start_time

            retrieved_sources = response.get("sources", [])

            hit_rate = calculate_hit_rate(retrieved_sources, expected_sources)
            mrr = calculate_mrr(retrieved_sources, expected_sources)
            ndcg = calculate_ndcg(retrieved_sources, expected_sources, k=5)

            result = {
                "id": question_id,
                "question": question_text,
                "answer": response.get("answer"),
                "retrieval": {
                    "hit_rate": hit_rate,
                    "mrr": mrr,
                    "ndcg": ndcg,
                },
                "sources": retrieved_sources,
                "expected_sources": expected_sources,
                "time_seconds": case_time,
                "test_set": test_set_name,
                "category": question_data.get("category"),
                "difficulty": question_data.get("difficulty"),
                "token_usage": response.get("token_usage"),
            }

            logger.success(
                f"Question {question_id}: HR={hit_rate:.4f}, MRR={mrr:.4f}, "
                f"NDCG={ndcg:.4f} ({case_time:.2f}s)"
            )

        except Exception as e:
            case_time = time.time() - case_start_time
            logger.error(f"Question {question_id} failed: {str(e)}")
            result = {
                "id": question_id,
                "question": question_text,
                "answer": None,
                "error": str(e),
                "expected_sources": expected_sources,
                "time_seconds": case_time,
                "test_set": test_set_name,
                "category": question_data.get("category"),
            }

        results.append(result)

    return results


def compute_aggregate_metrics(results: List[Dict[str, Any]]) -> Dict[str, float]:
    """
    Compute aggregate retrieval metrics from evaluation results.

    Args:
        results: List of evaluation result dictionaries.

    Returns:
        Dictionary containing average hit_rate, mrr, and ndcg.
    """
    valid_results = [r for r in results if "retrieval" in r]
    if valid_results:
        avg_hit_rate = sum(r["retrieval"]["hit_rate"] for r in valid_results) / len(valid_results)
        avg_mrr = sum(r["retrieval"]["mrr"] for r in valid_results) / len(valid_results)
        avg_ndcg = sum(r["retrieval"]["ndcg"] for r in valid_results) / len(valid_results)
    else:
        avg_hit_rate = 0.0
        avg_mrr = 0.0
        avg_ndcg = 0.0

    return {
        "avg_hit_rate": avg_hit_rate,
        "avg_mrr": avg_mrr,
        "avg_ndcg": avg_ndcg,
    }


def run_variant_evaluation(
    system_config: Dict[str, Any],
    exp_config: ExperimentConfig,
    variant: Dict[str, Any],
    meal_info: Dict[str, Any],
    test_sets: List[Dict[str, Any]],
    exp_dir: Path,
    test_generation_tracker: Optional[TokenTracker] = None,
) -> Dict[str, Any]:
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
        "merged": {
            "chunker": merged_config.get("chunker", {}),
            "embedding": merged_config.get("embedding", {}),
            "retrieval": merged_config.get("retrieval", {}),
        },
    }

    llm_preset = exp_config.evaluation.get("llm_preset", "default")

    try:
        variant_tracker = TokenTracker()

        pipeline = RAGPipeline(
            config_path=None,
            llm_preset=llm_preset,
            meal_name=meal_name,
            token_tracker=variant_tracker,
        )
        pipeline.config = merged_config

        if hasattr(pipeline, 'indexer') and pipeline.indexer is not None:
            pipeline.indexer.close()

        indexer = prepare_index_for_variant(merged_config, meal_config, variant_name)
        pipeline.indexer = indexer
        pipeline.retriever.indexer = indexer

        total_start_time = time.time()
        all_results = []
        for test_set in test_sets:
            results = evaluate_test_set(pipeline, test_set)
            all_results.extend(results)

        total_time = time.time() - total_start_time

        metrics = compute_aggregate_metrics(all_results)

        token_usage_data = variant_tracker.to_dict()
        if test_generation_tracker is not None and test_generation_tracker.record_count > 0:
            token_usage_data["test_generation"] = test_generation_tracker.to_dict()

        variant_result = {
            "variant_name": variant_name,
            "variant_description": variant.get("description", ""),
            "timestamp": datetime.now().isoformat(),
            "total_questions": len(all_results),
            "total_time_seconds": total_time,
            "avg_time_per_question": total_time / len(all_results) if all_results else 0,
            "retrieval_metrics": metrics,
            "config_snapshot": config_snapshot,
            "results": all_results,
            "token_usage": token_usage_data,
        }

        logger.success(
            f"Variant '{variant_name}' evaluation completed: "
            f"HR={metrics['avg_hit_rate']:.4f}, MRR={metrics['avg_mrr']:.4f}, "
            f"NDCG={metrics['avg_ndcg']:.4f}"
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
        raise


def run_experiment(
    config_path: str,
    skip_preprocessing: bool = False,
    use_llm_report: bool = False,
    system_config_path: str = "config.yaml",
) -> Dict[str, Any]:
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

    logger.info(f"Experiment directory: {exp_dir}")

    try:
        logger.info("Step 1: Preparing meal...")
        meal_info = prepare_meal(system_config, exp_config, skip_preprocessing)

        test_generation_tracker = TokenTracker()

        logger.info("Step 2: Preparing test sets...")
        test_sets = prepare_test_sets(
            system_config, exp_config, meal_info, skip_preprocessing,
            token_tracker=test_generation_tracker,
        )

        meal_snapshot = meal_info["config"].to_dict()

        test_set_snapshots = []
        for test_set in test_sets:
            test_set_snapshots.append({
                "name": test_set.get("name"),
                "strategy": test_set.get("strategy"),
                "num_questions": len(test_set.get("questions", [])),
                "created_at": test_set.get("created_at"),
                "meal_data_id": test_set.get("meal_data_id"),
            })

        config_snapshot = {
            "data": exp_config.data,
            "test_sets": exp_config.test_sets,
            "evaluation": exp_config.evaluation,
            "llm": exp_config.llm,
        }

        exp_manager.save_snapshots(
            exp_dir=exp_dir,
            config=exp_config,
            meal_snapshot=meal_snapshot,
            test_set_snapshots=test_set_snapshots,
            config_snapshot=config_snapshot,
        )

        logger.info("Step 3: Running variant evaluations...")
        all_variant_results = []
        experiment_tracker = TokenTracker()

        for i, variant in enumerate(exp_config.variants, 1):
            variant_name = variant.get("name", f"variant_{i}")
            logger.info(f"Evaluating variant {i}/{len(exp_config.variants)}: {variant_name}")

            try:
                variant_result = run_variant_evaluation(
                    system_config=system_config,
                    exp_config=exp_config,
                    variant=variant,
                    meal_info=meal_info,
                    test_sets=test_sets,
                    exp_dir=exp_dir,
                    test_generation_tracker=test_generation_tracker,
                )

                exp_manager.save_variant_result(exp_dir, variant_name, variant_result)
                all_variant_results.append(variant_result)

                if "token_usage" in variant_result:
                    variant_tracker = TokenTracker()
                    for rec_data in variant_result["token_usage"].get("records", []):
                        from src.token_tracker import DetailedTokenUsage, TokenRecord
                        usage = DetailedTokenUsage(
                            input_tokens=rec_data["usage"]["input_tokens"],
                            output_tokens=rec_data["usage"]["output_tokens"],
                            system_prompt_tokens=rec_data["usage"].get("system_prompt_tokens", 0),
                            contexts_tokens=rec_data["usage"].get("contexts_tokens", 0),
                            query_tokens=rec_data["usage"].get("query_tokens", 0),
                        )
                        variant_tracker.record(
                            category=rec_data["category"],
                            model_name=rec_data["model_name"],
                            usage=usage,
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

        total_token_usage = experiment_tracker.get_total()
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

        if info.get('meal_snapshot'):
            print(f"\nMeal: {info['meal_snapshot'].get('name', 'N/A')}")
            print(f"Data ID: {info['meal_snapshot'].get('data_id', 'N/A')[:12]}...")

        if info.get('test_set_snapshots'):
            print(f"\nTest Sets ({len(info['test_set_snapshots'])}):")
            for ts in info['test_set_snapshots']:
                print(f"  - {ts.get('strategy', 'unknown')}: {ts.get('num_questions', 0)} questions")

        if info.get('variant_results'):
            print(f"\nVariant Results ({len(info['variant_results'])}):")
            for vr in info['variant_results']:
                name = vr.get('variant_name', 'unknown')
                if 'retrieval_metrics' in vr:
                    metrics = vr['retrieval_metrics']
                    print(f"  - {name}: HR={metrics.get('avg_hit_rate', 0):.4f}, "
                          f"MRR={metrics.get('avg_mrr', 0):.4f}, "
                          f"NDCG={metrics.get('avg_ndcg', 0):.4f}")
                else:
                    print(f"  - {name}: {vr.get('error', 'No metrics')}")

        print("\n" + "=" * 80)

    except FileNotFoundError:
        print(f"Experiment not found: {exp_id}")
        sys.exit(1)


def compare_experiments(
    exp_ids: List[str],
    system_config_path: str = "config.yaml",
    output_format: str = "table",
    save_report: bool = False,
    report_path: Optional[str] = None,
) -> Dict[str, Any]:
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
            exp_dir = Path(system_config.get("experiments", {}).get("dir", "data/exp_reports"))
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


def _build_comparison_data(results: List[Dict[str, Any]]) -> Dict[str, Any]:
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
                "data_id": meal.get("data_id", "N/A")[:12] if meal.get("data_id") else "N/A",
                "pdf_count": meal.get("stats", {}).get("total_pdfs", 0),
                "page_count": meal.get("stats", {}).get("total_pages", 0),
                "chunk_count": meal.get("stats", {}).get("total_chunks", 0),
            }

        if info.get("test_set_snapshots"):
            for ts in info["test_set_snapshots"]:
                exp_data["test_sets"].append({
                    "strategy": ts.get("strategy", "unknown"),
                    "num_questions": ts.get("num_questions", 0),
                })

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
                            "chunk_size": merged.get("chunker", {}).get("chunk_size", "N/A"),
                            "chunk_overlap": merged.get("chunker", {}).get("chunk_overlap", "N/A"),
                            "embedding_model": merged.get("embedding", {}).get("model_name", "N/A"),
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
            best_variants.append({
                "experiment_name": exp["name"],
                "variant_name": best_variant["name"],
                "metrics": best_variant["metrics"],
            })

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


def _extract_category_metrics(variant_result: Dict[str, Any]) -> Dict[str, Dict[str, float]]:
    """
    Extract metrics grouped by question category from variant results.

    Args:
        variant_result: Variant result dictionary.

    Returns:
        Dictionary mapping category names to their metrics.
    """
    category_metrics: Dict[str, Dict[str, List[float]]] = {}

    for result in variant_result.get("results", []):
        category = result.get("category", "unknown")
        if category not in category_metrics:
            category_metrics[category] = {
                "hit_rates": [],
                "mrrs": [],
                "ndcgs": [],
            }

        if "retrieval" in result:
            category_metrics[category]["hit_rates"].append(result["retrieval"].get("hit_rate", 0))
            category_metrics[category]["mrrs"].append(result["retrieval"].get("mrr", 0))
            category_metrics[category]["ndcgs"].append(result["retrieval"].get("ndcg", 0))

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
    comparison_data: Dict[str, Any],
    not_found: List[str],
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
        print(f"\nWarning: The following experiments were not found: {', '.join(not_found)}")

    print("\n" + "-" * 120)
    print("SUMMARY: BEST VARIANT PER EXPERIMENT")
    print("-" * 120)
    print(f"{'Experiment':<35} {'Variant':<25} {'Hit Rate':>10} {'MRR':>10} {'NDCG':>10}")
    print("-" * 120)

    for bv in comparison_data["best_variants"]:
        print(f"{bv['experiment_name'][:33]:<35} {bv['variant_name'][:23]:<25} "
              f"{bv['metrics']['hit_rate']:>10.4f} {bv['metrics']['mrr']:>10.4f} "
              f"{bv['metrics']['ndcg']:>10.4f}")

    print("-" * 120)

    print("\n" + "-" * 120)
    print("DETAILED RESULTS: ALL VARIANTS")
    print("-" * 120)

    for exp in comparison_data["experiments"]:
        print(f"\nExperiment: {exp['name']} ({exp['experiment_id']})")
        print(f"Status: {exp['status']} | Created: {exp['created_at']}")

        if exp["meal_info"]:
            print(f"Meal: {exp['meal_info']['name']} ({exp['meal_info']['pdf_count']} PDFs, "
                  f"{exp['meal_info']['page_count']} pages)")

        if exp["test_sets"]:
            test_set_str = ", ".join(
                f"{ts['strategy']}({ts['num_questions']})" for ts in exp["test_sets"]
            )
            print(f"Test Sets: {test_set_str}")

        print(f"\n{'Variant':<30} {'Hit Rate':>10} {'MRR':>10} {'NDCG':>10} {'Time':>10}")
        print("-" * 80)

        for v in exp["variants"]:
            time_str = f"{v['avg_time_per_question']:.2f}s" if v.get("avg_time_per_question") else "N/A"
            print(f"{v['name'][:28]:<30} {v['metrics']['hit_rate']:>10.4f} "
                  f"{v['metrics']['mrr']:>10.4f} {v['metrics']['ndcg']:>10.4f} {time_str:>10}")

            if "error" in v:
                print(f"  Error: {v['error']}")

            if "category_metrics" in v:
                print("  By Category:")
                for cat, metrics in v["category_metrics"].items():
                    print(f"    {cat}: HR={metrics['hit_rate']:.4f}, "
                          f"MRR={metrics['mrr']:.4f}, NDCG={metrics['ndcg']:.4f} ({metrics['count']} questions)")

    print("\n" + "=" * 120 + "\n")


def _generate_comparison_report(
    comparison_data: Dict[str, Any],
    not_found: List[str],
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
    lines.append(f"**Experiments Compared**: {comparison_data['summary']['total_experiments']}")
    lines.append(f"**Total Variants**: {comparison_data['summary']['total_variants']}")
    lines.append("")

    if not_found:
        lines.append("## Warnings")
        lines.append("")
        lines.append(f"The following experiments were not found: {', '.join(not_found)}")
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
            time_str = f"{v['avg_time_per_question']:.2f}s" if v.get("avg_time_per_question") else "N/A"
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
    output_dir: Optional[str] = None,
) -> Dict[str, Any]:
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
        raise FileNotFoundError(f"Experiment directory not found: {exp_dir}")

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
            raise ValueError("Asset verification failed. See details above.")
    else:
        logger.warning("Skipping asset verification (--skip-verification)")

    config_path = exp_path / "config_snapshot.yaml"
    if not config_path.exists():
        raise FileNotFoundError(f"Configuration snapshot not found: {config_path}")

    logger.info(f"Reproducing experiment from: {exp_dir}")
    logger.info("Note: Results may differ due to LLM randomness.")

    import tempfile
    import yaml

    with open(config_path, "r", encoding="utf-8") as f:
        config_snapshot = yaml.safe_load(f)

    manifest_path = exp_path / "manifest.json"
    with open(manifest_path, "r", encoding="utf-8") as f:
        manifest = json.load(f)

    original_variants = manifest.get("variants", [])
    if original_variants:
        variants = []
        for v_name in original_variants:
            result_path = exp_path / "results" / f"{v_name.lower().replace(' ', '_').replace('-', '_')}.json"
            variant_config = {"name": v_name, "config_overrides": {}}

            if result_path.exists():
                try:
                    with open(result_path, "r", encoding="utf-8") as f:
                        result_data = json.load(f)
                    if "config_snapshot" in result_data and "variant" in result_data["config_snapshot"]:
                        variant_config["config_overrides"] = result_data["config_snapshot"]["variant"].get("config_overrides", {})
                        variant_config["description"] = result_data["config_snapshot"]["variant"].get("description", "")
                except Exception as e:
                    logger.warning(f"Failed to load variant config from {result_path}: {str(e)}")

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
            print(f"\nExperiment reproduced successfully!")
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
