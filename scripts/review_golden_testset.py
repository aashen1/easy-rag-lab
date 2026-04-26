"""Interactive review tool for golden test set questions.

Provides a CLI-based interactive workflow for reviewing and editing
golden test set questions one at a time. Supports approval, revision,
rejection, and skip operations with automatic progress saving.
Also provides an audit mode for generating quality reports.

Usage:
    pixi run python scripts/review_golden_testset.py
    pixi run python scripts/review_golden_testset.py --input data/golden_testset/golden_150.json
    pixi run python scripts/review_golden_testset.py --start-from 50
    pixi run python scripts/review_golden_testset.py --audit
    pixi run python scripts/review_golden_testset.py --audit --input data/golden_testset/golden_150.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.test_generator import TestSetGenerator as _TSG

_validator = _TSG({"test_generation": {}})


def validate_answer_numerical_accuracy(
    question_data: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    """Validate numerical accuracy, delegating to TestSetGenerator."""
    return _validator._validate_numerical_accuracy(question_data)


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
        print(
            f"  Chunks:     {', '.join(source_chunks[:5])}"
            + (f" +{len(source_chunks) - 5} more" if len(source_chunks) > 5 else "")
        )

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


def review_question(
    question: dict[str, Any], reviewer: str | None = None
) -> dict[str, Any]:
    """Interactively review and potentially edit a single question.

    Args:
        question: Question dictionary to review.
        reviewer: Optional reviewer identifier.

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
            if reviewer:
                question["metadata"]["reviewer"] = reviewer
            print("  ✓ Approved")
            return question

        elif choice == "e":
            question["question"] = edit_field(question.get("question", ""), "question")
            question["answer"] = edit_field(question.get("answer", ""), "answer")
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

            question.setdefault("metadata", {})
            question["metadata"]["review_status"] = REVIEW_STATUS_NEEDS_REVISION
            if reviewer:
                question["metadata"]["reviewer"] = reviewer

            print("  ✓ Edited (marked as needs_revision, choose action again)")
            continue

        elif choice == "r":
            question.setdefault("metadata", {})
            question["metadata"]["reviewed"] = True
            question["metadata"]["review_status"] = REVIEW_STATUS_REJECTED
            question["metadata"]["reviewed_at"] = datetime.now().isoformat()
            if reviewer:
                question["metadata"]["reviewer"] = reviewer
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


def check_auto_approve_eligibility(
    question: dict[str, Any], audit_flags: dict[str, set[str]] | None = None
) -> tuple[bool, list[str]]:
    """Check if a question is eligible for auto-approval.

    A question is auto-approvable if it passes all quality checks:
    1. excerpt_verified == True (or irrelevant type)
    2. No numerical auto-correction
    3. Not flagged by audit report (template, duplication, concentration)
    4. Question length in reasonable range (15-200 chars)
    5. Answer length in reasonable range (10-500 chars)

    Args:
        question: Question dictionary to check.
        audit_flags: Optional dict with keys 'template_ids', 'duplicate_ids',
            'concentrated_ids' containing sets of question IDs flagged by audit.

    Returns:
        Tuple of (is_eligible, list_of_reasons_if_not).
    """
    reasons = []
    metadata = question.get("metadata", {})
    q_type = question.get("question_type", "")
    q_id = question.get("id", "")

    if q_type != "irrelevant" and not metadata.get("excerpt_verified", False):
        reasons.append("excerpt not verified")

    if metadata.get("numerical_auto_corrected", False):
        reasons.append("numerical auto-corrected")

    if audit_flags:
        if q_id in audit_flags.get("template_ids", set()):
            reasons.append("template pattern detected")
        if q_id in audit_flags.get("duplicate_ids", set()):
            reasons.append("potential content duplication")
        if q_id in audit_flags.get("concentrated_ids", set()):
            reasons.append("document concentration")

    q_text = question.get("question", "")
    if len(q_text) < 15:
        reasons.append(f"question too short ({len(q_text)} chars)")
    elif len(q_text) > 200:
        reasons.append(f"question too long ({len(q_text)} chars)")

    answer = question.get("answer", "")
    if len(answer) < 10:
        reasons.append(f"answer too short ({len(answer)} chars)")
    elif len(answer) > 500:
        reasons.append(f"answer too long ({len(answer)} chars)")

    return len(reasons) == 0, reasons


