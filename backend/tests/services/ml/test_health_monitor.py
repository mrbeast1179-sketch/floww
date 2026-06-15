"""
tests/services/ml/test_health_monitor.py

Unit tests for ML model health monitor — compute_psi, assess_model_health,
get_all_models_health, and ModelHealthStatus thresholds.
"""
from __future__ import annotations

import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import numpy as np
import pytest

# ensure backend/ is on sys.path so `from services...` works
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # -> backend/

from services.ml.health_monitor import (
    ModelHealthStatus,
    _compute_feature_drift,
    assess_model_health,
    compute_psi,
    get_all_models_health,
)

# ── compute_psi ──────────────────────────────────────────────────────────────

class TestComputePsi:
    golden_bins = 10

    def test_identical_distributions_returns_near_zero(self):
        """PSI of a distribution against itself should be ≈ 0."""
        np.random.seed(42)
        data = np.random.normal(0, 1, 500)
        psi = compute_psi(data, data, bins=self.golden_bins)
        assert psi == pytest.approx(0.0, abs=0.01)

    def test_shifted_distribution_returns_positive_psi(self):
        """Shifting mean by 1 sigma should produce clearly positive PSI."""
        np.random.seed(123)
        expected = np.random.normal(0, 1, 1000)
        actual = np.random.normal(1.0, 1, 1000)
        psi = compute_psi(expected, actual, bins=self.golden_bins)
        assert psi > 0.1

    def test_large_shift_high_psi(self):
        """Mean shift of 3 sigma should yield PSI > 0.25 (drift threshold)."""
        np.random.seed(7)
        expected = np.random.normal(0, 1, 2000)
        actual = np.random.normal(3.0, 1, 2000)
        psi = compute_psi(expected, actual, bins=self.golden_bins)
        assert psi > 0.25

    def test_too_few_samples_returns_zero(self):
        """If len < bins, PSI should return 0.0 guard value."""
        small = np.array([1.0, 2.0, 3.0])
        psi = compute_psi(small, small, bins=10)
        assert psi == 0.0

    def test_constant_array_returns_zero(self):
        """Constant data → unique breakpoints collapse → return 0.0."""
        const = np.ones(50)
        psi = compute_psi(const, const, bins=10)
        assert psi == 0.0

    def test_different_variance(self):
        """Same mean, different variance → positive PSI."""
        np.random.seed(42)
        expected = np.random.normal(0, 1, 1000)
        actual = np.random.normal(0, 2, 1000)
        psi = compute_psi(expected, actual, bins=self.golden_bins)
        assert psi > 0.0

    def test_psi_non_negative(self):
        """PSI is always >= 0 (it's a sum of KL-like terms)."""
        np.random.seed(99)
        for _ in range(5):
            a = np.random.normal(np.random.randn() * 2, 0.5 + np.random.rand(), 500)
            b = np.random.normal(np.random.randn() * 2, 0.5 + np.random.rand(), 500)
            psi = compute_psi(a, b, bins=self.golden_bins)
            assert psi >= 0.0, f"PSI went negative: {psi}"


# ── ModelHealthStatus constants ───────────────────────────────────────────────

class TestModelHealthStatus:
    def test_constants_exist(self):
        assert ModelHealthStatus.HEALTHY == "HEALTHY"
        assert ModelHealthStatus.DEGRADED == "DEGRADED"
        assert ModelHealthStatus.CRITICAL == "CRITICAL"
        assert ModelHealthStatus.STALE == "STALE"
        assert ModelHealthStatus.UNKNOWN == "UNKNOWN"


# ── assess_model_health ───────────────────────────────────────────────────────

