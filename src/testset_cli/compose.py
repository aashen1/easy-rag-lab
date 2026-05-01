from __future__ import annotations

import json
from pathlib import Path

from loguru import logger

from src.testset_composer import TestSetComposer


def run_compose(args) -> int:
    composer = TestSetComposer()

    if args.subcommand == "merge":
        return _run_merge(args, composer)
    elif args.subcommand == "filter":
        return _run_filter(args, composer)
    elif args.subcommand == "incremental":
        return _run_incremental(args, composer)

    logger.error(f"Unknown compose subcommand: {args.subcommand}")
    return 1


def _load_test_set(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _save_test_set(data: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    logger.success(f"Saved to {output_path}")


def _run_merge(args, composer: TestSetComposer) -> int:
    sources = []
    for spec in args.sources:
        try:
            meal, test_name = spec.split(":", 1)
        except ValueError:
            meal = ""
            test_name = spec

        meal_dir = Path(args.data_dir) / meal if meal else Path(args.data_dir)
        test_path = meal_dir / "test_sets" / f"{test_name}.json"

        if not test_path.exists():
            test_path = Path(test_name)

        if not test_path.exists():
            logger.error(f"Source test set not found: {test_path}")
            return 1

        sources.append(_load_test_set(test_path))

    result = composer.compose_merge(
        sources=sources,
        name=args.name,
        meal_id=args.meal if hasattr(args, "meal") else "",
    )

    output_dir = (
        Path(args.data_dir) / args.meal / "test_sets"
        if hasattr(args, "meal") and args.meal
        else Path(args.data_dir) / "test_sets"
    )
    output_path = output_dir / f"{args.name}.json"
    _save_test_set(result, output_path)

    logger.info(
        f"Merged {len(sources)} sources into {len(result['questions'])} questions"
    )
    return 0


def _run_filter(args, composer: TestSetComposer) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Input test set not found: {input_path}")
        return 1

    test_set = _load_test_set(input_path)

    question_types = args.question_type.split(",") if args.question_type else None
    categories = args.category.split(",") if args.category else None
    difficulties = args.difficulty.split(",") if args.difficulty else None
    review_statuses = args.review_status.split(",") if args.review_status else None

    result = composer.compose_filter(
        test_set=test_set,
        question_types=question_types,
        categories=categories,
        difficulties=difficulties,
        review_statuses=review_statuses,
        max_questions=args.limit,
        name=args.name,
    )

    output_path = (
        Path(args.output)
        if args.output
        else Path(input_path).parent / f"{args.name}.json"
    )
    _save_test_set(result, output_path)

    logger.info(
        f"Filtered from {len(test_set.get('questions', []))} to {len(result['questions'])} questions"
    )
    return 0


def _run_incremental(args, composer: TestSetComposer) -> int:
    base_path = Path(args.base)
    if not base_path.exists():
        logger.error(f"Base test set not found: {base_path}")
        return 1

    base_set = _load_test_set(base_path)

    supplement_path = Path(args.supplement_file)
    if not supplement_path.exists():
        logger.error(f"Supplement test set not found: {supplement_path}")
        return 1

    supplement_set = _load_test_set(supplement_path)
    new_questions = supplement_set.get("questions", [])

    result = composer.compose_incremental(
        base_test_set=base_set,
        new_questions=new_questions,
        name=args.name,
        meal_id=args.meal if hasattr(args, "meal") else "",
    )

    output_dir = (
        Path(args.data_dir) / args.meal / "test_sets"
        if hasattr(args, "meal") and args.meal
        else base_path.parent
    )
    output_path = output_dir / f"{args.name}.json"
    _save_test_set(result, output_path)

    logger.info(
        f"Incremental compose: {len(base_set.get('questions', []))} base + "
        f"{len(new_questions)} new → {len(result['questions'])} total"
    )
    return 0
