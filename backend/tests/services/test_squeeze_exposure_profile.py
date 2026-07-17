"""
backend/tests/services/test_squeeze_exposure_profile.py

SqueezeMetrics Spot-Shifted Exposure Profile -- TDD suite (steal-list #6)
=========================================================================

Mirrors the canonical pattern of ``tests/services/test_consensus_pricing.py``
(16 cases) AND ``tests/services/test_insider_scraper.py`` (16 cases):
the DuckDB sidecar uses the same ``DummyEngine``/execute_write-call-args
pattern (defined inline so this test file is self-contained), and the
17 cases pin the full output contract + every defensive-guard path.

       1. test_empty_chain_returns_empty_with_warning
       2. test_invalid_inputs_returns_empty_with_warning
       3. test_three_strike_sym_chain_yields_5pt_profile
       4. test_zero_oi_contracts_filtered_silently
       5. test_low_iv_produces_larger_gamma_then_dollar_gex
       6. test_high_iv_produces_smaller_gamma_then_dollar_gex
       7. test_shifts_pct_sorted_ascending_in_output
       8. test_current_total_invariant_equals_shift_zero_net_gex
       9. test_dominant_sign_positive_when_call_gex_dominates
      10. test_dominant_sign_negative_when_put_side_dominates
      11. test_n_profile_rows_matches_input_shift_count
      12. test_documented_output_keys_contract
      13. test_profile_rows_have_meaningful_variance_across_shifts
      14. test_profile_has_at_least_one_nonzero_row
      15. test_low_iv_call_gex_dwarfs_high_iv_call_gex_at_shift_zero
      16. test_shifted_chain_constructed_with_numeric_T_not_string_expiry
      17. test_persistence_init_creates_table_and_persist_upserts
"""

from __future__ import annotations

from datetime import date
from typing import Any

import math
import pytest

from services.squeeze_exposure_profile import (
    compute_spot_shifted_exposure_profile,
    init_exposure_profile_table,
    persist_daily,
)


# ─────────────────────────────────────────────────────────────────────
# DuckDB sidecar stub -- same pattern as test_insider_scraper.py
# ─────────────────────────────────────────────────────────────────────


class DummyEngine:
    """Stand-in for ``DuckDBEngine`` that records writes + returns
    canned query results. The bare minimum surface the service touches."""

    def __init__(self) -> None:
        self.sqls: list[str] = []
        self.params_seq: list[tuple] = []

    def execute_write(self, sql: str, params_seq=None) -> None:
        self.sqls.append(sql)
        if params_seq:
            for p in params_seq:
                self.params_seq.append(p)


# ─────────────────────────────────────────────────────────────────────
# Reference fixture: SPY-like BS-repriced chain via bs_greeks.
# ─────────────────────────────────────────────────────────────────────


def make_synth_chain(
    spot: float = 100.0,
    strikes: tuple[float, ...] = (90.0, 95.0, 100.0, 105.0, 110.0),
    oi: float = 100.0,
    iv: float = 0.20,
    kind: str = "call",
) -> list[dict]:
    """Build a clean synthetic chain using bs_greeks to back the mid
    prices, so the test's IV-inversion path actually computes."""
    from bs_greeks import bs_call_price, bs_put_price
    chain: list[dict] = []
    for K in strikes:
        if kind == "call":
            mid = bs_call_price(spot, K, 30.0 / 365.0, iv, r=0.045)
        else:
            mid = bs_put_price(spot, K, 30.0 / 365.0, iv, r=0.045)
        chain.append({
            "strike": float(K),
            "oi": oi,
            "type": kind,
            "bid": float(mid),
            "ask": float(mid),
            "lastPrice": float(mid),
            "impliedVolatility": iv,
            "expiry": "30DTE",
        })
    return chain


# ─────────────────────────────────────────────────────────────────────
# 1. Empty + invalid-input guards
# ─────────────────────────────────────────────────────────────────────


def test_empty_chain_returns_empty_with_warning():
    out = compute_spot_shifted_exposure_profile([], 100.0, 30.0 / 365.0)
    assert out["profile"] == []
    assert out["current_total_exposure"] == 0.0
    assert any("empty" in w or "non-positive" in w for w in out["warnings"])


