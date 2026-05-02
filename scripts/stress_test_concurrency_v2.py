"""Binary-search stress test for API concurrency limits using real exp paths.

Tests two phases using the EXACT same code paths as the real experiment:
  Phase 1 - Query:   RAGPipeline.query() with real retrieval + generation
  Phase 2 - Eval:    BuiltinEvaluator.evaluate_batch() with real metric LLM calls

This produces token consumption patterns identical to real experiments,
so the measured concurrency limits are reliable.

Usage:
    pixi run python scripts/stress_test_concurrency_v2.py --meal <meal_name>
    pixi run python scripts/stress_test_concurrency_v2.py --meal <meal_name> --hi 30 --lo 1

Environment: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_ID (from .env)
"""

import argparse
import contextlib
import json
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from dotenv import load_dotenv
from loguru import logger

from eval.evaluators.base import EvaluationSample
from eval.evaluators.builtin_evaluator import BuiltinEvaluator
from src.pipeline import RAGPipeline
from src.utils import get_llm_config, load_config


def _load_test_set(meal_name: str) -> dict | None:
    data_dir = Path(os.getenv("DATA_DIR", "data"))
    meals_dir = data_dir / "meals" / meal_name / "test_sets"
    if not meals_dir.exists():
        return None
    for f in meals_dir.iterdir():
        if f.suffix == ".json":
            with open(f, encoding="utf-8") as fh:
                return json.load(fh)
    return None


def _build_pipeline(meal_name: str, concurrent_queries: int) -> RAGPipeline:
    config = load_config("config.yaml")
    config.setdefault("evaluation", {})
    config["evaluation"]["concurrent_queries"] = concurrent_queries
    pipeline = RAGPipeline(config=config, meal_name=meal_name)
    return pipeline


def _run_query_phase(
    pipeline: RAGPipeline,
    questions: list[dict],
    concurrency: int,
) -> dict:
    wall_start = time.monotonic()
    results = []
    errors = []
    rate_limit_count = 0

    pipelines = [pipeline]
    for _ in range(concurrency - 1):
        pipelines.append(pipeline.clone_for_concurrency())

    _idx = [0]
    import threading

    _lock = threading.Lock()

    def assign_pipeline():
        with _lock:
            idx = _idx[0] % len(pipelines)
            _idx[0] += 1
            return pipelines[idx]

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {}
        for i, q in enumerate(questions):
            p = assign_pipeline()
            question_text = q.get("question", "")
            if not question_text:
                continue
            future = pool.submit(p.query, question_text)
            futures[future] = (i, q)

        for future in as_completed(futures):
            i, q = futures[future]
            try:
                result = future.result()
                results.append({"id": i, "ok": True, "result": result})
            except Exception as e:
                err_str = str(e)
                is_rate_limit = any(
                    s in err_str.lower() for s in ["429", "rate", "throttl", "overload"]
                )
                if is_rate_limit:
                    rate_limit_count += 1
                errors.append(
                    {"id": i, "ok": False, "error": err_str, "is_429": is_rate_limit}
                )

    wall_elapsed = time.monotonic() - wall_start

    for p in pipelines[1:]:
        with contextlib.suppress(Exception):
            p.close()

    return {
        "concurrency": concurrency,
        "num_questions": len(questions),
        "wall_time": wall_elapsed,
        "ok": len(results),
        "err": len(errors),
        "rate_limit_errors": rate_limit_count,
        "other_errors": len(errors) - rate_limit_count,
    }


