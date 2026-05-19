"""
backend/routes/heatseeker.py

API routes for Skylit-parity Heatseeker.
    Wave 1: flip zones, node lifecycle, air pockets.
    Wave 2: beach ball, reverse rug, rainbow road, velocity mode, trinity.

Routes fetch the option chain and pass it into the pure functions in
`services.heatseeker`. Mongo-backed history endpoints fall back to empty
input on failure — the pure functions tolerate that.
"""

import logging
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query

from services.heatseeker import (
    _gex_per_strike,
    _king_node_strike,
    calc_air_pockets,
    calc_flip_zones,
    calc_node_lifecycle,
    calc_trinity_confluence,
    calc_velocity_mode,
    detect_beach_ball,
    detect_rainbow_road,
    detect_reverse_rug,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/heatseeker", tags=["heatseeker"])


async def _fetch_chain(ticker: str, expiries: int) -> Dict[str, Any]:
    """
    Resolve the option chain for ``ticker`` using the same fetcher the rest
    of server.py uses. Imported lazily so the routes module remains import-
    safe before ``app`` is constructed.
    """
    # Local import so the routes module doesn't trigger heavy server.py
    # initialization at import time.
    from server import fetch_spot_and_chains_merged, _sanitize  # noqa: F401
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"
    raw = await fetch_spot_and_chains_merged(t, expiries)
    return raw


async def _fetch_history(ticker: str) -> List[Dict[str, Any]]:
    """
    Fetch the last 24h of spot snapshots for ``ticker`` from the snapshots
    collection. Wave 1 returns an empty list if Mongo isn't available — the
    pure function treats this as "all nodes fresh".
    """
    try:
        from server import db
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        cursor = db.snapshots.find(
            {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
            {"spot": 1, "ts": 1, "_id": 0},
        ).sort("ts", 1)
        history: List[Dict[str, Any]] = []
        async for doc in cursor:
            spot = doc.get("spot")
            if spot is None:
                continue
            ts = doc.get("ts")
            history.append({
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "spot": float(spot),
            })
        return history
    except Exception as e:
        logger.warning(f"heatseeker history fetch fail for {ticker}: {e}")
        return []


@router.get("/flip-zones")
async def flip_zones_route(
    ticker: str = "SPY",
    window_pct: float = Query(0.05, gt=0.0, le=0.5),
    expiries: int = Query(4, ge=1, le=12),
):
    """All cumulative-GEX sign changes within ±window_pct of spot."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_flip_zones(spot, contracts, window_pct=window_pct)
    return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})


@router.get("/node-lifecycle")
async def node_lifecycle_route(
    ticker: str = "SPY",
    expiries: int = Query(4, ge=1, le=12),
):
    """Top 10 |GEX| nodes classified Fresh/Tested/Delivered/Decaying."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    history = await _fetch_history(ticker.upper())
    result = calc_node_lifecycle(spot, contracts, history)
    return _sanitize({
        "ticker": ticker.upper(),
        "spot": spot,
        "history_points": len(history),
        **result,
    })


@router.get("/air-pockets")
async def air_pockets_route(
    ticker: str = "SPY",
    min_gap_pct: float = Query(0.005, gt=0.0, le=0.5),
    expiries: int = Query(4, ge=1, le=12),
):
    """Contiguous strike ranges with |GEX| below 20% of the local median."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    result = calc_air_pockets(spot, contracts, min_gap_pct=min_gap_pct)
    return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})


# ---------------------------------------------------------------------------
# Wave 2 helpers
# ---------------------------------------------------------------------------

async def _fetch_king_node_history(ticker: str) -> List[Dict[str, Any]]:
    """
    Build a king-node history for ``ticker``. Each entry is
    ``{"timestamp": iso8601, "king_node_strike": float, "spot": float}``.

    Strategy: query last 30 minutes of spot snapshots from ``db.snapshots``.
    If a snapshot has a stored ``king_node_strike``, use it; otherwise leave
    the history empty (the pure function returns calm/0 in that case). On
    any Mongo failure, return an empty list so the route still returns a
    well-formed payload.
    """
    try:
        from server import db
        from datetime import datetime, timedelta, timezone

        cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
        cursor = db.snapshots.find(
            {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
            {"spot": 1, "ts": 1, "king_node_strike": 1, "_id": 0},
        ).sort("ts", 1)
        history: List[Dict[str, Any]] = []
        async for doc in cursor:
            kn = doc.get("king_node_strike")
            if kn is None:
                continue
            ts = doc.get("ts")
            try:
                spot = float(doc.get("spot") or 0)
                king = float(kn)
            except (TypeError, ValueError):
                continue
            history.append({
                "timestamp": ts.isoformat() if hasattr(ts, "isoformat") else str(ts),
                "king_node_strike": king,
                "spot": spot,
            })
        return history
    except Exception as e:
        logger.warning(f"heatseeker king-node history fetch fail for {ticker}: {e}")
        return []


async def _trinity_snapshot(ticker: str, expiries: int) -> Dict[str, Any]:
    """
    Resolve a single trinity-confluence snapshot for ``ticker``.

    Returns the four-field dict expected by ``calc_trinity_confluence``:
        ``gex_regime``, ``spot``, ``gamma_flip``, ``trend_direction``.

    On any failure, returns a fully-missing snapshot so the trinity score
    treats this index as a divergence rather than crashing.
    """
    missing = {
        "gex_regime": "missing",
        "spot": None,
        "gamma_flip": None,
        "trend_direction": "missing",
    }
    try:
        raw = await _fetch_chain(ticker, expiries)
        spot = raw.get("spot")
        contracts = raw.get("contracts") or []
        if not spot or not contracts:
            return missing

        # gex_regime: net signed GEX summed across all strikes.
        gex_map = _gex_per_strike(spot, contracts)
        net = sum(gex_map.values())
        if net > 0:
            regime = "positive"
        elif net < 0:
            regime = "negative"
        else:
            regime = "neutral"

        # gamma_flip: re-use advanced_analytics' calc_gamma_flip_levels.
        gamma_flip: Optional[float] = None
        try:
            from advanced_analytics import calc_gamma_flip_levels
            flips = calc_gamma_flip_levels(spot, contracts)
            if isinstance(flips, dict):
                gf = flips.get("primary_flip") or flips.get("gamma_flip")
                if gf is not None:
                    gamma_flip = float(gf)
        except Exception as e:
            logger.debug(f"trinity gamma_flip fetch fail for {ticker}: {e}")

        # trend_direction: compare current spot to spot 30 minutes ago.
        trend: str = "missing"
        try:
            from server import db
            from datetime import datetime, timedelta, timezone

            cutoff = datetime.now(timezone.utc) - timedelta(minutes=30)
            doc = await db.snapshots.find_one(
                {"ticker": ticker.upper(), "ts": {"$gte": cutoff}},
                sort=[("ts", 1)],
            )
            if doc and doc.get("spot"):
                old = float(doc["spot"])
                if old > 0:
                    pct = (float(spot) - old) / old
                    if pct > 0.001:
                        trend = "up"
                    elif pct < -0.001:
                        trend = "down"
                    else:
                        trend = "flat"
        except Exception as e:
            logger.debug(f"trinity trend fetch fail for {ticker}: {e}")

        return {
            "gex_regime": regime,
            "spot": float(spot),
            "gamma_flip": gamma_flip,
            "trend_direction": trend,
        }
    except Exception as e:
        logger.warning(f"trinity snapshot fail for {ticker}: {e}")
        return missing


# ---------------------------------------------------------------------------
# Wave 2 routes
# ---------------------------------------------------------------------------

@router.get("/beach-ball")
async def beach_ball_route(
    ticker: str = "SPY",
    expiries: int = Query(4, ge=1, le=12),
):
    """Beach Ball: spot stretched past the King Node (overshoot/reversion)."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    result = detect_beach_ball(spot, contracts)
    return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})