def test_invalid_inputs_returns_empty_with_warning():
    """Spot=0 OR T=0 must produce the well-formed empty dict (no crash)."""
    out_a = compute_spot_shifted_exposure_profile([{"strike": 100}], 0.0, 0.1)
    out_b = compute_spot_shifted_exposure_profile([{"strike": 100}], 100.0, 0.0)
    for out in (out_a, out_b):
        assert out["profile"] == []
        assert out["current_total_exposure"] == 0.0
        assert isinstance(out["warnings"], list) and len(out["warnings"]) >= 1


# ─────────────────────────────────────────────────────────────────────
# 2. Happy-path shape
# ─────────────────────────────────────────────────────────────────────


def test_three_strike_sym_chain_yields_5pt_profile():
    """A 5-strike synthetic call chain should produce the default
    5-point profile (shifts_pct = (-5, -2, 0, 2, 5))."""
    chain = make_synth_chain(strikes=(90.0, 95.0, 100.0, 105.0, 110.0), kind="call")
    out = compute_spot_shifted_exposure_profile(chain, 100.0, 30.0 / 365.0)
    assert len(out["profile"]) == 5
    assert out["shifts_pct"] == [-5.0, -2.0, 0.0, 2.0, 5.0]
    assert out["method"] == "bs_reprice_then_dollar_gex"


def test_zero_oi_contracts_filtered_silently():
    """Contracts with OI=0 must be dropped with a warning (not a crash).
    The remaining valid contracts produce the expected 5-point profile."""
    bad_chain = make_synth_chain(strikes=(90.0, 95.0, 100.0)) + [
        {"strike": 105.0, "oi": 0.0, "type": "call", "bid": 1.0, "ask": 1.1, "impliedVolatility": 0.20},
        {"strike": 110.0, "oi": 0.0, "type": "call", "bid": 0.5, "ask": 0.6, "impliedVolatility": 0.20},
    ]
    out = compute_spot_shifted_exposure_profile(bad_chain, 100.0, 30.0 / 365.0)
    assert len(out["profile"]) == 5
    assert any("OI" in w or "oi" in w or "zero" in w for w in out["warnings"])


# ─────────────────────────────────────────────────────────────────────
# 3. IV-driven width check
# ─────────────────────────────────────────────────────────────────────


def test_low_iv_produces_larger_gamma_then_dollar_gex():
    """Mathematical note: Black-Scholes ATM gamma is inversely proportional
    to σ (Γ_ATM = N'(d1) / (S·σ·√T)). For a synthetic chain tightly clustered
    around ATM (K=90..110), low IV produces a SHARP concentrated peak at
    K=100 while high IV spreads the wings outward at lower magnitude — so
    the LOW-IV call chain should produce the LARGER total dollar-GEX at
    the shift=0 row. Positive-control check on the math against the
    documented upper bound of ~16× between σ=0.05 and σ=0.80."""
    chain_low = make_synth_chain(iv=0.05, kind="call")
    chain_high = make_synth_chain(iv=0.80, kind="call")
    out_low = compute_spot_shifted_exposure_profile(
        chain_low, 100.0, 30.0 / 365.0)
    out_high = compute_spot_shifted_exposure_profile(
        chain_high, 100.0, 30.0 / 365.0)
    # The shift=0 row is index 2 (sorted asc: [-5, -2, 0, +2, +5]).
    call_low = out_low["profile"][2]["call_gex_dollars"]
    call_high = out_high["profile"][2]["call_gex_dollars"]
    assert call_low > call_high, (
        f"low-IV call chain should produce larger ATM-concentrated "
        f"call_gex_dollars than high-IV chain (low={call_low}, high={call_high})"
    )


def test_high_iv_produces_smaller_gamma_then_dollar_gex():
    """Inverse check on the low-IV test: high-IV spreads the gamma wings
    outward away from ATM, lowering the ATM peak contribution at the
    tight 90..110 strike range used for the synthetic chain. This is
    the well-known 'vol flatten' effect — as IV rises, ATM gamma falls
    and OTM/ITM wings absorb the difference."""
    chain_low = make_synth_chain(iv=0.05, kind="call")
    chain_high = make_synth_chain(iv=0.50, kind="call")
    out_low = compute_spot_shifted_exposure_profile(
        chain_low, 100.0, 30.0 / 365.0)
    out_high = compute_spot_shifted_exposure_profile(
        chain_high, 100.0, 30.0 / 365.0)
    call_low = out_low["profile"][2]["call_gex_dollars"]
    call_high = out_high["profile"][2]["call_gex_dollars"]
    assert call_high < call_low, (
        f"high-IV call chain should produce smaller call_gex_dollars "
        f"than low-IV chain at ATM (high={call_high}, low={call_low})"
    )


