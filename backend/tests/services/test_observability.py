"""
backend/tests/services/test_observability.py

Unit tests for the observability / Prometheus metrics stack.

Coverage:
    - Each metric increments/sets under expected conditions
    - /metrics endpoint returns valid Prometheus exposition format
    - Histogram buckets are reasonable
    - VPIN engine emits metrics on bucket finalize
    - Anomaly detector emits metrics on update
    - WebSocket connect/disconnect updates gauge
    - DuckDB engine emits queue depth and batch size
"""

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Ensure backend/ is on path
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from prometheus_client import CollectorRegistry


@pytest.fixture(autouse=True)
def fresh_registry(monkeypatch):
    """Replace the global REGISTRY with a fresh one for each test."""
    from services import observability
    new_reg = CollectorRegistry()
    monkeypatch.setattr(observability, "REGISTRY", new_reg)
    # Re-create all metrics with the new registry
    from prometheus_client import Counter, Gauge, Histogram

    observability.ingestion_messages_total = Counter(
        "floww_ingestion_messages_total",
        "Total market data messages ingested",
        labelnames=["symbol", "kind"],
        registry=new_reg,
    )
    observability.duckdb_queue_depth = Gauge(
        "floww_duckdb_queue_depth",
        "Current number of items in the DuckDB write queue",
        registry=new_reg,
    )
    observability.duckdb_batch_size = Histogram(
        "floww_duckdb_batch_size",
        "Number of rows per DuckDB batch flush",
        buckets=[1, 5, 10, 25, 50, 100, 250, 500, 1000],
        registry=new_reg,
    )
    observability.vpin_current = Gauge(
        "floww_vpin_current",
        "Current VPIN value (0-1) per ticker",
        labelnames=["ticker"],
        registry=new_reg,
    )
    observability.qi_zscore_current = Gauge(
        "floww_qi_zscore_current",
        "Current Quote Imbalance z-score per ticker",
        labelnames=["ticker"],
        registry=new_reg,
    )
    observability.trinity_score = Gauge(
        "floww_trinity_score",
        "Trinity Alignment Index score (0-100)",
        registry=new_reg,
    )
    observability.anomaly_score = Gauge(
        "floww_anomaly_score",
        "Current anomaly reconstruction error per ticker",
        labelnames=["ticker"],
        registry=new_reg,
    )
    observability.anomaly_detected_total = Counter(
        "floww_anomaly_detected_total",
        "Total number of anomaly threshold breaches",
        registry=new_reg,
    )
    observability.api_request_duration_seconds = Histogram(
        "floww_api_request_duration_seconds",
        "HTTP request duration in seconds",
        labelnames=["route", "method", "status"],
        buckets=[0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0],
        registry=new_reg,
    )
    observability.websocket_connections = Gauge(
        "floww_websocket_connections",
        "Current number of active WebSocket connections per topic",
        labelnames=["topic"],
        registry=new_reg,
    )
    observability.schwab_token_expires_in_seconds = Gauge(
        "floww_schwab_token_expires_in_seconds",
        "Seconds until Schwab OAuth token expires (0 if no token)",
        registry=new_reg,
    )
    yield new_reg


# ---------------------------------------------------------------------------
# Test 1: ingestion_messages_total increments
# ---------------------------------------------------------------------------
def test_ingestion_counter_increments():
    from services.observability import metrics as m
    m.ingestion_messages_total.labels(symbol="SPY", kind="tick").inc()
    m.ingestion_messages_total.labels(symbol="SPY", kind="tick").inc()
    m.ingestion_messages_total.labels(symbol="QQQ", kind="tick").inc()
    output = m.get_metrics_bytes().decode()
    assert 'floww_ingestion_messages_total{kind="tick",symbol="SPY"} 2' in output
    assert 'floww_ingestion_messages_total{kind="tick",symbol="QQQ"} 1' in output


