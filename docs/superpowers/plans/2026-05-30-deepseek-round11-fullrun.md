# DeepSeek Pro — Round 11 Full Run (~5-hour execution prompt)

> **For agentic workers:** Execute top-to-bottom. Steps use checkbox (`- [ ]`).
> This is a FULL multi-hour workload across 5 phases — do NOT stop after Phase 1.

**Goal:** Take the floww backend from 9 failing tests to ~0, harden routes/contracts, fix the ML *leakage* (mechanically, with brutal honesty gates), and clean hygiene debt — all verified with real pytest/grep output, all on `origin/main`.

**Architecture:** FastAPI + pytest. You fix source bugs to make existing tests pass, then add coverage and do well-scoped refactors. One task at a time: fix → verify with real output → pathspec commit → push+verify → next.

**Tech stack:** Python 3.13, pytest (asyncio auto), FastAPI, numpy, sklearn. Venv: `backend/.venv`.

---

## 0. PRIME DIRECTIVE — read first, re-read hourly

You have ~5 hours. **Spend ALL of it.** The last run finished in 20 minutes because it was small — this is 10x larger; pace yourself, do every phase. **Honesty is the only metric that matters.** A truthful "Phases 1–3 done, 4 partial, 5 not reached" is a win. A fabricated "all green" is the worst possible outcome and is caught in seconds by re-running pytest. The project's Round-7 fake-completion incident is the floor — never go below it.

If you finish all 5 phases with time left, go to Phase 6 (stretch). Never idle, never fake.

## 1. NON-NEGOTIABLE RULES

1. **Canonical clone ONLY:** `/Users/nav/Documents/GitHub/floww`. If `pwd` doesn't end in it, STOP and cd.
2. **Venv only:** `backend/.venv/bin/python3`. Tests: `cd backend && .venv/bin/python3 -m pytest <path> -q -p no:cacheprovider`. **NEVER** run `tests/chaos` (destructive) or `tests/e2e` (needs a browser).
3. **NEVER claim a test/grep result without pasting the real output line.** No "should pass."
4. **PATHSPEC COMMITS ONLY:** `git commit -m "..." -- file1 file2`. **NEVER** `git add -A`/`git add .`/`git commit -a` (other agents share this clone's index — this rule is why origin didn't break last round).
5. **Anti-skip gate after EVERY commit:**
   `git pull --rebase --autostash origin main && git push origin main` then
   `git fetch origin && git log origin/main --oneline -1 | grep "<your subject>"`. Empty grep = push failed = STOP.
