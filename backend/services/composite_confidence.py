"""
backend/services/composite_confidence.py

Composite Score Confidence Bands — bootstrap-style CI around the
synthesised 0..100 Composite Flow Score.

The shipped :class:`CompositeFlowScore.compute` emits a single point
estimate like ``78``. From a trader's perspective that's incomplete:
is ``78`` the result of a stable reading, or is it noise from one
poll cycle that will swing to 60 next cycle? The bands tell you.

We wrap the point estimate with a 95% confidence interval derived
from the **non-parametric bootstrap** of the rolling sub-score
history in :mod:`backend.services.chain_replay`. Pure-Python only —
no torch / numba / scipy (Round-9 freeze rule).

Method (non-parametric bootstrap)
---------------------------------

Given N historical sub-score dicts ``H = [h_1, h_2, ..., h_N]`` from
``chain_replay.tail(N)``:

  1. Draw ``B`` resamples of size ``N`` with replacement from ``H``.
  2. For each resample compute the mean of each of the four
     sub-scores (``illiquidity``, ``toxicity``, ``dislocation``,
     ``direction``).
  3. Weight those four means via the published
     :class:`CompositeFlowScore` weighting
     ``(0.30, 0.25, 0.25, 0.20)`` to obtain one bootstrapped
     composite value per draw.
  4. Sort the ``B`` bootstrapped composites and read the 2.5th and
     97.5th percentiles → 95% CI bounds.

This works under hard-score bounds ``[0, 100]`` because the
bootstrap respects the empirical support of the historical data.

Output schema (snake_case, mirrors ``CompositeFlowScore``)::

    {
        "score":            float,    # point estimate (live composite)
        "lower":            float,    # 2.5th percentile of bootstrapped CIs
        "upper":            float,    # 97.5th percentile
        "width":            float,    # upper - lower
        "label":            "HIGH"|"MED"|"WATCH"|"LOW",  # point-estimate band
        "confidence_label": "NARROW"|"MODERATE"|"WIDE",
        "is_warming":       bool,
        "n_samples":        int,      # count of valid history entries used
    }

Confidence width bands::

      width <  10  → NARROW    (stable within a single tier)
      10 ≤ width < 25  → MODERATE  (single tier, but jittering)
      width ≥ 25  → WIDE      (potentially spanning multiple tiers)

Label interpretation::

The displayed label is ALWAYS the point estimate's tier (so alert
thresholds built on the score's tier keep firing on the same
condition). The width/confidence_label is ONLY a visual flag — the
frontend uses it to colour the band chip but does NOT override the
point-estimate's tier pill.

Usage::

    from services.chain_replay import ChainReplay
    from services.composite_confidence import CompositeConfidence

    cr = ChainReplay(buffer_size=240)
    history = cr.read_tail(last_n=64)
    out = CompositeConfidence.compute(history)
"""
from __future__ import annotations

import random
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Weights — MUST stay synchronised with composite_flow_score.py.
# These are duplicated here (rather than imported) so the bootstrap
# service has no internal coupling to the synthesiser. If the
# published weights ever change, update both files. Rescaled to the
# 5-component split in the steal-list deferred-(b) ship:
#   illiq 0.30 → 0.25 · tox 0.25 → 0.20 · dis unchanged 0.25 ·
#   dir unchanged 0.20 · NEW sentiment 0.10.
# ─────────────────────────────────────────────────────────────────────

_W_ILLIQUIDITY = 0.25
_W_TOXICITY    = 0.20
_W_DISLOCATION = 0.25
_W_DIRECTION   = 0.20
_W_SENTIMENT   = 0.10

# Bootstrap configuration ─
_DEFAULT_B_RESAMPLES = 100          # 100 resamples × N history = ~6400 ops
_DEFAULT_MIN_HISTORY = 5            # Below this, we say "warming"
_PERCENTILE_LOW = 0.025             # 2.5th percentile
_PERCENTILE_HIGH = 0.975            # 97.5th percentile

# Width classification thresholds
_WIDTH_NARROW = 10.0
_WIDTH_MODERATE = 25.0

