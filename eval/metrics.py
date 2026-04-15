from typing import List


def calculate_hit_rate(
    retrieved_sources: List[str], expected_sources: List[str]
) -> float:
    if not expected_sources:
        return 0.0

    retrieved_set = set(retrieved_sources)
    expected_set = set(expected_sources)

    hits = len(retrieved_set & expected_set)
    return hits / len(expected_set)


def calculate_mrr(
    retrieved_sources: List[str], expected_sources: List[str]
) -> float:
    if not expected_sources:
        return 0.0

    expected_set = set(expected_sources)

    for i, source in enumerate(retrieved_sources):
        if source in expected_set:
            return 1.0 / (i + 1)

    return 0.0


def calculate_ndcg(
    retrieved_sources: List[str], expected_sources: List[str], k: int = 5
) -> float:
    if not expected_sources:
        return 0.0

    expected_set = set(expected_sources)

    dcg = 0.0
    for i, source in enumerate(retrieved_sources[:k]):
        if source in expected_set:
            dcg += 1.0 / (i + 1)

    ideal_dcg = 0.0
    for i in range(min(len(expected_sources), k)):
        ideal_dcg += 1.0 / (i + 1)

    if ideal_dcg == 0:
        return 0.0

    return dcg / ideal_dcg
