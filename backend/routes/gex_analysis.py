"""
GEX Analysis API Routes
=======================

Additional endpoints for comprehensive GEX analysis including:
- Term structure across expiries
- VEX computation and GEX+VEX combined
- Liquidity analysis
- Put-call ratio signals
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Path
from fastapi.responses import JSONResponse

router = APIRouter()


def _get_spot_and_chain(ticker: str) -> tuple[float, list[dict], list[dict]] | None:
    """Fetch spot price and options chain via yfinance."""
    try:
        import yfinance as yf
        from datetime import datetime, date

        yt = yf.Ticker(ticker.upper())
        hist = yt.history(period="5d")
        if hist is None or len(hist) == 0:
            return None

        spot = float(hist["Close"].iloc[-1])
        expiry_attr = getattr(yt, "options", None) or []
        if not expiry_attr:
            return None

        chosen_expiry = str(expiry_attr[0])
        chain = yt.option_chain(chosen_expiry)

        calls = (
            chain.calls.fillna(0).to_dict(orient="records")
            if chain.calls is not None
            else []
        )
        puts = (
            chain.puts.fillna(0).to_dict(orient="records")
            if chain.puts is not None
            else []
        )

        # Compute DTE from the chosen expiry
        try:
            expiry_date = datetime.strptime(chosen_expiry, "%Y-%m-%d").date()
            dte_days = max((expiry_date - date.today()).days, 1)
        except Exception:
            dte_days = 1

        for c in calls:
            c.setdefault("expiry", chosen_expiry)
            c["type"] = "call"
            c["dte"] = dte_days
        for p in puts:
            p.setdefault("expiry", chosen_expiry)
            p["type"] = "put"
            p["dte"] = dte_days

        return spot, calls, puts
    except Exception:
        return None


def _normalize_contracts(calls: list, puts: list) -> list[dict]:
    """Normalize yfinance contract dicts to GEX computation format."""
    combined = calls + puts
    normalized = []

    for c in combined:
        nc = dict(c)
        nc["type"] = "call" if c.get("type", "CALL").upper() in ("CALL", "CALLS") else "put"
        nc["strike"] = float(nc.get("strike", 0))
        nc["iv"] = float(nc.get("iv", nc.get("impliedVolatility", 0.2)))
        if nc["iv"] <= 0:
            nc["iv"] = 0.2
        nc["oi"] = float(nc.get("openInterest", nc.get("oi", nc.get("volume", 0)) or 0))

        dte_days = nc.get("dte", 1)
        if dte_days is None or dte_days == 0:
            dte_days = 1
        nc["T"] = max(float(dte_days), 1) / 365.0

        normalized.append(nc)

    return normalized


@router.get("/gex/term-structure/{ticker}")
async def get_gex_term_structure(
    ticker: str = Path(..., min_length=1, max_length=10),
):
    """Get GEX term structure across expiries."""
    ticker = ticker.upper()

    try:
        from services.gex_term_structure import compute_gex_term_structure
        from services.gex_core import compute_gex_by_strike

        result = _get_spot_and_chain(ticker)
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"No options chain data for {ticker}"}
            )

        spot, calls, puts = result
        contracts = _normalize_contracts(calls, puts)
        gex_by_strike = compute_gex_by_strike(spot, contracts)
        term_result = compute_gex_term_structure(spot, gex_by_strike)

        return JSONResponse(content=term_result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/gex/liquidity/{ticker}")
async def get_gex_liquidity_analysis(
    ticker: str = Path(..., min_length=1, max_length=10),
):
    """Get comprehensive GEX+VEX liquidity analysis."""
    ticker = ticker.upper()

    try:
        from services.gex_paper_accurate import DEFAULT_ADV_SHARES, full_paper_diagnostic
        from services.gex_vex_calculator import full_liquidity_analysis
        from services.gex_core import compute_gex_by_strike

        result = _get_spot_and_chain(ticker)
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"No options chain data for {ticker}"}
            )

        spot, calls, puts = result
        contracts = _normalize_contracts(calls, puts)
        gex_by_strike = compute_gex_by_strike(spot, contracts)

        # Get ADV proxy
        adv = {
            "SPY": 75_000_000, "SPX": 3_500_000, "QQQ": 45_000_000,
            "IWM": 28_000_000, "DIA": 3_000_000,
        }.get(ticker, DEFAULT_ADV_SHARES)

        # Compute net GEX and VEX
        total_gex = sum(c.get("gex", 0) for c in gex_by_strike)
        total_vex = sum(c.get("vex", 0) for c in gex_by_strike)

        # Compute flip level
        try:
            from services.gex_core import find_zero_crossings
            flip_levels = find_zero_crossings(spot, gex_by_strike)
            flip_level = flip_levels[0] if flip_levels else None
        except Exception:
            flip_level = None

        # Full analysis
        result = full_liquidity_analysis(total_gex, total_vex, spot, adv)
        result["spot"] = spot
        result["gamma_imbalance"] = full_paper_diagnostic(
            total_gex, spot, adv, flip_level
        ).get("paper_metrics", {}).get("gamma_imbalance", {})

        return JSONResponse(content=result)

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )


@router.get("/gex/flow-analysis/{ticker}")
async def get_flow_analysis(ticker: str = Path(..., min_length=1, max_length=10)):
    """Analyze options flow direction."""
    ticker = ticker.upper()

    return JSONResponse(content={
        "ticker": ticker,
        "flow_analysis": "See /api/steal-three/level for detailed flow analytics",
        "note": "Full flow analysis requires transaction-level data"
    })


@router.get("/gex/flippoints/{ticker}")
async def get_flip_points(ticker: str = Path(..., min_length=1, max_length=10)):
    """Get zero-gamma flip points with regime analysis."""
    ticker = ticker.upper()

    try:
        from services.gex_paper_accurate import DEFAULT_ADV_SHARES, compute_flip_metrics
        from services.gex_core import compute_gex_by_strike, find_zero_crossings

        result = _get_spot_and_chain(ticker)
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"No options chain data for {ticker}"}
            )

        spot, calls, puts = result
        contracts = _normalize_contracts(calls, puts)
        gex_by_strike = compute_gex_by_strike(spot, contracts)
        flip_levels = find_zero_crossings(spot, gex_by_strike)

        net_gex = sum(c.get("gex", 0) for c in gex_by_strike)

        flip_metrics = {}
        if flip_levels:
            flip_metrics = compute_flip_metrics(spot, flip_levels[0], net_gex)

        return JSONResponse(content={
            "ticker": ticker,
            "spot": spot,
            "flip_levels": flip_levels,
            "flip_metrics": flip_metrics,
            "net_gex": net_gex,
        })

    except Exception as e:
        return JSONResponse(
            status_code=500,
            content={"error": str(e)}
        )