# Confidence label constants
CONFIDENCE_NARROW = "NARROW"
CONFIDENCE_MODERATE = "MODERATE"
CONFIDENCE_WIDE = "WIDE"

CONFIDENCE_COLORS: dict[str, str] = {
    CONFIDENCE_NARROW:  "#22c55e",   # green
    CONFIDENCE_MODERATE: "#fbbf24",  # amber
    CONFIDENCE_WIDE:    "#ef4444",   # red
}


# ─────────────────────────────────────────────────────────────────────
# Pure helpers
# ─────────────────────────────────────────────────────────────────────

def _coerce_float(v: Any, default: float = 0.0) -> float:
    """Strict float coercion — None / non-numeric / NaN / Inf → default.

    Mirrors :func:`chain_replay._safe_float` but without the clamp
    option (we don't need bounds clamping here — sub-scores feed
    straight into the Composite formula which has its own clamp).
    """
    if v is None:
        return float(default)
    try:
        f = float(v)
    except (TypeError, ValueError):
        return float(default)
    # NaN / Inf check via micro-optimised identity comparison.
    if f != f or f == float("inf") or f == float("inf") * -1:
        return float(default)
    return f


def _classify_width(width: float) -> str:
    """Map a CI width (in score-units, [0, 100]) to a 3-band tier."""
    if width < _WIDTH_NARROW:
        return CONFIDENCE_NARROW
    if width < _WIDTH_MODERATE:
        return CONFIDENCE_MODERATE
    return CONFIDENCE_WIDE


def _extract_sub_scores(snap: dict[str, Any]) -> tuple[float, float, float, float, float]:
    """Read the 5 sub-scores out of a snapshot dict. Defaults to 0.0.

    Steal-list deferred-(b) ship: 4-tuple widened to 5-tuple to absorb
    sentiment. If the legacy 4-tuple shape is encountered (older snapshots
    in chain_replay), sentiment defaults to 0.0 — that sub-score is
    silently absent from older history entries, NOT a hard-mismatch.
    """
    sub = (snap.get("sub_scores") or {}) if isinstance(snap, dict) else {}
    return (
        _coerce_float(sub.get("illiquidity", 0.0)),
        _coerce_float(sub.get("toxicity",    0.0)),
        _coerce_float(sub.get("dislocation", 0.0)),
        _coerce_float(sub.get("direction",   0.0)),
        _coerce_float(sub.get("sentiment",   0.0)),
    )


def _weight_aggregate(ill: float, tox: float, dis: float, dirn: float, sent: float) -> float:
    """Apply published composite weights to five sub-scores."""
    return 100.0 * (
        _W_ILLIQUIDITY * ill
        + _W_TOXICITY    * tox
        + _W_DISLOCATION * dis
        + _W_DIRECTION   * dirn
        + _W_SENTIMENT   * sent
    )


# ─────────────────────────────────────────────────────────────────────
# CompositeConfidence — stateless bootstrap CI
# ─────────────────────────────────────────────────────────────────────

