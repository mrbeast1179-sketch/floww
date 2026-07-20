"""
Conviction v2 — the quality-over-quantity layer for the institutional alert
engine. Spec: docs/superpowers/specs/2026-07-20-flow-quality-conviction-v2-design.md

Pure functions only — flow_alerts.eval_institutional composes these; nothing
here touches I/O. Four levers, each attacking a documented noise source:

  detect_spreads   — ~35% of options volume is multi-leg; paired legs must
                     never be sold as directional whales (Nasdaq/TradeAlgo).
  cw_iv_spread     — Cremers-Weinbaum (JFQA 2010): volume-weighted call-put
                     IV spread at matched strikes predicts returns; the
                     print-less substitute for at-ask aggression.
  cluster_biases   — >=3 same-bias qualifying contracts in one snapshot =
                     laddered institutional accumulation.
  bh_fdr           — Benjamini-Hochberg (1995) control on the sigma-spike
                     rule: testing ~300 tickers/day at a raw cutoff is a
                     multiple-testing machine; keep only FDR survivors.

Plus the empirical "prime" conviction bracket: premium >= $250k AND
vol/OI >= 5 — the 55-62% directional bracket from UOA product research.
"""

from __future__ import annotations

import math

# Legs pair when their volumes match within this ratio band and both clear
# the floor — "simultaneous volume spikes with matching sizes" is the
# canonical print-less spread fingerprint.
_SPREAD_RATIO_LO = 0.7
_SPREAD_RATIO_HI = 1.0 / 0.7
_SPREAD_VOL_FLOOR = 1000
_STRADDLE_STRIKE_TOL = 0.05

_CW_CONFIRM = 0.015          # |call IV − put IV| that counts as confirmation
_PRIME_PREMIUM = 250e3
_PRIME_VOL_OI = 5.0
_CLUSTER_MIN_SCORE = 70


def _ratio_match(v1: float, v2: float) -> bool:
    if not v1 or not v2 or v1 < _SPREAD_VOL_FLOOR or v2 < _SPREAD_VOL_FLOOR:
        return False
    r = v1 / v2
    return _SPREAD_RATIO_LO <= r <= _SPREAD_RATIO_HI


def detect_spreads(rows: list[dict]) -> int:
    """Flag likely multi-leg strategy legs in ONE scan snapshot (in place).

    Vertical: same under+exp+type, different strikes, matched volumes.
    Straddle/strangle: same under+exp, opposite types, strikes within 5%,
    matched volumes. Returns the number of rows flagged.
    """
    n = 0
    by_ue: dict[tuple, list[dict]] = {}
    for r in rows or []:
        by_ue.setdefault((r.get("under"), r.get("exp")), []).append(r)
    for legs in by_ue.values():
        if len(legs) < 2:
            continue
        for i in range(len(legs)):
            for j in range(i + 1, len(legs)):
                a, b = legs[i], legs[j]
                if not _ratio_match(a.get("vol") or 0, b.get("vol") or 0):
                    continue
                same_type = a.get("type") == b.get("type")
                if same_type and a.get("strike") != b.get("strike"):
                    pass                      # vertical fingerprint
                elif not same_type and a.get("strike") and b.get("strike") and \
                        abs(a["strike"] - b["strike"]) / max(a["strike"], b["strike"]) <= _STRADDLE_STRIKE_TOL:
                    pass                      # straddle/strangle fingerprint
                else:
                    continue
                for leg in (a, b):
                    if not leg.get("spread_leg"):
                        leg["spread_leg"] = True
                        n += 1
    return n


def cw_iv_spread(rows: list[dict]) -> dict[str, float]:
    """Cremers-Weinbaum volume-weighted (call IV − put IV) per ticker.

    Pairs calls and puts of the SAME under+exp+strike; weight = min of the
    pair's volumes (the size both sides actually agree on). Positive =>
    call demand richening => bullish informed pressure.
    """
    calls: dict[tuple, dict] = {}
    puts: dict[tuple, dict] = {}
    for r in rows or []:
        if r.get("iv") is None or not r.get("strike"):
            continue
        key = (r.get("under"), r.get("exp"), r.get("strike"))
        (calls if r.get("type") == "call" else puts)[key] = r
    acc: dict[str, list] = {}
    for key, c in calls.items():
        p = puts.get(key)
        if not p:
            continue
        w = min(c.get("vol") or 0, p.get("vol") or 0)
        if w <= 0:
            continue
        acc.setdefault(key[0], []).append((c["iv"] - p["iv"], w))
    out: dict[str, float] = {}
    for under, pairs in acc.items():
        tot = sum(w for _, w in pairs)
        if tot > 0:
            out[under] = sum(s * w for s, w in pairs) / tot
    return out


def cluster_biases(rows: list[dict], min_n: int = 3) -> dict[str, str]:
    """{ticker: bias} where >=min_n distinct qualifying contracts (score >=
    70, opening-shaped) share one bias in this snapshot — laddered
    accumulation across strikes/expiries."""
    from services.flow_alerts import infer_side_bias  # deferred: no cycle at import time

    tally: dict[tuple, set] = {}
    for r in rows or []:
        if (r.get("_score") or 0) < _CLUSTER_MIN_SCORE:
            continue
        side, bias = infer_side_bias(r)
        if side != "BUY" or not bias:
            continue
        tally.setdefault((r["under"], bias), set()).add(r.get("ckey"))
    out: dict[str, str] = {}
    for (under, bias), ckeys in tally.items():
        if len(ckeys) >= min_n:
            out[under] = bias
    return out


def sigma_pvalue(sigma: float) -> float:
    """One-sided normal p-value for a sigma-spike observation."""
    return 0.5 * math.erfc(sigma / math.sqrt(2.0))


def bh_fdr(pvals: dict[str, float], q: float = 0.10) -> set[str]:
    """Benjamini-Hochberg: the largest k with p_(k) <= k*q/m; reject 1..k.

    Returns the set of keys whose discoveries survive at FDR level q.
    """
    if not pvals:
        return set()
    items = sorted(pvals.items(), key=lambda kv: kv[1])
    m = len(items)
    k_star = 0
    for k, (_, p) in enumerate(items, start=1):
        if p <= k * q / m:
            k_star = k
    return {key for key, _ in items[:k_star]}


def is_prime(r: dict) -> bool:
    """The empirically measured 55-62% directional bracket: premium >= $250k
    AND vol/OI >= 5 (UOA product research)."""
    return (r.get("premium") or 0) >= _PRIME_PREMIUM and (r.get("vol_oi") or 0) >= _PRIME_VOL_OI


def cw_confirms(bias: str | None, cw: float | None) -> bool:
    if bias is None or cw is None:
        return False
    if bias == "BULLISH":
        return cw >= _CW_CONFIRM
    if bias == "BEARISH":
        return cw <= -_CW_CONFIRM
    return False
