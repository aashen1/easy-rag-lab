import argparse
import sys
from typing import Any, Dict, Optional

from loguru import logger

from src.meal import MealManager, MealStatus, validate_meal_name
from src.pipeline import RAGPipeline
from src.sampler import SamplingConfig
from src.utils import load_config, setup_logger


def main():
    parser = argparse.ArgumentParser(
        description="RAG System - Financial Report Q&A")
    parser.add_argument("--query", type=str, help="Query question")
    parser.add_argument("--build-index", action="store_true",
                        help="Build vector index")
    parser.add_argument(
        "--rebuild", action="store_true", help="Rebuild index from scratch"
    )
    parser.add_argument(
        "--force-parse",
        action="store_true",
        help="Force re-parse PDFs even if output exists",
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
        "--seed", type=int, help="Random seed for sampling and test generation"
    )
    parser.add_argument(
        "--config", type=str, default="config.yaml", help="Config file path"
    )
    parser.add_argument(
        "--llm-preset", type=str, help="LLM preset name (default, opus, sonnet, haiku)"
    )

    meal_group = parser.add_argument_group("Meal (dataset profile) commands")
    meal_group.add_argument(
        "--create-meal", nargs="?", const="__auto__", default=None,
        help="Create a meal with optional name (auto-generated if omitted)"
    )
    meal_group.add_argument(
        "--meal", type=str, help="Use specified meal for Q&A"
    )
    meal_group.add_argument(
        "--list-meals", action="store_true", help="List all meals with status"
    )
    meal_group.add_argument(
        "--meal-info", type=str, help="Show detailed info for a meal"
    )
    meal_group.add_argument(
        "--delete-meal", type=str, help="Delete specified meal"
    )
    meal_group.add_argument(
        "--rename-meal", nargs=2, metavar=("OLD", "NEW"),
        help="Rename a meal"
    )
    meal_group.add_argument(
        "--copy-meal", nargs=2, metavar=("SOURCE", "TARGET"),
        help="Copy a meal (shallow copy, shared vector index)"
    )
    meal_group.add_argument(
        "--repair-meal", type=str, help="Repair an unavailable meal"
    )

    testgen_group = parser.add_argument_group("Test set generation")
    testgen_group.add_argument(
        "--generate-test-set", type=str,
        help="Generate test set for specified meal"
    )
    testgen_group.add_argument(
        "--strategy", type=str, default="factual",
        choices=["factual", "boundary", "multi_hop", "document"],
        help="Test generation strategy (default: factual)"
    )
    testgen_group.add_argument(
        "--num-questions", type=int, default=20,
        help="Number of questions to generate (default: 20)"
    )
    testgen_group.add_argument(
        "--name", type=str, default=None,
        help="Name for the test set (new format)",
    )

    args = parser.parse_args()

    config = load_config(args.config)
    setup_logger(config)

    has_action = (
        args.query
        or args.build_index
        or args.rebuild
        or args.create_meal is not None
        or args.list_meals
        or args.meal_info
        or args.delete_meal
        or args.rename_meal
        or args.copy_meal
        or args.repair_meal
        or args.generate_test_set
        or args.meal
    )

    if not has_action:
        parser.print_help()
        return

    meal_manager = MealManager(config)

    if args.list_meals:
        _handle_list_meals(meal_manager)
        return

    if args.meal_info:
        _handle_meal_info(meal_manager, args.meal_info)
        return

    if args.delete_meal:
        _handle_delete_meal(meal_manager, args.delete_meal)
        return

    if args.rename_meal:
        _handle_rename_meal(
            meal_manager, args.rename_meal[0], args.rename_meal[1])
        return

    if args.copy_meal:
        _handle_copy_meal(meal_manager, args.copy_meal[0], args.copy_meal[1])
        return

    if args.create_meal is not None:
        _handle_create_meal(meal_manager, args)
        return

    if args.repair_meal:
        _handle_repair_meal(meal_manager, args.repair_meal)
        return

    if args.generate_test_set:
        _handle_generate_test_set(meal_manager, config, args)
        return

    if args.build_index or args.rebuild:
        sampling_config = _build_sampling_config(args)
        pipeline = RAGPipeline(config_path=args.config,
                               llm_preset=args.llm_preset)
        pipeline.build_index(
            rebuild=args.rebuild,
            force_parse=args.force_parse,
            sampling_config=sampling_config,
        )
        logger.info("Index built successfully")

    if args.meal:
        pipeline = RAGPipeline(
            config_path=args.config, llm_preset=args.llm_preset, meal_name=args.meal
        )

        status, issues = meal_manager.check_meal_status(args.meal)
        if status != MealStatus.AVAILABLE:
            logger.warning(
                f"Meal '{args.meal}' status: {status.value}. "
                "Some PDFs may be missing or changed."
            )
            for issue in issues:
                logger.warning(f"  {issue}")

        if args.query:
            result = pipeline.query(args.query)
            _print_query_result(result)
        else:
            _interactive_qa(pipeline, args.meal)
    elif args.query:
        pipeline = RAGPipeline(config_path=args.config,
                               llm_preset=args.llm_preset)
        result = pipeline.query(args.query)
        _print_query_result(result)


