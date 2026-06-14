"""
backend/routes/position_sizing_api.py

REST API for Kelly Criterion position sizing.

GET /api/position-sizing?account=100000&win_rate=0.55&payoff=1.8&kelly_fraction=0.5

Returns JSON with kelly_fraction, dollar_allocation, max_contracts, and flags.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/api/position-sizing")
async def position_sizing(
    account: float = Query(..., gt=0, description="Account size in dollars"),
    win_rate: float = Query(..., ge=0.0, le=1.0, description="Win rate [0, 1]"),
    payoff: float = Query(..., gt=0.0, description="Payoff ratio (avg win / avg loss)"),
    kelly_fraction: float = Query(0.5, gt=0.0, le=1.0, description="Fractional Kelly multiplier"),
    contract_value: float = Query(1.0, gt=0.0, description="Notional value per contract"),
):
    """Calculate optimal position size using fractional Kelly criterion.

    Query parameters:
        account:        Total account equity (> 0)
        win_rate:       Historical win rate, 0.0 to 1.0
        payoff:         Average win divided by average loss (> 0)
        kelly_fraction: Kelly fraction multiplier, default 0.5 (half-Kelly)
        contract_value: Dollar value per contract for max_contracts calc

    Returns JSON:
        kelly_fraction:     Raw Kelly fraction (before fractional scaling)
        adjusted_fraction:  After Kelly multiplier (before clamp)
        kelly_pct:          Final % of account to allocate (clamped to 0.25)
        dollar_allocation:  Dollar amount to allocate
        max_contracts:      Maximum whole contracts
        capped:             Whether the raw value exceeded the 25% cap
    """
    from services.position_sizing import size_position

    try:
        result = size_position(
            account_size=account,
            win_rate=win_rate,
            payoff_ratio=payoff,
            kelly_fraction=kelly_fraction,
            contract_value=contract_value,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    return {
        "kelly_fraction": round(result.kelly_fraction, 6),
        "adjusted_fraction": round(result.adjusted_fraction, 6),
        "kelly_pct": round(result.kelly_pct, 6),
        "dollar_allocation": result.dollar_allocation,
        "max_contracts": result.max_contracts,
        "win_rate": result.win_rate,
        "payoff_ratio": result.payoff_ratio,
        "kelly_multiplier": result.kelly_multiplier,
        "account_size": result.account_size,
        "capped": result.capped,
    }
