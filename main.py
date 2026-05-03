import argparse
import sys
from typing import Any

from loguru import logger

from src.case_collector import (
    CASE_TYPE_BAD,
    CASE_TYPE_GOOD,
    convert_case,
    save_case,
)
from src.exceptions import ConfigurationError
from src.meal import MealManager, MealStatus, validate_meal_name
from src.pipeline import RAGPipeline
from src.query_history import QueryHistory
from src.sampler import SamplingConfig
from src.test_set_manager import TestSetManager
from src.utils import load_config, setup_logger


def main() -> None:
    """Entry point for the RAG System CLI.

    Parses command-line arguments and dispatches to the appropriate
    handler functions for index building, meal management, test set
    generation, and interactive Q&A.

    The CLI supports the following main operations:
    - Build/rebuild vector index from PDF documents
    - Create, list, delete, rename, copy, repair, merge, and extend meals
    - Generate test sets with various strategies
    - Run interactive Q&A sessions
    - Execute single queries
    """
    parser = argparse.ArgumentParser(description="RAG System - Financial Report Q&A")
    parser.add_argument("--query", type=str, help="Query question")
    parser.add_argument("--build-index", action="store_true", help="Build vector index")
    parser.add_argument(
        "--rebuild", action="store_true", help="Rebuild index from scratch"
    )
    parser.add_argument(
        "--force-parse",
        action="store_true",
        help="Force re-parse PDFs even if output exists",
    )
    parser.add_argument("--sample-count", type=int, help="Sample N PDFs for testing")
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
        "--interactive",
        action="store_true",
        help="Start interactive Q&A mode (use with or without --meal)",
    )
    parser.add_argument(
        "--llm-preset", type=str, help="LLM preset name (default, opus, sonnet, haiku)"
    )

    meal_group = parser.add_argument_group("Meal (dataset profile) commands")
    meal_group.add_argument(
        "--create-meal",
        nargs="?",
        const="__auto__",
        default=None,
        help="Create a meal with optional name (auto-generated if omitted)",
    )
    meal_group.add_argument("--meal", type=str, help="Use specified meal for Q&A")
    meal_group.add_argument(
        "--list-meals", action="store_true", help="List all meals with status"
    )
    meal_group.add_argument(
        "--meal-info", type=str, help="Show detailed info for a meal"
    )
    meal_group.add_argument("--delete-meal", type=str, help="Delete specified meal")
    meal_group.add_argument(
        "--rename-meal", nargs=2, metavar=("OLD", "NEW"), help="Rename a meal"
    )
    meal_group.add_argument(
        "--copy-meal",
        nargs=2,
        metavar=("SOURCE", "TARGET"),
        help="Copy a meal (shallow copy, shared vector index)",
    )
    meal_group.add_argument(
        "--repair-meal", type=str, help="Repair an unavailable meal"
    )
    meal_group.add_argument(
        "--merge-meals",
        nargs="+",
        metavar="MEAL",
        help="Merge multiple meals into a new meal",
    )
    meal_group.add_argument(
        "--extend-meal", metavar="MEAL", help="Extend a meal by adding new PDF files"
    )
    meal_group.add_argument(
        "--add-pdfs",
        nargs="+",
        metavar="PDF",
        help="PDF files to add (used with --extend-meal)",
    )

    testset_group = parser.add_argument_group("Test set management")
    testset_group.add_argument(
        "--merge-test-sets",
        nargs="+",
        metavar="SPEC",
        help="Merge multiple test sets (format: meal:test_set)",
    )

    testgen_group = parser.add_argument_group("Test set generation")
    testgen_group.add_argument(
        "--generate-test-set", type=str, help="Generate test set for specified meal"
    )
    testgen_group.add_argument(
        "--strategy",
        type=str,
        default="factual",
        choices=["factual", "boundary", "multi_hop", "document", "hybrid", "golden"],
        help="Test generation strategy (default: factual)",
    )
    testgen_group.add_argument(
        "--num-questions",
        type=int,
        default=20,
        help="Number of questions to generate (default: 20)",
    )
    testgen_group.add_argument(
        "--name",
        type=str,
        default=None,
        help="Name for the test set (new format)",
    )

    report_group = parser.add_argument_group("Report generation")
    report_group.add_argument(
        "--llm-report-only",
        type=str,
        metavar="EXP_DIR",
        help="Generate LLM report for a completed experiment directory",
    )

    history_group = parser.add_argument_group("Query history commands")
    history_group.add_argument(
        "--history-list",
        action="store_true",
        help="List recent query history records",
    )
    history_group.add_argument(
        "--history-show",
        type=str,
        metavar="ID",
        help="Show details of a specific history record",
    )
    history_group.add_argument(
        "--history-save",
        type=str,
        metavar="ID",
        help="Save a history record as badcase/goodcase (requires --case-type)",
    )
    history_group.add_argument(
        "--case-type",
        type=str,
        choices=["bad", "good"],
        help="Case type for --history-save (bad or good)",
    )
    history_group.add_argument(
        "--history-limit",
        type=int,
        default=10,
        help="Number of history records to list (default: 10)",
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
        or args.merge_meals
        or args.extend_meal
        or args.merge_test_sets
        or args.meal
        or args.llm_report_only
        or args.interactive
        or args.history_list
        or args.history_show
        or args.history_save
    )

    if not has_action:
        parser.print_help()
        return

    meal_manager = MealManager(config)

    if args.history_list:
        _handle_history_list(config, args.history_limit)
        return

    if args.history_show:
        _handle_history_show(config, args.history_show)
        return

    if args.history_save:
        _handle_history_save(config, args.history_save, args.case_type)
        return

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
        _handle_rename_meal(meal_manager, args.rename_meal[0], args.rename_meal[1])
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

    if args.llm_report_only:
        try:
            from eval.run_experiment import generate_llm_report_only

            generate_llm_report_only(args.llm_report_only, args.config)
        except ConfigurationError as e:
            logger.error(str(e))
            sys.exit(1)
        except Exception as e:
            logger.error(f"Failed to generate LLM report: {str(e)}")
            sys.exit(1)
        return

    if args.merge_meals:
        _handle_merge_meals(meal_manager, args.merge_meals, args.name)
        return

    if args.extend_meal:
        if not args.add_pdfs:
            logger.error("--add-pdfs is required when using --extend-meal")
            sys.exit(1)
        _handle_extend_meal(meal_manager, args.extend_meal, args.add_pdfs, args.name)
        return

    if args.merge_test_sets:
        if not args.meal:
            logger.error("--meal is required when using --merge-test-sets")
            sys.exit(1)
        _handle_merge_test_sets(
            meal_manager, config, args.merge_test_sets, args.meal, args.name
        )
        return

    if args.build_index or args.rebuild:
        sampling_config = _build_sampling_config(args)
        if sampling_config is not None:
            pipeline = RAGPipeline(config=args.config, llm_preset=args.llm_preset)
            pipeline.build_index(
                rebuild=args.rebuild,
                force_parse=args.force_parse,
                sampling_config=sampling_config,
            )
            logger.info("Index built successfully (sampled, not linked to a meal)")
        else:
            resolved_meal = _resolve_meal_name(meal_manager, args)
            if resolved_meal:
                _handle_rebuild_meal(meal_manager, resolved_meal, args)
                logger.info("Index built successfully via meal system")
            else:
                logger.error("No PDFs found and no meal available. Cannot build index.")
                sys.exit(1)

    needs_meal = args.query or args.interactive
    resolved_meal = _resolve_meal_name(meal_manager, args) if needs_meal else None

    if resolved_meal:
        pipeline = RAGPipeline(
            config=args.config, llm_preset=args.llm_preset, meal_name=resolved_meal
        )

        status, issues = meal_manager.check_meal_status(resolved_meal)
        if status != MealStatus.AVAILABLE:
            logger.warning(
                f"Meal '{resolved_meal}' status: {status.value}. "
                "Some PDFs may be missing or changed."
            )
            for issue in issues:
                logger.warning(f"  {issue}")

        if args.query:
            result = pipeline.query(args.query)
            _print_query_result(result)
            history_cfg = config.get("query_history", {})
            history = QueryHistory(
                max_entries=history_cfg.get("max_entries", 10),
                history_dir=history_cfg.get("dir"),
            )
            record_id = history.add(
                question=args.query,
                result=result,
                meal_name=resolved_meal,
                llm_preset=args.llm_preset,
                config_overrides={},
            )
            print(f"\n📝 已记录到历史 (ID: {record_id})")
        elif args.interactive:
            _interactive_qa(pipeline, resolved_meal)
    elif needs_meal:
        logger.error(
            "No meal available. Create one with --create-meal or add PDFs to data/raw/."
        )
        sys.exit(1)