def build_audit_flags(report: dict[str, Any]) -> dict[str, set[str]]:
    """Build sets of question IDs flagged by audit report.

    Args:
        report: Audit report from audit_testset().

    Returns:
        Dict with 'template_ids', 'duplicate_ids', 'concentrated_ids' keys.
    """
    flags: dict[str, set[str]] = {
        "template_ids": set(),
        "duplicate_ids": set(),
        "concentrated_ids": set(),
    }

    for group in report.get("content_duplication", {}).get("groups", []):
        for qid in group.get("question_ids", []):
            flags["duplicate_ids"].add(qid)

    return flags


def run_auto_approve(
    input_path: Path,
    dry_run: bool = False,
) -> None:
    """Auto-approve questions that pass all quality checks.

    Questions that pass all checks are marked as auto_approved.
    Questions with empty/invalid content are marked as auto_rejected.

    Args:
        input_path: Path to the golden test set JSON file.
        dry_run: If True, only report what would be done without modifying.
    """
    testset = load_testset(input_path)
    questions = testset.get("questions", [])

    if not questions:
        logger.error("No questions found in test set")
        return

    report = audit_testset(input_path)
    audit_flags = build_audit_flags(report)

    auto_approved = 0
    auto_rejected = 0
    needs_review = 0

    for question in questions:
        metadata = question.get("metadata", {})
        current_status = metadata.get("review_status")
        if current_status in (REVIEW_STATUS_APPROVED, REVIEW_STATUS_REJECTED):
            continue

        q_text = question.get("question", "")
        answer = question.get("answer", "")

        if not q_text.strip() or not answer.strip():
            if not dry_run:
                question.setdefault("metadata", {})
                question["metadata"]["reviewed"] = True
                question["metadata"]["review_status"] = REVIEW_STATUS_REJECTED
                question["metadata"]["reviewed_at"] = datetime.now().isoformat()
                question["metadata"]["review_notes"] = "auto_rejected: empty content"
            auto_rejected += 1
            continue

        is_eligible, reasons = check_auto_approve_eligibility(question, audit_flags)

        if is_eligible:
            if not dry_run:
                question.setdefault("metadata", {})
                question["metadata"]["reviewed"] = True
                question["metadata"]["review_status"] = "auto_approved"
                question["metadata"]["reviewed_at"] = datetime.now().isoformat()
                question["metadata"]["review_notes"] = (
                    "auto_approved: passed all quality checks"
                )
            auto_approved += 1
        else:
            needs_review += 1

    if not dry_run:
        create_backup(input_path)
        testset["metadata"]["updated_at"] = datetime.now().isoformat()
        audit_entry = {
            "event": "auto_approve",
            "timestamp": datetime.now().isoformat(),
            "auto_approved": auto_approved,
            "auto_rejected": auto_rejected,
            "needs_review": needs_review,
        }
        testset["metadata"].setdefault("audit_log", []).append(audit_entry)
        save_testset(testset, input_path)

    print(f"\n{'=' * 80}")
    print("  Auto-Approve Results" + (" (DRY RUN)" if dry_run else ""))
    print(f"{'=' * 80}")
    print(f"  Auto-approved: {auto_approved}")
    print(f"  Auto-rejected: {auto_rejected}")
    print(f"  Needs review:  {needs_review}")
    print(f"  Total:         {len(questions)}")
    if dry_run:
        print("\n  (No changes were made - use without --dry-run to apply)")
    print(f"{'=' * 80}")


