"""
backend/services/flowseeker.py

Skylit-parity Flowseeker — live institutional options flow with classification
and contract drilldown.

Replaces the FRONTEND "demo mode" (SKYLIT_FEATURES.md line 144) by exposing
real options flow data through a thin service layer over FlashAlpha
(backend/flashalpha_client.py). FlashAlpha's `/v1/flow/options/{symbol}/recent`
is the primary source — it covers the institutional prints Skylit's
Flowseeker UI shows. Databento OPRA.PILLAR `stream_live_trades`
(databento_provider.py:206) is the streaming complement; this module
deliberately stays on the request/response HTTP path so the surface stays
testable without a live websocket subscription.

20-column print shape (mirrors Skylit Flowseeker UI):
    timestamp, ticker, strike, expiration, side, type,
    size, price, premium, volume, oi, vol_oi_ratio,
    chain_ratio, classification, conditions, ask_pct,
    spot, bid, ask, exchange

Classification rules:
    sweep    — multiple exchanges within 1s window AND size > 100
    block    — single exchange AND size >= 500
    unusual  — vol_oi_ratio > 2.0 OR premium > $100k
    regular  — anything else
The four classes are evaluated in order: sweep > block > unusual > regular.

All functions degrade gracefully — if FlashAlpha returns None (no key, rate
limit, 403), `fetch_live_flow` returns []. The route layer translates an
empty list to a 200 with `[]` body so the frontend never crashes.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Classification thresholds (centralized so tests can reference them)
# ---------------------------------------------------------------------------

SWEEP_MIN_SIZE: int = 100
SWEEP_TIME_WINDOW_SEC: float = 1.0
BLOCK_MIN_SIZE: int = 500
UNUSUAL_VOL_OI_RATIO: float = 2.0
UNUSUAL_PREMIUM_USD: float = 100_000.0


# ---------------------------------------------------------------------------
# Helpers — coercion is tolerant because FlashAlpha keys vary by endpoint
# ---------------------------------------------------------------------------

def _f(val: Any, default: float = 0.0) -> float:
    """Coerce to float; tolerate None / strings / bad types."""
    try:
        if val is None:
            return default
        return float(val)
    except (TypeError, ValueError):
        return default


def _i(val: Any, default: int = 0) -> int:
    """Coerce to int (via float so '12.0' works)."""
    try:
        if val is None:
            return default
        return int(float(val))
    except (TypeError, ValueError):
        return default


def _first(d: Dict[str, Any], *keys: str, default: Any = None) -> Any:
    """Return the first present, non-None value among ``keys`` in ``d``."""
    for k in keys:
        if k in d and d[k] is not None:
            return d[k]
    return default


def _exchanges(row: Dict[str, Any]) -> List[str]:
    """
    Pull exchange list from a print row. FlashAlpha sometimes returns a single
    `exchange` string and sometimes a `exchanges` list. Returns at least an
    empty list.
    """
    raw = row.get("exchanges")
    if isinstance(raw, list):
        return [str(x) for x in raw if x]
    single = row.get("exchange")
    if isinstance(single, str) and single:
        return [single]
    return []


# ---------------------------------------------------------------------------
# Classification
# ---------------------------------------------------------------------------

def classify_print(row: Dict[str, Any]) -> str:
    """
    Classify a single options print into sweep / block / unusual / regular.

    Order of precedence:
        1. sweep   — multiple exchanges within 1s window AND size > 100
        2. block   — single exchange AND size >= 500
        3. unusual — vol_oi_ratio > 2.0 OR premium > $100k
        4. regular — anything else

    Robust to missing/None fields. ``vol_oi_ratio`` is recomputed from
    ``volume`` and ``oi`` if not pre-set, with a zero-OI guard.
    """
    if not isinstance(row, dict):
        return "regular"

    size = _i(_first(row, "size", "quantity", "trade_size"))
    premium = _f(_first(row, "premium", "notional"))
    exchanges = _exchanges(row)
    time_window = _f(_first(row, "time_window_sec", "time_window"))

    # Sweep: multi-leg across exchanges in a short window. The "1s" rule is
    # encoded in two ways depending on what the upstream provides:
    #   (a) explicit time_window_sec field
    #   (b) ``is_sweep`` boolean from upstream
    is_sweep_flag = bool(row.get("is_sweep") or row.get("sweep"))
    multi_exchange = len(exchanges) > 1
    sweep_window_ok = (
        time_window > 0 and time_window <= SWEEP_TIME_WINDOW_SEC
    ) or is_sweep_flag
    if size > SWEEP_MIN_SIZE and multi_exchange and sweep_window_ok:
        return "sweep"

    # Block: large single-exchange print
    single_exchange = len(exchanges) <= 1
    if size >= BLOCK_MIN_SIZE and single_exchange:
        return "block"

    # Unusual: vol/OI imbalance or huge dollar premium
    volume = _f(_first(row, "volume"))
    oi = _f(_first(row, "oi", "open_interest"))
    pre_ratio = row.get("vol_oi_ratio")
    if pre_ratio is not None:
        vol_oi_ratio = _f(pre_ratio)
    else:
        vol_oi_ratio = (volume / oi) if oi > 0 else 0.0
    if vol_oi_ratio > UNUSUAL_VOL_OI_RATIO or premium > UNUSUAL_PREMIUM_USD:
        return "unusual"

    return "regular"


# ---------------------------------------------------------------------------
# Normalization: upstream row -> 20-column Flowseeker shape
# ---------------------------------------------------------------------------

def _normalize_print(raw: Dict[str, Any], ticker_hint: Optional[str] = None) -> Dict[str, Any]:
    """
    Map a single upstream row to the canonical 20-column Flowseeker shape.

    FlashAlpha's various flow endpoints use slightly different keys (e.g.
    ``oi`` vs ``open_interest``, ``side`` vs ``trade_side``); this helper
    flattens them. Fields not provided by upstream get sane defaults (0 for
    numerics, "" for strings, [] for conditions).
    """
    if not isinstance(raw, dict):
        return {}

    exchanges = _exchanges(raw)
    exchange = exchanges[0] if exchanges else str(raw.get("exchange", "") or "")
    volume = _f(_first(raw, "volume"))
    oi = _f(_first(raw, "oi", "open_interest"))
    pre_ratio = raw.get("vol_oi_ratio")
    vol_oi_ratio = _f(pre_ratio) if pre_ratio is not None else ((volume / oi) if oi > 0 else 0.0)

    conditions = raw.get("conditions")
    if not isinstance(conditions, list):
        conditions = [str(conditions)] if conditions else []

    row = {
        "timestamp": _first(raw, "timestamp", "ts", "time", "trade_time", default=""),
        "ticker": str(_first(raw, "ticker", "underlying", "symbol", default=ticker_hint or "") or "").upper(),
        "strike": _f(_first(raw, "strike", "strike_price")),
        "expiration": str(_first(raw, "expiration", "expiry", "expiration_date", default="") or ""),
        "side": str(_first(raw, "side", "trade_side", default="") or ""),
        "type": str(_first(raw, "type", "option_type", "right", default="") or "").upper(),
        "size": _i(_first(raw, "size", "quantity", "trade_size")),
        "price": _f(_first(raw, "price", "fill_price", "trade_price")),
        "premium": _f(_first(raw, "premium", "notional")),
        "volume": volume,
        "oi": oi,
        "vol_oi_ratio": vol_oi_ratio,
        "chain_ratio": _f(_first(raw, "chain_ratio")),
        "classification": "",  # filled below
        "conditions": conditions,
        "ask_pct": _f(_first(raw, "ask_pct", "fill_pct", "premium_pct")),
        "spot": _f(_first(raw, "spot", "underlying_price")),
        "bid": _f(_first(raw, "bid")),
        "ask": _f(_first(raw, "ask")),
        "exchange": exchange,
    }
    row["classification"] = classify_print(raw)
    return row


# ---------------------------------------------------------------------------
# Provider lookup
# ---------------------------------------------------------------------------

def _get_client():
    """
    Lazy-import the FlashAlphaClient so this module stays importable in
    environments without aiohttp (e.g. unit tests). Tests patch this symbol.
    """
    from flashalpha_client import FlashAlphaClient
    return FlashAlphaClient()


def _extract_prints(payload: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Tease the print list out of a FlashAlpha response. The API wraps results
    differently per endpoint — sometimes ``{"data": [...]}``, sometimes
    ``{"prints": [...]}``, sometimes the list at the top level. Returns []
    if nothing matches.
    """
    if payload is None:
        return []
    if isinstance(payload, list):
        return [r for r in payload if isinstance(r, dict)]
    if not isinstance(payload, dict):
        return []
    for k in ("prints", "data", "results", "flow", "trades"):
        val = payload.get(k)
        if isinstance(val, list):
            return [r for r in val if isinstance(r, dict)]
    return []


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def fetch_live_flow(
    ticker: Optional[str] = None,
    *,
    limit: int = 50,
    min_premium: float = 0.0,
) -> List[Dict[str, Any]]:
    """
    Fetch live institutional options flow.

    Args:
        ticker: Optional ticker symbol. If None, returns cross-ticker outliers.
        limit: Max number of prints to return (post-filter).
        min_premium: Filter out prints with premium below this dollar threshold.

    Returns:
        List of dicts in the 20-column Flowseeker shape. Empty list if the
        provider is unavailable, rate-limited, or returns nothing. Never
        raises.
    """
    if limit <= 0:
        return []
    client = _get_client()
    try:
        if ticker:
            sym = ticker.strip().upper()
            payload = await client.get_options_flow_recent(sym)
            if not payload:
                # fall back to live flow endpoint (different tier)
                payload = await client.get_flow_live(sym)
        else:
            payload = await client.get_options_flow_outliers()
    except Exception as e:
        logger.warning(f"flowseeker: provider error: {e}")
        return []

    raw_prints = _extract_prints(payload)
    out: List[Dict[str, Any]] = []
    for raw in raw_prints:
        row = _normalize_print(raw, ticker_hint=ticker)
        if not row:
            continue
        if ticker and row.get("ticker") and row["ticker"] != ticker.strip().upper():
            continue
        if row["premium"] < min_premium:
            continue
        out.append(row)
        if len(out) >= limit:
            break
    return out


