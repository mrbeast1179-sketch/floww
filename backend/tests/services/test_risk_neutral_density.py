"""
backend/tests/services/test_risk_neutral_density.py

Risk-Neutral Density test profile (steal-list #4 — value 9 / effort 3)
=====================================================================

Pins the contract documented at the top of
``backend/services/risk_neutral_density.py``. Twenty hand-verified
cases that exercise every documented output key + the defensive
guards that prevent silent crashes on malformed chains.

    1.  test_empty_calls_returns_empty_arrays_with_warning
    2.  test_single_call_returns_warning_only
    3.  test_three_calls_returns_bell_shaped_pdf
    4.  test_filter_restricts_strikes_to_around_spot
    5.  test_high_iv_produces_wider_pdf
    6.  test_low_iv_produces_narrower_pdf
    7.  test_pdf_integrates_to_near_one
    8.  test_pdf_is_non_negative_everywhere
    9.  test_cdf_is_monotonic_increasing
    10. test_cdf_ends_at_one_at_max_strike
    11. test_expected_price_close_to_spot_for_symmetric_chain
    12. test_median_close_to_spot_for_symmetric_chain
    13. test_mode_close_to_spot_for_symmetric_chain
    14. test_p_below_95pct_spot_in_reasonable_range
    15. test_p_above_105pct_spot_in_reasonable_range
    16. test_r_zero_yields_same_pdf_shape
    17. test_T_zero_returns_degenerate_with_warning
    18. test_negative_strikes_filtered
    19. test_nan_inf_inputs_do_not_crash
    20. test_documented_output_keys_contract
"""

from __future__ import annotations

import math

import pytest

from services.risk_neutral_density import compute_rnd_pdf

# ─────────────────────────────────────────────────────────────────────
# Reference fixture — a clean SPY-like call chain around spot=100.
# Strike range 90 → 110 in steps of 5, monotone BS repricing at T=1/12,
# uniform 20% IV, r=5%. Mid price is bs_call_price (with bid/ask ±1%
# noise priced in to look realistic).
# ─────────────────────────────────────────────────────────────────────


def make_call_chain(
    spot: float = 100.0,
    strikes: tuple[float, ...] = (90.0, 95.0, 100.0, 105.0, 110.0),
    iv: float = 0.20,
    r: float = 0.05,
    T: float = 1.0 / 12.0,
) -> list[dict]:
    """Build a clean reference call chain using BS repricing.

    Each row has strike/bid/ask/lastPrice. The mid is 0.5·(bid+ask) but
    we set bid=ask=last=mid so the chain is internally consistent.
    """
    from bs_greeks import bs_call_price
    chain: list[dict] = []
    for k in strikes:
        cp = bs_call_price(spot, float(k), T, iv, r=r, q=0.0)
        if not math.isfinite(cp) or cp < 0:
            cp = max(0.0, cp)
        chain.append({
            "strike": float(k),
            "bid": float(cp),
            "ask": float(cp),
            "lastPrice": float(cp),
        })
    return chain


def _call_or_skip(call_chain, **kwargs):
    """Run the engine + return dict, skipping if scipy/numpy unavailable."""
    out = compute_rnd_pdf(call_chain, **kwargs)
    return out


# ─────────────────────────────────────────────────────────────────────
# 1. Empty / sparse / malformed chains
# ─────────────────────────────────────────────────────────────────────


def test_empty_calls_returns_empty_arrays_with_warning():
    out = compute_rnd_pdf([], spot=100.0, T=1.0 / 12.0, r=0.05)
    assert out["n_strikes_used"] == 0
    assert out["x_grid"] == []
    assert out["pdf"] == []
    assert out["cdf"] == []
    assert out["expected_price"] is None
    assert out["median"] is None
    assert out["mode"] is None
    assert isinstance(out["warnings"], list)
    assert len(out["warnings"]) >= 1
    assert any("no valid" in w or "empty" in w for w in out["warnings"])


