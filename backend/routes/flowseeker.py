"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown + chain + screen.
Uses CVForge's cvserver API for real-time options data (32 expirations, 171 strikes).
Falls back to yfinance when CVForge is unavailable.
"""

import asyncio
import json
import logging
import math
import os
import time
from datetime import datetime

import httpx
from fastapi import APIRouter, HTTPException, Query

from services.flowseeker import contract_drilldown, fetch_live_flow

logger = logging.getLogger(__name__)

# ── CVForge cvserver config ──
# Use the remote cvserver endpoint (same as screener project)
CVFORGE_URL = os.environ.get("CVSERVER_URL", "https://tap.convexvalue.com/api/data/mcp")
CVFORGE_API_KEY = os.environ.get("CVSERVER_API_KEY", "")
CVFORGE_TIMEOUT = 15.0  # seconds

# ── Cache ──
_chain_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 120  # 2 minutes


def _safe_float(v):
    if v is None:
        return None
    try:
        f = float(v)
        return None if math.isnan(f) else f
    except (TypeError, ValueError):
        return None


# ── CVForge → frontend format transformation ──

# Frontend expects these params and order:
_FRONTEND_PARAMS = ["strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"]

def _transform_cvforge_response(raw: dict, symbol: str) -> dict:
    """
    Transform CVForge cvserver response to the format the FlowseekerProTab expects.
    CVForge:  params [expiration_date, strike_price, contract_type, iv, delta, gamma, theta, vega,
                       bid, ask, midpoint, open_interest, day_volume, underlying_price]
              strikes [strike, [call_vals(14)], [put_vals(14)]]
    Frontend: params [strike, bid, ask, lastPrice, volume, openInterest, impliedVolatility]
              strikes [strike, [call_vals(7)], [put_vals(7)]]
    """
    cv_params = raw.get("params", [])

    # Build cv_param_name → index mapping
    cv_idx = {name: i for i, name in enumerate(cv_params)}

    # Map frontend field names to CVForge param names and default indices
    # Frontend expects: strike, bid, ask, lastPrice, volume, openInterest, impliedVolatility
    # CVForge has:      strike_price, bid, ask, midpoint(bid+ask)/2, open_interest, implied_volatility
    field_map = {
        "bid": "bid",
        "ask": "ask",
        "lastPrice": "midpoint",  # Use midpoint as last price
        "volume": "day_volume",
        "openInterest": "open_interest",
        "impliedVolatility": "implied_volatility",
    }

    def extract_vals(call_or_put_vals: list) -> list:
        """Extract 7 frontend fields from a 14-element CVForge values array."""
        result = []
        for front_name in _FRONTEND_PARAMS:
            if front_name == "strike":
                continue  # strike is s[0], not in vals
            cv_name = field_map.get(front_name, front_name)
            idx = cv_idx.get(cv_name)
            if idx is not None and idx < len(call_or_put_vals):
                result.append(_safe_float(call_or_put_vals[idx]))
            else:
                result.append(None)
        return result

    transformed_chain = []
    for exp in raw.get("chain", []):
        exp_strikes = []
        for strike_data in exp.get("strikes", []):
            if not strike_data or len(strike_data) < 3:
                continue
            strike_price = strike_data[0]
            call_vals = extract_vals(strike_data[1]) if len(strike_data) > 1 else []
            put_vals = extract_vals(strike_data[2]) if len(strike_data) > 2 else []
            exp_strikes.append([strike_price, call_vals, put_vals])
        transformed_chain.append({
            "expiration": exp.get("expiration", ""),
            "strikes": exp_strikes,
        })

    return {
        "symbol": symbol.upper(),
        "params": _FRONTEND_PARAMS,
        "chain": transformed_chain,
    }


async def _cvforge_chain(symbol: str, fields: list[str] | None = None) -> dict | None:
    """
    Fetch options chain from CVForge's cvserver API via MCP JSON-RPC.
    Transforms response to match frontend's expected format:
      params: ["strike", "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility"]
      strikes: [strike, [call_vals], [put_vals]]
    Returns None on failure (caller should fallback to yfinance).
    """
    if not fields:
        fields = [
            "expiration_date", "strike_price", "contract_type",
            "implied_volatility", "delta", "gamma", "theta", "vega",
            "bid", "ask", "midpoint", "open_interest", "day_volume",
            "underlying_price",
        ]
    if not CVFORGE_API_KEY:
        logger.debug("cvforge: no API key, skipping")
        return None

    # Map yfinance-style index symbols to cvserver format
    _sym_map = {"^SPX": "I:SPX", "^NDX": "I:NDX", "^RUT": "I:RUT", "^VIX": "I:VIX"}
    cv_symbol = _sym_map.get(symbol.upper(), symbol.upper())

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CVFORGE_API_KEY}",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "get_chain",
            "arguments": {
                "symbol": cv_symbol,
                "params": fields,
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                logger.warning(f"cvforge chain: HTTP {resp.status_code} for {symbol}")
                return None
            result = resp.json()
            if "error" in result:
                logger.warning(f"cvforge chain: error for {symbol}: {result['error']}")
                return None
            # Extract text content from MCP response
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                raw = json.loads(content[0]["text"])
            else:
                raw = result.get("result", {})

            # Transform CVForge format → frontend-expected format
            return _transform_cvforge_response(raw, symbol)
    except Exception as e:
        logger.warning(f"cvforge chain: error for {symbol}: {e}")
        return None


def _yfinance_chain_sync(sym: str, fields: list[str]) -> dict:
    """Synchronous yfinance fallback."""
    import yfinance as yf
    t = yf.Ticker(sym)
    exps = list(t.options)[:6]
    if not exps:
        return {"symbol": sym, "params": ["strike"] + fields, "chain": []}
    result = []
    for exp in exps:
        try:
            oc = t.option_chain(exp)
            strikes_out = []
            for _, row in oc.calls.iterrows():
                strike = float(row.get("strike", 0))
                cv, pv = [], []
                for f in fields:
                    v1 = row.get(f)
                    pr = oc.puts[oc.puts["strike"] == strike]
                    v2 = pr.iloc[0].get(f) if len(pr) > 0 else None
                    cv.append(_safe_float(v1))
                    pv.append(_safe_float(v2))
                strikes_out.append([strike, cv, pv])
            result.append({"expiration": exp, "strikes": strikes_out})
        except Exception:
            continue
    return {"symbol": sym, "params": ["strike"] + fields, "chain": result}


# ── Router ──
router = APIRouter(prefix="/api/flowseeker", tags=["flowseeker"])


@router.get("/live")
async def live_flow(
    ticker: str | None = Query(None),
    limit: int = Query(50, ge=1, le=500),
    min_premium: float = Query(0.0, ge=0.0),
):
    """Live institutional options flow with classification."""
    prints = await fetch_live_flow(ticker=ticker, limit=limit, min_premium=min_premium)
    return {
        "ticker": (ticker.strip().upper() if ticker else None),
        "count": len(prints),
        "prints": prints,
    }


@router.get("/drilldown/{symbol}")
async def drilldown(symbol: str):
    """Contract-level drilldown."""
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    return await contract_drilldown(sym)


@router.get("/chain/{symbol}")
async def options_chain(symbol: str):
    """
    Options chain — tries CVForge first (32 exp, 171 strikes), falls back to yfinance.
    Cached for 120s.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    # Cache check
    if sym in _chain_cache:
        ts, data = _chain_cache[sym]
        if time.time() - ts < CACHE_TTL:
            return data

    # Try CVForge first (fast, rich data)
    data = await _cvforge_chain(sym)
    if data and data.get("chain"):
        _chain_cache[sym] = (time.time(), data)
        return data

    # Fallback to yfinance (slow but reliable)
    try:
        loop = asyncio.get_event_loop()
        fields = [
            "bid", "ask", "lastPrice", "volume", "openInterest", "impliedVolatility",
        ]
        data = await asyncio.wait_for(
            loop.run_in_executor(None, _yfinance_chain_sync, sym, fields),
            timeout=60.0,
        )
        _chain_cache[sym] = (time.time(), data)
        return data
    except TimeoutError:
        return {
            "symbol": sym,
            "params": ["strike", "bid", "ask", "lastPrice", "volume", "openInterest"],
            "chain": [],
            "error": "timeout",
        }
    except Exception as e:
        logger.warning(f"flowseeker chain: {sym}: {e}")
        return {"symbol": sym, "params": [], "chain": [], "error": str(e)}