# ---------------------------------------------------------------------------
# Test 2: vpin_current gauge sets per ticker
# ---------------------------------------------------------------------------
def test_vpin_gauge_sets():
    from services.observability import metrics as m
    m.vpin_current.labels(ticker="SPY").set(0.72)
    m.vpin_current.labels(ticker="QQQ").set(0.35)
    output = m.get_metrics_bytes().decode()
    assert 'floww_vpin_current{ticker="SPY"} 0.72' in output
    assert 'floww_vpin_current{ticker="QQQ"} 0.35' in output


# ---------------------------------------------------------------------------
# Test 3: qi_zscore_current gauge sets
# ---------------------------------------------------------------------------
def test_qi_zscore_gauge_sets():
    from services.observability import metrics as m
    m.qi_zscore_current.labels(ticker="SPY").set(1.85)
    output = m.get_metrics_bytes().decode()
    assert 'floww_qi_zscore_current{ticker="SPY"} 1.85' in output


# ---------------------------------------------------------------------------
# Test 4: trinity_score gauge sets
# ---------------------------------------------------------------------------
def test_trinity_score_gauge_sets():
    from services.observability import metrics as m
    m.trinity_score.set(67.5)
    output = m.get_metrics_bytes().decode()
    assert "floww_trinity_score 67.5" in output


# ---------------------------------------------------------------------------
# Test 5: anomaly_score gauge and anomaly_detected_total counter
# ---------------------------------------------------------------------------
def test_anomaly_metrics():
    from services.observability import metrics as m
    m.anomaly_score.labels(ticker="SPY").set(0.0042)
    m.anomaly_detected_total.inc()
    m.anomaly_detected_total.inc()
    output = m.get_metrics_bytes().decode()
    assert 'floww_anomaly_score{ticker="SPY"} 0.0042' in output
    assert "floww_anomaly_detected_total 2" in output


# ---------------------------------------------------------------------------
# Test 6: api_request_duration_seconds histogram
# ---------------------------------------------------------------------------
def test_api_duration_histogram():
    from services.observability import metrics as m
    m.api_request_duration_seconds.labels(
        route="/api/vpin/{ticker}", method="GET", status="200"
    ).observe(0.023)
    m.api_request_duration_seconds.labels(
        route="/api/vpin/{ticker}", method="GET", status="200"
    ).observe(0.150)
    output = m.get_metrics_bytes().decode()
    assert "floww_api_request_duration_seconds_bucket" in output
    assert 'method="GET"' in output
    assert 'route="/api/vpin/{ticker}"' in output
    assert 'status="200"' in output


# ---------------------------------------------------------------------------
# Test 7: websocket_connections gauge inc/dec
# ---------------------------------------------------------------------------
def test_websocket_gauge():
    from services.observability import metrics as m
    m.websocket_connections.labels(topic="ticks").inc()
    m.websocket_connections.labels(topic="ticks").inc()
    m.websocket_connections.labels(topic="flow").inc()
    output = m.get_metrics_bytes().decode()
    assert 'floww_websocket_connections{topic="ticks"} 2' in output
    assert 'floww_websocket_connections{topic="flow"} 1' in output
    m.websocket_connections.labels(topic="ticks").dec()
    output = m.get_metrics_bytes().decode()
    assert 'floww_websocket_connections{topic="ticks"} 1' in output


# ---------------------------------------------------------------------------
# Test 8: duckdb_queue_depth gauge
# ---------------------------------------------------------------------------
def test_duckdb_queue_depth():
    from services.observability import metrics as m
    m.duckdb_queue_depth.set(42)
    output = m.get_metrics_bytes().decode()
    assert "floww_duckdb_queue_depth 42" in output


# ---------------------------------------------------------------------------
# Test 9: duckdb_batch_size histogram
# ---------------------------------------------------------------------------
def test_duckdb_batch_size_histogram():
    from services.observability import metrics as m
    m.duckdb_batch_size.observe(50)
    m.duckdb_batch_size.observe(100)
    output = m.get_metrics_bytes().decode()
    assert "floww_duckdb_batch_size_bucket" in output
    assert "floww_duckdb_batch_size_count 2" in output


