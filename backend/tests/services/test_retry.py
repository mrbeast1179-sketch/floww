"""Unit tests for services/retry.py — GSD Phase 3.3."""
from __future__ import annotations

import asyncio

import pytest

from services.retry import retry_async, retry_sync


class Flaky:
    """Fails n times, then succeeds."""

    def __init__(self, failures: int):
        self.failures = failures
        self.calls = 0

    def __call__(self) -> str:
        self.calls += 1
        if self.calls <= self.failures:
            raise RuntimeError(f"transient {self.calls}")
        return "ok"


def test_retry_sync_succeeds_after_failures():
    flaky = Flaky(2)
    result = retry_sync(flaky, attempts=4, base_delay=0.01)
    assert result == "ok"
    assert flaky.calls == 3


def test_retry_sync_exhausts_and_raises():
    flaky = Flaky(10)
    with pytest.raises(RuntimeError, match="transient 3"):
        retry_sync(flaky, attempts=3, base_delay=0.01)
    assert flaky.calls == 3


def test_retry_sync_no_retry_on_success():
    flaky = Flaky(0)
    assert retry_sync(flaky, attempts=3) == "ok"
    assert flaky.calls == 1


def test_jitter_bounds_delay():
    from services.retry import _jittered_delay
    for attempt in range(5):
        d = _jittered_delay(attempt, base_delay=0.5)
        assert 0 < d <= 10.0


def test_async_retry():
    async def main() -> str:
        calls = {"n": 0}

        async def maybe_fail() -> str:
            calls["n"] += 1
            if calls["n"] < 3:
                raise ValueError("transient")
            return "done"

        return await retry_async(maybe_fail, attempts=5, base_delay=0.01)

    assert asyncio.run(main()) == "done"


def test_sync_wrapped_yfinance_fetch():
    """The actual integration: fetch_underlying_ohlcv survives transient failures."""
    import sys
    sys.path.insert(0, ".")
    from unittest.mock import MagicMock, patch

    import pandas as pd

    from services.yfinance_fetcher import fetch_underlying_ohlcv

    good_df = pd.DataFrame({
        "timestamp": pd.to_datetime(["2026-08-26 09:30"]),
        "open": [760.0], "high": [761.0], "low": [759.0],
        "close": [760.5], "volume": [1000],
    })

    fake_ticker = MagicMock()
    fake_ticker.history.side_effect = [
        Exception("rate limited"),
        pd.DataFrame(),          # empty (transient)
        good_df,                 # success on 3rd try
    ]

    def fake_ticker_fn(_sym):
        return fake_ticker

    with patch("services.yfinance_fetcher.yf.Ticker", side_effect=fake_ticker_fn):
        df = fetch_underlying_ohlcv("SPY", period="1d", interval="1m")

    assert len(df) == 1
    assert fake_ticker.history.call_count == 3
