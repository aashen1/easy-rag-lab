from eval.metrics.chunk import (
    calculate_chunk_hit_rate,
    calculate_chunk_mrr,
    calculate_chunk_ndcg,
)
from eval.metrics.dedup import (
    calculate_dedup_hit_rate,
    calculate_dedup_mrr,
    calculate_dedup_ndcg,
    deduplicate_by_document,
)
from eval.metrics.fpr import calculate_false_positive_rate
from eval.metrics.llm_retrieval import (
    calculate_context_precision,
    calculate_context_recall,
    can_infer_from_context,
    judge_context_relevance,
    split_into_sentences,
)
from eval.metrics.retrieval import (
    calculate_hit_rate,
    calculate_mrr,
    calculate_ndcg,
    calculate_retrieval_diversity,
)
from eval.metrics.utils import (
    normalize_source,
    normalize_source_with_equivalence,
    parse_chunk_id,
)

_GENERATION_EXPORTS = [
    "calculate_answer_relevancy",
    "calculate_faithfulness",
    "calculate_hallucination_rate",
    "extract_statements",
    "parse_relevancy_response",
    "verify_statements",
]


def __getattr__(name):
    if name in _GENERATION_EXPORTS:
        from eval.metrics.generation import (
            calculate_answer_relevancy,
            calculate_faithfulness,
            calculate_hallucination_rate,
            extract_statements,
            parse_relevancy_response,
            verify_statements,
        )

        result = locals()[name]
        globals()[name] = result
        return result
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "calculate_hit_rate",
    "calculate_mrr",
    "calculate_ndcg",
    "calculate_retrieval_diversity",
    "calculate_chunk_hit_rate",
    "calculate_chunk_mrr",
    "calculate_chunk_ndcg",
    "deduplicate_by_document",
    "calculate_dedup_hit_rate",
    "calculate_dedup_mrr",
    "calculate_dedup_ndcg",
    "calculate_false_positive_rate",
    "calculate_faithfulness",
    "calculate_answer_relevancy",
    "calculate_hallucination_rate",
    "calculate_context_precision",
    "calculate_context_recall",
    "normalize_source",
    "normalize_source_with_equivalence",
    "extract_statements",
    "parse_relevancy_response",
    "verify_statements",
    "can_infer_from_context",
    "judge_context_relevance",
    "split_into_sentences",
    "parse_chunk_id",
]
