from __future__ import annotations

import contextlib
import json
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from loguru import logger

from eval.evaluators.base import BaseEvaluator, EvaluationResult, EvaluationSample
from eval.evaluators.builtin_evaluator import BuiltinEvaluator
from eval.evaluators.ragas_evaluator import RagasEvaluator
from eval.metrics.metric_resolver import MetricResolver
from eval.runner.metrics import build_legacy_resolver, merge_result, namespace_result
from src.exceptions import ConfigurationError
from src.experiment import ExperimentConfig
from src.pipeline import RAGPipeline
from src.utils import get_llm_config, sanitize_name


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


def _save_question_checkpoint(
    checkpoint_path: Path,
    variant_name: str,
    experiment_name: str,
    samples: list[dict[str, Any]],
    total_questions: int,
    model_name: str = "",
) -> None:
    """
    Save question-level checkpoint for resume support.

    Args:
        checkpoint_path: Path to the checkpoint file.
        variant_name: Name of the variant being evaluated.
        experiment_name: Name of the experiment.
        samples: List of collected samples so far.
        total_questions: Total number of questions to process.
        model_name: LLM model name used for generation (for change detection).
    """
    checkpoint_data = {
        "variant_name": variant_name,
        "experiment_name": experiment_name,
        "model_name": model_name,
        "completed_questions": len(samples),
        "total_questions": total_questions,
        "samples": samples,
    }
    tmp_path = checkpoint_path.with_suffix(".json.tmp")
    try:
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(checkpoint_data, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, checkpoint_path)
    except OSError as e:
        logger.warning(f"Failed to save question checkpoint: {str(e)}")
        with contextlib.suppress(OSError):
            tmp_path.unlink()


def _load_question_checkpoint(
    checkpoint_path: Path,
) -> list[dict[str, Any]] | None:
    """
    Load question-level checkpoint if available.

    Args:
        checkpoint_path: Path to the checkpoint file.

    Returns:
        List of previously collected samples, or None if no valid checkpoint.
    """
    if not checkpoint_path.exists():
        return None

    try:
        with open(checkpoint_path, encoding="utf-8") as f:
            data = json.load(f)
        samples = data.get("samples", [])
        if samples:
            logger.info(
                f"Loaded question checkpoint: {data.get('completed_questions', 0)}/"
                f"{data.get('total_questions', '?')} questions already completed "
                f"for variant '{data.get('variant_name', '?')}'"
            )
            return samples
    except (json.JSONDecodeError, OSError) as e:
        logger.warning(f"Failed to load question checkpoint: {str(e)}")

    return None


