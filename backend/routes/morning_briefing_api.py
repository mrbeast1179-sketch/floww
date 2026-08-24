"""
backend/routes/morning_briefing_api.py

Morning Briefing API routes.

GET /api/briefing/{ticker}  →  returns {regime, narrative, timestamp, metrics}
GET /api/briefing/{ticker}/html  →  returns HTML rendering

Note: This router is mounted at prefix="/api" in server.py,
so routes here should NOT include the /api prefix. I-7 fix.
"""

from __future__ import annotations

import logging
import time
from typing import Any

from fastapi import APIRouter, HTTPException, Path
from fastapi.responses import HTMLResponse, JSONResponse

logger = logging.getLogger(__name__)

router = APIRouter()

# 15-minute cache: {ticker: (timestamp, result)}
_briefing_cache: dict[str, dict[str, Any]] = {}
_CACHE_TTL_SECONDS = 900  # 15 minutes


def _get_cached(ticker: str) -> dict[str, Any] | None:
    """Return cached briefing if fresh, else None."""
    entry = _briefing_cache.get(ticker.upper())
    if entry is None:
        return None
    age = time.monotonic() - entry["_cached_at"]
    if age > _CACHE_TTL_SECONDS:
        return None
    return entry


def _set_cached(ticker: str, result: dict[str, Any]) -> None:
    """Cache a briefing result with timestamp."""
    entry = dict(result)
    entry["_cached_at"] = time.monotonic()
    _briefing_cache[ticker.upper()] = entry


def _strip_cache_metadata(result: dict[str, Any]) -> dict[str, Any]:
    """Remove internal cache fields from response."""
    return {k: v for k, v in result.items() if not k.startswith("_")}


@router.get("/briefing/{ticker}")
async def get_briefing(
    ticker: str = Path(..., min_length=1, max_length=10),
):
    """
    Generate a morning briefing for the given ticker.

    Returns JSON with regime, narrative, timestamp, and supporting metrics.
    Results are cached for 15 minutes per ticker.
    """
    ticker = ticker.upper().strip()

    # Check cache
    cached = _get_cached(ticker)
    if cached is not None:
        return JSONResponse(content=_strip_cache_metadata(cached))

    # Build briefing
    try:
        from services.morning_briefing import BriefingResult, build_briefing

        # Try to get top movers and spot from server's cache
        top_movers = []
        spot = 0.0
        chain_contracts = None
        try:
            import server as srv
            if hasattr(srv, "_movers_cache") and srv._movers_cache.get("data"):
                top_movers = sorted(
                    srv._movers_cache["data"],
                    key=lambda r: abs(r.get("pct", 0)),
                    reverse=True,
                )[:5]
            # Fetch spot and chain data via the server's chain loader
            from server import fetch_spot_and_chains_merged
            raw = await fetch_spot_and_chains_merged(ticker, max_expiries=4)
            if raw:
                spot = float(raw.get("spot", 0.0) or 0.0)
                # Normalize contracts: convert date-string expiry to year-fraction T
                from datetime import date, datetime
                today = date.today()
                normalized = []
                for c in raw.get("contracts", []):
                    nc = dict(c)
                    # Convert expiry date string to T (years)
                    expiry = nc.get("expiry") or nc.get("expiration")
                    if expiry:
                        if isinstance(expiry, str):
                            try:
                                exp_date = datetime.strptime(expiry, "%Y-%m-%d").date()
                                dte_days = max((exp_date - today).days, 1)
                            except (ValueError, TypeError):
                                dte_days = 1
                            nc["expiry"] = max(float(dte_days), 1) / 365.0
                        elif isinstance(expiry, (int, float)):
                            nc["expiry"] = max(float(expiry), 1) / 365.0
                    normalized.append(nc)
                chain_contracts = normalized

                # Gamma backfill: cvserver chain rows often arrive without
                # gamma. GexAggregator treats missing gamma as 0 → net_gex 0
                # and every paper metric empty. Compute gamma via the Rust
                # solver (bs path) from IV when absent — same as the grid
                # pipeline does.
                missing = [c for c in normalized if not c.get("gamma")]
                if missing:
                    from bs_greeks import bs_gamma as _bsg
                    for c in missing:
                        try:
                            iv = float(c.get("iv") or 0)
                            t = float(c.get("expiry") or c.get("T") or 0)
                            k = float(c.get("strike") or 0)
                            if iv > 0 and t > 0 and k > 0 and spot > 0:
                                c["gamma"] = _bsg(spot, k, t, iv, q=0.013)
                        except Exception:
                            continue
                    logger.info(
                        f"briefing: backfilled gamma for {len(missing)}/{len(normalized)} contracts"
                    )
        except Exception:
            logger.debug(f"Chain fetch failed for {ticker}, will use fallback")

        # Fallback: if we have spot but no chain, try server's live GEX cache
        if spot > 0 and chain_contracts is None:
            try:
                import server as srv_fb
                if hasattr(srv_fb, "_gex_cache") and ticker in srv_fb._gex_cache:
                    cached_gex = srv_fb._gex_cache[ticker]
                    if cached_gex and cached_gex.get("contracts"):
                        chain_contracts = cached_gex.get("contracts")
                        logger.debug(f"Using cached GEX contracts for {ticker}")
            except Exception:
                pass

        result: BriefingResult = await build_briefing(
            ticker=ticker,
            top_movers=top_movers,
            spot=spot,
            chain_contracts=chain_contracts,
        )

        response = {
            "ticker": result.ticker,
            "regime": result.regime,
            "narrative": result.narrative,
            "timestamp": result.timestamp,
            "metrics": result.metrics,
        }

        # Cache the result
        _set_cached(ticker, response)

        return JSONResponse(content=_strip_cache_metadata(response))

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Briefing generation failed for {ticker}: {str(e)}",
        ) from e


