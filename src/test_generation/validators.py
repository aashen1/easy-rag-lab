import re
from typing import Any

from loguru import logger

from src.test_generation.chunk_locator import verify_quote_in_segment
from src.test_generation.models import (
    MIN_QUOTE_LENGTH,
    MIN_QUOTE_LENGTH_CJK,
    MIN_QUOTE_LENGTH_DEFAULT,
)


def validate_numerical_accuracy(
    question_data: dict[str, Any],
) -> tuple[bool, dict[str, Any] | None]:
    """Validate numerical accuracy in answer against ground_truth_excerpt.

    Detects 10x unit conversion errors where excerpt has large numbers
    in yuan but answer incorrectly converts to yi-yuan.

    Args:
        question_data: Dictionary containing 'answer' and
            'ground_truth_excerpt'.

    Returns:
        Tuple of (is_valid, correction). is_valid is True if numbers
        are consistent. correction is None or contains fix information.
    """
    answer = question_data.get("answer", "")
    excerpt = question_data.get("ground_truth_excerpt", "")

    if not answer or not excerpt:
        return True, None

    excerpt_nums_raw = re.findall(r"[\d,]{8,}(?:\.\d+)?", excerpt)
    excerpt_yi_values: list[float] = []
    for raw_num in excerpt_nums_raw:
        try:
            clean = raw_num.replace(",", "")
            val = float(clean)
            yi_val = val / 1e8
            if yi_val > 1:
                excerpt_yi_values.append(yi_val)
        except ValueError:
            continue

    if not excerpt_yi_values:
        return True, None

    answer_yi_matches = re.findall(r"([\d,.]+)\s*亿", answer)
    answer_yi_values: list[float] = []
    for num_str in answer_yi_matches:
        try:
            answer_yi_values.append(float(num_str.replace(",", "")))
        except ValueError:
            continue

    if not answer_yi_values:
        return True, None

    errors: list[dict[str, Any]] = []
    for ans_val in answer_yi_values:
        for exc_val in excerpt_yi_values:
            if exc_val == 0:
                continue
            ratio = ans_val / exc_val
            if 9.5 <= ratio <= 10.5:
                errors.append(
                    {
                        "type": "10x_error",
                        "answer_value": ans_val,
                        "excerpt_value_yi": round(exc_val, 2),
                        "correct_value": round(exc_val, 2),
                    }
                )
            elif 0.05 <= ratio <= 0.15:
                errors.append(
                    {
                        "type": "10x_error_reverse",
                        "answer_value": ans_val,
                        "excerpt_value_yi": round(exc_val, 2),
                        "correct_value": round(exc_val, 2),
                    }
                )

    if errors:
        correction = {
            "errors": errors,
            "suggestion": (
                "Answer contains 10x unit conversion errors. "
                "Values in yuan should be divided by 100,000,000 "
                "to convert to yi-yuan."
            ),
        }
        return False, correction

    return True, None


def validate_answer_consistency(
    question_data: dict[str, Any],
) -> tuple[bool, str]:
    """Validate answer for internal consistency, especially sign contradictions.

    Detects cases where an answer describes a value as negative but
    presents it as a positive number (or vice versa), which commonly
    occurs when the source text omits a negative sign.

    Args:
        question_data: Dictionary containing 'answer' and
            'ground_truth_excerpt'.

    Returns:
        Tuple of (is_consistent, warning_message). is_consistent is
        True if no contradictions found.
    """
    answer = question_data.get("answer", "")
    excerpt = question_data.get("ground_truth_excerpt", "")

    if not answer:
        return True, ""

    negative_indicators = ["负值", "为负", "负数", "均为负", "均为负值"]
    has_negative_description = any(ind in answer for ind in negative_indicators)

    if not has_negative_description:
        return True, ""

    answer_numbers = re.findall(r"(-?\d+[\d,.]*\d*|-?\d+)", answer)
    positive_numbers = []
    for num_str in answer_numbers:
        try:
            val = float(num_str.replace(",", ""))
            if val > 0:
                positive_numbers.append(val)
        except ValueError:
            continue

    if not positive_numbers:
        return True, ""

    excerpt_negative_indicators = ["负", "-"]
    excerpt_has_negative = any(ind in excerpt for ind in excerpt_negative_indicators)

    if excerpt_has_negative:
        for num in positive_numbers:
            neg_form = f"-{num}"
            neg_form_comma = f"-{num:,.2f}"
            if neg_form in excerpt or neg_form_comma in excerpt:
                return False, (
                    f"Answer describes value as negative but presents "
                    f"positive number {num}. Source text implies "
                    f"negative value."
                )

    large_positive_with_negative_desc = any(n > 10 for n in positive_numbers)
    if large_positive_with_negative_desc and has_negative_description:
        return False, (
            f"Answer contains positive numbers {positive_numbers} "
            f"but describes them as negative. Likely missing "
            f"negative sign from source text."
        )

    return True, ""


