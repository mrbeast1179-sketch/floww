"""
backend/services/public_api_adapter.py

Adapter that bridges PublicBroker (Public.com API) to floww's internal data shape.

floww's existing fetch_spot_and_chains_merged() expects:
    {"ticker": str, "spot": float, "expiries": [...], "contracts": [...], "data_source": str}

PublicBroker.get_option_chain_parsed() returns:
    {"calls": [OptionContract...], "puts": [OptionContract...]}

This adapter converts PublicBroker's output to floww's expected shape.

Routing priority (in fetch_spot_and_chains_merged):
    1. Public API (this adapter)  — PRIMARY
    2. cvserver_client.py         — fallback
    3. yfinance + Databento        — last resort
"""
from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from services.public_api import PublicBroker

log = logging.getLogger(__name__)

BROKER: PublicBroker | None = None


async def _get_broker() -> PublicBroker | None:
    """Lazy-init the singleton PublicBroker (auths on first use)."""
    global BROKER
    if BROKER is None:
        import os
        secret_key = os.environ.get("PUBLIC_API_KEY", "")
        if not secret_key:
            log.warning("PUBLIC_API_KEY not set — Public API unavailable")
            return None
        BROKER = PublicBroker(secret_key=secret_key)
        try:
            await BROKER.auth()
            accounts = await BROKER.get_accounts()
            trading = BROKER.get_trading_account()
            if trading is None and accounts:
                trading = BROKER.get_trading_account()
        except Exception as e:
            log.warning("PublicBroker auth failed: %s", e)
            BROKER = None
            return None
    return BROKER


def _normalize_symbol(symbol: str) -> str:
    """Map user-facing tickers to Public.com instrument symbols."""
    return symbol.upper().replace("^", "")


async def fetch_chain_from_public_api(
    ticker: str,
    max_expiries: int = 4,
) -> dict[str, Any] | None:
    """
    Fetch options chain from Public API, return floww-shaped dict.

    Returns the same shape as fetch_spot_and_chains_merged:
        {"ticker": str, "spot": float, "expiries": [...], "contracts": [...], "data_source": "public_api"}

    Returns None if Public API key missing or call fails.
    """
    pb = await _get_broker()
    if pb is None:
        return None

    trading = pb.get_trading_account()
    if trading is None:
        log.warning("No trading account for Public API")
        return None

    account_id = trading.account_id
    symbol = _normalize_symbol(ticker)

    # 1. Get expirations
    try:
        expiries = await pb.get_option_expirations(symbol, account_id)
    except Exception as e:
        log.warning("Public API expirations fail for %s: %s", ticker, e)
        return None

    if not expiries:
        log.warning("Public API returned no expirations for %s", ticker)
        return None

    # 2. Get spot quote
    try:
        quotes = await pb.get_quotes([symbol], account_id)
        spot = quotes[0].mid_price if quotes else 0.0
        if spot is None:
            spot = quotes[0].last if quotes else 0.0
        if spot is None:
            spot = 0.0
    except Exception as e:
        log.warning("Public API quote fail for %s: %s", ticker, e)
        return None

    # 3. Fetch chain for each expiry (up to max_expiries)
    contracts: list[dict[str, Any]] = []
    exp_dates = []
    today = datetime.now(UTC).date()

    for exp in expiries[:max_expiries]:
        exp_dates.append(exp)
        try:
            parsed = await pb.get_option_chain_parsed(symbol, exp, account_id)
        except Exception as e:
            log.warning("Public API chain fail for %s %s: %s", ticker, exp, e)
            continue

        for side in ("calls", "puts"):
            for oc in parsed.get(side, []):
                try:
                    exp_d = datetime.strptime(oc.expiration, "%Y-%m-%d").date()
                except (ValueError, TypeError):
                    continue
                T = max((exp_d - today).days, 1) / 365.0
                contracts.append({
                    "expiry": oc.expiration,
                    "T": T,
                    "type": "CALL" if side == "calls" else "PUT",
                    "strike": oc.strike,
                    "oi": oc.open_interest or 0,
                    "iv": oc.iv or 0.0,
                    "delta": oc.delta,
                    "gamma": oc.gamma,
                    "theta": oc.theta,
                    "vega": oc.vega,
                    "bid": oc.bid,
                    "ask": oc.ask,
                    "volume": oc.volume or 0,
                    "oi_source": "public_api",
                })

    if not contracts:
        log.warning("Public API returned 0 contracts for %s", ticker)
        return None

    return {
        "ticker": ticker.upper(),
        "spot": float(spot),
        "expiries": exp_dates,
        "contracts": contracts,
        "data_source": "public_api",
    }


async def fetch_spot_from_public_api(
    ticker: str,
) -> float | None:
    """Fetch spot price from Public API. Returns None if unavailable."""
    pb = await _get_broker()
    if pb is None:
        return None

    trading = pb.get_trading_account()
    if trading is None:
        return None

    symbol = _normalize_symbol(ticker)
    try:
        quotes = await pb.get_quotes([symbol], trading.account_id)
        if quotes:
            q = quotes[0]
            return q.mid_price or q.last or 0.0
    except Exception as e:
        log.warning("Public API spot fail for %s: %s", ticker, e)
        return None
    return None
