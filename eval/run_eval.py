import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(project_root))

from src.utils import load_config, setup_logger
from src.pipeline import RAGPipeline
from src.sampler import SamplingConfig
from src.meal import MealManager, MealStatus
from eval.metrics import calculate_hit_rate, calculate_mrr, calculate_ndcg
from loguru import logger
import json
import random
import time
from datetime import datetime
from typing import Any, Dict, List


def run_evaluation(
    pipeline: RAGPipeline,
    test_data_path: str,
    output_dir: str,
    sample_size: int = None,
    meal_data_id: str = None,
) -> Dict[str, Any]:
    test_data_path = Path(test_data_path)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    with open(test_data_path, "r", encoding="utf-8") as f:
        test_cases = json.load(f)

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

            hit_rate = calculate_hit_rate(
                retrieved_sources, test_case.get("expected_sources", [])
            )
            mrr = calculate_mrr(
                retrieved_sources, test_case.get("expected_sources", [])
            )
            ndcg = calculate_ndcg(
                retrieved_sources, test_case.get("expected_sources", []), k=5
            )

            result = {
                "id": test_case["id"],
                "question": test_case["question"],
                "answer": response["answer"],
                "retrieval": {
                    "hit_rate": hit_rate,
                    "mrr": mrr,
                    "ndcg": ndcg,
                },
                "sources": retrieved_sources,
                "time_seconds": case_time,
            }

            logger.success(
                f"Test case {test_case['id']}: HR={hit_rate:.2f}, MRR={mrr:.2f}, NDCG={ndcg:.2f} ({case_time:.2f}s)"
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

    retrieval_metrics = {
        "avg_hit_rate": sum(r["retrieval"]["hit_rate"] for r in results if "retrieval" in r)
        / len([r for r in results if "retrieval" in r])
        if [r for r in results if "retrieval" in r]
        else 0,
        "avg_mrr": sum(r["retrieval"]["mrr"] for r in results if "retrieval" in r)
        / len([r for r in results if "retrieval" in r])
        if [r for r in results if "retrieval" in r]
        else 0,
        "avg_ndcg": sum(r["retrieval"]["ndcg"] for r in results if "retrieval" in r)
        / len([r for r in results if "retrieval" in r])
        if [r for r in results if "retrieval" in r]
        else 0,
    }

    summary = {
        "timestamp": datetime.now().isoformat(),
        "meal_data_id": meal_data_id,
        "total_test_cases": len(test_cases),
        "total_time_seconds": total_time,
        "avg_time_per_case": total_time / len(test_cases),
        "retrieval_metrics": retrieval_metrics,
        "results": results,
    }

    output_file = output_dir / "baseline_report.json"
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.success(f"Evaluation completed in {total_time:.2f}s")
    logger.success(f"Report saved to: {output_file}")

    return summary


def print_summary(summary: Dict[str, Any]) -> None:
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
    print(f"  Hit Rate: {summary['retrieval_metrics']['avg_hit_rate']:.4f}")
    print(f"  MRR:      {summary['retrieval_metrics']['avg_mrr']:.4f}")
    print(f"  NDCG:     {summary['retrieval_metrics']['avg_ndcg']:.4f}")
    print("=" * 60)


if __name__ == "__main__":
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

    args = parser.parse_args()

    config = load_config(args.config)
    setup_logger(config)

    meal_data_id = None
    test_data_path = args.test_data
    output_dir = args.output_dir

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
            jsonl_files = sorted(test_sets_dir.glob("*.json")) if test_sets_dir.exists() else []
            if not jsonl_files:
                logger.error(
                    f"No test sets found for meal '{args.meal}'. "
                    "Generate one with: python main.py --generate-test-set {args.meal}"
                )
                sys.exit(1)
            test_set_path = jsonl_files[0]
            logger.info(f"Using test set: {test_set_path.stem}")

        test_data_path = str(test_set_path)
        output_dir = str(meal_manager.get_meal_dir(args.meal))

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

    pipeline = RAGPipeline(
        config_path=args.config,
        llm_preset=args.llm_preset,
        meal_name=args.meal,
    )

    if not args.meal:
        collection_info = pipeline.indexer.get_collection_info()
        index_exists = collection_info is not None and collection_info.get("points_count", 0) > 0

        if args.rebuild:
            logger.info("Rebuilding index from scratch...")
            pipeline.build_index(rebuild=True, sampling_config=sampling_config)
            logger.success("Index rebuilt successfully")
        elif args.build_index or not index_exists:
            if not index_exists:
                logger.warning("Vector index is empty or does not exist. Building index automatically...")
            pipeline.build_index(sampling_config=sampling_config)
            logger.success("Index built successfully")

    summary = run_evaluation(
        pipeline=pipeline,
        test_data_path=test_data_path,
        output_dir=output_dir,
        meal_data_id=meal_data_id,
    )

    print_summary(summary)
