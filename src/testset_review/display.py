from __future__ import annotations

from typing import Any

SEPARATOR = "=" * 80
THIN_SEP = "-" * 80


def format_progress_bar(current: int, total: int, width: int = 40) -> str:
    if total == 0:
        return f"[{' ' * width}] 0%"
    pct = min(100, int(current / total * 100))
    filled = int(width * current / total)
    bar = "█" * filled + "░" * (width - filled)
    return f"[{bar}] {pct}%"


def format_header(
    filepath: str,
    total: int,
    approved: int,
    rejected: int,
    pending: int,
    reviewer: str | None = None,
    viewer_type: str | None = None,
) -> str:
    lines = [
        SEPARATOR,
        "  Test Set Review Tool",
        f"  File: {filepath}",
    ]
    if reviewer:
        lines.append(f"  Reviewer: {reviewer}")
    if viewer_type:
        lines.append(f"  PDF Viewer: {viewer_type}")
    lines.append(
        f"  Total: {total} | Approved: {approved} | "
        f"Rejected: {rejected} | Pending: {pending}"
    )
    lines.append(f"  {format_progress_bar(approved + rejected, total)}")
    lines.append(SEPARATOR)
    return "\n".join(lines)


def format_question_header(
    question: dict[str, Any],
    index: int,
    total: int,
    tier: str = "",
) -> str:
    q_id = question.get("id", "?")
    q_type = question.get("question_type", "?")
    category = question.get("category", "")
    difficulty = question.get("difficulty", "?")
    source_count = len(question.get("source_files", []))

    lines = []
    lines.append(f"\n{THIN_SEP}")
    lines.append(f"  Question {index}/{total}  [ID: {q_id}]")
    meta_parts = [f"type: {q_type}"]
    if category:
        meta_parts.append(f"category: {category}")
    meta_parts.append(f"difficulty: {difficulty}")
    meta_parts.append(f"sources: {source_count}")
    if tier:
        meta_parts.append(f"tier: {tier}")
    lines.append(f"  {' | '.join(meta_parts)}")
    lines.append(THIN_SEP)

    return "\n".join(lines)


def format_question_body(question: dict[str, Any]) -> str:
    text = question.get("question", "(no question)")
    lines = [f"\n  Q: {text}"]

    source_files = question.get("source_files", [])
    if source_files:
        files = ", ".join(source_files[:3])
        if len(source_files) > 3:
            files += f" (+{len(source_files) - 3})"
        lines.append(f"  Source files: {files}")

    return "\n".join(lines)


def format_chunk_context(chunks: list[str], max_lines: int = 8) -> str:
    if not chunks:
        return ""

    lines = ["  --- Chunk Context ---"]
    for i, chunk in enumerate(chunks[:3]):
        display = chunk[:200].replace("\n", " ")
        if len(chunk) > 200:
            display += "..."
        lines.append(f"  [{i + 1}] {display}")
    if len(chunks) > 3:
        lines.append(f"  ... and {len(chunks) - 3} more chunks")

    return "\n".join(lines)


def format_ai_review(ai_review: dict[str, Any]) -> str:
    if not ai_review:
        return ""

    score = ai_review.get("overall_score", "?")
    tier = ai_review.get("tier", "?")
    comment = ai_review.get("overall_comment", "")

    lines = [f"  AI Score: {score}/10 | Tier: {tier}"]
    if comment:
        lines.append(f"  AI Comment: {comment[:300]}")
    return "\n".join(lines)


def format_review_prompt() -> str:
    return "\n  Actions: [a]pprove  [r]eject  [e]dit  [s]kip  [q]uit\n  Choice > "


def format_session_summary(
    total: int,
    approved: int,
    rejected: int,
    pending: int,
    session_approved: int,
    session_rejected: int,
    session_skipped: int,
    avg_time: float,
    duration: float,
    filepath: str,
) -> str:
    lines = [
        "",
        SEPARATOR,
        "  Review Session Summary",
        f"  {format_progress_bar(approved + rejected, total)}",
        f"  Total: {total} | Approved: {approved} | "
        f"Rejected: {rejected} | Pending: {pending}",
        f"  This session: {session_approved} approved, "
        f"{session_rejected} rejected, {session_skipped} skipped",
    ]
    if avg_time > 0:
        lines.append(f"  Avg time per decision: {avg_time:.1f}s")
    lines.append(f"  Duration: {duration:.0f}s")
    lines.append(f"  Saved to: {filepath}")
    lines.append(SEPARATOR)
    return "\n".join(lines)
