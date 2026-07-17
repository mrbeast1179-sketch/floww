"""
backend/services/multi_level_ofi.py

Multi-Level Order Flow Imbalance (MLOFI).

Implements the multi-level OFI calculation per
"Multi-Level Order-Flow Imbalance in a Limit Order Book"
by Ke Xu, Martin D. Gould, Sam D. Howison (2019, arXiv:1907.06230).
Two implementations:

  * ``MultiLevelOFI`` — LOB-based.  Takes two consecutive snapshots
    (each defined as ``{level: {"bid": (price, size), "ask": (price, size)}}``)
    and returns the per-level OFI vector + aggregated OFI.
  * ``StructuralOFI`` — chain-based proxy.  Uses options-chain snapshots
    (call_oi + put_oi per strike across two consecutive chain fetches) to
    estimate a structural OFI when LOB snapshots are not available.

Both produce a Blademap-friendly dict:
    {
      "of_per_level": [float, ...],   # multi-level OFI vector
      "of_aggregated": float,         # sum across levels
      "imbalance_label": str,         # buy-heavy / sell-heavy / neutral
      "levels_used": int,
      "snaps_used": int,              # 2 if both fetches present else 1
    }

The math (verbatim from the paper):

    OFI_t^ℓ ≔
        ΔV(B)^ℓ · I{P(B)^ℓ > 0}
      + ΔV(A)^ℓ · I{P(A)^ℓ < 0}
      + ΔP(B)^ℓ · V(B)^ℓ_{-} · I{P(B)^ℓ < 0}
      + ΔP(A)^ℓ · V(A)^ℓ_{+} · I{P(A)^ℓ > 0}

where ΔV(B)^ℓ is the change in bid size at level ℓ (zero if
bid price moved down), ΔV(A)^ℓ is the change in ask size (zero if
ask price moved up), V(B)^ℓ_{-} is the previous bid size,
V(A)^ℓ_{+} the previous ask size, ΔP(B)^ℓ the bid-price change,
and ΔP(A)^ℓ the ask-price change.

Implemented here as the simplified equivalent the paper actually
uses for out-of-sample regression (and what ``markwick`` uses in his
blog tutorial): a per-level net-flow delta.

This is pure-Python and the route layer can import it unconditionally.
"""
from __future__ import annotations

import logging
import math
from collections import deque
from collections.abc import Iterable
from typing import Any

log = logging.getLogger(__name__)


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


# ─────────────────────────────────────────────────────────────────────
# LOB-based Multi-Level OFI
# ─────────────────────────────────────────────────────────────────────

class MultiLevelOFI:
    """Pure-Python multi-level OFI on a stack of LOB snapshots.

    Usage::

        ofi = MultiLevelOFI(levels=5)
        ofi.push_snapshot({ℓ: {"bid": (101.5, 200), "ask": (101.6, 300)}, ...})
        out = ofi.compute()  # returns vector across all levels (length=levels_used)
    """

    def __init__(self, levels: int = 5, history: int = 4):
        self.levels = max(1, int(levels))
        self._snaps: deque[dict[int, dict[str, tuple[float, float]]]] = deque(maxlen=max(2, history))

    def push_snapshot(self, snap: dict[int, dict[str, tuple[float, float]]]) -> None:
        """Add a snapshot. Each level is ``{"bid": (price, size), "ask": (price, size)}``."""
        self._snaps.append(snap)

    def compute(self) -> dict[str, Any]:
        if len(self._snaps) < 2:
            return {
                "of_per_level": [],
                "of_aggregated": 0.0,
                "imbalance_label": "neutral",
                "levels_used": 0,
                "snaps_used": len(self._snaps),
            }
        prev, cur = self._snaps[-2], self._snaps[-1]
        # Use ``len(...)`` (count of keyed levels) instead of
        # ``max(prev.keys())`` (highest index). For a 5-key snapshot
        # indexed 0..4, ``max(keys) == 4`` would yield one fewer level
        # than the snapshot actually contains.
        n_used = min(self.levels, min((len(prev) if prev else 0), (len(cur) if cur else 0)))
        per_level: list[float] = []
        for lvl_i in range(n_used):
            # prev_bid, prev_ask, cur_bid, cur_ask
            pb = prev.get(lvl_i, {})
            cb = cur.get(lvl_i, {})
            pbp, pbs = _safe_tuple(pb.get("bid"))
            pap, pas = _safe_tuple(pb.get("ask"))
            cbp, cbs = _safe_tuple(cb.get("bid"))
            cap, cas = _safe_tuple(cb.get("ask"))

            # Bid side: price up → +size, price down → -size, flat → Δsize
            of_bid = 0.0
            if cbp > pbp:
                of_bid += cbs
            elif cbp < pbp:
                of_bid -= cbs
            else:
                of_bid += cbs - pbs

            # Ask side: price up → +size (asks weakening / absorbed), price down → -size
            of_ask = 0.0
            if cap < pap:
                of_ask -= cas          # ask price came down → size grew → sell pressure
            elif cap > pap:
                of_ask += cas          # ask price rose → less liquidity on ask → buy pressure
            else:
                of_ask += pas - cas    # ask side size change inverted (less size = buy)

            per_level.append(of_bid + of_ask)

        agg = sum(per_level)
        return {
            "of_per_level": per_level,
            "of_aggregated": float(round(agg, 2)),
            "imbalance_label": _classify_imbalance(agg, per_level),
            "levels_used": n_used,
            "snaps_used": len(self._snaps),
        }


