from __future__ import annotations

from typing import Any

from loguru import logger

from src.retrieval_analyzer import compute_ground_truth_metrics
from src.trace_models import ROOT_CAUSES, DiagnosisResult, GroundTruth, PipelineTrace


def diagnose(
    trace: PipelineTrace | dict[str, Any],
    ground_truth: GroundTruth | dict[str, Any],
) -> DiagnosisResult:
    """Diagnose the root cause of a bad case using trace and ground truth.

    Applies a decision tree to classify the root cause into one of six
    categories (RC-0 through RC-5) based on where the ground truth chunk
    appears or disappears in the pipeline.

    Args:
        trace: PipelineTrace object or its dict representation.
        ground_truth: GroundTruth object or its dict representation.

    Returns:
        DiagnosisResult with root cause classification, severity, finding,
        fix suggestion, and config patch.
    """
    if isinstance(ground_truth, dict):
        gt_chunk_ids = ground_truth.get("chunk_ids") or []
        gt_answer = ground_truth.get("answer_text", "")
    else:
        gt_chunk_ids = ground_truth.chunk_ids or []
        gt_answer = ground_truth.answer_text

    metrics = compute_ground_truth_metrics(trace, gt_chunk_ids)

    if not gt_chunk_ids:
        logger.debug("Empty ground truth chunk IDs; defaulting to RC-1")
        return DiagnosisResult(
            root_cause=ROOT_CAUSES["RC-1"][0],
            root_cause_id="RC-1",
            severity="high",
            finding=f"Ground truth chunk (ids: {gt_chunk_ids}) 未出现在检索结果中",
            fix_suggestion="正确答案未被召回，建议增大 top_k 或更换检索方法",
            config_patch={"retrieval.top_k": 10, "retrieval.method": "hybrid"},
            confidence=0.8,
        )

    found_in_retrieval = metrics["found_in_retrieval"]
    retrieval_rank = metrics["retrieval_rank"]
    found_in_rerank = metrics["found_in_rerank"]
    rerank_rank = metrics["rerank_rank"]
    found_in_context = metrics["found_in_context"]
    context_dropped = metrics["context_dropped"]

    if not found_in_retrieval:
        if _has_query_mismatch(trace):
            logger.debug("GT not in retrieval + query mismatch → RC-5")
            return DiagnosisResult(
                root_cause=ROOT_CAUSES["RC-5"][0],
                root_cause_id="RC-5",
                severity="medium",
                finding="查询改写后仍无法命中正确 chunk",
                fix_suggestion="查询与文档词汇不匹配，建议启用查询改写或更换改写策略",
                config_patch={"retrieval.query_rewrite.enabled": True},
                confidence=0.6,
            )
        logger.debug("GT not in retrieval → RC-1")
        return DiagnosisResult(
            root_cause=ROOT_CAUSES["RC-1"][0],
            root_cause_id="RC-1",
            severity="high",
            finding=f"Ground truth chunk (ids: {gt_chunk_ids}) 未出现在检索结果中",
            fix_suggestion="正确答案未被召回，建议增大 top_k 或更换检索方法",
            config_patch={"retrieval.top_k": 10, "retrieval.method": "hybrid"},
            confidence=0.8,
        )

    if context_dropped:
        logger.debug("GT in retrieval but context dropped → RC-3")
        return DiagnosisResult(
            root_cause=ROOT_CAUSES["RC-3"][0],
            root_cause_id="RC-3",
            severity="high",
            finding="Ground truth chunk 在检索结果中但被上下文截断丢弃",
            fix_suggestion="正确答案被上下文截断丢弃，建议增大 max_context_tokens",
            config_patch={"generation.max_context_tokens": 8192},
            confidence=0.8,
        )

    if found_in_rerank and rerank_rank is not None and rerank_rank > 3:
        logger.debug("GT in rerank but rank {} > 3 → RC-2", rerank_rank)
        return DiagnosisResult(
            root_cause=ROOT_CAUSES["RC-2"][0],
            root_cause_id="RC-2",
            severity="medium",
            finding=f"Ground truth chunk 在检索结果中排名 #{rerank_rank}，未进入有效上下文区域",
            fix_suggestion="正确答案排名靠后，建议启用 Reranker 或调整重排序参数",
            config_patch={"retrieval.reranker.enabled": True},
            confidence=0.8,
        )

    if not found_in_rerank and retrieval_rank is not None and retrieval_rank > 3:
        logger.debug("GT not in rerank, retrieval rank {} > 3 → RC-2", retrieval_rank)
        return DiagnosisResult(
            root_cause=ROOT_CAUSES["RC-2"][0],
            root_cause_id="RC-2",
            severity="medium",
            finding=f"Ground truth chunk 在检索结果中排名 #{retrieval_rank}，未进入有效上下文区域",
            fix_suggestion="正确答案排名靠后，建议启用 Reranker 或调整重排序参数",
            config_patch={"retrieval.reranker.enabled": True},
            confidence=0.8,
        )

    effective_rank = rerank_rank if rerank_rank is not None else retrieval_rank

    if found_in_context:
        answer = _get_generation_answer(trace)
        if gt_answer and gt_answer in answer:
            logger.debug("GT in context and answer matches → RC-0")
            return DiagnosisResult(
                root_cause=ROOT_CAUSES["RC-0"][0],
                root_cause_id="RC-0",
                severity="low",
                finding="Ground truth chunk 在 top-1 且答案匹配，管线表现正常",
                fix_suggestion="管线表现正常，可能是误标",
                config_patch={},
                confidence=1.0,
            )
        logger.debug("GT in context but answer mismatch → RC-4")
        rank_info = f"（排名 #{effective_rank}）" if effective_rank is not None else ""
        return DiagnosisResult(
            root_cause=ROOT_CAUSES["RC-4"][0],
            root_cause_id="RC-4",
            severity="medium",
            finding=f"Ground truth chunk 在上下文中{rank_info}，但 LLM 回答未正确利用",
            fix_suggestion="上下文包含正确信息但 LLM 未能正确利用，建议调整系统提示词或更换模型",
            config_patch={},
            confidence=0.8,
        )

    logger.debug("GT in retrieval but rank > context count → RC-2")
    rank_val = effective_rank if effective_rank is not None else retrieval_rank
    return DiagnosisResult(
        root_cause=ROOT_CAUSES["RC-2"][0],
        root_cause_id="RC-2",
        severity="medium",
        finding=f"Ground truth chunk 在检索结果中排名 #{rank_val}，未进入有效上下文区域",
        fix_suggestion="正确答案排名靠后，建议启用 Reranker 或调整重排序参数",
        config_patch={"retrieval.reranker.enabled": True},
        confidence=0.8,
    )


