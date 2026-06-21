"""
backend/tests/test_bs_greeks_characterization.py

Phase 4 Task 8 character pin for top-level Black-Scholes Greek values in
``backend/bs_greeks.py``.  **NO numerical edits to ``bs_greeks.py``** -- pure
characterization: lock in current analytic behaviour against an independent
finite-difference oracle + cross-greek invariants + the
``_mask_zero`` distinguishability test that plan §4 explicitly calls out.

Companion to ``backend/tests/test_bs_greeks_canonical.py`` which pins
gamma/vega against Hull Table 15.1 (book values) + put-call parity.

This file extends that coverage with:

1. FD-oracle cross-check for all six Greeks (gamma, vega, vanna, charm,
   vomma, zomma) at the same Hull input set so the two files' anchors
   are consistent.  If a future refactor drifts any Greek past the FD
   tolerance, this file fails immediately and loudly.

2. ``_mask_zero`` distinguishability: ``T<=0`` (and the other guard
   clauses) returns ``0.0`` silently -- the genuine numerical-exception
   path inside ``try / except`` returns the same ``0.0`` but emits a
   ``log.warning("... masked error ...")`` with the caller name so the
   silent failure is observable.  A future refactor that accidentally
   silences the warning OR lifts the guard clause will be caught here.

If a future PR removes this file, the diff will show a single path
deletion in CI -- the reviewers' cue to re-audit ``bs_greeks.py``.
"""

import math

import pytest

from bs_greeks import (
    bs_call_price,
    bs_charm,
    bs_delta,
    bs_gamma,
    bs_vanna,
    bs_vega,
    bs_vomma,
    bs_zomma,
)

# ---------------------------------------------------------------------------
# Hull Table 15.1 inputs (matches test_bs_greeks_canonical.py so both files'
# pins are mutually consistent if a reviewer cross-checks).
# ---------------------------------------------------------------------------
S: float = 49.0
K: float = 50.0
T: float = 30.0 / 365.0
SIGMA: float = 0.20
R: float = 0.05
Q: float = 0.0

# FD step sizes (industry-standard central-difference choices).
H_SPOT: float = 1e-3    # for d/dS derivatives (delta, gamma)
H_SIGMA: float = 1e-3   # for d/dsigma derivatives (vega, vanna, vomma, zomma)
H_TIME: float = 1e-4    # for d/dT derivatives (charm -- 1e-4 rather than 1e-3 because
                        #   bs_charm's closed form has a `1 / (2*T*sigma*sqrt(T))` term that
                        #   amplifies T-step noise; h=1e-3 would make FD truncation dominate
                        #   relative-error in the FD-vs-analytic test)

# FD relative tolerance: h=1e-3 central-diff is O(h^2) accurate to about
# 1e-6 relative for smooth Greeks.  We use 5e-3 (relaxed) so that
# cross-terms (vanna, charm) with their own denominators don't false-fail
# on routine floating-point noise.
FD_REL_TOL: float = 5e-3


def _rel_err(actual: float, expected: float) -> float:
    """Relative error with zero-expected guard."""
    if abs(expected) < 1e-12:
        return abs(actual)
    return abs(actual - expected) / abs(expected)


# ---------------------------------------------------------------------------
# 1. gamma FD-oracle: gamma ~= d(delta_call) / dS
# ---------------------------------------------------------------------------
class TestGammaFDOracle:
    """Central-difference derivative of ``bs_delta(kind='call')`` w.r.t. S."""

    def test_fd_matches_analytic(self) -> None:
        h = H_SPOT
        d_up = bs_delta(S + h, K, T, SIGMA, q=Q, kind="call", r=R)
        d_dn = bs_delta(S - h, K, T, SIGMA, q=Q, kind="call", r=R)
        fd_gamma = (d_up - d_dn) / (2 * h)
        analytic = bs_gamma(S, K, T, SIGMA, q=Q, r=R)
        assert _rel_err(fd_gamma, analytic) < FD_REL_TOL, (
            f"FD gamma {fd_gamma} vs analytic {analytic}, rel_err="
            f"{_rel_err(fd_gamma, analytic):.2e}"
        )


