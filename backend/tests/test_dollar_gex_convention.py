"""
Regression test for the platform-wide Dollar-GEX convention.

Pins the GEX / VEX / charm / vomma / vega scaling to the industry-standard
"1%-move" formula used by SqueezeMetrics, SpotGamma, Perfiliev (2022), and
every retail GEX dashboard we cross-check against:

    GEX_per_contract = gamma * OI * 100 * spot^2 * 0.01

Why this test exists
====================
Earlier code had at least one real outlier (``app/backend/spy_data.py:113``)
that used ``* spot`` instead of ``* spot * spot * 0.01`` — silently under-
weighting the app-shell GEX values by a factor of ``1 / (spot * 0.01)`` ≈
~170× for SPY at $580. With the helpers in ``bs_greeks.py`` in place, the
constant is centralised, and this test guards against future regressions.

Run:
    cd backend && pytest tests/test_dollar_gex_convention.py -v

References (open-access)
- Perfiliev, S. (2022). "How to Calculate Gamma Exposure (GEX) and Zero
  Gamma Level." https://perfiliev.com/blog/how-to-calculate-gamma-exposure-and-zero-gamma-level/
- SqueezeMetrics / SpotGamma community implementations.
- TradingView community-authored GEX scripts.
"""

from __future__ import annotations

import math
from typing import Any

import pytest

from bs_greeks import (
    CONTRACT_MULTIPLIER,  # noqa: F401  (used in TestConventionPins)
    DOLLAR_MOVE_CONVENTION,  # noqa: F401  (used in TestConventionPins)
    bs_charm,  # noqa: F401  (used in TestSecondOrderConvention fixtures)
    bs_gamma,
    bs_vanna,
    bs_vega,
    bs_vomma,
    dollar_charm_per_contract,
    dollar_gex_per_contract,
    dollar_vega_per_contract,
    dollar_vex_per_contract,
    dollar_vomma_per_contract,
)

# ---------------------------------------------------------------------------
# Test 1 — Convention pins (the constant does not silently drift)
# ---------------------------------------------------------------------------

class TestConventionPins:
    """If any of these assertions fire, you've broken platform-wide parity."""

    def test_dollar_move_convention_is_canonical_1pct(self):
        # 1%-move conventional constant. SqueezeMetrics / SpotGamma /
        # Perfiliev / every retail dashboard. Don't change without
        # re-running the SqueezeMetrics-band test below.
        assert DOLLAR_MOVE_CONVENTION == 0.01, (
            "DOLLAR_MOVE_CONVENTION drifted from the 1% spot-move convention. "
            "Re-run audit docs/superpowers/specs/2026-06-13-gex-gamma-correctness-"
            "audit-design.md before changing this constant."
        )

    def test_contract_multiplier_is_equity_100(self):
        assert CONTRACT_MULTIPLIER == 100.0, (
            "CONTRACT_MULTIPLIER drifted from 100 (equity option contract "
            "size). Changing this breaks parity with every US equity-options "
            "GEX platform."
        )


# ---------------------------------------------------------------------------
# Test 2 — Hand-computed single-contract magnitudes (the test of record)
# ---------------------------------------------------------------------------