def validate_answer_evidence_consistency(
    answer: str,
    evidence_list: list[dict[str, Any]],
) -> tuple[bool, list[str]]:
    """Validate that key information in answer appears in evidence.

    Checks that numerical values, proper nouns, and key terms in the
    answer can be found in the provided evidence quotes.

    Supports unit conversion (元→亿元, 万→亿) and numerical
    approximation matching.

    Args:
        answer: The generated answer text.
        evidence_list: List of evidence dictionaries, each containing
            a 'quote' key with the source text.

    Returns:
        Tuple of (is_valid, issues). is_valid is True if all key
        information is supported by evidence.
    """
    if not answer:
        return True, []

    issues: list[str] = []

    evidence_text = " ".join(
        e.get("quote", "") for e in evidence_list if e.get("quote")
    )

    if not evidence_text:
        return True, []

    def extract_numbers_with_units(text: str) -> list[tuple[float, str, str]]:
        patterns = [
            (r"(\d+[\d,]*\.?\d*)\s*亿元", "亿"),
            (r"(\d+[\d,]*\.?\d*)\s*万元", "万"),
            (r"(\d+[\d,]*\.?\d*)\s*元", "元"),
            (r"(\d+[\d,]*\.?\d*)\s*%", "%"),
            (r"(\d+[\d,]*\.?\d*)\s*％", "%"),
            (r"(\d+[\d,]*\.?\d*)\s*个百分点", "百分点"),
            (r"(\d+[\d,]*\.?\d*)\s*个", "个"),
            (r"(\d+[\d,]*\.?\d*)", ""),
        ]

        results = []
        for pattern, unit in patterns:
            matches = re.findall(pattern, text)
            for match in matches:
                try:
                    val = float(match.replace(",", ""))
                    results.append((val, unit, f"{match}{unit}"))
                except ValueError:
                    continue
        return results

    def convert_to_base_unit(value: float, unit: str) -> float:
        if unit == "亿":
            return value * 100_000_000
        elif unit == "万":
            return value * 10_000
        elif unit in ("元", ""):
            return value
        else:
            return value

    answer_numbers = extract_numbers_with_units(answer)
    evidence_numbers = extract_numbers_with_units(evidence_text)

    for ans_val, ans_unit, ans_orig in answer_numbers:
        if ans_val < 10:
            continue

        ans_base = convert_to_base_unit(ans_val, ans_unit)

        found = False
        for ev_val, ev_unit, _ev_orig in evidence_numbers:
            ev_base = convert_to_base_unit(ev_val, ev_unit)

            if abs(ans_base - ev_base) / max(ev_base, 1) < 0.01:
                found = True
                break

            if (
                ans_unit == "亿"
                and ev_unit == "元"
                and abs(ans_val - ev_val / 100_000_000) < 0.01
            ):
                found = True
                break

            if (
                ans_unit == "万"
                and ev_unit == "元"
                and abs(ans_val - ev_val / 10_000) < 0.01
            ):
                found = True
                break

            if abs(ans_val - ev_val) / max(ev_val, 1) < 0.05:
                found = True
                break

        if not found:
            issues.append(f"数值 '{ans_orig}' 未在证据中找到")

    proper_nouns = re.findall(
        r"[\u4e00-\u9fff]{2,8}(?:股份|集团|公司|行业|市场|技术|产品|业务)",
        answer,
    )
    suffixes = ["股份", "集团", "公司", "行业", "市场", "技术", "产品", "业务"]
    for noun in proper_nouns:
        if noun in evidence_text:
            continue
        core_found = False
        for suffix in suffixes:
            if noun.endswith(suffix):
                core = noun[: -len(suffix)]
                if len(core) >= 2 and core in evidence_text:
                    core_found = True
                    break
        if not core_found:
            issues.append(f"专有名词 '{noun}' 未在证据中找到")

    return len(issues) == 0, issues


