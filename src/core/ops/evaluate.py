from __future__ import annotations

from loguru import logger


def _word_overlap(text_a: str, text_b: str) -> float:
    """Compute simple word-overlap ratio between two strings.

    Tokenises both inputs on whitespace, then returns the ratio of
    shared unique words to the total unique words across both inputs
    (Jaccard-like).

    Args:
        text_a: First text.
        text_b: Second text.

    Returns:
        Float between 0.0 and 1.0 indicating overlap strength.
    """
    set_a = set(text_a.lower().split())
    set_b = set(text_b.lower().split())
    if not set_a and not set_b:
        return 1.0
    if not set_a or not set_b:
        return 0.0
    intersection = set_a & set_b
    union = set_a | set_b
    return len(intersection) / len(union)


def evaluate_single(
    question: str,
    answer: str,
    contexts: list[str],
    expected_answer: str | None = None,
    expected_sources: list[str] | None = None,
    metrics: list[str] | None = None,
    config: dict | None = None,
) -> dict[str, float]:
    """Evaluate a single RAG answer with lightweight, LLM-free metrics.

    Phase A stub that computes basic word-overlap metrics without
    requiring an LLM. The full implementation will delegate to
    ``BuiltinEvaluator`` in a later phase.

    Metrics computed:
        - ``context_relevance``: word overlap between *question* and
          concatenated *contexts*.
        - ``answer_relevancy``: word overlap between *question* and
          *answer*.
        - ``hit_rate`` (only when *expected_sources* is provided): 1.0
          if any expected source string appears in *contexts*, 0.0
          otherwise.

    Args:
        question: The original user question.
        answer: The generated answer text.
        contexts: Retrieved context chunks used to produce the answer.
        expected_answer: Ground-truth answer (unused in Phase A).
        expected_sources: Optional list of expected source identifiers.
            When provided, ``hit_rate`` is computed.
        metrics: Optional list of metric names to compute. When None,
            all available metrics are computed.
        config: Optional configuration dictionary (unused in Phase A).

    Returns:
        Dictionary mapping metric names to their float values.

    Raises:
        ValueError: If *question* or *answer* is empty.
    """
    if not question or not isinstance(question, str):
        raise ValueError("question must be a non-empty string")
    if not answer or not isinstance(answer, str):
        raise ValueError("answer must be a non-empty string")

    logger.debug(f"evaluate_single called for question: {question[:50]}...")

    all_metrics: dict[str, float] = {}

    concatenated_contexts = " ".join(contexts) if contexts else ""

    all_metrics["context_relevance"] = _word_overlap(question, concatenated_contexts)
    all_metrics["answer_relevancy"] = _word_overlap(question, answer)

    if expected_sources is not None:
        hit = 0.0
        for src in expected_sources:
            if any(src in ctx for ctx in contexts):
                hit = 1.0
                break
        all_metrics["hit_rate"] = hit

    if metrics is not None:
        all_metrics = {k: v for k, v in all_metrics.items() if k in metrics}

    logger.debug(f"evaluate_single results: {all_metrics}")
    return all_metrics
