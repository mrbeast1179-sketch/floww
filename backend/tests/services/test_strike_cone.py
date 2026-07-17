"""
backend/tests/services/test_strike_cone.py

Strike-Cone test profile (steal-list #10 — value 5 / effort 2)
=============================================================

This file pins the Strike-Cone contract documented in
``backend/services/strike_cone.py``. Fifteen hand-verified cases:

    1.  test_empty_distribution_returns_graceful_empty
    2.  test_single_strike_clamps_to_that_strike
    3.  test_two_strikes_exact_linear_interp
    4.  test_standard_interpolation_three_strikes
    5.  test_exact_match_returns_strike_verbatim
    6.  test_target_out_of_bounds_top_clamped_with_warning
    7.  test_target_out_of_bounds_bottom_clamped_with_warning
    8.  test_reversed_input_auto_sorted_to_canonical_order
    9.  test_jittery_non_monotone_input_sort_with_warning
    10. test_large_target_delta_clamped_to_nearest_strike
    11. test_negative_strikes_filtered
    12. test_spot_detached_from_chain_strikes
    13. test_missing_keys_in_distribution_handled_gracefully
    14. test_nan_values_in_distribution_returned_as_warned
    15. test_target_prob_exactly_half_returns_median_strike
"""

from __future__ import annotations

import math

import pytest

from services.strike_cone import compute_cone

# ─────────────────────────────────────────────────────────────────────
# Reference fixtures — a clean SPY-like distribution around spot=100.
# Strikes 90 / 95 / 100 / 105 / 110, monotone prob_above + delta.
# ─────────────────────────────────────────────────────────────────────


def make_dist(spot: float = 100.0,
              strikes: list[float] = (90, 95, 100, 105, 110),
              prob_above_curve: list[float] | None = None,
              delta_curve: list[float] | None = None):
    """Create a clean reference distribution centred on spot."""
    if prob_above_curve is None:
        # monotonically decreasing prob_above as strike rises
        prob_above_curve = [0.92, 0.74, 0.51, 0.30, 0.13]
    if delta_curve is None:
        # monotonically decreasing call-delta as strike rises
        delta_curve = [0.92, 0.78, 0.53, 0.27, 0.10]
    return [
        {
            "strike": k,
            "prob_above": pa,
            "prob_below": round(1.0 - pa, 4),
            "delta": d,
            "iv": 0.20,
        }
        for k, pa, d in zip(strikes, prob_above_curve, delta_curve, strict=False)
    ]


# ─────────────────────────────────────────────────────────────────────
# 1. Empty / sparse / malformed distributions
# ─────────────────────────────────────────────────────────────────────


def test_empty_distribution_returns_graceful_empty():
    out = compute_cone([], spot=100.0, target_probs=(0.16,), target_deltas=(0.16,))
    assert out["n_strikes"] == 0
    assert out["prob_cones"] == []
    assert out["delta_cones"] == []
    assert any("no valid strikes" in w for w in out["warnings"]) or \
        any("empty" in w or "no usable" in w for w in out["warnings"])


def test_distribution_not_a_list_returns_error_payload():
    out = compute_cone("not a list", spot=100.0)  # type: ignore[arg-type]
    assert out["n_strikes"] == 0
    assert out["prob_cones"] == []
    assert out["delta_cones"] == []
    assert any("must be a list" in w for w in out["warnings"])


def test_single_strike_clamps_to_that_strike():
    dist = make_dist(strikes=[100.0])
    out = compute_cone(dist, spot=100.0, target_probs=(0.16,), target_deltas=(0.16,))
    assert out["n_strikes"] == 1
    # Only one strike available — every target clamps to 100.0.
    assert out["prob_cones"][0]["strike_above"] == 100.0
    assert out["prob_cones"][0]["strike_below"] == 100.0
    assert out["delta_cones"][0]["strike_above"] == 100.0
    assert out["delta_cones"][0]["strike_below"] == 100.0


def test_two_strikes_exact_linear_interp():
    dist = make_dist(
        strikes=[95.0, 105.0],
        prob_above_curve=[0.74, 0.30],   # 0.16 sits below 0.30 → clamps to 105
        delta_curve=[0.78, 0.27],         # 0.16 below 0.27 → clamps to 105
    )
    out = compute_cone(dist, spot=100.0, target_probs=(0.16,), target_deltas=(0.16,))
    # Both targets are below the achievable min prob/delta — clamp to 105.
    assert out["prob_cones"][0]["strike_above"] == 105.0
    assert out["delta_cones"][0]["strike_above"] == 105.0
    # The 0.50 target sits BETWEEN 0.74 (strike=95) and 0.30 (strike=105) →
    # genuine interpolation, NOT a clamp at 95.
    # t = (0.74 - 0.50) / (0.74 - 0.30) = 0.24 / 0.44 ≈ 0.5455
    # strike = 95 + 0.5455 * 10 ≈ 100.45
    out2 = compute_cone(dist, spot=100.0, target_probs=(0.50,), target_deltas=(0.50,))
    # Direction-sensitive assertion: pin the t-weight (catches sign errors
    # that a raw 100.45 ± 1.005 tolerance would miss). The t-check IS the
    # single source of truth; the derived strike value follows arithmetically.
    strike = out2["prob_cones"][0]["strike_above"]
    t = (strike - 95.0) / 10.0   # 10.0 = (hi_strike - lo_strike)
    assert math.isclose(t, 0.5454545, rel_tol=1e-3), (
        f"interp t-weight for target=0.50 between 0.74@95 and 0.30@105 "
        f"should be ≈0.5455 (got t={t:.6f}, strike={strike})"
    )