def collect_rag_samples(
    pipeline: RAGPipeline,
    test_set: dict[str, Any],
    equivalence_groups: dict[str, list[str]] | None = None,
    checkpoint_dir: Path | None = None,
    variant_name: str = "",
    experiment_name: str = "",
    model_name: str = "",
    max_questions: int | None = None,
) -> list[dict[str, Any]]:
    """
    Run pipeline queries and collect raw samples for evaluation.

    Supports question-level checkpointing: each completed question result is
    appended to a checkpoint file so that if the process is interrupted, the
    next run can resume from where it left off.

    Args:
        pipeline: Configured RAG pipeline.
        test_set: Test set dictionary with questions.
        equivalence_groups: Optional dict mapping group keys to lists of
            equivalent file paths for dedup normalization.
        checkpoint_dir: Optional directory for saving question-level checkpoints.
        variant_name: Name of the variant (for checkpoint file naming).
        experiment_name: Name of the experiment (for checkpoint metadata).
        model_name: LLM model name used for generation (for change detection).
        max_questions: If set, only evaluate the first N questions (partial
            evaluation for quick verification).

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

    if max_questions is not None and max_questions < len(questions):
        logger.info(
            f"Partial evaluation: using first {max_questions}/{len(questions)} questions"
        )
        questions = questions[:max_questions]

    logger.info(
        f"Collecting results for test set '{test_set_name}' ({len(questions)} questions)..."
    )

    concurrent_workers = _get_concurrent_workers(pipeline, len(questions))

    checkpoint_path: Path | None = None
    if checkpoint_dir is not None and variant_name:
        checkpoint_dir.mkdir(parents=True, exist_ok=True)
        safe_name = sanitize_name(variant_name)
        checkpoint_path = checkpoint_dir / f"{safe_name}_checkpoint.json"

    samples: list[dict[str, Any]] = []
    start_index = 0

    if checkpoint_path is not None:
        existing = _load_question_checkpoint(checkpoint_path)
        if existing is not None:
            samples = existing
            start_index = len(samples)
            if start_index >= len(questions):
                logger.info(
                    f"All {len(questions)} questions already completed, using checkpoint"
                )
                return samples
            logger.info(f"Resuming from question {start_index + 1}/{len(questions)}")

    if concurrent_workers > 1 and start_index < len(questions):
        samples = _collect_rag_samples_concurrent(
            pipeline=pipeline,
            questions=questions,
            start_index=start_index,
            test_set_name=test_set_name,
            equivalence_groups=equivalence_groups,
            concurrent_workers=concurrent_workers,
            checkpoint_path=checkpoint_path,
            variant_name=variant_name,
            experiment_name=experiment_name,
            model_name=model_name,
        )
    else:
        samples = _collect_rag_samples_serial(
            pipeline=pipeline,
            questions=questions,
            start_index=start_index,
            test_set_name=test_set_name,
            equivalence_groups=equivalence_groups,
            checkpoint_path=checkpoint_path,
            variant_name=variant_name,
            experiment_name=experiment_name,
            model_name=model_name,
            existing_samples=samples,
        )

    return samples


def _get_concurrent_workers(pipeline: RAGPipeline, remaining: int) -> int:
    """
    Determine the number of concurrent query workers.

    Args:
        pipeline: RAG pipeline instance.
        remaining: Number of questions remaining to process.

    Returns:
        Number of workers (1 = serial, >1 = concurrent).
    """
    concurrent_cfg = pipeline.config.get("evaluation", {}).get("concurrent_queries", 1)
    if concurrent_cfg < 1:
        concurrent_cfg = 1
    if remaining < 2:
        return 1
    return min(concurrent_cfg, remaining)


def _query_single_question(
    pipeline: RAGPipeline,
    question_data: dict[str, Any],
    question_idx: int,
    total_questions: int,
    test_set_name: str,
    equivalence_groups: dict[str, list[str]] | None,
) -> dict[str, Any]:
    """
    Query a single question against the pipeline.

    Each call uses an independent pipeline instance, so no locking is needed.

    Args:
        pipeline: RAG pipeline instance (dedicated to this thread).
        question_data: Question dictionary.
        question_idx: Question index (0-based).
        total_questions: Total number of questions.
        test_set_name: Name of the test set.
        equivalence_groups: Optional equivalence groups for dedup.

    Returns:
        Sample dictionary with query results.
    """
    question_id = question_data.get("id", f"q{question_idx + 1}")
    question_text = question_data.get("question", "")

    if not question_text:
        logger.warning(f"Question {question_id} has no text, skipping")
        return {
            "question_id": question_id,
            "question": "",
            "_skip": True,
        }

    logger.info(
        f"Processing question {question_idx + 1}/{total_questions}: {question_id}"
    )

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

        logger.success(f"Question {question_id}: collected result ({case_time:.2f}s)")
        return sample

    except Exception as e:
        case_time = time.time() - case_start_time
        logger.error(f"Question {question_id} failed: {str(e)}")
        return {
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


def _collect_rag_samples_serial(
    pipeline: RAGPipeline,
    questions: list[dict[str, Any]],
    start_index: int,
    test_set_name: str,
    equivalence_groups: dict[str, list[str]] | None,
    checkpoint_path: Path | None,
    variant_name: str,
    experiment_name: str,
    model_name: str,
    existing_samples: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Collect RAG samples serially (original behavior).

    Args:
        pipeline: RAG pipeline instance.
        questions: List of question dictionaries.
        start_index: Index to start from (for checkpoint resume).
        test_set_name: Name of the test set.
        equivalence_groups: Optional equivalence groups.
        checkpoint_path: Optional checkpoint file path.
        variant_name: Variant name for checkpoint.
        experiment_name: Experiment name for checkpoint.
        model_name: LLM model name for checkpoint.
        existing_samples: Previously collected samples (from checkpoint).

    Returns:
        Complete list of sample dictionaries.
    """
    samples = list(existing_samples)

    for i in range(start_index, len(questions)):
        question_data = questions[i]
        question_id = question_data.get("id", f"q{i + 1}")
        question_text = question_data.get("question", "")

        if not question_text:
            logger.warning(f"Question {question_id} has no text, skipping")
            samples.append(
                {
                    "question_id": question_id,
                    "question": "",
                    "_skip": True,
                }
            )
            continue

        logger.info(f"Processing question {i + 1}/{len(questions)}: {question_id}")

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

        if checkpoint_path is not None:
            checkpoint_samples = [
                {k: v for k, v in s.items() if k != "_skip"}
                for s in samples
                if not s.get("_skip")
            ]
            _save_question_checkpoint(
                checkpoint_path,
                variant_name,
                experiment_name,
                checkpoint_samples,
                len(questions),
                model_name=model_name,
            )

    return [
        {k: v for k, v in s.items() if k != "_skip"}
        for s in samples
        if not s.get("_skip")
    ]