@router.get("/briefing/{ticker}/html", response_class=HTMLResponse)
async def get_briefing_html(
    ticker: str = Path(..., min_length=1, max_length=10),
):
    """Return the briefing as a simple HTML page for quick viewing."""
    ticker = ticker.upper().strip()

    # Use the JSON endpoint logic
    cached = _get_cached(ticker)
    if cached is None:
        try:
            from services.morning_briefing import build_briefing

            result = await build_briefing(ticker=ticker)
            response = {
                "ticker": result.ticker,
                "regime": result.regime,
                "narrative": result.narrative,
                "timestamp": result.timestamp,
                "metrics": result.metrics,
            }
            _set_cached(ticker, response)
            cached = _strip_cache_metadata(response)
        except Exception as e:
            return HTMLResponse(
                content=f"<html><body><h1>Error</h1><p>{e}</p></body></html>",
                status_code=500,
            )
    else:
        cached = _strip_cache_metadata(cached)

    regime = cached.get("regime", "UNKNOWN")
    narrative = cached.get("narrative", "No narrative available.")
    _metrics = cached.get("metrics", {})
    timestamp = cached.get("timestamp", "")

    regime_color = {
        "BULLISH": "#22c55e",
        "BEARISH": "#ef4444",
        "NEUTRAL": "#f59e0b",
        "UNKNOWN": "#6b7280",
    }.get(regime, "#6b7280")

    html = f"""<!DOCTYPE html>
<html><head><title>{ticker} Briefing</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 600px; margin: 40px auto; padding: 0 20px; background: #0f172a; color: #e2e8f0; }}
.card {{ background: #1e293b; border-radius: 12px; padding: 24px; border: 1px solid #334155; }}
.regime {{ color: {regime_color}; font-size: 14px; font-weight: 700; letter-spacing: 0.05em; text-transform: uppercase; }}
.narrative {{ font-size: 16px; line-height: 1.6; margin: 16px 0; }}
.metrics {{ font-size: 12px; color: #94a3b8; margin-top: 20px; border-top: 1px solid #334155; padding-top: 12px; }}
</style></head><body>
<div class="card">
  <div class="regime">{regime} — {ticker}</div>
  <div class="narrative">{narrative}</div>
  <div class="metrics">Generated: {timestamp}</div>
</div></body></html>"""

    return HTMLResponse(content=html)
