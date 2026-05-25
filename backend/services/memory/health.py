#!/usr/bin/env python3
"""
backend/services/memory/health.py — Memory health monitor.

Exposes GET /api/admin/memory/health with:
  - entry_count, query_latency_p99, embedding_cache_hit_rate
  - federation_lag, last_consolidation, pruning_stats
  - Prometheus metrics for Agent 10
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

# Prometheus metrics (in-process counters)
_metrics = {
    "memory_entry_count": 0,
    "memory_query_count": 0,
    "memory_query_latency_ms": [],
    "memory_federation_lag_s": 0.0,
    "memory_federation_events_synced": 0,
    "memory_consolidation_last_at": None,
    "memory_consolidation_merged_24h": 0,
    "memory_pruned_24h": 0,
    "memory_cache_hits": 0,
    "memory_cache_misses": 0,
}


def record_query(latency_ms: float):
    """Record a memory query for latency tracking."""
    _metrics["memory_query_count"] += 1
    _metrics["memory_query_latency_ms"].append(latency_ms)
    # Keep only last 1000 measurements
    if len(_metrics["memory_query_latency_ms"]) > 1000:
        _metrics["memory_query_latency_ms"] = _metrics["memory_query_latency_ms"][-1000:]


def record_cache_hit():
    _metrics["memory_cache_hits"] += 1


def record_cache_miss():
    _metrics["memory_cache_misses"] += 1


def record_federation_sync(lag_seconds: float, events_synced: int):
    _metrics["memory_federation_lag_s"] = lag_seconds
    _metrics["memory_federation_events_synced"] += events_synced


def record_consolidation(merged: int):
    _metrics["memory_consolidation_last_at"] = datetime.now(timezone.utc).isoformat()
    _metrics["memory_consolidation_merged_24h"] += merged


def record_pruning(pruned: int):
    _metrics["memory_pruned_24h"] += pruned


def get_health_status(mem0_client=None, user_id: str = "user_c778280e23af") -> dict:
    """Get current memory health status."""
    now = datetime.now(timezone.utc)

    # Calculate query latency percentiles
    latencies = _metrics["memory_query_latency_ms"]
    if latencies:
        sorted_lat = sorted(latencies)
        p50 = sorted_lat[len(sorted_lat) // 2]
        p95 = sorted_lat[int(len(sorted_lat) * 0.95)]
        p99 = sorted_lat[int(len(sorted_lat) * 0.99)] if len(sorted_lat) >= 100 else sorted_lat[-1]
    else:
        p50 = p95 = p99 = 0.0

    # Cache hit rate
    total_cache = _metrics["memory_cache_hits"] + _metrics["memory_cache_misses"]
    cache_hit_rate = _metrics["memory_cache_hits"] / total_cache if total_cache > 0 else 0.0

    # Entry count from mem0
    entry_count = 0
    if mem0_client:
        try:
            result = mem0_client.get_all(filters={"user_id": user_id}, limit=1)
            if isinstance(result, dict):
                entry_count = result.get("total", result.get("count", 0))
            elif isinstance(result, list):
                entry_count = len(result)
        except Exception:
            entry_count = _metrics["memory_entry_count"]

    return {
        "entry_count": entry_count,
        "query_count_total": _metrics["memory_query_count"],
        "query_latency_p50_ms": round(p50, 2),
        "query_latency_p95_ms": round(p95, 2),
        "query_latency_p99_ms": round(p99, 2),
        "embedding_cache_hit_rate": round(cache_hit_rate, 4),
        "federation_lag_seconds": round(_metrics["memory_federation_lag_s"], 2),
        "federation_events_synced_total": _metrics["memory_federation_events_synced"],
        "last_consolidation_at": _metrics["memory_consolidation_last_at"],
        "consolidation_merged_24h": _metrics["memory_consolidation_merged_24h"],
        "pruning_stats": {
            "pruned_24h": _metrics["memory_pruned_24h"],
        },
        "timestamp": now.isoformat(),
    }


def get_prometheus_metrics() -> str:
    """Export metrics in Prometheus text format."""
    lines = [
        "# HELP floww_memory_entry_count Total memory entries",
        "# TYPE floww_memory_entry_count gauge",
        f"floww_memory_entry_count {_metrics['memory_entry_count']}",
        "",
        "# HELP floww_memory_query_latency_ms Query latency",
        "# TYPE floww_memory_query_latency_ms summary",
        f"floww_memory_query_latency_ms{{quantile=\"0.5\"}} {_metrics['memory_query_latency_ms'][len(_metrics['memory_query_latency_ms'])//2] if _metrics['memory_query_latency_ms'] else 0}",
        f"floww_memory_query_latency_ms{{quantile=\"0.99\"}} {_metrics['memory_query_latency_ms'][int(len(_metrics['memory_query_latency_ms'])*0.99)] if _metrics['memory_query_latency_ms'] else 0}",
        "",
        "# HELP floww_memory_federation_lag_s Federation replication lag",
        "# TYPE floww_memory_federation_lag_s gauge",
        f"floww_memory_federation_lag_s {_metrics['memory_federation_lag_s']}",
        "",
        "# HELP floww_memory_cache_hit_rate Embedding cache hit rate",
        "# TYPE floww_memory_cache_hit_rate gauge",
        f"floww_memory_cache_hit_rate {_metrics['memory_cache_hits'] / max(1, _metrics['memory_cache_hits'] + _metrics['memory_cache_misses'])}",
    ]
    return "\n".join(lines)
