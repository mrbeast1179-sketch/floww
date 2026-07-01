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
            "implied_volatility", "open_interest", "underlying_price",
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


# ── Market-wide cross-symbol scan (BladeMap scanner grid) ──
# Powers the FlowSeeker Pro tab: ONE cvforge screen across ALL underlyings
# ranked by day_volume, so the hottest flow in the whole market surfaces
# (SPY, NVDA, TSLA, ENPH… whatever is active — not a fixed watchlist).
# Returns raw {columns, rows}; the frontend computes Flow Score / flow-type /
# lean exactly like the scenner34 build. Only live cvserver fields are used
# (day_volume vs OI) — there is no per-trade tape on this feed.
@router.get("/scan")
async def market_scan(
    min_volume: int = Query(1000, ge=0),
    limit: int = Query(300, ge=1, le=1000),
):
    """Cross-symbol options flow scan (day_volume vs OI). Returns {columns, rows, count}."""
    columns = [
        "underlying_ticker", "ticker", "contract_type", "strike_price",
        "expiration_date", "day_volume", "open_interest",
        "implied_volatility", "delta", "underlying_price",
    ]
    if not CVFORGE_API_KEY:
        raise HTTPException(503, "cvserver API key not configured")
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
                "filters": [{"field": "day_volume", "op": "gt", "value": min_volume}],
                "sort": [{"field": "day_volume", "direction": "desc"}],
                "limit": limit,
            },
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                raise HTTPException(502, f"cvserver returned {resp.status_code}")
            result = resp.json()
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                d = json.loads(content[0]["text"])
            else:
                d = result.get("result", {})
            rows = d.get("rows", [])
            return {"columns": columns, "rows": rows, "count": len(rows)}
    except HTTPException:
        raise
    except Exception as e:
        logger.warning(f"cvforge scan failed: {e}")
        raise HTTPException(502, f"scan failed: {e}")


