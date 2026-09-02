"""
WTI Crude Oil HAR-IV Volatility Forecast
=========================================
Surface-level forecast for front-month WTI (CL=F): realized vol at 5/22/66-day
windows, CBOE OVX reading, and a direction call (RISING / FALLING / FLAT) for
next-week realized vol.

Ported from the audited WTI research — HAR-RV(5/22/66) + OVX regime blend.
Requires only yfinance (already in the project).
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import yfinance as yf

log = logging.getLogger(__name__)

CL_F = "CL=F"
OVX = "^OVX"
TRADING_DAYS = 252


def _fetch_close(ticker: str, days: int) -> pd.Series | None:
    end = datetime.now()
    start = end - timedelta(days=days + 45)
    try:
        frame = yf.download(ticker, start=start, end=end, progress=False, auto_adjust=True)
        if frame.empty:
            return None
        close = frame["Close"]
        if isinstance(close, pd.DataFrame):
            close = close.iloc[:, 0]
        close = close.dropna().astype(float)
        return close
    except Exception as exc:
        log.warning("yfinance fetch %s failed: %s", ticker, exc)
        return None


def _realized_vol(returns: pd.Series, window: int) -> float | None:
    if len(returns) < window:
        return None
    tail = returns.iloc[-window:]
    return float(np.sqrt(tail.var() * TRADING_DAYS)) * 100


def forecast() -> dict:
    """One-shot HAR-IV volatility forecast for WTI crude."""
    cl = _fetch_close(CL_F, 300)
    ovx = _fetch_close(OVX, 5)

    if cl is None or len(cl) < 66:
        return {
            "ok": False,
            "error": "insufficient_cl_data",
            "as_of": None,
            "price": None,
            "realized_rv5": None,
            "realized_rv22": None,
            "realized_rv66": None,
            "ovx": None,
            "forecast_pct": None,
            "direction": "UNKNOWN",
            "direction_conf": None,
        }

    ret = np.log(cl / cl.shift(1)).dropna()
    rv5 = _realized_vol(ret, 5)
    rv22 = _realized_vol(ret, 22)
    rv66 = _realized_vol(ret, 66)

    ovx_val = None
    if ovx is not None and len(ovx) >= 1:
        try:
            ovx_val = float(ovx.iloc[-1])
        except Exception:
            pass

    last_price = float(cl.iloc[-1])
    as_of = cl.index[-1]

    # HAR-style blend: short window dominates, long window anchors, OVX nudges
    components = []
    if rv5 is not None:
        components.append(rv5 * 0.45)
    if rv22 is not None:
        components.append(rv22 * 0.30)
    if rv66 is not None:
        components.append(rv66 * 0.15)
    if ovx_val is not None:
        components.append(ovx_val * 0.10)

    forecast_pct = float(np.mean(components)) if components else None

    # Direction: compare 5d realized vs 22d. Rising if short > medium by >10%,
    # Falling if short < medium by >10%, else FLAT.
    direction = "UNKNOWN"
    direction_conf = None
    if rv5 is not None and rv22 is not None and rv22 > 0:
        ratio = rv5 / rv22
        if ratio > 1.10:
            direction = "RISING"
            direction_conf = min(0.95, 0.55 + (ratio - 1.10) * 2.0)
        elif ratio < 0.90:
            direction = "FALLING"
            direction_conf = min(0.95, 0.55 + (0.90 - ratio) * 2.0)
        else:
            direction = "FLAT"
            direction_conf = 0.50

    return {
        "ok": True,
        "as_of": as_of.isoformat(),
        "price": round(last_price, 2),
        "realized_rv5": round(rv5, 2) if rv5 is not None else None,
        "realized_rv22": round(rv22, 2) if rv22 is not None else None,
        "realized_rv66": round(rv66, 2) if rv66 is not None else None,
        "ovx": round(ovx_val, 2) if ovx_val is not None else None,
        "forecast_pct": round(forecast_pct, 2) if forecast_pct is not None else None,
        "direction": direction,
        "direction_conf": round(direction_conf, 3) if direction_conf is not None else None,
    }
