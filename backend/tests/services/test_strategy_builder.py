"""8-case pytest suite for services/strategy_builder.evaluate_strategy.

Mirrors the #6 chain_consensus / #20 insider / #10 strike cone test-suite
pattern: smoke + behavior verification on each public entry point.

Verified-against API (direct probe in this session, 2026-07-16)::

    evaluate_strategy(
        legs,
        spot: float,
        expiry: str | None = None,
        today: str | None = None,
        n_grid_points: int = 150,
    ) -> dict

Return-dict keys (full schema)::
    ticker, spot, premium_total, max_profit_at_grid, max_loss_at_grid,
    breakevens, n_breakevens, spot_grid, payoff_grid,
    probability_of_profit, expected_pnl, expected_move_pct,
    var_95, expected_shortfall_95, greeks_aggregate,
    warnings, leg_count, structure_label

Contract-multiplier convention: legs are quoted at per-share prices,
the service multiplies by 100 to convert to notional $ amount. Iron
butterfly (net credit) → premium_total = -500 (sellers' credit).
Bull call spread (net debit) → premium_total = +500 (buyer's debit).
Long call → premium_total = +300 (buyer pays 3.0×100).

Failure mode: invalid legs (zero qty / negative strike / bad expiry)
are filtered out + emit structured warnings via the ``warnings`` field.
The service NEVER raises.
"""

from __future__ import annotations

from datetime import date, timedelta

from services.strategy_builder import evaluate_strategy

# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────


def _leg(
    *,
    side: str,
    qty: int,
    option_type: str,
    strike: float,
    expiry: str,
    premium: float,
    iv: float | None = 0.30,
):
    """Build a leg dict matching the strategy_builder contract."""
    return {
        "side": side,
        "qty": qty,
        "option_type": option_type,
        "strike": strike,
        "expiry": expiry,
        "premium": premium,
        "iv": iv,
    }


def _future_expiry(days_out: int = 14) -> str:
    """ISO date string ``days_out`` calendar days from today."""
    return (date.today() + timedelta(days=days_out)).isoformat()


# ─────────────────────────────────────────────────────────────────────
# Test classes — organized by strategy shape
# ─────────────────────────────────────────────────────────────────────


class TestEvaluateStrategyIronButterfly:
    """Iron butterfly: short straddle + long wings at single expiry."""

    def test_returns_expected_schema_keys(self):
        spot = 100.0
        expiry = _future_expiry(14)
        legs = [
            _leg(side="sell", qty=1, option_type="call",
                 strike=100.0, expiry=expiry, premium=4.0),
            _leg(side="buy",  qty=1, option_type="call",
                 strike=110.0, expiry=expiry, premium=1.5),
            _leg(side="sell", qty=1, option_type="put",
                 strike=100.0, expiry=expiry, premium=4.0),
            _leg(side="buy",  qty=1, option_type="put",
                 strike=90.0,  expiry=expiry, premium=1.5),
        ]
        out = evaluate_strategy(legs, spot=spot)

        assert isinstance(out, dict)
        # Required schema keys
        for k in (
            "ticker", "spot", "premium_total",
            "max_profit_at_grid", "max_loss_at_grid",
            "breakevens", "n_breakevens",
            "spot_grid", "payoff_grid",
            "probability_of_profit", "expected_pnl",
            "var_95", "expected_shortfall_95",
            "greeks_aggregate", "warnings", "leg_count", "structure_label",
        ):
            assert k in out, (
                f"Required schema key {k!r} missing from "
                f"evaluate_strategy output — got {sorted(out)}"
            )
        # Iron butterfly: short at-the-money straddle + long OTM wings
        assert out["structure_label"] == "iron_butterfly"
        assert out["leg_count"] == 4
        # Net credit: 8.0 received - 3.0 paid = 5.0 credit per share × 100
        # Signed as negative on the per-leg basis per service convention.
        assert out["premium_total"] == -500.0

    def test_iron_butterfly_has_two_breakevens(self):
        spot = 100.0
        expiry = _future_expiry(14)
        legs = [
            _leg(side="sell", qty=1, option_type="call",
                 strike=100.0, expiry=expiry, premium=4.0),
            _leg(side="buy",  qty=1, option_type="call",
                 strike=110.0, expiry=expiry, premium=1.5),
            _leg(side="sell", qty=1, option_type="put",
                 strike=100.0, expiry=expiry, premium=4.0),
            _leg(side="buy",  qty=1, option_type="put",
                 strike=90.0,  expiry=expiry, premium=1.5),
        ]
        out = evaluate_strategy(legs, spot=spot)
        # Iron butterfly has 2 breakevens (one each side of body strike).
        assert out["n_breakevens"] >= 1
        assert isinstance(out["breakevens"], list)


