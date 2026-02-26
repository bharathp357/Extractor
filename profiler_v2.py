"""
PROFILER V2: Tests the OPTIMIZED scraper pipeline via ai_automator module.
Runs 3 queries and reports detailed timing from the result dict.
"""
import time
import sys
sys.path.insert(0, r"c:\Hold On Projects\P2")

from ai_automator import get_automator

QUERIES = [
    "What is Kubernetes",
    "Explain microservices architecture",
    "What is Redis cache",
]

def profile():
    print("=" * 70)
    print("  PROFILER V2 — Optimised Pipeline")
    print("=" * 70)

    # Browser launch (timed)
    t0 = time.perf_counter()
    automator = get_automator()
    launch_ms = round((time.perf_counter() - t0) * 1000)
    print(f"\n  Browser launch: {launch_ms}ms\n")

    for qi, query in enumerate(QUERIES, 1):
        print(f"── Query {qi}/{len(QUERIES)}: \"{query}\" ──")

        result = automator.send_and_get_response(query)
        t = result.get("timing", {})

        success = result["success"]
        resp_len = len(result["response"]) if success else 0
        total = t.get("total_ms", "?")

        print(f"  Success:         {success}")
        print(f"  Response length: {resp_len} chars")
        print()
        print(f"  {'Phase':<25} {'Time':>10}")
        print(f"  {'─'*25} {'─'*10}")
        print(f"  {'Navigation':<25} {t.get('navigation_ms','?'):>8}ms")
        print(f"  {'Container wait':<25} {t.get('container_wait_ms','?'):>8}ms")
        print(f"  {'Polling':<25} {t.get('polling_ms','?'):>8}ms")
        print(f"  {'Poll count':<25} {t.get('poll_count','?'):>8}")
        print(f"  {'Total scrape':<25} {t.get('scrape_ms','?'):>8}ms")
        print(f"  {'─'*25} {'─'*10}")
        print(f"  {'TOTAL':<25} {total:>8}ms")
        print()

    # Summary comparison with v1 baseline
    print("=" * 70)
    print("  V1 BASELINE (from profiler.py):")
    print("    Q1=9852ms  Q2=7304ms  Q3=8118ms  AVG=8425ms")
    print("=" * 70)
    print("  PROFILING V2 COMPLETE")
    print("=" * 70)


if __name__ == "__main__":
    profile()
