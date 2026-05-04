"""Artifact CLI for querying artifact status and pointers.

Usage:
    pixi run python -m src.artifact_cli list
    pixi run python -m src.artifact_cli pointer full_parsed
    pixi run python -m src.artifact_cli info <data_id_prefix>
"""

import argparse
import contextlib
import json
import sys
from pathlib import Path

from loguru import logger

from src.meal import ArtifactCache
from src.utils import load_config, setup_logger


def cmd_list(args: argparse.Namespace) -> None:
    config = load_config()
    artifacts_config = config.get("artifacts", {})
    artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))

    if not artifacts_dir.exists():
        logger.info("No artifacts directory found")
        return

    groups = sorted(
        d for d in artifacts_dir.iterdir() if d.is_dir() and d.name != "_pointers"
    )

    if not groups:
        logger.info("No artifact groups found")
        return

    print(f"Found {len(groups)} artifact group(s) in {artifacts_dir}:\n")
    for group_dir in groups:
        manifest_path = group_dir / "manifest.json"
        manifest = None
        if manifest_path.exists():
            with contextlib.suppress(Exception):
                manifest = json.loads(manifest_path.read_text(encoding="utf-8"))

        subdirs = sorted(d.name for d in group_dir.iterdir() if d.is_dir())
        pdf_count = manifest.get("pdf_count", "?") if manifest else "?"
        created = manifest.get("created_at", "?") if manifest else "?"

        print(f"  {group_dir.name}/")
        print(f"    PDFs: {pdf_count}, Created: {created}")
        print(f"    Subdirs: {', '.join(subdirs)}")
        print()


def cmd_pointer(args: argparse.Namespace) -> None:
    config = load_config()
    artifacts_config = config.get("artifacts", {})
    artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))
    raw_dir = Path(config.get("parser", {}).get("input_dir", "data/raw"))

    cache = ArtifactCache(artifacts_dir, raw_dir)
    resolved = cache.resolve_pointer(args.name)

    if resolved:
        print(f"Pointer '{args.name}' -> {resolved}")
    else:
        pointer_file = cache.pointers_dir / f"{args.name}.pointer"
        if pointer_file.exists():
            content = pointer_file.read_text(encoding="utf-8").strip()
            target = artifacts_dir / content
            print(f"Pointer '{args.name}' points to {content}")
            print(f"  Target does not exist: {target}")
        else:
            print(f"Pointer '{args.name}' not found")
            available = (
                list(cache.pointers_dir.glob("*.pointer"))
                if cache.pointers_dir.exists()
                else []
            )
            if available:
                names = [p.stem for p in available]
                print(f"  Available pointers: {', '.join(names)}")


def cmd_info(args: argparse.Namespace) -> None:
    config = load_config()
    artifacts_config = config.get("artifacts", {})
    artifacts_dir = Path(artifacts_config.get("dir", "data/artifacts"))

    group_dir = artifacts_dir / args.data_id
    if not group_dir.exists():
        matches = sorted(
            d
            for d in artifacts_dir.iterdir()
            if d.is_dir() and d.name.startswith(args.data_id)
        )
        if len(matches) == 1:
            group_dir = matches[0]
        elif len(matches) > 1:
            print(f"Ambiguous prefix '{args.data_id}', matches:")
            for m in matches:
                print(f"  {m.name}")
            return
        else:
            print(f"No artifact group found matching '{args.data_id}'")
            return

    print(f"Artifact group: {group_dir.name}\n")

    manifest_path = group_dir / "manifest.json"
    if manifest_path.exists():
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            print("Manifest:")
            print(json.dumps(manifest, indent=2, ensure_ascii=False))
        except Exception as e:
            logger.error(f"Failed to read manifest: {e}")
    else:
        print("No manifest.json found")

    subdirs = sorted(d for d in group_dir.iterdir() if d.is_dir())
    if subdirs:
        print("\nSubdirectories:")
        for subdir in subdirs:
            file_count = sum(1 for _ in subdir.rglob("*") if _.is_file())
            print(f"  {subdir.name}/ ({file_count} files)")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Artifact CLI for querying artifact status and pointers"
    )
    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    list_parser = subparsers.add_parser("list", help="List all artifact groups")
    list_parser.set_defaults(func=cmd_list)

    pointer_parser = subparsers.add_parser(
        "pointer", help="Resolve a pointer to an artifact directory"
    )
    pointer_parser.add_argument("name", help="Pointer name (e.g., full_parsed)")
    pointer_parser.set_defaults(func=cmd_pointer)

    info_parser = subparsers.add_parser(
        "info", help="Show details of an artifact group"
    )
    info_parser.add_argument("data_id", help="Data ID prefix (e.g., d3a711e6)")
    info_parser.set_defaults(func=cmd_info)

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    config = load_config()
    setup_logger(config)

    args.func(args)


if __name__ == "__main__":
    main()
