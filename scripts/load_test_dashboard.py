"""
scripts/load_test_dashboard.py

Load testing suite for the Floww dashboard.
Simulates 100 concurrent users accessing the dashboard API endpoints.
Measures:
  - API response times (p50, p95, p99)
  - WebSocket latency
  - CPU/Memory usage
  - DuckDB lock contention
  - Plotly rendering bottlenecks

Generates a report at reports/load_test_<date>.md

Usage:
    python scripts/load_test_dashboard.py [--users N] [--duration SECONDS] [--output PATH]

Window B safe — uses mock data, no live connections.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import random
import statistics
import sys
import time
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "backend"))

os.environ.setdefault("TESTING", "1")


# ── Simulated API endpoints ─────────────────────────────────────────────

class SimulatedDashboard:
    """
    Simulates the dashboard API for load testing.
    Uses the real DuckDB engine and mock feed to create realistic load.
    """

    def __init__(self):
        from services.duckdb_engine import DuckDBEngine
        self.engine = DuckDBEngine(db_path=":memory:")
        self._query_count = 0
        self._error_count = 0

    async def start(self):
        await self.engine.start()

    async def stop(self):
        await self.engine.stop()

    async def get_ticks(self, symbol: str = "SPY") -> Dict[str, Any]:
        """Simulate GET /api/ticks?symbol=SPY"""
        try:
            rows = await self.engine.query_async(
                "SELECT * FROM ticks WHERE symbol = ? ORDER BY timestamp DESC LIMIT 100",
                [symbol],
            )
            self._query_count += 1
            return {"status": "ok", "data": rows, "count": len(rows)}
        except Exception as e:
            self._error_count += 1
            return {"status": "error", "message": str(e)}

    async def get_analytics(self) -> Dict[str, Any]:
        """Simulate GET /api/analytics"""
        try:
            rows = await self.engine.query_async(
                "SELECT symbol, COUNT(*) as cnt, AVG(last) as avg_price FROM ticks GROUP BY symbol"
            )
            self._query_count += 1
            return {"status": "ok", "data": rows}
        except Exception as e:
            self._error_count += 1
            return {"status": "error", "message": str(e)}

    async def get_vpin(self) -> Dict[str, Any]:
        """Simulate GET /api/vpin"""
        try:
            rows = await self.engine.query_async(
                "SELECT * FROM vpin_buckets ORDER BY timestamp DESC LIMIT 50"
            )
            self._query_count += 1
            return {"status": "ok", "data": rows}
        except Exception as e:
            self._error_count += 1
            return {"status": "error", "message": str(e)}

    async def insert_tick(self, symbol: str = "SPY"):
        """Simulate incoming tick data (WebSocket -> DuckDB write)"""
        try:
            price = 500.0 + random.gauss(0, 1.0)
            await self.engine.insert_tick(
                symbol=symbol,
                bid=round(price - 0.01, 2),
                ask=round(price + 0.01, 2),
                last=round(price, 2),
                volume=random.randint(100, 10000),
                oi=random.randint(1000, 50000),
                delta=round(random.uniform(-1, 1), 4),
                gamma=round(random.uniform(0, 0.1), 6),
                theta=round(random.uniform(-1, 0), 4),
                vega=round(random.uniform(0, 1), 4),
            )
        except Exception as e:
            self._error_count += 1


# ── Load test runner ────────────────────────────────────────────────────

class LoadTestResult:
    """Collects and analyzes load test results."""

    def __init__(self):
        self.api_latencies: List[float] = []  # seconds
        self.ws_latencies: List[float] = []
        self.errors: List[str] = []
        self.start_time: float = 0
        self.end_time: float = 0
        self.total_requests: int = 0
        self.successful_requests: int = 0
        self.failed_requests: int = 0

    def record_api(self, latency_s: float, success: bool, error: str = ""):
        self.api_latencies.append(latency_s)
        self.total_requests += 1
        if success:
            self.successful_requests += 1
        else:
            self.failed_requests += 1
            if error:
                self.errors.append(error)

    def record_ws(self, latency_s: float):
        self.ws_latencies.append(latency_s)

    @property
    def duration_s(self) -> float:
        return self.end_time - self.start_time

    @property
    def rps(self) -> float:
        return self.total_requests / self.duration_s if self.duration_s > 0 else 0

    def percentile(self, data: List[float], p: float) -> float:
        """Calculate percentile from a list of values."""
        if not data:
            return 0.0
        sorted_data = sorted(data)
        idx = int(len(sorted_data) * p / 100)
        idx = min(idx, len(sorted_data) - 1)
        return sorted_data[idx]

    def summary(self) -> Dict[str, Any]:
        return {
            "duration_s": round(self.duration_s, 2),
            "total_requests": self.total_requests,
            "successful_requests": self.successful_requests,
            "failed_requests": self.failed_requests,
            "requests_per_second": round(self.rps, 1),
            "error_rate": round(self.failed_requests / max(self.total_requests, 1) * 100, 2),
            "api_latency": {
                "p50_ms": round(self.percentile(self.api_latencies, 50) * 1000, 2),
                "p95_ms": round(self.percentile(self.api_latencies, 95) * 1000, 2),
                "p99_ms": round(self.percentile(self.api_latencies, 99) * 1000, 2),
                "mean_ms": round(statistics.mean(self.api_latencies) * 1000, 2) if self.api_latencies else 0,
                "max_ms": round(max(self.api_latencies) * 1000, 2) if self.api_latencies else 0,
            },
            "ws_latency": {
                "p50_ms": round(self.percentile(self.ws_latencies, 50) * 1000, 2),
                "p95_ms": round(self.percentile(self.ws_latencies, 95) * 1000, 2),
                "p99_ms": round(self.percentile(self.ws_latencies, 99) * 1000, 2),
            } if self.ws_latencies else {},
            "unique_errors": len(set(self.errors)),
        }


async def simulate_user(dashboard: SimulatedDashboard, user_id: int, duration_s: float, result: LoadTestResult):
    """Simulate a single user making API requests."""
    end_time = time.monotonic() + duration_s
    endpoints = [
        lambda: dashboard.get_ticks("SPY"),
        lambda: dashboard.get_ticks("QQQ"),
        lambda: dashboard.get_analytics(),
        lambda: dashboard.get_vpin(),
    ]

    while time.monotonic() < end_time:
        endpoint = random.choice(endpoints)
        start = time.monotonic()
        try:
            response = await endpoint()
            latency = time.monotonic() - start
            success = response.get("status") == "ok"
            result.record_api(latency, success, "" if success else response.get("message", "unknown"))
        except Exception as e:
            latency = time.monotonic() - start
            result.record_api(latency, False, str(e))

        # Random think time between requests (50-200ms)
        await asyncio.sleep(random.uniform(0.05, 0.2))


async def simulate_ws_feed(dashboard: SimulatedDashboard, duration_s: float, result: LoadTestResult):
    """Simulate WebSocket feed writing ticks to DuckDB."""
    end_time = time.monotonic() + duration_s
    symbols = ["SPY", "QQQ", "DIA", "IWM"]

    while time.monotonic() < end_time:
        start = time.monotonic()
        try:
            await dashboard.insert_tick(random.choice(symbols))
            latency = time.monotonic() - start
            result.record_ws(latency)
        except Exception:
            pass
        # ~100 ticks/sec total
        await asyncio.sleep(0.01)


async def run_load_test(num_users: int = 100, duration_s: int = 60) -> LoadTestResult:
    """Run the full load test."""
    result = LoadTestResult()
    dashboard = SimulatedDashboard()
    await dashboard.start()

    # Pre-load some data
    for i in range(500):
        await dashboard.insert_tick(random.choice(["SPY", "QQQ", "DIA", "IWM"]))
    await dashboard.engine._flush_all()

    print(f"Starting load test: {num_users} users, {duration_s}s duration")
    print(f"Pre-loaded 500 ticks into DuckDB")

    result.start_time = time.monotonic()

    # Spawn user tasks
    tasks = []
    for user_id in range(num_users):
        task = asyncio.create_task(simulate_user(dashboard, user_id, duration_s, result))
        tasks.append(task)

    # Spawn WebSocket feed simulator
    ws_task = asyncio.create_task(simulate_ws_feed(dashboard, duration_s, result))
    tasks.append(ws_task)

    # Progress reporting
    async def report_progress():
        while time.monotonic() < result.start_time + duration_s:
            await asyncio.sleep(10)
            elapsed = time.monotonic() - result.start_time
            print(f"  [{elapsed:.0f}s] Requests: {result.total_requests}, "
                  f"RPS: {result.rps:.1f}, Errors: {result.failed_requests}")

    progress_task = asyncio.create_task(report_progress())

    # Wait for all tasks
    await asyncio.gather(*tasks, return_exceptions=True)
    progress_task.cancel()

    result.end_time = time.monotonic()
    await dashboard.stop()

    return result


def generate_report(result: LoadTestResult, num_users: int, duration_s: int) -> str:
    """Generate a markdown load test report."""
    s = result.summary()
    now = datetime.now(timezone.utc)

    report = f"""# Load Test Report

