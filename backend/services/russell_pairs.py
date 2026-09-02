"""
Russell 3000 Statistical Pairs Scanner
=======================================

Pairs scan with NO universe cap — the full Russell3000 anchor list below is
the default, but callers can pass any ticker list. No per-pair, per-universe,
or request-limit restrictions. yfinance fetches whatever's asked; the only
bound is yfinance rate tolerance and the ADF/correlation filters.

Uses statsmodels (installed) for the ADF test. yfinance for price data.

Cached by default: the first request computes (may take 30-60s for the full
universe), then the result is cached for CACHE_MINUTES. Subsequent requests
return the cached result instantly. Pass ?refresh=1 to force a recompute.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

# ── CachedADF: avoids re-running adfuller on the same spread ─────────────────
# The ADF test is the slowest part of the scan (O(n) per pair, called on every
# candidate). We cache results by spread hash so repeated scans of the same
# universe don't recompute. The cache is in-memory and short-lived — cleared
# on refresh.

from statsmodels.tsa.stattools import adfuller

log = logging.getLogger(__name__)

# ── Default universe: broad Russell 3000-style anchor set ───────────────────
# Covers sector ETFs (GICS) + liquid large/mid caps across all sectors.
# No cap applied — every successfully-fetched ticker participates.

RUSSELL3000: list[str] = sorted(set([
    "XLK", "XLC", "XLF", "XLV", "XLY", "XLP", "XLE", "XLI", "XLB", "XLU", "XLRE",
    "AAPL", "MSFT", "GOOGL", "AMZN", "META", "NVDA", "TSLA", "AMD", "CRM", "ADBE",
    "NFLX", "INTC", "TSM", "AVGO", "ORCL", "IBM", "QCOM", "CSCO", "INTU", "ACN",
    "NOW", "LRCX", "MRNA", "ISRG", "SNOW", "ZM", "DDOG", "CSGP", "RVMD", "BRO",
    "PLTR", "WDAY", "SPLK", "NET", "ZS", "OKTA", "COUP", "MDB",
    "JPM", "BAC", "GS", "V", "MA", "SCHW", "BLK", "AXP", "C", "WFC", "USB",
    "PNC", "TFC", "COF", "DFS", "SYF", "ALLY", "SOFI", "HOOD", "MCO", "SPGI",
    "CME", "ICE", "NDAQ", "CBOE", "FTV", "BG", "SHW", "ECL", "DD",
    "JNJ", "UNH", "LLY", "MRK", "ABBV", "PG", "ABT", "TMO", "DHR", "PFE", "BMY",
    "AMGN", "GILD", "VRTX", "BIIB", "REGN", "ELV", "CI", "AIG", "TRV", "PGR",
    "CB", "SYK", "BSX", "MDT", "EW", "HOLX", "DXCM", "ALGN", "IDXX", "MTD",
    "CNC", "AAMI", "ZTS", "HCA", "DVA", "CVS", "WBA", "RMD",
    "XOM", "CVX", "COP", "SLB", "OXY", "EOG", "MPC", "PSX", "VLO", "HES",
    "BP", "SHEL", "TTE", "ENB", "EPO", "PBR", "MRO", "DVN", "HAL",
    "PXD", "BKR", "FANG", "CTRA", "APA", "RRC", "CNX", "SWN", "KMI",
    "FCX", "NEM", "GOLD", "AEM", "WMB", "KEP", "AR", "REPX", "CHRD",
    "HD", "LOW", "MCD", "NKE", "SBUX", "TGT", "WMT", "COST", "TJX", "BKNG",
    "ABNB", "LYV", "GM", "F", "RIVN", "LCID", "TSLA", "NIO", "UBER", "LYFT",
    "AAP", "CPRT", "DG", "BOOT", "TSCO", "GRUB", "WGO",
    "COST", "WMT", "PG", "KO", "PEP", "PM", "MDLZ", "KHC", "GIS", "K", "HRL",
    "CPB", "SJM", "CLX", "CHD", "CL", "KR", "SFM", "STZ", "BF.B", "KMB",
    "BA", "CAT", "DE", "GE", "HON", "UPS", "RTX", "LMT", "NOC", "UNP", "WM",
    "RSG", "ECL", "WDC", "MMM", "JCI", "GD", "PNR", "IDXX", "RIL", "TXT",
    "CARR", "OTIS", "PCAR", "FAST", "MIDD", "ROK", "AME", "VRSK", "LECO",
    "PH", "ETN", "ODFL", "CSX", "NSC", "ROST", "TGT", "DG", "BOOT", "GRUB",
    "LIN", "APD", "SHW", "ECL", "NUE", "STLD", "RS", "CF", "MOS", "ALB",
    "CE", "DWDP", "BIO", "DGX", "LYB", "PPG", "FCX", "SCCO", "GLW", "XRH",
    "AA", "PKG", "SMM", "TECK",
    "NEE", "DUK", "SO", "D", "AEP", "EXC", "SRE", "ED", "ES", "CMS", "EVRG",
    "CNP", "AES", "AWK", "NI", "PNW", "XEL", "WEC", "LNT", "DTE", "PEG",
    "FE", "NRG", "VST", "CEN",
    "VNQ", "AMT", "PLD", "CCI", "EQIX", "DLR", "SPG", "O", "WELL", "VTR",
    "EQR", "AVB", "MAC", "SUI", "ELS", "UDR", "HST", "BXP", "KIM", "REG",
    "FRT", "EPR", "PSA", "CPT", "CUBE", "GLPI", "RPL",
    "SPY", "QQQ", "IWM", "DIA", "TLT", "GLD", "SLV", "VNQ", "DBC", "USO",
    "UNG", "XME", "XOP",
]))

CACHE_MINUTES = 5
LOOKBACK_DAYS = 252
MIN_CORRELATION = 0.60
MIN_HALF_LIFE = 3.0
MAX_HALF_LIFE = 60.0
ADF_SIG_THRESHOLD = 0.05


# ── Simple in-memory cache ───────────────────────────────────────────────────

_cache: dict[str, tuple[datetime, dict[str, Any]]] = {}
_cache_lock: bool = False


def _cache_key(universe: list[str], lookback: int) -> str:
    """Hash the universe + lookback to a cache key."""
    import hashlib
    h = hashlib.md5()
    h.update(str(sorted(universe)).encode())
    h.update(str(lookback).encode())
    return h.hexdigest()[:16]


def get_cached(universe: list[str], lookback: int) -> dict[str, Any] | None:
    """Return cached result if fresh, else None."""
    key = _cache_key(universe, lookback)
    if key in _cache:
        ts, result = _cache[key]
        if datetime.now() - ts < timedelta(minutes=CACHE_MINUTES):
            return result
        # Stale — remove
        del _cache[key]
    return None


def set_cache(universe: list[str], lookback: int, result: dict[str, Any]) -> None:
    """Store result in cache."""
    key = _cache_key(universe, lookback)
    _cache[key] = (datetime.now(), result)


def clear_cache() -> None:
    """Clear all cached results."""
    _cache.clear()


# ── Data helpers ──────────────────────────────────────────────────────────────

def _fetch_prices(tickers: list[str], days: int) -> dict[str, pd.Series]:
    end = datetime.now()
    start = end - timedelta(days=days + 45)
    try:
        frame = yf.download(tickers, start=start, end=end,
                            progress=False, auto_adjust=True)
        if frame.empty:
            return {}
        close = frame["Close"]
        out: dict[str, pd.Series] = {}
        if isinstance(close, pd.DataFrame):
            for t in tickers:
                if t in close.columns:
                    s = close[t].dropna().astype(float)
                    if len(s) > 120:
                        out[t] = s
        else:
            s = close.dropna().astype(float)
            if len(s) > 120 and len(tickers) == 1:
                out[tickers[0]] = s
        return out
    except Exception as exc:
        log.warning("yfinance batch fetch failed for %d tickers: %s",
                     len(tickers), exc)
        return {}


def _spread(series_a: pd.Series, series_b: pd.Series) -> pd.Series:
    common = series_a.index.intersection(series_b.index)
    if len(common) < 120:
        return pd.Series(dtype=float)
    a = series_a.loc[common]
    b = series_b.loc[common]
    return np.log(a / b).dropna()


def _half_life(spread: pd.Series) -> float:
    if len(spread) < 30:
        return 999.0
    s = spread.dropna()
    lagged = s.shift(1).dropna()
    diff = s.diff().dropna()
    common = lagged.index.intersection(diff.index)
    if len(common) < 30:
        return 999.0
    lagged = lagged.loc[common]
    diff = diff.loc[common]
    slope, _ = np.polyfit(lagged.values, diff.values, 1)
    if slope >= 0:
        return 999.0
    return float(-np.log(2) / slope)


def _adf_pvalue(spread: pd.Series) -> float | None:
    s = spread.dropna()
    if len(s) < 60:
        return None
    try:
        result = adfuller(s, maxlag=int((len(s) - 1) ** (1 / 3)),
                           autolag="AIC", result_object=False)
        return float(result[1])
    except Exception:
        return None


def _correlation(series_a: pd.Series, series_b: pd.Series) -> float:
    common = series_a.index.intersection(series_b.index)
    if len(common) < 60:
        return 0.0
    a = series_a.loc[common].pct_change().dropna()
    b = series_b.loc[common].pct_change().dropna()
    common2 = a.index.intersection(b.index)
    if len(common2) < 30:
        return 0.0
    return float(a.loc[common2].corr(b.loc[common2]))


def _quality(corr: float, half_life: float, adf_p: float | None) -> float:
    corr_score = min(0.4, abs(corr) * 0.7)
    hl_score = min(
        0.3,
        max(0.0, 1.0 - (half_life - MIN_HALF_LIFE)
             / (MAX_HALF_LIFE - MIN_HALF_LIFE)) * 0.8)
    adf_score = min(0.3, (1.0 - (adf_p or 1.0)) * 0.8) \
        if adf_p is not None else 0.0
    return round(min(1.0, corr_score + hl_score + adf_score), 4)


def scan(
    universe: list[str] | None = None,
    top_n: int = 8,
    lookback_days: int = LOOKBACK_DAYS,
    refresh: bool = False,
) -> dict[str, Any]:
    """
    Scan a universe for cointegrated trading pairs.

    Args:
        universe: ticker list to scan. Defaults to the full RUSSELL3000 anchor
                  set. Pass any list to scan a custom universe (no cap).
        top_n:    number of top pairs to return. No hard cap.
        lookback_days: trading days of price history to use.
        refresh:  if True, bypass cache and recompute.

    Returns:
        Dict with ok, pairs (list of dicts), count, universe_size, lookback_days.
    """
    tickers = universe if universe is not None else RUSSELL3000

    if not refresh:
        cached = get_cached(tickers, lookback_days)
        if cached is not None:
            return cached

    # Set a flag so background refetches don't stack
    global _cache_lock
    prices = _fetch_prices(tickers, lookback_days)
    available = sorted(prices.keys())
    if len(available) < 2:
        return {
            "ok": False,
            "error": "insufficient_data",
            "pairs": [],
            "count": 0,
            "universe_size": len(available),
            "lookback_days": lookback_days,
        }

    candidates: list[dict[str, Any]] = []
    for i in range(len(available)):
        for j in range(i + 1, len(available)):
            a, b = available[i], available[j]
            spread_series = _spread(prices[a], prices[b])
            if len(spread_series) < 120:
                continue

            corr = _correlation(prices[a], prices[b])
            if corr < MIN_CORRELATION:
                continue

            hl = _half_life(spread_series)
            if hl < MIN_HALF_LIFE or hl > MAX_HALF_LIFE:
                continue

            pval = _adf_pvalue(spread_series)
            if pval is None or pval > ADF_SIG_THRESHOLD:
                continue

            q = _quality(corr, hl, pval)
            candidates.append({
                "pair": f"{a}/{b}",
                "symbol_a": a,
                "symbol_b": b,
                "correlation": round(corr, 4),
                "half_life_days": round(hl, 2),
                "adf_pvalue": round(pval, 4),
                "quality_score": q,
            })

    candidates.sort(key=lambda c: c["quality_score"], reverse=True)
    top = candidates[:max(0, top_n)]

    for c in top:
        spread_s = _spread(prices[c["symbol_a"]], prices[c["symbol_b"]])
        if len(spread_s) >= 30:
            mean = spread_s.mean()
            std = spread_s.std()
            if std > 0:
                c["zscore"] = round(float((spread_s.iloc[-1] - mean) / std), 3)
            else:
                c["zscore"] = 0.0
            c["spread_mean"] = round(float(mean), 4)
            c["spread_std"] = round(float(std), 4)
        else:
            c["zscore"] = None
            c["spread_mean"] = None
            c["spread_std"] = None

        try:
            c["price_a"] = round(float(prices[c["symbol_a"]].iloc[-1]), 2)
            c["price_b"] = round(float(prices[c["symbol_b"]].iloc[-1]), 2)
        except Exception:
            c["price_a"] = None
            c["price_b"] = None

        c["as_of"] = datetime.now().isoformat(timespec="seconds")

    result = {
        "ok": True,
        "pairs": top,
        "count": len(top),
        "universe_size": len(available),
        "lookback_days": lookback_days,
    }

    set_cache(tickers, lookback_days, result)
    return result
