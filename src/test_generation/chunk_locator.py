import difflib
import json
import re
import warnings
from pathlib import Path
from typing import Any

from loguru import logger


def verify_quote_in_segment(
    quote: str,
    segment_text: str,
    fuzzy_match_threshold: float = 0.85,
) -> dict[str, Any]:
    """Verify if a quote exists in a segment text.

    First attempts exact match, then falls back to fuzzy matching if
    exact match fails.

    Args:
        quote: The quote text to verify.
        segment_text: The segment text to search within.
        fuzzy_match_threshold: Minimum similarity ratio for fuzzy match.

    Returns:
        Dictionary with keys:
            - found: bool indicating if quote was found
            - position: int or None, the character position of the match
            - match_type: str, one of "exact", "fuzzy", or None
    """
    if not quote or not segment_text:
        return {"found": False, "position": None, "match_type": None}

    pos = segment_text.find(quote)
    if pos != -1:
        return {"found": True, "position": pos, "match_type": "exact"}

    fuzzy_result = fuzzy_match_quote(quote, segment_text, fuzzy_match_threshold)
    if fuzzy_result["found"]:
        return {
            "found": True,
            "position": fuzzy_result["position"],
            "match_type": "fuzzy",
        }

    return {"found": False, "position": None, "match_type": None}