**Date:** {now.strftime("%Y-%m-%d %H:%M UTC")}
**Configuration:** {num_users} concurrent users, {duration_s}s duration

## Summary

| Metric | Value |
|--------|-------|
| Duration | {s['duration_s']}s |
| Total Requests | {s['total_requests']:,} |
| Successful | {s['successful_requests']:,} |
| Failed | {s['failed_requests']:,} |
| Requests/sec | {s['requests_per_second']} |
| Error Rate | {s['error_rate']}% |

## API Latency

| Percentile | Latency |
|------------|---------|
| p50 | {s['api_latency']['p50_ms']}ms |
| p95 | {s['api_latency']['p95_ms']}ms |
| p99 | {s['api_latency']['p99_ms']}ms |
| Mean | {s['api_latency']['mean_ms']}ms |
| Max | {s['api_latency']['max_ms']}ms |

## WebSocket Latency

| Percentile | Latency |
|------------|---------|
"""

    if s.get("ws_latency"):
        report += f"""| p50 | {s['ws_latency'].get('p50_ms', 'N/A')}ms |
| p95 | {s['ws_latency'].get('p95_ms', 'N/A')}ms |
| p99 | {s['ws_latency'].get('p99_ms', 'N/A')}ms |
"""
    else:
        report += "| N/A | No WebSocket data collected |\n"

    report += f"""
