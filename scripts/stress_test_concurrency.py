"""Binary-search stress test for LongCat API concurrency limits.

Tests two phases using the EXACT same SDK call pattern as the real pipeline:
  Phase 1 - Query:   short prompt (simulates pipeline.query() → Generator)
  Phase 2 - RAGAS:   long prompt (simulates RAGAS metric evaluation)

Binary searches from a high starting concurrency DOWN to the max safe level.

Usage:
    pixi run python scripts/stress_test_concurrency.py [--hi N] [--lo N] [--requests N]

Environment: LLM_API_KEY, LLM_BASE_URL, LLM_MODEL_ID (from .env)
"""

import argparse
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from anthropic import Anthropic
from dotenv import load_dotenv
from loguru import logger

QUERY_PROMPT = "请简要说明什么是净资产收益率（ROE）。"
RAGAS_PROMPT = (
    "你是一个专业的金融研报评估专家。请根据以下上下文，评估回答的忠实度（Faithfulness）。\n\n"
    "上下文：\n"
    "净资产收益率（ROE）是衡量公司盈利能力的重要指标，计算公式为净利润除以股东权益。"
    "ROE越高，说明公司运用股东资金的效率越高。一般来说，ROE持续高于15%的公司具有较强的竞争优势。"
    "但需要注意，过高的ROE可能源于高杠杆，而非真正的经营效率提升。杜邦分析法将ROE分解为"
    "净利润率、资产周转率和权益乘数三个部分，有助于深入理解ROE的驱动因素。\n\n"
    "回答：ROE是净利润除以股东权益，越高越好。\n\n"
    "请评估该回答是否完全基于上下文信息，是否存在幻觉或推断。给出1-10的评分和理由。"
)


def create_client(api_key: str, base_url: str) -> Anthropic:
    base_url = base_url.rstrip("/")
    if not base_url.endswith("/anthropic"):
        base_url = f"{base_url}/anthropic"
    return Anthropic(
        api_key="dummy",
        base_url=base_url,
        default_headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json",
        },
    )


def fire_request(
    client: Anthropic, model: str, prompt: str, max_tokens: int, req_id: int
) -> dict:
    start = time.monotonic()
    try:
        client.messages.create(
            model=model,
            max_tokens=max_tokens,
            temperature=0.0,
            messages=[{"role": "user", "content": f"{prompt} (id={req_id})"}],
        )
        elapsed = time.monotonic() - start
        return {"id": req_id, "ok": True, "latency": elapsed, "error": None}
    except Exception as e:
        elapsed = time.monotonic() - start
        error_type = type(e).__name__
        status = getattr(e, "status_code", None)
        return {
            "id": req_id,
            "ok": False,
            "latency": elapsed,
            "error": f"{error_type}(status={status}): {e}",
        }