@router.get("/reverse-rug")
async def reverse_rug_route(
    ticker: str = "SPY",
    expiries: int = Query(4, ge=1, le=12),
):
    """Reverse Rug: positive floor below + negative ceiling above."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    result = detect_reverse_rug(spot, contracts)
    return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})


@router.get("/rainbow-road")
async def rainbow_road_route(
    ticker: str = "SPY",
    max_dominant_share: float = Query(0.15, gt=0.0, le=1.0),
    expiries: int = Query(4, ge=1, le=12),
):
    """Rainbow Road: no dominant structure — chaos, sit out."""
    from server import _sanitize
    raw = await _fetch_chain(ticker, expiries)
    spot = raw.get("spot")
    contracts = raw.get("contracts") or []
    if not spot or not contracts:
        raise HTTPException(404, f"No options data for {ticker}")
    result = detect_rainbow_road(spot, contracts, max_dominant_share=max_dominant_share)
    return _sanitize({"ticker": ticker.upper(), "spot": spot, **result})


@router.get("/velocity-mode")
async def velocity_mode_route(ticker: str = "SPY"):
    """
    Velocity Mode: rate of King Node drift over the last ~30 minutes.

    History comes from Mongo ``db.snapshots`` (entries with a stored
    ``king_node_strike``). If Mongo is unavailable or no usable rows exist,
    the pure function returns ``velocity=0, mode="calm", n_snapshots=0`` —
    matching Wave 1's node-lifecycle fallback shape.
    """
    from server import _sanitize
    history = await _fetch_king_node_history(ticker.upper())
    result = calc_velocity_mode(history)
    return _sanitize({"ticker": ticker.upper(), **result})


@router.get("/trinity-confluence")
async def trinity_confluence_route(
    expiries: int = Query(4, ge=1, le=12),
):
    """
    Trinity Confluence: SPX/SPY/QQQ alignment, 0–100.

    Always queries the three tickers; if any individual snapshot fails to
    load, that dimension is recorded as ``"missing"`` rather than crashing
    the request.
    """
    from server import _sanitize
    spx = await _trinity_snapshot("SPX", expiries)
    spy = await _trinity_snapshot("SPY", expiries)
    qqq = await _trinity_snapshot("QQQ", expiries)
    result = calc_trinity_confluence(spx, spy, qqq)
    return _sanitize({
        "snapshots": {"SPX": spx, "SPY": spy, "QQQ": qqq},
        **result,
    })
