from __future__ import annotations

import time
from typing import Any

from loguru import logger

from eval.evaluators.base import BaseEvaluator, EvaluationSample
from eval.evaluators.builtin_evaluator import BuiltinEvaluator
from eval.evaluators.ragas_evaluator import RagasEvaluator
from eval.metrics.metric_resolver import MetricResolver
from eval.runner.metrics import build_legacy_resolver, merge_result, namespace_result
from src.exceptions import ConfigurationError
from src.experiment import ExperimentConfig
from src.pipeline import RAGPipeline
from src.utils import get_llm_config


def create_evaluators(
    exp_config: ExperimentConfig,
    system_config: dict[str, Any],
) -> dict[str, BaseEvaluator]:
    """
    Create evaluator instances based on experiment configuration.

    Args:
        exp_config: Experiment configuration.
        system_config: System configuration dictionary.

    Returns:
        Dictionary mapping backend name to evaluator instance.
    """
    backends = exp_config.evaluation.get("backends", ["builtin"])
    evaluators: dict[str, BaseEvaluator] = {}

    for backend in backends:
        if backend == "builtin":
            evaluators["builtin"] = BuiltinEvaluator(config=system_config)
        elif backend == "ragas":
            ragas_config = system_config.get("evaluation", {}).get("ragas", {})
            evaluators["ragas"] = RagasEvaluator(
                config={**system_config, "ragas": ragas_config}
            )
        else:
            logger.warning(f"Unknown evaluation backend: {backend}")

    return evaluators


def collect_rag_samples(
    pipeline: RAGPipeline,
    test_set: dict[str, Any],
    equivalence_groups: dict[str, list[str]] | None = None,
) -> list[dict[str, Any]]:
    """
    Run pipeline queries and collect raw samples for evaluation.

    Args:
        pipeline: Configured RAG pipeline.
        test_set: Test set dictionary with questions.
        equivalence_groups: Optional dict mapping group keys to lists of
            equivalent file paths for dedup normalization.

    Returns:
        List of sample dictionaries with query results.
    """
    test_set_name = test_set.get("name") or test_set.get("metadata", {}).get(
        "name", "unknown"
    )
    questions = test_set.get("questions", [])
    questions = [
        q for q in questions if q.get("metadata", {}).get("review_status") != "rejected"
    ]

    logger.info(
        f"Collecting results for test set '{test_set_name}' ({len(questions)} questions)..."
    )

    samples = []
    for i, question_data in enumerate(questions, 1):
        question_id = question_data.get("id", f"q{i}")
        question_text = question_data.get("question", "")

        if not question_text:
            logger.warning(f"Question {question_id} has no text, skipping")
            continue

        logger.info(f"Processing question {i}/{len(questions)}: {question_id}")

        case_start_time = time.time()
        try:
            response = pipeline.query(question_text)
            case_time = time.time() - case_start_time

            sample = {
                "question_id": question_id,
                "question": question_text,
                "answer": response.get("answer", ""),
                "contexts": response.get("contexts", []),
                "expected_sources": question_data.get("source_files", []),
                "expected_answer": question_data.get("answer"),
                "ground_truth_excerpt": question_data.get("ground_truth_excerpt"),
                "retrieved_sources": response.get("sources", []),
                "chunk_ids": response.get("chunk_ids", []),
                "expected_chunks": question_data.get("source_chunks", []),
                "equivalence_groups": equivalence_groups,
                "question_type": question_data.get("question_type", "factual"),
                "time_seconds": case_time,
                "test_set": test_set_name,
                "category": question_data.get("category"),
                "difficulty": question_data.get("difficulty"),
                "token_usage": response.get("token_usage"),
                "expect_retrieval": question_data.get("expect_retrieval", True),
                "expect_no_answer": question_data.get("expect_no_answer", False),
            }

            logger.success(
                f"Question {question_id}: collected result ({case_time:.2f}s)"
            )

        except Exception as e:
            case_time = time.time() - case_start_time
            logger.error(f"Question {question_id} failed: {str(e)}")
            sample = {
                "question_id": question_id,
                "question": question_text,
                "answer": "",
                "contexts": [],
                "expected_sources": question_data.get("source_files", []),
                "expected_answer": question_data.get("answer"),
                "ground_truth_excerpt": question_data.get("ground_truth_excerpt"),
                "retrieved_sources": [],
                "chunk_ids": [],
                "expected_chunks": question_data.get("source_chunks", []),
                "equivalence_groups": equivalence_groups,
                "question_type": question_data.get("question_type", "factual"),
                "expect_retrieval": question_data.get("expect_retrieval", True),
                "expect_no_answer": question_data.get("expect_no_answer", False),
                "time_seconds": case_time,
                "test_set": test_set_name,
                "category": question_data.get("category"),
                "error": str(e),
            }

        samples.append(sample)

    return samples


