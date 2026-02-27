"""
AI Command Center — Google AI Mode Benchmark
Measures: throughput, latency, failure rate, block detection.
"""
import requests
import time
import json
import sys

BASE = "http://127.0.0.1:5050"
PROVIDER = "google"

PROMPTS = [
    "What is Python?",
    "Explain Docker in one line",
    "What is AWS Lambda?",
    "How does Git work?",
    "What is REST API?",
    "Define machine learning",
    "What is Kubernetes?",
    "Explain TCP/IP briefly",
    "What is a hash table?",
    "Define recursion",
    "What is CI/CD?",
    "Explain OAuth2",
    "What is WebSocket?",
    "Define microservices",
    "What is SQL injection?",
    "Explain DNS briefly",
    "What is GraphQL?",
    "Define API gateway",
    "What is Redis?",
    "Explain load balancing",
    "What is React?",
    "Define serverless",
    "What is MongoDB?",
    "Explain CORS",
    "What is TypeScript?",
    "Define blockchain",
    "What is gRPC?",
    "Explain JWT tokens",
    "What is Nginx?",
    "Define DevOps",
]


def send_query(prompt, followup=False):
    """Send a single query and return timing + result info."""
    t0 = time.perf_counter()
    try:
        r = requests.post(f"{BASE}/api/send", json={
            "prompt": prompt,
            "provider": PROVIDER,
            "followup": followup,
        }, timeout=60)
        elapsed = round((time.perf_counter() - t0) * 1000)
        data = r.json()
        return {
            "success": data.get("success", False),
            "prompt": prompt,
            "response_len": len(data.get("response", "")),
            "total_ms": elapsed,
            "scrape_ms": data.get("timing", {}).get("total_ms", 0),
            "overhead_ms": data.get("timing", {}).get("overhead_ms", 0),
            "error": data.get("error") or (None if data.get("success") else data.get("response", "")[:100]),
            "blocked": "blocked" in str(data.get("response", "")).lower() or "unusual traffic" in str(data.get("response", "")).lower(),
        }
    except Exception as e:
        elapsed = round((time.perf_counter() - t0) * 1000)
        return {
            "success": False,
            "prompt": prompt,
            "response_len": 0,
            "total_ms": elapsed,
            "scrape_ms": 0,
            "overhead_ms": 0,
            "error": str(e)[:100],
            "blocked": False,
        }


def run_burst_test(count=15, delay=0):
    """Rapid-fire queries with optional delay between each."""
    print(f"\n{'='*60}")
    print(f" BURST TEST: {count} queries, {delay}s delay between each")
    print(f"{'='*60}\n")

    results = []
    start = time.perf_counter()

    for i in range(count):
        prompt = PROMPTS[i % len(PROMPTS)]
        print(f"  [{i+1:2d}/{count}] \"{prompt[:40]}\"...", end=" ", flush=True)
        result = send_query(prompt)
        results.append(result)

        status = "OK" if result["success"] else "FAIL"
        blocked = " [BLOCKED!]" if result["blocked"] else ""
        print(f"{status} {result['total_ms']}ms ({result['response_len']} chars){blocked}")

        if result["blocked"]:
            print(f"\n  *** BLOCK DETECTED at query #{i+1} ***\n")
            break

        if delay > 0 and i < count - 1:
            time.sleep(delay)

    total_time = round((time.perf_counter() - start) * 1000)
    return results, total_time


def print_stats(results, total_time_ms, label=""):
    """Print summary statistics."""
    ok = [r for r in results if r["success"]]
    fail = [r for r in results if not r["success"]]
    blocked = [r for r in results if r["blocked"]]

    if ok:
        latencies = [r["total_ms"] for r in ok]
        avg_lat = round(sum(latencies) / len(latencies))
        min_lat = min(latencies)
        max_lat = max(latencies)
        avg_chars = round(sum(r["response_len"] for r in ok) / len(ok))
    else:
        avg_lat = min_lat = max_lat = avg_chars = 0

    total_sec = total_time_ms / 1000
    qps = len(ok) / total_sec if total_sec > 0 else 0

    print(f"\n{'─'*60}")
    if label:
        print(f"  {label}")
        print(f"{'─'*60}")
    print(f"  Total queries:     {len(results)}")
    print(f"  Successful:        {len(ok)}")
    print(f"  Failed:            {len(fail)}")
    print(f"  Blocked:           {len(blocked)}")
    print(f"  Total time:        {total_time_ms}ms ({total_sec:.1f}s)")
    print(f"  Queries/sec:       {qps:.2f}")
    print(f"  Avg latency:       {avg_lat}ms")
    print(f"  Min latency:       {min_lat}ms")
    print(f"  Max latency:       {max_lat}ms")
    print(f"  Avg response:      {avg_chars} chars")

    if fail:
        print(f"\n  Errors:")
        for r in fail:
            print(f"    - \"{r['prompt'][:30]}\": {r['error']}")

    return {
        "total": len(results),
        "success": len(ok),
        "failed": len(fail),
        "blocked": len(blocked),
        "total_ms": total_time_ms,
        "qps": round(qps, 2),
        "avg_ms": avg_lat,
        "min_ms": min_lat,
        "max_ms": max_lat,
        "avg_chars": avg_chars,
    }


