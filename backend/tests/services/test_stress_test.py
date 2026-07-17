"""
backend/tests/services/test_stress_test.py

Steal-List #12 — Whole-book scenario stress-test matrix  [high-impact]
========================================================================
value 8 / effort 4 (V/E 2.0 — highest unblocked value after #7).
Steal from George-Dros_Options_Portfolio/functions.py:457-770
(analyze_combined_impact, process_portfolio, compute_portfolio_stats)
+ 3D surface plots L797-884.

Lands in floww: pure-logic ``backend/services/stress_test.py`` computing
a 3D P&L matrix over (spot × IV × time) shocks against the existing
position store; aggregated marginals per axis; Plotly surface on Skylit.

Algorithm (RED contract — the impl must hit these exact values)
-----------------------------------------------------------------
For each leg [K, T_years, iv, quantity, kind∈{call,put}, side∈{buy,sell}]:

    sign  = +1 if side == "buy" else -1
    base  = bs_price(current_spot, K, T, r, iv, kind)
    leg_base_value = base * quantity * 100 * sign  # 100 = contract multiplier

For each (spot_mult, iv_mult, days_decay):
    spot_new = current_spot * spot_mult
    iv_new   = iv * iv_mult
    T_new    = max(0.0, T - days_decay / 365.0)

    if T_new <= 0:
        shocked_price = intrinsic(spot_new, K, kind)
    else:
        shocked_price = bs_price(spot_new, K, T_new, r, iv_new, kind)

    leg_pnl = (shocked_price - base) * quantity * 100 * sign
    cell.total_book_pnl = sum(leg_pnl for leg in positions)

Marginals:
    marginal_pnl_per_spot  = [(sm, pnl) for sm ∈ spot_mults]            (iv=1.0, t=0)
    marginal_pnl_per_iv    = [(im, pnl) for im ∈ iv_mults]               (spot=1.0, t=0)
    marginal_pnl_per_t     = [(td, pnl) for td ∈ days_decay]             (spot=1.0, iv=1.0)

Output dict schema (frozen — test_bucket_4 verifies this):
    base_spot, base_book_value, n_legs, shock_axes (3 lists),
    pnl_matrix (list of {spot_mult, iv_mult, days_decay,
                          shocked_book_value, total_book_pnl}),
    marginal_pnl_per_spot (list of [mult, pnl]),
    marginal_pnl_per_iv   (list of [mult, pnl]),
    marginal_pnl_per_t    (list of [days, pnl]),
    warnings (list[str]).

16 cases organized in 4 buckets mirroring the canonical steal-list TDD
pattern (test_squeeze_exposure_profile / test_realized_volatility):

       Bucket 1 — Math correctness (4) + T=0 collapse
       Bucket 2 — Aggregation & grid shape (4)
       Bucket 3 — Boundary & edge cases (4)
       Bucket 4 — Schema contract & defensive degradation (4)
"""

from __future__ import annotations

import math

import pytest

# ─────────────────────────────────────────────────────────────────────
# Helpers — local Black-Scholes reference so tests pin on a formula the
# impl can match precisely (no coupling to the impl's exact BS impl).
# ─────────────────────────────────────────────────────────────────────


def _norm_cdf(x: float) -> float:
    """Standard-normal CDF via math.erf (avoids scipy dependency)."""
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _bs(spot: float, K: float, T: float, r: float, sigma: float, kind: str) -> float:
    """Black-Scholes reference pricer; intrinsic fallback at T<=0."""
    if T <= 0.0 or sigma <= 0.0:
        if kind == "call":
            return max(spot - K, 0.0)
        return max(K - spot, 0.0)
    sqrt_t = math.sqrt(T)
    d1 = (math.log(spot / K) + (r + 0.5 * sigma * sigma) * T) / (sigma * sqrt_t)
    d2 = d1 - sigma * sqrt_t
    if kind == "call":
        return spot * _norm_cdf(d1) - K * math.exp(-r * T) * _norm_cdf(d2)
    return K * math.exp(-r * T) * _norm_cdf(-d2) - spot * _norm_cdf(-d1)


CANONICAL_POSITIONS: list[dict[str, object]] = [
    {"K": 100.0, "T": 30 / 365.0, "iv": 0.20, "quantity": 1,
     "kind": "call", "side": "buy"},
    {"K": 105.0, "T": 30 / 365.0, "iv": 0.20, "quantity": 1,
     "kind": "call", "side": "sell"},
]