def _build_sampling_config(args: argparse.Namespace) -> SamplingConfig | None:
    """Build a SamplingConfig from command-line arguments.

    Checks for sample-count, sample-pages, and sample-ratio arguments.
    Only one sampling mode can be specified at a time.

    Args:
        args: Parsed command-line arguments.

    Returns:
        SamplingConfig if a sampling mode is specified, None otherwise.

    Raises:
        SystemExit: If multiple sampling modes are specified.
    """
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


def _resolve_meal_name(
    meal_manager: MealManager, args: argparse.Namespace
) -> str | None:
    """Resolve the meal name to use for query/interactive/build-index.

    Priority:
      1. Explicit --meal argument
      2. Auto-resolve to the default full-dataset meal (get_or_create_full_meal)

    Args:
        meal_manager: MealManager instance for meal operations.
        args: Parsed command-line arguments.

    Returns:
        Meal name string, or None if no meal can be resolved.
    """
    if args.meal:
        return args.meal

    try:
        meal = meal_manager.get_or_create_full_meal()
        logger.info(f"No --meal specified, auto-resolved to meal '{meal.name}'")
        return meal.name
    except Exception as e:
        logger.error(f"Failed to auto-resolve default meal: {e}")
        return None


def _handle_rebuild_meal(
    meal_manager: MealManager, meal_name: str, args: argparse.Namespace
) -> None:
    """Rebuild a meal's index through the meal system.

    If --rebuild is specified, deletes and recreates the meal.
    Otherwise, ensures the meal exists and is up-to-date.

    Args:
        meal_manager: MealManager instance for meal operations.
        meal_name: Name of the meal to rebuild or ensure.
        args: Parsed command-line arguments.
    """
    if args.rebuild and meal_manager.meal_exists(meal_name):
        logger.info(f"Rebuilding meal '{meal_name}' from scratch...")
        meal_manager.delete_meal(meal_name)

    if not meal_manager.meal_exists(meal_name):
        meal_manager.get_or_create_full_meal(
            name=meal_name,
            force_parse=args.force_parse,
        )
    else:
        logger.info(f"Meal '{meal_name}' already exists, index is ready")