def _build_sampling_config(args: argparse.Namespace) -> Optional[SamplingConfig]:
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
    return sampling_config


def _handle_meal_info(meal_manager: MealManager, name: str) -> None:
    if not meal_manager.meal_exists(name):
        logger.error(f"Meal '{name}' not found")
        sys.exit(1)

    meal = meal_manager.load_meal(name)
    status, issues = meal_manager.check_meal_status(name)

    print(f"\n{'='*60}")
    print(f"Meal: {meal.name}")
    print(f"{'='*60}")
    print(f"Data ID:       {meal.data_id}")
    print(f"Collection:    {meal.collection_name}")
    print(f"Status:        {status.value}")
    print(f"Created:       {meal.created_at}")

    if meal.config_snapshot:
        print(f"\nConfig Snapshot:")
        for stage, cfg in meal.config_snapshot.items():
            print(f"  {stage}: {cfg}")

    if meal.config_hashes:
        print(f"\nConfig Hashes:")
        for stage, h in meal.config_hashes.items():
            print(f"  {stage}: {h}")

    print(f"\nStats:")
    for k, v in meal.stats.items():
        print(f"  {k}: {v}")

    print(f"\nPDF Files ({len(meal.pdf_files)}):")
    for mf in meal.pdf_files:
        file_path = meal_manager.raw_dir / mf.path
        exists = file_path.exists()
        status_icon = "✅" if exists else "❌"
        print(
            f"  {status_icon} {mf.path}  (sha256: {mf.sha256[:16]}..., size: {mf.size_bytes} bytes)")

    if issues:
        print(f"\nIssues:")
        for issue in issues:
            print(f"  ⚠️ {issue}")

    equivalents = meal_manager.find_equivalent_meals(meal.data_id)
    other_equivalents = [m for m in equivalents if m.name != meal.name]
    if other_equivalents:
        print(f"\nEquivalent meals (same data_id):")
        for eq in other_equivalents:
            print(f"  - {eq.name} (collection: {eq.collection_name})")
    else:
        print(f"\nNo other meals share this data group.")

    print()


def _handle_list_meals(meal_manager: MealManager) -> None:
    meals = meal_manager.list_meals()
    if not meals:
        print("No meals found.")
        return

    from collections import defaultdict
    data_groups = defaultdict(list)
    for meal in meals:
        data_groups[meal.data_id].append(meal)

    print(f"\n{'Name':<20} {'DataID':<14} {'Status':<16} {'PDFs':>5} {'Pages':>7} {'Chunks':>8} {'Config':<20} {'Created'}")
    print("-" * 115)

    for data_id, group_meals in data_groups.items():
        for i, meal in enumerate(group_meals):
            status, issues = meal_manager.check_meal_status(meal.name)
            status_str = status.value
            if status == MealStatus.AVAILABLE:
                status_str = "✅ available"
            elif status == MealStatus.FILES_MISSING:
                status_str = f"⚠️ {len(issues)} missing"
            elif status == MealStatus.FILES_CHANGED:
                status_str = f"❌ {len(issues)} changed"
            elif status == MealStatus.MIXED:
                status_str = f"❌ {len(issues)} issues"

            config_str = ""
            if meal.config_snapshot and "chunker" in meal.config_snapshot:
                cs = meal.config_snapshot["chunker"]
                config_str = f"sz={cs.get('chunk_size', '?')} ov={cs.get('overlap', '?')}"

            data_id_str = data_id[:12]
            if len(group_meals) > 1 and i > 0:
                data_id_str = f"  └─{data_id[:10]}"

            print(
                f"{meal.name:<20} {data_id_str:<14} {status_str:<16} "
                f"{meal.stats.get('total_pdfs', '?'):>5} "
                f"{meal.stats.get('total_pages', '?'):>7} "
                f"{meal.stats.get('total_chunks', '?'):>8} "
                f"{config_str:<20} "
                f"{meal.created_at[:16]}"
            )

        if len(group_meals) > 1:
            print(
                f"  ↳ Same data group ({len(group_meals)} meals share data_id={data_id[:12]})")

    print()


