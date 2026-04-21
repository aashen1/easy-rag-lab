
from eval.metrics.retrieval import calculate_hit_rate, calculate_mrr, calculate_ndcg
from eval.metrics.utils import _parse_chunk_id, normalize_source


def deduplicate_by_document(
    retrieved_sources: list[str],
    retrieved_chunk_ids: list[str] | None = None,
) -> list[int]:
    """Return indices to keep after deduplicating by document.

    Identifies the first occurrence of each unique document in the
    retrieved results and returns their indices. Subsequent occurrences
    of the same document are excluded.

    When retrieved_chunk_ids is provided, the function first attempts
    to extract the document stem from the chunk_id (format:
    "{doc_stem}_{index:03d}") for more precise deduplication. If
    chunk_id parsing fails, it falls back to normalizing the source path.

    Args:
        retrieved_sources: List of retrieved source paths.
        retrieved_chunk_ids: Optional list of chunk identifiers
            corresponding to retrieved_sources. If provided, used for
            document identification. If None, deduplication is based
            on source path only.

    Returns:
        List of integer indices to keep (first occurrence of each
        unique document), in ascending order.
    """
    seen: set = set()
    keep_indices: list[int] = []

    for i, source in enumerate(retrieved_sources):
        if retrieved_chunk_ids is not None and i < len(retrieved_chunk_ids):
            doc_stem, _ = _parse_chunk_id(retrieved_chunk_ids[i])
            if doc_stem != retrieved_chunk_ids[i]:
                key = doc_stem
            else:
                key = normalize_source(source, include_parent=True)
        else:
            key = normalize_source(source, include_parent=True)

        if key not in seen:
            seen.add(key)
            keep_indices.append(i)

    return keep_indices


def calculate_dedup_hit_rate(
    retrieved_sources: list[str],
    expected_sources: list[str],
    k: int = 5,
    retrieved_chunk_ids: list[str] | None = None,
) -> float:
    """Calculate hit rate after deduplicating by document.

    First deduplicates the retrieved sources so that each document
    appears only once, then calculates hit rate on the deduplicated
    list using the standard calculate_hit_rate function.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider. Defaults to 5.
        retrieved_chunk_ids: Optional list of chunk identifiers for
            more precise deduplication.

    Returns:
        Hit rate as a float between 0.0 and 1.0.
    """
    keep_indices = deduplicate_by_document(retrieved_sources, retrieved_chunk_ids)
    deduped_sources = [retrieved_sources[i] for i in keep_indices]
    return calculate_hit_rate(deduped_sources, expected_sources, k=k)


def calculate_dedup_mrr(
    retrieved_sources: list[str],
    expected_sources: list[str],
    retrieved_chunk_ids: list[str] | None = None,
) -> float:
    """Calculate MRR after deduplicating by document.

    First deduplicates the retrieved sources so that each document
    appears only once, then calculates MRR on the deduplicated list
    using the standard calculate_mrr function.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        retrieved_chunk_ids: Optional list of chunk identifiers for
            more precise deduplication.

    Returns:
        Reciprocal rank as a float between 0.0 and 1.0.
    """
    keep_indices = deduplicate_by_document(retrieved_sources, retrieved_chunk_ids)
    deduped_sources = [retrieved_sources[i] for i in keep_indices]
    return calculate_mrr(deduped_sources, expected_sources)


def calculate_dedup_ndcg(
    retrieved_sources: list[str],
    expected_sources: list[str],
    k: int = 5,
    relevance_scores: dict[str, int] | None = None,
    retrieved_chunk_ids: list[str] | None = None,
) -> float:
    """Calculate NDCG after deduplicating by document.

    First deduplicates the retrieved sources so that each document
    appears only once, then calculates NDCG on the deduplicated list
    using the standard calculate_ndcg function.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider. Defaults to 5.
        relevance_scores: Optional dict mapping source names to
            relevance scores.
        retrieved_chunk_ids: Optional list of chunk identifiers for
            more precise deduplication.

    Returns:
        NDCG as a float between 0.0 and 1.0.
    """
    keep_indices = deduplicate_by_document(retrieved_sources, retrieved_chunk_ids)
    deduped_sources = [retrieved_sources[i] for i in keep_indices]
    return calculate_ndcg(deduped_sources, expected_sources, k=k, relevance_scores=relevance_scores)
