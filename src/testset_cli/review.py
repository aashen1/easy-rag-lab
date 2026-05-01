from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from loguru import logger

from src.testset_review.display import (
    format_ai_review,
    format_chunk_context,
    format_header,
    format_question_body,
    format_question_header,
    format_review_prompt,
    format_session_summary,
)
from src.testset_review.engine import (
    ReviewEngine,
    ReviewSessionConfig,
)
from src.testset_review.pdf_viewer import PDFViewer


def run_review(args) -> int:
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

    config = ReviewSessionConfig(
        reviewer=getattr(args, "reviewer", None),
        start_from=getattr(args, "start_from", 1),
        include_auto_approved=getattr(args, "include_auto_approved", False),
        only_new=getattr(args, "only_new", False),
    )
    engine = ReviewEngine(config)
    questions, state = engine.initialize(questions)

    pdf_viewer = None
    if not getattr(args, "no_pdf", False):
        pdf_viewer = PDFViewer(data_dir=getattr(args, "data_dir", "data"))

    print(
        format_header(
            filepath=str(input_path),
            total=state.total,
            approved=state.approved,
            rejected=state.rejected,
            pending=state.pending,
            reviewer=config.reviewer,
            viewer_type=pdf_viewer.viewer_type if pdf_viewer else None,
        )
    )

    save_interval = 5
    changes_since_save = 0
    session_start = time.time()

    for i in range(config.start_from - 1, state.total):
        question = questions[i]

        if engine.should_skip(question, state):
            continue

        ai_review = question.get("metadata", {}).get("ai_review")
        tier = ""
        if ai_review:
            tier = ai_review.get("tier", "")

        print(format_question_header(question, i + 1, state.total, tier=tier))
        print(format_question_body(question))

        if ai_review:
            print(format_ai_review(ai_review))

        show_chunks = not getattr(args, "no_chunks", False)
        if show_chunks and pdf_viewer:
            chunks = pdf_viewer.get_chunks_for_question(question)
            if chunks:
                chunk_texts = [c.get("text", "") for c in chunks]
                print(format_chunk_context(chunk_texts))

        try:
            choice = input(format_review_prompt()).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("\n\nExiting review session...")
            break

        action = ""
        if choice in ("a", "approve"):
            action = "approve"
        elif choice in ("r", "reject"):
            action = "reject"
        elif choice in ("e", "edit"):
            action = "edit"
            print('  Enter edits as JSON (e.g. {"question": "new text"}):')
            edit_input = input("  Edits > ").strip()
            try:
                edits = json.loads(edit_input)
            except json.JSONDecodeError:
                print("  Invalid JSON, skipping edit")
                action = "skip"
            questions[i] = engine.apply_action(question, action, edits=edits)
            changes_since_save += 1
            engine.update_state(state, action)
            continue
        elif choice in ("s", "skip"):
            action = "skip"
        elif choice in ("q", "quit"):
            test_set["metadata"]["last_reviewed_index"] = i
            break
        else:
            print(f"  Unknown action: {choice}")
            action = "skip"

        questions[i] = engine.apply_action(question, action)
        changes_since_save += 1
        engine.update_state(state, action)

        if changes_since_save >= save_interval:
            test_set["questions"] = questions
            test_set["metadata"]["updated_at"] = datetime.now().isoformat()
            test_set["metadata"]["last_reviewed_index"] = i
            with open(input_path, "w", encoding="utf-8") as f:
                json.dump(test_set, f, ensure_ascii=False, indent=2)
            changes_since_save = 0
            print(f"\n  [Auto-saved at question {i + 1}]")

    test_set["questions"] = questions
    test_set["metadata"]["updated_at"] = datetime.now().isoformat()
    test_set["metadata"].pop("last_reviewed_index", None)

    progress = engine.compute_review_progress(questions)
    test_set["metadata"]["review_progress"] = progress
    if progress["pending"] == 0:
        test_set["metadata"]["quality_status"] = "human_reviewed"
    else:
        test_set["metadata"].setdefault("quality_status", "ai_reviewed")

    with open(input_path, "w", encoding="utf-8") as f:
        json.dump(test_set, f, ensure_ascii=False, indent=2)

    session_duration = time.time() - session_start
    final_approved = progress["approved"]
    final_rejected = progress["rejected"]
    final_pending = progress["pending"]

    if (state.session_approved + state.session_rejected) > 0:
        avg_time = session_duration / (state.session_approved + state.session_rejected)
    else:
        avg_time = 0.0

    print(
        format_session_summary(
            total=state.total,
            approved=final_approved,
            rejected=final_rejected,
            pending=final_pending,
            session_approved=state.session_approved,
            session_rejected=state.session_rejected,
            session_skipped=state.session_skipped,
            avg_time=avg_time,
            duration=session_duration,
            filepath=str(input_path),
        )
    )

    return 0
