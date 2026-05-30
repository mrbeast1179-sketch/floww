# Round 10 — Architect Audit & Remediation (2026-05-30, Claude)

> Session goal: "connect everything, make sure it syncs, no mistakes." Established
> ground truth, fixed the foundational blocker, integrated/reverted overnight
> agent WIP, repaired regressions, and fixed the high-ROI failure clusters. This
> doc is the honest state + prioritized backlog for the swarm.

## TL;DR — the overnight narrative was false in one critical way

**The test suite was never running.** Two test bootstraps replaced real packages
in `sys.modules` with bare `ModuleType` stubs (stripping `__path__`), so pytest
aborted at collection with 25 errors. "354 passed" was a *subset* run; the full
suite never executed. Fixing collection unmasked ~60 pre-existing failures that
were always there. None were introduced by this session.

Baseline progression: **suite-won't-collect → 60 failed → 39 failed / 2533 passed**
(excluding `tests/chaos` = destructive, `tests/e2e` = needs a browser).

## Commits landed on origin/main this session (all verified with anti-skip gate)

| SHA | What |
|---|---|
| `81e64c0` | Collection fix — stop tests clobbering `sys.modules['services'/'scipy'/'torch']` (25 collection errors → 0) |
| `8872718` | Schwab reconnect jitter + finished P1.2 async-mock chaos tests (8 pass) |
| `a6e130b` | Committed missing QQQ/TLT `rf_production` models (force-add) → 5/5 inference works on a fresh clone |
| `4e789c8` | Fixed `from backend.X` imports that re-broke collection |
| `6bfedc6` | Restored `data_providers` router (an agent had gutted it; `server.py` imports it) |
| `f2eebdf` | Salvaged rate-limit tracker + fixed dedup test import |
| `7004509` | Put-delta sign bug + credit_monitor config fields |
| `3d7bdc5` | `AlertEngine.get_latest/get_previous` (detect_alerts) |

(Agent `14bc435` — H26's `/api/health` probes + schwab jitter — was integrated; we
independently produced the same `_FakeWS` schwab fix.)

## Verified critical findings

1. **ML "Sharpe 5.20" is fabricated.** It's an `acc/(1-acc)` proxy
   (`scripts/train_real_data_ml.py:356`, `train_gex_models.py:156`), not a Sharpe.
   The models actually wired into live inference (`*_rf_production`) are honest but
   have **~0.35 test accuracy = no edge** for a 3-class target. Real leakage is in
   the *trainers*: `StandardScaler` + supervised feature-selection fit on the FULL
   series **before** the train/test split (`train_real_data_ml.py:404-426`). The
   `*_wf` / `*_gbm_deep` artifacts carry in-sample numbers (Sharpe 7.8–31) and a
   `beats_baselines` SHIP gate that was hardcoded true. **The committed QQQ/TLT
   models fix the inference *crash* — they do not add predictive edge.**

2. **Concurrency hazard (process-level, not just clones).** Multiple agents (H26,
   H27, …) were live in THIS clone sharing the git index. A `git commit` without a
   pathspec swallowed a concurrently-staged broken file (`data_providers.py` with a
   `from backend.` import) and pushed it to origin. Mitigation now in use: pathspec
   commits, `pull --rebase --autostash`, lane separation.