@router.get("/screen")
async def screen_options(
    ticker: str = Query(...),
    min_premium: float = Query(0.0, ge=0.0),
    min_oi: int = Query(0, ge=0),
    option_type: str = Query(None),
    limit: int = Query(50, ge=1, le=500),
):
    """Screen options — uses CVForge screen API if available, else cached chain."""
    sym = (ticker or "").strip().upper()

    # Try CVForge screen API first
    cvforge_data = await _cvforge_screen(sym, min_premium, min_oi, option_type, limit)
    if cvforge_data:
        return cvforge_data

    # Fallback: use cached chain data
    if sym not in _chain_cache:
        await options_chain(sym)

    chain = _chain_cache.get(sym, (0, {})).get("1", {}).get("chain", [])
    contracts = []
    for exp in chain:
        for strike_data in exp.get("strikes", []):
            strike, cv, pv = strike_data[0], strike_data[1] or [], strike_data[2] or []
            for ctype, vals in [("CALL", cv), ("PUT", pv)]:
                prem = (vals[2] or 0) * 100 if len(vals) > 2 else 0
                oi = int(vals[4] or 0) if len(vals) > 4 else 0
                if prem >= min_premium and oi >= min_oi:
                    if not option_type or option_type.upper() == ctype:
                        contracts.append({
                            "ticker": sym, "strike": strike,
                            "expiration": exp.get("expiration", ""),
                            "type": ctype,
                            "bid": vals[0] if len(vals) > 0 else None,
                            "ask": vals[1] if len(vals) > 1 else None,
                            "lastPrice": vals[2] if len(vals) > 2 else None,
                            "volume": int(vals[3] or 0) if len(vals) > 3 else 0,
                            "openInterest": oi,
                            "premium": prem,
                        })

    contracts.sort(key=lambda c: c.get("premium", 0), reverse=True)
    return {"ticker": sym, "count": len(contracts), "results": contracts[:limit]}


