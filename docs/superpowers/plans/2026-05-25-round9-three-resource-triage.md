# Round 9 — Six-to-Eight-Hour Three-Resource Triage Plan (FINAL)

## Context

Three independent audits (DEEP_DIVE, JANE_STREET_REVIEW, ROUND3 — all run on `/Users/nav/GitHub/floww` stale clone via DeepSeek Flash on Hermes, which hallucinates) surfaced 150+ issues. Architect verified 5 of 6 spot-checks against canonical (`/Users/nav/Documents/GitHub/floww`):

| Audit claim | Canonical state | Verdict |
|---|---|---|
| `conftest.py:28-81` autouse event-loop fixture kills 2,363 tests | Confirmed present | **REAL** |
| `inference.py` MODEL_REGISTRY broken | Already fixed; all 5 `_wf` model files exist | **STALE** |
| `ml_api.py:206` `os.path.exists()` no `import os` | Confirmed missing | **REAL** |
| `admin.py:37` `delete_many()` no `await` | Confirmed | **REAL** |
| `useMarketData.js:124` `fetch({timeout:30000})` | Confirmed (browsers ignore) | **REAL** |
| `heatseeker.py:119` `_fetch_history(..., lookback_mins=...)` | Confirmed call site | **REAL** |
| `ml_training.py` 10 routes call non-existent functions | Architect verified all 10 functions absent AND zero callers in frontend/scripts | **REAL — safe to DELETE** |

**Resources confirmed** (corrected from prior plan):
- 15 Hermes agents (Owl Alpha via router — the reliable one)
- 1 DeepSeek V4 Flash (free, hallucinates but rips through volume)
- 1 OpenCode GLM 5.1

**User-confirmed decisions** (from AskUserQuestion):
1. **ml_training.py**: DELETE (architect verified zero usage and zero defined functions)
2. **H14 SECRET_KEY**: hard-fail in production if env missing
3. **Sync cadence**: every 15 minutes
4. **NEW: memory + code leak hunting** added as 4th track

---

## Work Decomposition — 21 Units Across 3 Resources

### Hermes Track A — P0 Runtime Crash Fixes (Hermes 1-5, ~90 min)

| # | Unit | File(s) | Acceptance |
|---|---|---|---|
| H1 | Remove `autouse` event-loop fixture in `conftest.py:28-81`; let pytest-asyncio manage the loop. Replace with a per-test fixture (no `autouse`) that supplies a fresh motor client when the test asks for one. | `backend/tests/conftest.py` | `pytest -q --ignore=tests/e2e \| tail -3` shows ≥ 2,363 passing (up from ~35) |
| H2 | Add `import os` at top of `ml_api.py`. Run `pyflakes backend/routes/ml_api.py` to catch any other undefined names. | `backend/routes/ml_api.py` | `python -c "from routes.ml_api import router"` succeeds; pyflakes returns 0 undefined names |
| H3 | Add `await` to `admin.py:37` `db.errors.delete_many(...)`. Fix undefined `_start_time` (line 28) and `_schwab_streamer` (line 115) — either import from server.py or remove broken routes. | `backend/routes/admin.py` | `curl -X POST localhost:8000/api/errors/clear` returns 200 with `{deleted: N}`; pyflakes clean |
| H4 | Fix `heatseeker.py:119` `_fetch_history(...)` call. Either add `lookback_mins` to function signature OR change call site to pass an existing param. | `backend/routes/heatseeker.py` + `backend/services/heatseeker_history.py` if exists | `curl localhost:8000/api/heatseeker/node-lifecycle?ticker=SPY` returns 200, not 500 |
| H5 | **DELETE** `backend/routes/ml_training.py` entirely + remove the 2 include lines from `server.py:2687-2688`. Verified by architect: 10 functions don't exist anywhere, zero callers in frontend/scripts/tests. Working `/api/ml/*` routes live in `ml_api.py` and `ml_predict_api.py` — those stay intact. | `backend/routes/ml_training.py` (delete), `backend/server.py` (remove 2 lines) | `ls backend/routes/ml_training.py` → No such file; `grep ml_training backend/server.py` returns 0; backend starts clean; `pytest` doesn't regress |