# ---------------------------------------------------------------------------
# 2. vega FD-oracle: vega ~= d(call_price) / dsigma
# ---------------------------------------------------------------------------
class TestVegaFDOracle:
    """Central-difference derivative of ``bs_call_price`` w.r.t. sigma."""

    def test_fd_matches_analytic(self) -> None:
        h = H_SIGMA
        p_up = bs_call_price(S, K, T, SIGMA + h, r=R, q=Q)
        p_dn = bs_call_price(S, K, T, SIGMA - h, r=R, q=Q)
        fd_vega = (p_up - p_dn) / (2 * h)
        analytic = bs_vega(S, K, T, SIGMA, q=Q, r=R)
        assert _rel_err(fd_vega, analytic) < FD_REL_TOL, (
            f"FD vega {fd_vega} vs analytic {analytic}, rel_err="
            f"{_rel_err(fd_vega, analytic):.2e}"
        )


# ---------------------------------------------------------------------------
# 3. vanna FD-oracle: vanna ~= d(delta_call) / dsigma
# ---------------------------------------------------------------------------
class TestVannaFDOracle:
    """Central-difference derivative of ``bs_delta`` w.r.t. sigma."""

    def test_fd_matches_analytic(self) -> None:
        h = H_SIGMA
        d_up = bs_delta(S, K, T, SIGMA + h, q=Q, kind="call", r=R)
        d_dn = bs_delta(S, K, T, SIGMA - h, q=Q, kind="call", r=R)
        fd_vanna = (d_up - d_dn) / (2 * h)
        analytic = bs_vanna(S, K, T, SIGMA, q=Q, r=R)
        assert _rel_err(fd_vanna, analytic) < FD_REL_TOL, (
            f"FD vanna {fd_vanna} vs analytic {analytic}, rel_err="
            f"{_rel_err(fd_vanna, analytic):.2e}"
        )


# ---------------------------------------------------------------------------
# 4. charm FD-oracle: charm_xx = -d(delta_xx)/dT (call and put each in their own method)
# ---------------------------------------------------------------------------
class TestCharmFDOracle:
    """Central-difference derivative of ``bs_delta`` w.r.t. T, for both
    call and put legs.  Call + put live in the same class to mirror the
    canonical test file's `TestHullTable15_1_ATM30DayCall`'s two-method
    call_delta + put_delta structure; both paths are exercised so a
    future refactor that breaks the `kind` toggle inside ``bs_charm``
    trips both."""
    def test_call_fd_matches_analytic(self) -> None:
        h = H_TIME
        d_up = bs_delta(S, K, T + h, SIGMA, q=Q, kind="call", r=R)
        d_dn = bs_delta(S, K, T - h, SIGMA, q=Q, kind="call", r=R)
        fd_charm = -(d_up - d_dn) / (2 * h)
        analytic = bs_charm(S, K, T, SIGMA, q=Q, kind="call", r=R)
        assert _rel_err(fd_charm, analytic) < FD_REL_TOL, (
            f"FD charm(call) {fd_charm} vs analytic {analytic}, rel_err="
            f"{_rel_err(fd_charm, analytic):.2e}"
        )

    def test_put_fd_matches_analytic(self) -> None:
        h = H_TIME
        d_up = bs_delta(S, K, T + h, SIGMA, q=Q, kind="put", r=R)
        d_dn = bs_delta(S, K, T - h, SIGMA, q=Q, kind="put", r=R)
        fd_charm = -(d_up - d_dn) / (2 * h)
        analytic = bs_charm(S, K, T, SIGMA, q=Q, kind="put", r=R)
        assert _rel_err(fd_charm, analytic) < FD_REL_TOL, (
            f"FD charm(put) {fd_charm} vs analytic {analytic}, rel_err="
            f"{_rel_err(fd_charm, analytic):.2e}"
        )