def run_review(
    input_path: Path,
    start_from: int = 1,
    include_auto_approved: bool = False,
    reviewer: str | None = None,
) -> None:
    """Run the interactive review process.

    Args:
        input_path: Path to the golden test set JSON file.
        start_from: Question index to start from (1-based).
        include_auto_approved: Whether to show auto_approved questions.
        reviewer: Optional reviewer identifier.
    """
    testset = load_testset(input_path)
    questions = testset.get("questions", [])

    if not questions:
        logger.error("No questions found in test set")
        return

    create_backup(input_path)

    last_index = testset.get("metadata", {}).get("last_reviewed_index")
    if start_from <= 1 and last_index is not None:
        start_from = last_index + 1
        logger.info(f"Resuming from last reviewed position: question {start_from}")

    total = len(questions)
    approved = sum(
        1
        for q in questions
        if q.get("metadata", {}).get("review_status")
        in (REVIEW_STATUS_APPROVED, "auto_approved")
    )
    rejected = sum(
        1
        for q in questions
        if q.get("metadata", {}).get("review_status") == REVIEW_STATUS_REJECTED
    )
    pending = total - approved - rejected

    print(f"\n{'=' * 80}")
    print("  Golden Test Set Review Tool")
    print(f"  File: {input_path}")
    if reviewer:
        print(f"  Reviewer: {reviewer}")
    print(
        f"  Total: {total} | Approved: {approved} | Rejected: {rejected} | Pending: {pending}"
    )
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
        if review_status == "auto_approved" and not include_auto_approved:
            continue

        display_question(question, i + 1, total)

        result = review_question(question, reviewer=reviewer)

        if result.get("_action") == "quit":
            testset["metadata"]["last_reviewed_index"] = i
            break

        questions[i] = result
        changes_since_save += 1

        if changes_since_save >= save_interval:
            testset["questions"] = questions
            testset["metadata"]["updated_at"] = datetime.now().isoformat()
            testset["metadata"]["last_reviewed_index"] = i
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
    if reviewer:
        audit_entry["reviewer"] = reviewer
    testset["metadata"].setdefault("audit_log", []).append(audit_entry)

    save_testset(testset, input_path)

    final_approved = sum(
        1
        for q in questions
        if q.get("metadata", {}).get("review_status")
        in (REVIEW_STATUS_APPROVED, "auto_approved")
    )
    final_rejected = sum(
        1
        for q in questions
        if q.get("metadata", {}).get("review_status") == REVIEW_STATUS_REJECTED
    )
    final_pending = total - final_approved - final_rejected

    print(f"\n{'=' * 80}")
    print("  Review Summary")
    print(
        f"  Total: {total} | Approved: {final_approved} | "
        f"Rejected: {final_rejected} | Pending: {final_pending}"
    )
    print(f"  Saved to: {input_path}")
    print(f"{'=' * 80}")