def _run_eval_phase(
    samples: list[dict],
    config: dict,
    concurrency: int,
) -> dict:
    eval_config = dict(config)
    eval_config.setdefault("evaluation", {})
    eval_config["evaluation"]["builtin_concurrent_workers"] = concurrency

    evaluator = BuiltinEvaluator(config=eval_config)

    llm_config = get_llm_config(config, "default")

    eval_samples = []
    for s in samples:
        eval_samples.append(
            EvaluationSample(
                question_id=s.get("question_id", "q_unknown"),
                question=s.get("question", ""),
                answer=s.get("answer", ""),
                contexts=s.get("contexts", []),
                expected_sources=s.get("expected_sources", []),
                expected_answer=s.get("expected_answer"),
                llm_config=llm_config,
                retrieval_metrics=["hit_rate"],
                generation_metrics=["faithfulness", "answer_relevancy"],
                chunk_ids=s.get("chunk_ids", []),
                expected_chunks=s.get("expected_chunks", []),
                equivalence_groups=s.get("equivalence_groups"),
                expect_retrieval=s.get("expect_retrieval", True),
                expect_no_answer=s.get("expect_no_answer", False),
                retrieved_sources=s.get("retrieved_sources", []),
                question_type=s.get("question_type", "factual"),
            )
        )

    wall_start = time.monotonic()
    rate_limit_count = 0
    other_error_count = 0
    ok_count = 0

    try:
        eval_results = evaluator.evaluate_batch(eval_samples, llm_config=llm_config)
        ok_count = len(eval_results)
        for r in eval_results:
            if r.error:
                is_rate = any(
                    s in str(r.error).lower()
                    for s in ["429", "rate", "throttl", "overload"]
                )
                if is_rate:
                    rate_limit_count += 1
                else:
                    other_error_count += 1
                ok_count -= 1
    except Exception as e:
        err_str = str(e)
        is_rate = any(
            s in err_str.lower() for s in ["429", "rate", "throttl", "overload"]
        )
        if is_rate:
            rate_limit_count = len(eval_samples)
        else:
            other_error_count = len(eval_samples)

    wall_elapsed = time.monotonic() - wall_start

    return {
        "concurrency": concurrency,
        "num_samples": len(eval_samples),
        "wall_time": wall_elapsed,
        "ok": ok_count,
        "err": rate_limit_count + other_error_count,
        "rate_limit_errors": rate_limit_count,
        "other_errors": other_error_count,
    }


def _has_rate_limit(result: dict) -> bool:
    return result["rate_limit_errors"] > 0 or result["other_errors"] > 0


def _binary_search_phase(
    phase_name: str,
    run_fn,
    lo: int,
    hi: int,
) -> dict:
    print(f"\n{'=' * 70}")
    print(f"  Phase: {phase_name}")
    print(f"  Binary search range: [{lo}, {hi}]")
    print(f"{'=' * 70}")
    print(
        f"{'CQ':>4} | {'Wall(s)':>8} | {'OK':>4} | {'Err':>4} | {'429':>4} | {'Other':>5} | Status"
    )
    print("-" * 60)

    safe_max = 0
    all_results = []
    tested = set()

    while lo <= hi:
        mid = (lo + hi) // 2
        if mid in tested:
            break
        tested.add(mid)

        r = run_fn(mid)
        all_results.append(r)

        is_rejected = _has_rate_limit(r)
        status = "REJECTED" if is_rejected else "OK"

        print(
            f"{r['concurrency']:>4} | "
            f"{r['wall_time']:>8.2f} | "
            f"{r['ok']:>4} | "
            f"{r['err']:>4} | "
            f"{r['rate_limit_errors']:>4} | "
            f"{r['other_errors']:>5} | "
            f"{status}"
        )

        if is_rejected:
            hi = mid - 1
        else:
            safe_max = mid
            lo = mid + 1

    if safe_max > 0 and (safe_max + 1) not in tested and safe_max + 1 <= hi + 1:
        verify_r = run_fn(safe_max + 1)
        all_results.append(verify_r)
        is_rejected = _has_rate_limit(verify_r)
        status = "REJECTED" if is_rejected else "OK (surprise!)"
        print(
            f"{verify_r['concurrency']:>4} | "
            f"{verify_r['wall_time']:>8.2f} | "
            f"{verify_r['ok']:>4} | "
            f"{verify_r['err']:>4} | "
            f"{verify_r['rate_limit_errors']:>4} | "
            f"{verify_r['other_errors']:>5} | "
            f"{status} (boundary verify)"
        )
        if not is_rejected:
            safe_max = safe_max + 1

    print(f"\n  {phase_name} max safe concurrency: {safe_max}")
    return {"phase": phase_name, "safe_max": safe_max, "results": all_results}