def _safe_tuple(v: Any) -> tuple[float, float]:
    if v is None:
        return (0.0, 0.0)
    if isinstance(v, (list, tuple)) and len(v) >= 2:
        return _safe_float(v[0]), _safe_float(v[1])
    return (0.0, 0.0)


def _classify_imbalance(agg: float, by_level: list[float]) -> str:
    if agg > 0 and by_level and any(v > 0 for v in by_level):
        return "buy_pressure"
    if agg < 0 and by_level and any(v < 0 for v in by_level):
        return "sell_pressure"
    return "neutral"


# ─────────────────────────────────────────────────────────────────────
# Chain-based structural OFI proxy
# ─────────────────────────────────────────────────────────────────────

class StructuralOFI:
    """Approximate OFI from options-chain snapshots when LOB data is absent.

    For each strike, we compare ``call_oi + put_oi`` between two chain
    snapshots and weight by call-vs-put asymmetry.  This is NOT the
    Xu/Gould/Howison MLOFI directly, but it produces a correlated proxy
    that is useful for the Flowseeker feed until a real LOB feed lands.

    Level selection: the implementation picks the first ``self.levels``
    strikes by strike order (a stable, deterministic anchor that does NOT
    depend on whether ``spot`` is provided; if you need nearest-to-spot
    you can sort the rows by ``|strike - spot|`` before pushing).

    Usage::

        sof = StructuralOFI(levels=5)
        sof.push_chain(parsed_route_chain_dict)   # same shape as routes flowseeker
        out = sof.compute()
    """

    def __init__(self, levels: int = 5, history: int = 4):
        self.levels = max(1, int(levels))
        self._chain: deque[list[dict[str, Any]]] = deque(maxlen=max(2, history))

    @staticmethod
    def _flatten_chain(chain_data: Iterable[dict[str, Any]]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for exp in chain_data or []:
            if not isinstance(exp, dict):
                continue
            for s in exp.get("strikes", []) or []:
                if not isinstance(s, list) or len(s) < 3:
                    continue
                cv, pv = s[1], s[2]
                if not cv or not pv:
                    continue
                try:
                    rows.append({
                        "strike": _safe_float(s[0]),
                        "call_oi": _safe_float(cv[4] if len(cv) > 4 else None),
                        "put_oi": _safe_float(pv[4] if len(pv) > 4 else None),
                        "call_vol": _safe_float(cv[11] if len(cv) > 11 else None),
                        "put_vol": _safe_float(pv[11] if len(pv) > 11 else None),
                    })
                except Exception:
                    continue
        return rows

    def push_chain(self, chain_data: Iterable[dict[str, Any]]) -> None:
        rows = self._flatten_chain(chain_data)
        rows.sort(key=lambda r: r.get("strike", 0))
        self._chain.append(rows)

    def compute(self) -> dict[str, Any]:
        if len(self._chain) < 2:
            return {
                "of_per_level": [],
                "of_aggregated": 0.0,
                "imbalance_label": "neutral",
                "levels_used": 0,
                "snaps_used": len(self._chain),
            }
        prev, cur = self._chain[-2], self._chain[-1]
        # Match by strike; iterate `self.levels` strikes closest to spot
        # (we don't have spot here — assume centre of the chain).
        prev_by = {r["strike"]: r for r in prev}
        cur_by = {r["strike"]: r for r in cur}
        strikes = sorted(set(prev_by.keys()) | set(cur_by.keys()))
        # pick first N strikes as "outer" levels
        levels_used = min(self.levels, len(strikes))
        chosen = strikes[:levels_used]
        per_level: list[float] = []
        for _lvl_i, k in enumerate(chosen):
            p, c = prev_by.get(k), cur_by.get(k)
            if not p or not c:
                per_level.append(0.0)
                continue
            # Structural OFI proxy:
            #   bid side  ≈ call OI change weighted by call dominance
            #   ask side  ≈ -put OI change weighted by put dominance
            call_oi_d = c["call_oi"] - p["call_oi"]
            put_oi_d = c["put_oi"] - p["put_oi"]
            call_oi_t = max(p["call_oi"], c["call_oi"], 1.0)
            put_oi_t = max(p["put_oi"], c["put_oi"], 1.0)
            # Weight by dominance direction.
            of_bid = call_oi_d * (c["call_oi"] / call_oi_t)       # call OI growth = buy
            of_ask = -(put_oi_d * (c["put_oi"] / put_oi_t))        # put OI growth = sell (inverted)
            per_level.append(of_bid + of_ask)

        agg = sum(per_level)
        return {
            "of_per_level": [_round(v) for v in per_level],
            "of_aggregated": _round(agg),
            "imbalance_label": _classify_imbalance(agg, per_level),
            "levels_used": levels_used,
            "snaps_used": len(self._chain),
        }


def _round(v: float, d: int = 2) -> float:
    if not math.isfinite(v):
        return 0.0
    return float(round(v, d))
