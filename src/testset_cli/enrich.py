from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.testset_review.ai_reviewer import AIReviewer
from src.utils import load_config


def run_enrich(args) -> int:
    input_path = Path(args.input)
    if not input_path.exists():
        logger.error(f"Test set not found: {input_path}")
        return 1

    with open(input_path, encoding="utf-8") as f:
        test_set = json.load(f)

    questions = test_set.get("questions", [])
    if not questions:
        logger.error("No questions found in test set")
        return 1

    config = load_config()
    reviewer = AIReviewer(config, llm_preset=args.llm_preset)

    logger.info(f"Running AI review on {len(questions)} questions")
    reviewer.review_questions(questions)

    summary = reviewer.get_tier_summary(questions)
    logger.info(
        f"Tier A: {len(summary['A'])}, "
        f"Tier B: {len(summary['B'])}, "
        f"Tier C: {len(summary['C'])}"
    )

    if getattr(args, "auto_approve_tier_a", False) and summary["A"]:
        tier_a_count = 0
        for q in questions:
            review = q.get("metadata", {}).get("ai_review")
            if review and reviewer.classify_tier(review) == "A":
                current = q.get("metadata", {}).get("review_status", "pending")
                if current in ("approved", "rejected", "auto_approved"):
                    continue
                q.setdefault("metadata", {})
                q["metadata"]["review_status"] = "auto_approved"
                q["metadata"]["reviewed_at"] = datetime.now().isoformat()
                tier_a_count += 1
        logger.info(f"Auto-approved {tier_a_count} Tier A questions")

    test_set["metadata"]["updated_at"] = datetime.now().isoformat()
    test_set["metadata"]["quality_status"] = "ai_reviewed"

    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(test_set, f, ensure_ascii=False, indent=2)

    logger.success(f"AI review complete. Saved to {input_path}")
    return 0