6. **FORBIDDEN — do not edit (escalate to Nav if a fix needs them):**
   `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, **`MODEL_REGISTRY`**, any **model artifact** (`backend/models/*.joblib|*.json`), `frontend/.env`, `frontend/package.json`. Also DONE — do not touch: `tests/services/risk/test_gate.py` / `services/risk/gate.py` (architect handled), `tests/services/test_obsidian_sync.py`.
7. **FORBIDDEN git ops:** force-push, `--no-verify`, `reset --hard`, `checkout .`, `restore .`, `clean -fd`, `rebase -i`, amending another author's commit.
8. **Test discipline:** NEVER add `@pytest.mark.skip`/`xfail` to make a number look better (architect approval only). If your change breaks a *previously-passing* test, your change is wrong — revert.
9. **If a fix needs a forbidden file, a risk/trading threshold, a model retrain+promote decision, or guessing intended business behavior — STOP that task, write one sentence why, move on.**

## 2. ENVIRONMENT

```bash
cd /Users/nav/Documents/GitHub/floww && git fetch origin && git status --short
# Baseline (your starting truth, ~2.5 min):
cd backend && .venv/bin/python3 -m pytest -q --tb=no -p no:cacheprovider --ignore=tests/chaos --ignore=tests/e2e -rf 2>&1 | tail -30
```
Mongo should be up (`lsof -ti :27017`). The exact remaining failures + root causes are in `docs/ROUND10_DEEPSEEK_STATUS_2026-05-30.md` — read it.

---

# PHASE 1 — Close the last 9 failures

## Task 1.1 — fallback_responses (4) · stale paths + degraded-shape unification
**Files:** `backend/tests/routes/test_fallback_responses.py`, `backend/services/cache_router.py`

Root cause (verified by architect): tests hit `/api/analytics/implied-pdf|movers|history` but routes are at `/api/implied-pdf|movers|history` (flat `/api/`, per test_api convention) → 404. AND the route's `degraded_response` (in `services/cache_router.py:121`) returns `{degraded, detail, error_type, spot, contracts}`, but the test wants `{status, reason, stale, retry_after, asof}`.

- [ ] Run `pytest tests/routes/test_fallback_responses.py -q` → 4 failed.
- [ ] Fix the 3 stale paths in the test: `/api/analytics/implied-pdf/SPY` → `/api/implied-pdf/SPY`, `/api/analytics/movers` → `/api/movers`, `/api/analytics/history/SPY` → `/api/history/SPY`, `/api/analytics/regime/SPY` → `/api/regime/SPY`.
- [ ] In `services/cache_router.py`, change the module-level `degraded_response(error_type, detail, retry_after=15)` to return a **superset** dict that ALSO includes: `"status": "degraded"`, `"reason": error_type`, `"stale": True`, `"retry_after": retry_after`, `"asof": <ISO-8601 now>`. Keep the existing keys so current callers don't break.
- [ ] For `/movers` and `/history` the tests also assert `d["results"] == []` / `d["snapshots"] == [] and d["count"] == 0` — ensure those routes' degraded path returns those empty fields (read the routes; add the empty keys to their degraded return).
- [ ] Verify: `pytest tests/routes/test_fallback_responses.py -q` → 4 passed AND `pytest tests/test_api.py -q` still green (the routes are shared).
- [ ] Pathspec commit `-- backend/tests/routes/test_fallback_responses.py backend/services/cache_router.py` (+ any route file you edited). Gate.

## Task 1.2 — admin performance_stats (2)
**Files:** `backend/tests/routes/test_admin_auth_extra.py`

Root cause: test still requests the OLD double path `/api/api/performance/stats` (404); endpoint is now correctly `/api/performance/stats` and returns 503 because admin auth isn't configured in the test.
- [ ] Run the 2 tests; read them.
- [ ] Update the request paths to `/api/performance/stats` and `/api/databento/usage` (drop the extra `/api`). Then make the test set the admin key env the same way other admin tests do (grep the repo for how `_require_admin_auth` reads its key, e.g. an env var, and set it via monkeypatch/fixture) so no-key → 401 and with-key → 200. If the endpoint genuinely can't reach 200 without external config, assert the documented degraded/503 contract instead — but document why in the commit.
- [ ] Verify both pass; pathspec commit; gate.

## Task 1.3 — analytics_validation (1)
**Files:** `backend/server.py` (validation_exception_handler, ~line 167) OR `backend/tests/routes/test_analytics_validation.py`

Root cause: `flip-zones?window_pct=2.0` correctly returns 422, but the custom `validation_exception_handler` response doesn't expose the field under `detail`, so `any("window_pct" in str(d) for d in r.json()["detail"])` is False.
- [ ] Read the handler. Make it return the standard FastAPI shape `{"detail": [{"loc": [...], "msg": ..., "type": ...}, ...]}` (preserve `loc` so the field name appears) — this is the least-surprising fix and helps every validation test. Run the FULL suite after (server.py is shared) to confirm no regression.
- [ ] If touching server.py risks other tests, instead adjust the test to read the handler's actual key — but prefer fixing the handler. Verify; pathspec commit; gate.

## Task 1.4 — perf/latency (2) · do NOT skip
**Files:** `backend/tests/perf/test_p99_latency.py`, `backend/tests/services/test_greeks_api.py`
- [ ] Run each; read the asserted budget. These are wall-clock budgets that fail under load. Do NOT xfail/skip. Either (a) raise the budget to a realistic value with a comment explaining it's machine-dependent, or (b) make the assertion a p99 over N runs rather than a single sample. Keep them meaningful, not disabled. Verify; commit; gate.

---

# PHASE 2 — Route & contract hardening

## Task 2.1 — verify llm endpoints actually work
**Files:** `backend/routes/llm.py`, new `backend/tests/routes/test_llm_endpoints.py`
- [ ] DeepSeek wired `llm.py` to `services.llm` last round — VERIFY it: write a test hitting `GET /api/llm/providers`, `POST /api/llm/analyze-trade`, `POST /api/llm/generate-briefing` via TestClient; assert each returns 200 or a clean 503 (not a 500/ImportError). Fix `llm.py` if any 500s. Verify; commit; gate.

## Task 2.2 — collapse ml_dashboard duplicate routes
**Files:** `backend/routes/ml_dashboard.py`, `backend/server.py` (include_router order)
- [ ] The audit found `ml_dashboard.py` routes (`/api/ml/compare|predict|models|features|model-info`) are fully shadowed by `ml_api.py` + `ml_predict_api.py` (registered earlier). Confirm by grepping the duplicate paths. Remove the dead duplicates from `ml_dashboard.py` (keep only its unique `/dashboard/{ticker}`, `/reload/{ticker}`), OR if `ml_dashboard`'s impl is the intended one, fix include order — pick ONE owner per path. Verify the surviving endpoints still 200 + no ml tests regress. Commit; gate.

## Task 2.3 — full catch-all shadowing audit
**Files:** all `backend/routes/*.py`
- [ ] Grep every router for `@router.get("/{...}")` and confirm no literal route in the same router is declared AFTER it (the bug fixed for data_providers/trinity/anomaly last round). For each remaining offender, move literals above the catch-all. List what you found (even if zero). Verify imports + any related tests. Commit per file group; gate.

## Task 2.4 — silent-failure logging
**Files:** `backend/routes/ml_outcome_api.py:~296`, `backend/routes/ml_predict_api.py:~300`, `backend/routes/replay.py:~65`
- [ ] These have `except Exception: pass` that swallow errors silently (audit finding). Add a `logger.warning(...)` with context to each (do NOT change control flow). Verify the files import + related tests pass. Commit; gate.

---

# PHASE 3 — Test hardening & lint

## Task 3.1 — ruff clean
- [ ] `cd backend && .venv/bin/ruff check .` → fix every F-level error (unused imports/names, etc.) it reports in non-frozen files. Re-run until clean. Commit the fixes (pathspec the files you changed); gate. (Lint is the CI gate — keep it green.)

## Task 3.2 — coverage for this round's fixes
**Files:** new tests under `backend/tests/routes/` / `backend/tests/services/`
- [ ] Add focused tests pinning the contracts you fixed in Phase 1–2 that lack a regression test (e.g. the unified degraded shape; the llm endpoints; the route-ordering reachability of `/api/data/status`, `/api/trinity/align`). Each test must FAIL if the bug returns. Verify they pass now; commit; gate.

---

# PHASE 4 — ML LEAKAGE FIX (mechanical only — STRICTEST gates)

> The reported "Sharpe 5.20" was a fabricated `acc/(1-acc)` proxy and the trainers fit
> preprocessing on the full series before the split (leakage). You will fix the CODE,
> print HONEST raw metrics, and **commit NO model artifacts and change NO MODEL_REGISTRY.**
> You may NOT report a Sharpe number as evidence of anything. Promotion is the human's call.

## Task 4.1 — fit preprocessing inside each fold
**Files:** `backend/scripts/train_real_data_ml.py` (~404-426), `backend/scripts/train_gex_models.py` (~199-214)
- [ ] Read the walk-forward CV. Currently `StandardScaler().fit_transform` and supervised feature-selection run on the FULL `X` before the train/test split. Refactor so the scaler AND feature-selection are fit on **train-only** inside each fold and merely `transform` the test slice.
- [ ] **Verify mechanically (this is the DoD, not a Sharpe number):** `grep -n "scaler" backend/scripts/train_real_data_ml.py` and show that every `.fit(`/`.fit_transform(` on the scaler/selector is inside the fold loop, never on full `X`. Paste the grep.
- [ ] Do NOT run a full retrain, do NOT write `.joblib`, do NOT touch `MODEL_REGISTRY`. Commit only the two scripts; gate.

## Task 4.2 — kill the fake Sharpe metric
**Files:** `backend/scripts/train_real_data_ml.py:~356`, `backend/scripts/train_gex_models.py:~156`
- [ ] Replace `sharpe = test_acc / (1.0 - test_acc + 0.01)` with either the real `services.ml.gate.compute_trading_sharpe(...)` (if a return series is available) or remove the metric and print **raw fold OOS accuracy** instead. Never label `acc/(1-acc)` as "sharpe" anywhere.
- [ ] Verify: grep shows no remaining `acc / (1` or `/ (1.0 - ` Sharpe proxy. Commit; gate.

## Task 4.3 — leakage-guard regression test
**Files:** new `backend/tests/services/ml/test_no_preprocessing_leakage.py`
- [ ] Write a test that imports the trainer's fold function (or a small refactored helper) and asserts the scaler is NOT fit on data that includes the test indices (e.g., by spying on `.fit` calls, or asserting a documented invariant). It must fail against the OLD leaky pattern and pass against your fix. Verify; commit; gate.

---

# PHASE 5 — Hygiene

## Task 5.1 — doc-rot
**Files:** `docs/ROUND9_FINAL_CLOSURE.md`
- [ ] The audit found it cites non-existent files (`backend/services/backtest_engine.py`, `market_data_scheduler.py`) and wrong line refs. Correct the citations to the real files (`services/backtest.py`, `services/scheduler.py`, the central `server.py` task tracking) by grepping for the actual symbols. Commit; gate. (Docs — no test, but verify the files you cite exist via `ls`.)

## Task 5.2 — type hints + mypy
**Files:** `backend/services/greek_aggregator.py`, `iv_skew_analyzer.py`, `oi_change_detector.py`, `rate_limit_tracker.py`
- [ ] Fully annotate these 4 modules. Run `cd backend && .venv/bin/python3 -m mypy <files>` (install mypy in the venv if missing: `.venv/bin/pip install mypy`). Fix to exit 0. Paste the mypy output. Commit; gate.

## Task 5.3 — dead-code phase 2 (CAREFUL)
**Files:** per the "Likely dead" list in `docs/ROUND10_DEAD_CODE_AUDIT.md`
- [ ] For each candidate, `grep -rn "<name>" backend/ frontend/` to prove ZERO callers. ONLY then remove it, one symbol per commit, with the caller-grep (=0) pasted in the commit body. Run the full suite after each removal — any new failure = it wasn't dead, revert. Do at most 5 to stay safe. Gate each.

---

# PHASE 6 — Stretch (only if Phases 1–5 done with time left)
- [ ] Run the full suite; for any remaining failure not in scope, root-cause and fix if it's a clear source bug (not a forbidden file / judgment call).
- [ ] Migrate the deprecated `@app.on_event("startup"/"shutdown")` in `server.py` to a single FastAPI `lifespan` handler (the real "graceful shutdown" DeepSeek-v1 claimed but never did). Verify the app still imports + the full suite is green. Commit; gate.

---

## FINAL — honest status (required)
- [ ] Run: `cd backend && .venv/bin/python3 -m pytest -q --tb=no -p no:cacheprovider --ignore=tests/chaos --ignore=tests/e2e 2>&1 | tail -3` and paste the real summary line.
- [ ] Update `docs/ROUND10_DEEPSEEK_STATUS_2026-05-30.md` (append a Round-11 section): per task DONE (with the `N passed`/grep evidence) / PARTIAL / SKIPPED (+ one-line reason). Compare the final failure count to the 9 you started with. Pathspec-commit it. **No rounding up. No claim without the pytest/grep line proving it.**

## Self-review for the executor
Before declaring a phase done, re-read its tasks and confirm each has a pasted-output verification. If a task's DoD is a grep (Phase 4), the grep output IS the evidence — a Sharpe number is NOT.
