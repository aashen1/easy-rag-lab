from __future__ import annotations

from typing import Any

from loguru import logger

from src.trace_models import PipelineTrace


def compute_ground_truth_metrics(
    trace: PipelineTrace | dict[str, Any],
    ground_truth_chunk_ids: list[str],
) -> dict[str, Any]:
    """Compute retrieval metrics for ground truth chunks within a pipeline trace.

    Analyzes the trace steps to determine where ground truth chunks appear
    (or don't appear) in the retrieval, reranking, and context assembly stages.

    Args:
        trace: PipelineTrace object or its dict representation.
        ground_truth_chunk_ids: List of chunk IDs that constitute the ground truth.

    Returns:
        Dictionary with metrics:
        - found_in_retrieval (bool): Whether any GT chunk was in retrieval results
        - retrieval_rank (int | None): Best rank (1-based) of GT chunk in retrieval
        - retrieval_score (float | None): Score of the best-ranked GT chunk
        - found_in_rerank (bool): Whether any GT chunk was in rerank results
        - rerank_rank (int | None): Best rank of GT chunk after reranking
        - rerank_score (float | None): Rerank score of the best-ranked GT chunk
        - found_in_context (bool): Whether any GT chunk survived context assembly
        - context_dropped (bool): Whether GT chunk was in retrieval but dropped from context
    """
    steps = trace.get("steps", []) if isinstance(trace, dict) else trace.steps

    gt_set = set(ground_truth_chunk_ids)

    found_in_retrieval = False
    retrieval_rank = None
    retrieval_score = None

    found_in_rerank = False
    rerank_rank = None
    rerank_score = None

    found_in_context = False
    context_dropped = False

    if not gt_set:
        metrics = {
            "found_in_retrieval": False,
            "retrieval_rank": None,
            "retrieval_score": None,
            "found_in_rerank": False,
            "rerank_rank": None,
            "rerank_score": None,
            "found_in_context": False,
            "context_dropped": False,
        }
        logger.debug("Ground truth chunk IDs empty; all metrics set to defaults")
        return metrics

    retrieval_step = None
    rerank_step = None
    context_step = None

    for step in steps:
        stage = step.stage if hasattr(step, "stage") else step.get("stage", "")
        if stage == "retrieval":
            retrieval_step = step
        elif stage == "rerank":
            rerank_step = step
        elif stage == "context_assembly":
            context_step = step

    if retrieval_step is not None:
        output = (
            retrieval_step.output_data
            if hasattr(retrieval_step, "output_data")
            else retrieval_step.get("output_data", {})
        )
        results = output.get("results", [])
        best_rank = None
        best_score = None
        for idx, item in enumerate(results):
            chunk_id = item.get("chunk_id", "")
            if chunk_id in gt_set:
                rank = idx + 1
                score = item.get("score")
                if best_rank is None or rank < best_rank:
                    best_rank = rank
                    best_score = score
        if best_rank is not None:
            found_in_retrieval = True
            retrieval_rank = best_rank
            retrieval_score = best_score

    if rerank_step is not None:
        output = (
            rerank_step.output_data
            if hasattr(rerank_step, "output_data")
            else rerank_step.get("output_data", {})
        )
        results = output.get("results", [])
        best_rank = None
        best_score = None
        for idx, item in enumerate(results):
            chunk_id = item.get("chunk_id", "")
            if chunk_id in gt_set:
                rank = idx + 1
                score = item.get("score")
                if best_rank is None or rank < best_rank:
                    best_rank = rank
                    best_score = score
        if best_rank is not None:
            found_in_rerank = True
            rerank_rank = best_rank
            rerank_score = best_score

    if context_step is not None:
        ctx_input = (
            context_step.input_data
            if hasattr(context_step, "input_data")
            else context_step.get("input_data", {})
        )
        ctx_output = (
            context_step.output_data
            if hasattr(context_step, "output_data")
            else context_step.get("output_data", {})
        )
        final_context_count = ctx_output.get("final_context_count", 0)
        input_chunks = ctx_input.get("chunks", [])
        gt_in_input_count = sum(
            1 for c in input_chunks if c.get("chunk_id", "") in gt_set
        )
        effective_rank = rerank_rank if rerank_rank is not None else retrieval_rank
        if effective_rank is not None:
            found_in_context = effective_rank <= final_context_count
        if found_in_retrieval and gt_in_input_count > 0 and not found_in_context:
            context_dropped = True
    else:
        if found_in_retrieval:
            found_in_context = True

    metrics = {
        "found_in_retrieval": found_in_retrieval,
        "retrieval_rank": retrieval_rank,
        "retrieval_score": retrieval_score,
        "found_in_rerank": found_in_rerank,
        "rerank_rank": rerank_rank,
        "rerank_score": rerank_score,
        "found_in_context": found_in_context,
        "context_dropped": context_dropped,
    }

    logger.debug("Ground truth metrics computed: {}", metrics)
    return metrics