3. **Agent WIP had real regressions** (reverted/discarded this session):
   - `server.py` mass `prefix="/api"` removal — would break 6 relative-path routers
     (analytics, briefing, morning_briefing, memory, portfolio, live_trading).
   - `duckdb_engine.py` `asyncio.sleep → time.sleep` in an async retry (blocks the
     event loop).
   - `services/core.py` (imports a name that doesn't exist; unused) — deleted.
   - `test_duckdb_resilience.py` (asserts retries that don't occur) — deleted.
   - `alerts_api.py` removed the real `AcknowledgeRequest` class — reverted.

## Remaining failures (39) — root-caused, for the swarm

| Cluster | Count | Root cause | Recommended fix |
|---|---|---|---|
| `test_obsidian_sync` | 10 | `ObsidianSync.sync_all()` calls 4 **unimplemented** methods (`get_obsidian_path`, `get_claude_path`, `sync_file`, `save_log`) in `scripts/obsidian_sync.py` | Implement the 4 methods (a candidate patch exists). Peripheral dev tool — low priority. |
| `risk/test_gate` | 9 | RiskGate approve/reject/circuit-breaker logic mismatches | Investigate `services/risk/gate.py` vs the test contract (liquidity, conviction, daily-loss, consecutive-losses thresholds). |
| `test_microstructure_math::TestNodeLifecycle` | 6 | Node lifecycle state transitions (formed→active→tapped→expired) | Investigate the node tracker in `services/` microstructure module. |
| `test_causal_inference` | 4 | backdoor criterion / do-calculus / IV-method numerics | Domain math review. |
| `test_api` (shape) | 4 | endpoints omit keys tests expect (`implied_pdf`, `curve`, `stability_zones`, `total_charm_to_close`) | Reconcile endpoint response schema vs test expectations. |
| `test_fallback_responses` | 4 | degraded/fallback routes don't return 200 + required fields on upstream error | Align route error-handling with the degraded-contract tests. |
| `test_analytics_validation` | 1 | flip-zones `window_pct` too-large should 422 | Add the validation bound. |
| `test_p99_latency` | 1 | `fill_monitor` record latency budget | Likely flaky/perf — confirm on a quiet machine. |

## Route bugs (from the code audit; NOT yet fixed — agent's broad attempt was reverted)

- **`/api/performance/stats` double-prefix 404.** `admin.py` decorators use absolute
  `/api/...` AND `server.py` mounts with `prefix="/api"`. Correct fix: make
  `admin.py` + `llm.py` decorators **relative** (`/performance/stats`) and keep the
  uniform `prefix="/api"` — do NOT remove the prefix globally (breaks relative-path
  routers).
- **`llm.py` 3 dead endpoints** — `routes/llm.py` imports `llm_analyze_trade_handler`,
  `llm_generate_briefing_handler`, `get_llm_providers` from `server`; none exist →
  500s. Either implement them in `server.py` or remove the routes.
- **Catch-all shadowing** — `data_providers.py` (`/status`,`/health`), `trinity.py`
  (`/align`), `anomaly.py` (`/ensemble*`) are declared AFTER `/{ticker}` and are
  unreachable. Move literal routes before the `{ticker}` catch-all.
- **`ml_dashboard.py` fully route-shadowed** by `ml_api.py` + `ml_predict_api.py`
  (registered earlier). Collapse the duplication so the intended handler serves.

## ML integrity backlog (separate track from "make tests pass")

1. Quarantine fabricated-Sharpe artifacts (`*_wf`, `*_gbm_deep`).
2. Fix trainer leakage: fit scaler + feature-selection **inside** each walk-forward
   fold, not on the full series.
3. Replace the `acc/(1-acc)` "Sharpe" with `services.ml.gate.compute_trading_sharpe`
   under the Sharpe ≤ 3 cap the 2026-05-18 audit prescribed.
4. Retrain; only then is "5/5 models" meaningful as *edge*, not just non-crashing.

## Process recommendations

- **Don't run multiple write-agents in ONE clone sharing the index.** Give each a
  git worktree or stagger them. The index race already pushed a broken import to
  origin once this session.
- **Add a CI gate that runs `pytest --collect-only`** (and ruff). Either would have
  caught the `sys.modules` clobber and the `from backend.` import regressions before
  they reached origin.
- **Treat agent "N passed / done" as unverified** until a real run confirms it.

## Security (action required by Nav — I can't rotate your tokens)

- Rotate `ghp_lhtC…` (pasted into chat) and `ghp_MgVg…` (was embedded in the rogue
  clone's remote URL). The rogue clone `/Users/nav/floww` was archived to
  `/Users/nav/.archive/floww_rogue_20260530`.
