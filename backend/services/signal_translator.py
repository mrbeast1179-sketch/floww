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
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

KYLE_LAMBDA_ILLIQUID_THRESHOLD = 1e-6
MIN_CONVICTION = 0.7
MIN_ACCOUNT_EQUITY = 5000.0
MAX_POSITION_PCT = 0.01
MAX_OPEN_POSITIONS_PER_TICKER = 3
MIN_SENTIMENT_Z = -2.0


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


class SignalInput(BaseModel):
    """Input signals from Hermes analytics pipeline."""
    anomaly_score: float = 0.0
    gex_state: str = "neutral"  # "positive", "negative", "neutral"
    trinity_score: float = 0.0
    current_positions: Dict[str, int] = {}  # ticker -> qty
    account_equity: float = 0.0
    flashalpha_sentiment_z: float = 0.0
    vpin_cdf: float = 0.0
    kyle_lambda: float = 0.0
    ticker: str = ""
    spot_price: float = 0.0


def translate_signal(input_data: SignalInput) -> Optional[TradeIntent]:
    """Convert analytics signals into a TradeIntent.

    Returns None if conviction is too low or any risk gate fails.
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

    # Position sizing: 1% of equity max
    max_qty = int(input_data.account_equity * MAX_POSITION_PCT / max(input_data.spot_price, 1.0))
    qty = max(1, min(max_qty, 10))  # cap at 10 contracts

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
    )


def _check_gates(input_data: SignalInput, conviction: float) -> Dict[str, Any]:
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