def _has_query_mismatch(trace: PipelineTrace | dict[str, Any]) -> bool:
    """Check whether a query_rewrite step exists and produced different queries.

    Args:
        trace: PipelineTrace object or its dict representation.

    Returns:
        True if query rewrite step exists and rewritten queries differ
        from the original query.
    """
    if isinstance(trace, dict):
        steps = trace.get("steps", [])
        original_query = trace.get("question", "")
    else:
        steps = trace.steps
        original_query = trace.question

    for step in steps:
        stage = step.stage if hasattr(step, "stage") else step.get("stage", "")
        if stage == "query_rewrite":
            output = (
                step.output_data
                if hasattr(step, "output_data")
                else step.get("output_data", {})
            )
            rewritten = output.get("rewritten_queries", [])
            if rewritten and rewritten != [original_query]:
                return True
    return False


def _get_generation_answer(trace: PipelineTrace | dict[str, Any]) -> str:
    """Extract the generation answer from the pipeline trace.

    Args:
        trace: PipelineTrace object or its dict representation.

    Returns:
        The generated answer text, or empty string if not found.
    """
    steps = trace.get("steps", []) if isinstance(trace, dict) else trace.steps

    for step in steps:
        stage = step.stage if hasattr(step, "stage") else step.get("stage", "")
        if stage == "generation":
            output = (
                step.output_data
                if hasattr(step, "output_data")
                else step.get("output_data", {})
            )
            return output.get("answer", "")
    return ""