def _handle_delete_meal(meal_manager: MealManager, name: str) -> None:
    if not meal_manager.meal_exists(name):
        logger.error(f"Meal '{name}' not found")
        sys.exit(1)
    meal_manager.delete_meal(name)
    logger.success(f"Meal '{name}' deleted")


def _handle_rename_meal(meal_manager: MealManager, old_name: str, new_name: str) -> None:
    if not validate_meal_name(new_name):
        logger.error(
            f"Invalid meal name '{new_name}'. "
            "Only alphanumeric characters, underscores, and hyphens are allowed."
        )
        sys.exit(1)
    meal_manager.rename_meal(old_name, new_name)


def _handle_copy_meal(meal_manager: MealManager, source: str, target: str) -> None:
    if not validate_meal_name(target):
        logger.error(
            f"Invalid meal name '{target}'. "
            "Only alphanumeric characters, underscores, and hyphens are allowed."
        )
        sys.exit(1)
    meal_manager.copy_meal(source, target)


def _handle_create_meal(meal_manager: MealManager, args: argparse.Namespace) -> None:
    sampling_config = _build_sampling_config(args)
    if sampling_config is None:
        logger.error(
            "Sampling configuration required for meal creation (--sample-count/pages/ratio)")
        sys.exit(1)

    name = args.create_meal
    if name == "__auto__":
        name = None

    try:
        meal = meal_manager.create_meal(
            name=name,
            sampling_config=sampling_config,
            seed=args.seed,
            force_parse=args.force_parse,
        )
        logger.success(
            f"Meal '{meal.name}' created [{meal.data_id[:12]}] "
            f"({meal.stats.get('total_pdfs', 0)} PDFs, "
            f"{meal.stats.get('total_pages', 0)} pages, "
            f"{meal.stats.get('total_chunks', 0)} chunks)"
        )
    except (ValueError, FileNotFoundError) as e:
        logger.error(str(e))
        sys.exit(1)


def _handle_repair_meal(meal_manager: MealManager, name: str) -> None:
    if not meal_manager.meal_exists(name):
        logger.error(f"Meal '{name}' not found")
        sys.exit(1)

    status, issues = meal_manager.check_meal_status(name)
    if status == MealStatus.AVAILABLE:
        logger.info(f"Meal '{name}' is already available, no repair needed")
        return

    print(f"\nMeal '{name}' status check:")
    meal_config = meal_manager.load_meal(name)
    for mf in meal_config.pdf_files:
        file_path = meal_manager.raw_dir / mf.path
        if not file_path.exists():
            print(f"  ❌ {mf.path}  (file not found)")
        else:
            from src.meal import compute_file_sha256
            current = compute_file_sha256(file_path)
            if current == mf.sha256:
                print(f"  ✅ {mf.path}  (SHA256 matches)")
            else:
                print(f"  ⚠️  {mf.path}  (SHA256 mismatch)")

    print("\nOptions:")
    print("1. Specify replacement paths for missing/changed files")
    print("2. Skip problematic files (keep only available ones)")
    print("3. Cancel")

    choice = input("\nSelect option [1-3]: ").strip()
    if choice == "3" or not choice:
        logger.info("Repair cancelled")
        return

    replacements = {}
    if choice == "1":
        for mf in meal_config.pdf_files:
            file_path = meal_manager.raw_dir / mf.path
            if not file_path.exists():
                new_path = input(
                    f"  Replacement for '{mf.path}' (leave empty to skip): "
                ).strip()
                if new_path:
                    replacements[mf.path] = new_path
            else:
                from src.meal import compute_file_sha256
                current = compute_file_sha256(file_path)
                if current != mf.sha256:
                    new_path = input(
                        f"  Replacement for changed '{mf.path}' (leave empty to skip): "
                    ).strip()
                    if new_path:
                        replacements[mf.path] = new_path

    print("\nRepair mode:")
    print("1. Create new meal (original preserved, new data_id)")
    print("2. In-place repair (updates current meal, data_id will change)")

    mode = input("Select mode [1-2]: ").strip()
    create_new = mode != "2"

    new_name = None
    if create_new:
        default_name = f"{name}_repaired"
        new_name = input(
            f"New meal name [{default_name}]: ").strip() or default_name

    try:
        repaired = meal_manager.repair_meal(
            name=name,
            replacements=replacements if replacements else None,
            create_new=create_new,
            new_name=new_name,
        )
        logger.success(
            f"Meal '{repaired.name}' repaired [{repaired.data_id[:12]}] "
            f"({repaired.stats.get('total_pdfs', 0)} PDFs)"
        )
    except (ValueError, FileNotFoundError) as e:
        logger.error(str(e))
        sys.exit(1)