def _handle_meal_info(meal_manager: MealManager, name: str) -> None:
    """Display detailed information about a meal.

    Prints meal metadata, config snapshot, file list with status,
    and any issues detected.

    Args:
        meal_manager: MealManager instance for meal operations.
        name: Name of the meal to display.

    Raises:
        SystemExit: If the meal does not exist.
    """
    if not meal_manager.meal_exists(name):
        logger.error(f"Meal '{name}' not found")
        sys.exit(1)

    meal = meal_manager.load_meal(name)
    status, issues = meal_manager.check_meal_status(name)

    print(f"\n{'=' * 60}")
    print(f"Meal: {meal.name}")
    print(f"{'=' * 60}")
    print(f"Data ID:       {meal.data_id}")
    print(f"Collection:    {meal.collection_name}")
    print(f"Status:        {status.value}")
    print(f"Created:       {meal.created_at}")

    if meal.config_snapshot:
        print("\nConfig Snapshot:")
        for stage, cfg in meal.config_snapshot.items():
            print(f"  {stage}: {cfg}")

    if meal.config_hashes:
        print("\nConfig Hashes:")
        for stage, h in meal.config_hashes.items():
            print(f"  {stage}: {h}")

    print("\nStats:")
    for k, v in meal.stats.items():
        print(f"  {k}: {v}")

    print(f"\nPDF Files ({len(meal.pdf_files)}):")
    for mf in meal.pdf_files:
        file_path = meal_manager.raw_dir / mf.path
        exists = file_path.exists()
        status_icon = "✅" if exists else "❌"
        print(
            f"  {status_icon} {mf.path}  (sha256: {mf.sha256[:16]}..., size: {mf.size_bytes} bytes)"
        )

    if issues:
        print("\nIssues:")
        for issue in issues:
            print(f"  ⚠️ {issue}")

    equivalents = meal_manager.find_equivalent_meals(meal.data_id)
    other_equivalents = [m for m in equivalents if m.name != meal.name]
    if other_equivalents:
        print("\nEquivalent meals (same data_id):")
        for eq in other_equivalents:
            print(f"  - {eq.name} (collection: {eq.collection_name})")
    else:
        print("\nNo other meals share this data group.")

    print()