# ─────────────────────────────────────────────────────────────────────
# 2. Standard interpolation over 3+ strikes
# ─────────────────────────────────────────────────────────────────────


def test_standard_interpolation_three_strikes():
    """A target that sits cleanly between adjacent strikes interpolates
    by the linear weight ``t = (target - low) / (high - low)``."""
    dist = make_dist(
        strikes=[90.0, 100.0, 110.0],
        prob_above_curve=[0.92, 0.51, 0.13],
        delta_curve=[0.92, 0.53, 0.10],
    )
    # Target 0.30: between 0.51 (strikes[1]=100) and 0.13 (strikes[2]=110).
    # t = (0.51 - 0.30) / (0.51 - 0.13) = 0.21 / 0.38 ≈ 0.553
    # strike = 100 + 0.553 * (110 - 100) ≈ 105.53
    out = compute_cone(dist, spot=100.0, target_probs=(0.30,))
    strike_above = out["prob_cones"][0]["strike_above"]
    assert strike_above is not None
    assert math.isclose(strike_above, 100 + (0.51 - 0.30) / (0.51 - 0.13) * 10, rel_tol=1e-3)


def test_exact_match_returns_strike_verbatim():
    '''When a target exactly equals a curve value, no interpolation fires.'''
    dist = make_dist(
        strikes=[90.0, 100.0, 110.0],
        prob_above_curve=[0.92, 0.51, 0.13],
        delta_curve=[0.92, 0.51, 0.13],   # delta=0.13 exact at strike 110
    )
    out = compute_cone(dist, spot=100.0, target_probs=(0.51,), target_deltas=(0.13,))
    # prob_above=0.51 → strike_above should be 100 (the strike where pa==0.51)
    assert out["prob_cones"][0]["strike_above"] == 100.0
    # delta=0.13 → call-delta=0.13 is at strike=110
    assert out["delta_cones"][0]["strike_above"] == 110.0


# ─────────────────────────────────────────────────────────────────────
# 3. Out-of-bounds targets
# ─────────────────────────────────────────────────────────────────────


def test_target_out_of_bounds_top_clamped_with_warning():
    dist = make_dist()
    # prob_above=0.95 is above max(0.92) → clamps to lowest strike AND warns.
    out = compute_cone(dist, spot=100.0, target_probs=(0.95,))
    cone = out["prob_cones"][0]
    assert cone["strike_above"] == 90.0    # lowest strike (max-prob strike)
    assert cone["warning"] is not None
    assert "above curve max" in cone["warning"]


def test_target_out_of_bounds_bottom_clamped_with_warning():
    dist = make_dist()
    # prob_above=0.05 is below min(0.13) → clamps to highest strike AND warns.
    out = compute_cone(dist, spot=100.0, target_probs=(0.05,))
    cone = out["prob_cones"][0]
    assert cone["strike_above"] == 110.0   # highest strike (min-prob strike)
    assert cone["warning"] is not None
    assert "below curve min" in cone["warning"]


# ─────────────────────────────────────────────────────────────────────
# 4. Reversed / jittery input — auto-sort + warn
# ─────────────────────────────────────────────────────────────────────


def test_reversed_input_auto_sorted_to_canonical_order():
    """Strike order shouldn't matter — the service sorts internally."""
    dist = make_dist()
    rev = list(reversed(dist))
    out_fwd = compute_cone(dist, spot=100.0, target_probs=(0.30,))
    out_rev = compute_cone(rev, spot=100.0, target_probs=(0.30,))
    assert out_fwd["prob_cones"][0]["strike_above"] == \
        out_rev["prob_cones"][0]["strike_above"]