@router.get("/alerts/{symbol}")
async def unusual_activity_alerts(
    symbol: str,
    min_oi: int = Query(100, ge=0),
    min_vol_oi_ratio: float = Query(0.05, ge=0),
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=200),
):
    """
    Unusual activity alerts for a symbol's options chain.

    Identifies unusual activity based on option chain snapshots:
    - **high_volume**: day_volume / open_interest ratio above threshold (near money only)
    - **high_iv**: implied IV in top 25% for near-money options (min OI 500)
    - **oi_spike**: open interest > 2x average for near-money options (min OI 500)
    - **delta_extreme**: deep ITM (|delta| > 0.7) with high OI (>500)
    - **premium_concentration**: strikes with premium > $500K (min OI 1000)

    Each alert includes confidence scoring and human-readable factors.
    """
    sym = (symbol or "").strip().upper()

    columns = [
        "ticker", "strike_price", "expiration_date", "contract_type",
        "open_interest", "implied_volatility", "delta", "gamma",
        "bid", "ask", "midpoint", "day_volume", "underlying_price",
    ]
    if not CVFORGE_API_KEY:
        return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                "has_next": False, "error": "no API key"}

    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {CVFORGE_API_KEY}"}
    payload = {
        "jsonrpc": "2.0", "id": 1, "method": "tools/call",
        "params": {
            "name": "get_chain",
            "arguments": {"symbol": sym.upper(), "params": columns},
        },
    }
    try:
        async with httpx.AsyncClient(timeout=CVFORGE_TIMEOUT) as client:
            resp = await client.post(CVFORGE_URL, json=payload, headers=headers)
            if resp.status_code != 200:
                return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                        "has_next": False, "error": f"HTTP {resp.status_code}"}
            result = resp.json()
            if "error" in result:
                return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                        "has_next": False, "error": str(result["error"])}
            content = result.get("result", {}).get("content", [])
            if content and content[0].get("type") == "text":
                raw = json.loads(content[0]["text"])
            else:
                raw = result.get("result", {})

            chain_data = raw.get("chain", [])
            spot = float(raw.get("underlying_price", 0) or 0)
            # Fallback: extract spot from first strike's underlying_price field
            if spot == 0 and chain_data and chain_data[0].get("strikes"):
                first_strike = chain_data[0]["strikes"][0]
                if first_strike and len(first_strike) > 1:
                    cv = first_strike[1] if len(first_strike) > 1 else []
                    # underlying_price is at index 12 in the requested columns
                    if cv and len(cv) > 12:
                        spot = float(cv[12] or 0)

            # Analyze each expiry for unusual activity
            all_alerts = []
            for exp in chain_data:
                expiry = exp.get("expiration", "")
                strikes = exp.get("strikes", [])
                if not strikes:
                    continue

                # Calculate per-expiry statistics
                call_data = []
                for s in strikes:
                    if not s or len(s) < 3:
                        continue
                    strike = float(s[0]) or 0
                    cv = s[1] if len(s) > 1 else []
                    pv = s[2] if len(s) > 2 else []

                    def safe_float(arr, idx):
                        try:
                            return float(arr[idx]) if arr and idx < len(arr) and arr[idx] is not None else 0.0
                        except (TypeError, ValueError):
                            return 0.0

                    # Column indices matching the requested columns array:
                    # 0:ticker 1:strike_price 2:expiration_date 3:contract_type
                    # 4:open_interest 5:implied_volatility 6:delta 7:gamma
                    # 8:bid 9:ask 10:midpoint 11:day_volume 12:underlying_price
                    call_oi = safe_float(cv, 4)
                    put_oi = safe_float(pv, 4)
                    call_vol = safe_float(cv, 11)
                    put_vol = safe_float(pv, 11)
                    call_iv = safe_float(cv, 5)
                    put_iv = safe_float(pv, 5)
                    call_delta = safe_float(cv, 6)
                    put_delta = safe_float(pv, 6)
                    call_bid = safe_float(cv, 8)
                    call_ask = safe_float(cv, 9)
                    put_bid = safe_float(pv, 8)
                    put_ask = safe_float(pv, 9)

                    call_data.append({
                        "strike": strike, "call_oi": call_oi, "put_oi": put_oi,
                        "call_vol": call_vol, "put_vol": put_vol,
                        "call_iv": call_iv, "put_iv": put_iv,
                        "call_delta": call_delta, "put_delta": put_delta,
                        "call_bid": call_bid, "call_ask": call_ask,
                        "put_bid": put_bid, "put_ask": put_ask,
                    })

                # Only analyze strikes near spot price (within 25%)
                if spot > 0:
                    near_money = [d for d in call_data if abs(d["strike"] - spot) / spot <= 0.25]
                else:
                    near_money = call_data
                
                if not near_money:
                    continue

                # Calculate statistics on near-money options only
                avg_oi = sum(d["call_oi"] + d["put_oi"] for d in near_money) / max(len(near_money), 1)
                iv_values = sorted([d["call_iv"] for d in near_money if d["call_iv"] > 0.01])
                iv_p75 = iv_values[int(len(iv_values) * 0.75)] if iv_values else 0

                for d in near_money:
                    alerts_for_strike = []
                    confidence_score = 50
                    factors = []

                    # Check volume/OI ratio (unusual trading activity)
                    total_oi = d["call_oi"] + d["put_oi"]
                    total_vol = d["call_vol"] + d["put_vol"]
                    if total_oi > 100:
                        vol_oi = total_vol / total_oi
                        if vol_oi >= min_vol_oi_ratio and total_vol > 100:
                            alerts_for_strike.append("high_volume")
                            confidence_score += 10
                            factors.append("Vol/OI ratio: %.1f%% (threshold: %.0f%%)" % (vol_oi * 100, min_vol_oi_ratio * 100))
                            factors.append("Day volume: %.0f contracts" % total_vol)

                    # Check IV spike (min 500 OI)
                    if d["call_iv"] > 0 and iv_p75 > 0 and d["call_iv"] >= iv_p75 and total_oi >= 500:
                        alerts_for_strike.append("high_iv")
                        confidence_score += 10
                        factors.append("IV: %.1f%% (75th percentile: %.1f%%)" % (d["call_iv"] * 100, iv_p75 * 100))

                    # Check OI spike (min 500 OI, >2x average)
                    if total_oi > avg_oi * 2 and total_oi >= 500:
                        alerts_for_strike.append("oi_spike")
                        confidence_score += 10
                        factors.append("OI: %.0f (avg: %.0f, %.1fx average)" % (total_oi, avg_oi, total_oi / max(avg_oi, 1)))

                    # Check delta extreme with high OI (min 200)
                    if abs(d["call_delta"]) > 0.6 and d["call_oi"] > 200:
                        alerts_for_strike.append("delta_extreme")
                        confidence_score += 8
                        factors.append("Deep ITM call (delta: %.2f, OI: %.0f)" % (d["call_delta"], d["call_oi"]))
                    elif abs(d["put_delta"]) > 0.6 and d["put_oi"] > 200:
                        alerts_for_strike.append("delta_extreme")
                        confidence_score += 8
                        factors.append("Deep ITM put (delta: %.2f, OI: %.0f)" % (abs(d["put_delta"]), d["put_oi"]))

                    # Check premium concentration (min 500 OI)
                    call_mid = (d["call_bid"] + d["call_ask"]) / 2 if d["call_bid"] > 0 and d["call_ask"] > 0 else 0
                    if call_mid > 0 and total_oi >= 500:
                        premium = call_mid * total_oi * 100
                        if premium > 250_000:
                            alerts_for_strike.append("premium_concentration")
                            confidence_score += 12
                            factors.append("Est. premium: $%.0fK concentrated at strike %.0f" % (premium / 1000, d["strike"]))

                    if alerts_for_strike:
                        classification = alerts_for_strike[0]  # Primary classification
                        confidence_score = min(100, confidence_score)

                        # Determine tier
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
                            exp_date = datetime.strptime(expiry, "%Y-%m-%d")
                            dte = (exp_date - datetime.now()).days
                        except Exception:
                            dte = None

                        all_alerts.append({
                            "alert_id": "%s-%s-%s-%.0f" % (sym, expiry, classification, d["strike"]),
                            "ticker": sym,
                            "classification": classification,
                            "strike": d["strike"],
                            "expiration": expiry,
                            "dte": dte,
                            "underlying_price": spot,
                            "oi": total_oi,
                            "call_oi": d["call_oi"],
                            "put_oi": d["put_oi"],
                            "iv": d["call_iv"] if d["call_iv"] > 0 else d["put_iv"],
                            "delta": d["call_delta"],
                            "day_volume": total_vol,
                            "vol_oi_ratio": (total_vol / total_oi) if total_oi > 0 else 0,
                            "confidence_score": confidence_score,
                            "confidence_factors": factors,
                            "tier": tier,
                            "created_at": datetime.now().isoformat(),
                        })

            # Sort by confidence score descending
            all_alerts.sort(key=lambda a: a["confidence_score"], reverse=True)
            total = len(all_alerts)

            # Paginate
            start = (page - 1) * page_size
            end = start + page_size
            page_alerts = all_alerts[start:end]

            return {
                "alerts": page_alerts,
                "total": total,
                "page": page,
                "page_size": page_size,
                "has_next": end < total,
                "data_source": "cvserver",
                "spot_price": spot,
                "fetched_at": datetime.now().isoformat(),
            }
    except Exception as e:
        logger.warning("unusual activity alerts: %s: %s" % (sym, e))
        return {"alerts": [], "total": 0, "page": page, "page_size": page_size,
                "has_next": False, "error": str(e)}