# ─────────────────────────────────────────────────────────────────────
# 4. Shift-array contract
# ─────────────────────────────────────────────────────────────────────


def test_shifts_pct_sorted_ascending_in_output():
    """The output ``shifts_pct`` array MUST be in ascending order,
    regardless of how the caller passed it (sanity for downstream
    chart-rendering)."""
    chain = make_synth_chain(kind="call")
    out = compute_spot_shifted_exposure_profile(
        chain, 100.0, 30.0 / 365.0,
        shifts_pct=(5.0, 0.0, -5.0, 2.0, -2.0),
    )
    assert out["shifts_pct"] == [-5.0, -2.0, 0.0, 2.0, 5.0]
    assert len(out["profile"]) == 5


def test_n_profile_rows_matches_input_shift_count():
    """A custom shifts_pct of length N must produce exactly N profile
    rows -- the schema contract is 1:1 with the input."""
    chain = make_synth_chain(kind="call")
    out = compute_spot_shifted_exposure_profile(
        chain, 100.0, 30.0 / 365.0,
        shifts_pct=(-3.0, 1.0, 7.0),
    )
    assert len(out["profile"]) == 3


# ─────────────────────────────────────────────────────────────────────
# 5. shift=0 invariant + dominant_sign
# ─────────────────────────────────────────────────────────────────────


def test_current_total_invariant_equals_shift_zero_net_gex():
    """``current_total_exposure`` MUST equal the net_gex_dollars of the
    shift=0 row (the row's "as-if spot moved 0%" reading)."""
    chain = make_synth_chain(kind="call")
    out = compute_spot_shifted_exposure_profile(chain, 100.0, 30.0 / 365.0)
    shift_zero_row = next(r for r in out["profile"] if r["shift_pct"] == 0.0)
    assert out["current_total_exposure"] == shift_zero_row["net_gex_dollars"]


def test_dominant_sign_positive_when_call_gex_dominates():
    """A heavy-call chain should produce a positive-dominant net_gex
    at the shift=0 row (positive dealers dampen moves)."""
    chain = make_synth_chain(oi=1000.0, kind="call")
    out = compute_spot_shifted_exposure_profile(chain, 100.0, 30.0 / 365.0)
    shift_zero = next(r for r in out["profile"] if r["shift_pct"] == 0.0)
    assert shift_zero["dominant_sign"] in ("positive", "neutral")
    assert shift_zero["net_gex_dollars"] >= 0.0


def test_dominant_sign_negative_when_put_side_dominates():
    """A heavy-put chain should produce a negative-dominant net_gex
    at the shift=0 row (negative dealers amplify moves)."""
    chain = make_synth_chain(oi=1000.0, kind="put")
    out = compute_spot_shifted_exposure_profile(chain, 100.0, 30.0 / 365.0)
    shift_zero = next(r for r in out["profile"] if r["shift_pct"] == 0.0)
    assert shift_zero["dominant_sign"] in ("negative", "neutral")
    assert shift_zero["net_gex_dollars"] <= 0.0


# ─────────────────────────────────────────────────────────────────────
# 6. Documented output keys contract
# ─────────────────────────────────────────────────────────────────────


def test_documented_output_keys_contract():
    """The output dict + per-shift row MUST contain the keys documented
    at the top of services/squeeze_exposure_profile.py."""
    chain = make_synth_chain(kind="call")
    out = compute_spot_shifted_exposure_profile(chain, 100.0, 30.0 / 365.0)
    expected_top = {
        "ticker", "spot", "shifts_pct", "current_total_exposure",
        "profile", "warnings", "method",
    }
    assert expected_top.issubset(set(out.keys())), (
        f"output is missing documented top-level keys; "
        f"missing={expected_top - set(out.keys())}"
    )
    assert out["profile"], "profile array must be non-empty for valid input"
    expected_row = {
        "shift_pct", "shifted_spot", "total_gex_dollars",
        "call_gex_dollars", "put_gex_dollars", "net_gex_dollars",
        "dominant_sign", "per_strike", "warnings",
    }
    row_keys = set(out["profile"][0].keys())
    assert expected_row.issubset(row_keys), (
        f"profile row missing documented keys; "
        f"missing={expected_row - row_keys}"
    )
    assert isinstance(out["profile"][0]["per_strike"], list)


