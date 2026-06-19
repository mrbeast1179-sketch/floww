"""backend/tests/test_position_sizing.py — Reference tests for backend/domain/position_sizing.py.

Hand-verified pins from the design doc:
  Case 1. Stock (delta=1, mult=1) $200 budget / $2 loss-per-share = 100 contracts.
  Case 2. ATM call (delta=0.5, mult=100) $200 / $100 = 2 contracts.
  Case 3. OTM call (delta=0.2, mult=100) $200 / $40 = 5 contracts.
  Case 4. Deep ITM call (delta=0.9) $500 / $450 = 1 contract (floor).
  Case 5. Long PUT (delta=-0.5) sizes identically to ATM long call.
  Case 6. Zero delta → 0 contracts.
  Case 7. Zero stop distance → 0 contracts.

Kelly pins at p=0.55, b=1.65:
  f* = 0.2727..., half-Kelly = 0.1364, quarter-Kelly = 0.0682.
  Breakeven probability = 1/(b+1) = 0.3774 (37.74%).

Round-trip property: max_loss_at_stop(qty) <= budget (with floor rounding).
"""

from __future__ import annotations

import math

import pytest

from domain.position_sizing import (
    OPTION_MULTIPLIER,
    STOCK_MULTIPLIER,
    delta_adjusted_max_loss_size,
    half_kelly,
    kelly_breakeven_probability,
    kelly_fraction,
    max_loss_at_stop,
    quarter_kelly,
    size_position_at_stop,
)

# ----------------------------------------------------------------------- #
# delta_adjusted_max_loss_size                                            #
# ----------------------------------------------------------------------- #


class TestDeltaAdjustedMaxLossSize:
    """Hand-verified contract counts at the money management boundary."""

    def test_stock_with_delta_one(self):
        """Case 1: $200 budget / $2 loss-per-share = 100 contracts.

        With ``delta=1`` and ``multiplier=1`` (stock-equivalent), each share
        loses ``|entry − stop| = 2`` dollars. The formula
        ``floor(200 / 2) = 100``.
        """
        qty = delta_adjusted_max_loss_size(
            account_equity=10_000,
            risk_pct=0.02,
            delta=1.0,
            entry_spot=100.0,
            stop_spot=98.0,
            multiplier=STOCK_MULTIPLIER,
        )
        assert qty == 100

    def test_atm_call_50delta(self):
        """Case 2: ATM call (delta=0.5, mult=100) → 2 contracts.

        Loss-per-contract = 100 · 0.5 · 2 = $100. ``floor(200/100) = 2``.
        """
        qty = delta_adjusted_max_loss_size(
            account_equity=10_000,
            risk_pct=0.02,
            delta=0.5,
            entry_spot=100.0,
            stop_spot=98.0,
        )
        assert qty == 2

    def test_otm_call_20delta(self):
        """Case 3: OTM call (delta=0.2, mult=100) → 5 contracts.

        Smaller delta → *larger* position (you're betting on the move
        with low notional exposure). Loss-per-contract = 100 · 0.2 · 2 = $40.
        ``floor(200/40) = 5``.
        """
        qty = delta_adjusted_max_loss_size(
            account_equity=10_000,
            risk_pct=0.02,
            delta=0.2,
            entry_spot=100.0,
            stop_spot=98.0,
        )
        assert qty == 5

    def test_deep_itm_call_90delta(self):
        """Case 4: deep ITM (delta=0.9, mult=100) → 1 contract.

        Large deltaeff captures most of the underlying → small position.
        Loss-per-contract = 100 · 0.9 · 5 = $450. ``floor(500/450) = 1``.
        """
        qty = delta_adjusted_max_loss_size(
            account_equity=50_000,
            risk_pct=0.01,
            delta=0.9,
            entry_spot=200.0,
            stop_spot=195.0,
        )
        assert qty == 1

    def test_long_put_sign_irrelevant(self):
        """Case 5: PUT delta=-0.5 sizes identically to ATM call."""
        qty_call = delta_adjusted_max_loss_size(
            10_000, 0.02, +0.5, 100.0, 98.0
        )
        qty_put = delta_adjusted_max_loss_size(
            10_000, 0.02, -0.5, 100.0, 98.0
        )
        assert qty_call == qty_put == 2

    def test_zero_delta_returns_zero(self):
        """Case 6: deep OTM (delta≈0) cannot be safely sized."""
        qty = delta_adjusted_max_loss_size(
            10_000, 0.02, 0.0, 100.0, 98.0
        )
        assert qty == 0

        qty_tiny = delta_adjusted_max_loss_size(
            10_000, 0.02, 1e-9, 100.0, 98.0
        )
        assert qty_tiny == 0  # below EPSILON_DELTA=1e-6

    def test_zero_distance_returns_zero(self):
        """Case 7: no stop distance → cannot compute exposure."""
        qty = delta_adjusted_max_loss_size(
            10_000, 0.02, 0.5, 100.0, 100.0
        )
        assert qty == 0

    def test_negative_inputs_return_zero(self):
        """All non-positive scalar inputs → 0 contracts (silent mask)."""
        assert delta_adjusted_max_loss_size(0, 0.02, 0.5, 100, 98) == 0
        assert delta_adjusted_max_loss_size(10_000, 0.0, 0.5, 100, 98) == 0
        assert delta_adjusted_max_loss_size(10_000, 1.5, 0.5, 100, 98) == 0
        assert delta_adjusted_max_loss_size(10_000, -0.02, 0.5, 100, 98) == 0
        assert delta_adjusted_max_loss_size(10_000, 0.02, 0.5, -100, 98) == 0
        assert delta_adjusted_max_loss_size(10_000, 0.02, 0.5, 100, -98) == 0
        assert delta_adjusted_max_loss_size(10_000, 0.02, 0.5, 100, 98, multiplier=-1) == 0

    def test_round_trip_loss_within_budget(self):
        """Case 8: max_loss_at_stop(qty) <= budget under all delta+spot combos."""
        for delta in (0.05, 0.20, 0.50, 0.80, 0.95):
            for entry in (50.0, 100.0, 500.0):
                for stop_offset in (1.0, 5.0, 25.0):
                    stop = entry - stop_offset
                    equity, risk = 25_000.0, 0.015
                    budget = equity * risk
                    qty = delta_adjusted_max_loss_size(
                        equity, risk, delta, entry, stop
                    )
                    loss = max_loss_at_stop(qty, delta, entry, stop)
                    assert loss <= budget + 1e-6, (
                        f"delta={delta} entry={entry} stop={stop} "
                        f"qty={qty} loss={loss} budget={budget}"
                    )