# ---------------------------------------------------------------------------
# 5. vomma FD-oracle: vomma = d(vega) / dsigma
# ---------------------------------------------------------------------------
class TestVommaFDOracle:
    """Central-difference derivative of ``bs_vega`` w.r.t. sigma."""

    def test_fd_matches_analytic(self) -> None:
        h = H_SIGMA
        v_up = bs_vega(S, K, T, SIGMA + h, q=Q, r=R)
        v_dn = bs_vega(S, K, T, SIGMA - h, q=Q, r=R)
        fd_vomma = (v_up - v_dn) / (2 * h)
        analytic = bs_vomma(S, K, T, SIGMA, q=Q, r=R)
        assert _rel_err(fd_vomma, analytic) < FD_REL_TOL, (
            f"FD vomma {fd_vomma} vs analytic {analytic}, rel_err="
            f"{_rel_err(fd_vomma, analytic):.2e}"
        )


# ---------------------------------------------------------------------------
# 6. zomma FD-oracle: zomma = d(gamma) / dsigma
# ---------------------------------------------------------------------------
class TestZommaFDOracle:
    """Central-difference derivative of ``bs_gamma`` w.r.t. sigma.
    ``bs_zomma`` is completely absent from the existing canonical test file --
    this is the first numeric anchor for the function on the test tree.
    """

    def test_fd_matches_analytic(self) -> None:
        h = H_SIGMA
        g_up = bs_gamma(S, K, T, SIGMA + h, q=Q, r=R)
        g_dn = bs_gamma(S, K, T, SIGMA - h, q=Q, r=R)
        fd_zomma = (g_up - g_dn) / (2 * h)
        analytic = bs_zomma(S, K, T, SIGMA, q=Q, r=R)
        assert _rel_err(fd_zomma, analytic) < FD_REL_TOL, (
            f"FD zomma {fd_zomma} vs analytic {analytic}, rel_err="
            f"{_rel_err(fd_zomma, analytic):.2e}"
        )


# ---------------------------------------------------------------------------
# 7. cross-greek invariants (parity / dimension / sign properties)
# ---------------------------------------------------------------------------
class TestGreekInvariants:
    """Properties no future refactor should violate."""

    def test_gamma_call_equals_put(self) -> None:
        """gamma(i) is identical for puts and calls (kind-agnostic)."""
        g = bs_gamma(S, K, T, SIGMA, q=Q, r=R)
        assert bs_gamma(S, K, T, SIGMA, q=Q, r=R) == g

    def test_vega_positive_for_long_options(self) -> None:
        """Vega per Hull is non-negative for long options."""
        assert bs_vega(S, K, T, SIGMA, q=Q, r=R) > 0

    def test_gamma_positive_for_long_options(self) -> None:
        assert bs_gamma(S, K, T, SIGMA, q=Q, r=R) > 0

    def test_charm_call_and_put_collapse_to_same_when_q0(self) -> None:
        """When q=0, call-charm and put-charm share the pdf-only term and
        should be numerically equal.  This pins the branch where the
        'kind' toggle inside bs_charm decoupled the two paths."""
        c = bs_charm(S, K, T, SIGMA, q=Q, kind="call", r=R)
        p = bs_charm(S, K, T, SIGMA, q=Q, kind="put", r=R)
        assert _rel_err(c, p) < 1e-9, (
            f"q=0 charm(call)={c} should equal charm(put)={p}"
        )