def _collect_rag_samples_concurrent(
    pipeline: RAGPipeline,
    questions: list[dict[str, Any]],
    start_index: int,
    test_set_name: str,
    equivalence_groups: dict[str, list[str]] | None,
    concurrent_workers: int,
    checkpoint_path: Path | None,
    variant_name: str,
    experiment_name: str,
    model_name: str,
) -> list[dict[str, Any]]:
    """
    Collect RAG samples using concurrent query execution.

    Creates independent pipeline clones for each worker. Each clone shares
    the same vector indexer (thread-safe Qdrant client) but has its own
    LLM generator, enabling true concurrent LLM API calls.

    Args:
        pipeline: RAG pipeline instance (used as template for clones).
        questions: List of question dictionaries.
        start_index: Index to start from (for checkpoint resume).
        test_set_name: Name of the test set.
        equivalence_groups: Optional equivalence groups.
        concurrent_workers: Number of concurrent workers.
        checkpoint_path: Optional checkpoint file path.
        variant_name: Variant name for checkpoint.
        experiment_name: Experiment name for checkpoint.
        model_name: LLM model name for checkpoint.

    Returns:
        List of sample dictionaries with query results.
    """
    remaining_questions = questions[start_index:]
    logger.info(
        f"Concurrent query mode: {len(remaining_questions)} questions, "
        f"{concurrent_workers} workers"
    )

    pipelines: list[RAGPipeline] = [pipeline]
    for _ in range(concurrent_workers - 1):
        pipelines.append(pipeline.clone_for_concurrency())

    _pipeline_idx = [0]
    _idx_lock = threading.Lock()

    def assign_pipeline() -> RAGPipeline:
        with _idx_lock:
            idx = _pipeline_idx[0] % len(pipelines)
            _pipeline_idx[0] += 1
            return pipelines[idx]

    results_dict: dict[int, dict[str, Any]] = {}
    _results_lock = threading.Lock()

    def _on_future_done(fut: Any, real_idx: int) -> None:
        try:
            result = fut.result()
        except Exception as e:
            question_data = remaining_questions[real_idx - start_index]
            question_id = question_data.get("id", f"q{real_idx + 1}")
            logger.error(f"Concurrent query failed for {question_id}: {str(e)}")
            result = {
                "question_id": question_id,
                "question": question_data.get("question", ""),
                "answer": "",
                "contexts": [],
                "expected_sources": question_data.get("source_files", []),
                "expected_answer": question_data.get("answer"),
                "retrieved_sources": [],
                "chunk_ids": [],
                "expected_chunks": question_data.get("source_chunks", []),
                "equivalence_groups": equivalence_groups,
                "question_type": question_data.get("question_type", "factual"),
                "time_seconds": 0,
                "test_set": test_set_name,
                "error": str(e),
            }

        with _results_lock:
            results_dict[real_idx] = result
            if checkpoint_path is not None:
                sorted_samples = []
                for k in sorted(results_dict.keys()):
                    r = results_dict[k]
                    if r.get("_skip"):
                        continue
                    r_copy = {kk: vv for kk, vv in r.items() if kk != "_skip"}
                    sorted_samples.append(r_copy)
                _save_question_checkpoint(
                    checkpoint_path,
                    variant_name,
                    experiment_name,
                    sorted_samples,
                    len(questions),
                    model_name=model_name,
                )

    with ThreadPoolExecutor(max_workers=concurrent_workers) as executor:
        future_to_idx = {}
        for offset, question_data in enumerate(remaining_questions):
            real_idx = start_index + offset
            assigned = assign_pipeline()
            future = executor.submit(
                _query_single_question,
                assigned,
                question_data,
                real_idx,
                len(questions),
                test_set_name,
                equivalence_groups,
            )
            future.add_done_callback(
                lambda fut, idx=real_idx: _on_future_done(fut, idx)
            )
            future_to_idx[future] = real_idx

        for _future in as_completed(future_to_idx):
            pass

    samples = []
    for idx in sorted(results_dict.keys()):
        result = results_dict[idx]
        if result.get("_skip"):
            continue
        result.pop("_skip", None)
        samples.append(result)

    for p in pipelines[1:]:
        with contextlib.suppress(Exception):
            p.close()

    return samples