def audit_testset(input_path: Path) -> dict[str, Any]:
    """Generate an audit report for a golden test set.

    Analyzes the test set for quality issues including document distribution
    skew, numerical accuracy, content duplication, and pattern repetition.
    Does not assume any directory structure.

    Args:
        input_path: Path to the golden test set JSON file.

    Returns:
        Dictionary containing the audit report.
    """
    testset = load_testset(input_path)
    questions = testset.get("questions", [])
    if not questions:
        logger.error("No questions found in test set")
        return {"error": "No questions found"}

    report: dict[str, Any] = {
        "file": str(input_path),
        "total_questions": len(questions),
    }

    doc_counter: Counter[str] = Counter()
    for q in questions:
        for sf in q.get("source_files", []):
            doc_counter[sf] += 1
    total_docs = len(doc_counter)
    skewed_docs = {
        doc: count
        for doc, count in doc_counter.items()
        if count / len(questions) > 0.15
    }
    report["document_distribution"] = {
        "unique_source_files": total_docs,
        "top_10": doc_counter.most_common(10),
        "skewed_docs": skewed_docs,
    }

    numerical_issues: list[dict] = []
    for q in questions:
        if q.get("question_type") == "irrelevant":
            continue
        is_valid, correction = validate_answer_numerical_accuracy(q)
        if not is_valid and correction:
            numerical_issues.append(
                {
                    "id": q.get("id", "unknown"),
                    "question": q.get("question", "")[:80],
                    "correction": correction,
                }
            )
    report["numerical_accuracy"] = {
        "issues_found": len(numerical_issues),
        "issues": numerical_issues,
    }

    entity_groups: dict[tuple[str, ...], list[str]] = {}
    for q in questions:
        if q.get("question_type") == "irrelevant":
            continue
        entities = tuple(sorted(q.get("key_entities", [])))
        source = (
            q.get("source_files", ["unknown"])[0]
            if q.get("source_files")
            else "unknown"
        )
        key = (source, entities)
        if key not in entity_groups:
            entity_groups[key] = []
        entity_groups[key].append(q.get("id", "unknown"))

    duplicate_pairs: list[dict] = []
    for key, qids in entity_groups.items():
        if len(qids) >= 2 and len(key[1]) >= 2:
            duplicate_pairs.append(
                {
                    "source_file": key[0],
                    "shared_entities": list(key[1]),
                    "question_ids": qids,
                }
            )
    report["content_duplication"] = {
        "potential_duplicate_groups": len(duplicate_pairs),
        "groups": duplicate_pairs[:20],
    }

    doc_type_counter: Counter[str] = Counter()
    for q in questions:
        if q.get("question_type") == "irrelevant":
            continue
        source = (
            q.get("source_files", ["unknown"])[0]
            if q.get("source_files")
            else "unknown"
        )
        key = f"{source}|{q.get('question_type', 'unknown')}"
        doc_type_counter[key] += 1
    over_concentrated = {
        key: count for key, count in doc_type_counter.items() if count > 2
    }
    report["document_concentration"] = {
        "over_concentrated": over_concentrated,
    }

    diff_counter: Counter[str] = Counter(
        q.get("difficulty", "unknown") for q in questions
    )
    report["difficulty_distribution"] = dict(diff_counter)

    verified_count = sum(
        1 for q in questions if q.get("metadata", {}).get("excerpt_verified", False)
    )
    not_verified_count = sum(
        1
        for q in questions
        if q.get("question_type") not in ("irrelevant",)
        and q.get("metadata", {}).get("excerpt_verified") is False
    )
    report["excerpt_verification"] = {
        "verified": verified_count,
        "not_verified": not_verified_count,
        "total_non_irrelevant": sum(
            1 for q in questions if q.get("question_type") != "irrelevant"
        ),
    }

    pattern_counter: Counter[str] = Counter()
    for q in questions:
        qtext = q.get("question", "")
        pattern = re.sub(
            r"[\u4e00-\u9fff]{2,6}(集团|股份|公司|银行|医药|时代|电器|水泥|味业|白药|茅台|老窖)?",
            "X",
            qtext,
        )
        pattern = re.sub(r"\d{4}", "YEAR", pattern)
        pattern = re.sub(r"[\d,.]+%?", "NUM", pattern)
        pattern_counter[pattern] += 1
    template_patterns = {
        pat: count for pat, count in pattern_counter.items() if count >= 3
    }
    report["template_patterns"] = {
        "repeated_patterns": len(template_patterns),
        "patterns": dict(sorted(template_patterns.items(), key=lambda x: -x[1])[:10]),
    }

    return report


