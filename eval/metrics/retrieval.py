import math

from eval.metrics.utils import normalize_source
from src.exceptions import EvaluationError


def calculate_hit_rate(
    retrieved_sources: list[str],
    expected_sources: list[str],
    k: int = 5,
    mode: str = "standard"
) -> float:
    """Calculate hit rate for retrieval evaluation.

    Industry Standard Definition (mode='standard'):
        Hit Rate@k = 1.0 if at least one relevant document is in top-k results,
        otherwise 0.0. This is the recommended mode for fair comparison with
        other systems.

    Legacy Mode (mode='recall'):
        Calculates recall = (retrieved relevant docs) / (total relevant docs).
        This mode is kept for backward compatibility but may produce inflated
        scores compared to standard Hit Rate.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider for standard mode. Defaults to 5.
        mode: Calculation mode - 'standard' for industry standard Hit Rate@k,
              'recall' for legacy recall-based calculation. Defaults to 'standard'.

    Returns:
        Hit rate as a float between 0.0 and 1.0.

    Raises:
        ValueError: If mode is not 'standard' or 'recall'.
    """
    if mode not in ("standard", "recall"):
        raise EvaluationError(
            f"mode must be 'standard' or 'recall', got '{mode}'")

    if not expected_sources:
        return 0.0

    if mode == "standard":
        top_k = retrieved_sources[:k]
        top_k_set = set(normalize_source(s, include_parent=True)
                        for s in top_k)
        expected_set = set(normalize_source(s, include_parent=True)
                           for s in expected_sources)
        return 1.0 if top_k_set & expected_set else 0.0

    retrieved_set = set(normalize_source(s, include_parent=True)
                        for s in retrieved_sources)
    expected_set = set(normalize_source(s, include_parent=True)
                       for s in expected_sources)
    hits = len(retrieved_set & expected_set)
    return hits / len(expected_set)


def calculate_mrr(
    retrieved_sources: list[str], expected_sources: list[str]
) -> float:
    """Calculate Reciprocal Rank (RR) for a single query.

    This function computes the Reciprocal Rank for a single query, which is
    defined as 1/rank where rank is the position of the first relevant document
    in the retrieved list (1-indexed). The Mean Reciprocal Rank (MRR) is obtained
    by averaging RR values across multiple queries.

    The function normalizes source paths using their filename stems, allowing
    cross-format matching (e.g., "path/to/doc.pdf" matches "doc.md").

    Args:
        retrieved_sources: List of retrieved source paths, ordered by relevance
            (most relevant first).
        expected_sources: List of expected (relevant) source paths.

    Returns:
        Reciprocal Rank as a float between 0.0 and 1.0:
        - 1.0 if a relevant document is found at position 1
        - 1/n if the first relevant document is at position n
        - 0.0 if no relevant document is found or expected_sources is empty

    Note:
        This function calculates RR for a single query. To compute MRR across
        multiple queries, average the RR values from multiple calls.

    Example:
        >>> calculate_mrr(["doc2", "doc1", "doc3"], ["doc1"])
        0.5  # doc1 is at position 2, so RR = 1/2
    """
    if not expected_sources:
        return 0.0

    expected_set = set(normalize_source(s, include_parent=True)
                       for s in expected_sources)

    for i, source in enumerate(retrieved_sources):
        if normalize_source(source, include_parent=True) in expected_set:
            return 1.0 / (i + 1)

    return 0.0


def calculate_ndcg(
    retrieved_sources: list[str],
    expected_sources: list[str],
    k: int = 5,
    relevance_scores: dict[str, int] | None = None,
) -> float:
    """Calculate Normalized Discounted Cumulative Gain for retrieval evaluation.

    Supports multi-level relevance scoring (e.g., 0-3 scale) instead of simple
    binary relevance. Uses the standard DCG formula:
        DCG@k = Σ((2^rel_i - 1) / log2(i + 2))

    This implementation includes deduplication to handle cases where the same
    document appears multiple times in the retrieved results, ensuring NDCG
    always falls within [0, 1].

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider.
        relevance_scores: Optional dict mapping source names to relevance scores
            (e.g., {"doc1": 3, "doc2": 1}). Higher scores indicate higher relevance.
            If None, uses binary relevance (score=1 for all expected documents).

    Returns:
        NDCG as a float between 0.0 and 1.0.

    Examples:
        Binary relevance (default):
            >>> calculate_ndcg(["doc1", "doc2"], ["doc1", "doc2"])
            1.0

        Multi-level relevance:
            >>> rel_scores = {"doc1": 3, "doc2": 1}
            >>> calculate_ndcg(["doc1", "doc2"], ["doc1", "doc2"],
            ...                relevance_scores=rel_scores)
            1.0

        With duplicates (should not exceed 1.0):
            >>> calculate_ndcg(["doc1", "doc1", "doc1"], ["doc1"])
            1.0
    """
    if not expected_sources:
        return 0.0

    expected_normalized = [normalize_source(
        s, include_parent=True) for s in expected_sources]
    expected_set = set(expected_normalized)

    if relevance_scores is None:
        relevance_scores = {normalize_source(
            s, include_parent=True): 1 for s in expected_sources}

    retrieved_normalized = [normalize_source(
        s, include_parent=True) for s in retrieved_sources[:k]]

    seen: set = set()
    unique_retrieved: list[str] = []
    for source in retrieved_normalized:
        if source not in seen:
            seen.add(source)
            unique_retrieved.append(source)

    dcg = 0.0
    for i, source in enumerate(unique_retrieved):
        if source in expected_set and source in relevance_scores:
            rel = relevance_scores[source]
            dcg += (2**rel - 1) / math.log2(i + 2)

    ideal_rels = []
    for source in expected_normalized:
        if source in relevance_scores:
            ideal_rels.append(relevance_scores[source])

    ideal_rels.sort(reverse=True)
    ideal_rels = ideal_rels[:k]

    ideal_dcg = 0.0
    for i, rel in enumerate(ideal_rels):
        ideal_dcg += (2**rel - 1) / math.log2(i + 2)

    if ideal_dcg == 0:
        return 0.0

    ndcg = dcg / ideal_dcg

    return min(1.0, max(0.0, ndcg))


def calculate_retrieval_diversity(
    retrieved_sources: list[str],
    k: int = 5,
) -> float:
    """Calculate document diversity of retrieval results.

    Measures the ratio of unique documents to total results in top-k.
    A value of 1.0 means all top-k results come from different documents.
    A value close to 0 means all results come from the same document.

    Args:
        retrieved_sources: List of retrieved source file paths.
        k: Number of top results to consider. Defaults to 5.

    Returns:
        Diversity ratio as a float between 0.0 and 1.0.
    """
    top_k = retrieved_sources[:k]
    if not top_k:
        return 0.0
    unique = len(set(normalize_source(s, include_parent=True) for s in top_k))
    return unique / len(top_k)
