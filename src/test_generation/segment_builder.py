import random
import re
from typing import Any

from loguru import logger

from src.test_generation.models import DOMAIN_KEYWORDS, PROPER_NOUN_PATTERN
from src.test_generation.validators import is_genuine_proper_noun


def segment_document(
    document_content: str, segment_size: int = 8000
) -> list[dict[str, Any]]:
    """Divide a document into segments for question generation.

    Attempts to segment at sentence boundaries to avoid cutting mid-sentence.
    For documents shorter than segment_size, returns a single segment.

    Args:
        document_content: The full text content of the document.
        segment_size: Target character count per segment. Defaults to 8000.

    Returns:
        List of segment dictionaries, each containing:
            - text: The segment text content
            - start_char: Starting character position in original document
            - end_char: Ending character position in original document
            - segment_index: Zero-based index of the segment
    """
    if not document_content:
        return []

    doc_length = len(document_content)
    if doc_length <= segment_size:
        return [
            {
                "text": document_content,
                "start_char": 0,
                "end_char": doc_length,
                "segment_index": 0,
            }
        ]

    segments: list[dict[str, Any]] = []
    current_pos = 0
    segment_index = 0

    sentence_endings = ["。", "！", "？", "！", "?", "!", "\n\n", "；", ";"]

    while current_pos < doc_length:
        target_end = min(current_pos + segment_size, doc_length)

        if target_end >= doc_length:
            segment_text = document_content[current_pos:doc_length]
            if segment_text.strip():
                segments.append(
                    {
                        "text": segment_text,
                        "start_char": current_pos,
                        "end_char": doc_length,
                        "segment_index": segment_index,
                    }
                )
            break

        best_break = -1
        search_start = max(current_pos + segment_size // 2, current_pos)

        for ending in sentence_endings:
            pos = document_content.rfind(ending, search_start, target_end)
            if pos > best_break:
                best_break = pos

        if best_break == -1:
            space_pos = document_content.rfind(" ", search_start, target_end)
            if space_pos > current_pos:
                best_break = space_pos

        actual_end = best_break + 1 if best_break > current_pos else target_end

        segment_text = document_content[current_pos:actual_end]
        if segment_text.strip():
            segments.append(
                {
                    "text": segment_text,
                    "start_char": current_pos,
                    "end_char": actual_end,
                    "segment_index": segment_index,
                }
            )
            segment_index += 1

        current_pos = actual_end

    return segments


def build_segments_from_pages(
    pages: list[dict[str, Any]],
    target_chars: int = 8000,
) -> list[dict[str, Any]]:
    """Build segments by aggregating pages from parser output.

    Unlike :func:`segment_document` which re-segments from full
    document text, this function groups whole pages together so that
    each segment carries ``page_numbers`` for reliable chunk
    mapping.

    Args:
        pages: List of page dicts, each containing ``page_number``
            and ``text`` keys.
        target_chars: Target character count per segment.

    Returns:
        List of segment dictionaries.
    """
    if not pages:
        return []

    sorted_pages = sorted(pages, key=lambda p: p.get("page_number", 0))

    segments: list[dict[str, Any]] = []
    current_pages: list[dict[str, Any]] = []
    current_chars = 0
    segment_index = 0

    for page in sorted_pages:
        page_text = page.get("text", "")
        if not page_text or not page_text.strip():
            continue

        current_pages.append(page)
        current_chars += len(page_text)

        if current_chars >= target_chars:
            page_numbers = sorted(p.get("page_number", 0) for p in current_pages)
            text = "\n\n".join(p.get("text", "") for p in current_pages)
            segments.append(
                {
                    "text": text,
                    "segment_index": segment_index,
                    "page_numbers": page_numbers,
                    "start_char": 0,
                    "end_char": len(text),
                    "source_type": "pages_json",
                }
            )
            segment_index += 1
            current_pages = []
            current_chars = 0

    if current_pages:
        page_numbers = sorted(p.get("page_number", 0) for p in current_pages)
        text = "\n\n".join(p.get("text", "") for p in current_pages)
        segments.append(
            {
                "text": text,
                "segment_index": segment_index,
                "page_numbers": page_numbers,
                "start_char": 0,
                "end_char": len(text),
                "source_type": "pages_json",
            }
        )

    for i, seg in enumerate(segments):
        seg["start_char"] = sum(len(segments[j]["text"]) + 2 for j in range(i))
        seg["end_char"] = seg["start_char"] + len(seg["text"])

    return segments


def compact_segments(
    segments: list[dict[str, Any]],
    max_chars: int,
) -> list[dict[str, Any]]:
    """Truncate segment text to reduce token consumption.

    Args:
        segments: List of segment dictionaries with 'text' key.
        max_chars: Maximum characters per segment.

    Returns:
        Segments with truncated text (copies, originals unchanged).
    """
    compacted = []
    for seg in segments:
        text = seg.get("text", "")
        if len(text) <= max_chars:
            compacted.append(seg)
        else:
            compacted_seg = dict(seg)
            compacted_seg["text"] = text[:max_chars]
            compacted.append(compacted_seg)
    return compacted


def select_segments_for_question_type(
    segments: list[dict[str, Any]],
    question_type: str,
    num_segments: int = 1,
    sampling_strategy: str = "random",
) -> list[dict[str, Any]]:
    """Select document segments based on question type.

    Args:
        segments: List of segment dictionaries from segment_document.
        question_type: Type of question to generate.
        num_segments: Number of segments to select.
        sampling_strategy: Strategy for sampling segments.

    Returns:
        List of selected segment dictionaries.
    """
    if not segments:
        return []

    if question_type == "irrelevant":
        return []

    if question_type == "single_fact" or question_type == "missing":
        selected_count = 1
    elif question_type in ["multi_fact", "reasoning", "comparative"]:
        selected_count = min(random.randint(2, 3), len(segments))
    elif question_type == "adversarial":
        selected_count = min(random.randint(1, 2), len(segments))
    else:
        selected_count = min(num_segments, len(segments))

    if selected_count >= len(segments):
        return segments.copy()

    if sampling_strategy == "random":
        return random.sample(segments, selected_count)
    elif sampling_strategy == "sequential":
        start_idx = random.randint(0, len(segments) - selected_count)
        return segments[start_idx : start_idx + selected_count]
    else:
        return random.sample(segments, selected_count)


def select_candidate_segments(
    segments: list[dict[str, Any]],
    question_type: str,
    num_candidates: int = 4,
    sampling_strategy: str = "random",
) -> list[dict[str, Any]]:
    """Select candidate segments for multi-hop question generation.

    Args:
        segments: List of segment dictionaries.
        question_type: Type of question to generate.
        num_candidates: Number of candidate segments.
        sampling_strategy: Strategy for sampling segments.

    Returns:
        List of selected segment dictionaries.
    """
    if not segments:
        return []

    multi_hop_types = {"multi_fact", "reasoning", "comparative"}

    if question_type not in multi_hop_types:
        return select_segments_for_question_type(
            segments, question_type, num_candidates, sampling_strategy
        )

    actual_count = min(num_candidates, len(segments))

    if actual_count >= len(segments):
        return segments.copy()

    if sampling_strategy == "random":
        return select_diverse_segments(segments, actual_count)
    elif sampling_strategy == "sequential":
        start_idx = random.randint(0, len(segments) - actual_count)
        return segments[start_idx : start_idx + actual_count]
    else:
        return select_diverse_segments(segments, actual_count)


def select_diverse_segments(
    segments: list[dict[str, Any]],
    count: int,
) -> list[dict[str, Any]]:
    """Select segments with diversity in document position.

    Args:
        segments: List of segment dictionaries.
        count: Number of segments to select.

    Returns:
        List of selected segment dictionaries with diverse positions.
    """
    if count >= len(segments):
        return segments.copy()

    total_segments = len(segments)
    step = total_segments / count

    selected: list[dict[str, Any]] = []
    for i in range(count):
        target_index = int(i * step)
        target_index = min(target_index, total_segments - 1)

        for seg in segments:
            if seg.get("segment_index", 0) == target_index:
                selected.append(seg)
                break
        else:
            if segments:
                selected.append(segments[target_index])

    if len(selected) < count:
        remaining = [s for s in segments if s not in selected]
        needed = count - len(selected)
        if remaining and needed > 0:
            selected.extend(random.sample(remaining, min(needed, len(remaining))))

    return selected


def parse_segment_selection(
    llm_response: dict[str, Any],
    num_available_segments: int,
) -> list[int]:
    """Parse segment selection from LLM response.

    Args:
        llm_response: Parsed LLM response dictionary.
        num_available_segments: Total number of available segments.

    Returns:
        List of valid segment indices.
    """
    if num_available_segments <= 0:
        return []

    all_indices = list(range(num_available_segments))

    selected = llm_response.get("selected_segments")
    if selected is None:
        return all_indices

    if not isinstance(selected, list):
        logger.warning(f"selected_segments is not a list: {type(selected).__name__}")
        return all_indices

    valid_indices: list[int] = []
    for idx in selected:
        if isinstance(idx, int) and 0 <= idx < num_available_segments:
            valid_indices.append(idx)
        else:
            logger.warning(
                f"Invalid segment index: {idx} (available: 0-{num_available_segments - 1})"
            )

    if not valid_indices:
        logger.warning("No valid segment indices found in selected_segments")
        return all_indices

    return valid_indices


def validate_segment_relevance(
    selected_indices: list[int],
    segments: list[dict[str, Any]],
) -> bool:
    """Validate if selected segments share any common keywords.

    Args:
        selected_indices: List of segment indices that were selected.
        segments: List of all available segment dictionaries.

    Returns:
        True if segments share common keywords or if only one segment
        is selected. False if segments appear unrelated.
    """
    if len(selected_indices) <= 1:
        return True

    selected_segments = [segments[i] for i in selected_indices if i < len(segments)]

    if len(selected_segments) <= 1:
        return True

    keyword_sets: list[set[str]] = []
    for seg in selected_segments:
        text = seg.get("text", "")
        keywords = extract_segment_keywords(text)
        keyword_sets.append(keywords)

    if not keyword_sets:
        return True

    common_keywords = keyword_sets[0]
    for kw_set in keyword_sets[1:]:
        common_keywords = common_keywords & kw_set

    if not common_keywords:
        logger.warning(
            f"Selected segments (indices: {selected_indices}) share no common keywords. "
            "They may be unrelated, which could affect question quality."
        )
        return False

    logger.debug(
        f"Segments share {len(common_keywords)} common keywords: "
        f"{list(common_keywords)[:5]}"
    )
    return True


def extract_segment_keywords(text: str) -> set[str]:
    """Extract meaningful keywords from segment text.

    Args:
        text: The segment text to extract keywords from.

    Returns:
        Set of keyword strings extracted from the text.
    """
    keywords: set[str] = set()

    numbers_with_units = re.findall(r"\d+\.?\d*[万亿千百%％]?", text)
    keywords.update(numbers_with_units)

    proper_nouns = re.findall(
        PROPER_NOUN_PATTERN,
        text,
    )
    proper_nouns = [n for n in proper_nouns if is_genuine_proper_noun(n)]
    keywords.update(proper_nouns)

    for kw in DOMAIN_KEYWORDS:
        if kw in text:
            keywords.add(kw)

    return keywords