# ----------------------------------------------------------------------- #
# max_loss_at_stop                                                        #
# ----------------------------------------------------------------------- #


class TestMaxLossAtStop:
    def test_round_trip_atm(self):
        """2 ATM contracts at $100 each = $200 loss (== budget)."""
        loss = max_loss_at_stop(contracts=2, delta=0.5, entry_spot=100.0, stop_spot=98.0)
        assert loss == pytest.approx(200.0, abs=1e-9)

    def test_zero_contracts_returns_zero(self):
        assert max_loss_at_stop(0, 0.5, 100, 98) == 0.0
        assert max_loss_at_stop(-1, 0.5, 100, 98) == 0.0

    def test_put_sign_irrelevant(self):
        loss_long_call = max_loss_at_stop(2, 0.5, 100, 98)
        loss_long_put = max_loss_at_stop(2, -0.5, 100, 98)
        assert loss_long_call == loss_long_put

    def test_invalid_inputs_return_zero(self):
        assert max_loss_at_stop(2, 0.5, -100, 98) == 0.0
        assert max_loss_at_stop(2, 0.5, 100, -98) == 0.0
        assert max_loss_at_stop(2, 0.5, 100, 98, multiplier=-1) == 0.0

    def test_stock_one_share_loss(self):
        """1 stock share through $2 stop = $2 loss."""
        loss = max_loss_at_stop(1, 1.0, 100.0, 98.0, multiplier=1.0)
        assert loss == pytest.approx(2.0, abs=1e-9)


# ----------------------------------------------------------------------- #
# Kelly criterion                                                         #
# ----------------------------------------------------------------------- #


class TestKellyMath:
    def test_full_kelly_at_p_055_b_165(self):
        """f* = (0.55 · 1.65 − 0.45) / 1.65 = 0.2773..."""
        # 0.9075 / 1.65 = 0.27727...
        f_star = kelly_fraction(0.55, 1.65)
        assert f_star == pytest.approx(0.2773, abs=1e-3)

    def test_half_kelly_at_p_055_b_165(self):
        """half-Kelly = 0.5 · f* = 0.1386..."""
        assert half_kelly(0.55, 1.65) == pytest.approx(0.1386, abs=1e-3)

    def test_quarter_kelly_at_p_055_b_165(self):
        """quarter-Kelly = 0.25 · f* = 0.0693..."""
        assert quarter_kelly(0.55, 1.65) == pytest.approx(0.0693, abs=1e-3)

    def test_kelly_below_breakeven_returns_zero(self):
        """At p < 1/(b+1), the rational bet is 0 (no edge)."""
        # Breakeven at b=2.0 is p=1/3=0.333...
        f_below = kelly_fraction(0.30, 2.0)
        f_at = kelly_fraction(1 / 3.0, 2.0)
        f_above = kelly_fraction(0.40, 2.0)
        assert f_below == 0.0
        assert f_at == pytest.approx(0.0, abs=1e-9)
        assert f_above > 0.0

    def test_breakeven_probability(self):
        """1/(b+1) — at b=1.65 → 0.3774 (37.74%)."""
        assert kelly_breakeven_probability(1.65) == pytest.approx(0.3774, abs=1e-3)
        assert kelly_breakeven_probability(1.0) == 0.5
        assert kelly_breakeven_probability(2.0) == pytest.approx(1 / 3.0)

    def test_certain_loss_returns_zero(self):
        """p=0 ⇒ no edge."""
        assert kelly_fraction(0.0, 1.65) == 0.0
        assert kelly_fraction(-0.1, 1.65) == 0.0

    def test_certain_win_returns_full(self):
        """p=1 ⇒ f* = 1.0."""
        # With b=1.65, f* = (1·1.65 - 0)/1.65 = 1.0
        assert kelly_fraction(1.0, 1.65) == pytest.approx(1.0, abs=1e-9)

    def test_kelly_invalid_inputs(self):
        assert kelly_fraction(0.55, 0.0) == 0.0
        assert kelly_fraction(0.55, -1.0) == 0.0
        assert kelly_fraction(1.5, 1.65) == 0.0  # p > 1 invalid