async def _cvforge_screen(
    symbol: str,
    min_premium: float,
    min_oi: int,
    option_type: str | None,
    limit: int,
) -> dict | None:
    """Try CVForge screen API. Returns None on failure."""
    columns = [
        "ticker", "strike_price", "expiration_date", "contract_type",
        "trade_size", "trade_price", "open_interest", "implied_volatility",
        "delta", "gamma", "theta", "vega", "bid", "ask",
    ]
    filters = [{"field": "underlying_ticker", "op": "eq", "value": symbol}]
    if not CVFORGE_API_KEY:
        return None
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {CVFORGE_API_KEY}",
    }
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {
            "name": "screen",
            "arguments": {
                "columns": columns,
                "filters": filters,
                "sort": [{"field": "trade_price", "direction": "desc"}],
                "limit": limit,
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                return None
            result = resp.json()
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                import json
                d = json.loads(content[0]["text"])
            else:
                d = result.get("result", {})
            rows = d.get("rows", [])
            return {
                "ticker": symbol,
                "count": len(rows),
                "results": [
                    {
                        "ticker": r[0], "strike": r[1], "expiration": r[2],
                        "type": r[3], "size": r[4], "price": r[5],
                        "oi": r[6], "iv": r[7], "delta": r[8],
                        "gamma": r[9], "theta": r[10], "vega": r[11],
                        "bid": r[12], "ask": r[13],
                    }
                    for r in rows
                ],
            }
    except Exception as e:
        logger.warning(f"cvforge screen: {symbol}: {e}")
    return None


@router.get("/alerts/{symbol}")
async def sweep_alerts(
    symbol: str,
    min_premium: float = Query(50000.0, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    Institutional-grade live whale sweep alerts.

    Returns large options trades classified by:
    - sweep: multi-exchange fast execution, size >= 100
    - block: single large trade, size >= 500
    - unusual: size/OI ratio > 0.5
    - floor: large trade at bid/ask midpoint
    - golden_sweep: sweep + high confidence + directional

    Each alert includes:
    - confidence_score (0-100) with human-readable confidence_factors
    - sentiment (BULLISH/BEARISH/NEUTRAL)
    - direction (directional/ambiguous)
    - spread detection (is_spread, spread_type)
    - tier (1-5, where 1 = highest conviction)
    """
    sym = (symbol or "").strip().upper()

    columns = [
        "ticker", "strike_price", "expiration_date", "contract_type",
        "trade_size", "trade_price", "open_interest", "implied_volatility",
        "delta", "gamma", "theta", "vega", "bid", "ask",
        "trade_conditions", "trade_exchange", "underlying_price",
        "day_volume",
    ]
    filters = [
        {"field": "underlying_ticker", "op": "eq", "value": sym},
    ]
    if not CVFORGE_API_KEY:
        return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                "has_next": False, "provenance": {"source": "none", "error": "no API key"}}

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CVFORGE_API_KEY}"}
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "name": "screen",
            "arguments": {
                "columns": columns, "filters": filters,
                "sort": [{"field": "trade_price", "direction": "desc"}],
                "limit": page_size * page,
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                        "has_next": False, "provenance": {"source": "cvserver", "error": f"HTTP {resp.status_code}"}}
            result = resp.json()
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                d = json.loads(content[0]["text"])
            else:
                d = result.get("result", {})

            rows = d.get("rows", [])
            total = d.get("row_count", len(rows))

            # Paginate
            start = (page - 1) * page_size
            end = start + page_size
            page_rows = rows[start:end]

            alerts = []
            for r in page_rows:
                trade_size = float(r[4] or 0)
                trade_price = float(r[5] or 0)
                oi = float(r[6] or 0)
                iv = float(r[7] or 0)
                delta_val = float(r[8] or 0) if r[8] is not None else None
                gamma_val = float(r[9] or 0) if r[9] is not None else 0
                theta_val = float(r[10] or 0) if r[10] is not None else 0
                vega_val = float(r[11] or 0) if r[11] is not None else 0
                bid = float(r[12] or 0) if r[12] is not None else 0
                ask = float(r[13] or 0) if r[13] is not None else 0
                conditions = r[14] or ""
                exchange = r[15] or ""
                underlying_price = float(r[16] or 0) if r[16] is not None else 0
                day_volume = float(r[17] or 0) if r[17] is not None else 0

                premium = trade_size * trade_price * 100  # 100 shares per contract
                mid_price = (bid + ask) / 2 if bid > 0 and ask > 0 else trade_price

                # Classify the trade
                classification = "regular"
                if trade_size >= 100 and premium >= min_premium:
                    classification = "sweep"
                if trade_size >= 500:
                    classification = "block"
                if oi > 0 and trade_size / oi > 0.5:
                    classification = "unusual"
                if "floor" in conditions.lower() or "mid" in conditions.lower():
                    classification = "floor"
                if trade_size >= 100 and premium >= 100000 and delta_val and abs(delta_val) > 0.5:
                    classification = "golden_sweep"

                # Determine sentiment
                option_type = (r[3] or "").lower()
                if "buy" in conditions.lower() or trade_price >= mid_price:
                    sentiment = "BULLISH" if "call" in option_type else "BEARISH"
                elif "sell" in conditions.lower() or trade_price <= mid_price:
                    sentiment = "BEARISH" if "call" in option_type else "BULLISH"
                else:
                    sentiment = "NEUTRAL"

                # Direction
                if abs(delta_val or 0) > 0.3:
                    direction = "directional"
                else:
                    direction = "ambiguous"

                # Confidence scoring (0-100)
                confidence_score = 50  # baseline
                confidence_factors = []

                if trade_size >= 500:
                    confidence_score += 15
                    confidence_factors.append(f"Block trade: {trade_size:.0f} contracts")
                elif trade_size >= 100:
                    confidence_score += 10
                    confidence_factors.append(f"Sweep: {trade_size:.0f} contracts")

                if premium >= 1000000:
                    confidence_score += 15
                    confidence_factors.append(f"Premium: ${(premium/1e6):.1f}M")
                elif premium >= 100000:
                    confidence_score += 10
                    confidence_factors.append(f"Premium: ${(premium/1e3):.0f}K")

                if oi > 0:
                    vol_oi = trade_size / oi
                    if vol_oi > 0.5:
                        confidence_score += 10
                        confidence_factors.append(f"Vol/OI: {vol_oi:.1f}x (high)")
                    elif vol_oi > 0.1:
                        confidence_score += 5
                        confidence_factors.append(f"Vol/OI: {vol_oi:.1f}x")

                if iv > 0.5:
                    confidence_score += 5
                    confidence_factors.append(f"IV: {iv:.1%} (elevated)")

                if "sweep" in conditions.lower():
                    confidence_score += 10
                    confidence_factors.append("Sweep execution detected")

                if "multi" in exchange.lower() or "," in exchange:
                    confidence_score += 5
                    confidence_factors.append("Multi-exchange execution")

                # Cap confidence
                confidence_score = min(100, max(0, confidence_score))

                # Tier (1 = highest conviction)
                if confidence_score >= 80:
                    tier = 1
                elif confidence_score >= 65:
                    tier = 2
                elif confidence_score >= 50:
                    tier = 3
                elif confidence_score >= 35:
                    tier = 4
                else:
                    tier = 5

                # DTE calculation
                try:
                    exp_date = datetime.strptime(r[2], "%Y-%m-%d")
                    dte = (exp_date - datetime.now()).days
                except Exception:
                    dte = None

                alerts.append({
                    "alert_id": f"{sym}-{r[0]}-{r[2]}-{r[1]}",
                    "ticker": sym,
                    "option_ticker": r[0],
                    "option_type": r[3],
                    "strike": float(r[1] or 0),
                    "expiration": r[2],
                    "dte": dte,
                    "premium": premium,
                    "size": trade_size,
                    "price": trade_price,
                    "bid": bid,
                    "ask": ask,
                    "mid_price": mid_price,
                    "oi": oi,
                    "iv": iv,
                    "delta": delta_val,
                    "gamma": gamma_val,
                    "theta": theta_val,
                    "vega": vega_val,
                    "underlying_price": underlying_price,
                    "day_volume": day_volume,
                    "conditions": conditions,
                    "exchange": exchange,
                    "classification": classification,
                    "sentiment": sentiment,
                    "direction": direction,
                    "confidence": "HIGH" if confidence_score >= 70 else "MEDIUM" if confidence_score >= 40 else "LOW",
                    "confidence_score": confidence_score,
                    "confidence_factors": confidence_factors,
                    "tier": tier,
                    "pct_otm": abs((float(r[1] or 0) - underlying_price) / underlying_price * 100) if underlying_price > 0 else None,
                    "vol_oi_ratio": trade_size / oi if oi > 0 else None,
                    "created_at": datetime.now().isoformat(),
                })

            return {
                "alerts": alerts,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_next": end < total,
                "provenance": {
                    "source": "cvserver",
                    "fetched_at": datetime.now().isoformat(),
                    "is_market_hours": True,
                    "data_kind": "real",
                },
            }
    except Exception as e:
        logger.warning(f"sweep alerts: {sym}: {e}")
        return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                "has_next": False, "provenance": {"source": "cvserver", "error": str(e)}}