def main():
    load_dotenv()

    parser = argparse.ArgumentParser(
        description="Binary-search API concurrency limit using real exp paths"
    )
    parser.add_argument(
        "--meal", required=True, help="Meal name with existing test set"
    )
    parser.add_argument(
        "--hi", type=int, default=30, help="Upper bound of binary search"
    )
    parser.add_argument(
        "--lo", type=int, default=1, help="Lower bound of binary search"
    )
    parser.add_argument(
        "--phase",
        choices=["query", "eval", "both"],
        default="both",
        help="Which phase to test",
    )
    args = parser.parse_args()

    test_set = _load_test_set(args.meal)
    if test_set is None:
        logger.error(f"No test set found for meal '{args.meal}'")
        return

    questions = test_set.get("questions", [])
    questions = [
        q for q in questions if q.get("metadata", {}).get("review_status") != "rejected"
    ]
    if not questions:
        logger.error("No valid questions found in test set")
        return

    logger.info(f"Loaded {len(questions)} questions from meal '{args.meal}'")

    config = load_config("config.yaml")

    query_result = None
    eval_result = None
    samples_for_eval = None

    if args.phase in ("query", "both"):
        logger.info("Building pipeline for query phase...")
        pipeline = _build_pipeline(args.meal, concurrent_queries=1)

        def run_query(concurrency: int) -> dict:
            p = _build_pipeline(args.meal, concurrent_queries=1)
            return _run_query_phase(p, questions, concurrency)

        query_result = _binary_search_phase(
            "Query (pipeline.query)",
            run_query,
            lo=args.lo,
            hi=args.hi,
        )

        pipeline.close()

        if query_result["safe_max"] > 0:
            best_cq = query_result["safe_max"]
            logger.info(
                f"Collecting samples at best concurrency={best_cq} for eval phase..."
            )
            p = _build_pipeline(args.meal, concurrent_queries=1)
            samples_for_eval = _run_query_phase(p, questions, best_cq)
            p.close()

    if args.phase in ("eval", "both"):
        if samples_for_eval is None and args.phase == "eval":
            logger.info("Running serial query to collect samples for eval phase...")
            p = _build_pipeline(args.meal, concurrent_queries=1)
            raw = _run_query_phase(p, questions, 1)
            p.close()
            samples_for_eval = raw

        if isinstance(samples_for_eval, dict):
            sample_list = []
            for r in samples_for_eval.get("results", []):
                if r.get("ok") and "result" in r:
                    res = r["result"]
                    q_data = questions[r["id"]]
                    sample_list.append(
                        {
                            "question_id": q_data.get("id", f"q{r['id'] + 1}"),
                            "question": q_data.get("question", ""),
                            "answer": res.get("answer", ""),
                            "contexts": res.get("contexts", []),
                            "expected_sources": q_data.get("source_files", []),
                            "expected_answer": q_data.get("answer"),
                            "retrieved_sources": res.get("sources", []),
                            "chunk_ids": res.get("chunk_ids", []),
                            "expected_chunks": q_data.get("source_chunks", []),
                            "question_type": q_data.get("question_type", "factual"),
                            "expect_retrieval": q_data.get("expect_retrieval", True),
                            "expect_no_answer": q_data.get("expect_no_answer", False),
                        }
                    )
            samples_for_eval = sample_list

        if not samples_for_eval:
            logger.error("No samples available for eval phase")
        else:
            logger.info(f"Using {len(samples_for_eval)} samples for eval phase")

            def run_eval(concurrency: int) -> dict:
                return _run_eval_phase(samples_for_eval, config, concurrency)

            eval_result = _binary_search_phase(
                "Eval (BuiltinEvaluator.evaluate_batch)",
                run_eval,
                lo=args.lo,
                hi=args.hi,
            )

    print("\n" + "=" * 70)
    print("  FINAL SUMMARY")
    print("=" * 70)
    if query_result:
        print(f"  Query phase  max safe concurrency: {query_result['safe_max']}")
    if eval_result:
        print(f"  Eval phase   max safe concurrency: {eval_result['safe_max']}")
    print()
    print("  Recommended config.yaml settings:")
    if query_result:
        q_val = max(1, query_result["safe_max"] - 2)
        print(f"    concurrent_queries: {q_val}  (safe_max - 2)")
    if eval_result:
        e_val = max(1, eval_result["safe_max"] - 2)
        print(f"    builtin_concurrent_workers: {e_val}  (safe_max - 2)")
        print(f"    ragas.run_config.max_workers: {e_val}  (safe_max - 2)")


if __name__ == "__main__":
    main()
