"""
backend/services/signal_translator.py

Signal-to-intent translator: converts Hermes analytics signals into
TradeIntent objects with conviction scoring and risk gates.

Conviction = anomaly_score * (trinity_score/100) * (1 - vpin_cdf)

Risk gates (all must pass):
- position_size ≤ 0.01 * account_equity
- flashalpha_sentiment_z ≥ -2
- open_positions_in_ticker < 3
- kyle_lambda < KYLE_LAMBDA_ILLIQUID_THRESHOLD (1e-6)
- account_equity > $5000

References:
- Kyle, A.S. (1985). "Continuous Auctions and Insider Trading." Econometrica.
- Almgren, R. & Chriss, N. (2001). "Optimal Execution of Portfolio Transactions."
"""
from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, Field

from domain.kelly_replay import ANCHOR_PAYOFF, ANCHOR_WIN_PROB
from domain.position_sizing import (
    delta_adjusted_max_loss_size,
    half_kelly,
    kelly_fraction,
)

logger = logging.getLogger(__name__)

KYLE_LAMBDA_ILLIQUID_THRESHOLD = 1e-6
MIN_CONVICTION = 0.7
MIN_ACCOUNT_EQUITY = 5000.0
MAX_POSITION_PCT = 0.01
MAX_OPEN_POSITIONS_PER_TICKER = 3
MIN_SENTIMENT_Z = -2.0

# Default contract multiplier used when SignalInput.multiplier is not
# supplied. 100 matches the listed-equity-options convention; signals
# for stock-equivalent positions (delta≈1) can pass 1.
DEFAULT_MULTIPLIER = 100.0
LEGACY_QTY_CAP = 10  # legacy ceiling preserved for the naive path


class KellyRecommendation(BaseModel):
    """Diagnostic Kelly sizing data for side-by-side comparison.

    This is **NOT** an executable sizing decision — the actual
    ``TradeIntent.qty`` still uses the 1-2 % equity cap path (delta-aware
    when supplied, naive otherwise). The Kelly fields are reported so a
    trader can see, *before approval*, what the trade would look like
    under canonical half-Kelly sizing at the supplied (or anchor-default)
    win probability and payoff ratio.

    See ``backend/domain/position_sizing.py`` for the underlying
    primitives (Kelly 1956: ``f* = (p.b - q)/b``) and
    ``backend/domain/kelly_replay.py`` for the historical evidence that
    calibrates the anchor (p=0.55, b=1.65).
    """
    win_prob: float                       # Effective win prob (supplied or anchor).
    avg_rr: float                         # Effective payoff ratio (supplied or anchor).
    full_kelly_fraction: float            # Raw f* (≥ 0; 0 means negative edge).
    half_kelly_fraction: float            # f*/2 — pragmatic default.
    kelly_notional: float                 # account_equity * half_kelly_fraction ($).
    qty_kelly_naive: int                  # Floor(notional / spot) — diagnostic upper bound.
    would_trade: bool                     # True iff full_kelly_fraction > 0.


class TradeIntent(BaseModel):
    """Output of the signal translator — a trade ready for execution."""
    ticker: str
    side: str  # "buy" or "sell"
    qty: int = Field(ge=1)
    order_type: str = "limit"  # "limit", "stop", "stop_limit"
    limit_price: float = 0.0
    stop_loss: float = 0.0
    take_profit: float = 0.0
    signal_id: str = ""
    conviction: float = 0.0
    rationale: str = ""
    # ── Kelly diagnostic (mirror of ``kelly_win_prob`` / ``kelly_avg_rr``
    # on ``SignalInput``). ``None`` when the caller did not opt in and the
    # anchor fallback was deliberately not applied (currently never —
    # the anchor is always applied; reserved for future explicit opt-out).
    kelly: KellyRecommendation | None = None


