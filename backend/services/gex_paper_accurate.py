"""
backend/services/gex_paper_accurate.py

Paper-accurate GEX metrics implementing the methodology from:

  Paper #1 — Ni, Pearson, Poteshman & White (2020)
    "Does Option Trading Have a Pervasive Impact on Underlying Stock Prices?"
    SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=2867461

  Paper #2 — Barbon & Buraschi (2021)
    "Gamma Fragility"
    SSRN: https://papers.ssrn.com/sol3/papers.cfm?abstract_id=3725454

This module adds the paper-prescribed normalizations and decompositions
that the practitioner GEX formula (gamma × OI × 100 × S² × 0.01) alone
does not capture. The raw dollar GEX computation is unchanged — this
module WRAPS it with the academic risk metrics proven in the literature.

Key additions over the raw practitioner GEX:
  1. Gamma Imbalance (% of ADV) — Barbon-Buraschi Eq. (2)
  2. Zero-Gamma Flip Distance — Barbon-Buraschi Section II.B
  3. Intraday Regime Signal (momentum vs reversal) — Barbon-Buraschi Sec. I
  4. Gamma Decomposition (Hedge vs Info) — Ni-Pearson Sec. 3
  5. Flash Crash Probability Proxy — Barbon-Buraschi Sec. III.C
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np


# ---------------------------------------------------------------------------
# 1. Gamma Imbalance (Barbon-Buraschi Eq. 2)
#    ΓIB_i(t) = Hedgers Gamma_i × S_i(t) / ADSV_i(t)
#
#    Where:
#    - Hedgers Gamma_i = Σ(Γ_j × Inventory_j) for all options on stock i
#    - S_i(t) = underlying stock price at t
#    - ADSV_i(t) = average daily share volume (21-day rolling)
#
#    This normalizes raw dollar GEX by the stock's typical daily volume,
#    making GEX comparable across stocks of different liquidity. The paper
#    finds that one std dev increase in ΓIB decreases absolute returns by
#    5-25 bps for single stocks, >20 bps for indices.
#
#    Sign convention (dealer-positive, matching gex_aggregator.py):
#      Calls (+): dealers short calls → buy to re-hedge on rallies
#      Puts  (-): dealers short puts → sell to re-hedge on declines
# ---------------------------------------------------------------------------

def compute_gamma_imbalance(
    net_gex_dollars: float,
    spot: float,
    adv_shares: float,
) -> dict[str, Any]:
    """Compute the Barbon-Buraschi Gamma Imbalance (% of ADV).

    Args:
        net_gex_dollars: Net dollar GEX (Σ sign × gamma × OI × 100 × S² × 0.01)
        spot: Underlying price
        adv_shares: Average daily share volume (21-day rolling)

    Returns:
        dict with gamma_imbalance_pct, regime, and interpretation
    """
    if spot <= 0 or adv_shares <= 0:
        return {
            "gamma_imbalance_pct": 0.0,
            "gamma_imbalance_dollars_per_share": 0.0,
            "regime": "insufficient_data",
            "interpretation": "Cannot compute — missing spot or ADV data.",
        }

    # ΓIB = (Net GEX in dollars) / (S × ADSV) × 100
    # Net GEX is already in dollars-per-1%-move
    # First convert to dollars-per-$1-move: divide by (S × 0.01)
    # Then normalize by daily dollar volume: divide by (S × ADSV)
    # Simplification: ΓIB_pct = net_gex / (S² × 0.01 × ADSV) × 100

    daily_dollar_volume = spot * adv_shares
    if daily_dollar_volume <= 0:
        return {
            "gamma_imbalance_pct": 0.0,
            "gamma_imbalance_dollars_per_share": 0.0,
            "regime": "zero_volume",
            "interpretation": "Zero ADV — cannot normalize.",
        }

    # The practitioner GEX is already per-1%-move. The paper ΓIB normalizes
    # raw gamma×inventory by ADSV. We convert: raw_gamma_dollars = GEX / (S × 0.01)
    # Then ΓIB = raw_gamma_dollars / (S × ADSV) × 100
    #       = GEX / (S² × 0.01 × ADSV) × 100
    gamma_imbalance_pct = (net_gex_dollars / (spot * spot * 0.01 * adv_shares)) * 100.0

    # Also compute as dollars-per-share for display
    gamma_imbalance_dollars_per_share = net_gex_dollars / adv_shares if adv_shares > 0 else 0.0

    # Regime classification per Barbon-Buraschi:
    #   ΓIB > 0  → positive gamma → stabilizing (dealers mean-revert)
    #   ΓIB < 0  → negative gamma → destabilizing (dealers amplify)
    if gamma_imbalance_pct > 1.0:
        regime = "strong_positive_gamma"
        interpretation = (
            "Dealers strongly net long gamma — hedging is counter-cyclical. "
            "Expect intraday mean reversion and compressed volatility. "
            "Favorable for selling premium."
        )
    elif gamma_imbalance_pct > 0.1:
        regime = "positive_gamma"
        interpretation = (
            "Dealers net long gamma — hedging provides modest stabilization. "
            "Mild mean reversion expected."
        )
    elif gamma_imbalance_pct > -0.1:
        regime = "neutral_gamma"
        interpretation = (
            "Gamma imbalance near zero — dealer hedging has minimal directional impact. "
            "Volatility driven by other factors."
        )
    elif gamma_imbalance_pct > -1.0:
        regime = "negative_gamma"
        interpretation = (
            "Dealers net short gamma — hedging is pro-cyclical. "
            "Expect intraday momentum and elevated volatility. "
            "Gamma squeeze risk elevated."
        )
    else:
        regime = "strong_negative_gamma"
        interpretation = (
            "Dealers strongly net short gamma — hedging AMPLIFIES moves. "
            "Flash crash risk significantly elevated. "
            "Expect strong intraday momentum and wide ranges. Avoid short gamma strategies."
        )

    return {
        "gamma_imbalance_pct": round(gamma_imbalance_pct, 4),
        "gamma_imbalance_dollars_per_share": round(gamma_imbalance_dollars_per_share, 4),
        "regime": regime,
        "interpretation": interpretation,
        "spot": spot,
        "adv_shares": adv_shares,
        "net_gex_dollars": net_gex_dollars,
    }


# ---------------------------------------------------------------------------
# 2. Zero-Gamma Flip Distance (Barbon-Buraschi Section II.B)
#
#    The "Zero-Gamma Flip" is the price level where aggregate dealer gamma
#    transitions from positive to negative. Barbon-Buraschi shows this is
#    a critical regime boundary — crossing it triggers a shift from
#    stabilizing to destabilizing dealer hedging.
#
#    flip_distance_pct = (spot - flip_level) / spot × 100
#
#    Positive → spot is above flip → positive gamma regime (safe)
#    Negative → spot is below flip → negative gamma regime (risk)
# ---------------------------------------------------------------------------

def compute_flip_metrics(
    spot: float,
    zero_gamma_level: float | None,
    net_gex: float,
) -> dict[str, Any]:
    """Compute flip-level distance and regime proximity metrics.

    Args:
        spot: Current underlying price
        zero_gamma_level: Interpolated price where net GEX = 0
        net_gex: Current net dollar GEX

    Returns:
        dict with flip_distance_pct, regime, fragility_warning
    """
    if zero_gamma_level is None or zero_gamma_level <= 0 or spot <= 0:
        return {
            "flip_distance_pct": None,
            "flip_level": zero_gamma_level,
            "regime": "unknown",
            "fragility_warning": False,
            "warning_text": "",
        }

    flip_distance_pct = ((spot - zero_gamma_level) / spot) * 100.0

    # Barbon-Buraschi find that effects are strongest when the index
    # is within ~2-3% of the flip level. Within 1% = critical zone.
    fragility = False
    warning = ""
    if abs(flip_distance_pct) < 1.0:
        fragility = True
        direction = "above" if flip_distance_pct > 0 else "below"
        warning = (
            f"CRITICAL: Spot is within 1% of zero-gamma flip at ${zero_gamma_level:.2f}. "
            f"A {abs(flip_distance_pct):.1f}% move {direction} triggers regime flip. "
            "Dealer hedging direction will reverse — expect sharp acceleration."
        )
    elif abs(flip_distance_pct) < 2.5:
        warning = (
            f"WARNING: Spot within 2.5% of zero-gamma flip at ${zero_gamma_level:.2f}. "
            "Monitor closely for potential regime transition."
        )

    if flip_distance_pct > 2.5:
        regime = "safe_positive_gamma"
    elif flip_distance_pct > 0:
        regime = "positive_gamma_approach_flip"
    elif flip_distance_pct > -2.5:
        regime = "negative_gamma_approach_flip"
    else:
        regime = "deep_negative_gamma"

    return {
        "flip_distance_pct": round(flip_distance_pct, 4),
        "flip_level": round(zero_gamma_level, 2),
        "spot": spot,
        "net_gex": net_gex,
        "regime": regime,
        "fragility_warning": fragility,
        "warning_text": warning,
    }


# ---------------------------------------------------------------------------
# 3. Intraday Regime Signal — Momentum vs Reversal
#    (Barbon-Buraschi Section III.B)
#
#    Negative gamma imbalance → positive autocorrelation (momentum)
#    Positive gamma imbalance → negative autocorrelation (reversal)
#
#    The paper finds this effect is strongest at h=60 minute horizon,
#    consistent with dealers adjusting hedges intraday.
# ---------------------------------------------------------------------------

def predict_intraday_regime(
    gamma_imbalance_pct: float,
    flip_distance_pct: float | None = None,
) -> dict[str, Any]:
    """Predict intraday momentum vs reversal regime from gamma imbalance.

    Per Barbon-Buraschi Table II/III:
      - Negative ΓIB → dealers short gamma → sell into declines →
        POSITIVE autocorrelation (momentum/trend continuation)
      - Positive ΓIB → dealers long gamma → buy dips, sell rips →
        NEGATIVE autocorrelation (mean reversion)

    Args:
        gamma_imbalance_pct: ΓIB as percent of ADV
        flip_distance_pct: Optional distance to zero-gamma flip for confidence

    Returns:
        dict with predicted_regime, expected_autocorr_sign, confidence
    """
    # Default confidence based on ΓIB magnitude
    abs_gib = abs(gamma_imbalance_pct)

    if abs_gib > 2.0:
        confidence = "high"
    elif abs_gib > 0.5:
        confidence = "medium"
    elif abs_gib > 0.1:
        confidence = "low"
    else:
        confidence = "negligible"

    # Increase confidence near the flip level
    if flip_distance_pct is not None and abs(flip_distance_pct) < 2.0:
        if confidence == "low":
            confidence = "medium"
        elif confidence == "medium":
            confidence = "high"

    if gamma_imbalance_pct < -1.0:
        regime = "momentum"
        autocorr_sign = "positive"
        description = (
            "Strong negative gamma — dealer hedging amplifies trends. "
            "Expect intraday MOMENTUM: trends persist, breakouts run, "
            "reversals are false. Avoid fading moves. Ride the trend."
        )
    elif gamma_imbalance_pct < -0.1:
        regime = "mild_momentum"
        autocorr_sign = "positive"
        description = (
            "Mild negative gamma — slight trend amplification. "
            "Weaker momentum than strong negative regime."
        )
    elif gamma_imbalance_pct > 1.0:
        regime = "mean_reversion"
        autocorr_sign = "negative"
        description = (
            "Strong positive gamma — dealer hedging dampens trends. "
            "Expect intraday MEAN REVERSION: rallies fade, dips bought. "
            "Favorable for range-bound strategies, selling premium."
        )
    elif gamma_imbalance_pct > 0.1:
        regime = "mild_reversal"
        autocorr_sign = "negative"
        description = (
            "Mild positive gamma — slight mean reversion bias."
        )
    else:
        regime = "neutral"
        autocorr_sign = "none"
        description = (
            "Gamma near neutral — no strong intraday bias from dealer hedging."
        )

    return {
        "predicted_regime": regime,
        "expected_autocorr_sign": autocorr_sign,
        "confidence": confidence,
        "description": description,
        "gamma_imbalance_pct": round(gamma_imbalance_pct, 4),
    }


# ---------------------------------------------------------------------------
# 4. Gamma Decomposition — HedgeGamma vs InfoGamma
#    (Ni-Pearson Internet Appendix, Section 3)
#
#    The total net position gamma can be decomposed into:
#      HedgeGamma(t-τ,t) = component due to past stock price changes
#        — measures how much gamma changed because spot moved
#        — dealers MUST hedge this mechanically
#      InfoGamma(t-τ,t) = component due to changes in option positions
#        — measures how much gamma changed because OI changed
#        — reflects informed options flow
#      Gamma(t-τ, S_{t-τ}) = gamma from τ days ago at old spot
#        — baseline reference level
#
#    The paper finds:
#      - HedgeGamma is the STRONGEST predictor of future |returns|
#      - Negative HedgeGamma → higher subsequent volatility
#      - InfoGamma also predicts volatility but with smaller magnitude
#      - HedgeGamma interacts with direction: negative gamma + negative
#        returns → momentum continuation (dealers sell more)
# ---------------------------------------------------------------------------

def decompose_gamma(
    current_gex: float,              # GEX(S_t, OI_t)  — today's GEX at today's spot
    gex_at_old_spot: float | None,   # GEX(S_t, OI_{t-τ})  — old OI at today's spot
    gex_at_old_spot_old_oi: float | None,  # GEX(S_{t-τ}, OI_{t-τ}) — old OI at old spot
) -> dict[str, Any]:
    """Decompose net gamma change into Hedge and Information components.

    Follows Ni-Pearson decomposition (Internet Appendix, Section 3):

      HedgeGamma(t-τ,t) = GEX(S_t, OI_{t-τ}) - GEX(S_{t-τ}, OI_{t-τ})
        → change due to spot moving (MECHANICAL dealer hedging)

      InfoGamma(t-τ,t) = GEX(S_t, OI_t) - GEX(S_t, OI_{t-τ})
        → change due to OI changing (INFORMED options flow)

    Paper finding: HedgeGamma is the strongest predictor of future
    absolute returns. One std dev lower HedgeGamma → ~50 bps higher |return|.

    Args:
        current_gex: Today's GEX at today's spot and today's OI
        gex_at_old_spot: Today's GEX recomputed with OLD OI at today's spot
        gex_at_old_spot_old_oi: GEX at old spot with old OI (τ days ago)

    Returns:
        dict with hedge_gamma, info_gamma, total_change
    """
    if gex_at_old_spot is None and gex_at_old_spot_old_oi is None:
        return {
            "hedge_gamma": None,
            "info_gamma": None,
            "old_baseline_gamma": None,
            "total_change": None,
            "decomposition_available": False,
            "interpretation": "Insufficient data for decomposition — need prior GEX snapshots.",
        }

    # Default: if we don't have both historical snapshots, we can't decompose
    if gex_at_old_spot is None or gex_at_old_spot_old_oi is None:
        return {
            "hedge_gamma": None,
            "info_gamma": None,
            "old_baseline_gamma": gex_at_old_spot_old_oi,
            "total_change": current_gex - (gex_at_old_spot_old_oi or current_gex),
            "decomposition_available": False,
            "interpretation": "Partial data — full decomposition requires both old OI at new spot and old OI at old spot.",
        }

    hedge_gamma = gex_at_old_spot - gex_at_old_spot_old_oi
    info_gamma = current_gex - gex_at_old_spot
    total_change = current_gex - gex_at_old_spot_old_oi

    # Interpretation per Ni-Pearson:
    #   Negative HedgeGamma + negative returns → dealers sell → momentum
    #   Negative HedgeGamma + positive returns → dealers buy → momentum
    #   Positive HedgeGamma → stabilizing regardless of direction
    hedge_interpretation = ""
    if hedge_gamma < -1e8:  # threshold for "large negative"
        hedge_interpretation = (
            "Large negative HedgeGamma — spot moved against dealer positioning. "
            "Dealers likely forced to hedge, amplifying recent price move. "
            "Expect: elevated subsequent volatility (Ni-Pearson coefficient ≈ -0.3 to -0.6)."
        )
    elif hedge_gamma < 0:
        hedge_interpretation = "Negative HedgeGamma — minor dealer hedging pressure."
    elif hedge_gamma > 1e8:
        hedge_interpretation = (
            "Large positive HedgeGamma — spot moved favorably for dealer book. "
            "Dealers may reduce hedges, dampening volatility."
        )
    else:
        hedge_interpretation = "HedgeGamma near zero — minimal mechanical hedging impact."

    info_interpretation = ""
    if abs(info_gamma) > 1e8:
        direction = "increased" if info_gamma > 0 else "decreased"
        info_interpretation = (
            f"Significant InfoGamma — options positions {direction} net gamma by ${abs(info_gamma)/1e9:.2f}B. "
            "Indicates informed options flow entering/exiting."
        )
    else:
        info_interpretation = "InfoGamma near zero — no significant options position changes."

    return {
        "hedge_gamma": round(hedge_gamma, 2),
        "info_gamma": round(info_gamma, 2),
        "old_baseline_gamma": round(gex_at_old_spot_old_oi, 2),
        "current_gamma": round(current_gex, 2),
        "total_change": round(total_change, 2),
        "decomposition_available": True,
        "hedge_interpretation": hedge_interpretation,
        "info_interpretation": info_interpretation,
    }


# ---------------------------------------------------------------------------
# 5. Flash Crash Probability Proxy (Barbon-Buraschi Section III.C)
#
#    The paper finds that negative gamma imbalance is associated with
#    higher frequency and magnitude of flash crash events. Conditional
#    on negative ex-ante gamma imbalance, flash crashes are more likely
#    and larger in magnitude.
#
#    We provide a heuristic probability score based on:
#      - Gamma imbalance magnitude and sign
#      - Distance to zero-gamma flip
#      - Illiquidity (Amihud proxy)
# ---------------------------------------------------------------------------

def flash_crash_risk(
    gamma_imbalance_pct: float,
    flip_distance_pct: float | None = None,
    amihud_illiquidity: float | None = None,
    net_gex: float = 0.0,
) -> dict[str, Any]:
    """Estimate flash crash probability from gamma imbalance.

    Barbon-Buraschi finding (Table V): one std dev decrease in ΓIB
    → ~16 bps increase in daily High-Low spread, and the effect is
    stronger for illiquid stocks and near the flip level.

    Args:
        gamma_imbalance_pct: ΓIB as percent of ADV
        flip_distance_pct: Distance to zero-gamma flip (%)
        amihud_illiquidity: Amihud illiquidity ratio (|return|/dollar_volume)
        net_gex: Raw net dollar GEX for context

    Returns:
        dict with risk_level, crash_probability_estimate, warning flags
    """
    # Base risk from gamma imbalance sign and magnitude
    if gamma_imbalance_pct > 2.0:
        base_risk = 0.01  # 1% — very low
    elif gamma_imbalance_pct > 0.5:
        base_risk = 0.03  # 3%
    elif gamma_imbalance_pct > -0.5:
        base_risk = 0.08  # 8% — neutral zone
    elif gamma_imbalance_pct > -2.0:
        base_risk = 0.18  # 18% — negative gamma
    elif gamma_imbalance_pct > -5.0:
        base_risk = 0.30  # 30% — strong negative
    else:
        base_risk = 0.50  # 50% — extreme negative

    # Amplify near flip level (Barbon-Buraschi: effects strongest near flip)
    if flip_distance_pct is not None and abs(flip_distance_pct) < 1.0:
        base_risk *= 1.5
    elif flip_distance_pct is not None and abs(flip_distance_pct) < 2.5:
        base_risk *= 1.2

    # Amplify for illiquid stocks (Barbon-Buraschi interaction term)
    illiquidity_factor = 1.0
    if amihud_illiquidity is not None and amihud_illiquidity > 0:
        # Normalize: Amihud > 1e-6 is considered illiquid
        if amihud_illiquidity > 1e-5:
            illiquidity_factor = 1.5
        elif amihud_illiquidity > 1e-6:
            illiquidity_factor = 1.2

    crash_prob = min(base_risk * illiquidity_factor, 0.95)

    # Risk classification
    if crash_prob > 0.35:
        risk_level = "EXTREME"
        recommendation = (
            "EXTREME FLASH CRASH RISK. Dealer gamma profile highly unstable. "
            "Reduce position sizes, widen stops, avoid illiquid names. "
            "Consider long vol / tail hedge strategies."
        )
    elif crash_prob > 0.20:
        risk_level = "HIGH"
        recommendation = (
            "HIGH flash crash risk. Negative gamma + proximity to flip. "
            "Use tighter stops, favor liquid names, monitor intraday volume spikes."
        )
    elif crash_prob > 0.10:
        risk_level = "ELEVATED"
        recommendation = (
            "Elevated crash risk. Monitor gamma profile for deterioration. "
            "Standard risk controls sufficient."
        )
    elif crash_prob > 0.05:
        risk_level = "MODERATE"
        recommendation = "Moderate risk — normal market conditions."
    else:
        risk_level = "LOW"
        recommendation = (
            "Low flash crash risk. Positive gamma regime — dealer hedging "
            "provides structural stabilization."
        )

    return {
        "risk_level": risk_level,
        "crash_probability_estimate": round(crash_prob, 4),
        "gamma_imbalance_pct": round(gamma_imbalance_pct, 4),
        "flip_distance_pct": round(flip_distance_pct, 4) if flip_distance_pct is not None else None,
        "recommendation": recommendation,
    }


# ---------------------------------------------------------------------------
# Summary: Full paper-accurate GEX diagnostic (combines all 5 metrics)
# ---------------------------------------------------------------------------

def full_paper_diagnostic(
    net_gex: float,
    spot: float,
    adv_shares: float | None = None,
    zero_gamma_level: float | None = None,
    current_gex: float | None = None,
    gex_at_old_spot: float | None = None,
    gex_at_old_spot_old_oi: float | None = None,
    amihud_illiquidity: float | None = None,
) -> dict[str, Any]:
    """Compute the complete paper-accurate GEX diagnostic suite.

    This is the single entry point that wraps all five paper metrics
    into one response payload suitable for the briefing API.

    Args:
        net_gex: Net dollar GEX (from gex_aggregator or gex_core)
        spot: Underlying price
        adv_shares: Average daily share volume (optional — skips ΓIB if None)
        zero_gamma_level: Zero-gamma flip strike (optional)
        current_gex: Today's GEX for decomposition (optional)
        gex_at_old_spot: Prior GEX recomputed at current spot (optional)
        gex_at_old_spot_old_oi: Prior GEX at prior spot (optional)
        amihud_illiquidity: Amihud ratio (optional)

    Returns:
        Complete diagnostic dict with all paper metrics
    """
    result: dict[str, Any] = {
        "net_gex": net_gex,
        "spot": spot,
        "paper_metrics": {},
    }

    # 1. Gamma Imbalance
    if adv_shares is not None and adv_shares > 0:
        gi = compute_gamma_imbalance(net_gex, spot, adv_shares)
        result["paper_metrics"]["gamma_imbalance"] = gi
        gib_pct = gi["gamma_imbalance_pct"]
    else:
        result["paper_metrics"]["gamma_imbalance"] = {
            "error": "ADV not provided — skip Gamma Imbalance computation"
        }
        # Default ADV fallback — avoids magic number; mirrors briefing ADV dict
        _default_adv = 10_000_000
        gib_pct = (
            net_gex / (spot * spot * 0.01 * _default_adv) * 100
            if spot > 0
            else 0.0
        )  # rough proxy with explicit default

    # 2. Flip Metrics
    fm = compute_flip_metrics(spot, zero_gamma_level, net_gex)
    result["paper_metrics"]["flip_metrics"] = fm
    flip_dist = fm.get("flip_distance_pct")

    # 3. Intraday Regime
    ir = predict_intraday_regime(gib_pct, flip_dist)
    result["paper_metrics"]["intraday_regime"] = ir

    # 4. Gamma Decomposition
    dc = decompose_gamma(
        current_gex or net_gex,
        gex_at_old_spot,
        gex_at_old_spot_old_oi,
    )
    result["paper_metrics"]["gamma_decomposition"] = dc

    # 5. Flash Crash Risk
    fcr = flash_crash_risk(
        gib_pct,
        flip_dist,
        amihud_illiquidity,
        net_gex,
    )
    result["paper_metrics"]["flash_crash_risk"] = fcr

    return result


def put_call_ratio_signal(
    call_oi: float,
    put_oi: float,
    call_vol: float = 0.0,
    put_vol: float = 0.0,
) -> dict[str, Any]:
    """Pan-Poteshman (2006) put-call ratio directional signal.

    'The Information of Option Volume for Future Stock Prices'
    Review of Financial Studies 19, 871-908.

    Key finding: stocks with LOW PCR outperform by 40bps next day, 1% next week.
    Uses OI-based PCR as primary proxy when trade-level buyer-initiated data unavailable.
    """
    total_oi = call_oi + put_oi
    total_vol = call_vol + put_vol
    pcr_oi = (put_oi / total_oi) if total_oi > 0 else None
    pcr_vol = (put_vol / total_vol) if total_vol > 0 else None
    pcr = pcr_oi if pcr_oi is not None else (pcr_vol if pcr_vol is not None else 0.5)

    if pcr < 0.35:
        signal, confidence = "BULLISH", "high"
        interp = f"PCR {pcr:.2f} — calls dominate. Low PCR stocks outperform (Pan-Poteshman 2006)."
    elif pcr < 0.45:
        signal, confidence = "BULLISH", "medium"
        interp = f"PCR {pcr:.2f} — mild call dominance."
    elif pcr > 0.65:
        signal, confidence = "BEARISH", "high"
        interp = f"PCR {pcr:.2f} — puts dominate. High PCR stocks underperform."
    elif pcr > 0.55:
        signal, confidence = "BEARISH", "medium"
        interp = f"PCR {pcr:.2f} — mild put dominance."
    else:
        signal, confidence = "NEUTRAL", "low"
        interp = f"PCR {pcr:.2f} — balanced. No directional edge."

    return {
        "pcr_oi": round(pcr_oi, 4) if pcr_oi is not None else None,
        "pcr_vol": round(pcr_vol, 4) if pcr_vol is not None else None,
        "signal": signal,
        "confidence": confidence,
        "interpretation": interp,
    }
