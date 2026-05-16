"""
Load testing script for Confluence Decoder API.
Run with: cd backend && . .venv/bin/activate && python scripts/load_test.py
"""
import asyncio
import time
import statistics
import httpx

BASE = "http://localhost:8000/api"
CONCURRENT_USERS = 10
REQUESTS_PER_USER = 20

async def user_session(client: httpx.AsyncClient, user_id: int):
    """Simulate a user making a series of requests."""
    results = []
    endpoints = [
        ("/", "root"),
        ("/health", "health"),
        ("/tickers", "tickers"),
        ("/heatmap/SPY?expiries=2", "heatmap"),
        ("/chain/SPY?min_oi=500", "chain"),
        ("/spot/SPY", "spot"),
        ("/gex-timeframes/SPY", "timeframes"),
        ("/uoa/SPY", "uoa"),
    ]

    for path, name in endpoints:
        try:
            start = time.time()
            r = await client.get(f"{BASE}{path}", timeout=30)
            elapsed = time.time() - start
            results.append({
                "user": user_id,
                "endpoint": name,
                "status": r.status_code,
                "time": elapsed,
            })
        except Exception as e:
            results.append({
                "user": user_id,
                "endpoint": name,
                "status": 0,
                "time": 0,
                "error": str(e),
            })
        await asyncio.sleep(0.1)  # Small delay between requests

    return results


async def run_load_test():
    print(f"Load test: {CONCURRENT_USERS} concurrent users, {REQUESTS_PER_USER} requests each")
    print(f"Target: {BASE}")
    print("-" * 60)

    all_results = []
    start_time = time.time()

    async with httpx.AsyncClient(limits=httpx.Limits(max_connections=50)) as client:
        tasks = [user_session(client, i) for i in range(CONCURRENT_USERS)]
        results = await asyncio.gather(*tasks)
        for r in results:
            all_results.extend(r)

    total_time = time.time() - start_time

    # Analyze results
    total_requests = len(all_results)
    successful = [r for r in all_results if r["status"] == 200]
    failed = [r for r in all_results if r["status"] != 200]
    times = [r["time"] for r in successful if r["time"] > 0]

    print(f"\nResults:")
    print(f"  Total requests: {total_requests}")
    print(f"  Successful: {len(successful)} ({len(successful)/total_requests*100:.1f}%)")
    print(f"  Failed: {len(failed)} ({len(failed)/total_requests*100:.1f}%)")
    print(f"  Total time: {total_time:.2f}s")
    print(f"  Requests/sec: {total_requests/total_time:.1f}")

    if times:
        print(f"\nLatency:")
        print(f"  Min: {min(times)*1000:.0f}ms")
        print(f"  Max: {max(times)*1000:.0f}ms")
        print(f"  Mean: {statistics.mean(times)*1000:.0f}ms")
        print(f"  Median: {statistics.median(times)*1000:.0f}ms")
        if len(times) > 1:
            print(f"  P95: {sorted(times)[int(len(times)*0.95)]*1000:.0f}ms")

    if failed:
        print(f"\nFailed requests:")
        for r in failed[:10]:
            print(f"  {r['endpoint']}: status={r['status']}")

    print("\nDone.")


if __name__ == "__main__":
    asyncio.run(run_load_test())
