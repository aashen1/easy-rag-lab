from __future__ import annotations

import argparse
import sys

from src.testset_cli.approve import run_approve
from src.testset_cli.compose import run_compose
from src.testset_cli.enrich import run_enrich
from src.testset_cli.migrate import run_migrate
from src.testset_cli.review import run_review


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="testset",
        description="Test set pipeline management CLI",
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    migrate_parser = subparsers.add_parser(
        "migrate", help="Migrate golden test sets to portable directory"
    )
    migrate_parser.add_argument(
        "--data-dir", default="data", help="Data directory path"
    )
    migrate_parser.add_argument(
        "--dry-run", action="store_true", help="Preview migration without copying files"
    )

    enrich_parser = subparsers.add_parser(
        "enrich", help="Run AI pre-review on test set questions"
    )
    enrich_parser.add_argument("--input", required=True, help="Path to test set JSON")
    enrich_parser.add_argument("--llm-preset", default=None, help="LLM preset name")
    enrich_parser.add_argument(
        "--auto-approve-tier-a",
        action="store_true",
        help="Auto-approve Tier A questions",
    )

    review_parser = subparsers.add_parser(
        "review", help="Interactive human review of test set questions"
    )
    review_parser.add_argument("--input", required=True, help="Path to test set JSON")
    review_parser.add_argument(
        "--start-from",
        type=int,
        default=1,
        help="Question index to start from (1-based)",
    )
    review_parser.add_argument(
        "--reviewer", type=str, default=None, help="Reviewer identifier"
    )
    review_parser.add_argument(
        "--include-auto-approved",
        action="store_true",
        help="Show auto_approved questions during review",
    )
    review_parser.add_argument(
        "--only-new",
        action="store_true",
        help="Only review questions with quality_status='draft'",
    )
    review_parser.add_argument(
        "--no-pdf", action="store_true", help="Disable PDF viewer integration"
    )
    review_parser.add_argument(
        "--no-chunks", action="store_true", help="Disable chunk context display"
    )
    review_parser.add_argument("--data-dir", default="data", help="Data directory path")

    approve_parser = subparsers.add_parser(
        "approve", help="Finalize test set and optionally promote to portable"
    )
    approve_parser.add_argument("--input", required=True, help="Path to test set JSON")
    approve_parser.add_argument(
        "--data-dir", default="data", help="Data directory path"
    )

    compose_parser = subparsers.add_parser(
        "compose", help="Compose test sets (merge, filter, incremental)"
    )
    compose_sub = compose_parser.add_subparsers(
        dest="subcommand", help="Composition type"
    )

    merge_parser = compose_sub.add_parser("merge", help="Merge multiple test sets")
    merge_parser.add_argument(
        "--sources",
        nargs="+",
        required=True,
        help="Source specs: meal:test_name or path",
    )
    merge_parser.add_argument("--name", required=True, help="Output test set name")
    merge_parser.add_argument("--meal", default="", help="Target meal name")
    merge_parser.add_argument("--data-dir", default="data", help="Data directory path")

    filter_parser = compose_sub.add_parser("filter", help="Filter test set by criteria")
    filter_parser.add_argument("--input", required=True, help="Path to test set JSON")
    filter_parser.add_argument("--name", required=True, help="Output test set name")
    filter_parser.add_argument(
        "--question-type", default=None, help="Comma-separated question types"
    )
    filter_parser.add_argument(
        "--category", default=None, help="Comma-separated categories"
    )
    filter_parser.add_argument(
        "--difficulty", default=None, help="Comma-separated difficulties"
    )
    filter_parser.add_argument(
        "--review-status", default=None, help="Comma-separated review statuses"
    )
    filter_parser.add_argument("--limit", type=int, default=None, help="Max questions")
    filter_parser.add_argument("--output", default=None, help="Output file path")

    incremental_parser = compose_sub.add_parser(
        "incremental", help="Add new questions to existing test set"
    )
    incremental_parser.add_argument(
        "--base", required=True, help="Path to base test set JSON"
    )
    incremental_parser.add_argument(
        "--supplement-file", required=True, help="Path to supplement test set JSON"
    )
    incremental_parser.add_argument(
        "--name", required=True, help="Output test set name"
    )
    incremental_parser.add_argument("--meal", default="", help="Target meal name")
    incremental_parser.add_argument(
        "--data-dir", default="data", help="Data directory path"
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "migrate":
        return run_migrate(args)
    elif args.command == "enrich":
        return run_enrich(args)
    elif args.command == "review":
        return run_review(args)
    elif args.command == "approve":
        return run_approve(args)
    elif args.command == "compose":
        return run_compose(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
