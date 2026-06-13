"""
backend/services/trinity_alignment.py

Trinity Alignment Index: Cross-correlates GEX flip levels (zero-gamma strikes)
between SPX, SPY, and QQQ to produce a 0-100 confluence score.

When all three instruments have zero-gamma levels near the same price,
it indicates strong dealer hedging alignment — a high-probability
magnetic level for price.

References:
- Zero-gamma level: strike where net dealer gamma exposure flips sign
- Trinity alignment: confluence of SPX/SPY/QQQ zero-gamma levels
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np


class TrinityAlignmentIndex:
    """Cross-correlates GEX flip levels between SPX, SPY, and QQQ."""

    def __init__(self, tolerance_pct: float = 0.005):
        """
        Args:
            tolerance_pct: max distance between flip levels to count as aligned (0.5%)
        """
        self.tolerance_pct = tolerance_pct

    def compute(self,
                spy_flip_levels: List[float],
                qqq_flip_levels: List[float],
                spx_flip_levels: List[float],
                spy_spot: float = 0.0,
                qqq_spot: float = 0.0,
                spx_spot: float = 0.0) -> Dict[str, Any]:
        """Compute Trinity Alignment Index.

        Returns dict with:
          - score: float (0-100)
          - aligned_levels: list of dicts with level, instruments, spread
          - spy_flip_levels: list
          - qqq_flip_levels: list
          - spx_flip_levels: list
          - nearest_alignment: dict or None (closest aligned level to current price)
          - regime: str ("STRONG", "MODERATE", "WEAK", "NONE")
        """
        if not spy_flip_levels and not qqq_flip_levels and not spx_flip_levels:
            return {
                "score": 0.0,
                "aligned_levels": [],
                "spy_flip_levels": spy_flip_levels,
                "qqq_flip_levels": qqq_flip_levels,
                "spx_flip_levels": spx_flip_levels,
                "nearest_alignment": None,
                "regime": "NONE",
            }

        # Find aligned levels across instruments
        aligned = self._find_alignments(
            spy_flip_levels, qqq_flip_levels, spx_flip_levels,
            spy_spot, qqq_spot, spx_spot,
        )

        # Score based on number and tightness of alignments
        score = self._compute_score(aligned)

        # Regime
        if score >= 75:
            regime = "STRONG"
        elif score >= 50:
            regime = "MODERATE"
        elif score >= 25:
            regime = "WEAK"
        else:
            regime = "NONE"

        # Find nearest alignment to current price
        nearest = self._find_nearest(aligned, spy_spot, qqq_spot, spx_spot)

        return {
            "score": round(score, 2),
            "aligned_levels": aligned,
            "spy_flip_levels": spy_flip_levels,
            "qqq_flip_levels": qqq_flip_levels,
            "spx_flip_levels": spx_flip_levels,
            "nearest_alignment": nearest,
            "regime": regime,
        }

    def _find_alignments(self, spy_levels, qqq_levels, spx_levels,
                         spy_spot, qqq_spot, spx_spot) -> List[Dict]:
        """Find flip levels that align across instruments."""
        aligned = []

        # Normalize SPX levels to SPY-equivalent (SPX ≈ SPY * 10)
        spx_normalized = [s / 10.0 for s in spx_levels] if spx_levels else []

        all_candidates = []
        for lvl in spy_levels:
            all_candidates.append(("SPY", lvl, spy_spot))
        for lvl in qqq_levels:
            all_candidates.append(("QQQ", lvl, qqq_spot))
        for lvl in spx_normalized:
            all_candidates.append(("SPX", lvl, spx_spot / 10.0 if spx_spot else 0))

        # Group nearby levels
        used = set()
        for i, (inst1, lvl1, spot1) in enumerate(all_candidates):
            if i in used:
                continue
            group = [(inst1, lvl1)]
            used.add(i)
            for j, (inst2, lvl2, spot2) in enumerate(all_candidates):
                if j in used or i == j:
                    continue
                ref = spot1 if spot1 > 0 else lvl1
                if ref > 0 and abs(lvl1 - lvl2) / ref < self.tolerance_pct:
                    group.append((inst2, lvl2))
                    used.add(j)
            if len(group) >= 2:
                levels = [lev for _, lev in group]
                mean_level = np.mean(levels)
                spread = max(levels) - min(levels)
                ref_spot = spot1 if spot1 > 0 else mean_level
                spread_pct = spread / ref_spot if ref_spot > 0 else 0
                aligned.append({
                    "level": round(mean_level, 2),
                    "instruments": [i for i, _ in group],
                    "spread": round(spread, 2),
                    "spread_pct": round(spread_pct * 100, 4),
                    "n_instruments": len(group),
                })

        return sorted(aligned, key=lambda x: x["spread_pct"])

    def _compute_score(self, aligned: List[Dict]) -> float:
        """Score based on number and tightness of alignments."""
        if not aligned:
            return 0.0

        score = 0.0
        for a in aligned:
            # More instruments = higher score
            inst_bonus = min(a["n_instruments"] / 3.0, 1.0) * 40
            # Tighter spread = higher score
            spread_penalty = min(a["spread_pct"] / (self.tolerance_pct * 100), 1.0) * 30
            score += inst_bonus + (30 - spread_penalty)

        return min(score, 100.0)

    def _find_nearest(self, aligned, spy_spot, qqq_spot, spx_spot) -> Optional[Dict]:
        """Find the alignment nearest to current price."""
        if not aligned:
            return None
        spots = [s for s in [spy_spot, qqq_spot, spx_spot / 10.0 if spx_spot else 0] if s > 0]
        if not spots:
            return aligned[0] if aligned else None
        mean_spot = np.mean(spots)
        nearest = min(aligned, key=lambda a: abs(a["level"] - mean_spot))
        nearest["distance_from_spot"] = round(abs(nearest["level"] - mean_spot), 2)
        return nearest