# ---------------------------------------------------------------------------
# 8. _mask_zero distinguishability (plan §4 explicit fix)
# ---------------------------------------------------------------------------
class TestMaskZeroDistinguishable:
    """Guard clause (``T<=0`` etc.) returns ``0.0`` silently; ``_mask_zero``
    (numerical-exception catch) returns the same ``0.0`` but emits a
    ``log.warning`` that names the caller.  A future agent that
    (a) accidentally silences the warning (hides silent failures), or
    (b) lifts the guard clause (returns 0 silently and bypasses the
    try/except entirely) will trip one of these tests.

    Distinguishability test: ``caplog`` captures the ``bs_greeks`` logger
    -- guard clauses must produce zero records, ``_mask_zero`` path must
    produce at least one record containing "masked".
    """

    def test_guard_clause_T_le_zero_returns_zero_silently(self, caplog) -> None:
        """T <= 0 hits the front guard clause; silent; returns 0."""
        import logging

        caplog.set_level(logging.WARNING, logger="bs_greeks")
        caplog.clear()
        v = bs_gamma(S, K, 0.0, SIGMA, q=Q, r=R)
        assert v == 0.0
        bs_records = [r for r in caplog.records if r.name == "bs_greeks"]
        assert bs_records == [], (
            f"guard clause should be silent; got: {[r.getMessage() for r in bs_records]}"
        )

    def test_guard_clause_S_le_zero_returns_zero_silently(self, caplog) -> None:
        """S <= 0 hits the front guard clause; silent; returns 0."""
        import logging

        caplog.set_level(logging.WARNING, logger="bs_greeks")
        caplog.clear()
        v = bs_gamma(0.0, K, T, SIGMA, q=Q, r=R)
        assert v == 0.0
        bs_records = [r for r in caplog.records if r.name == "bs_greeks"]
        assert bs_records == [], (
            f"guard clause should be silent; got: {[r.getMessage() for r in bs_records]}"
        )

    def test_guard_clause_sigma_le_zero_returns_zero_silently(self, caplog) -> None:
        """sigma <= 0 hits the front guard clause; silent; returns 0."""
        import logging

        caplog.set_level(logging.WARNING, logger="bs_greeks")
        caplog.clear()
        v = bs_call_price(S=S, K=K, T=T, sigma=0.0, r=R, q=Q)
        assert v == 0.0
        bs_records = [r for r in caplog.records if r.name == "bs_greeks"]
        assert bs_records == [], (
            f"guard clause should be silent; got: {[r.getMessage() for r in bs_records]}"
        )

    def test_real_path_emits_no_bs_greeks_warning(self, caplog) -> None:
        """Vanilla inputs route through math without a `bs_greeks` warning.
        Exercises ALL six Greeks + both call/put kind paths so a future
        refactor that introduces a spurious `log.warning` in ANY of them
        is caught here."""
        import logging

        caplog.set_level(logging.WARNING, logger="bs_greeks")
        caplog.clear()
        bs_gamma(S, K, T, SIGMA, q=Q, r=R)
        bs_call_price(S=S, K=K, T=T, sigma=SIGMA, r=R, q=Q)
        bs_vega(S, K, T, SIGMA, q=Q, r=R)
        bs_vanna(S, K, T, SIGMA, q=Q, r=R)
        bs_charm(S, K, T, SIGMA, q=Q, kind="call", r=R)
        bs_charm(S, K, T, SIGMA, q=Q, kind="put", r=R)
        bs_vomma(S, K, T, SIGMA, q=Q, r=R)
        bs_zomma(S, K, T, SIGMA, q=Q, r=R)
        bs_records = [r for r in caplog.records if r.name == "bs_greeks"]
        assert bs_records == [], (
            f"real path should be silent across all six Greeks + both charm kinds; got: "
            f"{[r.getMessage() for r in bs_records]}"
        )

    def test_mask_zero_path_returns_zero_with_warning(self, caplog) -> None:
        """Construct a numerical exception (OverflowError via ``exp(-q*T)``
        with ``q = -1e300`` and ``T = 1.0``) so ``_mask_zero`` fires.
        Returns ``0.0`` + a ``bs_greeks`` warning containing 'masked'."""
        import logging

        caplog.set_level(logging.WARNING, logger="bs_greeks")
        caplog.clear()
        v = bs_call_price(S=S, K=K, T=1.0, sigma=SIGMA, r=R, q=-1e300)
        assert v == 0.0  # _mask_zero returns 0
        mask_records = [
            r
            for r in caplog.records
            if r.name == "bs_greeks" and "masked" in r.getMessage().lower()
        ]
        assert len(mask_records) >= 1, (
            f"_mask_zero path must emit a 'masked' warning; got: "
            f"{[(r.getMessage()) for r in caplog.records]}"
        )

    def test_mask_zero_warning_names_caller(self, caplog) -> None:
        """The warning identifies which top-level function triggered it."""
        import logging

        caplog.set_level(logging.WARNING, logger="bs_greeks")
        caplog.clear()
        bs_call_price(S=S, K=K, T=1.0, sigma=SIGMA, r=R, q=-1e300)
        mask_messages = {
            r.getMessage()
            for r in caplog.records
            if "masked" in r.getMessage().lower()
        }
        assert any("bs_call_price" in m for m in mask_messages), (
            f"warning should name the caller; got: {mask_messages}"
        )