def main():
    print("=" * 60)
    print("  AI COMMAND CENTER — GOOGLE AI MODE BENCHMARK")
    print("=" * 60)

    # Check server
    try:
        r = requests.get(f"{BASE}/api/warmup", timeout=5)
        data = r.json()
        if data.get("state") != "ready":
            print("Server not ready. Start with: python main.py --web")
            return
        print(f"  Server: READY (warmup: {data['timings']['total_ms']}ms)")
    except:
        print("  Server not reachable at", BASE)
        return

    all_stats = {}

    # ─── Test 1: Burst (no delay) — find raw throughput ───
    results1, time1 = run_burst_test(count=15, delay=0)
    all_stats["burst_0s"] = print_stats(results1, time1, "TEST 1: BURST (0s delay)")

    if any(r["blocked"] for r in results1):
        print("\n  Blocked during burst! Adding cooldown...")
        time.sleep(30)

    # ─── Test 2: Moderate pace (2s delay) ───
    results2, time2 = run_burst_test(count=10, delay=2)
    all_stats["paced_2s"] = print_stats(results2, time2, "TEST 2: PACED (2s delay)")

    if any(r["blocked"] for r in results2):
        print("\n  Blocked! Adding cooldown...")
        time.sleep(30)

    # ─── Test 3: Safe pace (4s delay) ───
    results3, time3 = run_burst_test(count=10, delay=4)
    all_stats["safe_4s"] = print_stats(results3, time3, "TEST 3: SAFE (4s delay)")

    # ─── Final projections ───
    print(f"\n{'='*60}")
    print("  THROUGHPUT PROJECTIONS")
    print(f"{'='*60}\n")

    for label, stats in all_stats.items():
        if stats["success"] > 0 and stats["blocked"] == 0:
            qps = stats["qps"]
            per_min = round(qps * 60)
            per_hr = round(qps * 3600)
            per_day = round(qps * 86400)
            print(f"  {label}:")
            print(f"    Raw QPS:    {qps}")
            print(f"    Per minute: {per_min}")
            print(f"    Per hour:   {per_hr}")
            print(f"    Per 24 hr:  {per_day}")
            print()

    # ─── Safe sustained estimates with cooldowns ───
    print(f"{'─'*60}")
    print("  SAFE SUSTAINED ESTIMATES (with cooldowns)")
    print(f"{'─'*60}")

    # Conservative: assume avg ~2.5s per query, 10% cooldown overhead
    ok_all = [r for r in (results1 + results2 + results3) if r["success"]]
    if ok_all:
        avg_all = sum(r["total_ms"] for r in ok_all) / len(ok_all) / 1000
        blocked_any = any(r["blocked"] for r in results1 + results2 + results3)

        # With 2s buffer between queries
        safe_cycle = avg_all + 2
        safe_per_min = round(60 / safe_cycle)
        safe_per_hr = round(3600 / safe_cycle)
        safe_per_day_no_cool = round(86400 / safe_cycle)

        # With 5-min cooldown every 50 queries
        queries_per_block = 50
        block_time = queries_per_block * safe_cycle
        cycle_time = block_time + 300  # 5 min cooldown
        rate = queries_per_block / cycle_time
        safe_per_day_cool = round(rate * 86400)

        print(f"\n  Average latency:          {round(avg_all * 1000)}ms ({round(avg_all, 2)}s)")
        print(f"  Safe cycle (query + 2s):  {round(safe_cycle, 2)}s")
        print(f"  Blocked during burst:     {'YES' if blocked_any else 'NO'}")
        print()
        print(f"  ┌──────────────┬─────────────────────────────────────┐")
        print(f"  │ Time Period  │ Queries (estimate)                  │")
        print(f"  ├──────────────┼─────────────────────────────────────┤")
        print(f"  │ 1 minute     │ {safe_per_min:<36}│")
        print(f"  │ 1 hour       │ {safe_per_hr:<36}│")
        print(f"  │ 24 hours     │ {safe_per_day_no_cool:<36}│")
        print(f"  │ 24h + 5m     │ {safe_per_day_cool} (with 5-min break every 50q)  │")
        print(f"  │   cooldowns  │                                     │")
        print(f"  └──────────────┴─────────────────────────────────────┘")

    # Save raw data
    report = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "provider": PROVIDER,
        "tests": all_stats,
        "all_results": [
            {"test": "burst_0s", "results": results1},
            {"test": "paced_2s", "results": results2},
            {"test": "safe_4s", "results": results3},
        ]
    }
    with open("benchmark_report.json", "w") as f:
        json.dump(report, f, indent=2)
    print(f"\n  Raw data saved to: benchmark_report.json")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
