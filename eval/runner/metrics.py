from __future__ import annotations

from typing import Any

from eval.evaluators.base import BaseEvaluator
from eval.metrics.metric_resolver import MetricResolver


def build_legacy_resolver(
    evaluators: dict[str, BaseEvaluator],
    retrieval_metrics: list[str] | None,
    generation_metrics: list[str] | None,
) -> MetricResolver:
    """Build a MetricResolver from legacy per-metric config.

    When the user specifies individual metrics via evaluation.metrics.retrieval
    and evaluation.metrics.generation (old style), convert to a custom preset.
    Uses comparison strategy for multi-backend and priority_fallback for
    single-backend to match the original namespace behavior.

    Args:
        evaluators: Available evaluators.
        retrieval_metrics: Legacy retrieval metric list.
        generation_metrics: Legacy generation metric list.

    Returns:
        MetricResolver configured with a custom preset matching legacy behavior.
    """
    custom = {
        "retrieval": retrieval_metrics or [],
        "generation": generation_metrics or [],
    }
    strategy = "comparison" if len(evaluators) > 1 else "priority_fallback"
    return MetricResolver(
        evaluators=evaluators,
        strategy=strategy,
        backend_priority=list(evaluators.keys()),
        metrics_preset="custom",
        custom_metrics=custom,
    )


def namespace_result(result: dict[str, Any], backend_name: str) -> dict[str, Any]:
    """Add backend name prefix to metric keys for comparison mode.

    Args:
        result: Single evaluation result dict.
        backend_name: Backend name to use as prefix.

    Returns:
        Result dict with prefixed metric keys.
    """
    if "generation" in result and result["generation"]:
        result["generation"] = {
            f"{backend_name}_{k}": v for k, v in result["generation"].items()
        }
    if "llm_retrieval" in result and result["llm_retrieval"]:
        result["llm_retrieval"] = {
            f"{backend_name}_{k}": v for k, v in result["llm_retrieval"].items()
        }
    return result


def merge_result(target: dict[str, Any], source: dict[str, Any]) -> None:
    """Merge source result into target, combining metric dicts.

    Args:
        target: Target result dict to merge into (modified in place).
        source: Source result dict to merge from.
    """
    for key in ("generation", "llm_retrieval"):
        if key in source and source[key]:
            if key not in target:
                target[key] = {}
            target[key].update(source[key])
    if "ragas_error" in source:
        target["ragas_error"] = source["ragas_error"]


