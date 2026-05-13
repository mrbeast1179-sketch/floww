"""SPY options chain fetcher with yfinance spot price.

Strategy to conserve Databento credits:
  - Pull SPY definitions for a single trading day (cheap, small metadata).
  - Pull statistics schema for SettlementPrice + OpenInterest for that day.
  - Compute IV + Greeks locally.
  - Cache the entire snapshot in MongoDB; only refresh when user explicitly requests.
  - Use yfinance for spot prices (free, no Databento credits).

If Databento isn't reachable or returns nothing usable, we fall back to a
realistic synthetic SPY chain so the terminal still renders. Synthetic snapshots
are marked source="synthetic".
"""
from __future__ import annotations
import os
import math
import random
import logging
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any
try:
    import databento as db
    HAS_DATABENTO = True
except ImportError:
    HAS_DATABENTO = False
from greeks import greeks as compute_greeks, implied_vol

logger = logging.getLogger(__name__)
RISK_FREE = 0.045  # 4.5% approx
DIV_YIELD = 0.013  # SPY ~1.3%


def _get_spot_yf(symbol: str) -> float | None:
    """Fetch spot price from yfinance (free, no Databento credits)."""
    try:
        import yfinance as yf
        t = yf.Ticker(symbol)
        info = t.fast_info
        price = info.get("last_price") if hasattr(info, "get") else None
        if price is None:
            hist = t.history(period="1d")
            if not hist.empty:
                price = float(hist["Close"].iloc[-1])
        return float(price) if price else None
    except Exception as e:
        logger.warning(f"yfinance spot fetch failed for {symbol}: {e}")
        return None