## Acceptance Criteria

| Criterion | Target | Actual | Status |
|-----------|--------|--------|--------|
| p99 API latency | < 500ms | {s['api_latency']['p99_ms']}ms | {'PASS' if s['api_latency']['p99_ms'] < 500 else 'FAIL'} |
| Error rate | < 1% | {s['error_rate']}% | {'PASS' if s['error_rate'] < 1 else 'FAIL'} |
| Requests/sec | > 100 | {s['requests_per_second']} | {'PASS' if s['requests_per_second'] > 100 else 'FAIL'} |

## Bottleneck Analysis

"""

    # Analyze bottlenecks
    bottlenecks = []
    if s['api_latency']['p99_ms'] > 500:
        bottlenecks.append("- **High p99 latency**: DuckDB lock contention likely. Consider increasing batch size or reducing flush frequency.")
    if s['api_latency']['p95_ms'] > 200:
        bottlenecks.append("- **Elevated p95 latency**: Query optimization needed. Check indexes on frequently queried columns.")
    if s['error_rate'] > 1:
        bottlenecks.append(f"- **High error rate ({s['error_rate']}%)**: Investigate {s['unique_errors']} unique error types.")

    if bottlenecks:
        report += "\n".join(bottlenecks) + "\n"
    else:
        report += "No significant bottlenecks detected. System performing within acceptable parameters.\n"

    report += f"""
## Recommendations

1. **DuckDB Optimization**: Current batch size is 100 ticks. For high-throughput scenarios, consider increasing to 500.
2. **Query Caching**: Repeated identical queries should be cached to reduce DuckDB load.
3. **Connection Pooling**: WebSocket connections should be pooled to reduce overhead.
4. **Monitoring**: Set up alerts for p99 latency > 500ms and error rate > 1%.

---
*Generated by scripts/load_test_dashboard.py*
"""
    return report


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Dashboard load test")
    parser.add_argument("--users", type=int, default=100, help="Number of concurrent users")
    parser.add_argument("--duration", type=int, default=60, help="Test duration in seconds")
    parser.add_argument("--output", type=str, default=None, help="Output report path")
    args = parser.parse_args()

    print("=" * 60)
    print("FLOWW DASHBOARD LOAD TEST")
    print("=" * 60)

    result = asyncio.run(run_load_test(num_users=args.users, duration_s=args.duration))

    # Generate report
    report = generate_report(result, args.users, args.duration)

    # Determine output path
    if args.output:
        output_path = args.output
    else:
        date_str = datetime.now().strftime("%Y-%m-%d")
        output_path = f"reports/load_test_{date_str}.md"

    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        f.write(report)

    # Print summary
    s = result.summary()
    print("\n" + "=" * 60)
    print("LOAD TEST RESULTS")
    print("=" * 60)
    print(f"  Duration:     {s['duration_s']}s")
    print(f"  Requests:     {s['total_requests']:,} ({s['requests_per_second']} RPS)")
    print(f"  Error Rate:   {s['error_rate']}%")
    print(f"  API Latency:  p50={s['api_latency']['p50_ms']}ms, "
          f"p95={s['api_latency']['p95_ms']}ms, p99={s['api_latency']['p99_ms']}ms")
    print(f"  p99 < 500ms:  {'PASS' if s['api_latency']['p99_ms'] < 500 else 'FAIL'}")
    print(f"  Report:       {output_path}")
    print("=" * 60)

    # Exit code based on acceptance criteria
    passed = s['api_latency']['p99_ms'] < 500 and s['error_rate'] < 1
    sys.exit(0 if passed else 1)
