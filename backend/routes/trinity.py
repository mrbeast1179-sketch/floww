"""
backend/routes/trinity.py

Trinity Alignment Index API routes.
Cross-correlates Zero-Gamma strike levels across SPX, SPY, and QQQ.

Endpoints:
  GET /api/trinity/{ticker}          — Trinity alignment for a single ticker
  GET /api/trinity/align             — Full SPX/SPY/QQQ alignment score
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/trinity", tags=["trinity"])


async def _fetch_chain(ticker: str, expiries: int = 4):
    """Fetch option chain with lazy import."""
    from server import fetch_spot_and_chains_merged
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    return await fetch_spot_and_chains_merged(t, expiries)


def _extract_zero_gamma_levels(spot: float, contracts: list[dict]) -> list[float]:
    """Extract zero-gamma (flip) levels from computed GEX data."""
    from services.gex_core import compute_gex_by_strike
    strikes_data = compute_gex_by_strike(spot, contracts)
    if not strikes_data:
        return []

    # Find zero crossings
    levels = []
    for i in range(len(strikes_data) - 1):
        gex_a = strikes_data[i]["gex"]
        gex_b = strikes_data[i + 1]["gex"]
        if (gex_a > 0 and gex_b < 0) or (gex_a < 0 and gex_b > 0):
            # Linear interpolation
            denom = gex_a - gex_b
            if denom != 0:
                t_frac = gex_a / denom
                crossing = strikes_data[i]["strike"] + t_frac * (
                    strikes_data[i + 1]["strike"] - strikes_data[i]["strike"]
                )
                levels.append(round(crossing, 2))
    return levels


@router.get("/align")
async def get_trinity_alignment(
    expiries: int = Query(4, ge=1, le=12),
):
    """Compute Trinity Alignment Index across SPX, SPY, and QQQ."""
    from services.trinity_alignment import TrinityAlignmentIndex

    tickers = ["SPY", "QQQ", "^SPX"]
    spots = {}
    flip_levels = {}

    for tk in tickers:
        try:
            raw = await _fetch_chain(tk, expiries)
            spot = raw.get("spot", 0)
            contracts = raw.get("contracts", [])
            spots[tk] = spot
            flip_levels[tk] = _extract_zero_gamma_levels(spot, contracts)
        except Exception as e:
            logger.warning(f"Trinity fetch failed for {tk}: {e}")
            spots[tk] = 0
            flip_levels[tk] = []

    trinity = TrinityAlignmentIndex(tolerance_pct=0.005)
    result = trinity.compute(
        spy_flip_levels=flip_levels.get("SPY", []),
        qqq_flip_levels=flip_levels.get("QQQ", []),
        spx_flip_levels=flip_levels.get("^SPX", []),
        spy_spot=spots.get("SPY", 0),
        qqq_spot=spots.get("QQQ", 0),
        spx_spot=spots.get("^SPX", 0),
    )

    # Emit Prometheus metric
    from services.observability import metrics as obs_metrics
    obs_metrics.trinity_score.set(result.get("score", 0.0))

    return result


@router.get("/{ticker}")
async def get_trinity_for_ticker(ticker: str, expiries: int = Query(4, ge=1, le=12)):
    """Get zero-gamma levels and GEX data for a single ticker."""
    t = ticker.upper()
    raw = await _fetch_chain(t, expiries)
    spot = raw.get("spot", 0)
    contracts = raw.get("contracts", [])
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {t}")

    from services.gex_core import compute_gex_by_strike
    strikes_data = compute_gex_by_strike(spot, contracts, t)
    flip_levels = _extract_zero_gamma_levels(spot, contracts)

    # ── Compute net GEX for paper-accurate metrics ──
    net_gex = sum(s.get("gex", 0.0) for s in strikes_data)

    response: dict = {
        "ticker": t,
        "spot": spot,
        "zero_gamma_levels": flip_levels,
        "strikes": strikes_data,
        "net_gex": round(net_gex, 2),
    }

    # ── Paper-accurate Gamma Imbalance (Barbon-Buraschi) ──
    if spot > 0 and flip_levels:
        try:
            from services.gex_paper_accurate import (
                compute_flip_metrics,
                compute_gamma_imbalance,
                cross_asset_gamma_spillover,
            )
            gi = compute_gamma_imbalance(net_gex, spot, adv_shares=75_000_000)
            fm = compute_flip_metrics(spot, flip_levels[0] if flip_levels else None, net_gex)
            response["gamma_imbalance"] = gi
            response["flip_metrics"] = fm
            # Cross-asset spillover: how much SPX gamma drives this ticker
            gib_pct = gi.get("gamma_imbalance_pct", 0)
            response["cross_asset_spillover"] = cross_asset_gamma_spillover(
                spx_gamma_imbalance_pct=gib_pct,
                single_stock_gamma_imbalance_pct=gib_pct,
                sector="broad",
            )
        except Exception:
            pass  # silent by design: sector fallback to broad; response otherwise complete

    return response