def _handle_list_meals(meal_manager: MealManager) -> None:
    """List all meals grouped by data_id.

    Prints a table showing meal name, data_id, status, PDF count,
    page count, chunk count, config, and creation date. Meals with
    the same data_id are grouped together.

    Args:
        meal_manager: MealManager instance for meal operations.
    """
    meals = meal_manager.list_meals()
    if not meals:
        print("No meals found.")
        return

    from collections import defaultdict

    data_groups = defaultdict(list)
    for meal in meals:
        data_groups[meal.data_id].append(meal)

    print(
        f"\n{'Name':<20} {'DataID':<14} {'Status':<16} {'PDFs':>5} {'Pages':>7} {'Chunks':>8} {'Config':<20} {'Created'}"
    )
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
                config_str = (
                    f"sz={cs.get('chunk_size', '?')} ov={cs.get('overlap', '?')}"
                )

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
                f"  ↳ Same data group ({len(group_meals)} meals share data_id={data_id[:12]})"
            )

    print()


def _handle_delete_meal(meal_manager: MealManager, name: str) -> None:
    """Delete a meal by name.

    Args:
        meal_manager: MealManager instance for meal operations.
        name: Name of the meal to delete.

    Raises:
        SystemExit: If the meal does not exist.
    """
    if not meal_manager.meal_exists(name):
        logger.error(f"Meal '{name}' not found")
        sys.exit(1)
    meal_manager.delete_meal(name)
    logger.success(f"Meal '{name}' deleted")


def _handle_rename_meal(
    meal_manager: MealManager, old_name: str, new_name: str
) -> None:
    """Rename a meal.

    Args:
        meal_manager: MealManager instance for meal operations.
        old_name: Current name of the meal.
        new_name: New name for the meal.

    Raises:
        SystemExit: If the new name is invalid.
    """
    if not validate_meal_name(new_name):
        logger.error(
            f"Invalid meal name '{new_name}'. "
            "Only alphanumeric characters, underscores, and hyphens are allowed."
        )
        sys.exit(1)
    meal_manager.rename_meal(old_name, new_name)


def _handle_copy_meal(meal_manager: MealManager, source: str, target: str) -> None:
    """Create a shallow copy of a meal.

    The copy shares the same vector index as the source meal.

    Args:
        meal_manager: MealManager instance for meal operations.
        source: Name of the source meal to copy.
        target: Name for the new meal copy.

    Raises:
        SystemExit: If the target name is invalid.
    """
    if not validate_meal_name(target):
        logger.error(
            f"Invalid meal name '{target}'. "
            "Only alphanumeric characters, underscores, and hyphens are allowed."
        )
        sys.exit(1)
    meal_manager.copy_meal(source, target)


def _handle_create_meal(meal_manager: MealManager, args: argparse.Namespace) -> None:
    """Create a new meal from sampled PDF files.

    Requires a sampling configuration (--sample-count/pages/ratio).

    Args:
        meal_manager: MealManager instance for meal operations.
        args: Parsed command-line arguments containing sampling config
            and optional meal name.

    Raises:
        SystemExit: If sampling config is missing or creation fails.
    """
    sampling_config = _build_sampling_config(args)
    if sampling_config is None:
        logger.error(
            "Sampling configuration required for meal creation (--sample-count/pages/ratio)"
        )
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
    """Interactively repair a meal with missing or changed files.

    Displays file status, prompts for replacement paths, and offers
    options to create a new meal or repair in-place.

    Args:
        meal_manager: MealManager instance for meal operations.
        name: Name of the meal to repair.

    Raises:
        SystemExit: If the meal does not exist or repair fails.
    """
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
        new_name = input(f"New meal name [{default_name}]: ").strip() or default_name

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