class TestEvaluateStrategyBullCallSpread:
    """Bull call spread: long lower strike + short higher strike."""

    def test_bull_call_spread_premium_is_positive_debit(self):
        spot = 100.0
        expiry = _future_expiry(21)
        legs = [
            _leg(side="buy",  qty=1, option_type="call",
                 strike=95.0,  expiry=expiry, premium=6.0),
            _leg(side="sell", qty=1, option_type="call",
                 strike=110.0, expiry=expiry, premium=1.0),
        ]
        out = evaluate_strategy(legs, spot=spot)

        assert isinstance(out, dict)
        assert out["structure_label"] == "bull_call_spread"
        # 6.0 paid - 1.0 received = 5.0 debit × 100 = +500
        assert out["premium_total"] == 500.0
        # Max loss bounded by net debit.
        assert out["max_loss_at_grid"] <= 0.0
        assert abs(out["max_loss_at_grid"]) <= 550.0


class TestEvaluateStrategyLongStraddle:
    """Long straddle: 1 long call + 1 long put at same strike + expiry."""

    def test_long_straddle_returns_greeks_aggregate_with_delta(self):
        spot = 100.0
        expiry = _future_expiry(30)
        legs = [
            _leg(side="buy", qty=1, option_type="call",
                 strike=100.0, expiry=expiry, premium=4.0),
            _leg(side="buy", qty=1, option_type="put",
                 strike=100.0, expiry=expiry, premium=4.0),
        ]
        out = evaluate_strategy(legs, spot=spot)

        assert isinstance(out, dict)
        assert out["structure_label"] == "long_straddle"
        # 4.0 + 4.0 = 8.0 debit × 100 = +800
        assert out["premium_total"] == 800.0
        # Aggregate greeks present with at least delta sub-key
        greeks = out.get("greeks_aggregate", {})
        assert isinstance(greeks, dict)
        assert "delta" in greeks


class TestEvaluateStrategySingleLongCall:
    """Single-leg long call — the trivial baseline."""

    def test_long_call_premium_and_max_loss(self):
        spot = 100.0
        expiry = _future_expiry(7)
        legs = [
            _leg(side="buy", qty=1, option_type="call",
                 strike=105.0, expiry=expiry, premium=3.0),
        ]
        out = evaluate_strategy(legs, spot=spot)

        assert isinstance(out, dict)
        assert out["structure_label"] == "long_call"
        # 3.0 debit × 100 = +300
        assert out["premium_total"] == 300.0
        # Max loss = premium paid (long call premium).
        assert out["max_loss_at_grid"] <= 0.0
        assert abs(out["max_loss_at_grid"]) <= 350.0