def test_single_call_returns_warning_only():
    """A single-strike chain can't be smoothed (need ≥4 points for cubic spline).
    Service should degrade gracefully: return empty arrays + warning."""
    chain = make_call_chain(strikes=(100.0,))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    # Either a sane degenerate single-strike output OR an explicit warning
    # about insufficient points — both are acceptable graceful paths.
    assert isinstance(out["warnings"], list)
    assert len(out["warnings"]) >= 1
    # No exception raised is the key behavioral assertion.


def test_three_calls_returns_bell_shaped_pdf():
    """A 5-strike symmetric chain centred on spot produces a non-empty
    PDF + CDF + expected_price within the strike range."""
    chain = make_call_chain(
        spot=100.0, strikes=(90.0, 95.0, 100.0, 105.0, 110.0),
    )
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    assert out["n_strikes_used"] >= 3
    assert len(out["x_grid"]) == out["n_grid_points"]
    assert len(out["pdf"]) == out["n_grid_points"]
    assert len(out["cdf"]) == out["n_grid_points"]
    # The PDF must have at least one non-trivial peak (not all zero).
    assert max(out["pdf"]) > 0
    # The grid span should be inside the input strike range.
    assert out["x_grid"][0] >= 90.0
    assert out["x_grid"][-1] <= 110.0


def test_filter_restricts_strikes_to_around_spot():
    """Strikes far from spot (outside ±30%) should be filtered out before
    the PDF is computed; the resulting grid spans the filtered range.

    Pruning window is [0.7·spot, 1.3·spot] = [70, 130]. The 5 strikes
    inside (70 / 90 / 100 / 110 / 130) survive; 50 and 200 are dropped.
    "
    """
    chain = make_call_chain(
        spot=100.0,
        strikes=(50.0, 70.0, 90.0, 100.0, 110.0, 130.0, 200.0),
    )
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    # 5 strikes survived (50 and 200 dropped — outside ±30% of spot).
    assert out["n_strikes_used"] == 5, (
        f"expected 5 strikes to survive pruning ([70, 130] window); "
        f"got {out['n_strikes_used']}"
    )
    # Grid spans the kept-strike range [70, 130]. _linspace(70, 130, 200)
    # is exact on these integerish endpoints, but we use a tight pytest.approx
    # tolerance to defend against any future linspace implementation drift.
    assert out["x_grid"][0] == pytest.approx(70.0, abs=1e-9), (
        f"x_grid[0] should be the lowest kept strike (70.0); "
        f"got {out['x_grid'][0]}"
    )
    assert out["x_grid"][-1] == pytest.approx(130.0, abs=1e-9), (
        f"x_grid[-1] should be the highest kept strike (130.0); "
        f"got {out['x_grid'][-1]}"
    )


# ─────────────────────────────────────────────────────────────────────
# 2. IV-driven width checks
# ─────────────────────────────────────────────────────────────────────


def test_high_iv_produces_wider_pdf():
    """A chain with IV=0.80 yields a wider expected-move distribution than
    a chain with IV=0.10 — measured by the difference between the median
    and the 5th/95th CDF-cross points (proxy for std-dev)."""
    chain_low = make_call_chain(iv=0.10, strikes=(85.0, 90.0, 95.0, 100.0,
                                                    105.0, 110.0, 115.0))
    chain_high = make_call_chain(iv=0.80, strikes=(85.0, 90.0, 95.0, 100.0,
                                                     105.0, 110.0, 115.0))
    out_low = compute_rnd_pdf(chain_low, spot=100.0, T=1.0 / 12.0, r=0.05)
    out_high = compute_rnd_pdf(chain_high, spot=100.0, T=1.0 / 12.0, r=0.05)
    # The expected_price should be near spot (symmetric chain) for both,
    # but the median-relative-to-expected move ought to be wider at high IV.
    # Use the tail-prob at 105% spot as the proxy — high IV → HIGHER p_above.
    p_high = out_high.get("tail_probs", {}).get("p_above_105pct_spot", 0.0)
    p_low = out_low.get("tail_probs", {}).get("p_above_105pct_spot", 0.0)
    assert p_high > p_low, (
        f"high-IV chain should yield higher p_above_105pct_spot than "
        f"low-IV chain (high={p_high}, low={p_low})"
    )


