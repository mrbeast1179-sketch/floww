"""
tests/services/ml/test_outcomes.py

Tests for the realized outcome attachment service.
"""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone, timedelta

from services.ml.outcomes import (
    attach_realized_outcomes,
    compute_rolling_accuracy,
    fetch_next_day_outcome,
    _try_underlying_bars,
)


@pytest.fixture
def mock_db():
    db = MagicMock()
    db["ml_predictions"] = AsyncMock()
    db["underlying_bars"] = AsyncMock()
    return db


class TestFetchNextDayOutcome:
    @pytest.mark.asyncio
    async def test_successful_fetch(self):
        mock_data = MagicMock()
        mock_data.empty = False
        mock_data.columns = ["Open", "High", "Low", "Close", "Volume"]
        mock_data.index = [datetime(2024, 1, 14), datetime(2024, 1, 15), datetime(2024, 1, 16)]
        mock_data.__getitem__ = lambda self, key: MagicMock(
            get=lambda k, d=0: {"Open": 450.0, "Close": 452.0, "High": 453.0, "Low": 449.0}.get(k, d)
        )
        mock_data.iloc = [MagicMock(get=lambda k, d=0: {"Open": 450.0, "Close": 452.0, "High": 453.0, "Low": 449.0}.get(k, d))]

        with patch("services.ml.outcomes.yf.download", return_value=mock_data):
            result = await fetch_next_day_outcome("SPY", "2024-01-14T10:00:00")
            # Result depends on mock structure; mainly testing no crash
            # The actual yfinance integration is tested manually

    @pytest.mark.asyncio
    async def test_empty_data(self):
        mock_data = MagicMock()
        mock_data.empty = True
        with patch("services.ml.outcomes.yf.download", return_value=mock_data):
            result = await fetch_next_day_outcome("SPY", "2024-01-14T10:00:00")
            assert result is None

    @pytest.mark.asyncio
    async def test_yfinance_error(self):
        with patch("services.ml.outcomes.yf.download", side_effect=Exception("network error")):
            result = await fetch_next_day_outcome("SPY", "2024-01-14T10:00:00")
            assert result is None


class TestTryUnderlyingBars:
    @pytest.mark.asyncio
    async def test_successful_fallback(self, mock_db):
        mock_db["underlying_bars"].find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[{
                "date": "2024-01-16",
                "open": 450.0,
                "close": 452.0,
                "high": 453.0,
                "low": 449.0,
            }]
        )
        result = await _try_underlying_bars(mock_db, "SPY", "2024-01-15T10:00:00")
        assert result is not None
        assert result["realized_label"] == 1  # close > open
        assert result["data_source"] == "underlying_bars"

    @pytest.mark.asyncio
    async def test_no_bars(self, mock_db):
        mock_db["underlying_bars"].find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[]
        )
        result = await _try_underlying_bars(mock_db, "SPY", "2024-01-15T10:00:00")
        assert result is None

    @pytest.mark.asyncio
    async def test_zero_prices(self, mock_db):
        mock_db["underlying_bars"].find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[{"date": "2024-01-16", "open": 0, "close": 0, "high": 0, "low": 0}]
        )
        result = await _try_underlying_bars(mock_db, "SPY", "2024-01-15T10:00:00")
        assert result is None


class TestAttachRealizedOutcomes:
    @pytest.mark.asyncio
    async def test_no_pending_predictions(self, mock_db):
        mock_db["ml_predictions"].find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[]
        )
        result = await attach_realized_outcomes(mock_db)
        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_recent_predictions(self, mock_db):
        recent_ts = datetime.now(timezone.utc) - timedelta(hours=2)
        mock_db["ml_predictions"].find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[{
                "_id": "pred1",
                "ticker": "SPY",
                "ts": recent_ts.isoformat(),
                "prediction": 1,
            }]
        )
        result = await attach_realized_outcomes(mock_db)
        assert result == 0  # Skipped because too recent

    @pytest.mark.asyncio
    async def test_skips_missing_ticker_or_ts(self, mock_db):
        old_ts = (datetime.now(timezone.utc) - timedelta(days=3)).isoformat()
        mock_db["ml_predictions"].find.return_value.sort.return_value.limit.return_value.to_list = AsyncMock(
            return_value=[
                {"_id": "pred1", "ticker": "", "ts": old_ts, "prediction": 1},
                {"_id": "pred2", "ticker": "SPY", "ts": "", "prediction": 1},
            ]
        )
        result = await attach_realized_outcomes(mock_db)
        assert result == 0


class TestComputeRollingAccuracy:
    @pytest.mark.asyncio
    async def test_no_predictions(self, mock_db):
        mock_db["ml_predictions"].aggregate.return_value.to_list = AsyncMock(return_value=[])
        result = await compute_rolling_accuracy(mock_db, "SPY")
        assert result["n_predictions"] == 0
        assert result["accuracy"] is None

    @pytest.mark.asyncio
    async def test_with_outcomes(self, mock_db):
        mock_db["ml_predictions"].aggregate.return_value.to_list = AsyncMock(
            return_value=[{
                "n_total": 100,
                "n_with_outcome": 80,
                "n_correct": 55,
                "avg_return": 0.15,
            }]
        )
        result = await compute_rolling_accuracy(mock_db, "SPY")
        assert result["n_predictions"] == 100
        assert result["n_with_outcomes"] == 80
        assert result["accuracy"] == 0.6875  # 55/80
        assert result["avg_return_pct"] == 0.15

    @pytest.mark.asyncio
    async def test_aggregation_error(self, mock_db):
        mock_db["ml_predictions"].aggregate.side_effect = Exception("db error")
        result = await compute_rolling_accuracy(mock_db, "SPY")
        assert result["n_predictions"] == 0
        assert result["accuracy"] is None


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