def _format_eval_result(
    sample: dict[str, Any],
    eval_result: EvaluationResult,
) -> dict[str, Any]:
    """Format an EvaluationResult into the result dict used by evaluate_with_builtin.

    Args:
        sample: Original sample dictionary from collect_rag_samples.
        eval_result: EvaluationResult from the builtin evaluator.

    Returns:
        Formatted result dictionary.
    """
    question_id = sample["question_id"]
    raw_retrieval = eval_result.retrieval_metrics

    doc_metrics: dict[str, Any] = {}
    chunk_metrics: dict[str, Any] = {}
    dedup_metrics: dict[str, Any] = {}
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

    result: dict[str, Any] = {
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

    return result


def evaluate_with_builtin(
    samples: list[dict[str, Any]],
    evaluator: BuiltinEvaluator,
    llm_config: dict[str, str] | None = None,
    retrieval_metrics: list[str] | None = None,
    generation_metrics: list[str] | None = None,
) -> list[dict[str, Any]]:
    """
    Evaluate samples using the builtin evaluator.

    Uses evaluator.evaluate_batch() which supports concurrent generation
    metric computation via ThreadPoolExecutor when generation metrics are
    requested and builtin_concurrent_workers > 1 in config.

    Args:
        samples: List of sample dictionaries from collect_rag_samples.
        evaluator: BuiltinEvaluator instance.
        llm_config: Optional LLM configuration for generation metrics.
        retrieval_metrics: Optional list of retrieval metrics to compute.
        generation_metrics: Optional list of generation metrics to compute.

    Returns:
        List of evaluation result dictionaries.
    """
    error_results: dict[int, dict[str, Any]] = {}
    valid_entries: list[tuple[int, dict[str, Any], EvaluationSample]] = []

    for idx, sample in enumerate(samples):
        question_id = sample["question_id"]

        if "error" in sample:
            error_results[idx] = {
                "id": question_id,
                "question": sample["question"],
                "answer": None,
                "error": sample["error"],
                "expected_sources": sample.get("expected_sources", []),
                "time_seconds": sample.get("time_seconds", 0),
                "test_set": sample.get("test_set", ""),
                "category": sample.get("category"),
            }
            continue

        expected_answer = sample.get("ground_truth_excerpt")
        if not expected_answer and sample.get("expect_retrieval", True):
            expected_answer = sample.get("expected_answer")

        eval_sample = EvaluationSample(
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
        valid_entries.append((idx, sample, eval_sample))

    if valid_entries:
        eval_samples = [es for _, _, es in valid_entries]
        batch_results = evaluator.evaluate_batch(
            samples=eval_samples,
            llm_config=llm_config,
            retrieval_metrics=retrieval_metrics,
            generation_metrics=generation_metrics,
        )

        for entry, eval_result in zip(valid_entries, batch_results, strict=True):
            idx, sample, _ = entry
            error_results[idx] = _format_eval_result(sample, eval_result)

    return [error_results[i] for i in range(len(samples))]


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
    checkpoint_dir: Path | None = None,
    variant_name: str = "",
    experiment_name: str = "",
    max_questions: int | None = None,
    profiler: Any | None = None,
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
        checkpoint_dir: Optional directory for question-level checkpoints.
        variant_name: Name of the variant (for checkpoint file naming).
        experiment_name: Name of the experiment (for checkpoint metadata).
        max_questions: If set, only evaluate the first N questions.
        profiler: Optional PipelineProfiler for S9 evaluation stage tracking.

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
        pipeline,
        test_set,
        equivalence_groups=equivalence_groups,
        checkpoint_dir=checkpoint_dir,
        variant_name=variant_name,
        experiment_name=experiment_name,
        model_name=llm_config.get("model_name", "") if llm_config else "",
        max_questions=max_questions,
    )

    all_results: dict[str, dict[str, Any]] = {}
    use_namespace = resolver.strategy == "comparison"

    eval_backend_names = list(allocation.keys())
    s9_metadata = {
        "backends": eval_backend_names,
        "num_samples": len(samples),
    }

    s9_context = (
        profiler.profile_stage("S9", s9_metadata)
        if profiler
        else contextlib.nullcontext()
    )

    with s9_context:
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
                or any(
                    m in ("context_precision", "context_recall") for m in ret_metrics
                )
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