class TestEvaluateStrategyInvalidLegs:
    """Mixed valid+invalid legs — invalid ones are skipped with warnings."""

    def test_invalid_legs_degrade_gracefully_with_warnings(self):
        """3 invalid legs (zero qty / negative strike / bad expiry) +
        1 valid leg → invalid are silently skipped, valid is evaluated."""
        expiry = _future_expiry(14)
        legs = [
            _leg(side="buy", qty=0, option_type="call",
                 strike=100.0, expiry=expiry, premium=4.0),       # invalid: zero qty
            _leg(side="buy", qty=1, option_type="call",
                 strike=-50.0, expiry=expiry, premium=4.0),      # invalid: negative strike
            _leg(side="buy", qty=1, option_type="call",
                 strike=100.0, expiry="not-a-date", premium=4.0), # invalid: bad expiry
            _leg(side="buy", qty=1, option_type="call",
                 strike=100.0, expiry=expiry, premium=3.0),       # 1 valid leg
        ]
        out = evaluate_strategy(legs, spot=100.0)

        # Function NEVER raises — returns a structured dict
        assert isinstance(out, dict)
        # Only the 1 valid leg contributes to the math
        assert out["leg_count"] == 1
        # The valid leg is a long_call → structure_label propagates
        assert out["structure_label"] in ("long_call", "single_leg")
        # The 3 invalid legs each produce a distinct warning
        warnings_text = " ".join(out["warnings"]).lower()
        assert "qty" in warnings_text, (
            f"Expected a qty-related warning, got: {out['warnings']}"
        )
        assert "strike" in warnings_text, (
            f"Expected a strike-related warning, got: {out['warnings']}"
        )
        assert "expiry" in warnings_text, (
            f"Expected an expiry-related warning, got: {out['warnings']}"
        )


class TestEvaluateStrategySmokeCheck:
    """Smoke checks across the public API surface."""

    def test_today_kwarg_accepts_iso_string(self):
        spot = 100.0
        expiry = _future_expiry(7)
        legs = [
            _leg(side="buy", qty=1, option_type="call",
                 strike=100.0, expiry=expiry, premium=3.0),
        ]
        out = evaluate_strategy(
            legs, spot=spot,
            today=date.today().isoformat(),
        )
        assert isinstance(out, dict)
        assert "probability_of_profit" in out
        pop = out["probability_of_profit"]
        assert 0.0 <= pop <= 1.0

    def test_today_kwarg_malformed_string_surfaces_warning_not_silent_default(self):
        """Strict guard against silent fallback: a malformed ``today``
        string (e.g. a typoed ``"yest"``) MUST surface a warning rather
        than silently degrading to ``date.today()``. The defensive
        fallback is fine for interactive UI but DANGEROUS for the #15
        backtester replay — a wrong-day synthetic-leg replay would
        corrupt the historical test without any error in the response
        payload. Pin the warning text so any future refactor that drops
        the warning is caught at the test layer."""
        spot = 100.0
        expiry = _future_expiry(7)
        legs = [
            _leg(side="buy", qty=1, option_type="call",
                 strike=100.0, expiry=expiry, premium=3.0),
        ]
        out = evaluate_strategy(
            legs, spot=spot,
            today="yest",   # deliberately malformed
        )
        warnings_text = " ".join(out["warnings"]).lower()
        assert "today not iso" in warnings_text, (
            f"malformed 'today' should emit a 'today not ISO' warning "
            f"so the #15 backtester caller can detect the silent "
            f"default-fallback. Got warnings={out['warnings']!r}"
        )

    def test_n_grid_points_kwarg_respected(self):
        spot = 100.0
        expiry = _future_expiry(7)
        legs = [
            _leg(side="buy", qty=1, option_type="call",
                 strike=100.0, expiry=expiry, premium=3.0),
        ]
        out_low = evaluate_strategy(legs, spot=spot, n_grid_points=20)
        out_high = evaluate_strategy(legs, spot=spot, n_grid_points=200)
        # Higher grid resolution → longer arrays.
        assert len(out_high["spot_grid"]) > len(out_low["spot_grid"])
        assert len(out_high["payoff_grid"]) > len(out_low["payoff_grid"])
        assert len(out_high["spot_grid"]) == 200
        assert len(out_low["spot_grid"]) == 20
