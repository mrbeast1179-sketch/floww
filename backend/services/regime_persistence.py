"""
backend/services/regime_persistence.py

Regime-Persistence classifier — steal-list rank #8 (value 6 / effort 2)
=========================================================================

A pure-logic post-processor that classifies a window of per-day
``gex_total`` values into one of four persistence regimes. Complements
floww's existing per-day dealer-positioning data with a 30-day stability
signal that the GEX-only panels don't surface.

LABELS
------

- ``persistent_positive``  : gex_total stayed > 0 for ≥ 75% of the window
- ``persistent_negative``  : gex_total stayed < 0 for ≥ 75% of the window
- ``transitional``         : sign flips on ≥ 25% of day-boundaries (n / 4)
                            AND window magnitude is non-trivial (max_abs
                            ≥ noise_floor)
- ``low_conviction``       : values cluster tightly around the mean (CV
                            < 0.10) OR the entire window sits below the
                            absolute noise floor so flips aren't
                            economically meaningful

METRICS (always returned alongside the regime label)
----------------------------------------------------

- ``sign_persistence_pct`` : max(pos_count, neg_count) / n
- ``flip_count``            : # of adjacent sign changes in the window
- ``magnitude_conviction``  : abs(mean) / (std + 1e-9) — confidence in
                              the average sign
- ``coefficient_of_variation`` : std / abs(mean) when mean != 0, else 0
- ``n_days_covered``        : # of valid (non-NaN, non-inf, non-missing)
                              gex_total rows used for classification

PURE-LOGIC: no yfinance calls, no DB writes, no logging side-effects. The
route layer (``backend/routes/steal_three.py``) fetches the per-day
``gex_total`` series via ``services.gex_history.get_gex_history_sync``
and passes the rows in.

INPUT SHAPE::

    rows = [
        {"ts": "2026-06-15T00:00:00+00:00", "gex_total": 12345.6},
        {"ts": "2026-06-16T00:00:00+00:00", "gex_total": 11200.3},
        ...
    ]

OUTPUT SCHEMA (keys always present, even on empty input)::

    {
        "regime":                  "persistent_positive" | "persistent_negative" |
                                   "transitional" | "low_conviction" | None,
        "sign_persistence_pct":    float,    # 0..1
        "flip_count":              int,
        "magnitude_conviction":    float,    # >= 0
        "coefficient_of_variation": float,    # >= 0
        "n_days_covered":          int,      # 0..len(rows)
        "window_label":            str,      # free-form echo of input
        "warnings":                list[str],
    }

Steal intent: ``iAmGiG/gex-llm-patterns/src/validation/regime_classifier.py``
(L110-243, ``classify_window`` + ``_classify_regime_type``) — port the four
metrics (sign-persistence %, flip count, magnitude conviction, CV) into
floww's pure-logic style. Thresholds are calibrated for floww's data
shape (``gex_total`` typically in hundreds-to-thousands range for
liquid names per ``gex_history.compute_gex_total_for_chain``).

Audit: ``backend/tests/services/test_regime_persistence.py`` (13 cases —
empty + single + all-positive + all-negative + alternating-flips + near-
zero-noise + stable-7-day + NaN/inf filter + missing-key + window-label
propagation + documented-keys + 50/50-mix boundary + module-constants
sanity).
"""

from __future__ import annotations

import math
from typing import Any

__all__ = [
    "classify_window",
    "REGIME_PERSISTENT_POSITIVE",
    "REGIME_PERSISTENT_NEGATIVE",
    "REGIME_TRANSITIONAL",
    "REGIME_LOW_CONVICTION",
    "PERSISTENCE_THRESHOLD",
    "CV_LOW_CONVICTION_MAX",
    "TRANSITIONAL_FLIP_DENOM",
    "NOISE_FLOOR_ABS",
]

# ─────────────────────────────────────────────────────────────────────
# Constants — threshold values exposed for downstream override / audit.
# Public (exported via __all__) so test_regime_persistence and any
# future front-end tile can read them via constants import.
# ─────────────────────────────────────────────────────────────────────

REGIME_PERSISTENT_POSITIVE = "persistent_positive"
REGIME_PERSISTENT_NEGATIVE = "persistent_negative"
REGIME_TRANSITIONAL = "transitional"
REGIME_LOW_CONVICTION = "low_conviction"

# Sign-persistence threshold: majority sign must hold for ≥ this fraction
# of the window for the regime to be classified as persistent_positive /
# persistent_negative. 0.75 = 75% of days have the same sign.
PERSISTENCE_THRESHOLD = 0.75

# Coefficient-of-variation ceiling for low_conviction classification.
# CV < 0.10 means the std is < 10% of the mean — values sit close to the
# mean regardless of sign — a flat regime with weak dealer conviction.
CV_LOW_CONVICTION_MAX = 0.10

# Sign-flip denominator: requires at least N/DENOM flips in a window of
# N to qualify as transitional. 4 (denom) means ≥ 25% of the day-boundaries
# show a sign flip.
TRANSITIONAL_FLIP_DENOM = 4

# Absolute-magnitude noise floor: when every gex_total value in the window
# has |value| < this threshold, the entire window is float-arithmetic
# noise and regime = low_conviction regardless of flip pattern. 1.0 is
# chosen empirically — floww's real-data gex_total values for liquid
# names sit well above 1.0 (per gex_history.compute_gex_total_for_chain
# formula: sign * gamma * OI * 100 * spot * 0.01).
NOISE_FLOOR_ABS = 1.0