def _handle_generate_test_set(
    meal_manager: MealManager, config: dict[str, Any], args: argparse.Namespace
) -> None:
    """Generate a test set for a specified meal.

    Supports multiple strategies: factual, boundary, multi_hop, document,
    hybrid, and golden.

    Args:
        meal_manager: MealManager instance for meal operations.
        config: Configuration dictionary.
        args: Parsed command-line arguments containing meal name, strategy,
            num_questions, and optional name.

    Raises:
        SystemExit: If the meal does not exist or generation fails.
    """
    from src.test_generator import TestSetGenerator

    generator = TestSetGenerator(config)
    try:
        if args.strategy == "golden":
            test_set = generator.generate_golden_testset(
                num_questions=args.num_questions or 150,
                name=getattr(args, "name", None) or "golden_150",
                llm_preset=args.llm_preset or "default",
                seed=getattr(args, "seed", None),
            )
        elif args.strategy == "document":
            if not meal_manager.meal_exists(args.generate_test_set):
                logger.error(f"Meal '{args.generate_test_set}' not found")
                sys.exit(1)
            test_set = generator.generate_document_based_questions(
                meal_name=args.generate_test_set,
                name=getattr(args, "name", None),
                num_questions=args.num_questions,
                llm_preset=args.llm_preset or "default",
            )
        elif args.strategy == "hybrid":
            if not meal_manager.meal_exists(args.generate_test_set):
                logger.error(f"Meal '{args.generate_test_set}' not found")
                sys.exit(1)
            test_set = generator.generate_hybrid_questions(
                meal_name=args.generate_test_set,
                name=getattr(args, "name", None),
                num_questions=args.num_questions,
                llm_preset=args.llm_preset or "default",
            )
        else:
            if not meal_manager.meal_exists(args.generate_test_set):
                logger.error(f"Meal '{args.generate_test_set}' not found")
                sys.exit(1)
            test_set = generator.generate_test_set(
                meal_name=args.generate_test_set,
                strategy=args.strategy,
                num_questions=args.num_questions,
                llm_preset=args.llm_preset or "default",
                seed=args.seed,
            )
        test_set_name = test_set.get("name") or test_set.get("metadata", {}).get(
            "name", "unknown"
        )
        logger.success(
            f"Test set '{test_set_name}' generated for meal '{args.generate_test_set}' "
            f"({len(test_set['questions'])} questions, strategy: {args.strategy})"
        )
    except Exception as e:
        logger.error(f"Failed to generate test set: {str(e)}")
        sys.exit(1)


def _handle_history_list(config: dict[str, Any], limit: int) -> None:
    """List recent query history records.

    Args:
        config: Configuration dictionary.
        limit: Maximum number of records to display.
    """
    history_cfg = config.get("query_history", {})
    history = QueryHistory(
        max_entries=history_cfg.get("max_entries", 10),
        history_dir=history_cfg.get("dir"),
    )
    records = history.list_recent(limit=limit)

    if not records:
        print("📝 暂无查询历史记录")
        return

    print(f"\n📝 最近 {len(records)} 条问答记录：")
    print("─" * 70)
    print(f"{'ID':<10} {'时间':<20} {'问题预览':<28} {'状态'}")
    print("─" * 70)

    for rec in records:
        rid = rec.get("id", "")
        ts = rec.get("timestamp", "")
        time_str = ts[5:19] if len(ts) >= 19 else ts
        question = rec.get("question", "")
        preview = question[:24] + "..." if len(question) > 24 else question
        saved = rec.get("saved_case_type")
        if saved == CASE_TYPE_BAD:
            status = "🚨 bad"
        elif saved == CASE_TYPE_GOOD:
            status = "✅ good"
        else:
            status = "—"
        print(f"{rid:<10} {time_str:<20} {preview:<28} {status}")

    print("─" * 70)
    print("使用 --history-save <id> --case-type bad|good 保存为 case\n")


def _handle_history_show(config: dict[str, Any], record_id: str) -> None:
    """Show details of a specific history record.

    Args:
        config: Configuration dictionary.
        record_id: The history record ID to display.
    """
    history_cfg = config.get("query_history", {})
    history = QueryHistory(
        max_entries=history_cfg.get("max_entries", 10),
        history_dir=history_cfg.get("dir"),
    )
    record = history.get(record_id)

    if record is None:
        print(f"❌ 未找到记录: {record_id}")
        return

    print(f"\n📝 历史记录详情 — {record_id}")
    print("─" * 50)
    print(f"时间:     {record.get('timestamp', '')}")
    print(f"问题:     {record.get('question', '')}")
    print(f"Meal:     {record.get('meal_name', '—')}")
    print(f"LLM预设:  {record.get('llm_preset', '—')}")
    saved = record.get("saved_case_type")
    if saved == CASE_TYPE_BAD:
        print(f"状态:     🚨 Badcase ({record.get('saved_case_id', '')})")
    elif saved == CASE_TYPE_GOOD:
        print(f"状态:     ✅ Goodcase ({record.get('saved_case_id', '')})")
    else:
        print("状态:     未保存")

    query_result = record.get("query_result")
    if query_result:
        answer = query_result.get("answer", "")
        print(f"\n回答:     {answer}")

        sources = query_result.get("sources", [])
        scores = query_result.get("scores", [])
        if sources:
            print("\n参考来源：")
            for i, (src, score) in enumerate(
                zip(sources[:3], scores[:3], strict=False), 1
            ):
                src_name = src.split("\\")[-1] if "\\" in src else src
                print(f"   {i}. {src_name} (相关度: {score:.4f})")

        tu = query_result.get("token_usage")
        if tu:
            print(
                f"\nToken: in={tu['input_tokens']:,} out={tu['output_tokens']:,} "
                f"total={tu['total_tokens']:,}"
            )

    print("─" * 50)


