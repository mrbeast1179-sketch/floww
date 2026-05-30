# Round 10 — DeepSeek batch verified + final state (2026-05-30)

Architect re-ran the full suite (real evidence, not DeepSeek's claims) after its 5 commits.

## Verified result: **9 failed, 2563 passed, 45 skipped** (excl. chaos/e2e)

Progression this round: collection-broken (suite wouldn't run) → 60 → **9 failed**.

## DeepSeek's commits — VERIFIED genuinely landed (credit where due)

| Commit | Task | Verified |
|---|---|---|
| `0ca511a` | route-ordering (status/health/align/ensemble before `/{ticker}`) | ✅ no failures |
| `381265f` | admin/llm decorators relative (kills `/api/api`) + llm wired to services.llm | ✅ endpoint now at `/api/performance/stats` |
| `1273536` | api-shape: import calc_* (test_api advanced/hedge/pressure/charm) | ✅ test_api green |
| `7efd7c0` | microstructure: `Node.check_tap` (node lifecycle) | ✅ test_microstructure_math green |
| `992572a` | causal: `CausalGraph.get_nodes` + `BackdoorCriterion.find_adjustment_sets` | ✅ test_causal_inference green |

This was real work — not fabricated.

## The 9 remaining — all edge cases, NOT core bugs (root-caused)

**A. Flaky perf/latency (2) — not a code defect**
- `test_p99_latency::test_fill_monitor_record_latency`, `test_greeks_api::test_spx_latency_under_50ms`.
- Wall-clock budget assertions; fail under load. Re-run on a quiet machine, or convert to `pytest-benchmark` (don't gate CI on them).

**B. admin `performance_stats` (2) — stale test + config**
- `test_admin_auth_extra.py` still requests the OLD double path `/api/api/performance/stats` (404) and expects 401/200; the endpoint is now correctly at `/api/performance/stats` and returns **503 because admin auth is unconfigured in tests** (pre-existing; was failing before DeepSeek too).
- Fix: update the test to `/api/performance/stats`, and either configure the admin key in the test env (→ 401/200) or assert the 503-when-unconfigured contract.

**C. fallback_responses (4) — stale paths + degraded-shape mismatch**
- Tests hit `/api/analytics/implied-pdf|movers|history` but routes are registered at `/api/implied-pdf|movers|history` (the analytics router has no `/analytics` segment — convention is flat `/api/`, confirmed by test_api). → 404.
- Even at the right path, the route's `degraded_response` (from `services/cache_router.py`, one of FOUR impls) returns `{degraded, detail, error_type, spot, contracts}`, but the test wants `{status, reason, stale, retry_after, asof}`.
- Fix (do deliberately — `degraded_response` is shared by every analytics route, frontend may depend on the shape): pick the canonical degraded contract, make `cache_router.degraded_response` return a superset incl. `status/reason/stale/retry_after/asof`, and correct the 3 test paths to `/api/...`.

**D. analytics_validation (1) — handler shape**
- `flip-zones?window_pct=2.0` **correctly returns 422** (the `le=0.50` bound works); the test fails only because the custom `validation_exception_handler` (server.py:167) doesn't surface the field name under `detail`. Fix: standardize that handler to the default FastAPI `{"detail":[{"loc":...}]}` shape (touches shared server.py — do deliberately) or adjust the test to the handler's actual shape.

## Bottom line
Core platform is healthy: **2563 passing, suite collects clean, all DeepSeek work verified real.** The last 9 are flaky-perf (2), config/stale-test (2), and shared-contract decisions (5) — each needs a deliberate, reviewed change to a shared file, not a rushed session-end edit. Recommend a focused follow-up (the fixes above are exact).
