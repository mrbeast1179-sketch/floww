"""
backend/services/risk_neutral_density.py

Risk-Neutral Density service — steal-list rank #4 (value 9 / effort 3)
======================================================================

Converts floww's existing per-strike call surface into the implied
risk-neutral probability density f_Q(K) over strikes at option expiry —
the Breeden–Litzenberger formula (1978):

    f_Q(K) = e^{r·T} · d²C(K) / dK²

where C(K) is the call price as a function of strike K, r is the risk-free
rate, and T is years-to-expiry. f_Q is the market-priced implied
probability density of the underlying's terminal value — the natural
"probability surface" complement to the strike cone (#10), consensus (#6),
and max-pain (#9) outputs.

Outputs (per `compute_rnd_pdf`):

    {
        "spot": float,
        "T_years": float,
        "r": float,
        "n_strikes_used": int,
        "n_grid_points": int,
        "x_grid": list[float],
        "pdf": list[float],
        "cdf": list[float],
        "expected_price": float,        # E[S_T] = ∫ K · f_Q(K) dK
        "expected_move_pct": float,     # (expected_price - spot)/spot × 100
        "median": float,                # K where CDF crosses 0.5
        "mode": float,                  # argmax of pdf
        "tail_probs": {
            "p_below_95pct_spot": float | None,
            "p_below_98pct_spot": float | None,
            "p_above_102pct_spot": float | None,
            "p_above_105pct_spot": float | None,
        },
        "warnings": list[str],
        "method": "cubic_spline_2nd_derivative" | "central_diff",
    }

ALGORITHM
---------

Pure-logic; no yfinance calls, no DB writes. All external I/O is owned
by the route layer (backend/routes/steal_three.py::rnd_endpoint) which
calls ``compute_rnd_pdf(chain_calls, spot, T, r)``.

Inputs (``chain_calls``):

    [
        {"strike": 90.0, "bid": ..., "ask": ..., "lastPrice": ...},
        ...
    ]

    The output of ``backend/server.py::fetch_spot_and_chains``
    filtered to one expiry + calls only.

Per-strike primary price resolver (mirrors the IV-solver convention at
``routes/steal_three.py:_iv_row``):
    mid = 0.5 * (bid + ask)        when both > 0
          lastPrice                otherwise

Strike-pruning step: filter to strikes K ∈ [0.7 · spot, 1.3 · spot].
Far-OTM/ITM tail strikes add numerical noise (the 2nd derivative is
already small there) without contributing shape information.

Smoothing engine (scipy-aware with graceful fallback):

  - When ≥4 valid strikes remain AND scipy is available: fit a natural
    cubic spline ``CubicSpline(strikes, prices)`` and compute the 2nd
    derivative via ``spline.derive(2)(x)`` on a 200-point evaluation grid.
    This is the .md-recommended algorithm ("cubic-spline smile smoothing +
    numerical 2nd derivative").

  - When fewer than 4 strikes remain OR scipy is unavailable: fall back
    to a pure-stdlib central-difference numerical 2nd derivative over
    the discrete call prices using a 2-strike adaptive step (ΔK = K[i+2] -
    K[i]) at each interior strike, then linearly-interpolate onto the
    evaluation grid.

Defensive guards (matches strike_cone.py):

  - Negative strikes filtered out (+ warning).
  - Non-numeric / NaN / inf prices coerced to None + warning.
  - PDF clipped to ≥ 0 (numerical ringing from spline 2nd derivative
    can produce tiny negatives near the boundaries).
  - PDF renormalised so the trapezoid-rule integral over x_grid is ≈ 1.0
    (±5% tolerance for 200-point discretisation).
  - CDF forced to end at 1.0 at K_max (compensates for the trapezoid-rule
    truncation).
  - Pure-logic: never raises on malformed input — every degradation
    surfaces a warning instead.

Steal intent: ``PavanAnanthSharma/Breeden-Litzenberger-formula-for-risk-neutral-densities``
(smile fit + reprice calls + d2C/dK2 = e^{rT} · f_Q(K)).

Audit: ``backend/tests/services/test_risk_neutral_density.py`` (20-case
hand-verified suite — empty/single/three/five-strike cases + IV-driven
width checks + integration + monotonicity + tail-prob sanity + r=0/T=0
edge cases + schema contract).
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import Any

# ─────────────────────────────────────────────────────────────────────
# Optional scipy dependency — checked at function-call time so the
# service degrades gracefully if a deployment is missing the optional
# install (numpy alone is in requirements.txt for sure; scipy is too per
# requirements.txt pinned at scipy==1.17.1 but defended here for future
# dependency-light environments).
# ─────────────────────────────────────────────────────────────────────
try:
    from scipy.integrate import trapezoid  # type: ignore[import-untyped]
    from scipy.interpolate import CubicSpline  # type: ignore[import-untyped]

    _SCIPY_AVAILABLE = True
except ImportError:
    _SCIPY_AVAILABLE = False


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────


def compute_rnd_pdf(
    chain_calls: Sequence[dict[str, Any]],
    spot: float = 0.0,
    T: float = 0.0,
    r: float = 0.05,
    expiry: str | None = None,
) -> dict[str, Any]:
    """Compute the Breeden–Litzenberger risk-neutral PDF of the underlying
    at one option expiry.

    Args:
        chain_calls: per-strike call dicts (rows from the yfinance chain).
            Each row needs at minimum ``strike``; price resolvers look at
            ``bid``, ``ask``, ``lastPrice`` in that priority order.
        spot: current underlying price (used for filter and tail-prob
            normalisation).
        T: years to expiry (T=0 returns a degenerate output + warning).
        r: risk-free rate (defaults to 5%, matching routes/steal_three.py).
        expiry: optional ISO date string for the chosen expiry
            (purely metadata — echoed in the output).

    Returns:
        A dict matching the schema documented at the top of this module.
        Always returns — never raises on malformed / sparse input.

    Notes:
        - Default evaluation grid has 200 points spanning the
          strike-pruning window [0.7·spot, 1.3·spot].
        - Strikes outside that window are dropped silently with a warning,
          keeping the integrator numerically stable.
        - T=0 returns an empty PDF with a warning (intrinsic-only call
          surface has zero 2nd derivative outside the spot strike).
    """
    warnings: list[str] = []

    # 1. Sanitize + filter + resolve mid prices ─────────────────────
    cleaned: list[tuple[float, float]] = []  # (strike, mid_price)
    for row in chain_calls:
        if not isinstance(row, dict):
            warnings.append("row not a dict — skipped")
            continue
        K = row.get("strike")
        if K is None:
            warnings.append("strike missing — row skipped")
            continue
        try:
            K_f = float(K)
        except (TypeError, ValueError):
            warnings.append(f"strike non-numeric: {K!r} — row skipped")
            continue
        if not math.isfinite(K_f) or K_f <= 0:
            warnings.append(
                f"strike non-positive / non-finite: {K_f} — row skipped"
            )
            continue
        bid = _to_float(row.get("bid"))
        ask = _to_float(row.get("ask"))
        last = _to_float(row.get("lastPrice"))
        mid = _resolve_mid(bid, ask, last)
        if mid is None:
            warnings.append(f"price unresolved on strike={K_f} — row skipped")
            continue
        cleaned.append((K_f, mid))

    # 2. Strike-pruning to focus window around spot ─────────────────
    if spot > 0 and math.isfinite(spot):
        K_low_prune = 0.7 * spot
        K_high_prune = 1.3 * spot
        before_n = len(cleaned)
        cleaned = [(k, p) for k, p in cleaned
                   if K_low_prune <= k <= K_high_prune]
        if before_n > 0 and len(cleaned) == 0:
            warnings.append(
                f"all strikes outside [{K_low_prune:.2f}, "
                f"{K_high_prune:.2f}] of spot={spot} — PDF empty"
            )

    # 2b. Re-sort after pruning — scipy.CubicSpline requires strictly
    # increasing x. yfinance comes pre-sorted but hand-crafted chains
    # and negative-strike + positive mixed chains (test fixtures) need
    # a defensive sort here so the integration step is feed-clean.
    cleaned.sort(key=lambda p: p[0])

    n = len(cleaned)
    method = "cubic_spline_2nd_derivative"

    # 3. Empty / sparse / T=0 guards ─────────────────────────────────
    if n < 1:
        return {
            "spot": spot, "T_years": T, "r": r, "expiry": expiry,
            "n_strikes_used": 0, "n_grid_points": 0,
            "x_grid": [], "pdf": [], "cdf": [],
            "expected_price": None, "expected_move_pct": None,
            "median": None, "mode": None,
            "tail_probs": {}, "warnings": warnings + ["no valid strikes"],
            "method": method,
        }

    if not math.isfinite(T) or T <= 0:
        warnings.append(
            f"T={T} — degenerate (Black-Scholes 2nd derivative undefined "
            f"at T=0); returning empty PDF"
        )
        return {
            "spot": spot, "T_years": T, "r": r, "expiry": expiry,
            "n_strikes_used": n, "n_grid_points": 0,
            "x_grid": [], "pdf": [], "cdf": [],
            "expected_price": None, "expected_move_pct": None,
            "median": None, "mode": None,
            "tail_probs": {}, "warnings": warnings,
            "method": method,
        }

    if n < 4 or not _SCIPY_AVAILABLE:
        if not _SCIPY_AVAILABLE:
            warnings.append(
                "scipy unavailable — falling back to central-difference 2nd derivative"
            )
        else:
            warnings.append(
                f"only {n} strikes — falling back to central-difference 2nd derivative (cubic spline needs ≥4 points)"
            )
        return _central_diff_rnd(cleaned, spot, T, r, expiry, warnings)

    # 4. Cubic-spline smoothing + 2nd derivative ──────────────────────
    strikes_arr = [k for k, _ in cleaned]
    prices_arr = [p for _, p in cleaned]

    K_min, K_max = strikes_arr[0], strikes_arr[-1]
    n_grid = 200
    x_grid = _linspace(K_min, K_max, n_grid)

    try:
        spline = CubicSpline(strikes_arr, prices_arr)
        second_deriv = [float(spline(x, 2)) for x in x_grid]
    except Exception as exc:
        warnings.append(
            f"CubicSpline failed ({type(exc).__name__}: {exc}) — falling "
            f"back to central-difference"
        )
        return _central_diff_rnd(cleaned, spot, T, r, expiry, warnings)

    # 5. Apply the e^{rT} factor + clip negatives ─────────────────────
    factor = math.exp(r * T)
    pdf_raw = [factor * d2 for d2 in second_deriv]
    pdf_clipped = [max(0.0, p) for p in pdf_raw]

    # 6. Trapezoid-rule normalisation ────────────────────────────────
    total = trapezoid(pdf_clipped, x_grid)
    if total <= 0:
        warnings.append(
            "PDF integrates to zero (spline 2nd derivative everywhere "
            "negative) — returning empty PDF"
        )
        return {
            "spot": spot, "T_years": T, "r": r, "expiry": expiry,
            "n_strikes_used": n, "n_grid_points": 0,
            "x_grid": [], "pdf": [], "cdf": [],
            "expected_price": None, "expected_move_pct": None,
            "median": None, "mode": None,
            "tail_probs": {}, "warnings": warnings,
            "method": method,
        }
    pdf_norm = [p / total for p in pdf_clipped]

    # 7. CDF via cumulative trapezoid → forced renormalised to 1.0 ───
    cdf = _cumulative_trapezoid(pdf_norm, x_grid)
    # Belt-and-suspenders: force CDF[-1] = 1.0 in case the trapezoid-rule
    # integral left a residual at the right edge of the grid.
    if cdf[-1] > 0:
        cdf = [c / cdf[-1] for c in cdf]
    else:
        # Already-failed total (caught above); this branch is defensive.
        cdf = [0.0] * n_grid

    # 8. Expected price (mean of K·f_Q(K)) via trapezoid-rule ────────
    weighted = [x_grid[i] * pdf_norm[i] for i in range(n_grid)]
    expected_price = float(trapezoid(weighted, x_grid))
    expected_move_pct = (
        (expected_price - spot) / spot * 100.0
        if spot > 0 else None
    )

    # 9. Median (K where CDF crosses 0.5) ─────────────────────────────
    median_idx = _first_ge(cdf, 0.5)
    median = x_grid[median_idx] if median_idx is not None else None

    # 10. Mode (argmax of pdf_norm) ───────────────────────────────────
    mode_idx = _argmax(pdf_norm)
    mode = x_grid[mode_idx]

    # 11. Tail-prob keys at standard spot-relative thresholds ────────
    tail_probs: dict[str, float | None] = {}
    if spot > 0:
        threshold_keys = (
            ("p_below_95pct_spot", 0.95 * spot, _cdf_at),
            ("p_below_98pct_spot", 0.98 * spot, _cdf_at),
            ("p_above_102pct_spot", 1.02 * spot, _one_minus_cdf_at),
            ("p_above_105pct_spot", 1.05 * spot, _one_minus_cdf_at),
        )
        for key, threshold, fn in threshold_keys:
            if K_min <= threshold <= K_max:
                tail_probs[key] = fn(cdf, x_grid, threshold)
            else:
                tail_probs[key] = None    # out of grid range

    return {
        "spot": spot, "T_years": T, "r": r, "expiry": expiry,
        "n_strikes_used": n, "n_grid_points": n_grid,
        "x_grid": x_grid,
        "pdf": pdf_norm,
        "cdf": cdf,
        "expected_price": round(expected_price, 4),
        "expected_move_pct": (
            round(expected_move_pct, 2)
            if expected_move_pct is not None else None
        ),
        "median": round(median, 4) if median is not None else None,
        "mode": round(mode, 4),
        "tail_probs": {k: (round(v, 4) if v is not None else None)
                       for k, v in tail_probs.items()},
        "warnings": warnings,
        "method": method,
    }


__all__ = [
    "compute_rnd_pdf",
]


# ─────────────────────────────────────────────────────────────────────
# Private helpers
# ─────────────────────────────────────────────────────────────────────


def _to_float(value: Any) -> float | None:
    """Coerce to float or None for non-numeric / NaN / inf inputs.

    Mirrors ``_safe_float`` in ``services/strike_cone.py``.
    """
    if value is None:
        return None
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(v):
        return None
    return v


def _resolve_mid(
    bid: float | None, ask: float | None, last: float | None,
) -> float | None:
    """Primary-price resolver: mid → lastPrice → None.

    Same convention as ``routes/steal_three.py::_iv_row`` so downstream
    badges read consistent prices.
    """
    if bid is not None and ask is not None and bid > 0 and ask > 0:
        return 0.5 * (bid + ask)
    if last is not None and last > 0:
        return last
    return None


def _linspace(start: float, stop: float, n: int) -> list[float]:
    """Pure-pure-Python linspace (avoid pulling numpy for one helper).
    Mirrors numpy.linspace semantics: n evenly-spaced values, endpoints
    inclusive.
    """
    if n < 2:
        return [start]
    step = (stop - start) / (n - 1)
    return [start + i * step for i in range(n)]


def _cumulative_trapezoid(pdf: list[float], x_grid: list[float]) -> list[float]:
    """Cumulative trapezoid integration: CDF = ∫_{-∞}^{x} pdf(s) ds on grid.

    Pure-Python implementation — avoids the numpy import for one
    function. Uses the trapezoid rule on each adjacent pair:
       CDF[i+1] = CDF[i] + 0.5 · (pdf[i] + pdf[i+1]) · (x_grid[i+1] - x_grid[i])
    """
    n = len(pdf)
    if n == 0 or len(x_grid) != n:
        return []
    cdf = [0.0] * n
    if n == 1:
        return cdf
    for i in range(n - 1):
        cdf[i + 1] = cdf[i] + 0.5 * (pdf[i] + pdf[i + 1]) * (x_grid[i + 1] - x_grid[i])
    return cdf


def _first_ge(values: list[float], target: float) -> int | None:
    """Return the smallest index i such that values[i] >= target.
    Returns None if no such i exists.
    """
    for i, v in enumerate(values):
        if v >= target:
            return i
    return None


def _argmax(values: list[float]) -> int:
    """Return the index of the largest value. Returns 0 on empty input."""
    if not values:
        return 0
    best_i = 0
    best_v = values[0]
    for i in range(1, len(values)):
        if values[i] > best_v:
            best_v = values[i]
            best_i = i
    return best_i


def _cdf_at(cdf: list[float], x_grid: list[float], x: float) -> float:
    """Linear-interpolate the CDF at an arbitrary x within x_grid."""
    if not cdf or not x_grid:
        return float("nan")
    if x <= x_grid[0]:
        return cdf[0]
    if x >= x_grid[-1]:
        return cdf[-1]
    # Find the bracket (x_grid[i] ≤ x < x_grid[i+1]) via simple scan
    # (cdf is short enough that linear scan beats bisect).
    for i in range(len(x_grid) - 1):
        if x_grid[i + 1] >= x:
            t = (x - x_grid[i]) / (x_grid[i + 1] - x_grid[i])
            return cdf[i] * (1.0 - t) + cdf[i + 1] * t
    return cdf[-1]    # pragma: no cover (fallback)


def _one_minus_cdf_at(
    cdf: list[float], x_grid: list[float], x: float,
) -> float:
    """Linear-interpolate (1 - CDF) at an arbitrary x within x_grid."""
    p = _cdf_at(cdf, x_grid, x)
    return 1.0 - p if math.isfinite(p) else float("nan")


# ─────────────────────────────────────────────────────────────────────
# Central-difference fallback (n < 4 strikes OR scipy unavailable)
# ─────────────────────────────────────────────────────────────────────


def _central_diff_rnd(
    cleaned: list[tuple[float, float]],
    spot: float,
    T: float,
    r: float,
    expiry: str | None,
    warnings: list[str],
) -> dict[str, Any]:
    """Pure-stdlib fallback: numerical 2nd derivative via central
    differences over the discrete call-price series.

    For each interior strike K[i] with K[i-2] ≤ K[i] ≤ K[i+2], compute:

        d²C/dK² ≈ (C[K[i+2]] - 2·C[K[i]] + C[K[i-2]]) / (K[i+2] - K[i-2])²

    Linear-interpolate the discrete PDF onto a 200-point grid.
    """
    warnings = list(warnings) + ["using central-diff fallback"]

    if not math.isfinite(T) or T <= 0 or len(cleaned) < 3:
        return {
            "spot": spot, "T_years": T, "r": r, "expiry": expiry,
            "n_strikes_used": len(cleaned), "n_grid_points": 0,
            "x_grid": [], "pdf": [], "cdf": [],
            "expected_price": None, "expected_move_pct": None,
            "median": None, "mode": None,
            "tail_probs": {}, "warnings": warnings,
            "method": "central_diff",
        }

    n = len(cleaned)
    # Interior points only — need i+1 and i-1 (or i+2 and i-2 for adaptive).
    # Use i+1 delta (simpler than adaptive i+2) since most chains are
    # evenly-spaced. Distinction noted in warnings if ΔK varies a lot.
    xi: list[float] = []
    fi: list[float] = []
    factor = math.exp(r * T)
    deltas = []
    for i in range(1, n - 1):
        # Adaptive step = (K[i+1] - K[i-1]) so uneven grids don't bias.
        dK = cleaned[i + 1][0] - cleaned[i - 1][0]
        deltas.append(dK)
        d2 = (cleaned[i + 1][1] - 2 * cleaned[i][1] + cleaned[i - 1][1]) / (
            dK * dK)
        xi.append(cleaned[i][0])
        fi.append(max(0.0, factor * d2))

    if not xi:
        warnings.append("central-diff: no interior points (chain too short)")
        return {
            "spot": spot, "T_years": T, "r": r, "expiry": expiry,
            "n_strikes_used": n, "n_grid_points": 0,
            "x_grid": [], "pdf": [], "cdf": [],
            "expected_price": None, "expected_move_pct": None,
            "median": None, "mode": None,
            "tail_probs": {}, "warnings": warnings,
            "method": "central_diff",
        }

    # ΔK uniformity check (warn if uneven)
    if len(set(round(d, 4) for d in deltas)) > 1:
        warnings.append("central-diff: uneven strike spacing")

    # Linear-interpolate onto a 200-point grid
    K_min, K_max = cleaned[0][0], cleaned[-1][0]
    if K_min == K_max:
        # Degenerate — return empty grid
        warnings.append("central-diff: degenerate strike range")
        return {
            "spot": spot, "T_years": T, "r": r, "expiry": expiry,
            "n_strikes_used": n, "n_grid_points": 0,
            "x_grid": [], "pdf": [], "cdf": [],
            "expected_price": None, "expected_move_pct": None,
            "median": None, "mode": None,
            "tail_probs": {}, "warnings": warnings,
            "method": "central_diff",
        }

    x_grid = _linspace(K_min, K_max, 200)
    pdf_norm = _resample_to_grid(xi, fi, x_grid)

    # Already in mass units but without normalisation; total integral
    # may differ from 1.0 because central-diff is approximate.
    # Normalise via cumulative-trapezoid + force CDF[-1] = 1.0 to keep
    # the integrator-result ≥ 0 and interpretable.
    cdf = _cumulative_trapezoid(pdf_norm, x_grid)
    if cdf[-1] > 0:
        pdf_norm = [p / cdf[-1] for p in pdf_norm]
        cdf = [c / cdf[-1] for c in cdf]
    else:
        warnings.append("central-diff: all 2nd derivatives ≤ 0")

    weighted = [x_grid[i] * pdf_norm[i] for i in range(len(x_grid))]
    expected_price = float(_trapezoid(weighted, x_grid))
    expected_move_pct = (
        (expected_price - spot) / spot * 100.0
        if spot > 0 else None
    )
    median_idx = _first_ge(cdf, 0.5)
    median = x_grid[median_idx] if median_idx is not None else None
    mode_idx = _argmax(pdf_norm)
    mode = x_grid[mode_idx]

    tail_probs: dict[str, float | None] = {}
    if spot > 0:
        threshold_keys = (
            ("p_below_95pct_spot", 0.95 * spot, _cdf_at),
            ("p_below_98pct_spot", 0.98 * spot, _cdf_at),
            ("p_above_102pct_spot", 1.02 * spot, _one_minus_cdf_at),
            ("p_above_105pct_spot", 1.05 * spot, _one_minus_cdf_at),
        )
        for key, threshold, fn in threshold_keys:
            if K_min <= threshold <= K_max:
                tail_probs[key] = fn(cdf, x_grid, threshold)
            else:
                tail_probs[key] = None

    return {
        "spot": spot, "T_years": T, "r": r, "expiry": expiry,
        "n_strikes_used": n, "n_grid_points": len(x_grid),
        "x_grid": x_grid,
        "pdf": pdf_norm,
        "cdf": cdf,
        "expected_price": round(expected_price, 4),
        "expected_move_pct": (
            round(expected_move_pct, 2)
            if expected_move_pct is not None else None
        ),
        "median": round(median, 4) if median is not None else None,
        "mode": round(mode, 4),
        "tail_probs": {k: (round(v, 4) if v is not None else None)
                       for k, v in tail_probs.items()},
        "warnings": warnings,
        "method": "central_diff",
    }


def _resample_to_grid(
    xi: list[float], fi: list[float], x_grid: list[float],
) -> list[float]:
    """Pure-Python linear-interpolation of (xi, fi) onto x_grid.

    Mirrors ``services/strike_cone.py::_interp_increasing`` semantics
    (clamp to endpoints when out-of-range).
    """
    out: list[float] = []
    sorted_pairs = sorted(zip(xi, fi, strict=False), key=lambda p: p[0])
    xs = [p[0] for p in sorted_pairs]
    ys = [p[1] for p in sorted_pairs]
    for x in x_grid:
        if x <= xs[0]:
            out.append(ys[0])
            continue
        if x >= xs[-1]:
            out.append(ys[-1])
            continue
        # Find the bracket
        found = False
        for i in range(len(xs) - 1):
            if xs[i + 1] >= x:
                t = (x - xs[i]) / (xs[i + 1] - xs[i])
                out.append(ys[i] * (1.0 - t) + ys[i + 1] * t)
                found = True
                break
        if not found:
            out.append(ys[-1])    # pragma: no cover
    return out


def _trapezoid(y: list[float], x: list[float]) -> float:
    """Pure-Python trapezoid-rule integration over (y, x)."""
    if not y or len(y) != len(x) or len(y) < 2:
        return 0.0
    out = 0.0
    for i in range(len(y) - 1):
        out += 0.5 * (y[i] + y[i + 1]) * (x[i + 1] - x[i])
    return out