EXPECTED_SCHEMA_KEYS: set[str] = {
    "base_spot", "base_book_value", "n_legs", "shock_axes",
    "pnl_matrix", "marginal_pnl_per_spot", "marginal_pnl_per_iv",
    "marginal_pnl_per_t", "warnings",
}


# ─────────────────────────────────────────────────────────────────────
# Bucket 1 — Math correctness + T=0 collapse (4 cases)
# ─────────────────────────────────────────────────────────────────────


def test_baseline_price_yields_zero_pnl_at_unshocked_coordinates() -> None:
    """The (1.0, 1.0, 0) cell must return exactly 0.0 P&L (no shock = no change)."""
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix(
        CANONICAL_POSITIONS, current_spot=100.0,
    )
    baseline = next(
        c for c in out["pnl_matrix"]
        if c["spot_mult"] == 1.0
        and c["iv_mult"] == 1.0
        and c["days_decay"] == 0.0
    )
    assert baseline["total_book_pnl"] == pytest.approx(0.0, abs=1e-9)


def test_time_decay_beyond_expiry_collapses_to_intrinsic_payoff() -> None:
    """A 60d shock on a 5DTE option must route through T<=0 intrinsic payoff.

    Intrinsic at spot_new=105 for K=100 call = 5.0; short-of-long,
    sign=+1 (buy), qty=1 ⇒ P&L = (5.0 − base) * 1 * 100.
    """
    from services.stress_test import compute_stress_test_matrix

    positions = [{
        "K": 100.0, "T": 5 / 365.0, "iv": 0.50, "quantity": 1,
        "kind": "call", "side": "buy",
    }]
    out = compute_stress_test_matrix(positions, current_spot=105.0)
    cell = next(
        c for c in out["pnl_matrix"]
        if c["spot_mult"] == 1.0
        and c["iv_mult"] == 1.0
        and c["days_decay"] == 60.0
    )
    base = _bs(105.0, 100.0, 5 / 365.0, 0.045, 0.50, "call")
    expected_pnl = (max(105.0 - 100.0, 0.0) - base) * 1 * 100
    assert cell["total_book_pnl"] == pytest.approx(expected_pnl, abs=1e-6)


def test_hand_traced_call_spread_at_expiry() -> None:
    """100/105 call spread at (spot=1.10×, iv=1.0×, time=30d) ⇒ exact P&L.

    With r=0.0, both options expire (T was 30/365).
    Long 100C intrinsic at S=110: 10.0; short 105C intrinsic: 5.0.
    Base BS values computed via the reference helper. The test pins the
    P&L computed via the SAME BS the impl uses, so FP agrees to ~1e-6.
    """
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix(
        CANONICAL_POSITIONS, current_spot=100.0, r=0.0,
    )
    cell = next(
        c for c in out["pnl_matrix"]
        if c["spot_mult"] == 1.10
        and c["iv_mult"] == 1.0
        and c["days_decay"] == 30.0
    )
    long_base = _bs(100.0, 100.0, 30 / 365.0, 0.0, 0.20, "call")
    short_base = _bs(100.0, 105.0, 30 / 365.0, 0.0, 0.20, "call")
    base_book = long_base * 1 * 100 - short_base * 1 * 100  # buy +, sell -
    shocked_book = (
        max(110.0 - 100.0, 0.0) * 1 * 100
        - max(110.0 - 105.0, 0.0) * 1 * 100
    )
    expected_pnl = shocked_book - base_book
    assert cell["total_book_pnl"] == pytest.approx(expected_pnl, abs=1e-6)


def test_iv_shock_sign_for_long_call_increases_value() -> None:
    """A long ATM call's value increases with IV under spot unchanged.

    IV up ⇒ positive P&L (long vega benefits); IV down ⇒ negative P&L.
    Pins the directional sign convention of the IV-axis marginals.
    """
    from services.stress_test import compute_stress_test_matrix

    positions = [{
        "K": 100.0, "T": 60 / 365.0, "iv": 0.30, "quantity": 1,
        "kind": "call", "side": "buy",
    }]
    out = compute_stress_test_matrix(positions, current_spot=100.0)
    iv_up_pnl = next(
        v for mult, v in out["marginal_pnl_per_iv"] if mult == 1.20
    )
    iv_down_pnl = next(
        v for mult, v in out["marginal_pnl_per_iv"] if mult == 0.80
    )
    assert iv_up_pnl > 0.0
    assert iv_down_pnl < 0.0


