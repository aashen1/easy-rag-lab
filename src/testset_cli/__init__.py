from __future__ import annotations

import argparse
import sys

from src.testset_cli.migrate import run_migrate


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

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "migrate":
        return run_migrate(args)

    parser.print_help()
    return 0


if __name__ == "__main__":
    sys.exit(main())
