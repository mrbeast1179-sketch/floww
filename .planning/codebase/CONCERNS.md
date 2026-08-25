# Codebase Concerns

**Analysis Date:** 2026-08-24

## Tech Debt

**7 pre-existing CI-only test failures (env-dependent class):**
- Issue: A stable set of ~7 backend tests fail only in CI, not locally. They depend on local environment state (services, data files, network).
- Why: Tests written against the dev machine's full environment (Mongo running, seeded data, Schwab/network access).
- Impact: CI is red on unrelated changes; masks real regressions in that noise floor.
- Fix approach: Tag them `flaky_env`, stub/fixture the environment dependencies, or gate them behind an opt-in marker; do NOT skip/xfail without architect approval.

**DuckDB engine lifecycle:**
- Issue: Engine/connection lifetime was implicit for a long time; `close()` was added recently (`backend/services/duckdb_engine.py`, line ~277) plus a teardown registry (line ~94) so `tests/conftest.py` closes engines after each test — while explicitly protecting the shared app singleton from teardown (comment near line ~458).
- Impact: New code paths may leak connections if they construct engines outside the registry; tests can hit file locks.
- Fix approach: Always create DuckDB engines through the existing factory so they register for teardown; never call `.close()` on the shared app singleton.

**Memoized module-global singletons in routes (`_alert_engine` pattern):**
- Issue: Routes lazily build service singletons into module globals: `_alert_engine = None` + `get_alert_engine()` in `backend/routes/alerts.py` (lines ~28–36). Same pattern likely in sibling route modules under `backend/routes/`.
- Why: Cheap lazy init; avoids import-time side effects.
- Impact: Hidden global state — hard to reset between tests, no dependency injection, config changes after first call are ignored.
- Fix approach: Migrate to FastAPI `Depends` providers or an app-state container when touching these routes.

**`models/` directory gitignored but partially tracked:**
- Issue: Root `.gitignore` excludes model artifacts, yet many files under `backend/models/` are already git-tracked (`DIA_*.joblib`, `*_manifest.json`, scalers — dozens of binaries).
- Impact: Repo bloat; ambiguity about which artifacts are source-of-truth vs. ignored regenerables; CLAUDE.md freezes these files anyway.
- Fix approach: Decide policy with Nav — either `git rm --cached` the stale artifacts (needs architect approval; destructive ops restricted) or un-ignore intentionally and document it.

**torch in requirements but used only by tests (and niche services):**
- Issue: `backend/requirements.txt:32` pins `torch>=2.3.0`, a multi-GB dependency, while imports appear mainly in `backend/tests/services/test_anomaly_training.py`, `test_autoformer_inference.py`, `test_patchtst_inference.py` and a few service modules (`backend/services/anomaly_detector.py`, `backend/services/ml_ensemble.py`, `backend/services/memory/chart_embeddings.py`).
- Impact: Slow installs, heavy CI images, for a dependency most of the platform never loads.
- Fix approach: Split into requirements-torch.txt or optional extra; make torch-dependent modules lazily import.

## Fragile Areas

**`backend/tests/conftest.py`:**
- Why fragile: Architect-frozen (R9), R10 P0.1 waiver applies; shared fixtures (`fresh_engine`, `seeded_quality_db`, `aclient`) underpin ~4.5k tests.
- Safe modification: Only with explicit architect approval; any change must show full-suite pass evidence.

**Frozen production modules:** `backend/services/ml/inference.py`, `backend/services/dash_ui.py` — surgical fixes only, justified in commit body (canonical example: HOLD-zone fix at `888abd4`).

## Test Coverage Gaps

**Env-dependent failure class:**
- What's not tested: The 7 CI-only failures have no isolated repro harness.
- Risk: Real CI regressions hide inside the known-failure noise.
- Priority: High
- Difficulty to test: Requires replicating CI environment or stubbing external deps per test.

---

*Concerns audit: 2026-08-24*
*Update as issues are fixed or new ones discovered*