### Hermes Track B — P0 Frontend Stability (Hermes 6-10, ~120 min)

| # | Unit | File(s) | Acceptance |
|---|---|---|---|
| H6 | Replace `fetch(url, { timeout: 30000 })` with `AbortSignal.timeout(30000)` everywhere. Browsers silently ignore `timeout`; this causes indefinite hangs. | `frontend/src/hooks/useMarketData.js`, plus any other hook found via `grep -rn 'timeout:' frontend/src/hooks/` | `grep -rn 'timeout: \[0-9\]' frontend/src/hooks/` returns 0; AbortSignal.timeout present at each fix |
| H7 | Fix `AlertOverlay.js:194` — `connect()` is called from one useEffect but defined inside another's closure. Refactor to component scope or properly scoped useCallback. | `frontend/src/components/AlertOverlay.js` | No `ReferenceError: connect is not defined` when tab visibility changes; manual reload test passes |
| H8 | 16 files use `process.env.REACT_APP_BACKEND_URL` with no fallback. Create `frontend/src/config/api.js` exporting `API_BASE = process.env.REACT_APP_BACKEND_URL \|\| "http://localhost:8000"`. Update all 16 imports. | `frontend/src/config/api.js` (new) + 16 callers from `grep -rln 'REACT_APP_BACKEND_URL' frontend/src/` | `grep -rn 'process.env.REACT_APP_BACKEND_URL' frontend/src/` returns only `config/api.js` |
| H9 | 12+ empty `catch (e) {}` blocks across 6 components. Replace with explicit error logging (use existing `reportError(e)` or `console.error`) + setState to user-visible error pane. | The 6 audit-identified component files | `grep -rn 'catch (e) {}' frontend/src/components/` returns 0 |
| H10 | Verify `CharmChart.jsx`/`VannaChart.jsx` import paths are still `../hooks/...` (audit-stale-clone may have regressed them). If broken, re-fix. | `frontend/src/components/CharmChart.jsx`, `frontend/src/components/VannaChart.jsx` | `grep '../../hooks' frontend/src/components/{Charm,Vanna}Chart.jsx` returns 0; npm start compiles clean |

### Hermes Track C — P0 Security + Deployment (Hermes 11-15, ~150 min)

| # | Unit | File(s) | Acceptance |
|---|---|---|---|
| H11 | Add `Depends(verify_api_key)` to 6 admin routes that leak trading state. Coordinate with H3 — H11 starts AFTER H3's commit lands on origin (origin-state gate). | `backend/routes/admin.py` (sections H3 didn't touch) | Each endpoint returns 401 without key, 200 with valid key. Tests in `backend/tests/routes/test_admin_auth.py` |
| H12 | Same auth fix for `/api/databento/usage` and `/api/performance/stats`. | `backend/routes/admin.py` + wherever `/api/performance/stats` lives | Same 401/200 pattern; tests added |
| H13 | Move API keys out of URL query params in `alpha_advantage.py`. Use `Authorization` header or POST body. | `backend/routes/alpha_advantage.py` | `grep 'apikey=' backend/routes/alpha_advantage.py` returns 0; existing tests still pass |
| H14 | `config/secrets.py:12` defaults to `"dev-only-key"`. Change: if `SECRET_KEY` env unset AND `ENVIRONMENT in {"production","staging"}` → raise SystemExit with clear error message. Default `"dev-only-key"` only allowed when `ENVIRONMENT=dev`. | `backend/config/secrets.py` (wherever this lives) | `ENVIRONMENT=production python -c "from config.secrets import SECRET_KEY"` exits with non-zero + clear message |
| H15 | Deployment hygiene quick wins: (a) `docker-compose.prod.yml` `Dockerfile` → `Dockerfile.backend`. (b) Azure Bicep dedupe duplicate `EnableMongo` + duplicate subnet. (c) `docker-compose.yml:39` `3000:80` → `3000:3000`. (d) `deploy.yml` app-name match terraform. (e) Add `frontend/public/offline.html`. (f) Add `models/` to `.gitignore`. | 6 files (listed in audit) | Each fix has a verification command in commit body; `docker compose -f docker-compose.prod.yml config` succeeds |