def verify_excerpt_in_document(
    excerpt: str,
    document_content: str,
    min_overlap: int = 15,
) -> bool:
    """Verify that the excerpt can be found in the document content.

    Uses fuzzy matching: strips whitespace and checks for substring
    overlap of at least min_overlap consecutive characters.

    Args:
        excerpt: The ground truth excerpt to verify.
        document_content: The full document content to search in.
        min_overlap: Minimum number of consecutive matching characters.

    Returns:
        True if the excerpt (or a substantial part of it) is found.
    """
    if not excerpt:
        return False

    excerpt_clean = re.sub(r"\s+", "", excerpt)
    doc_clean = re.sub(r"\s+", "", document_content)

    if excerpt_clean in doc_clean:
        return True

    for start in range(0, len(excerpt_clean) - min_overlap + 1, min_overlap // 2):
        window = excerpt_clean[start : start + min_overlap]
        if len(window) >= min_overlap and window in doc_clean:
            return True

    return False


def validate_question_quality(question_data: dict) -> bool:
    """Validate the quality of a generated question.

    Args:
        question_data: Dictionary containing question data.

    Returns:
        True if the question passes quality checks, False otherwise.
    """
    question = question_data.get("question", "")

    authenticity = check_authenticity_rules(question)
    if authenticity["has_issues"]:
        logger.debug(f"Question failed authenticity check: {authenticity['issues']}")
        return False

    if len(question) < 5:
        logger.debug("Question too short")
        return False

    if len(question) > 200:
        logger.debug("Question too long")
        return False

    return True


def check_authenticity_rules(question: str) -> dict[str, Any]:
    """Check if a question follows authenticity rules.

    Args:
        question: The question text to check.

    Returns:
        Dictionary with 'has_issues', 'issues', and 'is_authentic' keys.
    """
    issues = []

    academic_patterns = [
        "根据文档",
        "根据提供的信息",
        "请分析",
        "请说明",
        "请对比",
        "请总结",
        "文档中提到",
        "片段中提到",
    ]
    for pattern in academic_patterns:
        if pattern in question:
            issues.append(f"包含学术化表述：'{pattern}'")

    template_starts = [
        "请问",
        "请解释",
        "请描述",
    ]
    for start in template_starts:
        if question.startswith(start):
            issues.append(f"模板化开头：'{start}'")

    if len(question) > 100:
        issues.append("问题过长，可能不够直接")

    return {
        "has_issues": len(issues) > 0,
        "issues": issues,
        "is_authentic": len(issues) == 0,
    }


def validate_evidence(
    evidence_list: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    question_type: str = "unknown",
    doc_content: str = "",
    min_quote_length: int = MIN_QUOTE_LENGTH,
    fuzzy_match_threshold: float = 0.85,
) -> dict[str, Any]:
    """Validate evidence entries against document segments.

    For each evidence entry, verifies that the segment_index is valid
    and that the quote exists in the specified segment. When the
    segment_index is invalid, falls back to searching the full document.
    Quotes shorter than the adaptive minimum length are rejected as too fragmented.
    The threshold is MIN_QUOTE_LENGTH_CJK (15) for CJK-dominant quotes (>50% CJK
    characters) and MIN_QUOTE_LENGTH_DEFAULT (30) otherwise.

    Args:
        evidence_list: List of evidence dictionaries.
        segments: List of segment dictionaries.
        question_type: Type of question for logging context.
        doc_content: Full document content for fallback verification.
        min_quote_length: Minimum quote length in characters (deprecated, use
            adaptive threshold instead).
        fuzzy_match_threshold: Threshold for fuzzy quote matching.

    Returns:
        Dictionary with keys:
            - valid: bool indicating if all evidence is valid
            - verified_evidence: list of evidence dicts with added
                'verified' field
            - invalid_quotes: list of dicts with 'quote' and 'reason'
    """
    if not evidence_list:
        return {
            "valid": True,
            "verified_evidence": [],
            "invalid_quotes": [],
        }

    segment_map = {seg.get("segment_index", i): seg for i, seg in enumerate(segments)}

    verified_evidence: list[dict[str, Any]] = []
    invalid_quotes: list[dict[str, str]] = []

    for evidence in evidence_list:
        segment_index = evidence.get("segment_index")
        quote = evidence.get("quote", "")

        if segment_index is None:
            verified_evidence.append({**evidence, "verified": False})
            invalid_quotes.append(
                {
                    "quote": quote[:50] + "..." if len(quote) > 50 else quote,
                    "reason": "Missing segment_index",
                }
            )
            continue

        quote_clean = re.sub(r"\s+", "", quote)
        cjk_count = sum(1 for c in quote_clean if "\u4e00" <= c <= "\u9fff")
        cjk_ratio = cjk_count / len(quote_clean) if quote_clean else 0
        adaptive_min_length = (
            MIN_QUOTE_LENGTH_CJK if cjk_ratio > 0.5 else MIN_QUOTE_LENGTH_DEFAULT
        )
        if len(quote_clean) < adaptive_min_length:
            verified_evidence.append({**evidence, "verified": False})
            invalid_quotes.append(
                {
                    "quote": quote[:50] + "..." if len(quote) > 50 else quote,
                    "reason": f"Quote too short (< {adaptive_min_length} chars)",
                }
            )
            logger.debug(
                f"Quote too short ({len(quote_clean)} chars, "
                f"min={adaptive_min_length}, CJK ratio={cjk_ratio:.0%}): "
                f"'{quote[:30]}...' Question type: {question_type}"
            )
            continue

        if segment_index not in segment_map:
            if doc_content:
                doc_verified = verify_excerpt_in_document(quote, doc_content)
                if doc_verified:
                    verified_evidence.append(
                        {
                            **evidence,
                            "verified": True,
                            "match_type": "document_fuzzy",
                            "position": None,
                        }
                    )
                    logger.debug(
                        f"Quote found in document (not in segment "
                        f"{segment_index}): '{quote[:30]}...'"
                    )
                    continue

            verified_evidence.append({**evidence, "verified": False})
            invalid_quotes.append(
                {
                    "quote": quote[:50] + "..." if len(quote) > 50 else quote,
                    "reason": f"Invalid segment_index: {segment_index}",
                }
            )
            continue

        segment = segment_map[segment_index]
        segment_text = segment.get("text", "")

        verification = verify_quote_in_segment(
            quote, segment_text, fuzzy_match_threshold
        )

        if verification["found"]:
            verified_evidence.append(
                {
                    **evidence,
                    "verified": True,
                    "match_type": verification["match_type"],
                    "position": verification["position"],
                }
            )
        else:
            page_numbers = segment.get("page_numbers", [])
            page_verified = False
            if page_numbers:
                for other_seg in segments:
                    if other_seg.get("segment_index") == segment_index:
                        continue
                    other_pages = other_seg.get("page_numbers", [])
                    if set(other_pages) & set(page_numbers):
                        other_text = other_seg.get("text", "")
                        other_v = verify_quote_in_segment(
                            quote, other_text, fuzzy_match_threshold
                        )
                        if other_v["found"]:
                            verified_evidence.append(
                                {
                                    **evidence,
                                    "verified": True,
                                    "match_type": other_v["match_type"],
                                    "position": other_v["position"],
                                }
                            )
                            page_verified = True
                            logger.debug(
                                f"Quote found in sibling segment "
                                f"(same pages {page_numbers}): "
                                f"'{quote[:30]}...'"
                            )
                            break

            if not page_verified and doc_content:
                doc_verified = verify_excerpt_in_document(quote, doc_content)
                if doc_verified:
                    verified_evidence.append(
                        {
                            **evidence,
                            "verified": True,
                            "match_type": "document_fuzzy",
                            "position": None,
                        }
                    )
                    logger.debug(
                        f"Quote found in document (not in segment "
                        f"{segment_index}): '{quote[:30]}...'"
                    )
                    continue

            verified_evidence.append({**evidence, "verified": False})
            truncated_quote = quote[:50] + "..." if len(quote) > 50 else quote
            invalid_quotes.append(
                {
                    "quote": truncated_quote,
                    "reason": "Quote not found in segment",
                }
            )

            logger.warning(
                f"Potential hallucination detected: quote '{truncated_quote}' "
                f"not found in segment {segment_index}. "
                f"Question type: {question_type}"
            )

    all_valid = len(invalid_quotes) == 0

    return {
        "valid": all_valid,
        "verified_evidence": verified_evidence,
        "invalid_quotes": invalid_quotes,
    }


def calculate_quality_metrics(questions: list[dict]) -> dict[str, Any]:
    """Calculate quality metrics for generated questions.

    Args:
        questions: List of generated question dictionaries.

    Returns:
        Dictionary containing quality metrics.
    """
    if not questions:
        return {
            "format_correct_rate": 0.0,
            "authenticity_pass_rate": 0.0,
            "type_distribution": {},
        }

    type_counts = {}
    for q in questions:
        q_type = q.get("question_type", "unknown")
        type_counts[q_type] = type_counts.get(q_type, 0) + 1

    total = len(questions)
    authenticity_passed = sum(
        1
        for q in questions
        if check_authenticity_rules(q.get("question", ""))["is_authentic"]
    )

    return {
        "format_correct_rate": 1.0,
        "authenticity_pass_rate": authenticity_passed / total,
        "type_distribution": type_counts,
    }


def calculate_hybrid_quality_metrics(questions: list[dict]) -> dict[str, Any]:
    """Calculate quality metrics for hybrid-generated questions.

    Includes standard metrics plus quote_verification_rate and
    ground_truth_confidence.

    Args:
        questions: List of generated question dictionaries.

    Returns:
        Dictionary containing quality metrics.
    """
    if not questions:
        return {
            "format_correct_rate": 0.0,
            "authenticity_pass_rate": 0.0,
            "type_distribution": {},
            "quote_verification_rate": 0.0,
            "ground_truth_confidence": 0.0,
            "excerpt_verified_rate": 0.0,
            "numerical_correction_rate": 0.0,
        }

    base_metrics = calculate_quality_metrics(questions)

    total = len(questions)
    questions_with_verified_quotes = 0
    total_confidence = 0.0

    for q in questions:
        evidence = q.get("evidence", [])
        if not evidence:
            if q.get("question_type") in ("irrelevant", "missing"):
                questions_with_verified_quotes += 1
            continue

        verified_evidence = [e for e in evidence if e.get("verified", False)]
        if verified_evidence:
            questions_with_verified_quotes += 1

            for e in verified_evidence:
                match_type = e.get("match_type", "none")
                if match_type == "exact":
                    total_confidence += 1.0
                elif match_type == "fuzzy":
                    total_confidence += 0.9
                elif match_type == "document_fuzzy":
                    total_confidence += 0.8

    quote_verification_rate = questions_with_verified_quotes / total

    total_verified_evidence = sum(
        len([e for e in q.get("evidence", []) if e.get("verified", False)])
        for q in questions
    )
    ground_truth_confidence = (
        total_confidence / total_verified_evidence
        if total_verified_evidence > 0
        else 0.0
    )

    questions_with_excerpt = sum(
        1 for q in questions if q.get("metadata", {}).get("excerpt_verified", True)
    )
    questions_with_numerical_correction = sum(
        1
        for q in questions
        if q.get("metadata", {}).get("numerical_auto_corrected", False)
    )
    excerpt_verified_rate = questions_with_excerpt / total
    numerical_correction_rate = questions_with_numerical_correction / total

    return {
        **base_metrics,
        "quote_verification_rate": round(quote_verification_rate, 4),
        "ground_truth_confidence": round(ground_truth_confidence, 4),
        "excerpt_verified_rate": round(excerpt_verified_rate, 4),
        "numerical_correction_rate": round(numerical_correction_rate, 4),
    }


def detect_content_overlaps(
    documents: list[dict[str, Any]],
    threshold: float = 0.8,
) -> list[tuple[str, str, float]]:
    """Detect content overlap between document pairs.

    Samples 3 segments (beginning, middle, end) from the shorter
    document and checks if they appear in the longer document.

    Args:
        documents: List of document dicts with 'doc_id' and 'content'.
        threshold: Minimum hit rate to mark as supplementary.

    Returns:
        List of tuples: (supplementary_doc_id, primary_doc_id, ratio).
    """
    overlaps: list[tuple[str, str, float]] = []
    sample_size = 500

    for i in range(len(documents)):
        for j in range(i + 1, len(documents)):
            doc_a = documents[i]
            doc_b = documents[j]
            len_a = len(doc_a["content"])
            len_b = len(doc_b["content"])

            if len_a <= len_b:
                shorter, longer = doc_a, doc_b
            else:
                shorter, longer = doc_b, doc_a

            short_text = re.sub(r"\s+", "", shorter["content"])
            long_text = re.sub(r"\s+", "", longer["content"])

            if len(short_text) < 100:
                continue

            samples = [
                short_text[:sample_size],
                short_text[len(short_text) // 2 : len(short_text) // 2 + sample_size],
                short_text[-sample_size:],
            ]

            hits = sum(1 for s in samples if len(s) >= 50 and s in long_text)
            hit_rate = hits / len(samples)

            if hit_rate >= threshold:
                overlaps.append((shorter["doc_id"], longer["doc_id"], hit_rate))

    return overlaps


def build_primary_pool(
    documents: list[dict[str, Any]],
    overlaps: list[tuple[str, str, float]],
) -> list[dict[str, Any]]:
    """Build primary document pool, excluding supplementary documents.

    If document A is marked as supplementary to B, A is excluded from
    the primary pool.

    Args:
        documents: List of document dicts.
        overlaps: Overlap tuples from detect_content_overlaps().

    Returns:
        List of primary document dicts (supplementary excluded).
    """
    supplementary_ids: set[str] = set()
    primary_map: dict[str, str] = {}

    for supp_id, primary_id, _ratio in overlaps:
        if supp_id not in supplementary_ids:
            supplementary_ids.add(supp_id)
            primary_map[supp_id] = primary_id
        else:
            existing_primary_id = primary_map[supp_id]
            existing_doc = next(
                (d for d in documents if d["doc_id"] == existing_primary_id),
                None,
            )
            new_doc = next((d for d in documents if d["doc_id"] == primary_id), None)
            if (
                new_doc
                and existing_doc
                and len(new_doc["content"]) > len(existing_doc["content"])
            ):
                primary_map[supp_id] = primary_id

    return [d for d in documents if d["doc_id"] not in supplementary_ids]


def filter_adversarial_issues(
    issues: list[str],
    question_text: str,
) -> list[str]:
    """Filter answer-evidence issues for adversarial question type.

    Adversarial questions naturally contain interpretive language
    and computed values (e.g., percentage differences). This method
    removes issues that are expected for adversarial answers:

    - All proper noun issues are removed, since adversarial answers
      naturally contain interpretive language.
    - Number issues are kept only if the number appears in the
      question text (indicating it is a bait number from the
      original document that should be in evidence). Numbers not
      in the question are likely computed/derived by the LLM.

    Args:
        issues: List of issue strings from
            validate_answer_evidence_consistency.
        question_text: The question text to check for number presence.

    Returns:
        Filtered list of issues relevant to adversarial type.
    """
    filtered_issues = []
    for issue in issues:
        if issue.startswith("专有名词"):
            continue
        if issue.startswith("数值"):
            num_match = re.search(r"'([^']+)'", issue)
            if num_match:
                num_str = re.sub(
                    r"[亿万元个百分点个%％]+$",
                    "",
                    num_match.group(1),
                )
                try:
                    num_val = float(num_str.replace(",", ""))
                    if (
                        num_val >= 10
                        and str(int(num_val)) not in question_text
                        and num_str not in question_text
                    ):
                        continue
                except ValueError:
                    pass
        filtered_issues.append(issue)
    return filtered_issues


def supplement_evidence_for_uncovered_numbers(
    answer: str,
    evidence_list: list[dict[str, Any]],
    issues: list[str],
    doc_content: str,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Supplement evidence with document context for uncovered numbers.

    When answer-evidence consistency check finds numbers in the answer
    that are not covered by evidence quotes, this method searches the
    full document for those numbers and appends surrounding context
    as additional evidence entries.

    Args:
        answer: The generated answer text.
        evidence_list: Current list of evidence dictionaries.
        issues: List of issues from consistency check.
        doc_content: Full document content for searching.

    Returns:
        Tuple of (updated_evidence_list, remaining_issues).
    """
    if not doc_content or not issues:
        return evidence_list, issues

    number_issues = [i for i in issues if i.startswith("数值 '")]
    if not number_issues:
        return evidence_list, issues

    supplemented_evidence = list(evidence_list)
    remaining_issues = [i for i in issues if not i.startswith("数值 '")]
    supplemented_numbers: set[str] = set()

    for issue in number_issues:
        num_match = re.search(r"'([^']+)'", issue)
        if not num_match:
            remaining_issues.append(issue)
            continue

        num_str = num_match.group(1)
        core_num = re.sub(r"[亿万元个百分点个%％]+$", "", num_str)
        if not core_num or core_num in supplemented_numbers:
            remaining_issues.append(issue)
            continue

        search_pattern = core_num.replace(",", r"[,\s]*")
        try:
            found_in_doc = False
            for match in re.finditer(search_pattern, doc_content):
                start = max(0, match.start() - 80)
                end = min(len(doc_content), match.end() + 80)
                context = doc_content[start:end].strip()
                if start > 0:
                    context = "..." + context
                if end < len(doc_content):
                    context = context + "..."
                supplemented_evidence.append(
                    {
                        "segment_index": -1,
                        "quote": context,
                        "relevance": f"Auto-supplemented: contains number '{num_str}' from answer",
                        "verified": True,
                        "match_type": "auto_supplemented",
                        "position": None,
                    }
                )
                supplemented_numbers.add(core_num)
                found_in_doc = True
                break
            if not found_in_doc:
                remaining_issues.append(issue)
        except re.error:
            remaining_issues.append(issue)
            continue

    return supplemented_evidence, remaining_issues


def truncate_answer(
    qa: dict[str, Any],
    answer_text: str,
    answer_limit: int,
) -> None:
    """Truncate answer to the specified length limit.

    Attempts to truncate at the last Chinese period (。) within the
    limit if it is past the halfway point. Otherwise performs a hard
    truncation at the limit. Sets metadata flag when truncation
    occurs.

    Args:
        qa: Question-answer dictionary to modify in place.
        answer_text: Original answer text.
        answer_limit: Maximum character length for the answer.
    """
    if len(answer_text) <= answer_limit:
        return

    last_period = answer_text.rfind("。", 0, answer_limit)
    if last_period > answer_limit // 2:
        qa["answer"] = answer_text[: last_period + 1]
    else:
        qa["answer"] = answer_text[:answer_limit]
    qa.setdefault("metadata", {})
    qa["metadata"]["answer_truncated"] = True
    logger.info(
        f"Answer truncated for {qa.get('id', 'unknown')}: "
        f"{len(answer_text)} -> {len(qa['answer'])} chars"
    )