class SignalInput(BaseModel):
    """Input signals from Hermes analytics pipeline."""
    anomaly_score: float = 0.0
    gex_state: str = "neutral"  # "positive", "negative", "neutral"
    trinity_score: float = 0.0
    current_positions: dict[str, int] = {}  # ticker -> qty
    account_equity: float = 0.0
    flashalpha_sentiment_z: float = 0.0
    vpin_cdf: float = 0.0
    kyle_lambda: float = 0.0
    ticker: str = ""
    spot_price: float = 0.0
    # ── delta-aware sizing fields ────────────────────────────────────
    # Optional.  When provided, translate_signal() uses
    # domain.position_sizing.delta_adjusted_max_loss_size() instead of the
    # legacy implicit-delta=1 sizing rule.  Leaving them None preserves
    # the legacy behaviour for existing callers.
    delta: float | None = None
    stop_spot: float | None = None
    multiplier: float = DEFAULT_MULTIPLIER
    # ── Kelly diagnostic fields ───────────────────────────────────────
    # Optional. When BOTH are supplied, translate_signal() emits a
    # ``KellyRecommendation`` computed from this trader's calibrated
    # win probability and payoff ratio. When neither is supplied, the
    # anchor defaults (p=0.55, b=1.65 — matches kelly_replay.py
    # ANCHOR_WIN_PROB / ANCHOR_PAYOFF) are used. A partial-supply
    # (only one of the two) triggers a warning AND uses the anchor.
    kelly_win_prob: float | None = None
    kelly_avg_rr: float | None = None


