"""
backend/services/databento_oi.py

Open Interest (OI) lookup with Databento primary + yfinance fallback.

Resilience contract:
  - OI is ALWAYS a non-negative int.
  - If Databento is available and returns data → use it.
  - If Databento returns {} / raises / has no key → fallback to yfinance.
  - If yfinance also fails → return 0 for single lookups, {} for chain lookups.
  - I-8: NaN/None/negative values are clamped to 0.
"""

from __future__ import annotations

import logging
import os
from datetime import date as date_cls
from typing import Any

import yfinance as yf

from databento_provider import (
    PARENT_MAP,
    _fetch_oi_sync,
    _last_trading_day_utc,
)

log = logging.getLogger("databento_oi")

# ---------------------------------------------------------------------------
# yfinance fallback
# ---------------------------------------------------------------------------

def _yfinance_oi_for_contract(
    ticker: str,
    strike: float,
    expiry: str,
    opt_type: str,
) -> int:
    """Fetch OI for a single contract from yfinance.

    Args:
        ticker: Underlying ticker e.g. 'SPY'.
        strike: Strike price.
        expiry: Expiry date 'YYYY-MM-DD'.
        opt_type: 'call' or 'put'.

    Returns:
        Non-negative int OI. 0 if unavailable.
    """
    try:
        yf_ticker = yf.Ticker(ticker)
        chain = yf_ticker.option_chain(expiry)
    except Exception as e:
        log.debug(f"yfinance chain fetch failed {ticker} {expiry}: {e}")
        return 0

    calls = chain.calls if opt_type == "call" else chain.puts
    if calls is None or calls.empty:
        return 0

    # Match strike (within 0.01 for floating point tolerance)
    try:
        mask = calls["strike"].apply(lambda s: abs(float(s) - strike) < 0.01)
        matched = calls[mask]
        if matched.empty:
            log.debug(
                f"yfinance: no match {ticker} {opt_type} {strike} {expiry}"
            )
            return 0
        raw_oi = matched.iloc[0].get("openInterest", None)
        return _clamp_oi(raw_oi)
    except Exception as e:
        log.debug(f"yfinance parse error {ticker} {expiry}: {e}")
        return 0


def _clamp_oi(value: Any) -> int:
    """Clamp any OI value to a non-negative int (I-8 NaN/None guard)."""
    try:
        if value is None:
            return 0
        v = int(float(value))
        return max(v, 0)
    except (TypeError, ValueError, OverflowError):
        return 0


def _yfinance_full_chain(ticker: str) -> dict[str, dict[str, Any]]:
    """Fetch full options chain from yfinance with OI for all contracts.

    Returns dict keyed by '{strike}_{expiry}_{type}' with contract data.
    """
    result: dict[str, dict[str, Any]] = {}
    try:
        yf_ticker = yf.Ticker(ticker)
        expiries = yf_ticker.options
        if not expiries:
            return result

        # Limit to first 4 expiries to avoid rate limits
        for expiry in expiries[:4]:
            try:
                chain = yf_ticker.option_chain(expiry)
            except Exception as e:
                log.debug(f"yfinance chain fail {ticker} {expiry}: {e}")
                continue

            for _df, opt_type in [(chain.calls, "call"), (chain.puts, "put")]:
                if _df is None or _df.empty:
                    continue
                for row in _df.itertuples(index=False):
                    strike = float(getattr(row, "strike", 0) or 0)
                    oi = _clamp_oi(getattr(row, "openInterest", 0) or 0)
                    key = f"{strike}_{expiry}_{opt_type}"
                    result[key] = {
                        "underlying": ticker.upper(),
                        "strike": strike,
                        "expiry": expiry,
                        "type": opt_type,
                        "oi": oi,
                    }
    except Exception as e:
        log.warning(f"yfinance full chain fail {ticker}: {e}")

    return result


# ---------------------------------------------------------------------------
# Public API — resilient OI lookup
# ---------------------------------------------------------------------------

def get_oi(
    ticker: str,
    strike: float,
    expiry: str,
    opt_type: str = "call",
    timestamp: Any | None = None,
) -> int:
    """Resilient OI lookup for a single contract.

    Primary: Databento (if key available and cached).
    Fallback: yfinance.
    Default: 0.

    Returns:
        Non-negative int. Always.
    """
    # --- Attempt 1: Databento ---
    parent = PARENT_MAP.get(ticker.upper(), f"{ticker.upper()}.OPT")
    if not parent and ticker.upper().startswith("^"):
        bare = ticker.upper().replace("^", "")
        parent = PARENT_MAP.get(bare, f"{bare}.OPT")

    key = os.environ.get("DATABENTO_API_KEY", "")
    if key:
        try:
            use_day = _last_trading_day_utc()
            contracts = _fetch_oi_sync(parent, use_day)
            if not contracts:
                # Walk back up to 4 trading days
                from datetime import timedelta
                for _ in range(4):
                    use_day -= timedelta(days=1)
                    while use_day.weekday() >= 5:
                        use_day -= timedelta(days=1)
                    contracts = _fetch_oi_sync(parent, use_day)
                    if contracts:
                        break
            if contracts:
                # Find matching contract — data already has strike/expiry/type from _fetch_oi_sync
                for _sym, data in contracts.items():
                    try:
                        if (
                            abs(data.get("strike", 0) - strike) < 0.01
                            and data.get("expiry", "") == expiry
                            and data.get("type", "") == opt_type
                        ):
                            return _clamp_oi(data.get("oi", 0))
                    except Exception as e:
                        log.warning(
                            f"databento_oi: top-mover-loop: {e}",
                            exc_info=True,
                        )
                        continue
        except Exception as e:
            log.debug(f"Databento OI lookup failed for {ticker}: {e}")

    # --- Attempt 2: yfinance fallback ---
    log.info(f"yfinance OI fallback triggered for {ticker} {opt_type} {strike} {expiry}")
    return _yfinance_oi_for_contract(ticker, strike, expiry, opt_type)


def get_oi_chain(
    ticker: str,
    day: date_cls | None = None,
) -> dict[str, dict[str, Any]]:
    """Resilient full-chain OI lookup.

    Returns dict with contract data including non-negative 'oi' field.
    Primary: Databento. Fallback: yfinance full chain.
    """
    parent = PARENT_MAP.get(ticker.upper(), f"{ticker.upper()}.OPT")
    if not parent and ticker.upper().startswith("^"):
        bare = ticker.upper().replace("^", "")
        parent = PARENT_MAP.get(bare, f"{bare}.OPT")

    key = os.environ.get("DATABENTO_API_KEY", "")

    if key:
        try:
            from datetime import timedelta
            use_day = day or _last_trading_day_utc()
            contracts = _fetch_oi_sync(parent, use_day)
            if not contracts:
                for _ in range(4):
                    use_day -= timedelta(days=1)
                    while use_day.weekday() >= 5:
                        use_day -= timedelta(days=1)
                    contracts = _fetch_oi_sync(parent, use_day)
                    if contracts:
                        break
            if contracts:
                # Ensure all OI values are non-negative (I-8)
                cleaned = {}
                for sym, data in contracts.items():
                    cleaned[sym] = {**data, "oi": _clamp_oi(data.get("oi", 0))}
                return cleaned
        except Exception as e:
            log.debug(f"Databento chain fail {ticker}: {e}")

    # Fallback: yfinance full chain
    log.info(f"yfinance chain fallback triggered for {ticker}")
    return _yfinance_full_chain(ticker)


def has_databento_key() -> bool:
    """Check whether Databento credentials are configured."""
    return bool(os.environ.get("DATABENTO_API_KEY", ""))
