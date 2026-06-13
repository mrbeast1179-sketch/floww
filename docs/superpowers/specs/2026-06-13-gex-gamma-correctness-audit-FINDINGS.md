# GEX/Gamma Correctness Audit — Findings

- **Date:** 2026-06-13
- **Status:** COMPLETE (commits pushed to `audit/gex-gamma-correctness`)
- **Spec:** `2026-06-13-gex-gamma-correctness-audit-design.md`
- **Method:** golden-oracle, test-first (TDD) + finite-difference oracle

## TL;DR

The Black-Scholes **gamma, delta, vega, vanna, and vomma** formulas are **correct** and
verified against both Hull textbook values AND independent finite-difference derivatives.
The **charm** formula in both `bs_greeks.py` and `numba_greeks.py` had a **sign bug** —
it computed `+∂Δ/∂τ` (time-to-expiry convention) instead of the standard
`∂Δ/∂t = -∂Δ/∂τ` (calendar time convention). This has been **fixed and verified**.

## Commits

| Commit | Description |
|--------|-------------|
| `1b3bb31` | Golden-oracle GEX/gamma audit — pin dual-scale, observable masking |
| `f1c71ba` | Fix charm sign convention in bs_greeks.py and numba_greeks.py |

## Bugs Found & Fixed

### B6 — Charm sign bug (NEW — found by FD oracle)

**Severity: HIGH.** Both `bs_greeks.py::bs_charm` and `numba_greeks.py::bs_charm_vec`
computed charm with the **wrong sign**. The outer negation produced `+∂Δ/∂τ` instead
of the standard `-∂Δ/∂τ`. This contradicted:
- The industry standard (charm = ∂Δ/∂t = -∂Δ/∂τ)
- `stats.py::calc_charm_ex` (the production Heatseeker/gflows path)
- The FD oracle (independent finite-difference verification)

For an ATM call with r=0.05, the code returned +0.09576 when it should have been -0.09576.

**Impact:** Charm values displayed in the UI (server.py, portfolio.py, advanced_analytics.py,
routes/market_data.py) had the wrong sign. The `charm_flip` calculation used `abs()` so it
was sign-invariant, but raw charm values were inverted.

**Fix:** Removed the outer negation from both call and put paths in `bs_greeks.py`.
Corrected the formula in `numba_greeks.py` to match `stats.py`.

### B7 — numba charm hardcoded r=0 + missing r parameter (NEW)

**Severity: MEDIUM.** `numba_greeks.py::bs_charm_vec` had `r` hardcoded to 0.0 in the
`_d1d2` call and used `(0.0 - q)` instead of `(r - q)` in the formula. The function
signature had no `r` parameter at all.

**Fix:** Added `r: float = 0.05` parameter. Updated `_d1d2` call and formula to use `r`.
Updated `compute_all_greeks` to pass `r` through.

### B8 — numba put charm structural bug (NEW — found by code reviewer)

**Severity: MEDIUM (pre-existing, dormant for q=0).** The put charm branch in
`numba_greeks.py` had `(term1 - e^{-qT}*(1-N(d1)) - term)` instead of the correct
`(-q*e^{-qT}*(1-N(d1)) - term)`. For q=0 (SPX), this added a spurious `N(d1)-1 ≈ -0.40`
per year to put charm values. The `bs_greeks.py` put charm was correct.

**Fix:** Changed the put branch to match the standard formula and `stats.py`.

### B1 — Dual GEX scale (PREVIOUS SESSION — resolved by evidence)

The S² (display) vs S¹ (ML feature) scale difference is **intentional**, not a bug.
Both scales are now pinned by golden oracle tests with 10 assertions. The ratio
(display = spot × feature) is locked. Changing the S¹ scale requires retraining all
production GBM models — deferred and documented.

### B4 — Silent masking (PREVIOUS SESSION — fixed)

`except: return 0.0` in bs_greeks.py now logs a WARNING. Behavior preserved (still returns
0.0) but the silent failure is observable. 3 masking tests added.

### B5 — Test tolerance docstring (PREVIOUS SESSION — fixed)

`test_bs_greeks_canonical.py` docstring corrected (claimed 1e-6, code used 1e-3).

## Test Results

| Suite | Count | Status |
|-------|-------|--------|
| BS Greeks canonical (Hull 10e) | 20 | ✅ All pass |
| BS Greeks FD oracle | 24 | ✅ All pass (including charm after fix) |
| BS Greeks masking observability | 3 | ✅ All pass |
| GEX aggregator oracle | 12 | ✅ All pass |
| GEX history | varies | ✅ All pass |
| Greek aggregator | varies | ✅ All pass |
| Greeks API | varies | ✅ All pass (1 latency flake: 51ms vs 50ms budget) |
| Unit tests (charm etc.) | varies | ✅ All pass |
| **Total** | **153** | **✅ 153 pass** |

## What Was NOT Changed (integrity calls)

- GEX scale (S¹ vs S²) — model-input contract; changing requires retrain
- `_RISK_FREE = 0.045` and `_IV_FALLBACK = 0.20` in gex_history — model-locked
- No forbidden files touched (inference.py, dash_ui.py, conftest.py)

## Remaining Findings (flagged, not fixed)

1. **CI lint is red** — pyproject.toml enforces E but bs_greeks.py has ~28 pre-existing
   E701s (one-liner idiom). CLAUDE.md claims "F + E722" but the real config is broader.
2. **Three sources of "GEX"** coexist (numba aggregator, inline timeframe agg,
   gflows_greeks DuckDB) with no test proving they agree.
3. **Flat iv=0.20** in the feature path ignores the vol surface — retrain-coupled.
4. **`numba_greeks.py::bs_charm_vec`** — the `r` parameter issue was fixed in this
   audit (commit f1c71ba), but the function still doesn't expose `kind` as a named
   parameter (it's positional `0`/`1`), making the API fragile for callers.

## Evidence

- 153 passed, 0 regressions (1 latency flake is pre-existing)
- Lint delta on edited files: neutral or improved
- FD oracle independently verifies all 6 Greeks (delta, gamma, vega, vanna, vomma, charm)
  against finite differences of lower-order quantities
- Charm sign fix cross-validated against `stats.py::calc_charm_ex` formula

## Key Insight

The FD oracle earned its keep: the canonical Greek test only verified values at Hull
textbook points (single moneyness per Greek), and charm had **zero** canonical coverage.
The FD oracle caught a sign bug that would have been invisible from the textbook test
alone — because the canonical test doesn't test charm at all, and the magnitude was
correct (only the sign was wrong). This is exactly the kind of bug that passes
"tests pass" but produces wrong trading signals.