def translate_signal(
    input_data: SignalInput,
    kelly_policy: KellyRejectPolicy | None = None,
) -> TradeIntent | None:
    """Convert analytics signals into a TradeIntent.

    Returns None if conviction is too low or any risk gate fails
    (including the optional Kelly reject policy when supplied).

    Parameters
    ----------
    input_data : SignalInput
        Signal + sizing fields.
    kelly_policy : KellyRejectPolicy | None
        Optional gate policy. ``None`` (default) preserves the
        diagnostic-only behaviour — every passing signal emits a
        ``kelly`` block on the returned ``TradeIntent`` and no signal
        is rejected on Kelly grounds.
    """
    # Compute conviction
    conviction = (
        input_data.anomaly_score
        * (input_data.trinity_score / 100.0)
        * (1.0 - input_data.vpin_cdf)
    )

    # Risk gates
    gates = _check_gates(input_data, conviction)
    if not gates["approved"]:
        logger.info(
            f"Signal rejected for {input_data.ticker}: {gates['reason']} "
            f"(conviction={conviction:.4f})"
        )
        return None

    # Determine side from GEX state
    if input_data.gex_state == "positive":
        side = "buy"
    elif input_data.gex_state == "negative":
        side = "sell"
    else:
        side = "buy"  # default

    # Position sizing — two paths:
    #   • Delta-aware (preferred): when SignalInput has all three of
    #     ``delta``, ``stop_spot``, and a positive ``spot_price``, size
    #     via delta-adjusted max-loss-at-stop so the expected loss at
    #     the stop is bounded by ``equity * MAX_POSITION_PCT``.  Returns
    #     0 when the Greeks can't be safely sized — caller must
    #     interpret 0 as "cannot translate to a trade".
    #   • Legacy fallback: implicit delta=1 (stock-equivalent), sized as
    #     `qty = equity * 0.01 / spot_price` capped at LEGACY_QTY_CAP=10.
    fields_supplied = (
        input_data.delta is not None,
        input_data.stop_spot is not None,
        input_data.spot_price > 0,
    )
    # Warn on partial delta-aware fields — silent fall-through would
    # under-bet options ~50× and is dangerous.
    if any(fields_supplied) and not all(fields_supplied):
        logger.warning(
            "translate_signal: delta-aware fields partially supplied "
            "(delta=%s, stop_spot=%s, spot_price=%s). Falling back to naive "
            "spot-based sizing. Pass delta+positive spot+stop_spot together.",
            input_data.delta,
            input_data.stop_spot,
            input_data.spot_price,
        )

    if all(fields_supplied):
        qty = delta_adjusted_max_loss_size(
            account_equity=input_data.account_equity,
            risk_pct=MAX_POSITION_PCT,
            delta=input_data.delta,
            entry_spot=input_data.spot_price,
            stop_spot=input_data.stop_spot,
            multiplier=input_data.multiplier,
        )
    else:
        max_qty = int(
            input_data.account_equity * MAX_POSITION_PCT
            / max(input_data.spot_price, 1.0)
        )
        # Legacy: always at least 1 contract unless spot is 0.
        qty = max(1, max_qty)
    # Cap at the legacy ceiling (10) for both paths.
    qty = max(0, min(qty, LEGACY_QTY_CAP))

    # Generate signal ID
    signal_id = hashlib.sha256(
        f"{input_data.ticker}:{input_data.anomaly_score}:{time.time_ns()}".encode()
    ).hexdigest()[:16]

    # Build rationale
    rationale = (
        f"conviction={conviction:.3f} "
        f"(anomaly={input_data.anomaly_score:.3f} "
        f"trinity={input_data.trinity_score:.1f} "
        f"vpin={input_data.vpin_cdf:.3f})"
    )

    # ── Kelly diagnostic ────────────────────────────────────────────────
    # Always emit (anchor fallback when not supplied). The actual
    # ``TradeIntent.qty`` is NOT changed by this block — delta-aware
    # remains the source of truth for the executed contract count.
    # See ``backend/domain/position_sizing.py`` for ``kelly_fraction``
    # (Kelly 1956) and ``half_kelly``; see ``kelly_replay.py`` for the
    # calibration anchor this diagnostic mirrors.
    kelly_rec = _compute_kelly_recommendation(input_data)
    # ────────────────────────────────────────────────────────────────────

    # ── Kelly reject gate (opt-in) ──────────────────────────────────────────
    # Mirrors the existing 5 risk gates: emits ``None`` on failure with a
    # structured log line. Off by default so every existing caller is
    # bit-for-bit unchanged.
    if kelly_policy is not None and kelly_policy.reject_on_negative_edge:
        kelly_gate = _check_kelly_gate(input_data, kelly_rec, kelly_policy)
        if not kelly_gate["approved"]:
            if kelly_policy.log_rejections:
                logger.info(
                    f"Signal rejected for {input_data.ticker}: "
                    f"{kelly_gate['reason']} "
                    f"(conviction={conviction:.4f})"
                )
            return None
    # ────────────────────────────────────────────────────────────────────

    return TradeIntent(
        ticker=input_data.ticker,
        side=side,
        qty=qty,
        order_type="limit",
        limit_price=input_data.spot_price,
        stop_loss=round(input_data.spot_price * 0.98, 2),  # 2% stop
        take_profit=round(input_data.spot_price * 1.06, 2),  # 6% target (3:1 R:R)
        signal_id=signal_id,
        conviction=round(conviction, 4),
        rationale=rationale,
        kelly=kelly_rec,
    )


# ── Kelly anchor (canonical calibration) ────────────────────────────────────
# Mirrors ``kelly_replay.py:ANCHOR_WIN_PROB`` / ``ANCHOR_PAYOFF`` so the
# live diagnostic and the static replay report agree on the default
# win probability and payoff ratio when the caller doesn't supply them.
KELLY_ANCHOR_WIN_PROB: float = float(ANCHOR_WIN_PROB)
KELLY_ANCHOR_AVG_RR: float = float(ANCHOR_PAYOFF)
# ────────────────────────────────────────────────────────────────────────────