def _synthetic_snapshot(spot: float = 585.0, num_strikes: int = 41) -> Dict[str, Any]:
    """Build a realistic-looking SPY snapshot when Databento data is unavailable."""
    today = datetime.now(timezone.utc).date()
    # Pick next Friday as expiry
    days_ahead = (4 - today.weekday()) % 7
    if days_ahead == 0:
        days_ahead = 7
    expiry = today + timedelta(days=days_ahead)
    T = max(days_ahead / 365.0, 1 / 365.0)

    strikes = []
    step = 1.0
    start = round(spot - (num_strikes // 2) * step)
    for i in range(num_strikes):
        strikes.append(start + i * step)

    contracts = []
    rng = random.Random(42)
    for K in strikes:
        # IV smile
        moneyness = (K - spot) / spot
        iv = 0.13 + 0.45 * moneyness * moneyness + 0.02 * rng.random()
        # OI distribution peaks near ATM
        base_oi = int(20000 * math.exp(-((K - spot) ** 2) / (2 * 8 ** 2)))
        call_oi = max(100, base_oi + rng.randint(-2000, 2000))
        put_oi = max(100, base_oi + rng.randint(-2000, 2000))
        # Make some strikes "high conviction" (round numbers)
        if int(K) % 5 == 0:
            call_oi = int(call_oi * 1.6)
            put_oi = int(put_oi * 1.6)
        for opt, oi in (("C", call_oi), ("P", put_oi)):
            contracts.append({
                "strike": float(K),
                "type": opt,
                "open_interest": oi,
                "iv": iv,
                "expiry": expiry.isoformat(),
                "T": T,
            })
    return _aggregate(contracts, spot, source="synthetic")


def _aggregate(contracts: List[Dict[str, Any]], spot: float, source: str) -> Dict[str, Any]:
    """Compute per-strike greek exposures and aggregate stats. SPY contract mult = 100."""
    by_strike: Dict[float, Dict[str, float]] = {}
    totals = {"delta": 0.0, "gamma": 0.0, "vega": 0.0, "theta": 0.0,
              "vanna": 0.0, "charm": 0.0, "vomma": 0.0,
              "call_oi": 0, "put_oi": 0}

    for c in contracts:
        K = c["strike"]
        opt = c["type"]
        oi = c["open_interest"]
        iv = c["iv"]
        T = c["T"]
        g = compute_greeks(spot, K, T, RISK_FREE, iv, opt, DIV_YIELD)
        sign = 1 if opt == "C" else -1
        # Dealer convention: dealer is assumed SHORT what customers are LONG.
        row = by_strike.setdefault(K, {
            "strike": K, "gex": 0.0, "vex": 0.0, "dex": 0.0,
            "charm_exp": 0.0, "vanna_exp": 0.0, "theta_exp": 0.0, "vomma_exp": 0.0,
            "call_oi": 0, "put_oi": 0,
        })
        row["gex"] += sign * g["gamma"] * oi * 100 * spot  # dollar gamma per 1% move
        row["vex"] += sign * g["vanna"] * oi * 100
        row["dex"] += sign * g["delta"] * oi * 100
        row["charm_exp"] += sign * g["charm"] * oi * 100
        row["vanna_exp"] += sign * g["vanna"] * oi * 100
        row["theta_exp"] += sign * g["theta"] * oi * 100
        row["vomma_exp"] += sign * g["vomma"] * oi * 100
        if opt == "C":
            row["call_oi"] += oi
            totals["call_oi"] += oi
        else:
            row["put_oi"] += oi
            totals["put_oi"] += oi
        # Totals: market net (calls - puts)
        for k in ("delta", "gamma", "vega", "theta", "vanna", "charm", "vomma"):
            totals[k] += sign * g[k] * oi * 100

    rows = sorted(by_strike.values(), key=lambda r: r["strike"])
    # Identify King Node = strike with max |gex|
    king = max(rows, key=lambda r: abs(r["gex"])) if rows else None
    # Gamma flip = strike where cumulative GEX (from below) crosses zero
    flip = None
    cum = 0.0
    for r in rows:
        cum += r["gex"]
        if flip is None and cum > 0 and r["strike"] >= spot * 0.95:
            flip = r["strike"]
            break

    # Expirations list (unique)
    expiries = sorted({c["expiry"] for c in contracts})

    return {
        "source": source,
        "spot": spot,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "expiries": expiries,
        "strikes": rows,
        "totals": totals,
        "king_node": king["strike"] if king else None,
        "gamma_flip": flip,
        "summary": {
            "net_gex": sum(r["gex"] for r in rows),
            "net_vex": sum(r["vex"] for r in rows),
            "net_dex": sum(r["dex"] for r in rows),
            "pcr_oi": (totals["put_oi"] / totals["call_oi"]) if totals["call_oi"] else 0.0,
        }
    }


def fetch_spy_snapshot_databento() -> Dict[str, Any]:
    """Fetch SPY options snapshot from Databento. Falls back to synthetic on error.

    NOTE: This is the ONLY place that spends Databento credits. Only called when
    user explicitly clicks Refresh.
    """
    if not HAS_DATABENTO:
        logger.warning("Databento not installed; using synthetic data")
        spot = _get_spot_yf("SPY") or 585.0
        return _synthetic_snapshot(spot=spot)

    key = os.environ.get("DATABENTO_API_KEY")
    if not key:
        logger.warning("No DATABENTO_API_KEY set; using synthetic data")
        spot = _get_spot_yf("SPY") or 585.0
        return _synthetic_snapshot(spot=spot)

    try:
        client = db.Historical(key)
        end = datetime.now(timezone.utc) - timedelta(days=1)
        start = end - timedelta(days=2)

        # Get spot from yfinance (free)
        spot = _get_spot_yf("SPY") or 585.0

        # Definitions: instrument metadata
        defs = client.timeseries.get_range(
            dataset="OPRA.PILLAR",
            schema="definition",
            symbols="SPY.OPT",
            stype_in="parent",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            limit=20000,
        )
        defs_df = defs.to_df()
        if defs_df.empty:
            logger.warning("Databento definitions empty; using synthetic")
            return _synthetic_snapshot(spot=spot)

        # Statistics: open interest + settlement price
        stats = client.timeseries.get_range(
            dataset="OPRA.PILLAR",
            schema="statistics",
            symbols="SPY.OPT",
            stype_in="parent",
            start=start.strftime("%Y-%m-%d"),
            end=end.strftime("%Y-%m-%d"),
            limit=50000,
        )
        stats_df = stats.to_df()

        # Build a map: instrument_id -> {strike, expiry, type}
        meta = {}
        for _, r in defs_df.iterrows():
            try:
                meta[int(r["instrument_id"])] = {
                    "strike": float(r["strike_price"]) / 1e9 if r["strike_price"] > 1e6 else float(r["strike_price"]),
                    "expiry": str(r.get("expiration", ""))[:10],
                    "type": "C" if str(r.get("instrument_class", "C")).upper().startswith("C") else "P",
                }
            except Exception:
                continue

        # Group statistics by instrument
        contracts = []
        if not stats_df.empty:
            grouped = stats_df.groupby("instrument_id")
            for iid, g in grouped:
                m = meta.get(int(iid))
                if not m:
                    continue
                settle = g["price"].dropna().iloc[-1] if "price" in g and not g["price"].dropna().empty else None
                oi = int(g["quantity"].dropna().iloc[-1]) if "quantity" in g and not g["quantity"].dropna().empty else 0
                if settle is None or oi <= 0:
                    continue
                try:
                    exp = datetime.fromisoformat(m["expiry"]).date()
                except Exception:
                    continue
                today = datetime.now(timezone.utc).date()
                days = (exp - today).days
                if days < 0 or days > 60:
                    continue
                T = max(days / 365.0, 1 / 365.0)
                iv = implied_vol(float(settle), spot, m["strike"], T, RISK_FREE, m["type"], DIV_YIELD)
                if not iv or iv <= 0 or iv > 3:
                    iv = 0.2
                contracts.append({
                    "strike": m["strike"],
                    "type": m["type"],
                    "open_interest": oi,
                    "iv": iv,
                    "expiry": m["expiry"],
                    "T": T,
                })

        if not contracts:
            logger.warning("No usable Databento contracts; using synthetic")
            return _synthetic_snapshot(spot=spot)

        return _aggregate(contracts, spot, source="databento")

    except Exception as e:
        logger.exception(f"Databento fetch failed: {e}; using synthetic")
        spot = _get_spot_yf("SPY") or 585.0
        return _synthetic_snapshot(spot=spot)


def get_spot(symbol: str) -> Dict[str, Any]:
    """Return spot price for any ticker. Free (yfinance), no Databento credits."""
    sym = symbol.upper()
    price = _get_spot_yf(sym)
    return {
        "symbol": sym,
        "price": price,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "source": "yfinance" if price else "unavailable",
    }
