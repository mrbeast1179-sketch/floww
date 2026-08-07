"""
GEX Analysis API Routes
=======================

Additional endpoints for comprehensive GEX analysis including:
- Term structure across expiries
- VEX computation and GEX+VEX combined
- Liquidity analysis
- Put-call ratio signals

Mounted at /api in server.py
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

        for c in calls:
            c.setdefault("expiry", chosen_expiry)
        for p in puts:
            p.setdefault("expiry", chosen_expiry)

        return spot, calls, puts
    except Exception:
        return None


def _compute_contracts_gex(calls: list, puts: list, spot: float) -> list[dict]:
    """Add gamma and GEX to contracts using Black-Scholes."""
    from bs_greeks import dollar_gex_per_contract, bs_gamma
    
    combined = calls + puts
    
    for c in combined:
        try:
            strike = float(c.get("strike", 0))
            if strike <= 0:
                continue
                
            # Get time to expiry in years
            from datetime import datetime
            dte_days = c.get("dte", c.get("days_to_expiry", 1))
            T = max(float(dte_days), 1) / 365.0  # Avoid T=0
            
            # Get IV
            iv = float(c.get("iv", 0.2))
            if iv <= 0:
                continue
            
            # Get OI or volume
            oi = float(c.get("openInterest", c.get("oi", c.get("volume", 0))))
            
            # Get option type
            opt_type = c.get("type", "CALL").upper()
            if not isinstance(opt_type, str):
                opt_type = "CALL"
            sign = 1.0 if opt_type in ("CALL", "CALLS") else -1.0
            
            # Get time to expiry in years
            dte_days = c.get("dte", c.get("days_to_expiry", c.get("DTE", 1)))
            if dte_days is None or dte_days == 0:
                dte_days = 1
            T = max(float(dte_days), 1) / 365.0  # Avoid T=0
            
            # Get IV - yfinance uses 'impliedVolatility' or 'iv'
            iv = float(c.get("iv", c.get("impliedVolatility", c.get("Implied Volatility", 0.2))))
            if iv <= 0 or iv > 5.0:  # Sanity check IV
                iv = 0.2  # Default fallback
            
            # Get OI - yfinance uses 'openInterest' or 'oi'
            oi = c.get("openInterest", c.get("oi", c.get("Open Interest", 0))) or 0
            oi = float(oi)
            
            # Compute gamma
            gamma = bs_gamma(spot, strike, T, iv, q=0.0, r=0.05)
            
            # Compute GEX
            gex = dollar_gex_per_contract(gamma, oi, spot)
            
            # Compute vomma and vex
            from bs_greeks import bs_vomma, dollar_vex_per_contract
            vomma = bs_vomma(spot, strike, T, iv, q=0.0, r=0.05)
            vex = dollar_vex_per_contract(vomma, oi, spot)
            sign_vex = 1.0 if opt_type in ("CALL", "CALLS") else -1.0
            
            c["gamma"] = gamma
            c["gex"] = sign * gex
            c["vomma"] = vomma
            c["vex"] = sign_vex * vex
            
        except Exception:
            c["gex"] = 0.0
            c["gamma"] = 0.0
    
    return combined


@router.get("/gex/term-structure/{ticker}")
async def get_gex_term_structure(
    ticker: str = Path(..., min_length=1, max_length=10),
):
    """Get GEX term structure across expiries."""
    ticker = ticker.upper()

    try:
        from services.gex_term_structure import compute_gex_term_structure

        result = _get_spot_and_chain(ticker)
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"No options chain data for {ticker}"}
            )

        spot, calls, puts = result
        contracts = _compute_contracts_gex(calls, puts, spot)
        term_result = compute_gex_term_structure(spot, contracts)

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
        from services.gex_paper_accurate import full_paper_diagnostic
        from services.gex_vex_calculator import full_liquidity_analysis

        result = _get_spot_and_chain(ticker)
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"No options chain data for {ticker}"}
            )

        spot, calls, puts = result
        contracts = _compute_contracts_gex(calls, puts, spot)

        # Get ADV proxy
        adv = {
            "SPY": 75_000_000, "SPX": 3_500_000, "QQQ": 45_000_000,
            "IWM": 28_000_000, "DIA": 3_000_000,
        }.get(ticker, 10_000_000)

        # Compute net GEX and VEX
        total_gex = sum(c.get("gex", 0) for c in contracts)
        total_vex = sum(c.get("vex", 0) for c in contracts)

        # Compute flip level
        try:
            from services.gex_core import find_zero_crossings
            flip_levels = find_zero_crossings(spot, contracts)
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
        from services.gex_paper_accurate import compute_flip_metrics

        result = _get_spot_and_chain(ticker)
        if not result:
            return JSONResponse(
                status_code=404,
                content={"error": f"No options chain data for {ticker}"}
            )

        spot, calls, puts = result
        contracts = _compute_contracts_gex(calls, puts, spot)

        from services.gex_core import find_zero_crossings
        flip_levels = find_zero_crossings(spot, contracts)

        net_gex = sum(c.get("gex", 0) for c in contracts)

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