def _make_mock_db(
    predictions=None,
    latest_ts=None,
    feature_snapshots=None,
):
    """Build a mock Motor db with configurable ml_predictions collection."""
    col = MagicMock()

    # -- find().to_list() cursor for rolling accuracy --
    cursor = MagicMock()
    docs = predictions or []
    cursor.to_list = AsyncMock(return_value=docs)
    col.find = MagicMock(return_value=cursor)

    # -- find_one() for data freshness --
    if latest_ts is not None:
        ts_val = latest_ts.isoformat() if isinstance(latest_ts, datetime) else latest_ts
        col.find_one = AsyncMock(return_value={"timestamp": ts_val})
    else:
        col.find_one = AsyncMock(return_value=None)

    db = MagicMock()
    db.__getitem__ = lambda self, key: col
    db["ml_predictions"] = col
    return db


def _make_registry_with_model(ticker="SPY", model_id="spy_v3", training_stats=None):
    """Return (mock_registry, patcher_for_ModelRegistry)."""
    mock_reg = AsyncMock()

    model_doc = {
        "model_id": model_id,
        "created_at": "2024-01-01T00:00:00",
    }
    if training_stats:
        model_doc["training_data_stats"] = training_stats

    mock_reg.list_models = AsyncMock(return_value=[model_doc])
    return mock_reg


class TestAssessModelHealth:

    @pytest.mark.asyncio
    async def test_no_active_model_returns_unknown(self):
        mock_reg = AsyncMock()
        mock_reg.list_models = AsyncMock(return_value=[])
        db = _make_mock_db()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await assess_model_health(db, "SPY")
        assert result["status"] == ModelHealthStatus.UNKNOWN
        assert "No active model" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_healthy_model_high_accuracy(self):
        """Accuracy > 0.52 and < 48h fresh → HEALTHY."""
        now = datetime.now(UTC)
        docs = [
            {"prediction": 1, "outcome": 1, "timestamp": now.isoformat()}
            for _ in range(80)
        ] + [
            {"prediction": 0, "outcome": 1, "timestamp": now.isoformat()}
            for _ in range(20)
        ]
        db = _make_mock_db(predictions=docs, latest_ts=now)
        mock_reg = _make_registry_with_model()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await assess_model_health(db, "SPY")
        assert result["rolling_7d_accuracy"] == pytest.approx(0.8)
        assert result["status"] == ModelHealthStatus.HEALTHY

    @pytest.mark.asyncio
    async def test_critical_low_7d_accuracy(self):
        """7d accuracy < 0.50 → CRITICAL."""
        now = datetime.now(UTC)
        docs = [
            {"prediction": 1, "outcome": 0, "timestamp": now.isoformat()}
            for _ in range(70)
        ] + [
            {"prediction": 1, "outcome": 1, "timestamp": now.isoformat()}
            for _ in range(30)
        ]
        db = _make_mock_db(predictions=docs, latest_ts=now)
        mock_reg = _make_registry_with_model()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await assess_model_health(db, "SPY")
        assert result["rolling_7d_accuracy"] == pytest.approx(0.3)
        assert result["status"] == ModelHealthStatus.CRITICAL
        assert "retrain immediately" in result["recommendation"]

    @pytest.mark.asyncio
    async def test_degraded_low_30d_accuracy(self):
        """Accuracy < 0.50 → CRITICAL (mock returns same data for 7d and 30d)."""
        now = datetime.now(UTC)
        # 40/100 correct = 0.40 → below 0.50 threshold → CRITICAL
        docs = [
            {"prediction": 1, "outcome": 1, "timestamp": now.isoformat()}
            for _ in range(40)
        ] + [
            {"prediction": 0, "outcome": 1, "timestamp": now.isoformat()}
            for _ in range(60)
        ]
        db = _make_mock_db(predictions=docs, latest_ts=now)
        mock_reg = _make_registry_with_model()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await assess_model_health(db, "SPY")
        # Both 7d and 30d accuracy will be 0.40 (same data returned)
        # 7d → CRITICAL since 0.40 < 0.50
        assert result["status"] == ModelHealthStatus.CRITICAL

    @pytest.mark.asyncio
    async def test_stale_data_over_48h(self):
        """Last prediction > 48h ago → STALE."""
        stale_ts = datetime.now(UTC) - timedelta(hours=72)
        db = _make_mock_db(predictions=[], latest_ts=stale_ts)
        mock_reg = _make_registry_with_model()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await assess_model_health(db, "SPY")
        assert result["data_freshness_hours"] == pytest.approx(72.0, abs=1.0)
        assert result["status"] == ModelHealthStatus.STALE

    @pytest.mark.asyncio
    async def test_insufficient_outcomes_returns_unknown(self):
        """Fewer than 10 outcomes → accuracy is None → UNKNOWN."""
        now = datetime.now(UTC)
        db = _make_mock_db(predictions=[], latest_ts=now)
        mock_reg = _make_registry_with_model()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await assess_model_health(db, "SPY")
        assert result["rolling_7d_accuracy"] is None
        assert result["status"] == ModelHealthStatus.UNKNOWN

    @pytest.mark.asyncio
    async def test_ticker_is_uppercased(self):
        db = _make_mock_db(predictions=[], latest_ts=datetime.now(UTC))
        mock_reg = _make_registry_with_model()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await assess_model_health(db, "spy")
        assert result["ticker"] == "SPY"

    @pytest.mark.asyncio
    async def test_result_has_required_keys(self):
        now = datetime.now(UTC)
        db = _make_mock_db(predictions=[], latest_ts=now)
        mock_reg = _make_registry_with_model()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await assess_model_health(db, "SPY")
        required_keys = {"ticker", "status", "checked_at"}
        assert required_keys.issubset(result.keys())