# ----------------------------------------------------------------------- #
# size_position_at_stop aggregator                                        #
# ----------------------------------------------------------------------- #


class TestSizePositionAtStop:
    def test_summary_keys(self):
        summary = size_position_at_stop(
            account_equity=10_000,
            risk_pct=0.02,
            delta=0.5,
            entry_spot=100.0,
            stop_spot=98.0,
        )
        assert set(summary.keys()) == {"qty", "loss_per_contract", "max_dollar_loss"}
        assert summary["qty"] == 2
        assert summary["loss_per_contract"] == pytest.approx(100.0)
        assert summary["max_dollar_loss"] == pytest.approx(200.0)

    def test_cap_applied(self):
        """Hard ``cap`` clamps the result; loss respects the cap, not the budget."""
        # Without cap: floor(200/40) = 5 contracts (OTM delta=0.2)
        # With cap=2: expected qty=2, max_loss=$80 (< $200 budget)
        summary = size_position_at_stop(
            account_equity=10_000,
            risk_pct=0.02,
            delta=0.2,
            entry_spot=100.0,
            stop_spot=98.0,
            cap=2,
        )
        assert summary["qty"] == 2
        assert summary["max_dollar_loss"] == pytest.approx(80.0)


# ----------------------------------------------------------------------- #
# Cross-property sanity checks                                            #
# ----------------------------------------------------------------------- #


class TestSizingMonotonicity:
    """Smoke checks for mathematical sanity."""

    def test_larger_delta_means_fewer_contracts(self):
        """Higher |delta| → larger exposure per contract → smaller position."""
        low_delta = delta_adjusted_max_loss_size(
            10_000, 0.02, delta=0.2, entry_spot=100.0, stop_spot=98.0
        )
        high_delta = delta_adjusted_max_loss_size(
            10_000, 0.02, delta=0.8, entry_spot=100.0, stop_spot=98.0
        )
        assert low_delta > high_delta > 0

    def test_tighter_stop_means_fewer_contracts(self):
        """Tighter stop → smaller dollar move → larger exposure per
        contract → fewer contracts needed to hit budget."""
        loose = delta_adjusted_max_loss_size(
            10_000, 0.02, delta=0.5, entry_spot=100.0, stop_spot=90.0  # $10 mo
        )
        tight = delta_adjusted_max_loss_size(
            10_000, 0.02, delta=0.5, entry_spot=100.0, stop_spot=99.0  # $1 move
        )
        assert loose < tight

    def test_larger_risk_pct_means_more_contracts(self):
        # Use a low-multiplier + small-budget setup so BOTH sides produce
        # at least 1 contract — otherwise the test silently hits the
        # delta-aware 0-return sentinel on the budget-constrained side.
        # delta=0.05, mult=1, distance=2 → loss_per_unit=0.10
        #   risk=0.005 -> budget=$50 -> 500 contracts
        #   risk=0.05  -> budget=$500 -> 5000 contracts
        small = delta_adjusted_max_loss_size(10_000, 0.005, 0.05, 100, 98, multiplier=1.0)
        big = delta_adjusted_max_loss_size(10_000, 0.05, 0.05, 100, 98, multiplier=1.0)
        assert big > small > 0


class TestKellyMonotonicity:
    def test_higher_win_prob_higher_kelly(self):
        f_low = kelly_fraction(0.55, 1.65)
        f_high = kelly_fraction(0.65, 1.65)
        assert f_high > f_low > 0

    def test_higher_payoff_higher_kelly(self):
        f_low_b = kelly_fraction(0.55, 1.5)
        f_high_b = kelly_fraction(0.55, 2.0)
        assert f_high_b > f_low_b > 0

    def test_half_kelly_correctly_scales(self):
        f_star = kelly_fraction(0.55, 1.65)
        assert half_kelly(0.55, 1.65) == pytest.approx(0.5 * f_star)
        assert quarter_kelly(0.55, 1.65) == pytest.approx(0.25 * f_star)
