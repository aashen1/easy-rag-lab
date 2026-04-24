import math

from eval.metrics.utils import _parse_chunk_id


def calculate_chunk_hit_rate(
    retrieved_chunk_ids: list[str],
    expected_chunk_ids: list[str],
    adjacent_tolerance: int = 1,
    k: int = 5,
) -> float:
    """Calculate chunk-level hit rate with adjacent tolerance.

    This metric evaluates whether any of the top-k retrieved chunks match
    the expected chunks, supporting both exact matches and adjacent matches
    within a configurable tolerance window.

    A match occurs when:
    - The retrieved chunk_id is exactly in expected_chunk_ids (exact match), OR
    - The retrieved chunk belongs to the same document as an expected chunk
      AND the absolute difference between their chunk indices is within
      adjacent_tolerance (adjacent match).

    Args:
        retrieved_chunk_ids: List of retrieved chunk identifiers, ordered
            by relevance (most relevant first).
        expected_chunk_ids: List of expected (ground truth) chunk identifiers.
        adjacent_tolerance: Maximum allowed index difference for adjacent
            matching. Defaults to 1.
        k: Number of top results to consider. Defaults to 5.

    Returns:
        Hit rate as 1.0 if any match is found in top-k, 0.0 otherwise.
        Returns 0.0 if expected_chunk_ids is empty.
    """
    if not expected_chunk_ids:
        return 0.0

    expected_parsed = [_parse_chunk_id(cid) for cid in expected_chunk_ids]
    expected_exact_set = set(expected_chunk_ids)

    for chunk_id in retrieved_chunk_ids[:k]:
        if chunk_id in expected_exact_set:
            return 1.0
        ret_stem, ret_index = _parse_chunk_id(chunk_id)
        if ret_index == -1:
            continue
        for exp_stem, exp_index in expected_parsed:
            if exp_index == -1:
                continue
            if (
                ret_stem == exp_stem
                and abs(ret_index - exp_index) <= adjacent_tolerance
            ):
                return 1.0

    return 0.0


def calculate_chunk_mrr(
    retrieved_chunk_ids: list[str],
    expected_chunk_ids: list[str],
    adjacent_tolerance: int = 1,
) -> float:
    """Calculate chunk-level Mean Reciprocal Rank with adjacent tolerance.

    Uses the same matching logic as calculate_chunk_hit_rate but returns
    the reciprocal of the rank at which the first match is found, rather
    than a binary hit/miss.

    Args:
        retrieved_chunk_ids: List of retrieved chunk identifiers, ordered
            by relevance (most relevant first).
        expected_chunk_ids: List of expected (ground truth) chunk identifiers.
        adjacent_tolerance: Maximum allowed index difference for adjacent
            matching. Defaults to 1.

    Returns:
        Reciprocal rank as a float between 0.0 and 1.0:
        - 1.0 if the first match is at position 1
        - 1/n if the first match is at position n
        - 0.0 if no match is found or expected_chunk_ids is empty
    """
    if not expected_chunk_ids:
        return 0.0

    expected_parsed = [_parse_chunk_id(cid) for cid in expected_chunk_ids]
    expected_exact_set = set(expected_chunk_ids)

    for i, chunk_id in enumerate(retrieved_chunk_ids):
        if chunk_id in expected_exact_set:
            return 1.0 / (i + 1)
        ret_stem, ret_index = _parse_chunk_id(chunk_id)
        if ret_index == -1:
            continue
        for exp_stem, exp_index in expected_parsed:
            if exp_index == -1:
                continue
            if (
                ret_stem == exp_stem
                and abs(ret_index - exp_index) <= adjacent_tolerance
            ):
                return 1.0 / (i + 1)

    return 0.0


def calculate_chunk_ndcg(
    retrieved_chunk_ids: list[str],
    expected_chunk_ids: list[str],
    k: int = 5,
    adjacent_tolerance: int = 1,
) -> float:
    """Calculate chunk-level NDCG with adjacent tolerance.

    Assigns multi-level relevance scores based on match type:
    - Exact match: relevance = 2
    - Adjacent match (within tolerance): relevance = 1
    - No match: relevance = 0

    Uses the standard DCG formula:
        DCG@k = sum((2^rel_i - 1) / log2(i + 2))

    Deduplicates by chunk_id before computing to avoid inflated scores.

    Args:
        retrieved_chunk_ids: List of retrieved chunk identifiers, ordered
            by relevance (most relevant first).
        expected_chunk_ids: List of expected (ground truth) chunk identifiers.
        k: Number of top results to consider. Defaults to 5.
        adjacent_tolerance: Maximum allowed index difference for adjacent
            matching. Defaults to 1.

    Returns:
        NDCG as a float between 0.0 and 1.0.
        Returns 0.0 if expected_chunk_ids is empty.
    """
    if not expected_chunk_ids:
        return 0.0

    expected_exact_set = set(expected_chunk_ids)
    expected_parsed = [_parse_chunk_id(cid) for cid in expected_chunk_ids]

    seen: set = set()
    unique_retrieved: list[str] = []
    for chunk_id in retrieved_chunk_ids[:k]:
        if chunk_id not in seen:
            seen.add(chunk_id)
            unique_retrieved.append(chunk_id)

    def _get_relevance(chunk_id: str) -> int:
        if chunk_id in expected_exact_set:
            return 2
        ret_stem, ret_index = _parse_chunk_id(chunk_id)
        if ret_index == -1:
            return 0
        for exp_stem, exp_index in expected_parsed:
            if exp_index == -1:
                continue
            if (
                ret_stem == exp_stem
                and abs(ret_index - exp_index) <= adjacent_tolerance
            ):
                return 1
        return 0

    dcg = 0.0
    for i, chunk_id in enumerate(unique_retrieved):
        rel = _get_relevance(chunk_id)
        if rel > 0:
            dcg += (2**rel - 1) / math.log2(i + 2)

    ideal_rels = [2] * len(expected_chunk_ids)
    ideal_rels.sort(reverse=True)
    ideal_rels = ideal_rels[:k]

    ideal_dcg = 0.0
    for i, rel in enumerate(ideal_rels):
        ideal_dcg += (2**rel - 1) / math.log2(i + 2)

    if ideal_dcg == 0:
        return 0.0

    ndcg = dcg / ideal_dcg
    return min(1.0, max(0.0, ndcg))
