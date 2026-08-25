---
phase: session-2026-08-23-deploy-prep
extracted: 2026-08-24
source: session log (no numbered phase artifacts — extracted from git history 99fae06..46276a0 + Obsidian session notes)
missing_artifacts: [PLAN.md, SUMMARY.md, VERIFICATION.md, UAT.md]
---

# Learnings — Deploy Prep & Test Infrastructure (2026-08-23/24)

## Decisions

1. **Private-repo deploy path: SSH deploy key over curl-bootstrap.** The repo is
   private, so the original one-line `curl ... | bash` bootstrap 404s on any
   server. Generated an ed25519 keypair, registered the pub half as a read-only
   deploy key (`oracle-vm-deploy`) on GitHub, and wrote `deploy/free/oracle-setup.sh`
   to install it at `/root/.ssh/floww_deploy_key`. Private key stays local + gitignored.
2. **torch excluded from production image.** Grep proved torch is imported only by
   `backend/tests/*` — never by `server.py` or any service. `Dockerfile.backend` now
   grep-filters it from requirements (~1GB image savings). Verified `server.py` imports
   cleanly with torch import blocked.
3. **FTDC disabled on Mongo.** A FTDC interim-write failure aborts mongod (fassert →
   signal 6). Friend-scale traffic gains nothing from diagnostic samples.
   `diagnosticDataCollectionEnabled=false` in compose command args.
4. **Honest UI controls over phantom options.** Timeframe dropdown reduced to the three
   values with real server-side behavior differences (Scalp·1m / Day·5m / Swing·1h);
   Trinity DTE labels corrected to describe expiry counts, not DTE.
5. **Lane separation across concurrent agents.** Agent 1 (GSD) owns CI/lint/test-infra;
   agents 2/3 own live docker stack, frontend components, and deploy scripts. One
   writer per surface.

## Lessons

1. **`[tool:pytest]` in a pytest.ini file silently disables the entire file.**
   That section header is only valid in setup.cfg. pytest.ini requires `[pytest]`.
   Symptom was subtle: no errors, just asyncio_mode=auto / markers / filterwarnings
   all quietly not applied — surfacing as 39 unrelated "broken" tests.
2. **Wall-clock assertions in tests are load-flaky by construction.** A 50ms latency
   assert fails when the full suite hammers the CPU. Use generous ceilings for CI,
   warn-and-log for design budgets.
3. **Mocked ASGI apps must actually drive receive/send.** A bare `AsyncMock()` app
   accepts `await app(scope, receive, send)` but never awaits the send callable —
   downstream `send.assert_awaited()` can never pass. Spy-wrap a real coroutine.
4. **Module-global memoized singletons break test stubs.** `routes/alerts.py`
   caches `_alert_engine`; once built, stubs of `sys.modules["alert_engine"]` never
   fire. Tests must reset the global via monkeypatch. Same pattern exists in
   agent_hub, microstructure, paper_trading, replay routes (future hazard).
5. **Docker healthcheck failures need triage before restart.** `free-backend-1`
   showed unhealthy after 12h because the pre-fix image wedged on the None-coalesce
   bug — rebuilding with current code was the fix, not config changes.

## Patterns

1. **Time-bomb tests:** tests seeding fixed dates but asserting against sliding
   windows (`date.today() - n_days`) pass until the calendar overtakes them, then
   fail without any code change. Fix pattern: injectable `today` parameter on the
   read function; tests pass their fixed date through.
2. **Incremental excitation for Hawkes thinning:** maintain
   `A *= exp(-beta*w); A += 1` per candidate instead of recomputing
   `sum(exp(-beta*(t-t_i)))` — O(n²)→O(1) per simulation.
3. **Domination-rate bound for Ogata thinning:** derive λ★ from stationary intensity
   λ̄ = μ/(1−η) plus an events-on-[0,T] sup, NOT from the n_max cap (which inflates
   the iteration budget to ~9M when callers pass large caps).
4. **SWR cache poison guard:** degraded upstream payloads (429 windows) must never
   be cached — check payload completeness before `cache[key] = data`.
5. **None-coalesce discipline:** `dict.get("iv", 0.2)` returns None when the key
   exists with value None. Numeric fields from external APIs need explicit
   `or default` coalescing. Fixed at 14 sites; audit for new instances on every
   new integration field.

## Surprises

1. **The full test suite hung, didn't fail.** Root cause wasn't network or a broken
   test — leaked DuckDB engines each hold ~ncores spinning TaskScheduler threads;
   enough leaks froze the box at 93% CPU with no progress.
2. **A single stale .gitignore-style section header broke 39 tests across 11 files.**
   The pytest.ini header bug meant prior "fixes" to individual symptoms were treating
   noise; the real signal appeared only after the config actually loaded.
3. **`models/` is partially tracked despite gitignore.** Force-add works for tracked
   files; the SPY joblib re-pickle needed `git add -f`.
4. **CI collected tests for a gitignored module.** `.gitignore` excluded
   `backend/services/strategy_builder.py` while its test file was tracked — local
   runs passed, CI failed with ModuleNotFoundError. Gitignore hygiene is test
   infrastructure.