def evaluate_with_builtin(
    samples: list[dict[str, Any]],
    evaluator: BuiltinEvaluator,
    llm_config: dict[str, str] | None = None,
    retrieval_metrics: list[str] | None = None,
    generation_metrics: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate samples using the builtin evaluator.

    Args:
        samples: List of sample dictionaries from collect_rag_samples.
        evaluator: BuiltinEvaluator instance.
        llm_config: Optional LLM configuration for generation metrics.
        retrieval_metrics: Optional list of retrieval metrics to compute.
        generation_metrics: Optional list of generation metrics to compute.

    Returns:
        List of evaluation result dictionaries.
    """
    results = []
    for sample in samples:
        question_id = sample["question_id"]

        if "error" in sample:
            result = {
                "id": question_id,
                "question": sample["question"],
                "answer": None,
                "error": sample["error"],
                "expected_sources": sample.get("expected_sources", []),
                "time_seconds": sample.get("time_seconds", 0),
                "test_set": sample.get("test_set", ""),
                "category": sample.get("category"),
            }
            results.append(result)
            continue

        expected_answer = sample.get("ground_truth_excerpt")
        if not expected_answer and sample.get("expect_retrieval", True):
            expected_answer = sample.get("expected_answer")

        eval_result = evaluator.evaluate_single(
            EvaluationSample(
                question_id=question_id,
                question=sample["question"],
                answer=sample["answer"],
                contexts=sample.get("contexts", []),
                expected_sources=sample.get("expected_sources"),
                expected_answer=expected_answer,
                llm_config=llm_config,
                retrieval_metrics=retrieval_metrics,
                generation_metrics=generation_metrics,
                chunk_ids=sample.get("chunk_ids"),
                expected_chunks=sample.get("expected_chunks"),
                equivalence_groups=sample.get("equivalence_groups"),
                expect_retrieval=sample.get("expect_retrieval", True),
                expect_no_answer=sample.get("expect_no_answer", False),
                retrieved_sources=sample.get("retrieved_sources", []),
                question_type=sample.get("question_type"),
            )
        )

        raw_retrieval = eval_result.retrieval_metrics

        doc_metrics = {}
        chunk_metrics = {}
        dedup_metrics = {}
        fpr_value = None

        for k, v in raw_retrieval.items():
            if k.startswith("chunk_"):
                chunk_metrics[k.removeprefix("chunk_")] = v
            elif k.startswith("dedup_"):
                dedup_metrics[k.removeprefix("dedup_")] = v
            elif k == "false_positive_rate":
                fpr_value = v
            else:
                doc_metrics[k] = v

        result = {
            "id": question_id,
            "question": sample["question"],
            "answer": sample["answer"],
            "retrieval": doc_metrics,
            "chunk_retrieval": chunk_metrics if chunk_metrics else None,
            "dedup_retrieval": dedup_metrics if dedup_metrics else None,
            "false_positive_rate": fpr_value,
            "sources": sample.get("retrieved_sources", []),
            "expected_sources": sample.get("expected_sources", []),
            "time_seconds": sample.get("time_seconds", 0),
            "test_set": sample.get("test_set", ""),
            "category": sample.get("category"),
            "difficulty": sample.get("difficulty"),
            "question_type": sample.get("question_type"),
            "expect_retrieval": sample.get("expect_retrieval", True),
            "token_usage": sample.get("token_usage"),
        }

        if eval_result.generation_metrics:
            result["generation"] = eval_result.generation_metrics

        if eval_result.error:
            result["error"] = eval_result.error

        metric_parts = []
        for k, v in eval_result.retrieval_metrics.items():
            if v is not None:
                metric_parts.append(f"{k.upper()}={v:.4f}")
        for k, v in eval_result.generation_metrics.items():
            if v is not None:
                metric_parts.append(f"{k}={v:.4f}")
        metric_str = ", ".join(metric_parts) if metric_parts else "no metrics"
        logger.success(f"Question {question_id}: {metric_str}")

        results.append(result)

    return results


def evaluate_with_ragas(
    samples: list[dict[str, Any]],
    evaluator: RagasEvaluator,
    llm_config: dict[str, str],
    generation_metrics: list[str] | None = None,
    retrieval_metrics: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate samples using the RAGAS evaluator.

    Args:
        samples: List of sample dictionaries from collect_rag_samples.
        evaluator: RagasEvaluator instance.
        llm_config: LLM configuration for RAGAS.
        generation_metrics: Optional list of generation metrics to compute.
        retrieval_metrics: Optional list of retrieval metrics to compute
            (RAGAS-supported ones like context_precision, context_recall).

    Returns:
        List of evaluation result dictionaries.
    """
    valid_samples = [s for s in samples if "error" not in s]

    if not valid_samples:
        logger.warning("No valid samples for RAGAS evaluation")
        return []

    ragas_from_retrieval = [
        m
        for m in (retrieval_metrics or [])
        if m in evaluator.supported_generation_metrics
    ]

    all_ragas_metrics = list(
        dict.fromkeys((generation_metrics or []) + ragas_from_retrieval)
    )

    if not all_ragas_metrics:
        return []

    logger.info(f"Running RAGAS evaluation on {len(valid_samples)} samples...")

    ragas_samples = [
        EvaluationSample(
            question_id=s.get("question_id", ""),
            question=s.get("question", ""),
            answer=s.get("answer", ""),
            contexts=s.get("contexts", []),
            expected_sources=s.get("expected_sources"),
            expected_answer=s.get("expected_answer"),
            expect_retrieval=s.get("expect_retrieval", True),
        )
        for s in valid_samples
    ]

    ragas_results = evaluator.evaluate_batch(
        samples=ragas_samples,
        llm_config=llm_config,
        retrieval_metrics=retrieval_metrics,
        generation_metrics=all_ragas_metrics,
    )

    retrieval_metric_names = set(ragas_from_retrieval)

    results = []
    for i, eval_result in enumerate(ragas_results):
        sample = valid_samples[i]

        generation_part = {}
        llm_retrieval_part = {}
        expect_retrieval = sample.get("expect_retrieval", True)

        for k, v in eval_result.generation_metrics.items():
            if k in retrieval_metric_names:
                if expect_retrieval:
                    llm_retrieval_part[k] = v
            else:
                if not expect_retrieval and k in (
                    "answer_correctness",
                    "semantic_similarity",
                ):
                    continue
                generation_part[k] = v

        result = {
            "id": sample["question_id"],
            "question": sample["question"],
            "answer": sample["answer"],
            "generation": generation_part,
            "sources": sample.get("retrieved_sources", []),
            "expected_sources": sample.get("expected_sources", []),
            "time_seconds": sample.get("time_seconds", 0),
            "test_set": sample.get("test_set", ""),
            "category": sample.get("category"),
            "difficulty": sample.get("difficulty"),
        }

        if llm_retrieval_part:
            result["llm_retrieval"] = llm_retrieval_part

        if eval_result.error:
            result["ragas_error"] = eval_result.error

        metric_parts = []
        for k, v in eval_result.generation_metrics.items():
            if v is not None:
                if k in retrieval_metric_names and not expect_retrieval:
                    continue
                metric_parts.append(f"{k}={v:.4f}")
        metric_str = ", ".join(metric_parts) if metric_parts else "no metrics"
        if not expect_retrieval:
            logger.success(
                f"Question {sample['question_id']} (RAGAS): {metric_str} (expect_retrieval=False, skipped LLM retrieval)"
            )
        else:
            logger.success(f"Question {sample['question_id']} (RAGAS): {metric_str}")

        results.append(result)

    return results


def evaluate_test_set(
    pipeline: RAGPipeline,
    test_set: dict[str, Any],
    exp_config: ExperimentConfig | None = None,
    system_config: dict[str, Any] | None = None,
    meal_info: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate a single test set against the pipeline.

    Uses MetricResolver to determine which metrics each backend should
    compute, based on the configured resolution strategy and metrics preset.

    Args:
        pipeline: Configured RAG pipeline.
        test_set: Test set dictionary with questions.
        exp_config: Experiment configuration for backend selection.
        system_config: System configuration for evaluator creation.
        meal_info: Optional meal information containing equivalence_groups.

    Returns:
        List of evaluation result dictionaries.

    Raises:
        ValueError: If exp_config or system_config is not provided.
    """
    if exp_config is None or system_config is None:
        raise ConfigurationError(
            "exp_config and system_config are required for evaluation. "
            "Please use run_experiment.py with a valid experiment configuration."
        )

    evaluators = create_evaluators(exp_config, system_config)
    eval_config = exp_config.evaluation

    retrieval_metrics = eval_config.get("metrics", {}).get("retrieval")
    generation_metrics = eval_config.get("metrics", {}).get("generation")

    llm_preset = eval_config.get("llm_preset", "default")
    llm_config = get_llm_config(system_config, llm_preset)

    resolution_strategy = eval_config.get("resolution_strategy", "priority_fallback")
    backend_priority = eval_config.get("backend_priority", None)
    metrics_preset = eval_config.get("metrics_preset", None)
    custom_metrics = eval_config.get("custom_metrics", None)

    if metrics_preset and not retrieval_metrics and not generation_metrics:
        resolver = MetricResolver(
            evaluators=evaluators,
            strategy=resolution_strategy,
            backend_priority=backend_priority,
            metrics_preset=metrics_preset,
            custom_metrics=custom_metrics,
        )
    else:
        resolver = build_legacy_resolver(
            evaluators, retrieval_metrics, generation_metrics
        )

    unresolvable = resolver.validate()
    if unresolvable:
        logger.warning(
            f"The following metrics cannot be computed by any backend: {unresolvable}"
        )

    allocation = resolver.resolve()

    equivalence_groups = meal_info.get("equivalence_groups") if meal_info else None
    samples = collect_rag_samples(
        pipeline, test_set, equivalence_groups=equivalence_groups
    )

    all_results: dict[str, dict[str, Any]] = {}
    use_namespace = resolver.strategy == "comparison"

    for backend_name, metrics in allocation.items():
        if backend_name not in evaluators:
            logger.warning(f"Backend '{backend_name}' not available, skipping")
            continue

        evaluator = evaluators[backend_name]
        ret_metrics = metrics.get("retrieval", [])
        gen_metrics = metrics.get("generation", [])

        if not ret_metrics and not gen_metrics:
            continue

        needs_llm = bool(
            gen_metrics
            or any(m in ("context_precision", "context_recall") for m in ret_metrics)
        )

        if backend_name == "builtin":
            results = evaluate_with_builtin(
                samples=samples,
                evaluator=evaluator,
                llm_config=llm_config if needs_llm else None,
                retrieval_metrics=ret_metrics or None,
                generation_metrics=gen_metrics or None,
            )
        elif backend_name == "ragas":
            results = evaluate_with_ragas(
                samples=samples,
                evaluator=evaluator,
                llm_config=llm_config,
                generation_metrics=gen_metrics or None,
                retrieval_metrics=ret_metrics or None,
            )
        else:
            logger.warning(f"Unknown backend '{backend_name}', skipping")
            continue

        for r in results:
            if use_namespace:
                r = namespace_result(r, backend_name)
            qid = r["id"]
            if qid in all_results:
                merge_result(all_results[qid], r)
            else:
                all_results[qid] = r

    return list(all_results.values())
