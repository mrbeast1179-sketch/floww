"""
backend/tests/services/test_numba_greeks_delta_r.py

Defence-in-depth regression tests for the bs_delta_vec `r=0.0` hardcode in
backend/services/numba_greeks.py (P2 entry #5 in docs/superpowers/plans/
2026-06-20-freebuff-decoder-hardening-60h.md).

Pre-fix bug: bs_delta_vec's signature accepts an `r: float = 0.05` parameter,
but its body calls `_d1d2(S, K[i], T[i], sigma[i], 0.0, q)` — the `r`
parameter is silently ignored; every delta is computed with the risk-free
rate hard-pinned to 0.0.  This produces:
- Internally inconsistent delta series (delta via gamma/vega all use real `r`;
  delta is the lone hold-out using `r=0`).
- Silently wrong delta scaling — at r=0.05, BS delta(ITM-call) at K=S=100,
  T=0.25 differs from "delta(r=0)" by ~ exp(-r*T) * Phi(d1-shift) ≈ 0.6 % in
  the most-common legs.  Quantitatively small but coherent-option-pricing
  chains (delta-hedging, gamma-scalping) break down over hundreds of legs.

Pinned properties:
1. `bs_delta_vec(..., r=0.05)` MUST produce different output from
   `bs_delta_vec(..., r=0.10)` — the `r` parameter must have a visible effect.
2. `bs_delta_vec(..., r=0.05)` MUST match the closed-form Black-Scholes
   delta computed via scipy.stats.norm.cdf with the same inputs.
3. The default-parameter call (no explicit r) MUST use the signature default
   `r=0.05`, not the hardcoded `0.0`.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pytest
from scipy.stats import norm

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))


def _closed_form_delta(S: float, K: float, T: float, sigma: float, r: float, q: float = 0.0) -> float:
    """Reference Black-Scholes call-delta (independent of services.numba_greeks)."""
    d1 = (np.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * np.sqrt(T))
    return float(np.exp(-q * T) * norm.cdf(d1))


class TestBsDeltaVecHonoursRiskFreeRate:
    """Pinned regression: bs_delta_vec must read its `r` parameter."""

    def test_different_r_produces_different_delta(self):
        """Pins the BUG: before fix, all r values produced identical delta (because r hardcoded 0.0)."""
        from services.numba_greeks import bs_delta_vec

        S = 100.0
        K = np.array([90.0, 100.0, 110.0])
        T = np.array([0.25, 0.25, 0.25])
        sigma = np.array([0.2, 0.2, 0.2])

        delta_r005 = bs_delta_vec(S, K, T, sigma, q=0.0, r=0.05)
        delta_r010 = bs_delta_vec(S, K, T, sigma, q=0.0, r=0.10)

        # Different r values MUST produce different deltas (bug-fix invariance).
        diffs = np.abs(delta_r005 - delta_r010)
        assert diffs.max() > 1e-6, (
            f"bs_delta_vec ignores the `r` parameter — outputs identical for r=0.05 "
            f"and r=0.10 (max abs diff = {diffs.max():.2e}). The bug is the hardcoded "
            f"`_d1d2(S, K[i], T[i], sigma[i], 0.0, q)` at numba_greeks.py:163.  "
            f"See P2 entry #5 in docs/superpowers/plans/"
            f"2026-06-20-freebuff-decoder-hardening-60h.md."
        )

    def test_delta_r005_matches_closed_form(self):
        """bs_delta_vec(r=0.05) must match scipy.stats.norm.cdf reference within 1e-6."""
        from services.numba_greeks import bs_delta_vec

        S = 100.0
        K = np.array([85.0, 95.0, 100.0, 105.0, 115.0])
        T = np.array([0.10, 0.25, 0.50, 0.75, 1.00])
        sigma = np.array([0.20, 0.25, 0.30, 0.35, 0.40])

        out = bs_delta_vec(S, K, T, sigma, q=0.0, r=0.05)
        expected = np.array([
            _closed_form_delta(S, float(k), float(t), float(sig), r=0.05)
            for k, t, sig in zip(K, T, sigma, strict=True)
        ])
        np.testing.assert_allclose(out, expected, rtol=1e-6, atol=1e-8)

    def test_delta_r010_matches_closed_form(self):
        """Same closed-form check for r=0.10."""
        from services.numba_greeks import bs_delta_vec

        S = 100.0
        K = np.array([90.0, 100.0, 110.0])
        T = np.array([0.25, 0.25, 0.25])
        sigma = np.array([0.2, 0.2, 0.2])

        out = bs_delta_vec(S, K, T, sigma, q=0.0, r=0.10)
        expected = np.array([
            _closed_form_delta(S, float(k), float(t), float(sig), r=0.10)
            for k, t, sig in zip(K, T, sigma, strict=True)
        ])
        np.testing.assert_allclose(out, expected, rtol=1e-6, atol=1e-8)

    def test_sibling_vectors_honour_r_parameter(self):
        """Cross-vector regression net: bs_gamma_vec and bs_charm_vec must ALSO honour
        the `r` parameter (today they do, but a future contributor adding a new vector
        that hardcodes 0.0 must be caught).  Pins the symmetry-class: ALL greek vectors
        use the real `r`, none short-circuit to 0.0.  See P2 entry #5 in
        docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md."""
        from services.numba_greeks import bs_charm_vec, bs_gamma_vec

        S = 100.0
        K = np.array([90.0, 100.0, 110.0])
        T = np.array([0.25, 0.25, 0.25])
        sigma = np.array([0.2, 0.2, 0.2])

        for name, fn in (("bs_gamma_vec", bs_gamma_vec), ("bs_charm_vec", bs_charm_vec)):
            out_r005 = fn(S, K, T, sigma, q=0.0, r=0.05)
            out_r010 = fn(S, K, T, sigma, q=0.0, r=0.10)
            np.testing.assert_array_compare(
                np.not_equal, out_r005, out_r010,
                err_msg=(f"{name} ignores the `r` parameter - sibling-class regression "
                         f"of the bs_delta_vec bug (P2 entry #5)."),
            )


    def test_default_r_differs_from_explicit_r_zero(self):
        """Default `r` (signature default 0.05) MUST differ from explicit r=0.0."""
        from services.numba_greeks import bs_delta_vec

        S = 100.0
        K = np.array([100.0])
        T = np.array([0.25])
        sigma = np.array([0.2])

        delta_default = bs_delta_vec(S, K, T, sigma)
        delta_zero = bs_delta_vec(S, K, T, sigma, r=0.0)

        # If the body still hardcodes 0.0 inside _d1d2, both these calls produce
        # identical results.  This test catches the exact regression.
        np.testing.assert_array_compare(
            np.not_equal, delta_default, delta_zero,
            err_msg="default r is hardcoded to 0.0 in bs_delta_vec body (P2 entry #5)",
        )