### Hermes Track D — Memory + Code Leak Hunting (Hermes 16-19, ~120 min) **[NEW per user request]**

| # | Unit | File(s) | Acceptance |
|---|---|---|---|
| L1 | Backend memory-leak audit. Hunt: (a) unbounded module-level caches (`_cache = {}` never trimmed), (b) `asyncio.create_task(...)` results never stored/awaited (dangling tasks), (c) MongoDB cursors created without `.to_list()` or `async for` (cursor leak), (d) file handles outside `with` blocks, (e) module-level singletons holding refs to per-request state. Write findings to `docs/ROUND9_BACKEND_LEAK_AUDIT.md`. Do NOT fix in this unit — just report. | `docs/ROUND9_BACKEND_LEAK_AUDIT.md` (new) | Report lists each finding with `file:line` + estimated severity (High/Med/Low) + suggested fix. Reviewable in 5 min |
| L2 | Frontend timer/interval leak audit. Hunt every `setInterval(...)` and `setTimeout(...)` in `frontend/src/`; verify each is paired with a `clearInterval`/`clearTimeout` in a `useEffect` cleanup function. Same for `addEventListener` ↔ `removeEventListener`. Write findings to `docs/ROUND9_FRONTEND_LEAK_AUDIT.md`. | `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` (new) | Report enumerates: total timers found / total properly cleaned up / total leaking. Each leak has `file:line` + fix recommendation |
| L3 | Frontend useEffect cleanup audit. Find `useEffect` blocks that fetch/subscribe but don't return cleanup function. Stale-closure traps. AbortController not aborted on unmount. | Same as L2 (extend the report) | Findings appended to `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` |
| L4 | Fix the top 5 highest-severity leaks identified by L1+L2+L3. Pick those with the highest crash/OOM risk (e.g., a setInterval polling every 5s with no cleanup will leak the entire dataset every time component unmounts). Document each fix with before/after grep evidence. | TBD by L4 agent based on L1-L3 reports (file ownership claimed at commit time) | 5 commits, each fixing one leak, each with grep proof in message |

### DeepSeek V4 Flash Track — Mechanical Cleanup (single agent, ~4-6 hours)

DeepSeek Flash hallucinates on judgment work but rips through linter-mechanical changes. Strict scope: only changes a linter would suggest.

| # | Unit | Files | Acceptance |
|---|---|---|---|
| DS1 | Run `ruff --fix --select F401` to remove 581 unused imports. Commit per-directory (one commit per top-level dir under backend/). | All `backend/**/*.py` mechanical | `ruff check --select F401 backend/` returns 0; full test suite passes |
| DS2 | Replace 81 `print()` calls in production code with `logging.debug()` or `logging.info()`. Add `logger = logging.getLogger(__name__)` at top of each file if missing. Files: per `grep -rn '^[^#]*print(' backend/ --include="*.py"` | Files identified by grep | `grep -c '^[^#]*print(' <each>` returns 0; tests pass |
| DS3 | Replace bare `except:` with `except Exception:`. Special: `social_flow_pipeline.py:335` bare except catches KeyboardInterrupt — must become `except Exception:`. Sequence: starts only after DS1 commits land per-directory. | All `backend/**/*.py` (sequenced after DS1) | `grep -rn '^[^#]*except:' backend/ --include="*.py"` returns 0; tests pass |
| DS4 | Add lint CI gate. Create `.github/workflows/lint.yml` running ruff on PR. | `.github/workflows/lint.yml` (new), `backend/pyproject.toml` | Workflow valid; PRs run lint going forward |