def print_audit_report(report: dict[str, Any]) -> None:
    """Print a formatted audit report to stdout.

    Args:
        report: Audit report dictionary from audit_testset().
    """
    print(f"\n{'=' * 80}")
    print("  Golden Test Set Audit Report")
    print(f"  File: {report.get('file', 'N/A')}")
    print(f"  Total Questions: {report.get('total_questions', 0)}")
    print(f"{'=' * 80}")

    doc_dist = report.get("document_distribution", {})
    print("\n--- Document Distribution ---")
    print(f"  Unique source files: {doc_dist.get('unique_source_files', 0)}")
    print("  Top 10:")
    for doc, count in doc_dist.get("top_10", []):
        pct = count / report["total_questions"] * 100
        flag = " ⚠️ SKEWED" if doc in doc_dist.get("skewed_docs", {}) else ""
        print(f"    {doc}: {count} ({pct:.1f}%){flag}")

    num_issues = report.get("numerical_accuracy", {})
    print("\n--- Numerical Accuracy ---")
    print(f"  Issues found: {num_issues.get('issues_found', 0)}")
    for issue in num_issues.get("issues", [])[:10]:
        print(f"    {issue['id']}: {issue['question']}")
        for err in issue.get("correction", {}).get("errors", []):
            print(
                f"      → {err['type']}: answer={err['answer_value']}亿, "
                f"correct={err['correct_value']}亿"
            )

    content_dup = report.get("content_duplication", {})
    print("\n--- Content Duplication ---")
    print(
        f"  Potential duplicate groups: {content_dup.get('potential_duplicate_groups', 0)}"
    )
    for group in content_dup.get("groups", [])[:10]:
        print(
            f"    {group['source_file']}: entities={group['shared_entities']} "
            f"ids={group['question_ids']}"
        )

    conc = report.get("document_concentration", {})
    print("\n--- Document Concentration ---")
    if conc.get("over_concentrated"):
        for key, count in conc["over_concentrated"].items():
            print(f"    {key}: {count} questions")
    else:
        print("  No over-concentration detected ✓")

    diff = report.get("difficulty_distribution", {})
    print("\n--- Difficulty Distribution ---")
    for d, count in sorted(diff.items()):
        pct = count / report["total_questions"] * 100
        print(f"    {d}: {count} ({pct:.1f}%)")

    exc = report.get("excerpt_verification", {})
    print("\n--- Excerpt Verification ---")
    print(f"  Verified: {exc.get('verified', 0)}")
    print(f"  Not verified: {exc.get('not_verified', 0)}")
    print(f"  Total non-irrelevant: {exc.get('total_non_irrelevant', 0)}")

    tmpl = report.get("template_patterns", {})
    print("\n--- Template Patterns ---")
    print(f"  Repeated patterns: {tmpl.get('repeated_patterns', 0)}")
    for pat, count in tmpl.get("patterns", {}).items():
        print(f"    ({count}x) {pat[:80]}")

    print(f"\n{'=' * 80}")


def main():
    """CLI entry point for golden test set review."""
    parser = argparse.ArgumentParser(
        description="Interactive review tool for golden test set"
    )
    parser.add_argument(
        "--input",
        default="data/golden_testset/golden_150.json",
        help="Path to golden test set JSON file",
    )
    parser.add_argument(
        "--start-from",
        type=int,
        default=1,
        help="Question index to start from (1-based)",
    )
    parser.add_argument(
        "--audit",
        action="store_true",
        help="Run audit report instead of interactive review",
    )
    parser.add_argument(
        "--auto-approve",
        action="store_true",
        help="Auto-approve questions that pass all quality checks",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="With --auto-approve, only report what would be done",
    )
    parser.add_argument(
        "--include-auto-approved",
        action="store_true",
        help="Show auto_approved questions during interactive review",
    )
    parser.add_argument(
        "--reviewer",
        type=str,
        default=None,
        help="Reviewer identifier to record in metadata",
    )
    args = parser.parse_args()

    if args.audit:
        report = audit_testset(Path(args.input))
        print_audit_report(report)
    elif args.auto_approve:
        run_auto_approve(
            input_path=Path(args.input),
            dry_run=args.dry_run,
        )
    else:
        run_review(
            input_path=Path(args.input),
            start_from=args.start_from,
            include_auto_approved=args.include_auto_approved,
            reviewer=args.reviewer,
        )


if __name__ == "__main__":
    main()
