"""Interactive review tool for golden test set questions.

Provides a CLI-based interactive workflow for reviewing and editing
golden test set questions one at a time. Supports approval, revision,
rejection, and skip operations with automatic progress saving.

Usage:
    pixi run python scripts/review_golden_testset.py
    pixi run python scripts/review_golden_testset.py --input data/golden_testset/golden_150.json
    pixi run python scripts/review_golden_testset.py --start-from 50
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_NEEDS_REVISION = "needs_revision"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_PENDING = "pending"

SEPARATOR = "=" * 80
THIN_SEP = "-" * 80


def load_testset(path: Path) -> dict[str, Any]:
    """Load a golden test set JSON file.

    Args:
        path: Path to the JSON file.

    Returns:
        Parsed test set dictionary.

    Raises:
        FileNotFoundError: If the file does not exist.
    """
    if not path.exists():
        logger.error(f"Test set file not found: {path}")
        raise FileNotFoundError(f"Test set file not found: {path}")

    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_testset(testset: dict[str, Any], path: Path) -> None:
    """Save a golden test set JSON file.

    Args:
        testset: Test set dictionary to save.
        path: Path to save the JSON file.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(testset, f, ensure_ascii=False, indent=2)
    logger.info(f"Saved test set to {path}")


def create_backup(path: Path) -> Path:
    """Create a timestamped backup of the test set file.

    Args:
        path: Path to the original file.

    Returns:
        Path to the backup file.
    """
    timestamp = datetime.now().strftime("%Y%m%dT%H%M%S")
    backup_path = path.parent / f"{path.stem}.backup.{timestamp}.json"
    if path.exists():
        import shutil
        shutil.copy2(path, backup_path)
        logger.info(f"Backup created at {backup_path}")
    return backup_path


def display_question(question: dict[str, Any], index: int, total: int) -> None:
    """Display a question for review in a formatted way.

    Args:
        question: Question dictionary to display.
        index: Current question index (1-based).
        total: Total number of questions.
    """
    print(f"\n{SEPARATOR}")
    print(f"  Question {index}/{total}  |  ID: {question.get('id', 'N/A')}")
    print(SEPARATOR)

    print(f"\n  Type:       {question.get('question_type', 'N/A')}")
    print(f"  Difficulty: {question.get('difficulty', 'N/A')}")
    print(f"  Source:     {question.get('source_document', 'N/A')}")

    source_files = question.get("source_files", [])
    if source_files:
        print(f"  Files:      {', '.join(source_files)}")

    source_chunks = question.get("source_chunks", [])
    if source_chunks:
        print(f"  Chunks:     {', '.join(source_chunks[:5])}"
              + (f" +{len(source_chunks) - 5} more" if len(source_chunks) > 5 else ""))

    metadata = question.get("metadata", {})
    if metadata.get("excerpt_verified") is not None:
        verified = "YES" if metadata.get("excerpt_verified") else "NO"
        print(f"  Excerpt OK: {verified}")
    if metadata.get("reviewed"):
        print(f"  Reviewed:   YES ({metadata.get('review_status', 'unknown')})")

    print(f"\n{THIN_SEP}")
    print("\n  QUESTION:")
    print(f"    {question.get('question', 'N/A')}")

    print("\n  ANSWER:")
    answer = question.get("answer", "N/A")
    for line in answer.split("\n"):
        print(f"    {line}")

    excerpt = question.get("ground_truth_excerpt", "")
    if excerpt:
        print("\n  GROUND TRUTH EXCERPT:")
        for line in excerpt.split("\n"):
            print(f"    {line}")

    failure_mode = metadata.get("target_failure_mode", "")
    if failure_mode:
        print(f"\n  TARGET FAILURE MODE: {failure_mode}")

    print(f"\n{SEPARATOR}")


def edit_field(value: str, field_name: str) -> str:
    """Interactively edit a text field.

    Args:
        value: Current value of the field.
        field_name: Name of the field for display.

    Returns:
        New value (or original if no change).
    """
    print(f"\n  Current {field_name}:")
    print(f"    {value}")
    new_value = input(f"  New {field_name} (Enter to keep, 'clear' to empty): ").strip()
    if new_value == "clear":
        return ""
    if new_value == "":
        return value
    return new_value


