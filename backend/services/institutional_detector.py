"""
backend/services/institutional_detector.py

Blademap-style institutional positioning detection.

Pure-Python implementation of the conviction-scoring system from the
Blademap.ai blueprint. Computes per-alert:

  • conviction_score (0–100)  ← sum of four weighted sub-scores
  • sub_scores: {statistical_anomaly, institutional_pattern, market_context, price_impact}
  • key_levels: {entry, invalidation, target}
  • context.market_regime, context.dealer_positioning
  • rationale  (one sentence "why this is bullish/bearish")
  • recommended_actions: list[str]
  • signal_type ∈ {CALL_SWEEP, PUT_SWEEP, CALL_BLOCK, PUT_BLOCK, FLOOR_SWEEP,
                   GOLDEN_SWEEP, HIGH_VOLUME, HIGH_IV, OI_SPIKE,
                   DELTA_EXTREME, PREMIUM_CONCENTRATION, UNUSUAL_VOL_OI}

Design constraints (Round 9 freeze):
  - Imports only stdlib + numpy. NEVER torch, NEVER numba.
    route layer imports this synchronously and crashes are unacceptable.
  - Inputs are dicts shaped like CVForge cvserver ``get_chain`` rows.
  - Output matches the Blademap blueprint alert JSON exactly.

This module is a self-contained heuristic. It uses inline 1-D GEX math
to locate the zero-gamma crossing strike (no numba decorator). For richer
features (HMM regime, Hawkes firing rate, VPIN) the route layer is free
to wrap and feed extra context fields.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Iterable
from datetime import datetime
from typing import Any

log = logging.getLogger(__name__)


# ----------------------------------------------------------------------------
# Sub-score caps (per Blademap blueprint, totals must equal 100 max)
# ----------------------------------------------------------------------------
STATISTICAL_ANOMALY_MAX = 30
INSTITUTIONAL_PATTERN_MAX = 25
MARKET_CONTEXT_MAX = 20
PRICE_IMPACT_MAX = 25


# ----------------------------------------------------------------------------
# Signal-type constants — canonical names from the Blademap blueprint
# ----------------------------------------------------------------------------
SIGNAL_HIGH_VOLUME = "HIGH_VOLUME"
SIGNAL_HIGH_IV = "HIGH_IV"
SIGNAL_OI_SPIKE = "OI_SPIKE"
SIGNAL_DELTA_EXTREME = "DELTA_EXTREME"
SIGNAL_PREMIUM_CONCENTRATION = "PREMIUM_CONCENTRATION"
SIGNAL_FLOOR_SWEEP = "FLOOR_SWEEP"
SIGNAL_GOLDEN_SWEEP = "GOLDEN_SWEEP"
SIGNAL_CALL_SWEEP = "CALL_SWEEP"
SIGNAL_PUT_SWEEP = "PUT_SWEEP"
SIGNAL_CALL_BLOCK = "CALL_BLOCK"
SIGNAL_PUT_BLOCK = "PUT_BLOCK"
SIGNAL_UNUSUAL_VOL_OI = "UNUSUAL_VOL_OI"

# Bucket → slate / colour chips the frontend maps. Keeps brand consistency.
SIGNAL_TYPE_COLORS: dict[str, str] = {
    SIGNAL_HIGH_VOLUME: "#fbbf24",          # amber
    SIGNAL_HIGH_IV: "#f43f5e",              # rose
    SIGNAL_OI_SPIKE: "#a855f7",             # purple
    SIGNAL_DELTA_EXTREME: "#38bdf8",        # sky
    SIGNAL_PREMIUM_CONCENTRATION: "#22c55e",
    SIGNAL_FLOOR_SWEEP: "#2dd4bf",          # teal — dealer floor buy-in
    SIGNAL_GOLDEN_SWEEP: "#facc15",         # gold — zero-gamma flip area
    SIGNAL_CALL_SWEEP: "#fb7185",
    SIGNAL_PUT_SWEEP: "#34d399",
    SIGNAL_CALL_BLOCK: "#84cc16",
    SIGNAL_PUT_BLOCK: "#fb923c",
    SIGNAL_UNUSUAL_VOL_OI: "#94a3b8",
}


def _safe_float(v: Any, default: float = 0.0) -> float:
    if v is None:
        return default
    try:
        f = float(v)
        if math.isnan(f) or math.isinf(f):
            return default
        return f
    except (TypeError, ValueError):
        return default


def _distance_pct(strike: float, ref: float) -> float:
    """Return |strike-ref|/ref as a fraction. 0 if either side is 0."""
    if ref <= 0:
        return float("inf")
    return abs(strike - ref) / ref


# ----------------------------------------------------------------------------
# 1-D GEX aggregation (inline, no numba)
# ----------------------------------------------------------------------------
# We need a quick proxy of "where does dealer net-GEX cross zero" to feed
# the FLOOR_SWEEP / GOLDEN_SWEEP detection and the key_levels.invalidation.
# The shape mirrors gex_aggregator.aggregate_gex_1d but stays pure-python.

SIGN_CALL = 1   # dealer short call → contributes + GEX
SIGN_PUT = -1   # dealer short put  → contributes - GEX


def _aggregate_gex_1d(
    spot: float,
    rows: Iterable[dict[str, Any]],
    key_strike: str = "strike",
    key_gamma: str = "gamma",
    key_oi: str = "open_interest",
    key_type: str = "type",
) -> tuple[list[float], list[float]]:
    """
    Return (strikes_sorted, net_gex_per_strike).

    GEX contribution per contract = sign * gamma * OI * 100 * spot^2 * 0.01
    where sign = +1 (call) when dealers are short, -1 (put).
    """
    if spot <= 0:
        return [], []

    bucket: dict[float, float] = {}
    scale = spot * spot * 0.01 * 100.0
    for r in rows:
        strike = _safe_float(r.get(key_strike))
        gamma = _safe_float(r.get(key_gamma))
        oi = _safe_float(r.get(key_oi))
        t = r.get(key_type)
        if strike <= 0 or gamma == 0 or oi == 0:
            continue
        sign = SIGN_CALL if _is_call(t) else SIGN_PUT if _is_put(t) else 0
        if sign == 0:
            continue
        bucket[strike] = bucket.get(strike, 0.0) + sign * gamma * oi * scale

    if not bucket:
        return [], []

    strikes_sorted = sorted(bucket.keys())
    return strikes_sorted, [bucket[s] for s in strikes_sorted]


def _is_call(t: Any) -> bool:
    if t is None:
        return False
    s = str(t).strip().upper()
    return s in {"CALL", "C", "0"}


def _is_put(t: Any) -> bool:
    if t is None:
        return False
    s = str(t).strip().upper()
    return s in {"PUT", "P", "1"}


def _find_zero_gama_cross(strikes: list[float], gex: list[float]) -> float | None:
    """Linear-interp first strike where 1-D net GEX crosses zero."""
    if len(strikes) < 2 or len(gex) < 2:
        return None
    for i in range(len(strikes) - 1):
        a, b = gex[i], gex[i + 1]
        if (a > 0 and b < 0) or (a < 0 and b > 0):
            denom = a - b
            if denom == 0:
                continue
            t = a / denom
            return strikes[i] + t * (strikes[i + 1] - strikes[i])
    return None


def _king_node(strikes: list[float], gex: list[float]) -> tuple[float | None, float | None]:
    """Return (king_strike, king_value) — strike with max |GEX|."""
    if not strikes:
        return None, None
    king_i = max(range(len(strikes)), key=lambda i: abs(gex[i]))
    return strikes[king_i], gex[king_i]


# ----------------------------------------------------------------------------
# Conviction sub-score helpers
# ----------------------------------------------------------------------------

def _score_vol_oi(ratio: float) -> tuple[int, list[str]]:
    """Statistical Anomaly component (0-30) from vol/OI ratio."""
    if ratio <= 0:
        return 0, []
    if ratio >= 5.0:
        return 30, [f"Vol/OI ratio: {ratio:.1f}x — extreme (30/30)"]
    if ratio >= 3.0:
        return 20, [f"Vol/OI ratio: {ratio:.1f}x — heavy (20/30)"]
    if ratio >= 2.0:
        return 12, [f"Vol/OI ratio: {ratio:.1f}x — unusual (12/30)"]
    if ratio >= 1.0:
        return 6, [f"Vol/OI ratio: {ratio:.1f}x — elevated (6/30)"]
    return 0, []


def _score_iv(iv: float, p75_iv: float, p90_iv: float) -> tuple[int, list[str]]:
    if iv <= 0 or p90_iv <= 0:
        return 0, []
    if iv >= p90_iv:
        return 10, [f"IV {iv*100:.1f}% ≥ 90th-pct {p90_iv*100:.1f}% (10 pts)"]
    if iv >= p75_iv:
        return 6, [f"IV {iv*100:.1f}% ≥ 75th-pct {p75_iv*100:.1f}% (6 pts)"]
    return 0, []


def _score_premium(premium: float) -> tuple[int, list[str]]:
    """Institutional Pattern component (0-25) from $/premium concentrated at strike."""
    if premium <= 0:
        return 0, []
    if premium >= 1_000_000:
        return 25, ["$1M+ premium concentrated (25/25)"]
    if premium >= 500_000:
        return 20, [f"${int(premium/1000)}K premium concentrated (20/25)"]
    if premium >= 250_000:
        return 12, [f"${int(premium/1000)}K premium concentration (12/25)"]
    if premium >= 100_000:
        return 6, [f"${int(premium/1000)}K premium (6/25)"]
    return 0, []


def _score_call_put_divergence(call_vol: float, put_vol: float) -> tuple[int, list[str]]:
    """Price Impact component (0-25) — directional volume divergence."""
    if call_vol <= 0 or put_vol <= 0:
        return 0, []
    ratio = max(call_vol, put_vol) / max(min(call_vol, put_vol), 1.0)
    if ratio >= 5.0:
        return 25, [f"Call/Put vol ratio {ratio:.1f}x — extreme divergence (25/25)"]
    if ratio >= 3.0:
        return 18, [f"Call/Put vol ratio {ratio:.1f}x — strong (18/25)"]
    if ratio >= 2.0:
        return 10, [f"Call/Put vol ratio {ratio:.1f}x — directional (10/25)"]
    return 0, []


def _score_zero_gamma_proximity(strike: float, cross: float | None, spot: float) -> tuple[int, list[str]]:
    """Market Context (0-20) — strike sits near the dealer-gamma-flip strike."""
    if cross is None or cross <= 0 or spot <= 0:
        return 0, []
    d_cross = _distance_pct(strike, cross)
    d_spot = _distance_pct(strike, spot)
    if d_cross <= 0.005:
        return 20, [f"Strike within 0.5% of zero-gamma flip ${cross:.1f} (20/20)"]
    if d_cross <= 0.01:
        return 14, [f"Strike within 1% of zero-gamma flip ${cross:.1f} (14/20)"]
    if d_cross <= 0.03 and d_spot <= 0.05:
        return 8, [f"Near zero-gamma flip ${cross:.1f} and spot (8/20)"]
    return 0, []


# ----------------------------------------------------------------------------
# Direction inference
# ----------------------------------------------------------------------------

def _infer_direction(option_type: str, conviction_fits_bullish: bool) -> str:
    if option_type.upper() == "CALL":
        return "BULLISH" if conviction_fits_bullish else "BEARISH"
    if option_type.upper() == "PUT":
        return "BEARISH" if conviction_fits_bullish else "BULLISH"
    return "NEUTRAL"


# ----------------------------------------------------------------------------
# Tier mapping (T1 = highest conviction)
# ----------------------------------------------------------------------------

def _score_to_tier(score: int) -> int:
    if score >= 80:
        return 1
    if score >= 65:
        return 2
    if score >= 50:
        return 3
    if score >= 35:
        return 4
    return 5


# ----------------------------------------------------------------------------
# Main detector
# ----------------------------------------------------------------------------

class BlademapDetector:
    """
    Convert a single CVForge-style per-strike row into a Blademap alert.

    Usage:

        detector = BlademapDetector(ticker="SPY", spot=585.0)
        for row in chain_data["chain"][i]["strikes"]:
            alert = detector.detect(row, all_rows=strikes_flat)
            alerts.append(alert)

    ``all_rows`` is an iterable of dicts (the same shape as ``row``) used
    for chain-wide statistics (75th/90th IV percentile, 1-D GEX zero-cross).
    If not provided, only per-row heuristics run (sub-scores still valid).
    """

    def __init__(self, ticker: str, spot: float | None = None):
        self.ticker = (ticker or "").upper()
        self.spot = _safe_float(spot)

    # ---- Pre-pass: chain-wide stats from all_rows ----

    def _chain_stats(
        self, all_rows: Iterable[dict[str, Any]]
    ) -> tuple[float, float, float | None, float | None]:
        """Return (p75_iv, p90_iv, zero_gamma_cross, premium_at_spot)."""
        # NOTE: ``all_rows`` is the side-aware GEX row set (one CALL-side row
        # and one PUT-side row per strike), so we sample roughly 2x per strike
        # to get a blended call+put IV distribution across the whole chain.
        # Don't 'optimise' this back to single-side — the blend is intentional.
        ivs: list[float] = []
        for r in all_rows:
            for k in ("impliedVolatility", "iv"):
                v = _safe_float(r.get(k))
                if v > 0:
                    ivs.append(v)
                    break
        ivs.sort()
        p75 = ivs[int(len(ivs) * 0.75)] if ivs else 0.0
        p90 = ivs[int(len(ivs) * 0.90)] if ivs else 0.0

        cross = None
        if self.spot and self.spot > 0:
            strikes, gex = _aggregate_gex_1d(self.spot, all_rows)
            if strikes:
                cross = _find_zero_gama_cross(strikes, gex)

        return p75, p90, cross, None  # premium-at-spot is computed per-row

    # ---- Per-row detection ----

    def detect(
        self,
        row: dict[str, Any],
        all_rows: Iterable[dict[str, Any]] | None = None,
    ) -> dict[str, Any] | None:
        if not isinstance(row, dict):
            return None

        strike = _safe_float(row.get("strike"))
        call_oi = _safe_float(row.get("call_oi"))
        put_oi = _safe_float(row.get("put_oi"))
        call_vol = _safe_float(row.get("call_vol"))
        put_vol = _safe_float(row.get("put_vol"))
        call_iv = _safe_float(row.get("call_iv"))
        put_iv = _safe_float(row.get("put_iv"))
        call_delta = _safe_float(row.get("call_delta"))
        put_delta = _safe_float(row.get("put_delta"))
        call_bid = _safe_float(row.get("call_bid"))
        call_ask = _safe_float(row.get("call_ask"))
        put_bid = _safe_float(row.get("put_bid"))
        put_ask = _safe_float(row.get("put_ask"))

        # Skip empty rows
        if strike <= 0 or (call_oi + put_oi + call_vol + put_vol <= 0):
            return None

        p75_iv = p90_iv = 0.0
        cross = None
        if all_rows is not None:
            try:
                p75_iv, p90_iv, cross, _ = self._chain_stats(all_rows)
            except Exception as e:  # chain stats must NEVER crash alert loop
                log.debug("chain stats failed for %s: %s", self.ticker, e)

        total_oi = call_oi + put_oi
        total_vol = call_vol + put_vol
        vol_oi_ratio = (total_vol / total_oi) if total_oi > 0 else 0.0

        # ---- Per-row eligibility: what signal types are candidates ----
        candidates: list[str] = []
        reasons: list[str] = []

        if total_oi > 0 and vol_oi_ratio >= 1.0 and total_vol > 50:
            candidates.append(SIGNAL_UNUSUAL_VOL_OI)
        if call_iv > 0 and p90_iv > 0 and call_iv >= p90_iv and total_oi >= 500:
            candidates.append(SIGNAL_HIGH_IV)
        # OI spike detection: per-expiry mean comparison is intentionally
        # left to a future detector pass that has chain-of-expiry stats.
        # Today's pass only sees one expiry at a time.
        if (abs(call_delta) > 0.55 and call_oi > 200) or (
            abs(put_delta) > 0.55 and put_oi > 200
        ):
            candidates.append(SIGNAL_DELTA_EXTREME)

        call_mid = (call_bid + call_ask) / 2 if (call_bid > 0 and call_ask > 0) else 0.0
        premium_call = call_mid * (call_oi * 100.0) if call_mid > 0 else 0.0
        put_mid = (put_bid + put_ask) / 2 if (put_bid > 0 and put_ask > 0) else 0.0
        premium_put = put_mid * (put_oi * 100.0) if put_mid > 0 else 0.0
        premium = max(premium_call, premium_put)
        if premium >= 100_000:
            candidates.append(SIGNAL_PREMIUM_CONCENTRATION)

        # Floor sweep = deep ITM + unusually heavy at this strike (proxy for
        # institutional buy-in at the dealer's "floor").
        if (call_delta > 0.55 and call_vol > call_oi * 0.3 and call_oi > 500) or (
            put_delta < -0.55 and put_vol > put_oi * 0.3 and put_oi > 500
        ):
            candidates.append(SIGNAL_FLOOR_SWEEP)

        # Golden sweep — strike within 1% of zero-gamma flip + heavy activity.
        if (
            cross is not None
            and abs(strike - cross) / max(cross, 1.0) <= 0.01
            and total_vol > 100
            and total_oi > 300
        ):
            candidates.append(SIGNAL_GOLDEN_SWEEP)

        # Sweep / block proxies at the strike (no live flow feed — heuristic):
        if total_vol >= 500 and total_oi >= 500:
            if call_vol > put_vol * 1.5:
                candidates.append(SIGNAL_CALL_BLOCK)
            elif put_vol > call_vol * 1.5:
                candidates.append(SIGNAL_PUT_BLOCK)
            else:
                candidates.append(SIGNAL_UNUSUAL_VOL_OI)

        # Volume spike
        if total_vol > 0 and vol_oi_ratio >= 1.0 and total_vol > 200:
            candidates.append(SIGNAL_HIGH_VOLUME)

        if not candidates:
            return None

        # Pick the *primary* signal — priority order matters for the badge
        # colour and the rationale sentence.
        priority = [
            SIGNAL_GOLDEN_SWEEP,
            SIGNAL_FLOOR_SWEEP,
            SIGNAL_CALL_BLOCK,
            SIGNAL_PUT_BLOCK,
            SIGNAL_UNUSUAL_VOL_OI,
            SIGNAL_PREMIUM_CONCENTRATION,
            SIGNAL_DELTA_EXTREME,
            SIGNAL_HIGH_IV,
            SIGNAL_HIGH_VOLUME,
            SIGNAL_OI_SPIKE,
        ]
        primary = next((s for s in priority if s in candidates), candidates[0])
        reasons.append(f"Primary signal: {primary}")

        # ---- Direction ----
        put_heavy = put_vol > call_vol * 1.15 or abs(put_delta) > abs(call_delta)
        call_heavy = call_vol > put_vol * 1.15 or abs(call_delta) > abs(put_delta)
        if put_heavy:
            direction = "BEARISH"
            side = "PUT"
        elif call_heavy:
            direction = "BULLISH"
            side = "CALL"
        else:
            direction = "NEUTRAL"
            side = "CALL"

        # ---- Sub-scores ----
        sa_pts, sa_reasons = _score_vol_oi(vol_oi_ratio)
        iv_pts, iv_reasons = _score_iv(call_iv, p75_iv, p90_iv)
        stat_total = min(STATISTICAL_ANOMALY_MAX, sa_pts + iv_pts)

        prem_pts, prem_reasons = _score_premium(premium)
        pat_total = min(INSTITUTIONAL_PATTERN_MAX, prem_pts)

        ctx_pts, ctx_reasons = _score_zero_gamma_proximity(strike, cross, self.spot or 0.0)
        ctx_total = min(MARKET_CONTEXT_MAX, ctx_pts)

        pi_pts, pi_reasons = _score_call_put_divergence(call_vol, put_vol)
        imp_total = min(PRICE_IMPACT_MAX, pi_pts)

        conviction_score = stat_total + pat_total + ctx_total + imp_total
        conviction_score = max(0, min(100, conviction_score))

        # ---- GEX context (for header summary) ----
        dealer_positioning = (
            "net_short_gamma" if (cross is not None and self.spot and self.spot > 0 and abs((strike - cross) / max(self.spot, 1)) < 0.02 and pi_pts >= 10)
            else "net_long_gamma"
        )

        # Market regime heuristic — net directional volume dominance + vol
        if call_vol > 0 and put_vol > 0:
            ratio = call_vol / max(put_vol, 1)
            if ratio >= 2.0:
                market_regime = "BULLISH_VOLUME_SURGE"
            elif ratio <= 0.5:
                market_regime = "BEARISH_VOLUME_SURGE"
            elif vol_oi_ratio >= 2.0:
                market_regime = "VOL_EXPANSION"
            else:
                market_regime = "MEAN_REVERTING"
        else:
            market_regime = "QUIET"

        # ---- Key levels (rationale-driven, conservative defaults) ----
        spot = self.spot or strike
        invalidation = cross if cross is not None else (spot * 0.985 if direction == "BULLISH" else spot * 1.015)
        if direction == "BULLISH":
            target = max(spot + (spot - invalidation) * 3.0, strike * 1.02)
        else:
            target = min(spot - (invalidation - spot) * 3.0, strike * 0.98)

        # ---- Rationale ----
        if primary == SIGNAL_GOLDEN_SWEEP:
            rationale = (
                f"Heavy {side} activity at strike ${strike:.0f} sits within 1% of "
                f"the dealer zero-gamma flip (${cross:.2f}). A break past ${target:.2f} "
                f"could trigger dealer hedging that reinforces the move."
            )
        elif primary == SIGNAL_FLOOR_SWEEP:
            rationale = (
                f"Deep {'ITM' if side == 'CALL' else 'ITM put'} activity with elevated "
                f"volume vs. OI suggests institutional positioning at a structural floor."
            )
        elif primary in (SIGNAL_CALL_BLOCK, SIGNAL_PUT_BLOCK):
            rationale = (
                f"{'Bullish' if side == 'CALL' else 'Bearish'} block-sized activity "
                f"({total_vol:.0f} contracts vs. {total_oi:.0f} OI) signals "
                f"institutional accumulation."
            )
        elif primary == SIGNAL_PREMIUM_CONCENTRATION:
            rationale = (
                f"${int(premium/1000)}K of premium concentrated at ${strike:.0f} {side} — "
                f"size alone makes this a {direction.lower()} signal."
            )
        elif primary == SIGNAL_DELTA_EXTREME:
            rationale = (
                f"Deep ITM {side} (delta {call_delta if side == 'CALL' else abs(put_delta):.2f}) "
                f"with {total_oi:.0f} OI — looks like a hedge leg or conviction add."
            )
        elif primary == SIGNAL_HIGH_IV:
            rationale = (
                f"IV at the 90th-percentile of the chain ({call_iv*100:.1f}%) — vol expansion "
                f"concentrated at ${strike:.0f}."
            )
        else:  # HIGH_VOLUME / UNUSUAL_VOL_OI / OI_SPIKE
            rationale = (
                f"Unusual volume relative to open interest "
                f"({vol_oi_ratio:.1f}x) at ${strike:.0f} {side} — flow-to-position "
                f"imbalance worth watching."
            )

        # ---- Recommended actions ----
        recommended_actions: list[str] = []
        if conviction_score >= 65:
            recommended_actions.append(
                f"Watch for confirmation {'above' if direction == 'BULLISH' else 'below'} "
                f"${strike:.2f} before entering."
            )
            recommended_actions.append(f"Set invalidation at ${invalidation:.2f}.")
            recommended_actions.append(f"Primary target: ${target:.2f}.")
        elif conviction_score >= 40:
            recommended_actions.append(
                f"Add to watchlist — conviction not yet high ({conviction_score}/100)."
            )
        else:
            recommended_actions.append("Probe signal — wait for follow-up activity.")

        # ---- Assemble alert ----
        tier = _score_to_tier(conviction_score)
        now_iso = datetime.now().isoformat()
        exp = str(row.get("expiration") or "")
        alert_id = (
            f"{self.ticker}-{exp or 'CHAIN'}-{primary}-{int(strike)}-t{tier}"
        )

        factors: list[str] = reasons + sa_reasons + iv_reasons + prem_reasons + ctx_reasons + pi_reasons

        return {
            "alert_id": alert_id,
            "ticker": self.ticker,
            "timestamp": now_iso,
            "symbol": self.ticker,
            "signal_type": primary,
            "signal_types": candidates,
            "direction": direction,
            "side": side,
            "tier": tier,
            "tier_label": f"T{tier}",
            "strike": float(strike),
            "expiration": exp,
            "underlying_price": float(self.spot or 0.0),
            "conviction_score": conviction_score,
            "sub_scores": {
                "statistical_anomaly": {"points": stat_total, "max": STATISTICAL_ANOMALY_MAX},
                "institutional_pattern": {"points": pat_total, "max": INSTITUTIONAL_PATTERN_MAX},
                "market_context": {"points": ctx_total, "max": MARKET_CONTEXT_MAX},
                "price_impact": {"points": imp_total, "max": PRICE_IMPACT_MAX},
            },
            "indicators": {
                "call_oi": call_oi,
                "put_oi": put_oi,
                "call_vol": call_vol,
                "put_vol": put_vol,
                "iv": call_iv if call_iv > 0 else put_iv,
                "delta": call_delta if side == "CALL" else put_delta,
                "vol_oi_ratio": vol_oi_ratio,
                "midpoint": call_mid if side == "CALL" else put_mid,
                "estimated_premium": premium,
            },
            "key_levels": {
                "entry": float(round(spot, 2)),
                "invalidation": float(round(invalidation, 2)),
                "target": float(round(target, 2)),
            },
            "context": {
                "activity_summary": (
                    f"{primary.replace('_', ' ').title()} at ${strike:.0f} {side} "
                    f"({int(total_vol)} contracts, {int(total_oi)} OI)"
                ),
                "institutional_indicators": factors,
                "market_regime": market_regime,
                "dealer_positioning": dealer_positioning,
                "zero_gamma_cross": float(round(cross, 2)) if cross is not None else None,
            },
            "rationale": rationale,
            "recommended_actions": recommended_actions,
            "created_at": now_iso,
        }


# ----------------------------------------------------------------------------
# Convenience wrapper for the route layer
# ----------------------------------------------------------------------------

def detect_alerts_for_chain(
    ticker: str,
    spot: float,
    chain_data: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """
    Iterate the chain and emit Blademap-shaped alerts.

    ``chain_data`` is the list-of-expiries dict coming from CVForge
    ``get_chain``. The detector handles both shapes produced by the
    route layer:

      shape A: [{expiration, strikes}, ...]  (preferred — gamma available)
      shape B: list of rows [{strike, ...}, ...]

    Returns alerts sorted by conviction desc.

    Internally builds two parallel row lists:
      * ``flat_rows`` — one row per strike combining call+put fields;
        fed to ``BlademapDetector.detect()`` per row.
      * ``all_rows_for_gex`` — TWO rows per strike (one type=CALL with
        call_gamma+call_oi+call_iv, one type=PUT with put_gamma+put_oi+put_iv)
        so that ``_aggregate_gex_1d`` can bucket dealer gamma exposure
        correctly. The Market Context sub-score is fed from here.
    """
    det = BlademapDetector(ticker=ticker, spot=spot)

    flat_rows: list[dict[str, Any]] = []
    all_rows_for_gex: list[dict[str, Any]] = []
    if not chain_data:
        return []
    for exp in chain_data:
        for s in exp.get("strikes", []) if isinstance(exp, dict) else []:
            if not isinstance(s, dict) or len(s) < 3:
                continue
            call_v = s[1] if isinstance(s[1], list) else None
            put_v = s[2] if isinstance(s[2], list) else None
            if not call_v or not put_v:
                continue
            call_oi = _safe_float(call_v[4] if len(call_v) > 4 else None)
            put_oi = _safe_float(put_v[4] if len(put_v) > 4 else None)
            call_gamma = _safe_float(call_v[7] if len(call_v) > 7 else None)
            put_gamma = _safe_float(put_v[7] if len(put_v) > 7 else None)
            call_iv = _safe_float(call_v[5] if len(call_v) > 5 else None)
            put_iv = _safe_float(put_v[5] if len(put_v) > 5 else None)
            row = {
                "strike": _safe_float(s[0] if len(s) > 0 else 0),
                "expiration": exp.get("expiration", "") if isinstance(exp, dict) else "",
                "call_oi": call_oi,
                "put_oi": put_oi,
                "call_vol": _safe_float(call_v[11] if len(call_v) > 11 else None),
                "put_vol": _safe_float(put_v[11] if len(put_v) > 11 else None),
                "call_iv": call_iv,
                "put_iv": put_iv,
                "call_delta": _safe_float(call_v[6] if len(call_v) > 6 else None),
                "put_delta": _safe_float(put_v[6] if len(put_v) > 6 else None),
                "call_bid": _safe_float(call_v[8] if len(call_v) > 8 else None),
                "call_ask": _safe_float(call_v[9] if len(call_v) > 9 else None),
                "put_bid": _safe_float(put_v[8] if len(put_v) > 8 else None),
                "put_ask": _safe_float(put_v[9] if len(put_v) > 9 else None),
            }
            flat_rows.append(row)
            # Two side-aware rows for GEX zero-cross calculation.
            if call_oi > 0 or call_gamma != 0:
                all_rows_for_gex.append({
                    "strike": row["strike"],
                    "gamma": call_gamma,
                    "open_interest": call_oi,
                    "type": "CALL",
                    "iv": call_iv,
                })
            if put_oi > 0 or put_gamma != 0:
                all_rows_for_gex.append({
                    "strike": row["strike"],
                    "gamma": put_gamma,
                    "open_interest": put_oi,
                    "type": "PUT",
                    "iv": put_iv,
                })

    alerts: list[dict[str, Any]] = []
    for row in flat_rows:
        try:
            # Pass all_rows_for_gex so chain_stats (zero-gamma cross + IV percentiles)
            # is populated from the proper, side-aware row set.
            a = det.detect(row, all_rows=all_rows_for_gex)
        except Exception as e:
            log.warning("detector crashed on %s@%.0f: %s", ticker, row.get("strike"), e)
            continue
        if a:
            alerts.append(a)

    alerts.sort(key=lambda a: a["conviction_score"], reverse=True)
    return alerts
