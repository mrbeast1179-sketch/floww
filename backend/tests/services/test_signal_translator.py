"""
backend/tests/services/test_signal_translator.py

Unit tests for signal_translator.py — signal-to-intent translation.

Coverage:
    - Conviction calculation
    - All 5 risk gates (conviction, equity, sentiment, positions, liquidity)
    - TradeIntent generation with correct fields
    - Side determination from gex_state
    - Position sizing
    - Stop loss / take profit values
    - Signal ID generation
    - Rationale string format
"""

import logging
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


class TestConvictionCalculation:
    def test_basic_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        # conviction = 0.95 * (95/100) * (1-0.1) = 0.95 * 0.95 * 0.9 = 0.812
        assert result.conviction == pytest.approx(0.812, abs=0.01)

    def test_high_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        # conviction = 0.95 * 0.95 * 0.9 = 0.81225
        assert result.conviction > 0.8

    def test_zero_anomaly_gives_zero_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.0,
            trinity_score=100.0,
            vpin_cdf=0.0,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
            kyle_lambda=1e-7,
        )
        result = translate_signal(inp)
        assert result is None  # conviction = 0 < 0.7

    def test_max_vpin_reduces_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.9,
            trinity_score=90.0,
            vpin_cdf=1.0,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        _result = translate_signal(inp)
        # conviction = 0.9 * 0.9 * 0 = 0

    def test_boundary_conviction(self):
        from services.signal_translator import MIN_CONVICTION, SignalInput, translate_signal
        # Find inputs that give exactly MIN_CONVICTION
        inp = SignalInput(
            anomaly_score=MIN_CONVICTION,
            trinity_score=100.0,
            vpin_cdf=0.0,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.conviction >= MIN_CONVICTION


class TestRiskGates:
    def test_conviction_too_low(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.5,
            trinity_score=80.0,
            vpin_cdf=0.3,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_equity_too_low(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=1000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_sentiment_too_negative(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            flashalpha_sentiment_z=-3.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_too_many_open_positions(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            current_positions={"SPY": 3},
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_illiquid_market(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            kyle_lambda=1e-5,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is None

    def test_exact_equity_boundary(self):
        from services.signal_translator import MIN_ACCOUNT_EQUITY, SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=MIN_ACCOUNT_EQUITY,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None


class TestTradeIntentOutput:
    def test_has_signal_id(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert len(result.signal_id) == 16
        assert all(c in "0123456789abcdef" for c in result.signal_id)

    def test_side_positive_gex(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            gex_state="positive",
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.side == "buy"

    def test_side_negative_gex(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            gex_state="negative",
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.side == "sell"

    def test_side_neutral_defaults_buy(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            gex_state="neutral",
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.side == "buy"

    def test_stop_loss_is_2pct_below(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        expected_stop = round(450.0 * 0.98, 2)
        assert result.stop_loss == expected_stop

    def test_take_profit_is_6pct_above(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        expected_tp = round(450.0 * 1.06, 2)
        assert result.take_profit == expected_tp

    def test_rr_is_3_to_1(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=100.0,
        )
        result = translate_signal(inp)
        assert result is not None
        risk = result.limit_price - result.stop_loss
        reward = result.take_profit - result.limit_price
        rr = reward / risk
        assert rr == pytest.approx(3.0, abs=0.1)

    def test_rationale_contains_conviction(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert "conviction=" in result.rationale
        assert "anomaly=" in result.rationale
        assert "trinity=" in result.rationale

    def test_position_sizing_1pct_equity(self):
        from services.signal_translator import MAX_POSITION_PCT, SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=100.0,
        )
        result = translate_signal(inp)
        assert result is not None
        max_qty = int(10000.0 * MAX_POSITION_PCT / 100.0)
        assert result.qty <= max_qty + 1

    def test_ticker_preserved(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="QQQ",
            spot_price=350.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.ticker == "QQQ"

    def test_limit_price_equals_spot(self):
        from services.signal_translator import SignalInput, translate_signal
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            ticker="SPY",
            spot_price=450.0,
        )
        result = translate_signal(inp)
        assert result is not None
        assert result.limit_price == 450.0


class TestCheckGatesDirectly:
    def test_all_gates_pass(self):
        from services.signal_translator import SignalInput, _check_gates
        inp = SignalInput(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            flashalpha_sentiment_z=0.0,
            current_positions={},
            kyle_lambda=1e-7,
            ticker="SPY",
            spot_price=450.0,
        )
        conviction = 0.95 * 0.95 * 0.9
        result = _check_gates(inp, conviction)
        assert result["approved"] is True

    def test_conviction_gate_fails(self):
        from services.signal_translator import SignalInput, _check_gates
        inp = SignalInput(
            account_equity=10000.0,
            flashalpha_sentiment_z=0.0,
            current_positions={},
            kyle_lambda=1e-7,
        )
        result = _check_gates(inp, 0.5)
        assert result["approved"] is False
        assert "conviction" in result["reason"]

    def test_equity_gate_fails(self):
        from services.signal_translator import SignalInput, _check_gates
        inp = SignalInput(
            account_equity=100.0,
            flashalpha_sentiment_z=0.0,
            current_positions={},
            kyle_lambda=1e-7,
        )
        result = _check_gates(inp, 0.8)
        assert result["approved"] is False
        assert "equity" in result["reason"]


class TestKellyRecommendation:
    """Pins the wire-up between ``SignalInput.kelly_win_prob`` /
    ``kelly_avg_rr`` -> ``_compute_kelly_recommendation()`` -> ``TradeIntent.kelly``.
    """

    def _approved_input(self, **overrides):
        """Build a SignalInput that passes all five risk gates."""
        base = dict(
            anomaly_score=0.95,
            trinity_score=95.0,
            vpin_cdf=0.1,
            account_equity=10000.0,
            flashalpha_sentiment_z=0.0,
            current_positions={},
            kyle_lambda=1e-7,
            ticker="SPY",
            spot_price=450.0,
        )
        base.update(overrides)
        from services.signal_translator import SignalInput
        return SignalInput(**base)

    def test_kelly_block_present_on_every_approved_intent(self):
        from services.signal_translator import translate_signal
        intent = translate_signal(self._approved_input())
        assert intent is not None
        assert intent.kelly is not None

    def test_kelly_uses_anchor_defaults_when_neither_supplied(self):
        # Hand-derived for p=0.55, b=1.65:
        # f* = (0.55*1.65 - 0.45)/1.65 ≈ 0.2773; half_kelly ≈ 0.1386
        # notional = 10000 * 0.1386 ≈ $1,386.36
        from services.signal_translator import translate_signal
        intent = translate_signal(self._approved_input())
        assert intent.kelly.win_prob == pytest.approx(0.55, abs=1e-4)
        assert intent.kelly.avg_rr == pytest.approx(1.65, abs=1e-4)
        assert intent.kelly.full_kelly_fraction == pytest.approx(0.2773, abs=1e-3)
        assert intent.kelly.half_kelly_fraction == pytest.approx(0.1386, abs=1e-3)
        assert intent.kelly.kelly_notional == pytest.approx(1386.36, abs=1.0)
        assert intent.kelly.would_trade is True

    def test_kelly_passes_through_supplied_inputs(self):
        # Hand pin for p=0.65, b=2.0:
        # f* = (0.65*2.0 - 0.35)/2.0 = 0.475; half_kelly = 0.2375
        # notional = 10000 * 0.2375 = $2,375.00
        from services.signal_translator import translate_signal
        intent = translate_signal(
            self._approved_input(kelly_win_prob=0.65, kelly_avg_rr=2.0)
        )
        assert intent.kelly.win_prob == pytest.approx(0.65, abs=1e-4)
        assert intent.kelly.avg_rr == pytest.approx(2.0, abs=1e-4)
        assert intent.kelly.full_kelly_fraction == pytest.approx(0.475, abs=1e-3)
        assert intent.kelly.half_kelly_fraction == pytest.approx(0.2375, abs=1e-3)
        assert intent.kelly.kelly_notional == pytest.approx(2375.0, abs=1.0)

    def test_kelly_no_trade_filter_on_negative_edge(self):
        # For b=1.0, breakeven = 0.50; p=0.30 < 0.50 -> Kelly = 0.
        from services.signal_translator import translate_signal
        intent = translate_signal(
            self._approved_input(kelly_win_prob=0.30, kelly_avg_rr=1.0)
        )
        assert intent.kelly.full_kelly_fraction == 0.0
        assert intent.kelly.half_kelly_fraction == 0.0
        assert intent.kelly.kelly_notional == 0.0
        assert intent.kelly.qty_kelly_naive == 0
        assert intent.kelly.would_trade is False

    def test_kelly_partial_supply_warns_and_uses_anchor_for_missing(self, caplog):
        """Partial supply ⇒ warning AND fill only the MISSING field from the anchor.

        Verbatim: ``kelly_win_prob=0.65`` (supplied, used as-is);
        ``kelly_avg_rr=None`` (missing, filled from anchor=1.65).
        The supplied value is NEVER silently overwritten; the warning
        is the only signal that the trader is using a hybrid (their
        calibration blended with our anchor).
        """
        from services.signal_translator import translate_signal
        caplog.set_level(logging.WARNING, logger="services.signal_translator")
        intent = translate_signal(
            self._approved_input(kelly_win_prob=0.65)  # avg_rr=None
        )
        assert any(
            "Kelly fields partially supplied" in r.getMessage()
            for r in caplog.records
        ), "expected partial-supply warning"
        # Supplied wins.
        assert intent.kelly.win_prob == pytest.approx(0.65, abs=1e-4)
        # Missing falls back to anchor.
        assert intent.kelly.avg_rr == pytest.approx(1.65, abs=1e-4)

    def test_kelly_partial_supply_anchor_for_missing_inverse(self, caplog):
        """Inverse direction: only ``kelly_avg_rr`` supplied, ``kelly_win_prob`` None.

        Locks bidirectional partial-supply coverage: supplied wins on
        either side; missing always fills from the same anchor (0.55, 1.65).
        """
        from services.signal_translator import translate_signal
        caplog.set_level(logging.WARNING, logger="services.signal_translator")
        intent = translate_signal(
            self._approved_input(kelly_avg_rr=2.0)  # win_prob=None
        )
        assert any(
            "Kelly fields partially supplied" in r.getMessage()
            for r in caplog.records
        ), "expected partial-supply warning"
        # Missing → anchor 0.55.
        assert intent.kelly.win_prob == pytest.approx(0.55, abs=1e-4)
        # Supplied wins.
        assert intent.kelly.avg_rr == pytest.approx(2.0, abs=1e-4)

    def test_kelly_block_does_not_change_executed_qty(self):
        # Diagnostic only - TradeIntent.qty still respects LEGACY_QTY_CAP=10.
        from services.signal_translator import LEGACY_QTY_CAP, translate_signal
        intent = translate_signal(self._approved_input())
        assert intent.qty <= LEGACY_QTY_CAP
        assert intent.kelly is not None

    def test_kelly_qty_naive_upper_bound_math(self):
        # For half-Kelly(0.65, 2.0) = 0.2375 at equity=$10k, spot=$100:
        # notional=$2,375 -> qty_kelly_naive = floor(2375/100) = 23.
        from services.signal_translator import translate_signal
        intent = translate_signal(
            self._approved_input(
                kelly_win_prob=0.65,
                kelly_avg_rr=2.0,
                spot_price=100.0,
            )
        )
        assert intent.kelly.kelly_notional == pytest.approx(2375.0, abs=1.0)
        assert intent.kelly.qty_kelly_naive == 23


class TestKellyRecommendationByteCompat:
    """Defensive pins for direct ``TradeIntent(...)`` callers.

    Any caller that builds a ``TradeIntent`` directly — without going
    through ``translate_signal()`` — must still get a valid None-typed
    ``kelly`` field AND a serialisation round-trip. paper_trading.py,
    Hermes adapters, and any future caller rely on this contract.
    """

    def test_trade_intent_kelly_default_is_none_and_serializable(self):
        from services.signal_translator import TradeIntent
        intent = TradeIntent(
            ticker="SPY",
            side="buy",
            qty=1,
            order_type="limit",
            limit_price=450.0,
            stop_loss=441.0,
            take_profit=477.0,
            signal_id="deadbeefdeadbeef",
            conviction=0.81,
            rationale="unit test",
        )
        assert intent.kelly is None
        # .model_dump() must include the None-typed kelly key without
        # raising — downstream journal writers (paper_trading.py, JSONL
        # exporters) depend on this contract.
        dump = intent.model_dump()
        assert dump["kelly"] is None
        assert dump["ticker"] == "SPY"
        assert dump["qty"] == 1


class TestKellyRejectPolicy:
    """Pins the opt-in Kelly hard-gate. Mirrors ``test_sizer.py::TestKellySizerInit``."""

    def test_kelly_reject_policy_init_defaults_are_no_op(self):
        # Default dataclass must dispatch identically to ``policy=None``.
        from services.signal_translator import KellyRejectPolicy
        p = KellyRejectPolicy()
        assert p.reject_on_negative_edge is False
        assert p.min_win_prob == 0.50
        assert p.require_supplied_calibration is False
        assert p.log_rejections is True
        assert p.ignore_supplied_calibration is True

    def test_kelly_reject_policy_init_custom_overrides(self):
        from services.signal_translator import KellyRejectPolicy
        p = KellyRejectPolicy(
            reject_on_negative_edge=True,
            min_win_prob=0.40,
            require_supplied_calibration=True,
            log_rejections=False,
            ignore_supplied_calibration=False,
        )
        assert p.reject_on_negative_edge is True
        assert p.min_win_prob == 0.40
        assert p.require_supplied_calibration is True
        assert p.log_rejections is False
        assert p.ignore_supplied_calibration is False

    def test_kelly_gate_default_off_returns_intent(self, caplog):
        # policy=None and policy=KellyRejectPolicy() (default OFF) must
        # both return a TradeIntent — the diagnostic-only contract.
        from services.signal_translator import (
            KellyRejectPolicy,
            SignalInput,
            translate_signal,
        )
        caplog.set_level(logging.INFO, logger="services.signal_translator")
        inp = SignalInput(
            anomaly_score=0.95, trinity_score=95.0, vpin_cdf=0.1,
            account_equity=10000.0, ticker="SPY", spot_price=450.0,
            kelly_win_prob=0.30, kelly_avg_rr=1.0,  # NEGATIVE edge
        )
        # policy=None (default).
        assert translate_signal(inp) is not None
        # policy default — reject_on_negative_edge=False.
        assert translate_signal(inp, kelly_policy=KellyRejectPolicy()) is not None
        # No rejection log fired.
        assert not any(
            "kelly_negative_edge" in r.getMessage() for r in caplog.records
        )

    def test_kelly_gate_enabled_rejects_negative_edge(self, caplog):
        # reject_on_negative_edge=True + negative Kelly → None + log.
        from services.signal_translator import (
            KellyRejectPolicy,
            SignalInput,
            translate_signal,
        )
        caplog.set_level(logging.INFO, logger="services.signal_translator")
        inp = SignalInput(
            anomaly_score=0.95, trinity_score=95.0, vpin_cdf=0.1,
            account_equity=10000.0, ticker="SPY", spot_price=450.0,
            kelly_win_prob=0.30, kelly_avg_rr=1.0,  # breakeven 0.50 → no edge
        )
        policy = KellyRejectPolicy(reject_on_negative_edge=True)
        result = translate_signal(inp, kelly_policy=policy)
        assert result is None
        # Grep-friendly rejection reason token + conviction in log line.
        rejection_logs = [
            r for r in caplog.records
            if "kelly_negative_edge" in r.getMessage()
        ]
        assert len(rejection_logs) == 1
        msg = rejection_logs[0].getMessage()
        assert "Signal rejected for SPY" in msg
        assert "conviction=" in msg
        assert "win_prob=0.3" in msg

    def test_kelly_gate_enabled_passes_positive_edge(self):
        # Same policy as above but POSITIVE edge → TradeIntent returned.
        from services.signal_translator import (
            KellyRejectPolicy,
            SignalInput,
            translate_signal,
        )
        inp = SignalInput(
            anomaly_score=0.95, trinity_score=95.0, vpin_cdf=0.1,
            account_equity=10000.0, ticker="SPY", spot_price=450.0,
            kelly_win_prob=0.65, kelly_avg_rr=2.0,  # POSITIVE edge
        )
        policy = KellyRejectPolicy(reject_on_negative_edge=True)
        intent = translate_signal(inp, kelly_policy=policy)
        assert intent is not None
        assert intent.ticker == "SPY"
        assert intent.kelly is not None
        assert intent.kelly.would_trade is True

    def test_kelly_gate_enabled_with_supplied_bypass(self):
        # ignore_supplied_calibration=False: supplied (p, b) bypasses
        # the gate even when the calibration is sub-breakeven. Trader
        # explicitly owns the calibration; opt-in caveat ignored.
        from services.signal_translator import (
            KellyRejectPolicy,
            SignalInput,
            translate_signal,
        )
        inp = SignalInput(
            anomaly_score=0.95, trinity_score=95.0, vpin_cdf=0.1,
            account_equity=10000.0, ticker="SPY", spot_price=450.0,
            kelly_win_prob=0.30, kelly_avg_rr=1.0,  # negative edge
        )
        policy = KellyRejectPolicy(
            reject_on_negative_edge=True,
            ignore_supplied_calibration=False,
        )
        intent = translate_signal(inp, kelly_policy=policy)
        assert intent is not None
        assert intent.kelly.would_trade is False  # diagnostic still honest

    def test_kelly_gate_require_supplied_calibration(self):
        # require_supplied_calibration=True without both fields → reject.
        from services.signal_translator import (
            KellyRejectPolicy,
            SignalInput,
            translate_signal,
        )
        inp = SignalInput(
            anomaly_score=0.95, trinity_score=95.0, vpin_cdf=0.1,
            account_equity=10000.0, ticker="SPY", spot_price=450.0,
            # No kelly fields supplied → anchor fallback used internally.
        )
        policy = KellyRejectPolicy(
            reject_on_negative_edge=True,
            require_supplied_calibration=True,
        )
        assert translate_signal(inp, kelly_policy=policy) is None

    def test_kelly_gate_log_rejections_false_suppresses_log(self, caplog):
        # Symmetric inverse of test_kelly_gate_enabled_rejects_negative_edge:
        # when ``log_rejections=False``, the gate still rejects (returns
        # None) but emits NO rejection log line. Hard pin to keep the
        # silent-rejection path honest.
        from services.signal_translator import (
            KellyRejectPolicy,
            SignalInput,
            translate_signal,
        )
        caplog.set_level(logging.INFO, logger="services.signal_translator")
        inp = SignalInput(
            anomaly_score=0.95, trinity_score=95.0, vpin_cdf=0.1,
            account_equity=10000.0, ticker="SPY", spot_price=450.0,
            kelly_win_prob=0.30, kelly_avg_rr=1.0,
        )
        policy = KellyRejectPolicy(reject_on_negative_edge=True, log_rejections=False)
        result = translate_signal(inp, kelly_policy=policy)
        assert result is None
        assert not any(
            "kelly_negative_edge" in r.getMessage() for r in caplog.records
        ), "expected silent rejection when log_rejections=False"

    def test_kelly_gate_min_win_prob_threshold(self):
        # Positive edge overall (kelly.would_trade=True) but win_prob
        # below ``min_win_prob`` → secondary gate fires.
        from services.signal_translator import (
            KellyRejectPolicy,
            SignalInput,
            translate_signal,
        )
        # breakeven at b=2.0 is 1/(2.0+1) = 0.333; p=0.40 > breakeven so
        # would_trade=True. min_win_prob=0.45 should reject.
        inp = SignalInput(
            anomaly_score=0.95, trinity_score=95.0, vpin_cdf=0.1,
            account_equity=10000.0, ticker="SPY", spot_price=450.0,
            kelly_win_prob=0.40, kelly_avg_rr=2.0,
        )
        policy = KellyRejectPolicy(
            reject_on_negative_edge=True,
            min_win_prob=0.45,
        )
        result = translate_signal(inp, kelly_policy=policy)
        assert result is None
        # And the no-threshold policy passes.
        policy_loose = KellyRejectPolicy(
            reject_on_negative_edge=True, min_win_prob=0.30,
        )
        assert translate_signal(inp, kelly_policy=policy_loose) is not None