# ─────────────────────────────────────────────────────────────────────
# Bucket 2 — Aggregation & grid shape (4 cases)
# ─────────────────────────────────────────────────────────────────────


def test_grid_dimensions_match_axis_lengths() -> None:
    """pnl_matrix length = |spot| × |iv| × |days|."""
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix(
        CANONICAL_POSITIONS, current_spot=100.0,
    )
    axes = out["shock_axes"]
    expected_n = (
        len(axes["spot_multipliers"])
        * len(axes["iv_multipliers"])
        * len(axes["days_decay"])
    )
    assert len(out["pnl_matrix"]) == expected_n


def test_marginals_isolate_single_axis() -> None:
    """marginal_pnl_per_spot holds IV=1.0 and t=0.0; equals the matching
    cell of the master pnl_matrix at those coordinates."""
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix(
        CANONICAL_POSITIONS, current_spot=100.0,
    )
    for spot_m, pnl in out["marginal_pnl_per_spot"]:
        cell = next(
            c for c in out["pnl_matrix"]
            if c["spot_mult"] == spot_m
            and c["iv_mult"] == 1.0
            and c["days_decay"] == 0.0
        )
        assert pnl == pytest.approx(cell["total_book_pnl"], abs=1e-9)


def test_long_vs_short_sign_inversion() -> None:
    """Long+short of identical contracts ⇒ P&L identically 0 across the grid."""
    from services.stress_test import compute_stress_test_matrix

    long_pos = [{
        "K": 100.0, "T": 30 / 365.0, "iv": 0.20, "quantity": 1,
        "kind": "call", "side": "buy",
    }]
    short_pos = [{
        "K": 100.0, "T": 30 / 365.0, "iv": 0.20, "quantity": 1,
        "kind": "call", "side": "sell",
    }]
    out = compute_stress_test_matrix(
        long_pos + short_pos, current_spot=100.0,
    )
    for cell in out["pnl_matrix"]:
        assert cell["total_book_pnl"] == pytest.approx(0.0, abs=1e-9)


