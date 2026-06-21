"""
backend/routes/flowseeker.py

API routes for Skylit-parity Flowseeker — live options flow + drilldown.

Mirrors backend/routes/heatseeker.py's pattern: thin wrappers around
services/flowseeker.py with no business logic in the routes themselves.
Failures from the upstream provider degrade to 200 with empty payloads so
the frontend can render an empty state instead of crashing.
"""

import logging

from fastapi import APIRouter, HTTPException, Query

from services.flowseeker import contract_drilldown, fetch_live_flow

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/flowseeker", tags=["flowseeker"])


@router.get("/live")
async def live_flow(
    ticker: str | None = Query(None, description="Optional ticker; omit for cross-ticker outliers"),
    limit: int = Query(50, ge=1, le=500),
    min_premium: float = Query(0.0, ge=0.0),
):
    """
    Live institutional options flow with 20-column shape and Skylit-parity
    classification (sweep / block / unusual / regular).

    Returns ``{"ticker": str|None, "count": int, "prints": List[Dict]}``.
    """
    prints = await fetch_live_flow(ticker=ticker, limit=limit, min_premium=min_premium)
    return {
        "ticker": (ticker.strip().upper() if ticker else None),
        "count": len(prints),
        "prints": prints,
    }


@router.get("/drilldown/{symbol}")
async def drilldown(symbol: str):
    """
    Contract-level drilldown: chain volume, OI, chain ratio, recent prints,
    and 20-day vol/OI history (when the upstream tier exposes it).
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")
    return await contract_drilldown(sym)


@router.get("/chain/{symbol}")
async def options_chain(
    symbol: str,
    fields: str | None = Query(None, description="Comma-separated list of fields to include"),
):
    """
    Return options chain for a symbol.

    Fields is a comma-separated list of requested fields (e.g. "delta,gamma,oi,volume").
    Returns a well-formed structure the frontend can render even when the upstream
    provider is unavailable.
    """
    sym = (symbol or "").strip().upper()
    if not sym:
        raise HTTPException(400, "symbol required")

    # Parse requested fields
    requested_fields: list[str] = []
    if fields:
        requested_fields = [f.strip().lower() for f in fields.split(",") if f.strip()]

    try:
        from services.flowseeker import _get_client

        client = _get_client()
        chain_payload = await client.get_options_chain(sym)
    except Exception as e:
        logger.warning(f"flowseeker chain: provider error for {sym}: {e}")
        chain_payload = None

    # Normalize the chain into a standard structure
    empty_response = {
        "symbol": sym,
        "params": requested_fields,
        "chain": [],
    }

    if chain_payload is None:
        return empty_response

    # Try to extract strikes/expirations from various upstream shapes
    chain_out: list[dict] = []

    if isinstance(chain_payload, dict):
        # Shape: { "expirations": [ { "expiration": "...", "strikes": [...] } ] }
        expirations = chain_payload.get("expirations") or chain_payload.get("expiry_dates") or []
        if isinstance(expirations, list):
            for exp in expirations[:6]:  # cap at 6 expirations
                if isinstance(exp, str):
                    chain_out.append({"expiration": exp, "strikes": []})
                elif isinstance(exp, dict):
                    exp_str = str(exp.get("expiration") or exp.get("expiry") or exp.get("date") or "")
                    strikes_raw = exp.get("strikes") or exp.get("options") or []
                    strikes_out: list[list] = []
                    if isinstance(strikes_raw, list):
                        for s in strikes_raw:
                            if isinstance(s, (int, float)):
                                strikes_out.append([float(s), [], []])
                            elif isinstance(s, dict):
                                strike_val = float(s.get("strike") or s.get("strike_price") or 0)
                                call_vals = _extract_contract_vals(s.get("call") or s.get("calls"), requested_fields)
                                put_vals = _extract_contract_vals(s.get("put") or s.get("puts"), requested_fields)
                                strikes_out.append([strike_val, call_vals, put_vals])
                    chain_out.append({"expiration": exp_str, "strikes": strikes_out})
        # Fallback: flat list of contracts
        elif "contracts" in chain_payload or "options" in chain_payload:
            contracts = chain_payload.get("contracts") or chain_payload.get("options") or []
            by_exp: dict[str, list] = {}
            for c in contracts[:500]:
                if not isinstance(c, dict):
                    continue
                exp_str = str(c.get("expiration") or c.get("expiry") or "unknown")
                if exp_str not in by_exp:
                    by_exp[exp_str] = []
                strike_val = float(c.get("strike") or c.get("strike_price") or 0)
                ctype = str(c.get("type") or c.get("option_type") or c.get("right") or "").upper()
                vals = _extract_contract_vals(c, requested_fields)
                if ctype.startswith("C"):
                    by_exp[exp_str].append([strike_val, vals, []])
                else:
                    by_exp[exp_str].append([strike_val, [], vals])
            for exp_str, strikes in by_exp.items():
                chain_out.append({"expiration": exp_str, "strikes": strikes})

    return {
        "symbol": sym,
        "params": requested_fields,
        "chain": chain_out,
    }


def _extract_contract_vals(contract: dict | None, fields: list[str]) -> list:
    """Extract requested fields from a contract dict, returning a list of values."""
    if not isinstance(contract, dict) or not fields:
        return []
    return [contract.get(f) for f in fields]


@router.get("/screen")
async def screen_options(
    ticker: str = Query(..., description="Ticker symbol to screen"),
    min_premium: float = Query(0.0, ge=0.0, description="Minimum premium threshold"),
    min_oi: int = Query(0, ge=0, description="Minimum open interest"),
    min_delta: float = Query(None, description="Minimum absolute delta"),
    max_delta: float = Query(None, description="Maximum absolute delta"),
    option_type: str = Query(None, description="Filter: call, put, or all"),
    limit: int = Query(50, ge=1, le=500),
):
    """
    Screen options by criteria (premium, OI, delta, type).

    Returns filtered list of contracts matching all specified thresholds.
    Degrades gracefully to empty list when provider is unavailable.
    """
    sym = (ticker or "").strip().upper()
    if not sym:
        raise HTTPException(400, "ticker required")

    try:
        from services.flowseeker import _get_client

        client = _get_client()
        chain_payload = await client.get_options_chain(sym)
    except Exception as e:
        logger.warning(f"flowseeker screen: provider error for {sym}: {e}")
        chain_payload = None

    if chain_payload is None:
        return {"ticker": sym, "count": 0, "results": []}

    # Flatten chain into individual contracts for filtering
    contracts: list[dict] = []
    if isinstance(chain_payload, dict):
        expirations = chain_payload.get("expirations") or chain_payload.get("expiry_dates") or []
        if isinstance(expirations, list):
            for exp in expirations[:6]:
                exp_str = str(exp.get("expiration") or exp.get("expiry") or "") if isinstance(exp, dict) else str(exp)
                strikes = exp.get("strikes") or exp.get("options") or [] if isinstance(exp, dict) else []
                for s in strikes:
                    if isinstance(s, dict):
                        strike_val = float(s.get("strike") or s.get("strike_price") or 0)
                        for side_key, side_label in [("call", "CALL"), ("put", "PUT")]:
                            leg = s.get(side_key) or s.get(f"{side_key}s")
                            if isinstance(leg, dict):
                                contract = {
                                    "ticker": sym,
                                    "strike": strike_val,
                                    "expiration": exp_str,
                                    "type": side_label,
                                    **leg,
                                }
                                contracts.append(contract)
        # Fallback: flat contracts list
        flat = chain_payload.get("contracts") or chain_payload.get("options") or []
        if isinstance(flat, list) and not contracts:
            for c in flat[:500]:
                if isinstance(c, dict):
                    contracts.append({**c, "ticker": sym})

    # Apply filters
    from services.flowseeker import _f, _i

    filtered: list[dict] = []
    for c in contracts:
        premium = _f(c.get("premium") or c.get("notional"))
        if premium < min_premium:
            continue
        oi = _i(c.get("oi") or c.get("open_interest"))
        if oi < min_oi:
            continue
        if min_delta is not None or max_delta is not None:
            delta = _f(c.get("delta"))
            abs_delta = abs(delta)
            if min_delta is not None and abs_delta < min_delta:
                continue
            if max_delta is not None and abs_delta > max_delta:
                continue
        if option_type:
            ot = option_type.strip().upper()
            ctype = str(c.get("type") or c.get("option_type") or c.get("right") or "").upper()
            if ot == "CALL" and not ctype.startswith("C"):
                continue
            if ot == "PUT" and not ctype.startswith("P"):
                continue
        filtered.append(c)
        if len(filtered) >= limit:
            break

    return {"ticker": sym, "count": len(filtered), "results": filtered}