def _handle_history_save(
    config: dict[str, Any], record_id: str, case_type: str | None
) -> None:
    """Save a history record as a badcase or goodcase.

    Implements deduplication and type conversion logic:
    - Same type already saved → reject with message
    - Different type already saved → convert (delete old, create new)
    - Not saved yet → create new case

    Args:
        config: Configuration dictionary.
        record_id: The history record ID to save.
        case_type: ``"bad"`` or ``"good"``.
    """
    if case_type is None:
        print("❌ 必须指定 --case-type bad 或 --case-type good")
        return

    history_cfg = config.get("query_history", {})
    history = QueryHistory(
        max_entries=history_cfg.get("max_entries", 10),
        history_dir=history_cfg.get("dir"),
    )
    record = history.get(record_id)

    if record is None:
        print(f"❌ 未找到记录: {record_id}")
        return

    saved_type, saved_case_id = history.check_saved(record_id)

    if saved_type == case_type:
        label = "Badcase" if case_type == CASE_TYPE_BAD else "Goodcase"
        icon = "🚨" if case_type == CASE_TYPE_BAD else "✅"
        print(f"{icon} 该记录已标记为 {label}，无需重复保存")
        return

    query_result = record.get("query_result")
    if query_result is None:
        print(f"❌ 记录 {record_id} 的查询结果文件缺失")
        return

    question = query_result.get("question", "")
    meal_name = record.get("meal_name")

    if saved_type is not None and saved_case_id is not None:
        try:
            new_dir = convert_case(saved_case_id, case_type)
            history.mark_saved(record_id, case_type, new_dir.name)
            old_label = "Badcase" if saved_type == CASE_TYPE_BAD else "Goodcase"
            new_label = "Badcase" if case_type == CASE_TYPE_BAD else "Goodcase"
            new_icon = "🚨" if case_type == CASE_TYPE_BAD else "✅"
            print(
                f"{new_icon} 已将 {old_label} 转换为 {new_label}: {new_dir.name}\n"
                f"   原 {old_label} ({saved_case_id}) 已删除"
            )
        except Exception as e:
            logger.error(f"Failed to convert case: {e}")
            print(f"❌ 转换失败: {e}")
        return

    try:
        base_config = load_config()
        case_dir = save_case(
            case_type=case_type,
            question=question,
            result=query_result,
            config_overrides=record.get("config_overrides", {}),
            base_config=base_config,
            meal_config=None,
            meal_name=meal_name,
        )
        history.mark_saved(record_id, case_type, case_dir.name)
        icon = "🚨" if case_type == CASE_TYPE_BAD else "✅"
        label = "Badcase" if case_type == CASE_TYPE_BAD else "Goodcase"
        print(f"{icon} {label} 已保存: {case_dir.name}")
    except Exception as e:
        logger.error(f"Failed to save case: {e}")
        print(f"❌ 保存失败: {e}")


def _print_query_result(result: dict[str, Any]) -> None:
    """Print a formatted query result to stdout.

    Displays the question, answer, sources with relevance scores,
    and token usage breakdown.

    Args:
        result: Query result dictionary containing 'question', 'answer',
            and optionally 'sources', 'scores', 'token_usage'.
    """
    print(f"\n{'=' * 60}")
    print(f"Question: {result['question']}")
    print(f"{'=' * 60}")
    print(f"\nAnswer:\n{result['answer']}")
    if "contexts" in result:
        print(f"\n{'=' * 60}")
        print("Sources:")
        print(f"{'=' * 60}")
        for i, (source, score) in enumerate(
            zip(result["sources"], result["scores"], strict=False), 1
        ):
            print(f"{i}. {source} (relevance: {score:.4f})")
    if "token_usage" in result and result["token_usage"]:
        tu = result["token_usage"]
        print(f"\n{'=' * 60}")
        print("Token Usage:")
        print(f"{'=' * 60}")
        print(f"  Input:  {tu['input_tokens']:,}")
        print(f"  Output: {tu['output_tokens']:,}")
        print(f"  Total:  {tu['total_tokens']:,}")
        if tu.get("system_prompt_tokens"):
            print(f"    System Prompt: {tu['system_prompt_tokens']:,}")
            print(f"    Contexts:      {tu['contexts_tokens']:,}")
            print(f"    Query:         {tu['query_tokens']:,}")