# ─────────────────────────────────────────────────────────────────────
# 8. SPOT-SHIFTED MATH INVARIANTS (regression guard)
# ─────────────────────────────────────────────────────────────────────
#
# The .md spec says this service should report GEX at ±5% / ±2% shifted
# spots, NOT repeat the same `net_gex_dollars` five times. A regression
# where the aggregator crashed silently (e.g. ``float("30DTE")`` failure
# before the shifted_chain fix) would still pass the shape-only checks
# above. These tests pin the math by asserting meaningful variance across
# the 5 rows and at least one non-zero row.


def test_profile_rows_have_meaningful_variance_across_shifts():
    """The 5 shift rows MUST have at least 2 distinct ``net_gex_dollars``
    values — i.e. the spot-shifted math actually shifted. A regression
    where every row collapses to the same value (e.g. aggregator crashed
    on string-expiry coercion) would previously pass the shape tests
    silently. This pin catches that class of bug."""
    chain = make_synth_chain(iv=0.30, kind="call")
    out = compute_spot_shifted_exposure_profile(chain, 100.0, 30.0 / 365.0)
    vals = [row["net_gex_dollars"] for row in out["profile"]]
    distinct = set(round(v, 4) for v in vals)
    assert len(distinct) >= 2, (
        f"profile rows collapse to a single net_gex_dollars value: {vals} "
        f"— the spot-shifted math is broken"
    )


def test_profile_has_at_least_one_nonzero_row():
    """The shift=0 row MUST be non-zero for a valid high-IV call chain
    (anchor check: the canonical GEX math at the as-of spot must compute
    non-trivially). If this test ever fails after changes, the integrator
    is silently falling back to the defensive-degrade empty path."""
    chain = make_synth_chain(iv=0.30, kind="call")
    out = compute_spot_shifted_exposure_profile(chain, 100.0, 30.0 / 365.0)
    shift_zero = next(r for r in out["profile"] if r["shift_pct"] == 0.0)
    assert shift_zero["net_gex_dollars"] != 0.0, (
        f"shift=0 row net_gex_dollars collapsed to zero: {out['profile']}"
    )


def test_low_iv_call_gex_dwarfs_high_iv_call_gex_at_shift_zero():
    """Concrete ratio pin: for IV=0.05 vs IV=0.80 on the *same* synthetic
    call chain (5 strikes tightly clustered around ATM, equal OI per
    strike), the shift=0 ``call_gex_dollars`` should show a sizable
    low-IV > high-IV ratio because ATM gamma is inversely proportional
    to σ. The ATM-only theoretical upper bound is ~16× (Γ_ATM ∝ 1/σ);
    across the wider 90..110 strike span the ratio lands closer to
    ~5× because high-IV spreads the gamma wings outward. We pin
    ``ratio ≥ 2×`` as the *hard* floor with a generous ``rel=0.4`` tol
    so a minor numerical drift doesn't false-fail while a true
    IV→Γ→dollar-GEX sensitivity regression still gets caught."""
    chain_low = make_synth_chain(iv=0.05, kind="call")
    chain_high = make_synth_chain(iv=0.80, kind="call")
    out_low = compute_spot_shifted_exposure_profile(
        chain_low, 100.0, 30.0 / 365.0)
    out_high = compute_spot_shifted_exposure_profile(
        chain_high, 100.0, 30.0 / 365.0)
    # The shift=0 row is index 2 (sorted asc: [-5, -2, 0, +2, +5]).
    call_low = out_low["profile"][2]["call_gex_dollars"]
    call_high = out_high["profile"][2]["call_gex_dollars"]
    assert call_low > 0.0, (
        f"low-IV call_gex_dollars collapsed to non-positive: "
        f"{call_low} — IV-fallback chain may be silently dropped"
    )
    assert call_high >= 0.0, (
        f"high-IV call_gex_dollars went non-positive (suggests an "
        f"IV-solver regression on deep-ITM strikes): {call_high}"
    )
    ratio = call_low / call_high if call_high > 0.0 else float("inf")
    # pytest.approx() does NOT support LHS of ``>=`` (raises TypeError
    # ``'>= not supported between instances of 'float' and 'ApproxScalar'``
    # on the float >= approx(...) comparison). Use a plain scalar floor.
    # Hand-computed Black-Scholes math predicts ratio ≈ 3.25 across the
    # 90..110 ATM-clustered chain, so a 2× floor is a strong regression
    # guard (constant-gamma fallback would land ratio ≈ 1.0).
    assert ratio >= 2.0, (
        f"low-IV/high-IV call_gex_dollars ratio {ratio:.2f} fell below "
        f"the 2× floor (low=+{call_low:.4f}, high=+{call_high:.4f}) — "
        f"IV→Γ→dollar-GEX sensitivity likely broken"
    )