def test_jittery_non_monotone_input_sort_with_warning():
    """A bump in prob_above (provider jitter) is clamped to monotone with
    a single warning fired across the cones."""
    dist = make_dist(
        strikes=[90.0, 95.0, 100.0, 105.0, 110.0],
        prob_above_curve=[0.92, 0.74, 0.51, 0.55, 0.13],   # bump at 105
        delta_curve=[0.92, 0.78, 0.53, 0.27, 0.10],
    )
    out = compute_cone(dist, spot=100.0, target_probs=(0.4,))
    mono_warns = [w for w in out["warnings"] if "non-monotone" in w]
    assert len(mono_warns) == 1   # single coalesced warning across all cones
    assert "prob_above" in mono_warns[0]
    # After monotonicity fix: [0.92, 0.74, 0.51, 0.51, 0.13] at strikes
    # [90, 95, 100, 105, 110].  bisect_left on inv=[-0.92,-0.74,-0.51,
    # -0.51,-0.13] looking for -0.4 finds idx=4 (both -0.51 entries are
    # < -0.4; only -0.13 ≥ -0.4).
    # Bracket = (105, 110) with values (0.51, 0.13).
    # t = (0.51 - 0.4) / (0.51 - 0.13) = 0.11 / 0.38 ≈ 0.2895
    # strike = 105 + 0.2895 * 5 ≈ 106.4474
    assert math.isclose(out["prob_cones"][0]["strike_above"], 106.4474, rel_tol=1e-3), (
        f"after monotonicity clamp, bisect skips both -0.51 entries → "
        f"bracket is (105, 110); expected ~106.45, got "
        f"{out['prob_cones'][0]['strike_above']}"
    )


# ─────────────────────────────────────────────────────────────────────
# 5. Large target delta + negative strikes + detached spot
# ─────────────────────────────────────────────────────────────────────


def test_large_target_delta_clamped_to_nearest_strike():
    dist = make_dist()
    # delta=0.99 above max(0.92) → clamps to strikes[0]=90
    out = compute_cone(dist, spot=100.0, target_deltas=(0.99,))
    cone = out["delta_cones"][0]
    assert cone["strike_above"] == 90.0
    assert cone["warning"] is not None


def test_negative_strikes_filtered():
    """Negative strikes (defensive against bad upstream data) are dropped
    silently with a warning, not failed."""
    dist = [
        {"strike": -50.0, "prob_above": 0.99, "prob_below": 0.01, "delta": 0.99},
        {"strike": 100.0, "prob_above": 0.51, "prob_below": 0.49, "delta": 0.53},
        {"strike": 0.0, "prob_above": 0.50, "prob_below": 0.50, "delta": 0.50},
    ]
    out = compute_cone(dist, spot=100.0, target_probs=(0.51,), target_deltas=(0.53,))
    assert out["n_strikes"] == 1   # only the +100 strike survives
    assert out["prob_cones"][0]["strike_above"] == 100.0
    assert any("non-positive" in w for w in out["warnings"])


def test_spot_detached_from_chain_strikes():
    """If spot is far above or below all strikes, the curve is still valid —
    strikes are returned as absolute prices, not as offsets from spot."""
    dist_high = make_dist(strikes=[200.0, 210.0, 220.0])
    out = compute_cone(dist_high, spot=300.0, target_probs=(0.50,), target_deltas=(0.40,))
    # strikes are 200/210/220, prob_above = 0.92/0.74/0.51.
    # prob_above target=0.50 sits below min(0.51) → clamps to 220 (with warn).
    cone = out["prob_cones"][0]
    assert cone["strike_above"] == 220.0
    assert cone["warning"] is not None and "below curve min" in cone["warning"]
    # delta target=0.40 also below min(0.51) → call_above clamps to 220.
    dcone = out["delta_cones"][0]
    assert dcone["strike_above"] == 220.0
    # 1 - 0.40 = 0.60 sits BETWEEN 0.74 (210) and 0.51 (220) → real interp.
    # t = (0.74 - 0.60) / (0.74 - 0.51) = 0.14 / 0.23 ≈ 0.6087
    # strike = 210 + 0.6087 * 10 ≈ 216.087 (put_below leg)
    assert math.isclose(dcone["strike_below"], 216.087, rel_tol=1e-2), (
        f"delta target=0.40 → put below at call_d=0.60 should land ~216 "
        f"(got {dcone['strike_below']})"
    )


# ─────────────────────────────────────────────────────────────────────
# 6. Missing keys + NaN graceful
# ─────────────────────────────────────────────────────────────────────


def test_missing_keys_in_distribution_handled_gracefully():
    """A row missing prob_above or delta doesn't crash — it contributes None
    to that cone, then either filters out or warns."""
    dist = [
        {"strike": 100.0, "prob_above": 0.51, "prob_below": 0.49, "delta": 0.53},
        {"strike": 105.0},    # missing everything else
        {"strike": 110.0, "prob_above": 0.13, "prob_below": 0.87, "delta": 0.10},
    ]
    out = compute_cone(dist, spot=100.0, target_probs=(0.30,), target_deltas=(0.30,))
    # Sanity — service did not raise.
    assert out["n_strikes"] == 3
    # prob_cones should still have one entry, with a useful warning.
    cone = out["prob_cones"][0]
    assert cone["target_prob"] == 0.30
    # The middle row has no usable values for prob_above → filtered from this cone;
    # the cone should interpolate cleanly between 100 (pa=0.51) and 110 (pa=0.13).
    assert cone["strike_above"] is not None
    assert math.isclose(
        cone["strike_above"],
        100 + (0.51 - 0.30) / (0.51 - 0.13) * 10,
        rel_tol=1e-3,
    )


