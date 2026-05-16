"""Question generator for test set generation.

This module provides the QuestionGenerator class that handles
the core logic of generating individual questions.
"""

from typing import Any

from loguru import logger

from src.generator import Generator
from src.test_generation.llm_caller import (
    generate_irrelevant_question,
    generate_missing_question,
    generate_question_with_evidence,
)
from src.test_generation.models import QUESTION_TYPES
from src.test_generation.segment_builder import (
    compact_segments,
    select_candidate_segments,
    select_segments_for_question_type,
)
from src.test_generation.validators import (
    validate_answer_evidence_consistency,
    validate_evidence,
    validate_numerical_accuracy,
    verify_excerpt_in_document,
)


class QuestionGenerator:
    """Generator for individual questions.

    This class encapsulates the core logic for generating
    individual questions from document segments.

    Args:
        config: Application configuration dictionary.
        max_retries: Maximum number of retries for LLM calls.
        multi_hop_candidate_count: Number of candidate segments for multi-hop questions.
        segment_sampling_strategy: Strategy for sampling segments.
        compact_segment_max_chars: Maximum characters for compact segments.
        quote_fuzzy_match_threshold: Threshold for fuzzy quote matching.
    """

    def __init__(
        self,
        config: dict[str, Any],
        max_retries: int = 3,
        multi_hop_candidate_count: int = 4,
        segment_sampling_strategy: str = "random",
        compact_segment_max_chars: int = 6000,
        quote_fuzzy_match_threshold: float = 0.85,
    ):
        self.config = config
        self.max_retries = max_retries
        self.multi_hop_candidate_count = multi_hop_candidate_count
        self.segment_sampling_strategy = segment_sampling_strategy
        self.compact_segment_max_chars = compact_segment_max_chars
        self.quote_fuzzy_match_threshold = quote_fuzzy_match_threshold

    def generate_hybrid_question(
        self,
        segments: list[dict[str, Any]],
        doc_chunks: list[dict[str, Any]],
        question_type: str,
        generator: Generator,
        source_path: str,
        doc_name: str = "",
        doc_content: str = "",
    ) -> dict[str, Any] | None:
        """Generate a single question using hybrid strategy.

        Args:
            segments: List of document segments.
            doc_chunks: List of chunk dictionaries for the document.
            question_type: Type of question to generate.
            generator: Generator instance for LLM calls.
            source_path: Source path of the document.
            doc_name: Name of the document.
            doc_content: Full document content for fallback verification.

        Returns:
            Dictionary with question data, or None if generation fails.
        """
        multi_hop_types = {"multi_fact", "reasoning", "comparative"}

        if question_type in multi_hop_types:
            selected_segments = select_candidate_segments(
                segments,
                question_type,
                self.multi_hop_candidate_count,
                self.segment_sampling_strategy,
            )
        else:
            selected_segments = select_segments_for_question_type(
                segments, question_type, 1, self.segment_sampling_strategy
            )

        if not selected_segments and question_type != "irrelevant":
            logger.debug(f"No segments selected for question type: {question_type}")
            return None

        if question_type == "irrelevant":
            return generate_irrelevant_question(
                doc_name=doc_name,
                generator=generator,
                max_retries=self.max_retries,
            )

        if question_type == "missing":
            selected_segments = select_segments_for_question_type(
                segments, question_type, 1, self.segment_sampling_strategy
            )
            if selected_segments:
                selected_segments = compact_segments(
                    selected_segments, self.compact_segment_max_chars
                )
            return generate_missing_question(
                selected_segments=selected_segments,
                generator=generator,
            )

        compact_types = {"single_fact", "adversarial"}
        if question_type in compact_types and selected_segments:
            selected_segments = compact_segments(
                selected_segments, self.compact_segment_max_chars
            )

        for _attempt in range(self.max_retries):
            qa = generate_question_with_evidence(
                selected_segments=selected_segments,
                question_type=question_type,
                generator=generator,
            )

            if qa is None:
                continue

            qa["question_type"] = QUESTION_TYPES.get(question_type, question_type)

            evidence_list = qa.get("evidence", [])
            if not evidence_list:
                if question_type == "missing":
                    qa["ground_truth_excerpt"] = ""
                    return qa
                logger.debug(f"No evidence provided for question type: {question_type}")
                continue

            if question_type == "missing":
                logger.debug("Missing type question has evidence, retrying...")
                continue

            validation = validate_evidence(
                evidence_list,
                selected_segments,
                question_type,
                self.quote_fuzzy_match_threshold,
            )

            if not validation["valid"]:
                invalid_quotes = validation.get("invalid_quotes", [])
                reasons = [iq.get("reason", "unknown") for iq in invalid_quotes]
                logger.debug(
                    f"Evidence validation failed for question type {question_type}: "
                    f"{'; '.join(reasons)}"
                )
                continue

            if validation.get("evidence_text"):
                qa["evidence_text"] = validation["evidence_text"]

            if validation.get("excerpt"):
                qa["ground_truth_excerpt"] = validation["excerpt"]

            if question_type in {"single_fact", "multi_fact"}:
                excerpt = qa.get("ground_truth_excerpt", "")
                if excerpt and doc_content:
                    found, _ = verify_excerpt_in_document(
                        excerpt, doc_content, self.quote_fuzzy_match_threshold
                    )
                    if not found:
                        logger.debug(
                            f"Excerpt not found in document for {question_type} question"
                        )
                        continue

            if qa.get("answer"):
                answer_valid = validate_answer_evidence_consistency(
                    qa["answer"], evidence_list
                )
                if not answer_valid:
                    logger.debug(
                        f"Answer-evidence consistency check failed for "
                        f"{question_type} question"
                    )
                    continue

            if qa.get("answer"):
                numerical_valid, _ = validate_numerical_accuracy(qa)
                if not numerical_valid:
                    logger.debug(
                        f"Numerical accuracy check failed for {question_type} question"
                    )
                    continue

            return qa

        return None

    def post_process_question(
        self,
        qa: dict[str, Any],
        doc_content: str,
        seen_questions: set[str],
        *,
        check_answer_consistency: bool = False,
        golden_metadata: dict | None = None,
        validation_strictness: dict[str, str] | None = None,
        check_proper_nouns: bool = True,
    ) -> bool:
        """Post-process a generated question.

        Args:
            qa: Question dictionary to process.
            doc_content: Full document content for verification.
            seen_questions: Set of already seen question texts.
            check_answer_consistency: If True, run validate_answer_consistency.
            golden_metadata: If not None, add golden-specific metadata fields.
            validation_strictness: Strictness levels for different question types.
            check_proper_nouns: Whether to check proper nouns in validation.

        Returns:
            True if the question is valid and should be kept, False otherwise.
        """
        from src.test_generation.validators import validate_answer_consistency

        question_text = qa.get("question", "")
        if not question_text:
            return False

        if question_text in seen_questions:
            logger.debug(f"Duplicate question detected: {question_text[:50]}...")
            return False

        q_type_raw = qa.get("question_type", "")
        q_type = self._chinese_to_type_key(q_type_raw) or q_type_raw

        is_valid, correction = validate_numerical_accuracy(qa)
        if not is_valid and correction:
            logger.warning(f"Numerical accuracy issue: {correction['suggestion']}")
            for err in correction.get("errors", []):
                wrong_val = err["answer_value"]
                correct_val = err["correct_value"]
                answer_text = qa.get("answer", "")
                qa["answer"] = answer_text.replace(f"{wrong_val}", f"{correct_val}")
            qa.setdefault("metadata", {})
            qa["metadata"]["numerical_auto_corrected"] = True

        if check_answer_consistency:
            is_consistent, consistency_warning = validate_answer_consistency(qa)
            if not is_consistent:
                logger.warning(f"Answer consistency issue: {consistency_warning}")
                qa.setdefault("metadata", {})
                qa["metadata"]["answer_consistency_warning"] = consistency_warning

        if qa.get("ground_truth_excerpt"):
            excerpt = qa["ground_truth_excerpt"]
            found, _ = verify_excerpt_in_document(
                excerpt, doc_content, self.quote_fuzzy_match_threshold
            )
            qa.setdefault("metadata", {})
            qa["metadata"]["excerpt_verified"] = found
            if not found:
                logger.debug(
                    f"Excerpt not found in document during post-processing: "
                    f"{excerpt[:50]}..."
                )
                return False

        evidence_list = qa.get("evidence", [])
        if evidence_list and q_type not in ("irrelevant", "missing"):
            strictness = (validation_strictness or {}).get(q_type, "moderate")

            if strictness == "none":
                pass
            elif strictness == "lenient":
                is_consistent, issues = validate_answer_evidence_consistency(
                    qa.get("answer", ""),
                    evidence_list,
                    check_proper_nouns=check_proper_nouns,
                )
                if not is_consistent:
                    qa.setdefault("metadata", {})
                    qa["metadata"]["answer_evidence_issues"] = issues
            else:
                is_consistent, issues = validate_answer_evidence_consistency(
                    qa.get("answer", ""),
                    evidence_list,
                    check_proper_nouns=check_proper_nouns,
                )
                if not is_consistent:
                    logger.warning(
                        f"Answer-evidence inconsistency for question {qa.get('id')}: "
                        f"{'; '.join(issues)}"
                    )
                    qa.setdefault("metadata", {})
                    qa["metadata"]["answer_evidence_issues"] = issues

                    numerical_issues = [i for i in issues if i.startswith("数值")]
                    proper_noun_issues = [i for i in issues if i.startswith("专有名词")]

                    if strictness == "strict":
                        should_reject = len(issues) > 3 or len(numerical_issues) > 1
                    else:
                        should_reject = len(numerical_issues) > 2 or (
                            len(proper_noun_issues) > 0 and len(issues) > 2
                        )

                    if should_reject:
                        logger.warning(
                            f"Rejecting question {qa.get('id')} due to "
                            f"answer-evidence issues"
                        )
                        return False

        if golden_metadata is not None:
            qa.setdefault("metadata", {})
            qa["metadata"]["golden"] = True
            qa["metadata"].update(golden_metadata)

        seen_questions.add(question_text)
        return True

    def _chinese_to_type_key(self, chinese_type: str) -> str | None:
        """Convert Chinese question type to English key.

        Args:
            chinese_type: Chinese question type string.

        Returns:
            English key like 'single_fact', or None if not found.
        """
        from src.test_generation.models import QUESTION_TYPES

        reverse_map = {v: k for k, v in QUESTION_TYPES.items()}
        return reverse_map.get(chinese_type)