# ── Kelly reject policy ────────────────────────────────────────────────────
# Mirrors the ``SizerConfig`` dataclass-injection convention from
# ``backend/services/risk/sizer.py`` — defaults to OFF so all existing
# callers see zero behaviour change; opt in by passing
# ``kelly_policy=KellyRejectPolicy(reject_on_negative_edge=True)``.
#
# Semantic note: by default we ``ignore_supplied_calibration=True`` —
# once the trader opts in, the Kelly discipline is enforced even for
# user-supplied (p, b). Setting ``ignore_supplied_calibration=False``
# makes supplied calibration bypass the gate (use cautiously).
@dataclass(frozen=True)
class KellyRejectPolicy:
    """Policy for converting ``kelly.would_trade=False`` into a hard gate.

    All fields default to a no-op so unconfigured callers see no change
    in behaviour. Enable by instantiating with at least
    ``reject_on_negative_edge=True``.

    Fields
    ------
    reject_on_negative_edge : bool
        Master switch. When True, signals whose full-Kelly fraction is
        zero (negative edge or zero edge per Kelly 1956) are rejected
        just like a failed risk gate. Default ``False``.
    min_win_prob : float
        Secondary gate: reject if ``kelly.win_prob`` falls below this
        threshold. Default ``0.50`` (the breakeven for ``b=1.0``). Only
        fires when ``reject_on_negative_edge=True``.
    require_supplied_calibration : bool
        If True, signals that did NOT supply BOTH ``kelly_win_prob`` and
        ``kelly_avg_rr`` are rejected with reason
        ``kelly_missing_supplied_calibration``. Useful for forcing
        traders to commit a calibration rather than accept the anchor.
        Default ``False``.
    log_rejections : bool
        Mirror the existing gate logging convention. Default ``True``.
    ignore_supplied_calibration : bool
        If True (default), the gate fires regardless of whether (p, b)
        were supplied — Kelly discipline wins. If False, supplied
        calibration bypasses the gate (their calibration trumps the
        negative-edge check).
    """

    reject_on_negative_edge: bool = False
    min_win_prob: float = 0.50
    require_supplied_calibration: bool = False
    log_rejections: bool = True
    ignore_supplied_calibration: bool = True


# Reason tokens for grep-friendly rejection logging — match the
# existing risk-gate format ("conviction", "equity", "sentiment_z", etc).
KELLY_GATE_REASON_NEGATIVE_EDGE = "kelly_negative_edge"
KELLY_GATE_REASON_LOW_WIN_PROB = "kelly_low_win_prob"
KELLY_GATE_REASON_MISSING_CALIBRATION = "kelly_missing_supplied_calibration"


def _check_kelly_gate(
    input_data: SignalInput,
    kelly: KellyRecommendation,
    policy: KellyRejectPolicy,
) -> dict[str, Any]:
    """Apply the Kelly-reject policy. Returns ``{approved, reason}``.

    Same shape as :func:`_check_gates` so audit loggers that gate on
    ``gate["reason"]`` already work without modification.
    """
    supplied_both = (
        input_data.kelly_win_prob is not None
        and input_data.kelly_avg_rr is not None
    )
    # Supplied calibration overrides the gate when configured to.
    if supplied_both and not policy.ignore_supplied_calibration:
        return {"approved": True, "reason": ""}

    # Require supplied calibration — reject any anchor-fallback signal.
    if policy.require_supplied_calibration and not supplied_both:
        return {
            "approved": False,
            "reason": KELLY_GATE_REASON_MISSING_CALIBRATION,
        }

    # Primary gate: Kelly says don't trade.
    if not kelly.would_trade:
        return {
            "approved": False,
            "reason": (
                f"{KELLY_GATE_REASON_NEGATIVE_EDGE} "
                f"win_prob={kelly.win_prob} "
                f"avg_rr={kelly.avg_rr} "
                f"full_kelly={kelly.full_kelly_fraction}"
            ),
        }

    # Secondary gate: win prob below threshold.
    if kelly.win_prob < policy.min_win_prob:
        return {
            "approved": False,
            "reason": (
                f"{KELLY_GATE_REASON_LOW_WIN_PROB} "
                f"{kelly.win_prob} < {policy.min_win_prob}"
            ),
        }

    return {"approved": True, "reason": ""}


