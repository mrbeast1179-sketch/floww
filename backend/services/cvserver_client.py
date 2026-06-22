"""
backend/services/cvserver_client.py

CVForge cvserver HTTP client.
Talks to the remote cvserver MCP endpoint at tap.convexvalue.com.
Used as the primary data source for options chains, replacing yfinance.

Environment variables:
    CVSERVER_URL   — cvserver MCP endpoint (default: https://tap.convexvalue.com/api/data/mcp)
    CVSERVER_API_KEY — Bearer token for cvserver auth

Response format from get_chain:
    {
        "symbol": "SPY",
        "params": ["expiration_date", "strike_price", "contract_type", ...],
        "chain": [
            {
                "expiration": "2026-06-22",
                "strikes": [
                    [strike_price, [call_field_values], [put_field_values]],
                    ...
                ]
            },
            ...
        ],
        "contract_count": 13350,
        "elapsed_ms": 0
    }

Field order in the params array determines the order of values in each strike's
call/put arrays. The first param is always "expiration_date" (redundant with the
expiration key), the second is "strike_price" (redundant with the strike array
element), the third is "contract_type" — so actual per-contract fields start at
index 3.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
import time
from datetime import UTC, datetime

import httpx

logger = logging.getLogger(__name__)

CVSERVER_URL = os.environ.get(
    "CVSERVER_URL", "https://tap.convexvalue.com/api/data/mcp"
)
CVSERVER_API_KEY = os.environ.get("CVSERVER_API_KEY", "")
CVSERVER_TIMEOUT = float(os.environ.get("CVSERVER_TIMEOUT", "15"))

# Field name mapping: cvserver param -> our internal contract field name
FIELD_MAP = {
    "expiration_date": "expiry",
    "strike_price": "strike",
    "contract_type": "type",
    "implied_volatility": "iv",
    "delta": "delta",
    "gamma": "gamma",
    "theta": "theta",
    "vega": "vega",
    "open_interest": "oi",
    "day_volume": "volume",
    "bid": "bid",
    "ask": "ask",
    "midpoint": "midpoint",
    "underlying_price": "underlying_price",
}

# Default fields to request from cvserver
DEFAULT_FIELDS = [
    "expiration_date", "strike_price", "contract_type",
    "implied_volatility", "delta", "gamma", "theta", "vega",
    "bid", "ask", "midpoint", "open_interest", "day_volume",
    "underlying_price",
]

# In-memory cache: symbol -> (timestamp, data)
_cache: dict[str, tuple[float, dict]] = {}
CACHE_TTL = 60  # seconds


def _cvserver_call(method: str, arguments: dict) -> dict:
    """Synchronous JSON-RPC call to cvserver MCP endpoint."""
    headers = {
        "Content-Type": "application/json",
    }
    if CVSERVER_API_KEY:
        headers["Authorization"] = f"Bearer {CVSERVER_API_KEY}"

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": method,
        "params": arguments,
    }

    with httpx.Client(timeout=CVSERVER_TIMEOUT) as client:
        resp = client.post(CVSERVER_URL, json=payload, headers=headers)
        resp.raise_for_status()
        result = resp.json()

    if "error" in result:
        raise RuntimeError(f"cvserver error: {result['error']}")

    # Extract text content from MCP response
    content = result.get("result", {}).get("content", [])
    if content and content[0].get("type") == "text":
        import json
        return json.loads(content[0]["text"])

    return result.get("result", {})


async def _cvserver_call_async(method: str, arguments: dict) -> dict:
    """Async wrapper for _cvserver_call."""
    loop = asyncio.get_event_loop()
    return await loop.run_in_executor(None, _cvserver_call, method, arguments)


def _parse_chain_response(raw: dict, symbol: str) -> dict:
    """
    Parse cvserver get_chain response into our internal format:
    {
        "ticker": "SPY",
        "spot": 746.93,
        "expiries": ["2026-06-22", ...],
        "contracts": [
            {"expiry": "...", "T": 0.01, "type": "call", "strike": 700.0,
             "iv": 0.18, "delta": 0.42, "gamma": 0.003, ...},
            ...
        ],
        "data_source": "cvserver",
    }
    """
    params = raw.get("params", [])
    chain_data = raw.get("chain", [])

    if not chain_data:
        return {
            "ticker": symbol,
            "spot": 0,
            "expiries": [],
            "contracts": [],
            "data_source": "cvserver",
        }

    # Build field index map: param_name -> index in strike arrays
    field_idx = {p: i for i, p in enumerate(params)}

    contracts = []
    expiries = []
    today = datetime.now(UTC).date()
    spot = 0.0

    for exp_group in chain_data:
        expiration = exp_group.get("expiration", "")
        if not expiration:
            continue
        expiries.append(expiration)

        try:
            exp_date = datetime.strptime(expiration, "%Y-%m-%d").date()
        except (ValueError, TypeError):
            continue

        T = max((exp_date - today).days, 1) / 365.0

        for strike_entry in exp_group.get("strikes", []):
            if not strike_entry or len(strike_entry) < 3:
                continue

            strike_price = float(strike_entry[0])
            call_values = strike_entry[1] if len(strike_entry) > 1 else []
            put_values = strike_entry[2] if len(strike_entry) > 2 else []

            # Extract underlying_price from first available contract
            if spot == 0.0:
                for vals in (call_values, put_values):
                    idx = field_idx.get("underlying_price")
                    if idx is not None and idx < len(vals) and vals[idx] is not None:
                        try:
                            spot = float(vals[idx])
                        except (TypeError, ValueError):
                            pass

            # Build contract dicts for call and put
            for kind, vals in [("call", call_values), ("put", put_values)]:
                contract = {
                    "expiry": expiration,
                    "T": T,
                    "type": kind,
                    "strike": strike_price,
                }

                # Map each field
                for param_name, field_name in FIELD_MAP.items():
                    idx = field_idx.get(param_name)
                    if idx is not None and idx < len(vals):
                        val = vals[idx]
                        if val is not None:
                            try:
                                fval = float(val)
                                if math.isnan(fval) or math.isinf(fval):
                                    val = 0.0
                                else:
                                    val = fval
                            except (TypeError, ValueError):
                                val = None
                        contract[field_name] = val

                # Ensure required fields exist
                contract.setdefault("iv", 0.0)
                contract.setdefault("oi", 0.0)
                contract.setdefault("volume", 0.0)
                contract.setdefault("delta", 0.0)
                contract.setdefault("gamma", 0.0)
                contract.setdefault("theta", 0.0)
                contract.setdefault("vega", 0.0)
                contract.setdefault("bid", 0.0)
                contract.setdefault("ask", 0.0)
                contract.setdefault("midpoint", 0.0)

                contracts.append(contract)

    return {
        "ticker": symbol,
        "spot": spot,
        "expiries": sorted(expiries),
        "contracts": contracts,
        "data_source": "cvserver",
    }


async def fetch_chain_from_cvserver(
    symbol: str,
    fields: list[str] | None = None,
    max_expiries: int = 32,
) -> dict | None:
    """
    Fetch options chain from cvserver.
    Returns parsed dict in our internal format, or None on failure.
    """
    if not CVSERVER_API_KEY:
        logger.debug("cvserver: no API key configured, skipping")
        return None

    logger.debug(f"cvserver: fetching {symbol}, key={'set' if CVSERVER_API_KEY else 'EMPTY'}")

    # Check cache
    cache_key = f"cvserver:{symbol}:{max_expiries}"
    if cache_key in _cache:
        ts, data = _cache[cache_key]
        if time.time() - ts < CACHE_TTL:
            logger.debug(f"cvserver cache hit: {symbol}")
            return data

    if fields is None:
        fields = DEFAULT_FIELDS

    # Map yfinance-style index symbols to cvserver format
    # cvserver uses I: prefix for index underlyings
    _symbol_map = {
        "^SPX": "I:SPX",
        "^NDX": "I:NDX",
        "^RUT": "I:RUT",
        "^VIX": "I:VIX",
    }
    cv_symbol = _symbol_map.get(symbol.upper(), symbol.upper())
    logger.debug(f"cvserver: {symbol} → {cv_symbol}")

    try:
        raw = await _cvserver_call_async("tools/call", {
            "name": "get_chain",
            "arguments": {
                "symbol": cv_symbol,
                "params": fields,
            },
        })

        if not raw or not raw.get("chain"):
            logger.warning(f"cvserver: empty chain for {symbol}")
            return None

        parsed = _parse_chain_response(raw, cv_symbol)

        if not parsed["contracts"]:
            logger.warning(f"cvserver: no contracts parsed for {symbol}")
            return None

        _cache[cache_key] = (time.time(), parsed)
        logger.info(
            f"cvserver: {symbol} → {len(parsed['contracts'])} contracts, "
            f"{len(parsed['expiries'])} expiries, spot={parsed['spot']}"
        )
        return parsed

    except Exception as e:
        logger.warning(f"cvserver: fetch failed for {symbol}: {e}")
        return None


async def screen_from_cvserver(
    columns: list[str],
    filters: list[dict],
    sort: list[dict] | None = None,
    limit: int = 100,
) -> dict | None:
    """
    Run a screen query against cvserver.
    Returns {columns, rows, row_count} or None on failure.
    """
    if not CVSERVER_API_KEY:
        return None

    try:
        args: dict = {
            "columns": columns,
            "filters": filters,
            "limit": limit,
        }
        if sort:
            args["sort"] = sort

        raw = await _cvserver_call_async("tools/call", {
            "name": "screen",
            "arguments": args,
        })

        if not raw:
            return None

        return raw

    except Exception as e:
        logger.warning(f"cvserver screen failed: {e}")
        return None


def clear_cache() -> None:
    """Clear the cvserver response cache."""
    _cache.clear()