class CompositeConfidence:
    """Stateless non-parametric bootstrap of the Composite Flow Score."""

    @staticmethod
    def compute(
        history: list[dict[str, Any]],
        b_resamples: int = _DEFAULT_B_RESAMPLES,
        rng: random.Random | None = None,
    ) -> dict[str, Any]:
        """Compute the 95% bootstrap CI of the composite score over history.

        ``history`` is a chronological list of snapshot dicts as produced
        by :func:`chain_replay.ChainReplay.read_tail` /
        :func:`chain_replay.ChainReplay.read_window`. The LAST entry is
        treated as the live "now" — its ``composite`` is the point
        estimate and its ``label`` is the displayed tier.

        ``rng`` is optional; injectable so tests can pin a deterministic
        RNG and avoid flaky bootstrap draws. Defaults to ``None`` which
        uses the module-level ``random`` (non-seeded — bootstrap
        percentiles are robust to this in practice).

        Returns the snake_case dict per the module docstring.
        """
        # 1. Live snapshot — LAST entry of the history is "now".
        if not history or not isinstance(history, list):
            return _warming_response(0.0, 0, "LOW")

        latest = history[-1]
        if not isinstance(latest, dict):
            return _warming_response(0.0, 0, "LOW")

        point_est = _coerce_float(latest.get("composite", 0.0))
        live_label = str(latest.get("label") or "LOW")
        live_warming = bool(latest.get("is_warming", True))

        # 2. Filter to valid (non-warming) sub-score vectors.
        valid: list[dict[str, Any]] = [
            s for s in history
            if isinstance(s, dict) and not bool(s.get("is_warming", True))
        ]

        # 3. Warm-out: fewer than 5 valid samples → confidence not yet
        #    estimable. Return a "warm" payload whose score/lower/upper
        #    all equal the live point estimate (width=0).
        if live_warming or len(valid) < _DEFAULT_MIN_HISTORY:
            return {
                "score":            round(point_est, 1),
                "lower":            round(point_est, 1),
                "upper":            round(point_est, 1),
                "width":            0.0,
                "label":            live_label,
                "confidence_label": CONFIDENCE_WIDE,  # worst-case render
                "is_warming":       True,
                "n_samples":        len(valid),
            }

        # 4. Bootstrap resampling — assemble N resamples, compute the
        #    composite for each.
        n = len(valid)
        b = max(1, int(b_resamples))
        local_rng = rng if rng is not None else random

        # Slight optimisation: pre-extract the 5 sub-score vectors out
        # of history to make the inner resample loop pure-Python fast.
        ill_arr, tox_arr, dis_arr, dir_arr, sent_arr = [], [], [], [], []
        for s in valid:
            ill, tox, dis, dirn, send = _extract_sub_scores(s)
            ill_arr.append(ill)
            tox_arr.append(tox)
            dis_arr.append(dis)
            dir_arr.append(dirn)
            sent_arr.append(send)

        means: list[float] = []
        for _ in range(b):
            il = 0.0
            tx = 0.0
            di = 0.0
            dr = 0.0
            se = 0.0
            # Resample N indices with replacement.
            for _i in range(n):
                j = local_rng.randrange(n)
                il += ill_arr[j]
                tx += tox_arr[j]
                di += dis_arr[j]
                dr += dir_arr[j]
                se += sent_arr[j]
            means.append(_weight_aggregate(il / n, tx / n, di / n, dr / n, se / n))

        means.sort()
        # Percentile bounds — clamp indices into [0, b - 1].
        idx_lo = max(0, min(b - 1, int(_PERCENTILE_LOW  * b)))
        idx_hi = max(0, min(b - 1, int(_PERCENTILE_HIGH * b)))
        lower = float(means[idx_lo])
        upper = float(means[idx_hi])
        width = max(0.0, upper - lower)

        return {
            "score":            round(point_est, 1),
            "lower":            round(lower, 1),
            "upper":            round(upper, 1),
            "width":            round(width, 1),
            "label":            live_label,
            "confidence_label": _classify_width(width),
            "is_warming":       False,
            "n_samples":        int(n),
        }

    @staticmethod
    def colour_for(confidence_label: str) -> str:
        """Return the CSS hex colour for a given confidence tier.

        Used by the frontend to colour the ``[lower-upper]`` band chip.
        Returns a neutral grey for unknown labels.
        """
        return CONFIDENCE_COLORS.get(
            str(confidence_label or ""),
            "#94a3b8",
        )


# ─────────────────────────────────────────────────────────────────────
# Internal helper — concise warming-state response
# ─────────────────────────────────────────────────────────────────────

def _warming_response(score: float, n: int, label: str) -> dict[str, Any]:
    """Return a warming payload — bounds collapse to the point estimate."""
    s = float(score or 0.0)
    return {
        "score":            round(s, 1),
        "lower":            round(s, 1),
        "upper":            round(s, 1),
        "width":            0.0,
        "label":            str(label or "LOW"),
        "confidence_label": CONFIDENCE_WIDE,
        "is_warming":       True,
        "n_samples":        int(max(0, n)),
    }


__all__ = [
    "CompositeConfidence",
    "CONFIDENCE_NARROW",
    "CONFIDENCE_MODERATE",
    "CONFIDENCE_WIDE",
    "CONFIDENCE_COLORS",
    "_WIDTH_NARROW",
    "_WIDTH_MODERATE",
]