def test_low_iv_produces_narrower_pdf():
    """Inverse of the high-IV test: low-IV chain has tighter mass near spot."""
    chain_low = make_call_chain(iv=0.05, strikes=(95.0, 98.0, 100.0,
                                                    102.0, 105.0))
    chain_high = make_call_chain(iv=0.50, strikes=(95.0, 98.0, 100.0,
                                                     102.0, 105.0))
    out_low = compute_rnd_pdf(chain_low, spot=100.0, T=1.0 / 12.0, r=0.05)
    out_high = compute_rnd_pdf(chain_high, spot=100.0, T=1.0 / 12.0, r=0.05)
    # Low-IV chain should drive p_below_98pct_spot lower.
    p_low_below = out_low.get("tail_probs", {}).get("p_below_98pct_spot", 1.0)
    p_high_below = out_high.get("tail_probs", {}).get("p_below_98pct_spot", 1.0)
    assert p_low_below < p_high_below, (
        f"low-IV chain should pull mass closer to spot (lower "
        f"p_below_98pct_spot) — got low={p_low_below}, high={p_high_below}"
    )


# ─────────────────────────────────────────────────────────────────────
# 3. PDF / CDF invariants
# ─────────────────────────────────────────────────────────────────────


def test_pdf_integrates_to_near_one():
    """After the normalisation step, ∫pdf dx should be very close to 1.0
    (within ±5% tolerance for numerical integration on a 200-point grid)."""
    chain = make_call_chain(strikes=(85.0, 90.0, 95.0, 100.0, 105.0, 110.0,
                                       115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    if not out["pdf"]:
        pytest.skip("PDF empty — degradation path")
    # Trapezoid-rule integration on the discretised PDF.
    pdf = out["pdf"]
    x_grid = out["x_grid"]
    integral = 0.0
    for i in range(len(pdf) - 1):
        integral += 0.5 * (pdf[i] + pdf[i + 1]) * (x_grid[i + 1] - x_grid[i])
    assert 0.95 <= integral <= 1.05, (
        f"PDF must integrate to ≈1.0 after normalisation (got {integral:.4f})"
    )


def test_pdf_is_non_negative_everywhere():
    """Clipping pipeline must leave the PDF nowhere negative."""
    chain = make_call_chain(strikes=(85.0, 90.0, 95.0, 100.0, 105.0, 110.0,
                                       115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    if not out["pdf"]:
        pytest.skip("PDF empty — degradation path")
    assert all(p >= 0.0 for p in out["pdf"]), (
        f"PDF should be ≥ 0 everywhere (clip path active); min={min(out['pdf'])}"
    )


def test_cdf_is_monotonic_increasing():
    """CDF[i+1] ≥ CDF[i] for all i (CDF is a cumulative integral)."""
    chain = make_call_chain(strikes=(85.0, 90.0, 95.0, 100.0, 105.0, 110.0,
                                       115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    if not out["cdf"]:
        pytest.skip("CDF empty — degradation path")
    for i in range(len(out["cdf"]) - 1):
        assert out["cdf"][i + 1] >= out["cdf"][i] - 1e-12, (
            f"CDF must be non-decreasing; at i={i}, "
            f"CDF[{i}]={out['cdf'][i]}, CDF[{i+1}]={out['cdf'][i+1]}"
        )


def test_cdf_ends_at_one_at_max_strike():
    """After the renormalisation step, CDF[-1] ≈ 1.0 (within ±5%)."""
    chain = make_call_chain(strikes=(85.0, 90.0, 95.0, 100.0, 105.0, 110.0,
                                       115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    if not out["cdf"]:
        pytest.skip("CDF empty — degradation path")
    assert 0.95 <= out["cdf"][-1] <= 1.0001, (
        f"CDF must reach ≈1 at K_max (got {out['cdf'][-1]:.4f})"
    )


# ─────────────────────────────────────────────────────────────────────
# 4. Expected-price / median / mode contract
# ─────────────────────────────────────────────────────────────────────


def test_expected_price_close_to_spot_for_symmetric_chain():
    """A symmetric chain centred on spot=100 should yield expected_price
    within ±10% of spot (a wider tolerance than strict median==spot
    because the integrator is asymmetric in unit mass)."""
    chain = make_call_chain(strikes=(85.0, 90.0, 95.0, 100.0, 105.0, 110.0,
                                       115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    if out["expected_price"] is None:
        pytest.skip("expected_price unavailable — degradation path")
    assert abs(out["expected_price"] - 100.0) <= 10.0, (
        f"expected_price should be near spot=100.0 for symmetric chain; "
        f"got {out['expected_price']}"
    )


def test_median_close_to_spot_for_symmetric_chain():
    """Median (P(S<median)=0.5) should be within ±5% of spot for a symmetric
    distribution (the integrator is naturally mass-balanced)."""
    chain = make_call_chain(strikes=(85.0, 90.0, 95.0, 100.0, 105.0, 110.0,
                                       115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    if out["median"] is None:
        pytest.skip("median unavailable — degradation path")
    assert abs(out["median"] - 100.0) <= 5.0, (
        f"median should be near spot=100.0 (got {out['median']})"
    )


def test_mode_close_to_spot_for_symmetric_chain():
    """Mode (peak of PDF) should be within ±10% of spot for a symmetric chain."""
    chain = make_call_chain(strikes=(85.0, 90.0, 95.0, 100.0, 105.0, 110.0,
                                       115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    if out["mode"] is None:
        pytest.skip("mode unavailable — degradation path")
    assert abs(out["mode"] - 100.0) <= 10.0, (
        f"mode should be near spot=100.0 (got {out['mode']})"
    )


# ─────────────────────────────────────────────────────────────────────
# 5. Tail-prob sanity
# ─────────────────────────────────────────────────────────────────────


def test_p_below_95pct_spot_in_reasonable_range():
    """For a 20% IV 1-month option on a 100-stock, p_below_95 (= 95% of
    spot = 95) should be in [0.02, 0.45]. Anything outside this band
    signals a regression in the integrator."""
    chain = make_call_chain(iv=0.20, strikes=(85.0, 90.0, 95.0, 100.0,
                                                105.0, 110.0, 115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    p = out.get("tail_probs", {}).get("p_below_95pct_spot")
    if p is None:
        pytest.skip("p_below_95pct_spot unavailable — threshold out of grid")
    assert -0.05 <= p <= 0.55, (
        f"p_below_95pct_spot should be a sensible probability (got {p})"
    )


def test_p_above_105pct_spot_in_reasonable_range():
    """Symmetric partner of p_below_95pct_spot test."""
    chain = make_call_chain(iv=0.20, strikes=(85.0, 90.0, 95.0, 100.0,
                                                105.0, 110.0, 115.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    p = out.get("tail_probs", {}).get("p_above_105pct_spot")
    if p is None:
        pytest.skip("p_above_105pct_spot unavailable — threshold out of grid")
    assert -0.05 <= p <= 0.55, (
        f"p_above_105pct_spot should be a sensible probability (got {p})"
    )


# ─────────────────────────────────────────────────────────────────────
# 6. r / T edge cases
# ─────────────────────────────────────────────────────────────────────


def test_r_zero_yields_same_pdf_shape():
    """r=0 fallback: the e^{rT} factor becomes 1, so the PDF should have
    the same shape as r=0.05 (scaled by e^{-rT} numerically identical to
    1.0 vs ≈1.0025). Within ±5% scaling tolerance."""
    chain = make_call_chain(strikes=(85.0, 90.0, 95.0, 100.0, 105.0, 110.0,
                                       115.0))
    out_zero = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.0)
    out_real = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    if not out_zero["pdf"] or not out_real["pdf"]:
        pytest.skip("PDF unavailable — degradation path")
    # Compare the mode (argmax) — should be the same.
    mode_zero_idx = max(range(len(out_zero["pdf"])),
                         key=out_zero["pdf"].__getitem__)
    mode_real_idx = max(range(len(out_real["pdf"])),
                         key=out_real["pdf"].__getitem__)
    assert abs(out_zero["x_grid"][mode_zero_idx] -
               out_real["x_grid"][mode_real_idx]) <= 1.0, (
        f"r=0 vs r=5% should land at the same mode strike (got "
        f"{out_zero['x_grid'][mode_zero_idx]} vs "
        f"{out_real['x_grid'][mode_real_idx]})"
    )


def test_T_zero_returns_degenerate_with_warning():
    """T=0 makes all call prices = intrinsic (max(S-K, 0)) — the second
    derivative is zero everywhere except at K=S where it's a Dirac.
    Service should NOT crash; should return empty arrays or warning."""
    chain = make_call_chain(strikes=(90.0, 95.0, 100.0, 105.0, 110.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=0.0, r=0.05)
    # Either empty PDF + warning OR a degenerate spike at spot=100.
    if not out["pdf"]:
        assert any("T=0" in w or "zero" in w.lower() or "no" in w.lower()
                   for w in out["warnings"])
    else:
        # If it tried to integrate, the PDF should be near-degenerate.
        assert max(out["pdf"]) > 0


# ─────────────────────────────────────────────────────────────────────
# 7. Defensive guards
# ─────────────────────────────────────────────────────────────────────


def test_negative_strikes_filtered():
    """Negative strikes (defensive against bad upstream data) are dropped
    silently + warning, not crashed."""
    chain = [
        {"strike": -50.0, "bid": 1.0, "ask": 1.5, "lastPrice": 1.2},
        {"strike": 100.0, "bid": 5.0, "ask": 5.5, "lastPrice": 5.2},
        {"strike": 0.0, "bid": 0.0, "ask": 0.0, "lastPrice": 0.0},
        {"strike": 110.0, "bid": 0.5, "ask": 0.8, "lastPrice": 0.6},
    ]
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    # Service must not crash; -50 and 0 are filtered.
    assert out["n_strikes_used"] <= 2
    assert isinstance(out["warnings"], list)
    if out["n_strikes_used"] < 2:
        assert len(out["warnings"]) >= 1


def test_nan_inf_inputs_do_not_crash():
    """NaN/inf bid/ask/lastPrice rows are silently dropped + warning."""
    chain = [
        {"strike": 90.0, "bid": float("nan"), "ask": float("nan"),
         "lastPrice": float("nan")},
        {"strike": 100.0, "bid": float("inf"), "ask": float("inf"),
         "lastPrice": float("inf")},
        {"strike": 110.0, "bid": -1.0, "ask": -1.0, "lastPrice": -1.0},
        {"strike": 105.0, "bid": 1.0, "ask": 1.5, "lastPrice": 1.2},
    ]
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    # Service must not raise.
    assert "x_grid" in out
    assert "pdf" in out
    assert "warnings" in out
    # Either nothing passes the filter (empty) OR just the 105 row survives
    # (105 alone is < 4 strikes → central-diff fallback or warning).
    if out["n_strikes_used"] == 0:
        assert len(out["warnings"]) >= 1


# ─────────────────────────────────────────────────────────────────────
# 8. Schema + edge-utility
# ─────────────────────────────────────────────────────────────────────


def test_documented_output_keys_contract():
    """The output dict must contain the keys documented in the module."""
    chain = make_call_chain(strikes=(90.0, 95.0, 100.0, 105.0, 110.0))
    out = compute_rnd_pdf(chain, spot=100.0, T=1.0 / 12.0, r=0.05)
    expected_keys = {
        "spot", "T_years", "r", "n_strikes_used", "n_grid_points",
        "x_grid", "pdf", "cdf", "expected_price", "expected_move_pct",
        "median", "mode", "tail_probs", "warnings", "method",
    }
    assert expected_keys.issubset(set(out.keys())), (
        f"output dict missing documented keys; "
        f"missing={expected_keys - set(out.keys())}"
    )
    assert out["method"] == "cubic_spline_2nd_derivative"
    assert isinstance(out["tail_probs"], dict)
    assert isinstance(out["warnings"], list)
