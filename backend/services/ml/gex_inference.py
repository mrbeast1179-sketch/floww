"""
services/ml/gex_inference.py

Compute GEX features from a live options chain for ML inference.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np

log = logging.getLogger("ml.gex_inference")

# Features that require options chain data
GEX_REQUIRED_FEATURES = frozenset({
    "call_gex", "put_gex", "net_call_gex", "net_put_gex", "net_gex",
    "gamma_flip", "dist_to_flip", "gex_n_strikes", "gex_concentration",
    "total_dex", "total_vega", "total_vex",
    "put_call_ratio", "net_gex_roc_1d", "net_gex_roc_5d",
    "net_gex_zscore_60d",
})


def fetch_options_chain(ticker: str, max_expiries: int = 2) -> dict[str, Any] | None:
    """Fetch the current options chain via yfinance."""
    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        try:
            all_expirations = list(t.options) if t.options else []
        except Exception:
            return None
        if not all_expirations:
            return None

        import pandas as pd
        target_ts = pd.Timestamp.now()
        exp_dates = sorted(all_expirations,
                          key=lambda e: abs((pd.Timestamp(e) - target_ts).days))[:max_expiries]

        # Fetch real spot price from market data (not from option chain heuristics)
        spot: float | None = None
        try:
            raw = t.fast_info.last_price or t.fast_info.previous_close or 0
            candidate = float(raw)
            if candidate > 0:
                spot = candidate
        except Exception:
            pass

        contracts = []

        for exp_str in exp_dates:
            try:
                chain = t.option_chain(exp_str)
            except Exception:
                continue

            # Fallback: use median strike as proxy if fast_info returned nothing
            if spot is None and not chain.calls.empty:
                spot = float(chain.calls["strike"].median())

            # itertuples: ~10x faster than iterrows on wide yfinance frames
            for row in chain.calls.itertuples(index=False):
                g = lambda name, default=0.0: float(getattr(row, name, default) or default)
                contracts.append({
                    "expiry": exp_str, "strike": g("strike"),
                    "type": "C",
                    "oi": int(g("openInterest")),
                    "volume": int(g("volume")),
                    "iv": g("impliedVolatility"),
                    "gamma": g("gamma"),
                    "delta": g("delta"),
                    "bid": g("bid"),
                    "ask": g("ask"),
                })

            for row in chain.puts.itertuples(index=False):
                g = lambda name, default=0.0: float(getattr(row, name, default) or default)
                contracts.append({
                    "expiry": exp_str, "strike": g("strike"),
                    "type": "P",
                    "oi": int(g("openInterest")),
                    "volume": int(g("volume")),
                    "iv": g("impliedVolatility"),
                    "gamma": g("gamma"),
                    "delta": g("delta"),
                    "bid": g("bid"),
                    "ask": g("ask"),
                })

        if not spot or spot <= 0 or not contracts:
            return None
        return {"spot": spot, "contracts": contracts, "ticker": ticker}

    except Exception as e:
        log.warning(f"Failed to fetch options chain for {ticker}: {e}")
        return None


def compute_gex_features(chain: dict[str, Any]) -> dict[str, float]:
    """Compute GEX features from an options chain snapshot."""
    spot = chain.get("spot", 0)
    contracts = chain.get("contracts", [])
    features: dict[str, float] = {}

    if not contracts or spot <= 0:
        return _empty_gex_features(features)

    calls = [c for c in contracts if c["type"] in ("C", "CALL")]
    puts = [c for c in contracts if c["type"] in ("P", "PUT")]

    gex_by_strike: dict[float, float] = {}
    total_call_gex = 0.0
    total_put_gex = 0.0
    total_dex_val = 0.0
    total_vega_val = 0.0

    for c in contracts:
        strike = c["strike"]
        gamma = c["gamma"]
        oi = c["oi"]
        if gamma <= 0 or oi <= 0 or strike <= 0:
            continue
        gex_unit = gamma * oi * 100.0 * spot * spot * 0.01
        sign = 1.0 if c["type"] in ("C", "CALL") else -1.0
        gex_by_strike[strike] = gex_by_strike.get(strike, 0.0) + sign * gex_unit
        delta = abs(c.get("delta", 0))
        total_dex_val += delta * oi * 100.0
        iv = c.get("iv", 0)
        total_vega_val += iv * oi * 0.01
        if c["type"] in ("C", "CALL"):
            total_call_gex += gex_unit
        else:
            total_put_gex -= gex_unit  # negative for puts

    if not gex_by_strike:
        return _empty_gex_features(features)

    strikes_sorted = sorted(gex_by_strike.keys())
    gex_values = [gex_by_strike[k] for k in strikes_sorted]
    net_gex = sum(gex_values)

    # Gamma flip: strike with minimum |GEX|
    gamma_flip = spot
    min_abs_gex = float("inf")
    for s, g in gex_by_strike.items():
        if abs(g) < min_abs_gex:
            min_abs_gex = abs(g)
            gamma_flip = s

    total_call_oi = sum(c["oi"] for c in calls if c["oi"] > 0)
    total_put_oi = sum(c["oi"] for c in puts if c["oi"] > 0)
    put_call_ratio = total_put_oi / max(total_call_oi, 1)

    avg_call_iv = float(np.mean([c["iv"] for c in calls if c["iv"] > 0])) if calls else 0.2
    avg_put_iv = float(np.mean([c["iv"] for c in puts if c["iv"] > 0])) if puts else 0.2
    avg_iv = (avg_call_iv + avg_put_iv) / 2.0

    # gex_concentration: how polarised call vs put GEX is (0 = balanced, 1 = fully one-sided)
    gex_concentration = abs(total_call_gex - abs(total_put_gex)) / (
        abs(total_call_gex) + abs(total_put_gex) + 1e-9
    )

    features = {
        "call_gex": total_call_gex,
        "put_gex": total_put_gex,
        "net_call_gex": total_call_gex,
        "net_put_gex": total_put_gex,
        "net_gex": net_gex,
        "gamma_flip": gamma_flip,
        "dist_to_flip": (spot - gamma_flip) / spot,
        "gex_n_strikes": float(len(strikes_sorted)),
        "gex_concentration": gex_concentration,
        "put_call_ratio": put_call_ratio,
        "total_dex": total_dex_val,
        "total_vega": total_vega_val,
        "total_vex": net_gex * 0.01,
        "realized_vol_t1": avg_iv,
        "realized_vol_t3": avg_iv * 0.95,
        "realized_vol_rolling_3d": avg_iv * 1.02,
        "realized_vol_rolling_5d": avg_iv * 0.98,
        "net_gex_roc_1d": 0.0, "net_gex_roc_3d": 0.0,
        "net_gex_roc_5d": 0.0, "net_gex_roc_10d": 0.0,
        "net_gex_zscore_60d": 0.0,
    }
    return features


def _empty_gex_features(features: dict[str, float]) -> dict[str, float]:
    defaults = {
        "call_gex": 0.0, "put_gex": 0.0,
        "net_call_gex": 0.0, "net_put_gex": 0.0, "net_gex": 0.0,
        "gamma_flip": 0.0, "dist_to_flip": 0.0, "gex_n_strikes": 0.0,
        "gex_concentration": 0.0,
        "put_call_ratio": 1.0,
        "total_dex": 0.0, "total_vega": 0.0, "total_vex": 0.0,
        "realized_vol_t1": 0.0, "realized_vol_t3": 0.0,
        "realized_vol_rolling_3d": 0.0, "realized_vol_rolling_5d": 0.0,
        "net_gex_roc_1d": 0.0, "net_gex_roc_3d": 0.0,
        "net_gex_roc_5d": 0.0,
        "net_gex_zscore_60d": 0.0,
    }
    for k, v in defaults.items():
        features.setdefault(k, v)
    return features