def test_multiple_legs_sum_accurately() -> None:
    """Aggregated N-leg matrix equals the sum of N single-leg matrices.

    Linear-superposition sanity: every leg's per-cell P&L adds linearly
    under the (price × qty × 100 × sign) formula; verifies the impl
    didn't accidentally apply any non-linear aggregation.
    """
    from services.stress_test import compute_stress_test_matrix

    legs = [
        {"K": 95.0, "T": 30 / 365.0, "iv": 0.30, "quantity": 2,
         "kind": "call", "side": "buy"},
        {"K": 105.0, "T": 30 / 365.0, "iv": 0.25, "quantity": 1,
         "kind": "put", "side": "buy"},
        {"K": 110.0, "T": 30 / 365.0, "iv": 0.35, "quantity": 1,
         "kind": "call", "side": "sell"},
    ]
    out_combined = compute_stress_test_matrix(legs, current_spot=100.0)
    for cell in out_combined["pnl_matrix"]:
        indiv_sum = 0.0
        for leg in legs:
            single = compute_stress_test_matrix([leg], current_spot=100.0)
            single_cell = next(
                c for c in single["pnl_matrix"]
                if c["spot_mult"] == cell["spot_mult"]
                and c["iv_mult"] == cell["iv_mult"]
                and c["days_decay"] == cell["days_decay"]
            )
            indiv_sum += single_cell["total_book_pnl"]
        assert cell["total_book_pnl"] == pytest.approx(indiv_sum, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────
# Bucket 3 — Boundary & edge cases (4 cases)
# ─────────────────────────────────────────────────────────────────────


def test_empty_positions_array_returns_zero_grid_safely() -> None:
    """Empty book ⇒ all P&L cells = 0, no warnings, no crash."""
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix([], current_spot=100.0)
    assert out["n_legs"] == 0
    assert out["base_book_value"] == pytest.approx(0.0, abs=1e-9)
    for cell in out["pnl_matrix"]:
        assert cell["total_book_pnl"] == pytest.approx(0.0, abs=1e-9)


def test_extreme_spot_multipliers_handled_safely() -> None:
    """spot_mult=0.0 (underlyer vanishes) and 10.0 (10× pump) yield
    finite values; the impl must not produce NaN/inf at boundaries."""
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix(
        CANONICAL_POSITIONS, current_spot=100.0,
        spot_multipliers=(0.0, 1.0, 10.0),
    )
    for cell in out["pnl_matrix"]:
        assert math.isfinite(cell["total_book_pnl"])


def test_zero_iv_multiplier_avoids_zero_division() -> None:
    """iv_mult=0.0 path must use intrinsic fallback instead of dividing by σ."""
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix(
        CANONICAL_POSITIONS, current_spot=100.0,
        iv_multipliers=(0.0, 1.0, 2.0),
    )
    for cell in out["pnl_matrix"]:
        assert math.isfinite(cell["total_book_pnl"])


def test_expired_leg_at_baseline_produces_zero_pnl() -> None:
    """A leg with T<=0 at baseline contributes 0 to every grid cell."""
    from services.stress_test import compute_stress_test_matrix

    positions = [{
        "K": 100.0, "T": 0.0, "iv": 0.50, "quantity": 1,
        "kind": "call", "side": "buy",
    }]
    out = compute_stress_test_matrix(positions, current_spot=105.0)
    # n_legs may be 0 (filtered out) or 1 (counted but contributes zero);
    # either way the matrix must be all zeros.
    for cell in out["pnl_matrix"]:
        assert cell["total_book_pnl"] == pytest.approx(0.0, abs=1e-9)


# ─────────────────────────────────────────────────────────────────────
# Bucket 4 — Schema contract & defensive degradation (4 cases)
# ─────────────────────────────────────────────────────────────────────


def test_malformed_position_skipped_with_warning() -> None:
    """Positions missing required keys (e.g. 'side', 'iv') are skipped +
    a warning string is appended. The valid sibling legs still process."""
    from services.stress_test import compute_stress_test_matrix

    positions = [
        {"K": 100.0, "T": 30 / 365.0, "iv": 0.20, "quantity": 1,
         "kind": "call", "side": "buy"},  # valid
        {"K": 100.0, "T": 30 / 365.0, "iv": 0.20, "quantity": 1,
         "kind": "call"},                  # missing 'side'
        {"K": 100.0, "T": 30 / 365.0, "quantity": 1,
         "kind": "call", "side": "buy"},   # missing 'iv'
    ]
    out = compute_stress_test_matrix(positions, current_spot=100.0)
    assert out["n_legs"] == 1
    assert len(out["warnings"]) >= 1
    assert all(isinstance(w, str) for w in out["warnings"])


def test_negative_quantity_handled_gracefully() -> None:
    """A negative quantity (mathematically equivalent to a flip in side)
    is either absorbed as a sign flip or surfaced as a warning. Either
    contract is acceptable; the impl must NOT crash."""
    from services.stress_test import compute_stress_test_matrix

    positions = [
        {"K": 100.0, "T": 30 / 365.0, "iv": 0.20, "quantity": -1,
         "kind": "call", "side": "buy"},
        {"K": 100.0, "T": 30 / 365.0, "iv": 0.20, "quantity": 1,
         "kind": "call", "side": "buy"},
    ]
    out = compute_stress_test_matrix(positions, current_spot=100.0)
    cancel_or_warn = (
        all(c["total_book_pnl"] == pytest.approx(0.0, abs=1e-9)
            for c in out["pnl_matrix"])
        or any("negative" in w.lower() or "qty" in w.lower() or "quantity" in w.lower()
               for w in out["warnings"])
    )
    assert cancel_or_warn


def test_all_documented_keys_present_in_output() -> None:
    """Frozen-set equality: the output MUST contain exactly the documented
    keys, no missing, no extras — pins the schema contract for downstream
    Skylit surface consumers."""
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix(
        CANONICAL_POSITIONS, current_spot=100.0,
    )
    assert set(out.keys()) == EXPECTED_SCHEMA_KEYS


def test_non_numeric_inputs_in_shock_axes_warn_or_cast() -> None:
    """Integer shock axes (1 instead of 1.0) must coerce cleanly; no crash."""
    from services.stress_test import compute_stress_test_matrix

    out = compute_stress_test_matrix(
        CANONICAL_POSITIONS, current_spot=100.0,
        spot_multipliers=(1, 1),       # ints instead of floats
    )
    assert isinstance(out["pnl_matrix"], list)
    assert all(math.isfinite(c["total_book_pnl"]) for c in out["pnl_matrix"])