def compute_aggregate_metrics(results: list[dict[str, Any]]) -> dict[str, Any]:
    """
    Compute aggregate metrics from evaluation results.

    Supports both retrieval and generation metrics. Includes chunk-level,
    dedup, FPR, diversity, hallucination rate, and per-question-type breakdown.

    Args:
        results: List of evaluation result dictionaries.

    Returns:
        Dictionary containing average metrics including hit_rate, mrr, ndcg,
        chunk_level_metrics, dedup_metrics, diversity, hallucination_rate,
        and by_question_type breakdown.
    """
    from eval.metrics import calculate_hallucination_rate

    metrics: dict[str, Any] = {}

    valid_retrieval = [
        r for r in results if r.get("retrieval", {}).get("hit_rate") is not None
    ]
    if valid_retrieval:
        for metric_name in ["hit_rate", "mrr", "ndcg"]:
            values = [
                r["retrieval"][metric_name]
                for r in valid_retrieval
                if metric_name in r["retrieval"]
                and r["retrieval"][metric_name] is not None
            ]
            if values:
                metrics[f"avg_{metric_name}"] = sum(values) / len(values)
            else:
                metrics[f"avg_{metric_name}"] = 0.0
    else:
        metrics["avg_hit_rate"] = 0.0
        metrics["avg_mrr"] = 0.0
        metrics["avg_ndcg"] = 0.0

    metrics["retrieval_applicable_questions"] = len(valid_retrieval)
    metrics["total_questions"] = len(results)

    valid_generation = [r for r in results if "generation" in r and r["generation"]]
    if valid_generation:
        generation_metrics_set = set()
        for r in valid_generation:
            generation_metrics_set.update(r["generation"].keys())

        generation_aggregate = {}
        for metric_name in sorted(generation_metrics_set):
            values = [
                r["generation"][metric_name]
                for r in valid_generation
                if metric_name in r["generation"]
                and r["generation"][metric_name] is not None
            ]
            if values:
                generation_aggregate[f"avg_{metric_name}"] = sum(values) / len(values)

        if generation_aggregate:
            metrics["generation_metrics"] = generation_aggregate

    chunk_results = [
        r
        for r in results
        if r.get("chunk_retrieval") is not None and r["chunk_retrieval"]
    ]
    if chunk_results:
        avg_chunk_hit_rate = sum(
            r["chunk_retrieval"].get("hit_rate", 0) for r in chunk_results
        ) / len(chunk_results)
        avg_chunk_mrr = sum(
            r["chunk_retrieval"].get("mrr", 0) for r in chunk_results
        ) / len(chunk_results)
        avg_chunk_ndcg = sum(
            r["chunk_retrieval"].get("ndcg", 0) for r in chunk_results
        ) / len(chunk_results)
    else:
        avg_chunk_hit_rate = None
        avg_chunk_mrr = None
        avg_chunk_ndcg = None

    dedup_results = [
        r
        for r in results
        if r.get("dedup_retrieval") is not None and r["dedup_retrieval"]
    ]
    if dedup_results:
        avg_dedup_hit_rate = sum(
            r["dedup_retrieval"].get("hit_rate", 0) for r in dedup_results
        ) / len(dedup_results)
        avg_dedup_mrr = sum(
            r["dedup_retrieval"].get("mrr", 0) for r in dedup_results
        ) / len(dedup_results)
        avg_dedup_ndcg = sum(
            r["dedup_retrieval"].get("ndcg", 0) for r in dedup_results
        ) / len(dedup_results)
    else:
        avg_dedup_hit_rate = None
        avg_dedup_mrr = None
        avg_dedup_ndcg = None

    fpr_results = [r for r in results if r.get("false_positive_rate") is not None]
    avg_false_positive_rate = (
        sum(r["false_positive_rate"] for r in fpr_results) / len(fpr_results)
        if fpr_results
        else None
    )

    metrics["chunk_level_metrics"] = {
        "avg_hit_rate": avg_chunk_hit_rate,
        "avg_mrr": avg_chunk_mrr,
        "avg_ndcg": avg_chunk_ndcg,
        "retrieval_applicable_questions": len(chunk_results),
    }
    metrics["dedup_metrics"] = {
        "avg_hit_rate": avg_dedup_hit_rate,
        "avg_mrr": avg_dedup_mrr,
        "avg_ndcg": avg_dedup_ndcg,
    }
    metrics["avg_false_positive_rate"] = avg_false_positive_rate
    metrics["irrelevant_questions_count"] = len(fpr_results)

    diversity_values = [
        r["retrieval"]["retrieval_diversity"]
        for r in valid_retrieval
        if "retrieval_diversity" in r.get("retrieval", {})
        and r["retrieval"]["retrieval_diversity"] is not None
    ]
    metrics["avg_retrieval_diversity"] = (
        sum(diversity_values) / len(diversity_values) if diversity_values else None
    )

    faithfulness_values = [
        r["generation"]["faithfulness"]
        for r in valid_generation
        if "faithfulness" in r.get("generation", {})
        and r["generation"]["faithfulness"] is not None
    ]
    metrics["hallucination_rate"] = (
        calculate_hallucination_rate(faithfulness_values)
        if faithfulness_values
        else None
    )

    type_groups: dict[str, list[dict[str, Any]]] = {}
    for r in results:
        qtype = r.get("question_type", "unknown")
        if qtype not in type_groups:
            type_groups[qtype] = []
        type_groups[qtype].append(r)

    type_metrics: dict[str, dict[str, Any]] = {}
    for qtype, group in type_groups.items():
        type_entry: dict[str, Any] = {"count": len(group)}

        type_valid_retrieval = [
            r for r in group if r.get("retrieval", {}).get("hit_rate") is not None
        ]
        for mn in ["hit_rate", "mrr", "ndcg", "retrieval_diversity"]:
            vals = [
                r["retrieval"][mn]
                for r in type_valid_retrieval
                if mn in r["retrieval"] and r["retrieval"][mn] is not None
            ]
            if vals:
                type_entry[f"avg_{mn}"] = sum(vals) / len(vals)

        type_valid_gen = [r for r in group if "generation" in r and r["generation"]]
        for mn in ["faithfulness", "answer_relevancy"]:
            vals = []
            for r in type_valid_gen:
                gen = r["generation"]
                value = None
                for prefix in ["builtin_", "ragas_", ""]:
                    key = f"{prefix}{mn}" if prefix else mn
                    if key in gen and gen[key] is not None:
                        value = gen[key]
                        break
                if value is not None:
                    vals.append(value)
            if vals:
                type_entry[f"avg_{mn}"] = sum(vals) / len(vals)

        type_metrics[qtype] = type_entry

    if type_metrics:
        metrics["by_question_type"] = type_metrics

    llm_retrieval_results = [
        r for r in results if "llm_retrieval" in r and r["llm_retrieval"]
    ]
    llm_retrieval_from_generation = []
    for r in results:
        if "generation" in r and r["generation"]:
            gen = r["generation"]
            llm_keys = {
                k: v
                for k, v in gen.items()
                if k in {"context_precision", "context_recall"} and v is not None
            }
            if llm_keys:
                llm_retrieval_from_generation.append(llm_keys)

    all_llm_retrieval = []
    for r in llm_retrieval_results:
        all_llm_retrieval.append(r["llm_retrieval"])
    all_llm_retrieval.extend(llm_retrieval_from_generation)

    if all_llm_retrieval:
        cp_values = [
            lr["context_precision"]
            for lr in all_llm_retrieval
            if "context_precision" in lr and lr["context_precision"] is not None
        ]
        if cp_values:
            metrics["avg_context_precision"] = sum(cp_values) / len(cp_values)

        cr_values = [
            lr["context_recall"]
            for lr in all_llm_retrieval
            if "context_recall" in lr and lr["context_recall"] is not None
        ]
        if cr_values:
            metrics["avg_context_recall"] = sum(cr_values) / len(cr_values)

    return metrics