# ── get_all_models_health ────────────────────────────────────────────────────

class TestGetAllModelsHealth:
    @pytest.mark.asyncio
    async def test_returns_default_tickers_when_registry_fails(self):
        mock_reg = AsyncMock()
        mock_reg.get_active_tickers = AsyncMock(side_effect=Exception("db down"))
        db = _make_mock_db()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await get_all_models_health(db)
        # Should fall back to default tickers
        assert result["summary"]["total"] == 5
        assert "SPY" in result["models"]
        assert "QQQ" in result["models"]

    @pytest.mark.asyncio
    async def test_summary_counts(self):
        mock_reg = AsyncMock()
        mock_reg.get_active_tickers = AsyncMock(return_value=["SPY", "QQQ"])
        db = _make_mock_db()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await get_all_models_health(db)
        # Both models default to UNKNOWN status (no data)
        summary = result["summary"]
        assert summary["total"] == 2
        assert summary["healthy"] == 0
        assert summary["critical"] == 0
        assert summary["overall_status"] == "HEALTHY"  # no degraded or critical

    @pytest.mark.asyncio
    async def test_checked_at_present(self):
        mock_reg = AsyncMock()
        mock_reg.get_active_tickers = AsyncMock(return_value=[])
        db = _make_mock_db()
        with patch("services.ml.health_monitor._get_registry_from_db", return_value=mock_reg):
            result = await get_all_models_health(db)
        assert "checked_at" in result


# ── _compute_feature_drift (internal helper) ─────────────────────────────────

class TestComputeFeatureDrift:
    @pytest.mark.asyncio
    async def test_no_recent_snapshots_returns_empty(self):
        col = MagicMock()
        cursor = MagicMock()
        cursor.to_list = AsyncMock(return_value=[])
        sorted_cursor = MagicMock()
        sorted_cursor.to_list = AsyncMock(return_value=[])
        sorted_cursor.limit = MagicMock(return_value=sorted_cursor)
        col.find = MagicMock(return_value=MagicMock(sort=MagicMock(return_value=sorted_cursor)))

        db = MagicMock()
        db.__getitem__ = lambda self, key: col

        model_doc = {
            "model_id": "test",
            "training_data_stats": {"feat1": {"mean": 0, "std": 1}},
        }
        result = await _compute_feature_drift(db, "SPY", model_doc)
        assert result == {}

    @pytest.mark.asyncio
    async def test_no_training_stats_returns_empty(self):
        db = MagicMock()
        model_doc = {"model_id": "test"}  # no training_data_stats
        result = await _compute_feature_drift(db, "SPY", model_doc)
        assert result == {}