def _compute_kelly_recommendation(input_data: SignalInput) -> KellyRecommendation:
    """Compute the Kelly diagnostic block. Always returns a value.

    Win probability (``p``) and payoff ratio (``b``) resolve in this order:
      1. Both supplied on ``SignalInput`` → use them verbatim.
      2. Exactly one supplied → log a warning, fall back to the anchor.
      3. Neither supplied → use the anchor (``p=0.55, b=1.65``) silently.
    """
    p_supplied = input_data.kelly_win_prob is not None
    b_supplied = input_data.kelly_avg_rr is not None
    if p_supplied != b_supplied:
        # Mirror the delta-aware partial-supply sentinel so a half-set
        # caller's silent fall-through to 0.55/1.65 cannot be mistaken
        # for a deliberate calibration choice.
        logger.warning(
            "translate_signal: Kelly fields partially supplied "
            "(kelly_win_prob=%s, kelly_avg_rr=%s). Falling back to "
            "anchor defaults (p=%.2f, b=%.2f). Pass both together for a "
            "calibration-respecting diagnostic.",
            input_data.kelly_win_prob,
            input_data.kelly_avg_rr,
            KELLY_ANCHOR_WIN_PROB,
            KELLY_ANCHOR_AVG_RR,
        )
    p = float(input_data.kelly_win_prob) if p_supplied else KELLY_ANCHOR_WIN_PROB
    b = float(input_data.kelly_avg_rr) if b_supplied else KELLY_ANCHOR_AVG_RR
    fk = kelly_fraction(p, b)
    hk = half_kelly(p, b)
    notional = input_data.account_equity * hk
    spot = max(input_data.spot_price, 1.0)
    return KellyRecommendation(
        win_prob=round(p, 4),
        avg_rr=round(b, 4),
        full_kelly_fraction=round(fk, 4),
        half_kelly_fraction=round(hk, 4),
        kelly_notional=round(notional, 2),
        qty_kelly_naive=int(notional // spot),
        would_trade=fk > 0.0,
    )


def _check_gates(input_data: SignalInput, conviction: float) -> dict[str, Any]:
    """Check all risk gates. Returns {"approved": bool, "reason": str}."""
    # Gate 1: Conviction
    if conviction < MIN_CONVICTION:
        return {"approved": False, "reason": f"conviction {conviction:.4f} < {MIN_CONVICTION}"}

    # Gate 2: Account equity
    if input_data.account_equity < MIN_ACCOUNT_EQUITY:
        return {"approved": False, "reason": f"equity ${input_data.account_equity:,.0f} < ${MIN_ACCOUNT_EQUITY:,.0f}"}

    # Gate 3: Sentiment
    if input_data.flashalpha_sentiment_z < MIN_SENTIMENT_Z:
        return {"approved": False, "reason": f"sentiment_z {input_data.flashalpha_sentiment_z:.2f} < {MIN_SENTIMENT_Z}"}

    # Gate 4: Open positions
    open_qty = input_data.current_positions.get(input_data.ticker, 0)
    if open_qty >= MAX_OPEN_POSITIONS_PER_TICKER:
        return {"approved": False, "reason": f"open_positions {open_qty} >= {MAX_OPEN_POSITIONS_PER_TICKER}"}

    # Gate 5: Kyle Lambda liquidity
    if input_data.kyle_lambda > KYLE_LAMBDA_ILLIQUID_THRESHOLD:
        return {"approved": False, "reason": f"kyle_lambda {input_data.kyle_lambda:.2e} > {KYLE_LAMBDA_ILLIQUID_THRESHOLD:.2e}"}

    return {"approved": True, "reason": ""}