def fuzzy_match_quote(
    quote: str, segment_text: str, threshold: float = 0.85
) -> dict[str, Any]:
    """Perform fuzzy matching of a quote within segment text.

    Uses difflib.SequenceMatcher for similarity calculation. Handles
    minor differences such as whitespace variations and punctuation
    differences.

    Args:
        quote: The quote text to match.
        segment_text: The segment text to search within.
        threshold: Minimum similarity ratio for a match. Defaults to 0.85.

    Returns:
        Dictionary with keys:
            - found: bool indicating if a match was found
            - position: int or None, the starting character position
            - similarity: float, the similarity ratio of the best match
    """
    if not quote or not segment_text:
        return {"found": False, "position": None, "similarity": 0.0}

    quote_len = len(quote)
    if quote_len == 0:
        return {"found": False, "position": None, "similarity": 0.0}

    best_similarity = 0.0
    best_position = None

    normalized_quote = quote.replace("\n", " ").replace("\t", " ")
    normalized_quote = " ".join(normalized_quote.split())

    step = max(1, quote_len // 10)

    for start in range(0, len(segment_text) - quote_len + 1, step):
        substring = segment_text[start : start + quote_len]
        normalized_substring = substring.replace("\n", " ").replace("\t", " ")
        normalized_substring = " ".join(normalized_substring.split())

        matcher = difflib.SequenceMatcher(None, normalized_quote, normalized_substring)
        similarity = matcher.ratio()

        if similarity > best_similarity:
            best_similarity = similarity
            best_position = start

        if similarity >= threshold:
            for fine_start in range(
                max(0, start - step),
                min(len(segment_text) - quote_len + 1, start + step),
            ):
                fine_substring = segment_text[fine_start : fine_start + quote_len]
                fine_normalized = fine_substring.replace("\n", " ").replace("\t", " ")
                fine_normalized = " ".join(fine_normalized.split())

                fine_matcher = difflib.SequenceMatcher(
                    None, normalized_quote, fine_normalized
                )
                fine_similarity = fine_matcher.ratio()

                if fine_similarity > best_similarity:
                    best_similarity = fine_similarity
                    best_position = fine_start

    if best_similarity >= threshold:
        return {
            "found": True,
            "position": best_position,
            "similarity": best_similarity,
        }

    return {"found": False, "position": None, "similarity": best_similarity}


def texts_overlap(text_a: str, text_b: str, min_overlap_chars: int = 30) -> bool:
    """Check if two texts have significant overlapping content.

    .. deprecated::
        No longer used by the primary mapping path.  Kept for
        backward compatibility only.

    Uses a sliding-window approach: extracts substrings from text_a and
    checks if they appear in text_b. Handles OCR-induced whitespace
    differences by normalizing both texts before comparison.

    Args:
        text_a: First text (typically segment text).
        text_b: Second text (typically chunk text).
        min_overlap_chars: Minimum number of consecutive characters that
            must match to consider the texts overlapping.

    Returns:
        True if the texts share significant overlapping content.
    """
    if not text_a or not text_b:
        return False

    def _normalize(t: str) -> str:
        return " ".join(t.split())

    norm_a = _normalize(text_a)
    norm_b = _normalize(text_b)

    window = min_overlap_chars
    step = max(1, window // 3)

    for start in range(0, len(norm_a) - window + 1, step):
        substr = norm_a[start : start + window]
        if substr in norm_b:
            return True

    return False


def map_segments_to_chunks(
    segments: list[dict[str, Any]],
    doc_chunks: list[dict[str, Any]],
) -> dict[int, list[str]]:
    """Map document segments to chunk IDs based on text content overlap.

    .. deprecated::
        Use locate_source_chunks with page_numbers from page-based
        segments instead.  This method relies on fragile text matching.

    Determines which chunks belong to each segment by checking if the
    chunk's text content overlaps with the segment's text content.

    Args:
        segments: List of segment dictionaries with 'text' and
            'segment_index' keys.
        doc_chunks: List of chunk dictionaries from JSONL files, each
            containing 'chunk_id' and 'text' keys.

    Returns:
        Dictionary mapping segment_index to list of chunk_ids.
    """
    mapping: dict[int, list[str]] = {}

    chunk_texts: list[tuple[str, str]] = []
    for chunk in doc_chunks:
        chunk_id = chunk.get("chunk_id", "")
        text = chunk.get("text", "")
        if chunk_id and text:
            chunk_texts.append((chunk_id, text))

    for segment in segments:
        seg_text = segment.get("text", "")
        seg_index = segment.get("segment_index", 0)

        overlapping_chunks: list[str] = []

        if seg_text:
            for chunk_id, chunk_text in chunk_texts:
                if texts_overlap(seg_text, chunk_text):
                    overlapping_chunks.append(chunk_id)

        mapping[seg_index] = overlapping_chunks

    return mapping


def locate_source_chunks(
    page_numbers: list[int],
    quote: str,
    doc_chunks: list[dict[str, Any]],
    fuzzy_match_threshold: float = 0.85,
) -> list[str]:
    """Locate chunk IDs via two-stage mapping: page filter then quote match.

    Stage 1 narrows candidates to chunks whose page_number is in
    page_numbers.  Stage 2 matches quote text inside each candidate
    chunk (exact then fuzzy).  If stage 2 finds no matches the method
    falls back to returning all candidate chunk IDs.

    Args:
        page_numbers: Page numbers associated with the segment.
        quote: Verified quote text to locate within candidate chunks.
        doc_chunks: All chunk dictionaries for the document.
        fuzzy_match_threshold: Threshold for fuzzy quote matching.

    Returns:
        Sorted list of chunk_id strings.
    """
    if not page_numbers or not doc_chunks:
        return []

    page_set = set(page_numbers)
    candidate_chunks = [
        chunk
        for chunk in doc_chunks
        if chunk.get("metadata", {}).get("page_number") in page_set
    ]

    if not candidate_chunks:
        logger.debug(f"No chunks found for pages {page_numbers}")
        return []

    if not quote or not quote.strip():
        return sorted(c.get("chunk_id", "") for c in candidate_chunks)

    matching_ids: list[str] = []
    for chunk in candidate_chunks:
        chunk_text = chunk.get("text", "")
        chunk_id = chunk.get("chunk_id", "")
        if not chunk_text or not chunk_id:
            continue

        if quote in chunk_text:
            matching_ids.append(chunk_id)
        else:
            verification = verify_quote_in_segment(
                quote, chunk_text, fuzzy_match_threshold
            )
            if verification.get("found"):
                matching_ids.append(chunk_id)

    if not matching_ids:
        logger.debug(
            f"Quote not found in candidate chunks, "
            f"falling back to page-level mapping for pages {page_numbers}"
        )
        return sorted(c.get("chunk_id", "") for c in candidate_chunks)

    return sorted(matching_ids)


def locate_chunks_by_quote(
    quote: str,
    segments: list[dict[str, Any]],
    segment_chunk_map: dict[int, list[str]],
    doc_chunks: list[dict[str, Any]],
    fuzzy_match_threshold: float = 0.85,
) -> list[str]:
    """Locate chunk IDs that contain a verified quote text.

    .. deprecated::
        Use locate_source_chunks with page_numbers from page-based
        segments instead.

    Finds which segment contains the quote using character position,
    then looks up the chunk_ids from segment_chunk_map and verifies
    the quote appears in each chunk's text.

    Args:
        quote: The verified quote text to locate.
        segments: List of segment dictionaries.
        segment_chunk_map: Dictionary mapping segment_index to list of
            chunk_ids.
        doc_chunks: List of all chunk dictionaries from the document.
        fuzzy_match_threshold: Threshold for fuzzy quote matching.

    Returns:
        List of chunk_id strings that contain the quote text.
    """
    if not quote or not segments or not doc_chunks:
        return []

    containing_segment_index: int | None = None
    for segment in segments:
        segment_text = segment.get("text", "")
        seg_index = segment.get("segment_index")

        verification = verify_quote_in_segment(
            quote, segment_text, fuzzy_match_threshold
        )
        if verification["found"]:
            containing_segment_index = seg_index
            break

    if containing_segment_index is None:
        logger.debug(
            f"Quote not found in any segment, searching all chunks: {quote[:50]}..."
        )
        chunk_ids = [c.get("chunk_id", "") for c in doc_chunks if c.get("chunk_id", "")]
    else:
        chunk_ids = segment_chunk_map.get(containing_segment_index, [])
        if not chunk_ids:
            logger.debug(
                f"No chunks mapped to segment {containing_segment_index}, "
                f"searching all chunks directly"
            )
            chunk_ids = [
                c.get("chunk_id", "") for c in doc_chunks if c.get("chunk_id", "")
            ]

    chunk_id_to_text: dict[str, str] = {}
    for chunk in doc_chunks:
        chunk_id = chunk.get("chunk_id", "")
        if chunk_id:
            chunk_id_to_text[chunk_id] = chunk.get("text", "")

    matching_chunk_ids: list[str] = []
    for chunk_id in chunk_ids:
        chunk_text = chunk_id_to_text.get(chunk_id, "")
        if not chunk_text:
            continue
        if quote in chunk_text:
            matching_chunk_ids.append(chunk_id)
        else:
            verification = verify_quote_in_segment(
                quote, chunk_text, fuzzy_match_threshold
            )
            if verification["found"]:
                matching_chunk_ids.append(chunk_id)

    if not matching_chunk_ids:
        logger.debug(
            f"Quote found in segment but not in any mapped chunk: {quote[:50]}..."
        )

    return matching_chunk_ids


def locate_multi_hop_chunks(
    evidence_list: list[dict[str, Any]],
    segments: list[dict[str, Any]],
    segment_chunk_map: dict[int, list[str]],
    doc_chunks: list[dict[str, Any]],
    fuzzy_match_threshold: float = 0.85,
) -> list[str]:
    """Locate chunk IDs for multi-hop questions from multiple evidence entries.

    .. deprecated::
        Use locate_source_chunks with page_numbers from page-based
        segments instead.

    For each evidence entry with a verified quote, calls
    locate_chunks_by_quote to find the containing chunks, then
    returns the union of all unique chunk_ids.

    Args:
        evidence_list: List of evidence dictionaries.
        segments: List of segment dictionaries.
        segment_chunk_map: Dictionary mapping segment_index to chunk_ids.
        doc_chunks: List of all chunk dictionaries.
        fuzzy_match_threshold: Threshold for fuzzy quote matching.

    Returns:
        List of unique chunk_id strings.
    """
    if not evidence_list:
        return []

    all_chunk_ids: set[str] = set()

    for evidence in evidence_list:
        quote = evidence.get("quote", "")
        if not quote:
            continue

        chunk_ids = locate_chunks_by_quote(
            quote, segments, segment_chunk_map, doc_chunks, fuzzy_match_threshold
        )
        all_chunk_ids.update(chunk_ids)

    result = sorted(list(all_chunk_ids))

    if result:
        logger.debug(
            f"Located {len(result)} unique chunks from "
            f"{len(evidence_list)} evidence entries"
        )
    else:
        logger.warning(f"No chunks found for {len(evidence_list)} evidence entries")

    return result


def extract_key_sentences(answer: str) -> list[str]:
    """Extract key sentences from an answer text.

    Splits the answer by sentence delimiters and filters for sentences
    that contain specific data such as numbers, proper nouns, or
    domain-specific terms.

    Args:
        answer: The answer text to extract sentences from.

    Returns:
        List of key sentences that likely contain answer-specific
        information.
    """
    sentences = re.split(r"[。！？\n]", answer)
    sentences = [s.strip() for s in sentences if len(s.strip()) > 4]

    key_sentences = []
    for sent in sentences:
        has_number = bool(re.search(r"\d", sent))
        has_percentage = "%" in sent
        has_domain_terms = any(
            kw in sent
            for kw in [
                "增长",
                "下降",
                "上升",
                "减少",
                "增加",
                "收入",
                "利润",
                "营收",
                "市值",
                "占比",
                "规模",
                "产量",
                "销量",
                "价格",
                "成本",
            ]
        )
        if has_number or has_percentage or has_domain_terms:
            key_sentences.append(sent)

    if not key_sentences:
        key_sentences = [s for s in sentences if len(s) >= 6][:5]

    return key_sentences


def extract_key_terms(answer: str) -> list[str]:
    """Extract key terms from an answer text for chunk matching.

    Identifies meaningful terms including numbers with units, proper
    nouns, and domain-specific keywords.

    Args:
        answer: The answer text to extract terms from.

    Returns:
        List of key term strings.
    """
    terms: list[str] = []

    number_patterns = re.findall(r"\d+\.?\d*[万亿千百%％]?", answer)
    terms.extend(number_patterns)

    proper_nouns = re.findall(
        r"[\u4e00-\u9fff]{2,8}(?:股份|集团|公司|行业|市场|技术|产品|业务|报告|年度)",
        answer,
    )
    terms.extend(proper_nouns)

    domain_keywords = [
        "增长",
        "下降",
        "上升",
        "减少",
        "增加",
        "收入",
        "利润",
        "营收",
        "市值",
        "占比",
        "规模",
        "产量",
        "销量",
        "价格",
        "成本",
        "投资",
        "融资",
        "估值",
        "盈利",
        "亏损",
        "负债",
        "资产",
        "现金流",
        "毛利率",
        "净利率",
        "ROE",
        "ROA",
    ]
    for kw in domain_keywords:
        if kw in answer:
            terms.append(kw)

    return list(set(terms))


def chunk_matches_answer(
    chunk_text: str,
    key_sentences: list[str],
    key_terms: list[str],
    term_threshold: int = 3,
    overlap_threshold: float = 0.7,
) -> bool:
    """Check if a chunk text contains information relevant to the answer.

    A chunk is considered relevant if either:
    - It contains at least term_threshold key terms from the answer, OR
    - A key sentence from the answer has > overlap_threshold character
      overlap with the chunk text.

    Args:
        chunk_text: The text content of the chunk.
        key_sentences: Key sentences extracted from the answer.
        key_terms: Key terms extracted from the answer.
        term_threshold: Minimum number of key terms for a match.
        overlap_threshold: Minimum character overlap ratio for a match.

    Returns:
        True if the chunk is considered relevant to the answer.
    """
    if not key_terms and not key_sentences:
        return False

    matched_terms = sum(1 for term in key_terms if term in chunk_text)
    if matched_terms >= term_threshold:
        return True

    for sentence in key_sentences:
        if len(sentence) == 0:
            continue
        overlap_chars = 0
        window_size = min(len(sentence), len(chunk_text))
        for start in range(0, len(chunk_text) - window_size + 1):
            substring = chunk_text[start : start + len(sentence)]
            common = sum(1 for a, b in zip(sentence, substring, strict=False) if a == b)
            ratio = common / len(sentence)
            if ratio > overlap_chars:
                overlap_chars = ratio
        if overlap_chars > overlap_threshold:
            return True

    return False


def locate_answer_chunks(
    answer: str,
    source_path: str,
    chunks_dir: Path,
    adjacent_tolerance: int = 1,
) -> list[str]:
    """Locate chunk IDs that contain information relevant to the answer.

    .. deprecated::
        Use locate_chunks_by_quote for more accurate quote-based
        chunk location.

    Scans JSONL files in chunks_dir to find chunks belonging to the
    source document, then matches chunks against the answer text using
    keyword and substring overlap heuristics.

    Args:
        answer: The answer text to locate in chunks.
        source_path: Relative path of the source document.
        chunks_dir: Path to the chunks directory.
        adjacent_tolerance: Number of adjacent chunks to include.

    Returns:
        List of chunk_id strings for matched and adjacent chunks.
    """
    warnings.warn(
        "_locate_answer_chunks is deprecated. "
        "Use _locate_chunks_by_quote for more accurate quote-based "
        "chunk location.",
        DeprecationWarning,
        stacklevel=2,
    )
    if not answer or not source_path:
        return []

    if not chunks_dir or not chunks_dir.exists():
        logger.warning(f"Chunks directory not found: {chunks_dir}")
        return []

    normalized_source = source_path.replace("\\", "/")

    doc_chunks: list[dict[str, Any]] = []
    jsonl_files = list(chunks_dir.rglob("*.jsonl"))

    for jsonl_file in jsonl_files:
        try:
            with open(jsonl_file, encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    chunk = json.loads(line)
                    chunk_source = (
                        chunk.get("metadata", {}).get("source", "").replace("\\", "/")
                    )
                    if chunk_source == normalized_source:
                        doc_chunks.append(chunk)
        except Exception as e:
            logger.warning(f"Failed to read {jsonl_file}: {str(e)}")
            continue

    if not doc_chunks:
        logger.debug(f"No chunks found for source_path: {source_path}")
        return []

    doc_chunks.sort(key=lambda c: c.get("metadata", {}).get("chunk_index", 0))

    key_sentences = extract_key_sentences(answer)
    key_terms = extract_key_terms(answer)

    matched_indices: set = set()
    for i, chunk in enumerate(doc_chunks):
        chunk_text = chunk.get("text", "")
        if chunk_matches_answer(chunk_text, key_sentences, key_terms):
            matched_indices.add(i)

    if not matched_indices:
        logger.debug(f"No chunks matched for answer in source: {source_path}")
        return []

    expanded_indices: set = set()
    for idx in matched_indices:
        for offset in range(-adjacent_tolerance, adjacent_tolerance + 1):
            adj = idx + offset
            if 0 <= adj < len(doc_chunks):
                expanded_indices.add(adj)

    expanded_indices.discard(-1)

    result = [doc_chunks[i].get("chunk_id", "") for i in sorted(expanded_indices)]
    result = [cid for cid in result if cid]

    return result
