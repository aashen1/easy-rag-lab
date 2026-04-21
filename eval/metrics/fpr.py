

def calculate_false_positive_rate(
    retrieved_sources: list[str],
    k: int = 5,
) -> float:
    """Calculate False Positive Rate for irrelevant questions.

    For questions that have no relevant documents (irrelevant questions),
    all retrieved documents are false positives. The FPR measures the
    proportion of top-k slots occupied by irrelevant retrievals.

    Args:
        retrieved_sources: List of retrieved source paths for an
            irrelevant question.
        k: Number of top results to consider. Defaults to 5.

    Returns:
        False positive rate as a float between 0.0 and 1.0:
        - 1.0 if all k slots are filled with irrelevant results
        - 0.0 if no results are retrieved
        - Proportional value for partial retrieval
    """
    top_k = retrieved_sources[:k]
    return len(top_k) / k
