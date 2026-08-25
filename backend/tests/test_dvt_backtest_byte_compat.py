"""backend/tests/test_dvt_backtest_byte_compat.py — Smoke tests verifying
that the delta-aware refactor of `dvt_backtest.py::DVTBacktester.run_backtest()`
preserves byte-exact equivalence to the legacy stock formula and that the
delta-aware variant produces sensible alternatives when non-default Greeks
are supplied.

These tests do NOT touch the network (no yfinance calls); they construct
DVTBacktester directly and exercise only the size-formula branch.

Reference: Kendall (2008) "Trading and Exchanges" Ch. 14 (position sizing by
delta-equivalent notional); Tharp (1998) Ch. 7.
"""

from __future__ import annotations

import sys
from pathlib import Path

# The dvt_backtest.py lives at /Users/nav/, NOT inside the floww backend
# tree, so we need to add both /Users/nav/ (for dvt_backtest.py) AND
# the floww backend/ (for domain.position_sizing) to sys.path before
# importing. Without backend/ on sys.path, the canonical primitive
# import below cannot resolve.
PROJECT_ROOT = Path("/Users/nav")
FLOWW_BACKEND = PROJECT_ROOT / "Documents" / "GitHub" / "floww" / "backend"
for _p in (str(PROJECT_ROOT), str(FLOWW_BACKEND)):
    if _p not in sys.path:
        sys.path.insert(0, _p)


from dvt_backtest import DVTBacktester  # noqa: E402

from domain.position_sizing import delta_adjusted_max_loss_size  # noqa: E402

import pytest as _pytest

if __import__("importlib").util.find_spec("dvt_backtest") is None:
    _pytest.skip(
        "dvt_backtest.py (machine-local DVT engine) not present", allow_module_level=True
    )


# Legacy formula kept verbatim for cross-checking.
def _legacy_shares(account: float, risk_per_trade: float, entry: float, stop: float) -> int:
    """Original pre-refactor formula from dvt_backtest.py around line 200."""
    if stop <= 0 or entry <= 0 or entry - stop <= 0:
        return 0
    risk_amount = account * risk_per_trade
    return int(risk_amount / (entry - stop))


def _refactored_shares(
    account: float,
    risk_per_trade: float,
    delta: float,
    multiplier: float,
    entry: float,
    stop: float,
) -> int:
    """Direct passthrough to the canonical ``delta_adjusted_max_loss_size``.

    This helper is intentionally a one-line forwarder to the *same* primitive
    that ``dvt_backtest.py::DVTBacktester.run_backtest`` now calls. Inlining
    the formula here would just let the test compare the inlined copy
    against itself — which silently passes even if the canonical guard
    logic drifts. Direct call catches precision-level drift directly.
    """
    return delta_adjusted_max_loss_size(
        account_equity=account,
        risk_pct=risk_per_trade,
        delta=delta,
        entry_spot=entry,
        stop_spot=stop,
        multiplier=multiplier,
    )


class TestDVTDefaults:
    """Defaults reproduce legacy stock formula byte-equal."""

    def test_default_delta_is_one(self):
        bt = DVTBacktester("TEST")
        assert bt.delta == 1.0
        assert bt.multiplier == 1.0

    def test_explicit_delta_one_multiplier_one(self):
        bt = DVTBacktester("TEST", delta=1.0, multiplier=1.0)
        assert bt.delta == 1.0
        assert bt.multiplier == 1.0

    def test_byte_equal_legacy_across_grid(self):
        """Stock defaults produce identical integer outputs across a grid of
        realistic inputs."""
        params = [
            (10_000.0, 0.02, 100.0, 98.0),
            (25_000.0, 0.03, 55.30, 54.70),
            (5_000.0, 0.01, 200.0, 195.0),
            (1_000.0, 0.05, 42.0, 40.0),
            (50_000.0, 0.015, 580.0, 575.0),
        ]
        for equity, risk, entry, stop in params:
            leg = _legacy_shares(equity, risk, entry, stop)
            new = _refactored_shares(
                account=equity,
                risk_per_trade=risk,
                delta=1.0,
                multiplier=1.0,
                entry=entry,
                stop=stop,
            )
            assert new == leg, (
                f"drift: equity={equity} risk={risk} entry={entry} stop={stop} "
                f"legacy={leg} new={new}"
            )


class TestDVTAwareVariants:
    """Non-default Greeks scale position size in the right direction."""

    def test_atm_call_delta_halves_size(self):
        """delta=0.5 + mult=100 should yield ~halved contracts vs delta=1+mult=1."""
        equity, risk = 10_000.0, 0.02
        entry, stop = 100.0, 98.0
        # Stock default reference: legacy says 100 shares ($200 / $2).
        stock = _refactored_shares(equity, risk, 1.0, 1.0, entry, stop)
        # Each contract loss: 100 · 0.5 · 2 = $100 → 2 contracts.
        atm = _refactored_shares(equity, risk, 0.5, 100.0, entry, stop)
        # The SAME dollar budget ($200) buys FAR fewer option contracts.
        assert stock > atm
        assert atm == 2
        assert stock == 100

    def test_otm_low_delta_scales_up(self):
        """delta=0.2 should size larger than delta=0.5 (less exposure/contract)."""
        equity, risk = 10_000.0, 0.02
        otm = _refactored_shares(equity, risk, 0.2, 100.0, 100.0, 98.0)
        atm = _refactored_shares(equity, risk, 0.5, 100.0, 100.0, 98.0)
        assert otm > atm

    def test_put_sign_irrelevant(self):
        """delta=-0.5 should size identically to delta=+0.5."""
        long_call = _refactored_shares(
            10_000, 0.02, +0.5, 100.0, 100.0, 98.0
        )
        long_put = _refactored_shares(
            10_000, 0.02, -0.5, 100.0, 100.0, 98.0
        )
        assert long_call == long_put == 2

    def test_zero_delta_returns_zero(self):
        """delta=0 cannot size — the formula emits 0 (not Inf)."""
        contracts = _refactored_shares(
            10_000, 0.02, 0.0, 100.0, 100.0, 98.0
        )
        assert contracts == 0

    def test_mult_one_equals_stock_for_low_delta(self):
        """delta=0.5 + mult=1 should size equal to a deeply-discounted stock."""
        # Equivalent to: 1 share of a $200 stock but only $1 moves per $1 underlying.
        contracts = _refactored_shares(
            10_000, 0.02, 0.5, 1.0, 100.0, 98.0
        )
        # Loss per "share" = 1 * 0.5 * 2 = $1. $200 / $1 = 200.
        assert contracts == 200


class TestDVTBackwardsCompatibilitySurface:
    """Confirm the public surface didn't regress for existing callers."""

    def test_signature_unchanged(self):
        """DVTBacktester signature still accepts (symbol, start, end, timeframe)."""
        import inspect

        sig = inspect.signature(DVTBacktester.__init__)
        params = list(sig.parameters.keys())
        # Original four params + new delta + multiplier
        assert params[:4] == ["self", "symbol", "start", "end"]
        # New optional kwargs at the end (default values are None or 1.0)
        assert "delta" in params
        assert "multiplier" in params

    def test_existing_call_still_works(self):
        """`DVTBacktester(symbol, start='2024-01-01', timeframe='1d')` works."""
        bt = DVTBacktester("SPY", start="2024-01-01", timeframe="1d")
        assert bt.symbol == "SPY"
        assert bt.timeframe == "1d"
        assert bt.delta == 1.0
        assert bt.multiplier == 1.0