def test_shifted_chain_constructed_with_numeric_T_not_string_expiry():
    """Invariant regression guard: every row of every per-shift
    ``shifted_chain`` MUST carry the numeric evaluation expiry key
    (``T: float``) and MUST NOT carry the string label key
    (``expiry``). Any downstream consumer that walks
    ``_EXPIRY_KEYS = ("expiry", "T", ...)`` (e.g. GexAggregator.compute
    via FIRST-MATCH ``float(...)`` coercion) will silently crash on
    ``float("30DTE")`` if a future maintainer re-adds the string label,
    collapsing every shift row to zero GEX — the original silent
    regression this whole commit fixes. We monkey-patch the service
    module's standalone Stage-2 helper so the assertion targets the
    exact dict the consumer would receive, and iterate EVERY captured
    shift × EVERY contract (not just one row — sampling one row would
    let a regression land if a future refactor produces divergent
    schemas across shifts/contracts)."""
    from services import squeeze_exposure_profile as svc

    chain = make_synth_chain(iv=0.30, kind="call")

    captured: list[list[dict]] = []

    real_build = svc._build_shifted_chain_for_shift

    def spy_build(valid_contracts, shifted_spot, T, r):
        out = real_build(valid_contracts, shifted_spot, T, r)
        captured.append([dict(c) for c in out])
        return out

    svc._build_shifted_chain_for_shift = spy_build   # type: ignore[assignment]
    try:
        compute_spot_shifted_exposure_profile(
            chain, 100.0, 30.0 / 365.0)
    finally:
        svc._build_shifted_chain_for_shift = real_build   # type: ignore[assignment]

    assert captured, "_build_shifted_chain_for_shift was never invoked"
    for shift_idx, shifted in enumerate(captured):
        assert shifted, (
            f"shifted_chain[{shift_idx}] is empty — Stage-2 helper "
            f"silently dropped contracts"
        )
        for row_idx, c in enumerate(shifted):
            assert "expiry" not in c, (
                f"shifted_chain[{shift_idx}][{row_idx}] has a STRING "
                f"'expiry' key — would crash float() coercion on any "
                f"downstream consumer that walked _EXPIRY_KEYS "
                f"(regression of the original squeeze_exposure_profile "
                f"#6 bug). keys={sorted(c)}"
            )
            assert "T" in c, (
                f"shifted_chain[{shift_idx}][{row_idx}] missing numeric "
                f"'T' key. keys={sorted(c)}"
            )
            assert isinstance(c["T"], float), (
                f"shifted_chain[{shift_idx}][{row_idx}] 'T' must be "
                f"float, got {type(c['T']).__name__}"
            )
            assert "gamma" in c and isinstance(c["gamma"], (int, float)), (
                f"shifted_chain[{shift_idx}][{row_idx}] gamma missing/"
                f"non-numeric: keys={sorted(c)}"
            )


# ─────────────────────────────────────────────────────────────────────
# 7. Persistence smoke (DuckDB sidecar via DummyEngine + UPSERT)
# ─────────────────────────────────────────────────────────────────────


def test_persistence_init_creates_table_and_persist_upserts():
    """init_exposure_profile_table issues CREATE TABLE IF NOT EXISTS
    and persist_daily writes a 5-row UPSERT (one per shift) for a fresh
    ticker + snapshot_date. Mock the engine end-to-end."""
    eng = DummyEngine()
    init_exposure_profile_table(eng)
    assert len(eng.sqls) == 1
    assert "CREATE TABLE IF NOT EXISTS" in eng.sqls[0]
    assert "floww_squeeze_exposure_daily" in eng.sqls[0]

    chain = make_synth_chain(kind="call")
    profile_out = compute_spot_shifted_exposure_profile(
        chain, 100.0, 30.0 / 365.0)
    today = date(2026, 7, 16)
    n_written = persist_daily(eng, "SPY", profile_out, snapshot_date=today)
    assert n_written == 5
    # First param of the first UPSERT tuple is the snapshot_date.
    first = eng.params_seq[0]
    assert first[0] == today
    assert first[1] == "SPY"
    assert first[2] == -5.0   # shift_pct
    assert first[3] == pytest.approx(95.0, abs=1e-4)   # shifted_spot = 100 * (1 + -0.05)
