"""
backend/routes/quant.py

Quant signal catalog API — Phase 6.4.

Exposes the existing quant infrastructure as a catalog so the frontend can
browse available signals, their current state, and raw values without
duplicating logic between backend and frontend.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Query

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/quant", tags=["quant"])


@router.get("/signals")
async def quant_signal_catalog(
    ticker: str = Query("SPY", description="Ticker to evaluate signals for"),
) -> dict[str, Any]:
    """Return the catalog of available quant signals and their current values.

    Each signal entry includes:
        - name: canonical signal name
        - source: quant service that produces it
        - value: current numeric or categorical value (empty if unavailable)
        - unit: human-readable unit
        - description: one-line explanation
    """
    t = ticker.strip().upper()
    if t == "SPX":
        t = "^SPX"

    signals: list[dict[str, Any]] = []

    # --- GEX regime signals (from signal_translator / GEX core) ---
    try:
        from services.signal_translator import translate_signal, SignalInput

        regime = translate_signal(SignalInput(
            ticker=t,
            gex_zscore_60d=0.0,
            spot=0.0,
            gex_integrated=0.0,
            recent_flow=0.0,
        ))
        signals.append({
            "name": "gex_regime",
            "source": "signal_translator",
            "value": regime.get("signal_type", ""),
            "unit": "label",
            "description": "Translated GEX regime signal (buy_call / buy_put / hold / etc.)",
        })
    except Exception as e:
        logger.debug(f"gex_regime unavailable for {t}: {e}")

    # --- HMM regime classification ---
    try:
        from services.hmm_regime import GaussianHMMRegime

        hmm = GaussianHMMRegime()
        state = hmm.classify(t)
        if state:
            signals.append({
                "name": "hmm_regime",
                "source": "hmm_regime",
                "value": state.get("state", ""),
                "unit": "label",
                "description": "HMM-classified market regime (trending/ranging/volatile/quiet)",
            })
    except Exception as e:
        logger.debug(f"hmm_regime unavailable for {t}: {e}")

    # --- Composite flow score ---
    try:
        from services.composite_flow_score import CompositeFlowScore

        cfs = CompositeFlowScore()
        score = cfs.compute(t)
        if score is not None:
            signals.append({
                "name": "composite_flow_score",
                "source": "composite_flow_score",
                "value": round(score, 3),
                "unit": "index (-1..1)",
                "description": "Composite institutional flow score (negative = heavy put/flow selling)",
            })
    except Exception as e:
        logger.debug(f"composite_flow_score unavailable for {t}: {e}")

    # --- VPIN toxicity ---
    try:
        from services.vpin_engine import VpinEngine

        vpin = VpinEngine()
        tox = vpin.get_toxicity(t)
        if tox is not None:
            signals.append({
                "name": "vpin_toxicity",
                "source": "vpin_engine",
                "value": round(tox, 4),
                "unit": "z-score",
                "description": "VPIN-based market toxicity measure (high = stressed/liquidated)",
            })
    except Exception as e:
        logger.debug(f"vpin_toxicity unavailable for {t}: {e}")

    # --- IV rank / percentile ---
    try:
        from services.vol_analytics import calc_iv_rank_percentile

        ivr = calc_iv_rank_percentile(t, 0.2)
        if ivr:
            signals.append({
                "name": "iv_rank",
                "source": "vol_analytics",
                "value": round(ivr.get("iv_rank", 0), 3),
                "unit": "percentile (0..1)",
                "description": "Implied volatility rank vs trailing window",
            })
    except Exception as e:
        logger.debug(f"iv_rank unavailable for {t}: {e}")

    # --- Realized volatility ---
    try:
        from services.vol_analytics import calc_realized_volatility

        rv = calc_realized_volatility(t.replace("^", ""), 20)
        if rv:
            signals.append({
                "name": "realized_volatility_20d",
                "source": "vol_analytics",
                "value": round(rv.get("rv_close", 0), 4),
                "unit": "annualized vol",
                "description": "20-day realized volatility (annualized)",
            })
    except Exception as e:
        logger.debug(f"realized_volatility unavailable for {t}: {e}")

    # --- Volume clock ---
    try:
        from services.volume_clock import VolumeClock

        vc = VolumeClock()
        clock = vc.get_bucket(t)
        if clock:
            signals.append({
                "name": "volume_clock_bucket",
                "source": "volume_clock",
                "value": clock.get("bucket", ""),
                "unit": "label",
                "description": "Current volume-clock bucket (accumulation/distribution/equilibrium)",
            })
    except Exception as e:
        logger.debug(f"volume_clock unavailable for {t}: {e}")

    # --- IV surface metrics ---
    try:
        from services.vol_analytics import calc_skew_metrics

        skew = calc_skew_metrics(t.replace("^", ""), [])
        if skew:
            signals.append({
                "name": "iv_skew",
                "source": "vol_analytics",
                "value": round(skew.get("skew", 0), 4),
                "unit": "log-ratio",
                "description": "Call/put IV skew (positive = calls richer, negative = puts richer)",
            })
    except Exception as e:
        logger.debug(f"iv_skew unavailable for {t}: {e}")

    # --- Charm estimate (delta decay proxy) ---
    try:
        from services.advanced_analytics import calc_charm_integral

        charm = calc_charm_integral(t.replace("^", ""), [])
        if charm:
            signals.append({
                "name": "charm_integral",
                "source": "advanced_analytics",
                "value": round(charm, 4),
                "unit": "delta/day",
                "description": "Aggregate charm (delta decay) integral across option chain",
            })
    except Exception as e:
        logger.debug(f"charm unavailable for {t}: {e}")

    return {
        "ticker": t,
        "signals": signals,
        "count": len(signals),
    }