def _handle_generate_test_set(meal_manager: MealManager, config: Dict[str, Any], args: argparse.Namespace) -> None:
    if not meal_manager.meal_exists(args.generate_test_set):
        logger.error(f"Meal '{args.generate_test_set}' not found")
        sys.exit(1)

    from src.test_generator import TestSetGenerator

    generator = TestSetGenerator(config)
    try:
        if args.strategy == "document":
            test_set = generator.generate_document_based_questions(
                meal_name=args.generate_test_set,
                name=getattr(args, 'name', None),
                num_questions=args.num_questions,
                llm_preset=args.llm_preset or "default",
            )
        else:
            test_set = generator.generate_test_set(
                meal_name=args.generate_test_set,
                strategy=args.strategy,
                num_questions=args.num_questions,
                llm_preset=args.llm_preset or "default",
                seed=args.seed,
            )
        logger.success(
            f"Test set '{test_set['name']}' generated for meal '{args.generate_test_set}' "
            f"({len(test_set['questions'])} questions, strategy: {args.strategy})"
        )
    except Exception as e:
        logger.error(f"Failed to generate test set: {str(e)}")
        sys.exit(1)


def _print_query_result(result: Dict[str, Any]) -> None:
    print(f"\n{'='*60}")
    print(f"Question: {result['question']}")
    print(f"{'='*60}")
    print(f"\nAnswer:\n{result['answer']}")
    if "contexts" in result:
        print(f"\n{'='*60}")
        print("Sources:")
        print(f"{'='*60}")
        for i, (source, score) in enumerate(
            zip(result["sources"], result["scores"]), 1
        ):
            print(f"{i}. {source} (relevance: {score:.4f})")
    if "token_usage" in result and result["token_usage"]:
        tu = result["token_usage"]
        print(f"\n{'='*60}")
        print("Token Usage:")
        print(f"{'='*60}")
        print(f"  Input:  {tu['input_tokens']:,}")
        print(f"  Output: {tu['output_tokens']:,}")
        print(f"  Total:  {tu['total_tokens']:,}")
        if tu.get("system_prompt_tokens"):
            print(f"    System Prompt: {tu['system_prompt_tokens']:,}")
            print(f"    Contexts:      {tu['contexts_tokens']:,}")
            print(f"    Query:         {tu['query_tokens']:,}")


def _interactive_qa(pipeline: RAGPipeline, meal_name: str) -> None:
    print(f"\nInteractive Q&A mode (meal: {meal_name})")
    print("Type your question, or 'quit'/'exit'/'q' to exit.\n")

    while True:
        try:
            question = input("Q> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nExiting.")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            tracker = pipeline.token_tracker
            if tracker and tracker.record_count > 0:
                total = tracker.get_total()
                print(
                    f"\nSession Token Usage: in={total.input_tokens:,} out={total.output_tokens:,} total={total.total_tokens:,}")
            print("Exiting.")
            break

        try:
            result = pipeline.query(question)
            print(f"\nA: {result['answer']}")
            if "token_usage" in result and result["token_usage"]:
                tu = result["token_usage"]
                print(
                    f"  Tokens: in={tu['input_tokens']:,} out={tu['output_tokens']:,} total={tu['total_tokens']:,}")
            if "sources" in result:
                sources = result["sources"]
                scores = result["scores"]
                print(f"\n  Sources:")
                for i, (src, sc) in enumerate(zip(sources, scores), 1):
                    print(f"    {i}. {src} ({sc:.4f})")
            print()
        except Exception as e:
            logger.error(f"Query failed: {str(e)}")


if __name__ == "__main__":
    main()
