"""Utility functions for report generation."""


def generate_recommendations(
    hr: float | None = None,
    mrr: float | None = None,
    ndcg: float | None = None,
    faithfulness: float | None = None,
    relevancy: float | None = None,
    has_generation_metrics: bool = False,
    performance_message: str = "Current performance is satisfactory for baseline.",
) -> list[str]:
    """Generate optimization recommendations based on metric thresholds.

    Args:
        hr: Hit rate score.
        mrr: Mean reciprocal rank score.
        ndcg: Normalized discounted cumulative gain score.
        faithfulness: Faithfulness score.
        relevancy: Answer relevancy score.
        has_generation_metrics: Whether generation metrics are available.
        performance_message: Message to show when performance is satisfactory.

    Returns:
        List of recommendation strings.
    """
    recommendations = []
    rec_num = 1

    if hr is not None and hr < 0.6:
        recommendations.append(
            f"{rec_num}. Consider increasing `top_k` to retrieve more candidates."
        )
        rec_num += 1
        recommendations.append(
            f"{rec_num}. Evaluate embedding model quality for domain-specific content."
        )
        rec_num += 1

    if mrr is not None and mrr < 0.5:
        recommendations.append(
            f"{rec_num}. Consider adding a reranker to improve ranking."
        )
        rec_num += 1
        recommendations.append(
            f"{rec_num}. Review chunking strategy for better context preservation."
        )
        rec_num += 1

    if ndcg is not None and ndcg < 0.5:
        recommendations.append(
            f"{rec_num}. Consider hybrid retrieval (BM25 + vector search)."
        )
        rec_num += 1

    if has_generation_metrics:
        if faithfulness is not None and faithfulness < 0.6:
            recommendations.append(
                f"{rec_num}. Review prompt engineering to reduce hallucinations."
            )
            rec_num += 1
            recommendations.append(
                f"{rec_num}. Ensure retrieved contexts are relevant and complete."
            )
            rec_num += 1

        if relevancy is not None and relevancy < 0.6:
            recommendations.append(
                f"{rec_num}. Improve question understanding in the generation prompt."
            )
            rec_num += 1
            recommendations.append(
                f"{rec_num}. Consider answer validation or filtering."
            )
            rec_num += 1

    if not recommendations:
        recommendations.append(f"{rec_num}. {performance_message}")
        rec_num += 1
        recommendations.append(
            f"{rec_num}. Consider fine-tuning embedding model for domain-specific improvements."
        )
        rec_num += 1
        recommendations.append(
            f"{rec_num}. Explore advanced retrieval strategies for edge cases."
        )
        rec_num += 1

    return recommendations
