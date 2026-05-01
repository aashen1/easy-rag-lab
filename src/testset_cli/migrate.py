from __future__ import annotations

import shutil
from pathlib import Path

from loguru import logger


def migrate_golden_to_portable(
    golden_dir: Path,
    portable_dir: Path,
    dry_run: bool = False,
) -> list[str]:
    migrated: list[str] = []
    portable_dir.mkdir(parents=True, exist_ok=True)

    for json_file in sorted(golden_dir.glob("*.json")):
        dest = portable_dir / json_file.name
        if dest.exists():
            logger.info(
                f"Skipping {json_file.name}: already exists in portable directory"
            )
            continue

        logger.info(
            f"{'[DRY RUN] Would migrate' if dry_run else 'Migrating'} {json_file} -> {dest}"
        )
        if not dry_run:
            shutil.copy2(json_file, dest)
        migrated.append(json_file.name)

    return migrated


def run_migrate(args) -> int:
    data_dir = Path(args.data_dir if hasattr(args, "data_dir") else "data")
    golden_dir = data_dir / "golden_testset"
    portable_dir = data_dir / "test_sets"

    if not golden_dir.exists():
        logger.warning(f"Golden test set directory not found: {golden_dir}")
        return 0

    dry_run = getattr(args, "dry_run", False)
    migrated = migrate_golden_to_portable(golden_dir, portable_dir, dry_run=dry_run)

    if dry_run:
        logger.info(f"Dry run complete. {len(migrated)} files would be migrated:")
        for f in migrated:
            logger.info(f"  {f}")
    else:
        logger.success(
            f"Migration complete. {len(migrated)} files migrated to {portable_dir}"
        )

    return 0
