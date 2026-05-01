from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

from loguru import logger


def run_approve(args) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Test set not found: {input_path}")
        return 1

    with open(input_path, encoding="utf-8") as f:
        test_set = json.load(f)

    metadata = test_set.get("metadata", {})
    quality_status = metadata.get("quality_status", "draft")

    if quality_status not in ("ai_reviewed", "human_reviewed", "auto_approved"):
        logger.warning(
            f"Test set has quality_status='{quality_status}'. "
            f"Approve is designed for reviewed test sets."
        )

    metadata["quality_status"] = "approved"
    metadata["updated_at"] = datetime.now().isoformat()

    data_coverage = metadata.get("data_coverage", "partial")
    if data_coverage == "full":
        metadata.setdefault("portable", True)
        portable_dir = Path(getattr(args, "data_dir", "data")) / "test_sets"
        portable_dir.mkdir(parents=True, exist_ok=True)
        portable_path = portable_dir / f"{metadata.get('name', 'approved')}.json"
        shutil.copy2(input_path, portable_path)
        logger.success(f"Test set approved and promoted to portable: {portable_path}")
    else:
        logger.info(
            f"Test set approved but not portable "
            f"(data_coverage={data_coverage}, need 'full' for portability)"
        )

    metadata.setdefault("audit_log", []).append(
        {
            "event": "approved",
            "timestamp": datetime.now().isoformat(),
        }
    )

    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(test_set, f, ensure_ascii=False, indent=2)

    logger.success(f"Test set '{metadata.get('name')}' approved. Saved to {input_path}")
    return 0
