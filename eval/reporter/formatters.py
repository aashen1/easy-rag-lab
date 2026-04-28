from typing import Any


def get_generation_metric(
    gen_metrics: dict[str, float], metric_name: str
) -> float | None:
    """Get a generation metric value, handling builtin_/ragas_ prefixes.

    Priority: builtin > ragas > unprefixed (for backward compatibility)

    Args:
        gen_metrics: Dictionary of generation metrics.
        metric_name: Base metric name (e.g., 'faithfulness', 'answer_relevancy').

    Returns:
        Metric value or None if not found.
    """
    builtin_key = f"avg_builtin_{metric_name}"
    ragas_key = f"avg_ragas_{metric_name}"
    unprefixed_key = f"avg_{metric_name}"

    if builtin_key in gen_metrics and gen_metrics[builtin_key] is not None:
        return gen_metrics[builtin_key]
    if ragas_key in gen_metrics and gen_metrics[ragas_key] is not None:
        return gen_metrics[ragas_key]
    if unprefixed_key in gen_metrics and gen_metrics[unprefixed_key] is not None:
        return gen_metrics[unprefixed_key]
    return None


def get_all_generation_metrics(
    gen_metrics: dict[str, float], metric_name: str
) -> dict[str, float]:
    """Get all generation metric values with their prefixes.

    Args:
        gen_metrics: Dictionary of generation metrics.
        metric_name: Base metric name (e.g., 'faithfulness', 'answer_relevancy').

    Returns:
        Dictionary with prefixed metric names and values.
    """
    result = {}
    for prefix in ["builtin", "ragas"]:
        key = f"avg_{prefix}_{metric_name}"
        if key in gen_metrics and gen_metrics[key] is not None:
            result[prefix] = gen_metrics[key]
    unprefixed_key = f"avg_{metric_name}"
    if unprefixed_key in gen_metrics and gen_metrics[unprefixed_key] is not None:
        result["default"] = gen_metrics[unprefixed_key]
    return result


def dict_to_yaml_lines(data: Any, indent: int = 0) -> list[str]:
    """Convert a dict to YAML-like lines with arbitrary nesting depth.

    Args:
        data: Data to convert (dict, list, or scalar).
        indent: Current indentation level.

    Returns:
        List of YAML-formatted lines.
    """
    lines = []
    prefix = "  " * indent

    if isinstance(data, dict):
        for k, v in data.items():
            if isinstance(v, dict):
                lines.append(f"{prefix}{k}:")
                lines.extend(dict_to_yaml_lines(v, indent + 1))
            elif isinstance(v, list):
                lines.append(f"{prefix}{k}:")
                for item in v:
                    if isinstance(item, dict):
                        lines.append(f"{prefix}  -")
                        lines.extend(dict_to_yaml_lines(item, indent + 2))
                    else:
                        lines.append(f"{prefix}  - {item}")
            else:
                lines.append(f"{prefix}{k}: {v}")
    elif isinstance(data, list):
        for item in data:
            if isinstance(item, dict):
                lines.append(f"{prefix}-")
                lines.extend(dict_to_yaml_lines(item, indent + 1))
            else:
                lines.append(f"{prefix}- {item}")
    else:
        lines.append(f"{prefix}{data}")

    return lines


def generate_tech_summary(merged_config: dict[str, Any]) -> list[str]:
    """Generate a concise technology summary from merged config.

    Args:
        merged_config: Full merged configuration dictionary.

    Returns:
        List of markdown lines summarizing key technology choices.
    """
    lines = []
    retrieval = merged_config.get("retrieval", {})
    chunker = merged_config.get("chunker", {})
    embedding = merged_config.get("embedding", {})
    vector_store = merged_config.get("vector_store", {})

    method = retrieval.get("method", "vector")
    method_labels = {
        "vector": "Vector (dense)",
        "bm25": "BM25 (sparse)",
        "hybrid": "Hybrid (dense + sparse)",
    }
    lines.append(f"- Retrieval: {method_labels.get(method, method)}")
    lines.append(f"- Top-K: {retrieval.get('top_k', 5)}")

    reranker = retrieval.get("reranker", {})
    if reranker.get("enabled", False):
        lines.append(
            f"- Reranker: {reranker.get('model_name', 'N/A')} (top_n={reranker.get('top_n', 3)})"
        )
    else:
        lines.append("- Reranker: Disabled")

    query_rewrite = retrieval.get("query_rewrite", {})
    if query_rewrite.get("enabled", False):
        lines.append(f"- Query Rewrite: {query_rewrite.get('strategy', 'N/A')}")
    else:
        lines.append("- Query Rewrite: Disabled")

    if method == "hybrid":
        hybrid = retrieval.get("hybrid", {})
        lines.append(
            f"- Fusion: {hybrid.get('fusion', 'rrf')} (rrf_k={hybrid.get('rrf_k', 60)})"
        )

    lines.append(
        f"- Chunking: {chunker.get('strategy', 'fixed')} (size={chunker.get('chunk_size', 512)}, overlap={chunker.get('chunk_overlap', 0)})"
    )
    lines.append(f"- Embedding: {embedding.get('model_name', 'N/A')}")
    lines.append(
        f"- Vector Store: {vector_store.get('type', 'N/A')} ({vector_store.get('distance', 'Cosine')})"
    )

    return lines


def get_metric_description(metric: str) -> str:
    """Get description for a retrieval metric.

    Args:
        metric: Metric name (e.g., 'avg_hit_rate', 'avg_mrr').

    Returns:
        Human-readable description of the metric.
    """
    descriptions = {
        "avg_hit_rate": "Percentage of queries where relevant docs were retrieved",
        "avg_mrr": "Average position of first relevant document",
        "avg_ndcg": "Normalized ranking quality across all positions",
    }
    return descriptions.get(metric, "Retrieval quality metric")


def get_generation_metric_description(metric: str) -> str:
    """Get description for a generation quality metric.

    Args:
        metric: Metric name (e.g., 'avg_faithfulness', 'avg_builtin_faithfulness').

    Returns:
        Human-readable description of the metric.
    """
    descriptions = {
        "avg_faithfulness": "How well the answer is grounded in retrieved contexts",
        "avg_answer_relevancy": "How relevant the answer is to the question",
        "avg_builtin_faithfulness": "Builtin: How well the answer is grounded in retrieved contexts",
        "avg_builtin_answer_relevancy": "Builtin: How relevant the answer is to the question",
        "avg_ragas_faithfulness": "RAGAS: How well the answer is grounded in retrieved contexts",
        "avg_ragas_answer_relevancy": "RAGAS: How relevant the answer is to the question",
        "avg_ragas_context_precision": "RAGAS: How precise the retrieved contexts are",
        "avg_ragas_context_recall": "RAGAS: How completely the contexts cover the ground truth",
        "avg_ragas_answer_correctness": "RAGAS: How correct the answer is compared to reference",
        "avg_ragas_semantic_similarity": "RAGAS: Semantic similarity between answer and reference",
    }
    if metric not in descriptions:
        for prefix in ["builtin_", "ragas_"]:
            if prefix in metric:
                base_metric = metric.replace(prefix, "")
                base_desc = descriptions.get(f"avg_{base_metric}", "")
                backend = prefix.rstrip("_").upper()
                if base_desc:
                    return f"{backend}: {base_desc}"
                return f"{backend}: Generation quality metric"
    return descriptions.get(metric, "Generation quality metric")
