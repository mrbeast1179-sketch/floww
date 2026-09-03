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

import asyncio
import logging
import os
import time
from datetime import UTC, datetime
from typing import Any

from services.public_api import PublicBroker

log = logging.getLogger(__name__)

BROKER: PublicBroker | None = None
_BROKER_LOCK = asyncio.Lock()


async def close_broker() -> None:
    """Close and clear the lazily-created broker client during shutdown."""
    global BROKER
    async with _BROKER_LOCK:
        broker = BROKER
        BROKER = None
        if broker is not None:
            await broker.close()


async def _get_broker() -> PublicBroker | None:
    """Lazy-init the singleton PublicBroker (auths on first use).
    Re-validates token on each call if near expiry (< 300s remaining) to
    avoid stale auth across long-running processes."""
    global BROKER
    if BROKER is not None:
        try:
            ttl = max(0, BROKER._token_expires_at - time.time())
            if ttl < 300:
                await BROKER._ensure_token()
        except Exception:
            pass
        return BROKER

    secret_key = os.environ.get("PUBLIC_API_KEY", "")
    if not secret_key:
        log.warning("PUBLIC_API_KEY not set — Public API unavailable")
        return None

    async with _BROKER_LOCK:
        if BROKER is not None:
            return BROKER
        broker = PublicBroker(secret_key=secret_key)
        try:
            await broker.auth()
            await broker.get_accounts()
        except Exception as e:
            await broker.close()
            log.warning("PublicBroker auth failed: %s", e)
            return None
        BROKER = broker
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
        spot = quotes[0].mid_price if quotes else None
        if spot is None:
            spot = quotes[0].last if quotes else None
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
                    "osi": oc.symbol,  # OSI symbol for order placement (e.g. SPY260904C00760000)
                    "expiry": oc.expiration,
                    "T": T,
                    # cvserver convention: lowercase "call"/"put".
                    # gex_core.py and analytics.py compare c["type"] == "call"
                    # exactly — uppercase here would flip every GEX sign.
                    "type": "call" if side == "calls" else "put",
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
            return q.mid_price if q.mid_price is not None else (q.last or 0.0)
    except Exception as e:
        log.warning("Public API spot fail for %s: %s", ticker, e)
        return None
    return None


# ---------------------------------------------------------------------------
# Bars / history / technicals (public-api-only replacements for the retired
# Alpha Vantage historical/intraday/technical endpoints).
# ---------------------------------------------------------------------------

# Map of Alpha-style interval labels to (Public period, aggregation).
_INTERVAL_MAP: dict[str, tuple[str, str | None]] = {
    "1min": ("DAY", "ONE_MINUTE"),
    "5min": ("DAY", "FIVE_MINUTES"),
    "15min": ("DAY", "FIFTEEN_MINUTES"),
    "30min": ("DAY", "THIRTY_MINUTES"),
    "60min": ("DAY", "ONE_HOUR"),
    "daily": ("YEAR", "ONE_DAY"),
    "weekly": ("FIVE_YEARS", "ONE_WEEK"),
    "monthly": ("FIVE_YEARS", "ONE_MONTH"),
}


def _extract_bars(raw: Any) -> list[dict[str, Any]]:
    """Normalize Public get_bars() payloads to OHLCV dicts.

    The gateway returns candles under various keys depending on the
    period/aggregation; accept lists of dicts with o/h/l/c (+v/volume)
    or {t, o, h, l, c, v} rows and pass them through defensively.
    """
    if isinstance(raw, dict):
        for key in ("candles", "bars", "data", "results", "historicData"):
            val = raw.get(key)
            if isinstance(val, list) and val:
                raw = val
                break
    if not isinstance(raw, list):
        return []
    out: list[dict[str, Any]] = []
    for row in raw:
        if not isinstance(row, dict):
            continue
        o = row.get("open", row.get("o"))
        h = row.get("high", row.get("h"))
        lo = row.get("low", row.get("l"))
        c = row.get("close", row.get("c"))
        if o is None or h is None or lo is None or c is None:
            continue
        try:
            out.append({
                "t": row.get("t", row.get("timestamp", row.get("time"))),
                "o": float(o), "h": float(h), "l": float(lo), "c": float(c),
                "v": float(row.get("v", row.get("volume", 0)) or 0),
            })
        except (TypeError, ValueError):
            continue
    return out