def review_question(question: dict[str, Any]) -> dict[str, Any]:
    """Interactively review and potentially edit a single question.

    Args:
        question: Question dictionary to review.

    Returns:
        Updated question dictionary.
    """
    print("\n  Actions:")
    print("    [a] Approve     - Mark as reviewed and approved")
    print("    [e] Edit        - Edit question, answer, or excerpt")
    print("    [r] Reject      - Mark as rejected (will be excluded)")
    print("    [s] Skip        - Skip for now, review later")
    print("    [q] Quit        - Save progress and exit")

    while True:
        choice = input("\n  Your choice [a/e/r/s/q]: ").strip().lower()

        if choice == "a":
            question.setdefault("metadata", {})
            question["metadata"]["reviewed"] = True
            question["metadata"]["review_status"] = REVIEW_STATUS_APPROVED
            question["metadata"]["reviewed_at"] = datetime.now().isoformat()
            print("  ✓ Approved")
            return question

        elif choice == "e":
            question["question"] = edit_field(
                question.get("question", ""), "question"
            )
            question["answer"] = edit_field(
                question.get("answer", ""), "answer"
            )
            question["ground_truth_excerpt"] = edit_field(
                question.get("ground_truth_excerpt", ""), "ground_truth_excerpt"
            )

            new_type = input(
                f"  Question type [{question.get('question_type', '')}]: "
            ).strip()
            if new_type:
                question["question_type"] = new_type

            new_diff = input(
                f"  Difficulty [{question.get('difficulty', '')}]: "
            ).strip()
            if new_diff:
                question["difficulty"] = new_diff

            notes = input("  Review notes (optional): ").strip()
            if notes:
                question.setdefault("metadata", {})
                question["metadata"]["review_notes"] = notes

            print("  ✓ Edited (not yet approved, choose action again)")
            continue

        elif choice == "r":
            question.setdefault("metadata", {})
            question["metadata"]["reviewed"] = True
            question["metadata"]["review_status"] = REVIEW_STATUS_REJECTED
            question["metadata"]["reviewed_at"] = datetime.now().isoformat()
            reason = input("  Rejection reason: ").strip()
            if reason:
                question["metadata"]["review_notes"] = reason
            print("  ✗ Rejected")
            return question

        elif choice == "s":
            print("  → Skipped")
            return question

        elif choice == "q":
            return {"_action": "quit"}

        else:
            print("  Invalid choice, please try again")


def run_review(
    input_path: Path,
    start_from: int = 1,
) -> None:
    """Run the interactive review process.

    Args:
        input_path: Path to the golden test set JSON file.
        start_from: Question index to start from (1-based).
    """
    testset = load_testset(input_path)
    questions = testset.get("questions", [])

    if not questions:
        logger.error("No questions found in test set")
        return

    create_backup(input_path)

    total = len(questions)
    approved = sum(
        1 for q in questions
        if q.get("metadata", {}).get("review_status") == REVIEW_STATUS_APPROVED
    )
    rejected = sum(
        1 for q in questions
        if q.get("metadata", {}).get("review_status") == REVIEW_STATUS_REJECTED
    )
    pending = total - approved - rejected

    print(f"\n{'=' * 80}")
    print("  Golden Test Set Review Tool")
    print(f"  File: {input_path}")
    print(f"  Total: {total} | Approved: {approved} | Rejected: {rejected} | Pending: {pending}")
    print(f"{'=' * 80}")

    save_interval = 5
    changes_since_save = 0

    for i in range(start_from - 1, total):
        question = questions[i]

        review_status = question.get("metadata", {}).get("review_status")
        if review_status == REVIEW_STATUS_APPROVED:
            continue
        if review_status == REVIEW_STATUS_REJECTED:
            continue

        display_question(question, i + 1, total)

        result = review_question(question)

        if result.get("_action") == "quit":
            break

        questions[i] = result
        changes_since_save += 1

        if changes_since_save >= save_interval:
            testset["questions"] = questions
            testset["metadata"]["updated_at"] = datetime.now().isoformat()
            save_testset(testset, input_path)
            changes_since_save = 0
            print(f"\n  [Auto-saved at question {i + 1}]")

    testset["questions"] = questions
    testset["metadata"]["updated_at"] = datetime.now().isoformat()

    audit_entry = {
        "event": "review_session",
        "timestamp": datetime.now().isoformat(),
        "start_from": start_from,
        "total_questions": total,
    }
    testset["metadata"].setdefault("audit_log", []).append(audit_entry)

    save_testset(testset, input_path)

    final_approved = sum(
        1 for q in questions
        if q.get("metadata", {}).get("review_status") == REVIEW_STATUS_APPROVED
    )
    final_rejected = sum(
        1 for q in questions
        if q.get("metadata", {}).get("review_status") == REVIEW_STATUS_REJECTED
    )
    final_pending = total - final_approved - final_rejected

    print(f"\n{'=' * 80}")
    print("  Review Summary")
    print(f"  Total: {total} | Approved: {final_approved} | "
          f"Rejected: {final_rejected} | Pending: {final_pending}")
    print(f"  Saved to: {input_path}")
    print(f"{'=' * 80}")


def main():
    """CLI entry point for golden test set review."""
    parser = argparse.ArgumentParser(
        description="Interactive review tool for golden test set"
    )
    parser.add_argument(
        "--input", default="data/golden_testset/golden_150.json",
        help="Path to golden test set JSON file",
    )
    parser.add_argument(
        "--start-from", type=int, default=1,
        help="Question index to start from (1-based)",
    )
    args = parser.parse_args()

    run_review(
        input_path=Path(args.input),
        start_from=args.start_from,
    )


if __name__ == "__main__":
    main()