def _interactive_qa(pipeline: RAGPipeline, meal_name: str | None = None) -> None:
    """Run an interactive Q&A session.

    Continuously prompts for questions and displays answers until
    the user types 'quit' or 'exit'. Tracks and displays token usage
    on exit. Supports ``/badcase`` and ``/goodcase`` commands to save
    the last query result for reproducibility.

    Args:
        pipeline: RAGPipeline instance for query execution.
        meal_name: Optional meal name to display in the welcome message.
    """
    collection_info = pipeline.indexer.get_collection_info()
    if meal_name:
        print(f"\n🤖 RAG 问答系统已启动（meal: {meal_name}）")
    else:
        print("\n🤖 RAG 问答系统已启动")

    if collection_info:
        chunks_count = collection_info.get("points_count", 0)
        print(f"📝 数据库中已有 {chunks_count} 个文档片段")
    else:
        print(
            "⚠️  数据库为空，请先构建索引：pixi run python main.py --build-index --meal <name>"
        )

    print("输入 'quit' 或 'exit' 退出")
    print("输入 '/badcase' 或 '/goodcase' 保存最近一次查询\n")

    last_result: dict[str, Any] | None = None
    last_config_overrides: dict[str, Any] | None = None
    last_saved_type: str | None = None
    last_saved_case_id: str | None = None

    while True:
        try:
            question = input("💬 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！\n")
            break

        if not question:
            continue
        if question.lower() in ("quit", "exit", "q"):
            tracker = pipeline.token_tracker
            if tracker and tracker.record_count > 0:
                total = tracker.get_total()
                print(
                    f"\n📊 Session Token Usage: in={total.input_tokens:,} "
                    f"out={total.output_tokens:,} total={total.total_tokens:,}"
                )
            print("👋 再见！\n")
            break

        if question.lower() in ("/badcase", "/goodcase"):
            if last_result is None:
                print("⚠️  还没有查询记录，请先提问\n")
                continue
            case_type = (
                CASE_TYPE_BAD if question.lower() == "/badcase" else CASE_TYPE_GOOD
            )
            icon = "🚨" if case_type == CASE_TYPE_BAD else "✅"
            label = "Badcase" if case_type == CASE_TYPE_BAD else "Goodcase"

            if last_saved_type == case_type:
                print(f"{icon} 已标记为 {label}，无需重复保存\n")
                continue

            try:
                base_config = load_config()
                meal_config = getattr(pipeline, "meal_config", None)

                if last_saved_type is not None and last_saved_case_id is not None:
                    new_dir = convert_case(last_saved_case_id, case_type)
                    old_label = (
                        "Badcase" if last_saved_type == CASE_TYPE_BAD else "Goodcase"
                    )
                    print(
                        f"{icon} 已将 {old_label} 转换为 {label}: {new_dir.name}\n"
                        f"   原 {old_label} ({last_saved_case_id}) 已删除\n"
                    )
                    last_saved_type = case_type
                    last_saved_case_id = new_dir.name
                else:
                    case_dir = save_case(
                        case_type=case_type,
                        question=last_result.get("question", ""),
                        result=last_result,
                        config_overrides=last_config_overrides or {},
                        base_config=base_config,
                        meal_config=meal_config,
                        meal_name=meal_name,
                    )
                    print(f"{icon} {label} 已保存: {case_dir.name}\n")
                    last_saved_type = case_type
                    last_saved_case_id = case_dir.name
            except Exception as e:
                logger.error(f"Failed to save case: {e}")
                print(f"❌ 保存失败: {e}\n")
            continue

        try:
            result = pipeline.query(question)
            last_result = result
            last_config_overrides = None
            last_saved_type = None
            last_saved_case_id = None
            print(f"\n🤖 Assistant: {result['answer']}\n")

            if "token_usage" in result and result["token_usage"]:
                tu = result["token_usage"]
                print(
                    f"📊 Tokens: in={tu['input_tokens']:,} out={tu['output_tokens']:,} "
                    f"total={tu['total_tokens']:,}\n"
                )

            if "sources" in result and result["sources"]:
                print("📚 参考来源：")
                for i, (source, score) in enumerate(
                    zip(result["sources"][:3], result["scores"][:3], strict=False), 1
                ):
                    source_name = source.split("\\")[-1] if "\\" in source else source
                    print(f"   {i}. {source_name} (相关度: {score:.4f})")
                print()
        except Exception as e:
            logger.error(f"Error processing query: {str(e)}")
            print(f"\n❌ 处理问题时出错: {str(e)}\n")