async def contract_drilldown(symbol: str) -> Dict[str, Any]:
    """
    Contract-level drilldown: volume, OI, chain ratio, recent prints, vol/OI
    history.

    Args:
        symbol: Either a parent ticker (e.g. "SPY") for chain-level stats, or
            an OSI-style option symbol if the upstream supports it. FlashAlpha
            indexes by parent symbol, so the parent ticker is the practical
            input.

    Returns:
        Dict with:
            volume, oi, chain_ratio          — current chain stats
            recent_prints: List[Dict]        — last N prints, normalized
            vol_oi_history: List[float]      — last 20 daily vol/OI ratios
                                              (empty if not exposed by upstream)
        Always returns a well-formed dict; empty fields on provider failure.
    """
    sym = (symbol or "").strip().upper()
    empty: Dict[str, Any] = {
        "symbol": sym,
        "volume": 0.0,
        "oi": 0.0,
        "chain_ratio": 0.0,
        "recent_prints": [],
        "vol_oi_history": [],
    }
    if not sym:
        return empty

    client = _get_client()

    # Recent prints (chain context)
    try:
        recent_payload = await client.get_options_flow_recent(sym)
    except Exception as e:
        logger.warning(f"flowseeker drilldown: recent error: {e}")
        recent_payload = None

    # Aggregate summary (volume / OI rollup)
    try:
        summary_payload = await client.get_options_flow_summary(sym)
    except Exception as e:
        logger.warning(f"flowseeker drilldown: summary error: {e}")
        summary_payload = None

    # History (optional — many tiers don't expose it; tolerate)
    try:
        history_payload = await client.get_options_flow_history(sym)
    except Exception as e:
        logger.warning(f"flowseeker drilldown: history error: {e}")
        history_payload = None

    recent_prints = [_normalize_print(r, ticker_hint=sym) for r in _extract_prints(recent_payload)]
    recent_prints = [r for r in recent_prints if r]

    total_volume = 0.0
    total_oi = 0.0
    chain_ratio = 0.0
    if isinstance(summary_payload, dict):
        # FlashAlpha summary keys vary; coerce defensively.
        total_volume = _f(_first(summary_payload, "total_volume", "volume"))
        total_oi = _f(_first(summary_payload, "total_oi", "open_interest", "oi"))
        chain_ratio = _f(_first(summary_payload, "chain_ratio", "call_put_ratio"))

    # Vol/OI history extraction — accept a list of floats or list of dicts.
    vol_oi_history: List[float] = []
    hist_rows: List[Any] = []
    if isinstance(history_payload, dict):
        for k in ("history", "data", "vol_oi_history", "results"):
            v = history_payload.get(k)
            if isinstance(v, list):
                hist_rows = v
                break
    elif isinstance(history_payload, list):
        hist_rows = history_payload
    for h in hist_rows[:20]:
        if isinstance(h, (int, float)):
            vol_oi_history.append(_f(h))
        elif isinstance(h, dict):
            ratio = _first(h, "vol_oi_ratio", "ratio")
            if ratio is not None:
                vol_oi_history.append(_f(ratio))
            else:
                vol = _f(_first(h, "volume"))
                oi_h = _f(_first(h, "oi", "open_interest"))
                if oi_h > 0:
                    vol_oi_history.append(vol / oi_h)

    return {
        "symbol": sym,
        "volume": total_volume,
        "oi": total_oi,
        "chain_ratio": chain_ratio,
        "recent_prints": recent_prints,
        "vol_oi_history": vol_oi_history,
    }