# ─────────────────────────────────────────────────────────────────────
# Defensive extractor — coerce a single row's gex_total to a float
# ─────────────────────────────────────────────────────────────────────


def _safe_float(value: Any, key: str, warnings: list[str]) -> float | None:
    """Coerce a value to float; returns None + warning for None / NaN /
    inf / non-numeric inputs (so callers skip the row without crashing).
    """
    if value is None:
        warnings.append(f"{key} missing")
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        warnings.append(f"{key} not numeric")
        return None
    if not math.isfinite(v):
        warnings.append(f"{key} not finite (NaN/inf)")
        return None
    return v


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def classify_window(
    rows: list[dict[str, Any]],
    window_label: str = "30d",
) -> dict[str, Any]:
    """Classify a gex_total time-series window into a persistence regime.

    See module docstring for the input/output contract.
    """
    warnings: list[str] = []

    if not isinstance(rows, list):
        return {
            "regime": None,
            "sign_persistence_pct": 0.0,
            "flip_count": 0,
            "magnitude_conviction": 0.0,
            "coefficient_of_variation": 0.0,
            "n_days_covered": 0,
            "window_label": window_label,
            "warnings": ["rows must be a list"],
        }

    if not rows:
        return {
            "regime": None,
            "sign_persistence_pct": 0.0,
            "flip_count": 0,
            "magnitude_conviction": 0.0,
            "coefficient_of_variation": 0.0,
            "n_days_covered": 0,
            "window_label": window_label,
            "warnings": ["rows must be non-empty"],
        }

    # Filter to clean numeric gex_total values.
    cleaned: list[float] = []
    for r in rows:
        if not isinstance(r, dict):
            warnings.append("row not a dict — skipped")
            continue
        v = _safe_float(r.get("gex_total"), "gex_total", warnings)
        if v is not None:
            cleaned.append(v)

    n = len(cleaned)

    # All rows malformed or nan/inf — empty after cleaning.
    if n == 0:
        return {
            "regime": None,
            "sign_persistence_pct": 0.0,
            "flip_count": 0,
            "magnitude_conviction": 0.0,
            "coefficient_of_variation": 0.0,
            "n_days_covered": 0,
            "window_label": window_label,
            "warnings": warnings + ["no valid gex_total values post-cleaning"],
        }

    # Sign vector.
    signs = [1 if v > 0 else -1 for v in cleaned]
    pos_count = sum(1 for s in signs if s > 0)
    neg_count = n - pos_count
    if pos_count >= neg_count:
        majority_sign = 1
        sign_persistence_pct = pos_count / n
    else:
        majority_sign = -1
        sign_persistence_pct = neg_count / n

    # Flip count.
    flip_count = sum(
        1 for i in range(1, n) if signs[i] != signs[i - 1]
    )

    # Mean / std (population).
    mean = sum(cleaned) / n
    if n > 1:
        var = sum((v - mean) ** 2 for v in cleaned) / n
        std = math.sqrt(var)
    else:
        var = 0.0
        std = 0.0

    # magnitude_conviction — high when the absolute mean dwarfs the noise.
    # std + 1e-9 guards against div-by-zero on a flat window.
    magnitude_conviction = abs(mean) / (std + 1e-9)

    # coefficient_of_variation — undefined when mean is exactly zero.
    if abs(mean) < 1e-9:
        coefficient_of_variation = 0.0
    else:
        coefficient_of_variation = std / abs(mean)

    # Maximum absolute gex_total — used as a noise-floor check.
    max_abs = max(abs(v) for v in cleaned)

    # ── Arbitration (precedence matters — read carefully) ────────────
    regime: str | None = None

    if n < 2:
        # Single-sample window: cannot characterise regime, but the
        # flip_count and sign_persistence_pct are still well-defined.
        warnings.append(
            f"single-sample window — classification requires n>=2 (got n={n})"
        )
    elif sign_persistence_pct >= PERSISTENCE_THRESHOLD:
        # Strong majority sign → persistent regime.
        regime = (
            REGIME_PERSISTENT_POSITIVE if majority_sign == 1
            else REGIME_PERSISTENT_NEGATIVE
        )
    elif max_abs < NOISE_FLOOR_ABS:
        # Whole window sits below the absolute noise floor — flips are
        # not economically meaningful regardless of how many happen.
        # Overrides the transitional branch below.
        regime = REGIME_LOW_CONVICTION
    elif flip_count >= n / TRANSITIONAL_FLIP_DENOM:
        # Many sign flips in a non-trivial-magnitude window → transitional.
        regime = REGIME_TRANSITIONAL
    elif coefficient_of_variation < CV_LOW_CONVICTION_MAX:
        # Values cluster tightly around the mean (small CV relative to
        # mean) → low_conviction (signs may agree on direction but the
        # magnitude is too flat to commit a regime).
        regime = REGIME_LOW_CONVICTION
    # else: regime stays None — classification is inconclusive.

    return {
        "regime": regime,
        "sign_persistence_pct": float(round(sign_persistence_pct, 4)),
        "flip_count": flip_count,
        "magnitude_conviction": float(round(magnitude_conviction, 4)),
        "coefficient_of_variation": float(round(coefficient_of_variation, 4)),
        "n_days_covered": n,
        "window_label": window_label,
        "warnings": warnings,
    }
