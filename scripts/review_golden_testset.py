"""Interactive review tool for golden test set questions.

Provides a CLI-based interactive workflow for reviewing and editing
golden test set questions one at a time. Supports approval, revision,
rejection, and skip operations with automatic progress saving.

Enhanced features:
- AI pre-review with quality scoring and tier classification
- PDF auto-open at relevant page (SumatraPDF / Edge)
- Chunk context inline display
- Progress bar and session statistics
- Tiered review mode (AI filters, human reviews B/C tier)

Usage:
    pixi run python scripts/review_golden_testset.py
    pixi run python scripts/review_golden_testset.py --input data/golden_testset/golden_150.json
    pixi run python scripts/review_golden_testset.py --start-from 50
    pixi run python scripts/review_golden_testset.py --audit
    pixi run python scripts/review_golden_testset.py --ai-review --llm-preset default
    pixi run python scripts/review_golden_testset.py --tiered-review
    pixi run python scripts/review_golden_testset.py --sort-by-score
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any

from loguru import logger

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.ai_reviewer import AIReviewer
from scripts.pdf_viewer import PDFViewer
from src.test_generation.validators import validate_numerical_accuracy
from src.utils import load_config


def validate_answer_numerical_accuracy(
    question_data: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    """Validate numerical accuracy, delegating to standalone validator."""
    return validate_numerical_accuracy(question_data)


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


def format_progress_bar(current: int, total: int, width: int = 30) -> str:
    """Format a progress bar string.

    Args:
        current: Current progress count.
        total: Total count.
        width: Width of the progress bar in characters.

    Returns:
        Formatted progress bar string.
    """
    if total == 0:
        return "[" + " " * width + "] 0/0 (0%)"
    pct = current / total
    filled = int(width * pct)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {current}/{total} ({pct * 100:.0f}%)"


def format_ai_tier_badge(ai_review: dict[str, Any] | None) -> str:
    """Format an AI review tier badge for display.

    Args:
        ai_review: AI review result dictionary, or None.

    Returns:
        Formatted tier badge string.
    """
    if not ai_review:
        return ""
    tier = ai_review.get("tier", "?")
    score = ai_review.get("overall_score", 0.0)
    if tier == "A":
        return f"AI: A({score:.1f})"
    elif tier == "B":
        return f"⚠ AI: B({score:.1f})"
    else:
        return f"✗ AI: C({score:.1f})"


def display_question(
    question: dict[str, Any],
    index: int,
    total: int,
    pdf_viewer: PDFViewer | None = None,
    show_chunks: bool = True,
) -> None:
    """Display a question for review with enhanced context.

    Shows question details, AI review tier, chunk context, and PDF
    location in a compact, information-dense format.

    Args:
        question: Question dictionary to display.
        index: Current question index (1-based).
        total: Total number of questions.
        pdf_viewer: Optional PDFViewer instance for chunk/PDF info.
        show_chunks: Whether to display chunk context.
    """
    metadata = question.get("metadata", {})
    ai_review = metadata.get("ai_review")
    tier_badge = format_ai_tier_badge(ai_review)

    header_parts = [
        f"#{index}/{total}",
        question.get("id", "N/A"),
        question.get("question_type", "N/A"),
        question.get("difficulty", "N/A"),
    ]
    if tier_badge:
        header_parts.append(tier_badge)

    print(f"\n{SEPARATOR}")
    print(f"  {'  │  '.join(header_parts)}")
    print(SEPARATOR)

    print(f"\n  Q: {question.get('question', 'N/A')}")

    print("\n  A: ", end="")
    answer = question.get("answer", "N/A")
    for i, line in enumerate(answer.split("\n")):
        if i == 0:
            print(line)
        else:
            print(f"     {line}")

    excerpt = question.get("ground_truth_excerpt", "")
    if excerpt:
        verified = metadata.get("excerpt_verified")
        num_corrected = metadata.get("numerical_auto_corrected", False)
        flags = []
        if verified is True:
            flags.append("✓ Excerpt verified")
        elif verified is False:
            flags.append("✗ Excerpt NOT verified")
        if num_corrected:
            flags.append("✗ Numerical auto-corrected")

        print(f'\n  EXCERPT: "{excerpt}"')
        if flags:
            print(f"     {'  '.join(flags)}")

    if show_chunks and pdf_viewer:
        chunks = pdf_viewer.get_chunks_for_question(question)
        if chunks:
            print(f"\n{pdf_viewer.format_chunk_display(chunks)}")

    if pdf_viewer:
        pdf_path, page_number = pdf_viewer.locate_page_for_question(question)
        if pdf_path:
            page_info = f" → Page {page_number}" if page_number else ""
            viewer_type = pdf_viewer.viewer_type or "none"
            print(f"\n  PDF: {pdf_path.name}{page_info}  [p] Open ({viewer_type})")
        elif question.get("source_files"):
            source = question["source_files"][0]
            page_text = None
            if page_number is None and pdf_viewer.parsed_dir:
                page_text = pdf_viewer.get_page_text(source, 1)
            if not page_text:
                pages = pdf_viewer._load_pages_for_source(source)
                if pages:
                    best_page = None
                    best_score = 0.0
                    excerpt = question.get("ground_truth_excerpt", "")
                    if excerpt:
                        from difflib import SequenceMatcher

                        for p in pages:
                            score = SequenceMatcher(
                                None, excerpt[:200], p.get("text", "")[:2000]
                            ).ratio()
                            if score > best_score:
                                best_score = score
                                best_page = p
                    if best_page:
                        page_text = best_page.get("text", "")
            if page_text:
                print("\n  PAGE TEXT (no PDF viewer):")
                for line in page_text[:500].split("\n"):
                    if line.strip():
                        print(f"    {line.strip()[:72]}")

    failure_mode = metadata.get("target_failure_mode", "")
    if failure_mode:
        print(f"\n  TARGET FAILURE MODE: {failure_mode}")

    print(f"\n{THIN_SEP}")
    actions = "  [a]Approve  [e]Edit  [r]Reject  [s]Skip  [q]Quit"
    if pdf_viewer and pdf_viewer.viewer_path:
        actions += "  [p]PDF"
    if show_chunks:
        actions += "  [c]Chunks"
    if ai_review:
        actions += "  [i]AI detail"
    print(actions)
    print(SEPARATOR)


def display_ai_detail(ai_review: dict[str, Any]) -> None:
    """Display detailed AI review information.

    Args:
        ai_review: AI review result dictionary.
    """
    print(f"\n  {THIN_SEP}")
    print("  AI REVIEW DETAIL:")
    dimensions = ai_review.get("dimensions", {})
    for dim_name, dim_data in dimensions.items():
        if isinstance(dim_data, dict):
            score = dim_data.get("score", "?")
            reason = dim_data.get("reason", "")
            print(f"    {dim_name}: {score}/5 - {reason}")
    print(
        f"    Overall: {ai_review.get('overall_score', '?')}/5 ({ai_review.get('tier', '?')})"
    )
    print(f"    Comment: {ai_review.get('overall_comment', '')}")
    print(f"    Suggested: {ai_review.get('suggested_action', '')}")
    print(f"  {THIN_SEP}")


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
    question: dict[str, Any],
    reviewer: str | None = None,
    pdf_viewer: PDFViewer | None = None,
    show_chunks: bool = True,
) -> dict[str, Any]:
    """Interactively review and potentially edit a single question.

    Supports enhanced actions: open PDF, toggle chunks, view AI detail.

    Args:
        question: Question dictionary to review.
        reviewer: Optional reviewer identifier.
        pdf_viewer: Optional PDFViewer for PDF opening.
        show_chunks: Initial state of chunk display.

    Returns:
        Updated question dictionary.
    """
    current_show_chunks = show_chunks

    while True:
        choice = input("\n  Your choice: ").strip().lower()

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

        elif choice == "p" and pdf_viewer:
            pdf_path, page_number = pdf_viewer.locate_page_for_question(question)
            if pdf_path:
                page = page_number or 1
                success = pdf_viewer.open_at_page(pdf_path, page)
                if success:
                    print(f"  → Opened PDF at page {page}")
                else:
                    print("  → Failed to open PDF")
            else:
                print("  → No PDF path found for this question")
            continue

        elif choice == "c":
            current_show_chunks = not current_show_chunks
            state = "ON" if current_show_chunks else "OFF"
            print(f"  → Chunk display: {state}")
            continue

        elif choice == "i":
            ai_review = question.get("metadata", {}).get("ai_review")
            if ai_review:
                display_ai_detail(ai_review)
            else:
                print("  → No AI review available for this question")
            continue

        else:
            print(
                "  Invalid choice. Available: a/e/r/s/q"
                + (" p" if pdf_viewer else "")
                + " c i"
            )


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
    pdf_viewer: PDFViewer | None = None,
    show_chunks: bool = True,
) -> None:
    """Run the interactive review process with enhanced features.

    Args:
        input_path: Path to the golden test set JSON file.
        start_from: Question index to start from (1-based).
        include_auto_approved: Whether to show auto_approved questions.
        reviewer: Optional reviewer identifier.
        pdf_viewer: Optional PDFViewer for PDF opening and chunk display.
        show_chunks: Whether to display chunk context.
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

    print(f"\n{SEPARATOR}")
    print("  Golden Test Set Review Tool")
    print(f"  File: {input_path}")
    if reviewer:
        print(f"  Reviewer: {reviewer}")
    if pdf_viewer and pdf_viewer.viewer_type:
        print(f"  PDF Viewer: {pdf_viewer.viewer_type}")
    print(
        f"  Total: {total} | Approved: {approved} | Rejected: {rejected} | Pending: {pending}"
    )
    print(f"  {format_progress_bar(approved + rejected, total)}")
    print(SEPARATOR)

    save_interval = 5
    changes_since_save = 0
    session_start = time.time()
    session_approved = 0
    session_rejected = 0
    session_skipped = 0

    for i in range(start_from - 1, total):
        question = questions[i]

        review_status = question.get("metadata", {}).get("review_status")
        if review_status == REVIEW_STATUS_APPROVED:
            continue
        if review_status == REVIEW_STATUS_REJECTED:
            continue
        if review_status == "auto_approved" and not include_auto_approved:
            continue

        display_question(
            question,
            i + 1,
            total,
            pdf_viewer=pdf_viewer,
            show_chunks=show_chunks,
        )

        result = review_question(
            question,
            reviewer=reviewer,
            pdf_viewer=pdf_viewer,
            show_chunks=show_chunks,
        )

        if result.get("_action") == "quit":
            testset["metadata"]["last_reviewed_index"] = i
            break

        questions[i] = result
        changes_since_save += 1

        final_status = result.get("metadata", {}).get("review_status")
        if final_status == REVIEW_STATUS_APPROVED:
            session_approved += 1
        elif final_status == REVIEW_STATUS_REJECTED:
            session_rejected += 1
        else:
            session_skipped += 1

        if changes_since_save >= save_interval:
            testset["questions"] = questions
            testset["metadata"]["updated_at"] = datetime.now().isoformat()
            testset["metadata"]["last_reviewed_index"] = i
            save_testset(testset, input_path)
            changes_since_save = 0
            print(f"\n  [Auto-saved at question {i + 1}]")

    testset["questions"] = questions
    testset["metadata"]["updated_at"] = datetime.now().isoformat()

    session_duration = time.time() - session_start

    audit_entry = {
        "event": "review_session",
        "timestamp": datetime.now().isoformat(),
        "start_from": start_from,
        "total_questions": total,
        "session_approved": session_approved,
        "session_rejected": session_rejected,
        "session_skipped": session_skipped,
        "session_duration_sec": round(session_duration, 1),
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

    print(f"\n{SEPARATOR}")
    print("  Review Session Summary")
    print(f"  {format_progress_bar(final_approved + final_rejected, total)}")
    print(
        f"  Total: {total} | Approved: {final_approved} | "
        f"Rejected: {final_rejected} | Pending: {final_pending}"
    )
    print(
        f"  This session: {session_approved} approved, "
        f"{session_rejected} rejected, {session_skipped} skipped"
    )
    if session_duration > 0 and (session_approved + session_rejected) > 0:
        avg_time = session_duration / (session_approved + session_rejected)
        print(f"  Avg time per decision: {avg_time:.1f}s")
    print(f"  Duration: {session_duration:.0f}s")
    print(f"  Saved to: {input_path}")
    print(SEPARATOR)


def run_ai_review(
    input_path: Path,
    llm_preset: str | None = None,
    dry_run: bool = False,
) -> None:
    """Run AI pre-review on all questions.

    Args:
        input_path: Path to the golden test set JSON file.
        llm_preset: LLM preset name to use for review.
        dry_run: If True, only display results without saving.
    """
    config = load_config()
    reviewer = AIReviewer(config, llm_preset=llm_preset)

    testset = load_testset(input_path)
    questions = testset.get("questions", [])

    if not questions:
        logger.error("No questions found in test set")
        return

    print(f"\n{SEPARATOR}")
    print("  AI Pre-Review")
    print(f"  Model: {reviewer.llm_config.get('model_name', 'unknown')}")
    print(f"  Questions: {len(questions)}")
    print(SEPARATOR)

    reviewer.review_questions(questions)

    summary = reviewer.get_tier_summary(questions)

    print(f"\n{SEPARATOR}")
    print("  AI Review Results")
    print(f"{'=' * 80}")
    print(f"  Tier A (auto-approve): {len(summary['A'])} questions")
    print(f"  Tier B (needs review): {len(summary['B'])} questions")
    print(f"  Tier C (likely reject): {len(summary['C'])} questions")
    print(f"  Total: {len(questions)}")

    if summary["C"]:
        print("\n  Tier C questions (first 10):")
        for q_id in summary["C"][:10]:
            q = next((q for q in questions if q.get("id") == q_id), None)
            if q:
                ai = q.get("metadata", {}).get("ai_review", {})
                comment = ai.get("overall_comment", "")
                print(f"    {q_id}: {comment}")

    if not dry_run:
        create_backup(input_path)
        testset["questions"] = questions
        testset["metadata"]["updated_at"] = datetime.now().isoformat()
        audit_entry = {
            "event": "ai_review",
            "timestamp": datetime.now().isoformat(),
            "llm_preset": llm_preset or "default",
            "tier_a": len(summary["A"]),
            "tier_b": len(summary["B"]),
            "tier_c": len(summary["C"]),
        }
        testset["metadata"].setdefault("audit_log", []).append(audit_entry)
        save_testset(testset, input_path)
        print(f"\n  Results saved to {input_path}")
    else:
        print("\n  (DRY RUN - no changes saved)")

    print(SEPARATOR)


def run_tiered_review(
    input_path: Path,
    llm_preset: str | None = None,
    reviewer: str | None = None,
    auto_approve_tier_a: bool = True,
) -> None:
    """Run tiered review: AI pre-review then interactive review for B/C tiers.

    Args:
        input_path: Path to the golden test set JSON file.
        llm_preset: LLM preset name to use for AI review.
        reviewer: Optional reviewer identifier.
        auto_approve_tier_a: If True, automatically approve Tier A questions.
    """
    config = load_config()
    ai_reviewer = AIReviewer(config, llm_preset=llm_preset)

    testset = load_testset(input_path)
    questions = testset.get("questions", [])

    if not questions:
        logger.error("No questions found in test set")
        return

    create_backup(input_path)

    needs_ai = [q for q in questions if not q.get("metadata", {}).get("ai_review")]
    if needs_ai:
        print(f"\n{SEPARATOR}")
        print("  Step 1: AI Pre-Review")
        print(f"  Questions to review: {len(needs_ai)}")
        print(f"  Model: {ai_reviewer.llm_config.get('model_name', 'unknown')}")
        print(SEPARATOR)

        ai_reviewer.review_questions(questions)
    else:
        print("\n  All questions already have AI reviews, skipping AI pre-review step")

    summary = ai_reviewer.get_tier_summary(questions)

    print(f"\n{SEPARATOR}")
    print("  AI Review Summary")
    print(f"  Tier A (auto-approve): {len(summary['A'])}")
    print(f"  Tier B (needs review): {len(summary['B'])}")
    print(f"  Tier C (likely reject): {len(summary['C'])}")
    print(SEPARATOR)

    if auto_approve_tier_a and summary["A"]:
        tier_a_count = 0
        for q in questions:
            ai = q.get("metadata", {}).get("ai_review", {})
            if ai and ai_reviewer.classify_tier(ai) == "A":
                current_status = q.get("metadata", {}).get("review_status")
                if current_status not in (
                    REVIEW_STATUS_APPROVED,
                    REVIEW_STATUS_REJECTED,
                    "auto_approved",
                ):
                    q.setdefault("metadata", {})
                    q["metadata"]["reviewed"] = True
                    q["metadata"]["review_status"] = "auto_approved"
                    q["metadata"]["reviewed_at"] = datetime.now().isoformat()
                    q["metadata"]["review_notes"] = (
                        f"ai_tier_a: auto-approved (score={ai.get('overall_score', '?')})"
                    )
                    tier_a_count += 1
        print(f"\n  Auto-approved {tier_a_count} Tier A questions")

    testset["questions"] = questions
    testset["metadata"]["updated_at"] = datetime.now().isoformat()
    audit_entry = {
        "event": "tiered_review_ai_phase",
        "timestamp": datetime.now().isoformat(),
        "llm_preset": llm_preset or "default",
        "tier_a": len(summary["A"]),
        "tier_b": len(summary["B"]),
        "tier_c": len(summary["C"]),
        "auto_approved_tier_a": auto_approve_tier_a,
    }
    testset["metadata"].setdefault("audit_log", []).append(audit_entry)
    save_testset(testset, input_path)

    tier_bc_questions = [
        (i, q)
        for i, q in enumerate(questions)
        if q.get("metadata", {}).get("ai_review")
        and ai_reviewer.classify_tier(q["metadata"]["ai_review"]) in ("B", "C")
        and q.get("metadata", {}).get("review_status")
        not in (
            REVIEW_STATUS_APPROVED,
            REVIEW_STATUS_REJECTED,
            "auto_approved",
        )
    ]

    if not tier_bc_questions:
        print("\n  No Tier B/C questions need human review. Done!")
        return

    tier_bc_count = len(tier_bc_questions)
    print(f"\n{SEPARATOR}")
    print("  Step 2: Human Review (Tier B/C)")
    print(f"  Questions to review: {tier_bc_count}")
    print(f"  Tier B: {len(summary['B'])} | Tier C: {len(summary['C'])}")
    print(SEPARATOR)

    pdf_viewer = PDFViewer(data_dir=config.get("data_dir", "data"))

    save_interval = 5
    changes_since_save = 0
    session_start = time.time()
    session_approved = 0
    session_rejected = 0

    for review_idx, (original_idx, question) in enumerate(tier_bc_questions):
        display_question(
            question,
            review_idx + 1,
            tier_bc_count,
            pdf_viewer=pdf_viewer,
            show_chunks=True,
        )

        result = review_question(
            question,
            reviewer=reviewer,
            pdf_viewer=pdf_viewer,
            show_chunks=True,
        )

        if result.get("_action") == "quit":
            break

        questions[original_idx] = result
        changes_since_save += 1

        final_status = result.get("metadata", {}).get("review_status")
        if final_status == REVIEW_STATUS_APPROVED:
            session_approved += 1
        elif final_status == REVIEW_STATUS_REJECTED:
            session_rejected += 1

        if changes_since_save >= save_interval:
            testset["questions"] = questions
            testset["metadata"]["updated_at"] = datetime.now().isoformat()
            save_testset(testset, input_path)
            changes_since_save = 0

    session_duration = time.time() - session_start

    testset["questions"] = questions
    testset["metadata"]["updated_at"] = datetime.now().isoformat()
    audit_entry = {
        "event": "tiered_review_human_phase",
        "timestamp": datetime.now().isoformat(),
        "reviewer": reviewer,
        "tier_bc_reviewed": session_approved + session_rejected,
        "session_approved": session_approved,
        "session_rejected": session_rejected,
        "session_duration_sec": round(session_duration, 1),
    }
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
    final_pending = len(questions) - final_approved - final_rejected

    print(f"\n{SEPARATOR}")
    print("  Tiered Review Complete")
    print(f"  {format_progress_bar(final_approved + final_rejected, len(questions))}")
    print(
        f"  Total: {len(questions)} | Approved: {final_approved} | "
        f"Rejected: {final_rejected} | Pending: {final_pending}"
    )
    print(f"  Human session: {session_approved} approved, {session_rejected} rejected")
    print(f"  Duration: {session_duration:.0f}s")
    print(SEPARATOR)


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
        help="With --auto-approve or --ai-review, only report what would be done",
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
    parser.add_argument(
        "--ai-review",
        action="store_true",
        help="Run AI pre-review on all questions",
    )
    parser.add_argument(
        "--tiered-review",
        action="store_true",
        help="Run tiered review: AI pre-review then human review for B/C tiers",
    )
    parser.add_argument(
        "--llm-preset",
        type=str,
        default=None,
        help="LLM preset name for AI review (default: uses active_mode)",
    )
    parser.add_argument(
        "--sort-by-score",
        action="store_true",
        help="Sort questions by AI score (lowest first) for review",
    )
    parser.add_argument(
        "--no-chunks",
        action="store_true",
        help="Disable chunk context display",
    )
    parser.add_argument(
        "--no-pdf",
        action="store_true",
        help="Disable PDF viewer integration",
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
    elif args.ai_review:
        run_ai_review(
            input_path=Path(args.input),
            llm_preset=args.llm_preset,
            dry_run=args.dry_run,
        )
    elif args.tiered_review:
        run_tiered_review(
            input_path=Path(args.input),
            llm_preset=args.llm_preset,
            reviewer=args.reviewer,
        )
    else:
        config = load_config()
        pdf_viewer = (
            None if args.no_pdf else PDFViewer(data_dir=config.get("data_dir", "data"))
        )

        if args.sort_by_score:
            testset = load_testset(Path(args.input))
            questions = testset.get("questions", [])
            questions_with_scores = [
                (i, q)
                for i, q in enumerate(questions)
                if q.get("metadata", {}).get("ai_review")
                and q.get("metadata", {}).get("review_status")
                not in (
                    REVIEW_STATUS_APPROVED,
                    REVIEW_STATUS_REJECTED,
                    "auto_approved",
                )
            ]
            questions_with_scores.sort(
                key=lambda x: x[1]
                .get("metadata", {})
                .get("ai_review", {})
                .get("overall_score", 5.0)
            )
            if questions_with_scores:
                print(
                    f"\n  Sorted {len(questions_with_scores)} questions by AI score (lowest first)"
                )
                print(
                    f"  Score range: {questions_with_scores[0][1]['metadata']['ai_review']['overall_score']:.1f} - {questions_with_scores[-1][1]['metadata']['ai_review']['overall_score']:.1f}"
                )

        run_review(
            input_path=Path(args.input),
            start_from=args.start_from,
            include_auto_approved=args.include_auto_approved,
            reviewer=args.reviewer,
            pdf_viewer=pdf_viewer,
            show_chunks=not args.no_chunks,
        )


if __name__ == "__main__":
    main()