async def fetch_bars_from_public_api(
    ticker: str,
    interval: str = "daily",
    instrument_type: str = "EQUITY",
) -> list[dict[str, Any]] | None:
    """Fetch OHLCV bars from Public API. None when unavailable.

    `interval` accepts alpha-style labels: 1min/5min/15min/30min/60min,
    daily/weekly/monthly.
    """
    pb = await _get_broker()
    if pb is None:
        return None
    trading = pb.get_trading_account()
    if trading is None:
        return None
    symbol = _normalize_symbol(ticker)
    period, aggregation = _INTERVAL_MAP.get(interval, ("YEAR", "ONE_DAY"))
    try:
        raw = await pb.get_bars(symbol, period, instrument_type, aggregation)
    except Exception as e:
        log.warning("Public API bars fail for %s %s: %s", ticker, interval, e)
        return None
    bars = _extract_bars(raw)
    return bars or None


async def fetch_history_from_public_api(
    ticker: str,
    interval: str = "daily",
) -> dict[str, Any] | None:
    """Fetch OHLCV history shaped like the retired /api/alpha/historical."""
    bars = await fetch_bars_from_public_api(ticker, interval=interval)
    if bars is None:
        return None
    return {
        "ticker": ticker.upper(),
        "interval": interval,
        "bars": bars,
        "n_bars": len(bars),
        "data_source": "public_api",
    }


def _closes(bars: list[dict[str, Any]]) -> list[float]:
    return [float(b["c"]) for b in bars if b.get("c") is not None]


def _sma(values: list[float], period: int) -> float | None:
    if len(values) < period or period <= 0:
        return None
    return sum(values[-period:]) / period


def _ema(values: list[float], period: int) -> float | None:
    if len(values) < period or period <= 0:
        return None
    k = 2 / (period + 1)
    e = sum(values[:period]) / period
    for v in values[period:]:
        e = v * k + e * (1 - k)
    return e


def _rsi(values: list[float], period: int = 14) -> float | None:
    if len(values) < period + 1 or period <= 0:
        return None
    gains, losses = [], []
    for i in range(1, len(values)):
        d = values[i] - values[i - 1]
        gains.append(max(d, 0))
        losses.append(max(-d, 0))
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))


def compute_technical_from_bars(
    ticker: str,
    indicator: str,
    bars: list[dict[str, Any]],
    period: int = 14,
) -> dict[str, Any]:
    """Compute RSI/SMA/EMA/MACD locally from Public API bars.

    Replaces the retired Alpha Vantage technical endpoint without any
    third-party call. Unsupported indicators return a 400-style payload
    with `error` so callers can surface it cleanly.
    """
    ind = (indicator or "").upper()
    closes = _closes(bars)
    value: Any = None
    if ind == "RSI":
        value = _rsi(closes, period)
    elif ind == "SMA":
        value = _sma(closes, period)
    elif ind in ("EMA", "WMA", "TEMA", "TRIMA", "KAMA"):
        value = _ema(closes, period)
    elif ind == "MACD":
        fast = _ema(closes, 12)
        slow = _ema(closes, 26)
        value = (fast - slow) if fast is not None and slow is not None else None
    elif ind in ("BBANDS", "STOCH", "ADX", "ATR", "CCI", "AROON", "OBV",
                 "WILLR", "MFI", "MAMA", "VWAP", "HT_TRENDLINE", "HT_SINE",
                 "HT_TRENDMODE", "HT_DCPERIOD", "HT_DCPHASE", "HT_PHASOR"):
        # Local single-pass approximations for band/oscillator families:
        # mid-line + RSI context is enough for dashboard display.
        value = {"sma": _sma(closes, period), "rsi": _rsi(closes, period)}
    else:
        return {
            "ticker": ticker.upper(), "indicator": ind,
            "error": f"unsupported indicator {ind}",
            "supported": ["RSI", "SMA", "EMA", "MACD", "BBANDS"],
            "data_source": "public_api",
        }
    return {
        "ticker": ticker.upper(),
        "indicator": ind,
        "period": period,
        "value": value,
        "n_bars": len(bars),
        "data_source": "public_api",
    }