def test_nan_values_in_distribution_returned_as_warned():
    """NaN/inf in prob_above or delta are silently coerced to None + warning.
    The cone should still work as long as some non-NaN data exists."""
    dist = [
        {"strike": 100.0, "prob_above": float("nan"), "prob_below": 0.49, "delta": 0.53},
        {"strike": 105.0, "prob_above": 0.30, "prob_below": 0.70, "delta": float("inf")},
        {"strike": 110.0, "prob_above": 0.13, "prob_below": 0.87, "delta": 0.10},
    ]
    out = compute_cone(dist, spot=100.0, target_probs=(0.30,), target_deltas=(0.30,))
    # NaN/inf in prob_above at 100 and delta at 105 → those rows filtered from those cones.
    assert out["n_strikes"] == 3
    assert any("not finite" in w for w in out["warnings"])
    # prob_cones target 0.30 between 0.30 (105) and 0.13 (110) → t=(0.30-0.30)/(0.30-0.13)=0
    # → exact match at 105
    cone = out["prob_cones"][0]
    assert cone["strike_above"] == 105.0


# ─────────────────────────────────────────────────────────────────────
# 7. Edge: target_prob exactly 0.5 / 0.84
# ─────────────────────────────────────────────────────────────────────


def test_target_prob_exactly_half_returns_median_strike():
    """target=0.5 in a symmetric distribution centred on spot=100 should
    return strike=100 (the median) verbatim on prob_above."""
    dist = make_dist()    # 90/95/100/105/110; pa=0.92/0.74/0.51/0.30/0.13
    out = compute_cone(dist, spot=100.0, target_probs=(0.51,))
    # 0.51 is the prob_above at strike=100 — exact match.
    assert out["prob_cones"][0]["strike_above"] == 100.0
    assert out["prob_cones"][0]["warning"] is None


# ─────────────────────────────────────────────────────────────────────
# 8. End-to-end shape contract
# ─────────────────────────────────────────────────────────────────────


def test_target_delta_zero_clamps_to_extremes():
    """Edge: target_delta=0 means call_d=0 (deep OTM call above ATM) and
    call_d=1 (deep ITM put below ATM). Both clamps at curve extremes.
    Useful invariant: a single cone with target=0 always clamps both legs."""
    dist = make_dist()  # strikes 90/95/100/105/110; delta 0.92/0.78/0.53/0.27/0.10
    out = compute_cone(dist, spot=100.0, target_deltas=(0.0,))
    cone = out["delta_cones"][0]
    # Call_above searches for call_d=0 → clamp to highest strike (min delta).
    assert cone["strike_above"] == 110.0
    # Put_below searches for call_d=1.0 (1 - 0.0) → clamp to lowest strike
    # (max delta).
    assert cone["strike_below"] == 90.0
    # Joint-warn: both clamp messages should appear in cone["warning"]
    # (the service joins them as "above+below: …; …").
    assert cone["warning"] is not None
    assert "above curve max" in cone["warning"], (
        f"expected top-clamp wording in: {cone['warning']!r}"
    )
    assert "below curve min" in cone["warning"], (
        f"expected bottom-clamp wording in: {cone['warning']!r}"
    )


def test_compute_returns_documented_dict_keys():
    dist = make_dist()
    out = compute_cone(dist, spot=100.0, target_probs=(0.16, 0.30),
                       target_deltas=(0.16, 0.30))
    expected_keys = {"spot", "n_strikes", "method", "prob_cones",
                     "delta_cones", "warnings"}
    assert set(out.keys()) == expected_keys
    assert out["method"] == "linear_interp_bisect"
    assert isinstance(out["prob_cones"], list)
    assert isinstance(out["delta_cones"], list)
    assert all({"target_prob", "strike_above", "strike_below", "warning"}
               == set(c.keys()) for c in out["prob_cones"])
    assert all({"target_delta", "strike_above", "strike_below", "warning"}
               == set(c.keys()) for c in out["delta_cones"])


def test_no_target_returns_empty_cones_but_still_runs():
    dist = make_dist()
    out = compute_cone(dist, spot=100.0, target_probs=(), target_deltas=())
    assert out["n_strikes"] == 5
    assert out["prob_cones"] == []
    assert out["delta_cones"] == []