### OpenCode GLM 5.1 Track — Research Integration (single agent, ~4-6 hours)

GLM is best on math-heavy code with clear specs. Two highest-value Tier 1 ports.

| # | Unit | Files | Acceptance |
|---|---|---|---|
| G1 | Port pin-risk calculator from `FlashAlpha-lab/0dte-options-analytics`. Pure math, no API dependency. Returns `{pin_strike, pin_strength, dealer_hedge_dollars, expected_move}` from a chain payload. | `backend/services/pin_risk.py` (new), `backend/tests/services/test_pin_risk.py` (new with 5+ tests) | `pytest backend/tests/services/test_pin_risk.py -v` shows 5+ passed; commit includes synthetic-chain example with expected output; MIT license noted in module docstring |
| G2 | Port HMM emission features from `CameronScarpati/lob-regime-scanner`. Function `compute_emissions(returns, volumes) -> dict` returns `{realized_vol, abs_return, volume_ratio}`. Do NOT modify existing `regime_detector.py` — that's Round 10. | `backend/services/regime_emissions.py` (new), `backend/tests/services/test_regime_emissions.py` (new) | Tests pass with synthetic data; commit shows MIT license attribution |

### Architect (me) — Coordination + Closure (~60 min spread over 6-8 hours)

| # | Unit | Files | When |
|---|---|---|---|
| A1 | Live monitor: every 15 min, run `git fetch origin && git log origin/main --oneline --since="6 hours ago"` and post status table. Watch for halts, file-ownership violations, missed sync writes. | None (read-only) | Continuous, every 15 min |
| A2 | Closure: round-up doc with verified SHAs after all 21 units land. Verify L4's top-5 fixes by re-curling endpoints + re-checking grep counts. | `docs/ROUND9_CLOSURE.md`, `kanban/cards/round9_closure.md`, `docs/ROUND8_COMPLETION_LOG.md` (append) | Last 15 min of session |

---

## File Ownership Matrix (strict disjoint)

```
H1  → backend/tests/conftest.py
H2  → backend/routes/ml_api.py
H3  → backend/routes/admin.py (lines around 28-50)
H4  → backend/routes/heatseeker.py + backend/services/heatseeker_history.py
H5  → backend/routes/ml_training.py (DELETE) + backend/server.py (remove 2 lines)
H6  → frontend/src/hooks/useMarketData.js + any other hook with timeout: pattern
H7  → frontend/src/components/AlertOverlay.js (or .jsx)
H8  → frontend/src/config/api.js (new) + 16 callers (mechanical sed)
H9  → 6 audit-identified component files (empty catch blocks)
H10 → frontend/src/components/CharmChart.jsx, VannaChart.jsx
H11 → backend/routes/admin.py (sections NOT touched by H3) — origin-gated on H3
H12 → backend/routes/admin.py + wherever /api/performance/stats lives — origin-gated on H11
H13 → backend/routes/alpha_advantage.py
H14 → backend/config/secrets.py
H15 → docker-compose.prod.yml, infra/main.bicep, docker-compose.yml, .github/workflows/deploy.yml, frontend/public/offline.html (new), .gitignore
L1  → docs/ROUND9_BACKEND_LEAK_AUDIT.md (new, read-only audit)
L2  → docs/ROUND9_FRONTEND_LEAK_AUDIT.md (new, read-only audit)
L3  → docs/ROUND9_FRONTEND_LEAK_AUDIT.md (append, read-only audit)
L4  → TBD at commit time based on L1-L3 findings — claims ownership per-file
DS1 → backend/**/*.py (linter-driven mechanical only)
DS2 → ~5-10 files with print() calls
DS3 → backend/**/*.py (linter-driven, sequenced after DS1)
DS4 → .github/workflows/lint.yml (new), backend/pyproject.toml
G1  → backend/services/pin_risk.py + tests
G2  → backend/services/regime_emissions.py + tests
```

