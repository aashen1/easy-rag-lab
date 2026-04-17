from pathlib import Path
from typing import List


def normalize_source(source: str) -> str:
    """Normalize source path to a comparable form.

    Extracts the filename stem (without extension and directory),
    so that paths like "annual_report/贵州茅台2023年年度报告.md"
    and "贵州茅台2023年年度报告.pdf" both become "贵州茅台2023年年度报告".

    Args:
        source: Source path string.

    Returns:
        Normalized source stem string.
    """
    return Path(source).stem


def calculate_hit_rate(
    retrieved_sources: List[str], expected_sources: List[str]
) -> float:
    """Calculate hit rate for retrieval evaluation.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.

    Returns:
        Hit rate as a float between 0.0 and 1.0.
    """
    if not expected_sources:
        return 0.0

    retrieved_set = set(normalize_source(s) for s in retrieved_sources)
    expected_set = set(normalize_source(s) for s in expected_sources)

    hits = len(retrieved_set & expected_set)
    return hits / len(expected_set)


def calculate_mrr(
    retrieved_sources: List[str], expected_sources: List[str]
) -> float:
    """Calculate Mean Reciprocal Rank for retrieval evaluation.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.

    Returns:
        MRR as a float between 0.0 and 1.0.
    """
    if not expected_sources:
        return 0.0

    expected_set = set(normalize_source(s) for s in expected_sources)

    for i, source in enumerate(retrieved_sources):
        if normalize_source(source) in expected_set:
            return 1.0 / (i + 1)

    return 0.0


def calculate_ndcg(
    retrieved_sources: List[str], expected_sources: List[str], k: int = 5
) -> float:
    """Calculate Normalized Discounted Cumulative Gain for retrieval evaluation.

    Args:
        retrieved_sources: List of retrieved source paths.
        expected_sources: List of expected source paths.
        k: Number of top results to consider.

    Returns:
        NDCG as a float between 0.0 and 1.0.
    """
    if not expected_sources:
        return 0.0

    expected_set = set(normalize_source(s) for s in expected_sources)

    dcg = 0.0
    for i, source in enumerate(retrieved_sources[:k]):
        if normalize_source(source) in expected_set:
            dcg += 1.0 / (i + 1)

    ideal_dcg = 0.0
    for i in range(min(len(expected_sources), k)):
        ideal_dcg += 1.0 / (i + 1)

    if ideal_dcg == 0:
        return 0.0

    return dcg / ideal_dcg