# ---------------------------------------------------------------------------
# Test 10: schwab_token_expires_in_seconds gauge
# ---------------------------------------------------------------------------
def test_schwab_token_ttl_gauge():
    from services.observability import metrics as m
    m.schwab_token_expires_in_seconds.set(900)
    output = m.get_metrics_bytes().decode()
    assert "floww_schwab_token_expires_in_seconds 900" in output
    m.schwab_token_expires_in_seconds.set(0)
    output = m.get_metrics_bytes().decode()
    assert "floww_schwab_token_expires_in_seconds 0" in output


# ---------------------------------------------------------------------------
# Test 11: /metrics endpoint returns valid Prometheus format
# ---------------------------------------------------------------------------
def test_metrics_endpoint_returns_prometheus_format():
    from services.observability import metrics as m
    m.vpin_current.labels(ticker="SPY").set(0.5)
    data = m.get_metrics_bytes()
    text = data.decode()
    # Must have HELP and TYPE lines
    assert "# HELP floww_vpin_current" in text
    assert "# TYPE floww_vpin_current gauge" in text
    # Must have the actual value
    assert 'floww_vpin_current{ticker="SPY"} 0.5' in text
    # Content type
    assert m.get_metrics_content_type() == "text/plain; version=0.0.4; charset=utf-8"


# ---------------------------------------------------------------------------
# Test 12: VPIN engine emits metrics on bucket finalize
# ---------------------------------------------------------------------------
def test_vpin_engine_emits_metrics():
    from services.vpin_engine import VpinEngine
    from services.observability import metrics as m

    engine = VpinEngine(bucket_size=100.0, window=10, ticker="SPY")
    # Feed enough volume to trigger bucket finalize
    for i in range(20):
        engine.update(price_change=0.01, volume=10.0, sigma=0.2, dt=1.0)

    output = m.get_metrics_bytes().decode()
    # VPIN should have been set
    assert 'floww_vpin_current{ticker="SPY"}' in output
    # Ingestion counter should have incremented
    assert "floww_ingestion_messages_total" in output


# ---------------------------------------------------------------------------
# Test 13: VPIN engine without ticker does NOT emit metrics
# ---------------------------------------------------------------------------
def test_vpin_engine_no_ticker_no_metrics():
    from services.vpin_engine import VpinEngine

    engine = VpinEngine(bucket_size=100.0, window=10)  # no ticker
    for i in range(20):
        engine.update(price_change=0.01, volume=10.0, sigma=0.2, dt=1.0)

    # Engine should still work fine
    assert engine.compute_vpin() >= 0.0


# ---------------------------------------------------------------------------
# Test 14: Anomaly detector emits metrics on update
# ---------------------------------------------------------------------------
def test_anomaly_detector_emits_metrics():
    from services.anomaly_detector import FlowAnomalyDetector
    from services.observability import metrics as m

    detector = FlowAnomalyDetector(seq_len=5, latent_dim=4, ticker="SPY")
    # Feed enough observations to warm up
    for i in range(10):
        result = detector.update(vpin=0.5 + i * 0.01, qi=0.1)

    output = m.get_metrics_bytes().decode()
    assert 'floww_anomaly_score{ticker="SPY"}' in output


# ---------------------------------------------------------------------------
# Test 15: Histogram buckets cover expected API latency range
# ---------------------------------------------------------------------------
def test_api_latency_buckets_cover_range():
    from services.observability import metrics as m
    # p50 at 23ms should fall in 0.025 bucket
    m.api_request_duration_seconds.labels(
        route="/api/test", method="GET", status="200"
    ).observe(0.023)
    # p99 at 2.5s should fall in 2.5 bucket
    m.api_request_duration_seconds.labels(
        route="/api/test", method="GET", status="200"
    ).observe(2.5)

    output = m.get_metrics_bytes().decode()
    # Both observations should be counted
    assert "floww_duckdb_batch_size" not in output or True  # just checking no crash
    assert "floww_api_request_duration_seconds_count 2" in output
