"""
backend/services/uoa.py

Unusual Options Activity (UOA) detection.

Detects contracts with unusual characteristics:
  - Volume > 2x OI (vol_oi_ratio > 2.0)
  - Premium (strike * volume * 100) > min_premium
  - IV significantly above average (> 1.5x mean IV)
"""
import math
from typing import Any


def _safe_float(val, default=0.0):
    """Convert to float, replacing NaN/None with default."""
    try:
        v = float(val)
        return default if math.isnan(v) else v
    except (TypeError, ValueError):
        return default


def _safe_int(val, default=0):
    """Convert to int, replacing NaN/None with default."""
    return int(_safe_float(val, default))


def calc_uoa(
    spot: float,
    contracts: list[dict[str, Any]],
    ticker: str,
    min_premium: float = 100_000,
    limit: int = 20,
) -> dict[str, Any]:
    """Detect unusual options activity from option chain data.

    A contract is flagged as unusual when ANY of:
      1. vol_oi_ratio > 2.0  (volume more than 2x open interest)
      2. premium > min_premium  (notional premium = strike * volume * 100)
      3. iv > 1.5 * mean_iv  (implied vol 50%+ above chain average)

    Returns up to `limit` unusual contracts sorted by premium descending.
    """
    if not contracts:
        return {"ticker": ticker, "spot": spot, "unusual": [], "n_scanned": 0}

    # Compute mean IV for the chain (filter out zero/NaN iv)
    ivs = [_safe_float(c.get("iv")) for c in contracts]
    ivs = [v for v in ivs if v > 0]
    mean_iv = sum(ivs) / len(ivs) if ivs else 0.0
    iv_threshold = mean_iv * 1.5

    unusual = []
    for c in contracts:
        strike = _safe_float(c.get("strike"))
        volume = _safe_float(c.get("volume"))
        oi = _safe_float(c.get("oi"))
        iv = _safe_float(c.get("iv"))
        ctype = c.get("type", "")

        if strike <= 0:
            continue

        vol_oi_ratio = volume / oi if oi > 0 else (float("inf") if volume > 0 else 0.0)
        premium = strike * volume * 100.0

        reasons = []
        if vol_oi_ratio > 2.0:
            reasons.append(f"vol_oi={vol_oi_ratio:.1f}x")
        if premium >= min_premium:
            reasons.append(f"premium=${premium:,.0f}")
        if iv > iv_threshold and mean_iv > 0:
            reasons.append(f"iv={iv:.2f}vs{mean_iv:.2f}")

        if reasons:
            unusual.append({
                "strike": strike,
                "type": ctype,
                "expiry": c.get("expiry", ""),
                "volume": _safe_int(volume),
                "oi": _safe_int(oi),
                "iv": round(iv, 4),
                "vol_oi_ratio": round(vol_oi_ratio, 2),
                "premium": round(premium, 0),
                "spot": spot,
                "reasons": reasons,
            })

    # Sort by premium descending, take top N
    unusual.sort(key=lambda x: x["premium"], reverse=True)
    unusual = unusual[:limit]

    return {
        "ticker": ticker,
        "spot": spot,
        "unusual": unusual,
        "n_scanned": len(contracts),
        "n_unusual": len(unusual),
        "mean_iv": round(mean_iv, 4),
        "iv_threshold": round(iv_threshold, 4),
    }
