import warnings

warnings.warn(
    "eval/run_eval.py is deprecated and will be removed in a future version. "
    "Use eval/run_experiment.py with ExperimentConfig instead.",
    DeprecationWarning,
    stacklevel=2,
)

import json
import random
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

from eval.metrics import (
    calculate_answer_relevancy,
    calculate_context_precision,
    calculate_context_recall,
    calculate_faithfulness,
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
)
from src.experiment import (
    ExperimentConfig,
    is_new_format,
    load_experiment_config,
    merge_config,
)
from src.meal import MealManager, MealStatus
from src.pipeline import RAGPipeline
from src.sampler import SamplingConfig
from src.test_set_manager import TestSetManager
from src.utils import get_llm_config, load_config, setup_logger

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))


DEFAULT_RETRIEVAL_METRICS = ["hit_rate", "mrr", "ndcg"]
DEFAULT_GENERATION_METRICS = ["faithfulness", "answer_relevancy"]
DEFAULT_LLM_RETRIEVAL_METRICS = ["context_precision", "context_recall"]


def run_evaluation(
    pipeline: RAGPipeline,
    test_data_path: str,
    output_dir: str,
    sample_size: int = None,
    meal_data_id: str = None,
    metrics_config: list[str] | None = None,
    generation_metrics_config: list[str] | None = None,
    llm_retrieval_metrics_config: list[str] | None = None,
    llm_config: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Run evaluation on test data using the provided RAG pipeline.

    Args:
        pipeline: Configured RAG pipeline instance.
        test_data_path: Path to test data JSON file.
        output_dir: Directory to save evaluation report.
        sample_size: Optional number of test cases to sample.
        meal_data_id: Optional meal data identifier.
        metrics_config: Optional list of retrieval metric names to calculate.
            Defaults to ["hit_rate", "mrr", "ndcg"] when None.
        generation_metrics_config: Optional list of generation metric names to calculate.
            Supports "faithfulness" and "answer_relevancy". Defaults to empty list.
        llm_retrieval_metrics_config: Optional list of LLM-based retrieval metrics.
            Supports "context_precision" and "context_recall". Defaults to empty list.
        llm_config: Optional LLM configuration for generation metrics.
            Must contain api_key, base_url, and model_name keys.

    Returns:
        Dictionary containing evaluation summary with results and metrics.
    """
    if metrics_config is None:
        metrics_config = list(DEFAULT_RETRIEVAL_METRICS)
    if generation_metrics_config is None:
        generation_metrics_config = []
    if llm_retrieval_metrics_config is None:
        llm_retrieval_metrics_config = []
    test_data_path = Path(test_data_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(test_data_path, encoding="utf-8") as f:
        test_data = json.load(f)

    if isinstance(test_data, list):
        test_cases = test_data
    elif isinstance(test_data, dict) and "questions" in test_data:
        test_cases = test_data["questions"]
    else:
        logger.error(f"Unsupported test data format: {type(test_data)}")
        sys.exit(1)

    if sample_size and sample_size < len(test_cases):
        logger.info(f"Sampling {sample_size} test cases for quick evaluation")
        test_cases = random.sample(test_cases, sample_size)

    logger.info(f"Running evaluation on {len(test_cases)} test cases")

    results = []
    total_start_time = time.time()

    for i, test_case in enumerate(test_cases, 1):
        logger.info(
            f"Processing test case {i}/{len(test_cases)}: {test_case['id']}")

        case_start_time = time.time()
        try:
            response = pipeline.query(test_case["question"])
            case_time = time.time() - case_start_time

            retrieved_sources = response.get("sources", [])

            expected_sources = test_case.get("expected_sources", [])
            if not expected_sources:
                expected_sources = test_case.get("source_files", [])

            expect_retrieval = test_case.get("expect_retrieval", True)

            retrieval = {}
            if expect_retrieval and expected_sources:
                if "hit_rate" in metrics_config:
                    retrieval["hit_rate"] = calculate_hit_rate(retrieved_sources, expected_sources)
                if "mrr" in metrics_config:
                    retrieval["mrr"] = calculate_mrr(retrieved_sources, expected_sources)
                if "ndcg" in metrics_config:
                    retrieval["ndcg"] = calculate_ndcg(retrieved_sources, expected_sources, k=5)

            generation = {}
            if generation_metrics_config and llm_config:
                contexts = response.get("contexts", [])
                answer = response.get("answer", "")
                question = test_case.get("question", "")
                ground_truth = test_case.get("answer", "")

                if "faithfulness" in generation_metrics_config:
                    try:
                        logger.info(f"Calculating faithfulness for test case {test_case['id']}")
                        faithfulness_score = calculate_faithfulness(
                            answer=answer,
                            contexts=contexts,
                            api_key=llm_config["api_key"],
                            base_url=llm_config["base_url"],
                            model_name=llm_config["model_name"],
                        )
                        generation["faithfulness"] = faithfulness_score
                    except Exception as e:
                        logger.error(f"Failed to calculate faithfulness: {str(e)}")
                        generation["faithfulness"] = None

                if "answer_relevancy" in generation_metrics_config:
                    try:
                        logger.info(f"Calculating answer relevancy for test case {test_case['id']}")
                        relevancy_score = calculate_answer_relevancy(
                            question=question,
                            answer=answer,
                            api_key=llm_config["api_key"],
                            base_url=llm_config["base_url"],
                            model_name=llm_config["model_name"],
                        )
                        generation["answer_relevancy"] = relevancy_score
                    except Exception as e:
                        logger.error(f"Failed to calculate answer relevancy: {str(e)}")
                        generation["answer_relevancy"] = None

            llm_retrieval = {}
            if llm_retrieval_metrics_config and llm_config and contexts:
                question = test_case.get("question", "")
                ground_truth = test_case.get("answer", "")

                if "context_precision" in llm_retrieval_metrics_config:
                    try:
                        logger.info(f"Calculating context precision for test case {test_case['id']}")
                        cp_score = calculate_context_precision(
                            question=question,
                            expected_output=ground_truth,
                            retrieval_context=contexts,
                            api_key=llm_config["api_key"],
                            base_url=llm_config["base_url"],
                            model_name=llm_config["model_name"],
                        )
                        llm_retrieval["context_precision"] = cp_score
                    except Exception as e:
                        logger.error(f"Failed to calculate context precision: {str(e)}")
                        llm_retrieval["context_precision"] = None

                if "context_recall" in llm_retrieval_metrics_config:
                    try:
                        logger.info(f"Calculating context recall for test case {test_case['id']}")
                        cr_score = calculate_context_recall(
                            question=question,
                            ground_truth=ground_truth,
                            retrieval_context=contexts,
                            api_key=llm_config["api_key"],
                            base_url=llm_config["base_url"],
                            model_name=llm_config["model_name"],
                        )
                        llm_retrieval["context_recall"] = cr_score
                    except Exception as e:
                        logger.error(f"Failed to calculate context recall: {str(e)}")
                        llm_retrieval["context_recall"] = None

            result = {
                "id": test_case["id"],
                "question": test_case["question"],
                "answer": response["answer"],
                "retrieval": retrieval,
                "sources": retrieved_sources,
                "time_seconds": case_time,
            }

            if generation:
                result["generation"] = generation

            if llm_retrieval:
                result["llm_retrieval"] = llm_retrieval

            metric_parts = []
            if "hit_rate" in retrieval:
                metric_parts.append(f"HR={retrieval['hit_rate']:.2f}")
            if "mrr" in retrieval:
                metric_parts.append(f"MRR={retrieval['mrr']:.2f}")
            if "ndcg" in retrieval:
                metric_parts.append(f"NDCG={retrieval['ndcg']:.2f}")
            if generation:
                if "faithfulness" in generation and generation["faithfulness"] is not None:
                    metric_parts.append(f"FA={generation['faithfulness']:.2f}")
                if "answer_relevancy" in generation and generation["answer_relevancy"] is not None:
                    metric_parts.append(f"AR={generation['answer_relevancy']:.2f}")
            if llm_retrieval:
                if "context_precision" in llm_retrieval and llm_retrieval["context_precision"] is not None:
                    metric_parts.append(f"CP={llm_retrieval['context_precision']:.2f}")
                if "context_recall" in llm_retrieval and llm_retrieval["context_recall"] is not None:
                    metric_parts.append(f"CR={llm_retrieval['context_recall']:.2f}")
            metric_str = ", ".join(metric_parts)
            logger.success(
                f"Test case {test_case['id']}: {metric_str} ({case_time:.2f}s)"
            )

        except Exception as e:
            case_time = time.time() - case_start_time
            logger.error(f"Test case {test_case['id']} failed: {str(e)}")
            result = {
                "id": test_case["id"],
                "question": test_case["question"],
                "answer": None,
                "error": str(e),
                "time_seconds": case_time,
            }

        results.append(result)

    total_time = time.time() - total_start_time

    retrieval_metrics = {}
    valid_results = [r for r in results if "retrieval" in r and r["retrieval"]]
    if valid_results:
        for metric_name in metrics_config:
            values = [r["retrieval"][metric_name] for r in valid_results if metric_name in r["retrieval"]]
            if values:
                retrieval_metrics[f"avg_{metric_name}"] = sum(values) / len(values)
            else:
                retrieval_metrics[f"avg_{metric_name}"] = 0

    generation_metrics = {}
    valid_generation_results = [r for r in results if "generation" in r and r["generation"]]
    if valid_generation_results:
        for metric_name in generation_metrics_config:
            values = [
                r["generation"][metric_name]
                for r in valid_generation_results
                if metric_name in r["generation"] and r["generation"][metric_name] is not None
            ]
            if values:
                generation_metrics[f"avg_{metric_name}"] = sum(values) / len(values)

    llm_retrieval_metrics = {}
    valid_llm_retrieval_results = [r for r in results if "llm_retrieval" in r and r["llm_retrieval"]]
    if valid_llm_retrieval_results:
        for metric_name in llm_retrieval_metrics_config:
            values = [
                r["llm_retrieval"][metric_name]
                for r in valid_llm_retrieval_results
                if metric_name in r["llm_retrieval"] and r["llm_retrieval"][metric_name] is not None
            ]
            if values:
                llm_retrieval_metrics[f"avg_{metric_name}"] = sum(values) / len(values)

    summary = {
        "timestamp": datetime.now().isoformat(),
        "meal_data_id": meal_data_id,
        "total_test_cases": len(test_cases),
        "total_time_seconds": total_time,
        "avg_time_per_case": total_time / len(test_cases),
        "retrieval_metrics": retrieval_metrics,
        "results": results,
    }

    if generation_metrics:
        summary["generation_metrics"] = generation_metrics

    if llm_retrieval_metrics:
        summary["llm_retrieval_metrics"] = llm_retrieval_metrics

    output_file = output_dir / "baseline_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.success(f"Evaluation completed in {total_time:.2f}s")
    logger.success(f"Report saved to: {output_file}")

    return summary


def print_summary(summary: dict[str, Any]) -> None:
    """Print evaluation summary to stdout.

    Args:
        summary: Evaluation summary dictionary from run_evaluation.
    """
    print("\n" + "=" * 60)
    print("EVALUATION SUMMARY")
    print("=" * 60)
    print(f"Timestamp: {summary['timestamp']}")
    if summary.get("meal_data_id"):
        print(f"Meal Data ID: {summary['meal_data_id']}")
    print(f"Total test cases: {summary['total_test_cases']}")
    print(f"Total time: {summary['total_time_seconds']:.2f}s")
    print(f"Avg time per case: {summary['avg_time_per_case']:.2f}s")
    print("\nRetrieval Metrics:")
    label_map = {
        "avg_hit_rate": "Hit Rate",
        "avg_mrr": "MRR",
        "avg_ndcg": "NDCG",
    }
    for key, value in summary["retrieval_metrics"].items():
        label = label_map.get(key, key)
        print(f"  {label}: {value:.4f}")

    if summary.get("generation_metrics"):
        print("\nGeneration Metrics:")
        generation_label_map = {
            "avg_faithfulness": "Faithfulness",
            "avg_answer_relevancy": "Answer Relevancy",
        }
        for key, value in summary["generation_metrics"].items():
            label = generation_label_map.get(key, key)
            print(f"  {label}: {value:.4f}")

    if summary.get("llm_retrieval_metrics"):
        print("\nLLM Retrieval Metrics:")
        llm_retrieval_label_map = {
            "avg_context_precision": "Context Precision",
            "avg_context_recall": "Context Recall",
        }
        for key, value in summary["llm_retrieval_metrics"].items():
            label = llm_retrieval_label_map.get(key, key)
            print(f"  {label}: {value:.4f}")

    print("=" * 60)


if __name__ == "__main__":
    print("=" * 60)
    print("WARNING: eval/run_eval.py is DEPRECATED.")
    print("Please use: pixi run python eval/run_experiment.py")
    print("=" * 60)

    import argparse

    parser = argparse.ArgumentParser(description="RAG Evaluation Script")
    parser.add_argument(
        "--test-data", type=str, default="eval/test_data.json", help="Test data path"
    )
    parser.add_argument(
        "--output-dir", type=str, default="data/eval", help="Output directory"
    )
    parser.add_argument(
        "--sample-count", type=int, help="Sample N PDFs for testing"
    )
    parser.add_argument(
        "--sample-pages", type=int, help="Sample PDFs until total pages reach N"
    )
    parser.add_argument(
        "--sample-ratio", type=float, help="Sample ratio of total PDFs (0.0-1.0)"
    )
    parser.add_argument(
        "--build-index", action="store_true", help="Build index before evaluation"
    )
    parser.add_argument(
        "--rebuild", action="store_true", help="Rebuild index from scratch"
    )
    parser.add_argument(
        "--config", type=str, default="config.yaml", help="Config file path"
    )
    parser.add_argument(
        "--llm-preset", type=str, help="LLM preset name (default, opus, sonnet, haiku)"
    )
    parser.add_argument(
        "--meal", type=str, help="Use specified meal for evaluation"
    )
    parser.add_argument(
        "--test-set", type=str,
        help="Test set name within the meal (without .json extension)"
    )
    parser.add_argument(
        "--exp-config", type=str,
        help="Path to experiment configuration YAML file. If specified, "
             "meal and test-set parameters will be loaded from the experiment config."
    )
    parser.add_argument(
        "--variant", type=str,
        help="Variant name to use from experiment config (only valid with --exp-config). "
             "If not specified, uses the first variant."
    )

    args = parser.parse_args()

    config = load_config(args.config)
    setup_logger(config)

    meal_data_id = None
    test_data_path = args.test_data
    output_dir = args.output_dir
    exp_config: ExperimentConfig | None = None
    variant_config: dict[str, Any] | None = None

    if args.exp_config:
        logger.info(f"Loading experiment configuration from {args.exp_config}")
        exp_config = load_experiment_config(args.exp_config)

        if args.meal or args.test_set:
            logger.warning(
                "--meal and --test-set arguments are ignored when --exp-config is specified. "
                "Using values from experiment configuration."
            )

        meal_name = exp_config.data.get("meal")
        if not meal_name:
            logger.error(
                "Experiment configuration must specify a meal name in data.meal field")
            sys.exit(1)

        if args.variant:
            variant_config = None
            for v in exp_config.variants:
                if v.get("name") == args.variant:
                    variant_config = v
                    break
            if variant_config is None:
                available_variants = [v.get("name")
                                      for v in exp_config.variants]
                logger.error(
                    f"Variant '{args.variant}' not found. "
                    f"Available variants: {available_variants}"
                )
                sys.exit(1)
        else:
            variant_config = exp_config.variants[0] if exp_config.variants else None
            if variant_config:
                logger.info(
                    f"Using first variant: {variant_config.get('name')}")

        config = merge_config(config, exp_config, variant_config)

        meal_manager = MealManager(config)
        meal_config = meal_manager.load_meal(meal_name)
        meal_data_id = meal_config.data_id

        status, issues = meal_manager.check_meal_status(meal_name)
        if status != MealStatus.AVAILABLE:
            logger.warning(
                f"Meal '{meal_name}' status: {status.value}. "
                "Some PDFs may be missing or changed."
            )

        test_sets_dir = meal_manager.get_meal_dir(meal_name) / "test_sets"
        test_set_configs = exp_config.test_sets
        test_set_manager = TestSetManager(config)

        if test_set_configs:
            first_test_set = test_set_configs[0]
            if is_new_format(first_test_set):
                test_set_name = first_test_set.get("name")
                test_set_data = test_set_manager.find_by_name(meal_name, test_set_name)
                if test_set_data is None:
                    test_set_files = sorted(test_sets_dir.glob("*.json")) if test_sets_dir.exists() else []
                    if test_set_files:
                        test_set_path = test_set_files[0]
                        logger.warning(
                            f"Test set '{test_set_name}' not found, using: {test_set_path.stem}")
                    else:
                        logger.error(
                            f"No test sets found for meal '{meal_name}'. "
                            "Generate one with: python main.py --generate-test-set {meal_name}"
                        )
                        sys.exit(1)
                else:
                    test_set_path = test_sets_dir / f"{test_set_name}.json"
                    logger.info(f"Using test set: {test_set_name}")
            else:
                strategy = first_test_set.get("strategy", "document")
                num_questions = first_test_set.get("num_questions", 20)
                test_set_path = test_sets_dir / f"auto_{strategy}_n{num_questions}.json"

                if not test_set_path.exists():
                    test_set_files = sorted(test_sets_dir.glob("*.json")) if test_sets_dir.exists() else []
                    if test_set_files:
                        test_set_path = test_set_files[0]
                        logger.info(
                            f"Specified test set not found, using: {test_set_path.stem}")
                    else:
                        logger.error(
                            f"No test sets found for meal '{meal_name}'. "
                            "Generate one with: python main.py --generate-test-set {meal_name}"
                        )
                        sys.exit(1)
        else:
            test_set_files = sorted(test_sets_dir.glob("*.json")) if test_sets_dir.exists() else []
            if not test_set_files:
                logger.error(
                    f"No test sets found for meal '{meal_name}'. "
                    "Generate one with: python main.py --generate-test-set {meal_name}"
                )
                sys.exit(1)
            test_set_path = test_set_files[0]
            logger.info(f"Using test set: {test_set_path.stem}")

        test_data_path = str(test_set_path)
        output_dir = str(meal_manager.get_meal_dir(meal_name))

        llm_preset = exp_config.evaluation.get("llm_preset", args.llm_preset)
    else:
        if args.meal:
            meal_manager = MealManager(config)
            meal_config = meal_manager.load_meal(args.meal)
            meal_data_id = meal_config.data_id

            status, issues = meal_manager.check_meal_status(args.meal)
            if status != MealStatus.AVAILABLE:
                logger.warning(
                    f"Meal '{args.meal}' status: {status.value}. "
                    "Some PDFs may be missing or changed."
                )

            test_sets_dir = meal_manager.get_meal_dir(args.meal) / "test_sets"
            if args.test_set:
                test_set_path = test_sets_dir / f"{args.test_set}.json"
            else:
                test_set_files = sorted(test_sets_dir.glob(
                    "*.json")) if test_sets_dir.exists() else []
                if not test_set_files:
                    logger.error(
                        f"No test sets found for meal '{args.meal}'. "
                        "Generate one with: python main.py --generate-test-set {args.meal}"
                    )
                    sys.exit(1)
                test_set_path = test_set_files[0]
                logger.info(f"Using test set: {test_set_path.stem}")

            test_data_path = str(test_set_path)
            output_dir = str(meal_manager.get_meal_dir(args.meal))

        llm_preset = args.llm_preset

    sampling_config = None
    sample_modes = [
        ("count", args.sample_count),
        ("pages", args.sample_pages),
        ("ratio", args.sample_ratio),
    ]
    active_modes = [(m, v) for m, v in sample_modes if v is not None]
    if len(active_modes) > 1:
        logger.error(
            "Only one sampling mode can be specified at a time "
            f"(got: {', '.join(m for m, _ in active_modes)})"
        )
        sys.exit(1)
    if active_modes:
        mode, value = active_modes[0]
        sampling_config = SamplingConfig(mode=mode, value=value)

    meal_name_for_pipeline = None
    if args.exp_config:
        meal_name_for_pipeline = exp_config.data.get("meal")
    elif args.meal:
        meal_name_for_pipeline = args.meal

    pipeline = RAGPipeline(
        config_path=args.config,
        llm_preset=llm_preset,
        meal_name=meal_name_for_pipeline,
    )

    if args.exp_config:
        pipeline.config = config

    if not meal_name_for_pipeline:
        collection_info = pipeline.indexer.get_collection_info()
        index_exists = collection_info is not None and collection_info.get(
            "points_count", 0) > 0

        if args.rebuild:
            logger.info("Rebuilding index from scratch...")
            pipeline.build_index(rebuild=True, sampling_config=sampling_config)
            logger.success("Index rebuilt successfully")
        elif args.build_index or not index_exists:
            if not index_exists:
                logger.warning(
                    "Vector index is empty or does not exist. Building index automatically...")
            pipeline.build_index(sampling_config=sampling_config)
            logger.success("Index built successfully")

    metrics_config = None
    generation_metrics_config = None
    llm_config_for_metrics = None

    if args.exp_config and exp_config:
        metrics_config = exp_config.evaluation.get("metrics", {}).get("retrieval")
        generation_metrics_config = exp_config.evaluation.get("metrics", {}).get("generation")

        if generation_metrics_config:
            preset_name = exp_config.evaluation.get("llm_preset", args.llm_preset)
            llm_config_for_metrics = get_llm_config(config, preset_name)

    summary = run_evaluation(
        pipeline=pipeline,
        test_data_path=test_data_path,
        output_dir=output_dir,
        meal_data_id=meal_data_id,
        metrics_config=metrics_config,
        generation_metrics_config=generation_metrics_config,
        llm_config=llm_config_for_metrics,
    )

    pipeline.close()

    print_summary(summary)