**Same-file dependencies (origin-state gated, not blocked):**
- H3 → H11 (both touch admin.py at different lines)
- H11 → H12 (same file pattern)
- DS1 → DS3 (per-directory sequencing)
- L1+L2+L3 → L4 (L4 reads audit reports to pick top-5)

**Forbidden for ALL agents (untouchable this round):**
- `backend/services/ml/inference.py` (architect-resolved; STALE audit finding)
- `backend/services/dash_ui.py` (Round 7 frozen)
- `backend/server.py` EXCEPT H5's 2-line ml_training removal
- `frontend/src/App.js`, `frontend/src/App.css`, `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- Any `.joblib`, `.pt`, `.json` model artifact

---

## Obsidian + Kanban Sync — 15-Minute Cadence (USER CONFIRMED)

Every 15 minutes, each agent appends ONE line to TWO files:

**1.** `kanban/cards/agent_<id>_status.md` (per-agent log, repo-tracked)
**2.** `~/Documents/GitHub/Hermes/Daily Log.md` (daily aggregate, Obsidian-synced)

Line format:
```
[2026-05-25T18:15:00Z] H3 :: in-progress :: admin.py await applied, pyflakes clean :: HEAD=abc1234
[2026-05-25T18:30:00Z] H3 :: DONE :: pushed def5678 :: tests admin_auth.py pass 4/4
```

If an agent dies mid-task, the next architect session reads:
```bash
ls -t kanban/cards/agent_*_status.md | head -20 | xargs tail -1
```
…and sees the last status of every agent in 1 second.

**Hard rule per agent**: if 15 minutes pass without a status line, the agent self-HALTs with `STALLED` and waits for architect.

---

## Anti-Skip Gates (Round 8 Bulletproof, repeated)

Every unit ends with:
1. `git commit` with grep/curl/test output INLINE in message body
2. `git pull --rebase origin main && git push origin main`
3. `git fetch origin && git log origin/main --oneline -1 | grep <commit subject>` MUST match — else HALT

Dependent units (H11, H12, DS3, L4) check the prior unit's origin SHA in their Phase 0. Cannot skip.

---

## Wall-Clock Schedule (parallel start at t=0)

| Time | Hermes A (P0 crash) | Hermes B (Frontend) | Hermes C (Security) | Hermes D (Leaks) | DeepSeek Flash | GLM | Architect |
|------|------|------|------|------|------|------|------|
| t+0 | H1, H2, H3, H4, H5 launch | H6, H7 launch | H13, H14, H15 launch (H11 waits) | L1, L2, L3 launch | DS1 starts (backend/services/) | G1 starts | Status post #1 |
| t+15 | — | — | — | — | — | — | Status post #2 |
| t+30 | H1 lands (test count surges 35→2363+) | H6 lands | H13 lands | L1 done | DS1 services done; starts routes | G1 progressing | Status post #3 |
| t+45 | H2, H3 land | H7, H10 land | H11 starts; H14 lands | L2 done | DS1 routes done | G1 lands; G2 starts | Status post #4 |
| t+60 | H4 lands; H5 (delete) lands | H8 starts | H11 lands; H12 starts | L3 done; L4 starts on top-5 | DS3 starts (per-dir after DS1) | G2 progressing | Status post #5 |
| t+90 | All A done | H8, H9 land | H12, H15 land | L4 progressing (5 fixes) | DS3 services done | G2 lands | Status post #7 |
| t+150 | — | All B done | All C done | L4 lands | DS3 done; DS2 starts | — | Status post #11 |
| t+240 | — | — | — | — | DS2 lands; DS4 lands | — | Status post #17 |
| t+300 | — | — | — | — | — | — | A2 closure |

Worst case: 6-8 hours with halts/reruns. Best case: 5 hours.

---

## E2E Verification

**Backend P0 fixes (H1-H5, H11-H15):**
- After each commit, restart backend: `kill $(lsof -i :8000 -t) 2>/dev/null && cd backend && nohup uvicorn server:app --port 8000 > /tmp/uvicorn.log 2>&1 &`
- Curl affected endpoint; status code in commit body
- H1 specifically: `pytest -q --tb=no | tail -3` shows passing count ≥ 2,363

**Frontend P0 fixes (H6-H10):**
- CRA hot-reload picks up within 10s
- Open Chrome PWA via `decoder` alias → click affected element → no console error
- chrome-devtools MCP screenshots saved to `docs/screenshots/round9/`

**Leak fixes (L4):**
- Per-fix: chrome-devtools heap snapshot before fix, perform leak trigger (e.g., mount→unmount component 50×), heap snapshot after fix. Memory delta should be ~0 (was growing pre-fix).

**Research ports (G1, G2):**
- `pytest backend/tests/services/test_pin_risk.py -v`
- `pytest backend/tests/services/test_regime_emissions.py -v`

**Final coordinator gate (A2):**
- `git log origin/main --since="8 hours ago" --oneline | wc -l` → ≥ 21 work commits + closure
- `pytest -q --tb=no | tail -3` → passing count ≥ 2,363
- Open PWA → click previously-broken elements → visual confirmation

---

## What Could Go Wrong + Pre-emptive Fixes

| Risk | Mitigation |
|---|---|
| H1 conftest fix breaks tests in unexpected ways | H1 agent runs `pytest -q --tb=short` after the fix, reports any new failures BEFORE committing. If count drops below baseline 35, HALT. |
| H5 deletes ml_training.py but some script we missed imports from it | Architect already grepped: 0 callers in `frontend/src`, `scripts/`, `tests/`. Safe. |
| H11 race with H3 on same file | H11 Phase 0 step: `git log origin/main --oneline -1 \| grep "admin.py"` — must show H3's SHA first |
| DeepSeek Flash hallucinates and breaks code | DS1/DS3 ONLY run linter-mechanical changes; DS2 is `grep`-driven. Architect spot-checks one commit per DS unit. |
| GLM ports wrong math | G1/G2 ONLY add NEW files; can't break existing code. If math is wrong, tests fail; agent re-iterates. |
| L4 fixes a leak in a file owned by another agent | L4 claims file ownership at commit time and origin-gates on the owning agent's last commit. |
| Agent dies mid-task without writing status | 15-min hard-rule self-HALT. Architect monitors at every 15-min status post and notices the missing line. |
| All 15 Hermes agents not actually available | Plan still works: serialize Track A→B→C→D over 4-6 hours instead of parallel 2 hours. |

---

## What This Plan Does NOT Do (deferred Round 10)

- 88.8% functions missing type hints
- 83 functions > 50 lines (incl. `create_dash_app` at 591 lines)
- 932 potentially dead functions (need verification before deletion)
- ML feature unification across 3 cloned compute paths
- Data leakage in training pipeline (labels before temporal split)
- 50+ files with zero error logging (broader observability sprint)
- Cron job error detection (`set -e`, MAILTO)
- TypeScript migration / PropTypes adoption
- Tier 2 research (Neural Hawkes LOB, walk-forward VPIN, full-info trade classification)
- Tier 3 research (Deep LOB Forecaster, etc.)
- ALL 144 unverified audit findings from the stale-clone reports

---

## Self-Check (architect honesty)

1. **21 units is at the upper edge of what I should plan in one round.** I've added the leak track because user explicitly requested it; if any single agent is unavailable, the corresponding units defer cleanly to Round 10.
2. **The 6-hour wall-clock estimate is optimistic.** With halts, network failures, and DeepSeek Flash's hallucination rate, 8 hours is realistic. I've buffered the schedule.
3. **I am not promising every audit finding gets fixed.** 21 of 150+ is the right number for one round. Trying for more = Round 7 chaos.
4. **The leak track will likely find more issues than L4 can fix in time.** That's fine — L4 fixes the top 5, the rest become Round 10 backlog with audit reports already written.
5. **I will personally watch every 15-min status post.** If 3 consecutive posts show an agent stalled, I unblock it within 5 min (Round 8 Bulletproof showed this loop works).