def _handle_merge_meals(
    meal_manager: MealManager, meal_names: list[str], name: str | None
) -> None:
    """Merge multiple meals into a new meal.

    Combines PDFs from all source meals, deduplicates by SHA256,
    and creates a new meal with a new data_id.

    Args:
        meal_manager: MealManager instance for meal operations.
        meal_names: List of meal names to merge.
        name: Optional name for the new merged meal.

    Raises:
        SystemExit: If merge fails.
    """
    try:
        meal = meal_manager.merge_meals(meal_names, name=name)
        composition = meal.composition or {}
        dedup_info = composition.get("dedup_info", {})
        sources = composition.get("sources", [])

        logger.success(
            f"Meal '{meal.name}' created successfully by merging {len(meal_names)} meals"
        )
        print(f"\n  Total PDFs: {meal.stats.get('total_pdfs', 0)}", end="")
        if dedup_info.get("duplicates", 0) > 0:
            print(f" (duplicates removed: {dedup_info['duplicates']})")
        else:
            print()

        if sources:
            print("  Sources:")
            for src in sources:
                print(f"    - {src['meal']} ({src['pdf_count']} PDFs)")

        print()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)


def _handle_extend_meal(
    meal_manager: MealManager,
    source_meal: str,
    new_pdfs: list[str],
    name: str | None,
) -> None:
    """Extend a meal by adding new PDF files.

    Creates a new meal containing all PDFs from the source meal
    plus the newly added PDFs.

    Args:
        meal_manager: MealManager instance for meal operations.
        source_meal: Name of the source meal to extend.
        new_pdfs: List of paths to new PDF files to add.
        name: Optional name for the new extended meal.

    Raises:
        SystemExit: If extension fails.
    """
    try:
        meal = meal_manager.extend_meal(source_meal, new_pdfs, name=name)
        composition = meal.composition or {}
        added_files = composition.get("added_files", [])
        skipped_files = composition.get("skipped_files", [])

        logger.success(
            f"Meal '{meal.name}' created successfully by extending '{source_meal}'"
        )
        print(f"\n  Total PDFs: {meal.stats.get('total_pdfs', 0)}")
        print(f"  Added: {len(added_files)} new PDFs")
        if skipped_files:
            print(f"  Skipped (duplicates): {len(skipped_files)}")
        print()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)


def _handle_merge_test_sets(
    meal_manager: MealManager,
    config: dict[str, Any],
    source_specs: list[str],
    target_meal: str,
    name: str | None,
) -> None:
    """Merge multiple test sets into a new test set.

    Source specs should be in the format "meal:test_set".

    Args:
        meal_manager: MealManager instance for meal operations.
        config: Configuration dictionary.
        source_specs: List of source specs in "meal:test_set" format.
        target_meal: Name of the meal to associate the merged test set with.
        name: Optional name for the new merged test set.

    Raises:
        SystemExit: If the target meal does not exist or merge fails.
    """
    if not meal_manager.meal_exists(target_meal):
        logger.error(f"Target meal '{target_meal}' not found")
        sys.exit(1)

    parsed_specs = []
    for spec in source_specs:
        if ":" not in spec:
            logger.error(f"Invalid test set spec '{spec}'. Format: meal:test_set")
            sys.exit(1)
        parts = spec.split(":", 1)
        parsed_specs.append({"meal": parts[0], "test_set": parts[1]})

    target_meal_config = meal_manager.load_meal(target_meal)

    test_set_manager = TestSetManager(config)
    try:
        result = test_set_manager.merge_test_sets(
            source_specs=parsed_specs,
            target_meal_name=target_meal,
            target_meal_config=target_meal_config,
            name=name,
        )
        composition = result["metadata"].get("composition", {})
        dedup_count = composition.get("dedup_count", 0)
        final_count = composition.get("final_count", 0)
        sources = composition.get("sources", [])

        logger.success(
            f"Test set '{result['metadata']['name']}' created by merging {len(sources)} test sets"
        )
        print(f"\n  Total questions: {final_count}")
        if dedup_count > 0:
            print(f"  Duplicates removed: {dedup_count}")
        print("  Sources:")
        for src in sources:
            print(f"    - {src['meal']}:{src['test_set']}")
        print()
    except ValueError as e:
        logger.error(str(e))
        sys.exit(1)


if __name__ == "__main__":
    main()