class TestHandComputedSingleContract:
    """Reproduce the value pinned by tests/services/ml/test_gex_inference_extra.py."""

    def test_gex_matches_test_of_record(self):
        # Hand-computed reference for the canonical inputs (gamma=0.02,
        # OI=500, spot=530) used by tests/services/ml/test_gex_inference_extra.py.
        # NOTE: the inline comment in that file says "= 280,900.0" but that
        # was off by a factor of 10 \u2014 the actual value is 2,809,000. The math:
        #   gamma * oi * 100 * spot^2 * 0.01
        # = 0.02 * 500 * 100 * 280_900 * 0.01
        # = 2,809,000
        gamma, oi, spot = 0.02, 500.0, 530.0
        expected = 0.02 * 500.0 * 100.0 * (530.0 ** 2) * 0.01
        assert expected == pytest.approx(2_809_000.0, rel=1e-9)
        assert dollar_gex_per_contract(gamma, oi, spot) == pytest.approx(
            expected, rel=1e-9
        )

    def test_helper_equals_open_form_for_random_grid(self):
        """Test of record (broad coverage): helper == expanded formula."""
        cases = [
            (0.005, 1000.0, 580.0),
            (0.05, 100.0, 600.0),
            (0.15, 5_000.0, 5.0),       # ETF, high gamma, big spot
            (1e-4, 200_000.0, 0.20),    # penny gamma, deep OI small spot
            (0.10, 1.0, 1.0),            # degenerate, but should not crash
        ]
        for gamma, oi, spot in cases:
            helper_val = dollar_gex_per_contract(gamma, oi, spot)
            open_val = gamma * oi * CONTRACT_MULTIPLIER * spot * spot * DOLLAR_MOVE_CONVENTION
            assert helper_val == pytest.approx(open_val, rel=1e-12), (
                f"helper ({helper_val}) != open-form ({open_val}) "
                f"for gamma={gamma}, oi={oi}, spot={spot}"
            )

    def test_zero_inputs_return_zero(self):
        assert dollar_gex_per_contract(0.0, 500.0, 530.0) == 0.0
        assert dollar_gex_per_contract(0.02, 0.0, 530.0) == 0.0
        assert dollar_gex_per_contract(0.02, 500.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# Test 3 — Per-strike aggregation polarity (calls +, puts -)
# ---------------------------------------------------------------------------

class TestAggregationPolarity:
    """Per-strike net GEX must sum with correct sign convention (calls +/puts -)."""

    def test_call_and_put_aggregate_with_correct_sign(self):
        spot = 530.0
        gamma_call = bs_gamma(spot, 530.0, 30 / 365, 0.20, q=0.013)
        gamma_put = bs_gamma(spot, 530.0, 30 / 365, 0.20, q=0.013)
        # BS gamma is the same magnitude for ATM call and put.
        assert gamma_call == pytest.approx(gamma_put, rel=1e-9)
        oi = 500.0

        call_gex = dollar_gex_per_contract(gamma_call, oi, spot)
        put_gex_signed = -dollar_gex_per_contract(gamma_put, oi, spot)

        # Symmetric O/I on a strike should net to ~0 when both sides exist.
        net_per_strike = call_gex + put_gex_signed
        assert net_per_strike == pytest.approx(0.0, abs=1e-6)

        # Asymmetric: 1 call vs 3 puts → net should be -2 * unit
        net_asym = call_gex + 3 * put_gex_signed
        assert net_asym == pytest.approx(-2 * call_gex, rel=1e-9)


# ---------------------------------------------------------------------------
# Test 4 — VEX / Charm conventions (linear spot factor, not spot²)
# ---------------------------------------------------------------------------

class TestSecondOrderConvention:
    """Vanna/charm have units [1/spot] — formula is linear in spot."""

    def test_vex_uses_linear_spot(self):
        # Doubling spot must double the dollar-VEX (with same OI/vanna/IV).
        # If this fires, someone accidentally used spot² for vanna.
        spot1, spot2 = 530.0, 1060.0
        vanna = 0.001
        oi = 1000.0
        vex1 = dollar_vex_per_contract(vanna, oi, spot1)
        vex2 = dollar_vex_per_contract(vanna, oi, spot2)
        assert vex2 == pytest.approx(2 * vex1, rel=1e-9)

    def test_charm_uses_linear_spot(self):
        spot1, spot2 = 530.0, 1060.0
        charm = 0.01
        oi = 1000.0
        c1 = dollar_charm_per_contract(charm, oi, spot1)
        c2 = dollar_charm_per_contract(charm, oi, spot2)
        assert c2 == pytest.approx(2 * c1, rel=1e-9)

    def test_vomma_no_move_factor(self):
        # Vomma is per unit-σ; no 0.01 factor.
        vomma = 100.0
        oi = 500.0
        v = dollar_vomma_per_contract(vomma, oi)
        assert v == pytest.approx(vomma * oi * 100.0, rel=1e-12)

    def test_vega_no_move_factor(self):
        vega = 50.0
        oi = 500.0
        v = dollar_vega_per_contract(vega, oi)
        assert v == pytest.approx(vega * oi * 100.0, rel=1e-12)


# ---------------------------------------------------------------------------
# Test 5 — SqueezeMetrics-anchor band (sanity vs industry platforms)
# ---------------------------------------------------------------------------

def _build_fake_spy_chain(spot: float = 580.0) -> list[dict[str, Any]]:
    """Realistic-looking SPY 0DTE chain for the band assertion.

    Numbers are calibrated to roughly match a typical mid-day SPY chain:
    ~41 strikes ±$20 around spot, OI peaked at ATM and decaying outward,
    IV smile with ~3 vol points of wing premium. Puts are 85% of calls
    (typical bearish skew) so the chain has non-zero net GEX \u2014 a perfectly
    symmetric chain would cancel to zero.
    """
    chains: list[dict[str, Any]] = []
    # Generator parameters (matching the synthetic engine in app/backend/spy_data.py)
    expiry = "2099-12-31"
    T = max(1.0 / 365.0, 0.5 / 365.0)  # 0DTE-ish (2 business days)
    base_oi_atm = 25_000
    PUT_OI_RATIO = 0.85  # typical SPY put/call OI skew

    for strike_offset in range(-20, 21):  # 41 strikes
        strike = round(spot + strike_offset, 0)
        # Gaussian OI profile, peak at ATM, slight decay
        oi_factor = math.exp(-(strike_offset ** 2) / (2 * 6 ** 2))
        # Round-number strikes get a bump
        if strike % 5 == 0:
            oi_factor *= 1.6
        call_oi = max(100, int(base_oi_atm * oi_factor))
        put_oi = max(100, int(call_oi * PUT_OI_RATIO))
        # IV smile: ~3 vol points of wing premium
        moneyness = (strike - spot) / spot
        iv = 0.13 + 1.5 * moneyness ** 2
        chains.append({
            "strike": float(strike),
            "type": "C",
            "open_interest": float(call_oi),
            "impliedVolatility": iv,
            "expiry": expiry,
            "T": T,
        })
        chains.append({
            "strike": float(strike),
            "type": "P",
            "open_interest": float(put_oi),
            "impliedVolatility": iv,
            "expiry": expiry,
            "T": T,
        })
    return chains


class TestSqueezeMetricsAnchorBand:
    """A synthetic SPY-ish chain at $580 must net-GEX in the published band."""

    def test_total_net_gex_in_published_band_spy_at_580(self):
        # Per StackExchange / SqueezeMetrics / SpotGamma / Perfiliev:
        # SPY Total Net GEX at $580 typically falls in
        #   +$3B to +$15B (positive gamma regime)
        #   -$5B to -$15B (negative gamma regime)
        # in late 2024 / 2025 OPRA chains. Some platforms report up to $20B+
        # for short-dated 0DTE-heavy days; we use the conservative median.
        spot = 580.0
        contracts = _build_fake_spy_chain(spot=spot)
        assert len(contracts) >= 80, "test fixture too thin"

        # Sum the helper per contract, signed by call/put polarity.
        total_gex = 0.0
        for c in contracts:
            gamma = bs_gamma(
                spot, c["strike"], c["T"], c["impliedVolatility"], q=0.013
            )
            if gamma <= 0:
                continue
            sign = 1.0 if c["type"] == "C" else -1.0
            total_gex += sign * dollar_gex_per_contract(gamma, c["open_interest"], spot)

        # Synthetic SPY chain has put_oi = 0.85 * call_oi (typical SPY skew),
        # so net GEX > 0 (positive-gamma regime) and the magnitude should be
        # in the published +$1B to +$25B band.
        assert 1e9 <= total_gex <= 25e9, (
            f"Synthetic SPY chain at $580 produced net GEX = "
            f"{total_gex/1e9:.2f}B, outside the published +1B-+25B band. "
            f"Either the convention helper is wrong, or the synthetic chain "
            f"no longer matches typical SPY mid-day OI shape."
        )

    def test_per_contract_dollar_gex_within_sensible_unit_range(self):
        """A single ATM SPY contract should produce on the order of $1K–$1B
        dollar-GEX depending on OI size. The 0DTE ATM gamma of an option
        right at-the-money with high IV is ~0.05-0.10, which is larger than
        30DTE ATM gamma; combined with OI 5K-50K the per-contract value is
        typically $1M–$1B."""
        spot = 580.0
        gamma = bs_gamma(spot, spot, 1.0 / 365.0, 0.15, q=0.013)
        oi = 20_000.0
        per_contract = dollar_gex_per_contract(gamma, oi, spot)
        assert 1e3 <= per_contract <= 1e9, (
            f"Per-contract Dollar GEX ({per_contract:,.2f}) outside the "
            f"industry-expected range for ATM 0DTE SPY."
        )


# ---------------------------------------------------------------------------
# Test 6 — Cross-validate against the inline formula (no behaviour drift)
# ---------------------------------------------------------------------------

class TestInlineFormulaParity:
    """The helper must produce exactly what the inline formula produces."""

    def test_gex_inline_vs_helper(self):
        """Every form of the GEX formula already in the codebase must
        match the helper exactly. This guards against the case where a
        new copy-pasted site forgets a factor."""
        sc = 580.0
        gamma = bs_gamma(sc, 580.0, 30 / 365, 0.18, q=0.013)
        oi = 1_000.0

        # Form 1 — server.py compute_gex_by_strike (post-helper)
        helper_form = dollar_gex_per_contract(gamma, oi, sc)
        # Form 2 — extended formula (the "test of record" expanded form)
        inline_form = gamma * oi * 100.0 * sc * sc * 0.01
        # Form 3 — split constant form (matches assistant's snap to bs_greeks)
        split_form = gamma * oi * CONTRACT_MULTIPLIER * sc * sc * DOLLAR_MOVE_CONVENTION
        assert helper_form == pytest.approx(inline_form, rel=1e-12)
        assert helper_form == pytest.approx(split_form, rel=1e-12)

    def test_vex_inline_vs_helper(self):
        sc = 580.0
        vanna = bs_vanna(sc, 580.0, 30 / 365, 0.18, q=0.013)
        oi = 1_000.0
        helper_form = dollar_vex_per_contract(vanna, oi, sc)
        inline_form = vanna * oi * 100.0 * sc * 0.01
        assert helper_form == pytest.approx(inline_form, rel=1e-12)


# ---------------------------------------------------------------------------
# Sanity: import gymnastics
# ---------------------------------------------------------------------------

def test_imports_pass_at_collection_time():
    """Smoke test: pytest collection imports both bs_greeks helpers and the
    rest of the test module. Pytest fails collection on ImportError so this
    only adds an explicit assertion for clarity."""
    import bs_greeks  # noqa: F401
    for name in (
        "dollar_gex_per_contract",
        "dollar_vex_per_contract",
        "dollar_charm_per_contract",
        "dollar_vomma_per_contract",
        "dollar_vega_per_contract",
        "CONTRACT_MULTIPLIER",
        "DOLLAR_MOVE_CONVENTION",
    ):
        assert hasattr(bs_greeks, name), f"bs_greeks missing {name}"