def run_round(
    client: Anthropic,
    model: str,
    prompt: str,
    max_tokens: int,
    concurrency: int,
    num_requests: int,
) -> dict:
    results = []
    wall_start = time.monotonic()

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = [
            pool.submit(fire_request, client, model, prompt, max_tokens, i)
            for i in range(num_requests)
        ]
        for f in as_completed(futures):
            results.append(f.result())

    wall_elapsed = time.monotonic() - wall_start
    ok_count = sum(1 for r in results if r["ok"])
    err_count = sum(1 for r in results if not r["ok"])

    rate_limit_errs = []
    other_errs = []
    for r in results:
        if not r["ok"] and r["error"]:
            if (
                "429" in r["error"]
                or "rate" in r["error"].lower()
                or "throttl" in r["error"].lower()
                or "overload" in r["error"].lower()
            ):
                rate_limit_errs.append(r["error"])
            else:
                other_errs.append(r["error"])

    latencies = [r["latency"] for r in results if r["ok"]]

    return {
        "concurrency": concurrency,
        "num_requests": num_requests,
        "wall_time": wall_elapsed,
        "ok": ok_count,
        "err": err_count,
        "rate_limit_errors": len(rate_limit_errs),
        "other_errors": len(other_errs),
        "latency_avg": sum(latencies) / len(latencies) if latencies else 0,
        "latency_p50": sorted(latencies)[len(latencies) // 2] if latencies else 0,
        "latency_max": max(latencies) if latencies else 0,
        "error_samples": (rate_limit_errs + other_errs)[:3],
    }


def has_rate_limit(result: dict) -> bool:
    return result["rate_limit_errors"] > 0 or result["other_errors"] > 0


def binary_search(
    client: Anthropic,
    model: str,
    phase_name: str,
    prompt: str,
    max_tokens: int,
    lo: int,
    hi: int,
    num_requests: int,
) -> dict:
    print(f"\n{'=' * 70}")
    print(f"  Phase: {phase_name}")
    print(f"  Binary search range: [{lo}, {hi}], {num_requests} requests/round")
    print(f"{'=' * 70}")
    print(
        f"{'CQ':>4} | {'Wall(s)':>8} | {'OK':>4} | {'Err':>4} | {'429':>4} | {'Other':>5} | {'Avg(s)':>7} | {'P50(s)':>7} | {'Max(s)':>7} | Status"
    )
    print("-" * 95)

    safe_max = 0
    all_results = []
    tested = set()

    while lo <= hi:
        mid = (lo + hi) // 2
        if mid in tested:
            break
        tested.add(mid)

        r = run_round(client, model, prompt, max_tokens, mid, num_requests)
        all_results.append(r)

        is_rejected = has_rate_limit(r)
        status = "❌ REJECTED" if is_rejected else "✅ OK"

        print(
            f"{r['concurrency']:>4} | "
            f"{r['wall_time']:>8.2f} | "
            f"{r['ok']:>4} | "
            f"{r['err']:>4} | "
            f"{r['rate_limit_errors']:>4} | "
            f"{r['other_errors']:>5} | "
            f"{r['latency_avg']:>7.3f} | "
            f"{r['latency_p50']:>7.3f} | "
            f"{r['latency_max']:>7.3f} | "
            f"{status}"
        )

        if r["error_samples"]:
            for sample in r["error_samples"][:1]:
                print(f"     └─ {sample[:80]}")

        if is_rejected:
            hi = mid - 1
        else:
            safe_max = mid
            lo = mid + 1

    # Verify the boundary with one more round at safe_max + 1 if not tested
    if safe_max > 0 and (safe_max + 1) not in tested and safe_max + 1 <= hi + 1:
        verify_r = run_round(
            client, model, prompt, max_tokens, safe_max + 1, num_requests
        )
        all_results.append(verify_r)
        is_rejected = has_rate_limit(verify_r)
        status = "❌ REJECTED" if is_rejected else "✅ OK (surprise!)"
        print(
            f"{verify_r['concurrency']:>4} | "
            f"{verify_r['wall_time']:>8.2f} | "
            f"{verify_r['ok']:>4} | "
            f"{verify_r['err']:>4} | "
            f"{verify_r['rate_limit_errors']:>4} | "
            f"{verify_r['other_errors']:>5} | "
            f"{verify_r['latency_avg']:>7.3f} | "
            f"{verify_r['latency_p50']:>7.3f} | "
            f"{verify_r['latency_max']:>7.3f} | "
            f"{status} (boundary verify)"
        )
        if not is_rejected:
            safe_max = safe_max + 1

    all_results.sort(key=lambda x: x["concurrency"])

    print(f"\n  🏆 {phase_name} max safe concurrency: {safe_max}")
    return {"phase": phase_name, "safe_max": safe_max, "results": all_results}


def main():
    load_dotenv()

    api_key = os.getenv("LLM_API_KEY")
    base_url = os.getenv("LLM_BASE_URL")
    model = os.getenv("LLM_MODEL_ID", "LongCat-Flash-Lite")

    if not api_key or not base_url:
        logger.error("LLM_API_KEY and LLM_BASE_URL must be set in .env")
        return

    parser = argparse.ArgumentParser(description="Binary-search API concurrency limit")
    parser.add_argument(
        "--hi", type=int, default=40, help="Upper bound of binary search (must fail)"
    )
    parser.add_argument(
        "--lo", type=int, default=1, help="Lower bound of binary search"
    )
    parser.add_argument("--requests", type=int, default=8, help="Requests per round")
    args = parser.parse_args()

    client = create_client(api_key, base_url)
    logger.info(f"Model: {model}")
    logger.info(f"Search range: [{args.lo}, {args.hi}], {args.requests} requests/round")

    # Phase 1: Query (short prompt, 256 max_tokens)
    query_result = binary_search(
        client,
        model,
        "Query (pipeline.query)",
        QUERY_PROMPT,
        max_tokens=256,
        lo=args.lo,
        hi=args.hi,
        num_requests=args.requests,
    )

    # Phase 2: RAGAS evaluation (long prompt, 1024 max_tokens)
    ragas_result = binary_search(
        client,
        model,
        "RAGAS (metric evaluation)",
        RAGAS_PROMPT,
        max_tokens=1024,
        lo=args.lo,
        hi=args.hi,
        num_requests=args.requests,
    )

    print("\n" + "=" * 70)
    print("  FINAL SUMMARY")
    print("=" * 70)
    print(f"  Model: {model}")
    print(f"  Query phase  max safe concurrency: {query_result['safe_max']}")
    print(f"  RAGAS phase  max safe concurrency: {ragas_result['safe_max']}")
    print()
    print("  Recommended config.yaml settings:")
    print(
        f"    concurrent_queries: {max(1, query_result['safe_max'] - 2)}  (safe_max - 2)"
    )
    print(
        f"    builtin_concurrent_workers: {max(1, ragas_result['safe_max'] - 2)}  (safe_max - 2)"
    )
    print(
        f"    ragas.run_config.max_workers: {max(1, ragas_result['safe_max'] - 2)}  (safe_max - 2)"
    )


if __name__ == "__main__":
    main()
