from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

REVIEW_STATUS_APPROVED = "approved"
REVIEW_STATUS_NEEDS_REVISION = "needs_revision"
REVIEW_STATUS_REJECTED = "rejected"
REVIEW_STATUS_PENDING = "pending"
REVIEW_STATUS_AUTO_APPROVED = "auto_approved"

QUALITY_DRAFT = "draft"
QUALITY_AI_REVIEWED = "ai_reviewed"
QUALITY_AUTO_APPROVED = "auto_approved"
QUALITY_HUMAN_REVIEWED = "human_reviewed"
QUALITY_APPROVED = "approved"

ALL_APPROVED_STATUSES = {REVIEW_STATUS_APPROVED, REVIEW_STATUS_AUTO_APPROVED}


@dataclass
class ReviewSessionConfig:
    reviewer: str | None = None
    start_from: int = 1
    include_auto_approved: bool = False
    only_new: bool = False
    auto_approve_tier_a: bool = True
    save_interval: int = 5


@dataclass
class ReviewAction:
    action: str
    question: dict[str, Any] | None = None
    edits: dict[str, Any] | None = None
    notes: str = ""


@dataclass
class ReviewSessionState:
    total: int = 0
    approved: int = 0
    rejected: int = 0
    pending: int = 0
    session_approved: int = 0
    session_rejected: int = 0
    session_skipped: int = 0
    current_index: int = 0
    is_complete: bool = False


class ReviewEngine:
    def __init__(self, config: ReviewSessionConfig | None = None) -> None:
        self.config = config or ReviewSessionConfig()

    def initialize(
        self, questions: list[dict[str, Any]]
    ) -> tuple[list[dict[str, Any]], ReviewSessionState]:
        state = ReviewSessionState(total=len(questions))

        for q in questions:
            status = q.get("metadata", {}).get("review_status")
            if status in ALL_APPROVED_STATUSES:
                state.approved += 1
            elif status == REVIEW_STATUS_REJECTED:
                state.rejected += 1
            else:
                state.pending += 1

        return questions, state

    def should_skip(self, question: dict[str, Any], state: ReviewSessionState) -> bool:
        status = question.get("metadata", {}).get("review_status")

        if status == REVIEW_STATUS_REJECTED:
            return True
        if status in ALL_APPROVED_STATUSES and not self.config.include_auto_approved:
            return True

        return bool(self.config.only_new and status != REVIEW_STATUS_PENDING)

    def apply_action(
        self,
        question: dict[str, Any],
        action: str,
        edits: dict[str, Any] | None = None,
        notes: str = "",
    ) -> dict[str, Any]:
        now = datetime.now().isoformat()
        metadata = question.setdefault("metadata", {})

        if action == "approve":
            metadata["review_status"] = REVIEW_STATUS_APPROVED
            metadata["reviewed_at"] = now
            if notes:
                metadata["review_notes"] = notes

        elif action == "reject":
            metadata["review_status"] = REVIEW_STATUS_REJECTED
            metadata["reviewed_at"] = now
            if notes:
                metadata["review_notes"] = notes

        elif action == "skip":
            pass

        elif action == "edit":
            if edits:
                for key, value in edits.items():
                    question[key] = value
            metadata["review_status"] = REVIEW_STATUS_APPROVED
            metadata["reviewed_at"] = now
            metadata["review_notes"] = notes or "edited during review"

        elif action == "auto_approve":
            metadata["review_status"] = REVIEW_STATUS_AUTO_APPROVED
            metadata["reviewed_at"] = now

        if self.config.reviewer:
            metadata["reviewer"] = self.config.reviewer

        return question

    def update_state(
        self, state: ReviewSessionState, action: str, is_quit: bool = False
    ) -> ReviewSessionState:
        if is_quit:
            return state

        if action == "approve":
            state.session_approved += 1
            state.approved += 1
            state.pending -= 1
        elif action == "reject":
            state.session_rejected += 1
            state.rejected += 1
            state.pending -= 1
        elif action == "skip":
            state.session_skipped += 1

        state.current_index += 1
        if state.current_index >= state.total:
            state.is_complete = True

        return state

    def compute_review_progress(
        self, questions: list[dict[str, Any]]
    ) -> dict[str, int]:
        total = len(questions)
        approved = sum(
            1
            for q in questions
            if q.get("metadata", {}).get("review_status") in ALL_APPROVED_STATUSES
        )
        rejected = sum(
            1
            for q in questions
            if q.get("metadata", {}).get("review_status") == REVIEW_STATUS_REJECTED
        )
        pending = total - approved - rejected
        return {
            "total": total,
            "approved": approved,
            "rejected": rejected,
            "pending": pending,
        }

    def determine_quality_status(
        self, questions: list[dict[str, Any]], current_status: str = ""
    ) -> str:
        progress = self.compute_review_progress(questions)

        if progress["pending"] == 0 and progress["approved"] > 0:
            return QUALITY_HUMAN_REVIEWED

        if progress["approved"] > 0 or progress["rejected"] > 0:
            return QUALITY_AI_REVIEWED

        return current_status or QUALITY_DRAFT
