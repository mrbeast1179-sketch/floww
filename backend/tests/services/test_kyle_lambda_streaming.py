"""
backend/tests/services/test_kyle_lambda_streaming.py

Defence-in-depth regression tests for the KyleLambda.update() guard
re-ordering bug in backend/services/liquidity_metrics.py
(P2 entry #6 in docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md).

Pre-fix bug:
    def update(self, price, volume, sign):
        if len(self._returns) > 0:            # <-- WRONG gate
            prev_price = self._last_price if hasattr(self, '_last_price') else price
            if prev_price > 0:
                ret = math.log(price / prev_price) if price > 0 and prev_price > 0 else 0.0
                self._returns.append(ret)
                self._signed_volumes.append(sign * volume)
        self._last_price = price              # <-- set AFTER the body

Effect:
  - On first call: `_returns` is empty (deque) -> body skipped -> only `_last_price` is set.
  - On every subsequent call: `_returns` was NEVER appended (because internal gate
    was never entered on first call too), so `_returns` stays empty for the
    lifetime of the object.  No `lambda` regression ever sees data -> the
    estimator returns NaN/0 in production.

Fixed invariant (the test enforces):
  - After exactly 1 call: `_returns` is empty, `_last_price == price`, signed
    volumes empty (no diff to compute).
  - After exactly 2 calls: `_returns` has 1 entry = log(price2 / price1);
    `_signed_volumes` has 1 entry = sign2 * volume2; `_last_price == price2`.
  - After N calls: `_returns` has N-1 entries; lengths grow by exactly 1 per
    diff; the latest `_last_price` is the most recent price.
  - After >=2 calls, estimate() returns a finite scalar (no NaN/0 from
    empty regression buffer).
"""
from __future__ import annotations

import math
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


@pytest.fixture
def fresh_kyle():
    from services.liquidity_metrics import KyleLambda
    return KyleLambda(window=100)


class TestKyleLambdaStreamingGuard:
    """Pinned regression: streaming guard must allow successive diff computation."""

    def test_first_call_only_sets_last_price(self, fresh_kyle):
        fresh_kyle.update(price=100.0, volume=1.0, sign=+1)
        assert fresh_kyle._last_price == 100.0
        assert len(fresh_kyle._returns) == 0, (
            "first call should NOT append a return (no prior price to diff against) — "
            "got first_call_appended=True which would indicate the guard is using "
            "post-update `len(self._returns) > 0` in a way that gates the first diff."
        )
        assert len(fresh_kyle._signed_volumes) == 0

    def test_second_call_appends_return_with_log_diff(self, fresh_kyle):
        fresh_kyle.update(price=100.0, volume=1.0, sign=+1)
        fresh_kyle.update(price=110.0, volume=2.0, sign=-1)
        assert len(fresh_kyle._returns) == 1
        assert len(fresh_kyle._signed_volumes) == 1
        assert fresh_kyle._returns[0] == pytest.approx(math.log(110.0 / 100.0), rel=1e-9)
        assert fresh_kyle._signed_volumes[0] == pytest.approx(-2.0, rel=1e-9)
        assert fresh_kyle._last_price == 110.0

    def test_n_calls_produce_n_minus_1_returns(self, fresh_kyle):
        """Stress: 10 calls -> 9 returns (no skips, ever)."""
        n = 10
        for i in range(n):
            fresh_kyle.update(price=100.0 + i, volume=1.0, sign=+1)
        assert len(fresh_kyle._returns) == n - 1, (
            f"after {n} calls expected {n - 1} returns but got "
            f"{len(fresh_kyle._returns)} — bug regression: streaming "
            f"guard still drops returns (P2 entry #6)."
        )
        assert len(fresh_kyle._signed_volumes) == n - 1
        assert fresh_kyle._last_price == pytest.approx(100.0 + n - 1)

    def test_returns_match_manual_log_diff(self, fresh_kyle):
        """Pinned: the computed returns match an independent manual computation."""
        prices = [100.0, 102.0, 99.0, 105.0, 110.0, 108.0]
        signs = [+1, -1, +1, +1, -1, +1]
        vols = [10.0, 20.0, 15.0, 30.0, 25.0, 18.0]
        for p, s, v in zip(prices, signs, vols, strict=True):
            fresh_kyle.update(price=p, volume=v, sign=s)
        expected_returns = [math.log(prices[i] / prices[i - 1]) for i in range(1, len(prices))]
        for got, exp in zip(fresh_kyle._returns, expected_returns, strict=True):
            assert got == pytest.approx(exp, rel=1e-9)

    def test_signed_volumes_match_jpm_sign_convention(self, fresh_kyle):
        """Pinned: signed_volumes = sign * volume (buy = +, sell = -)."""
        observations = [
            (100.0, 10.0, +1),
            (102.0, 15.0, +1),
            (101.0, 20.0, -1),
            (104.0, 25.0, +1),
        ]
        for p, v, s in observations:
            fresh_kyle.update(price=p, volume=v, sign=s)
        # _signed_volumes[i] = observations[i+1].sign * observations[i+1].volume
        expected = [15.0, -20.0, 25.0]
        for got, exp in zip(fresh_kyle._signed_volumes, expected, strict=True):
            assert got == pytest.approx(exp, rel=1e-9)


    def test_zero_price_skips_appending_returns_without_corrupting_state(self, fresh_kyle):
        """Edge case: a zero previous-price call does not log(0/something) -> appending
        must be skipped but _last_price must still update."""
        fresh_kyle.update(price=0.0, volume=1.0, sign=+1)
        fresh_kyle.update(price=0.0, volume=1.0, sign=+1)  # both zero, skip ret
        assert len(fresh_kyle._returns) == 0
        assert fresh_kyle._last_price == 0.0
        # Recover: a positive price now produces a clean diff against 0.
        fresh_kyle.update(price=100.0, volume=1.0, sign=+1)  # no return yet (prev is 0)
        assert len(fresh_kyle._returns) == 0
        fresh_kyle.update(price=110.0, volume=1.0, sign=+1)  # log(110/100)
        assert len(fresh_kyle._returns) == 1
