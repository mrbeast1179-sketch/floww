# DeepSeek Pro — Round 10 Failure Remediation (execution prompt)

> **For agentic workers:** Implement task-by-task. Steps use checkbox (`- [ ]`).
> This is a self-contained brief — paste it whole into DeepSeek Pro.

**Goal:** Drive the floww backend test suite from **39 failing → as close to 0 as possible** by fixing pre-existing failures that were unmasked when the architect repaired test collection. Each task = one failing-test cluster with a known root cause.

**Architecture:** FastAPI backend + pytest. The tests already exist and already fail; you are *making existing tests pass by fixing source bugs*, not writing new features. Work one cluster at a time, verify with real pytest output, commit per cluster, confirm on origin, move on.

**Tech stack:** Python 3.13, pytest (asyncio auto), FastAPI, numpy. Venv at `backend/.venv`.

---

## 0. PRIME DIRECTIVE — read before doing anything

You have a 5-hour budget. **Honesty beats coverage.** A truthfully-reported "3 clusters fixed, 4 attempted, 2 too hard" is a SUCCESS. A fabricated "all green" is the single worst outcome and will be caught instantly by re-running pytest. The project's Round-7 fake-completion incident is the negative-example floor — do not repeat it.

## 1. NON-NEGOTIABLE RULES

1. **Canonical clone ONLY:** `/Users/nav/Documents/GitHub/floww`. If `pwd` doesn't end in `Documents/GitHub/floww`, STOP and `cd` there. Never create or use any other floww clone.
2. **Always use the venv:** `backend/.venv/bin/python3` — never system Python.
3. **NEVER claim a test passes without pasting the real pytest summary line** (e.g. `7 passed in 0.3s`). No paraphrasing, no "should pass."
4. **Anti-skip gate after EVERY commit:**
   ```bash
   git pull --rebase --autostash origin main && git push origin main
   git fetch origin && git log origin/main --oneline -1 | grep "<your commit subject substring>"
   ```
   If the `grep` prints nothing, your push did NOT land — STOP and investigate. Do not continue on a false success.
5. **PATHSPEC COMMITS ONLY.** Other AI agents may be editing this same clone and sharing the git index. Stage/commit ONLY your own files:
   ```bash
   git commit -m "msg" -- path/to/file1.py path/to/test1.py
   ```
   **NEVER** use `git add -A`, `git add .`, or `git commit -a` — you will swallow another agent's half-finished file and break origin (this already happened once).
6. **FORBIDDEN files — do not edit (ask the architect/Nav if a fix needs them):**
   `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, anything under `backend/models/` (`.joblib`/`.json`), `frontend/.env`, `frontend/package.json`.
7. **FORBIDDEN git ops:** `push --force`, `commit --no-verify`, `reset --hard`, `checkout .`, `restore .`, `clean -fd`, `rebase -i`, amending another author's commit.
8. **Test discipline:** Never add `@pytest.mark.skip`/`xfail` to make a number look better. If your change makes a *previously-passing* test fail, your change is wrong — revert it and re-think.
9. **If a fix would require (a) editing a forbidden file, (b) changing a risk/trading threshold, or (c) guessing at intended business behavior — SKIP the task, write one sentence on why, and move on.** Do not guess.
10. **One cluster at a time.** Fix → verify the cluster's named tests pass → run the wider module to check no regressions → commit (pathspec) → anti-skip gate → next.

## 2. ENVIRONMENT — copy/paste to start

```bash
cd /Users/nav/Documents/GitHub/floww
git fetch origin && git status --short            # confirm clean-ish; note any files other agents left dirty (don't touch them)
PY=backend/.venv/bin/python3
# baseline (this is the current truth; ~3 min):
cd backend && .venv/bin/python3 -m pytest -q --tb=no -p no:cacheprovider --ignore=tests/chaos --ignore=tests/e2e -rf 2>&1 | tail -45
cd /Users/nav/Documents/GitHub/floww
```
Notes: `--ignore=tests/chaos` (destructive: fills disk / memory) and `--ignore=tests/e2e` (needs a browser) — never run those two dirs. MongoDB should be up (`lsof -ti :27017`); DB tests need it.

---

## TASK 1 — obsidian_sync (10 failures) · HIGH confidence, do first

**Files:** Modify `backend/scripts/obsidian_sync.py` · Test `backend/tests/services/test_obsidian_sync.py`

**Failing tests:** all 10 in `test_obsidian_sync.py` (TestSyncDirection, TestConflictResolution, TestFrontmatterPreservation, TestDryRun, TestSkipFiles).

**Root cause (already diagnosed):** `ObsidianSync.sync_all()` calls four methods that are never defined on the class: `self.get_obsidian_path`, `self.sync_file`, `self.get_claude_path`, `self.save_log`. Every failing test invokes `sync_all()` → `AttributeError`.

- [ ] **Step 1 — see them fail:**
  `cd backend && .venv/bin/python3 -m pytest tests/services/test_obsidian_sync.py -q -p no:cacheprovider 2>&1 | tail -8` → expect 10 failed.
- [ ] **Step 2 — read** `backend/scripts/obsidian_sync.py` in full and the test file. Confirm which existing helpers/attributes exist (`self.vault_dir`, `self.memory_dir`, `self.state`, `self.conflicts`, `self.changes`, `self.log`, `self.dry_run`, `FILE_MAPPING`, `REVERSE_MAPPING`, `file_hash`, `file_mtime`, `extract_body`, `_convert_to_obsidian`, `_convert_to_claude`). **Adjust the patch below to match the ACTUAL names you find** — do not assume.
- [ ] **Step 3 — implement the four methods** inside `ObsidianSync` (insert before `sync_all`). Candidate (verify names against Step 2):
  ```python
      def get_obsidian_path(self, claude_name):
          mapped = FILE_MAPPING.get(claude_name)
          return self.vault_dir / (mapped if mapped else claude_name)

      def get_claude_path(self, obsidian_name):
          mapped = REVERSE_MAPPING.get(obsidian_name)
          return self.memory_dir / (mapped if mapped else obsidian_name)

      def save_log(self):
          if self.dry_run or not self.changes:
              return
          try:
              self.log_file.write_text("\n".join(self.changes) + "\n")
          except Exception:
              pass

      def sync_file(self, src, dst, key):
          src_hash, dst_hash = file_hash(src), file_hash(dst)
          last_hash = self.state.get_last_hash(key)
          new_content = self._convert_to_obsidian(src)
          if not dst.exists():
              if not self.dry_run:
                  dst.write_text(new_content)
              self.log(f"CREATE: {dst.name}")
              self.state.update(key, src_hash, file_mtime(src))
              return
          src_changed = src_hash != last_hash and last_hash != ""
          dst_changed = dst_hash != last_hash and last_hash != ""
          if src_changed and dst_changed:
              winner = "src" if file_mtime(src) >= file_mtime(dst) else "dst"
              self.conflicts.append({"file": key, "winner": winner})
              self.log(f"CONFLICT: {key} -> {winner} won", "warning")
              if winner == "src" and not self.dry_run:
                  dst.write_text(new_content)
              self.state.update(key, file_hash(dst), file_mtime(dst))
              return
          if extract_body(new_content) != extract_body(dst.read_text()):
              if not self.dry_run:
                  dst.write_text(new_content)
              self.log(f"UPDATE: {dst.name}")
          self.state.update(key, src_hash, file_mtime(src))
  ```
- [ ] **Step 4 — run until green**, iterating on the method bodies to match each test's assertions:
  `.venv/bin/python3 -m pytest tests/services/test_obsidian_sync.py -q -p no:cacheprovider 2>&1 | tail -6` → target `10 passed`.
- [ ] **Step 5 — commit + gate** (pathspec):
  ```bash
  cd /Users/nav/Documents/GitHub/floww
  git commit -m "fix(round-10): implement ObsidianSync.sync_file/get_*_path/save_log (10 tests)" -- backend/scripts/obsidian_sync.py
  git pull --rebase --autostash origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep "implement ObsidianSync"
  ```
**Done when:** `test_obsidian_sync.py` shows `10 passed` and the grep finds your commit on origin.

---

## TASK 2 — Route ordering: catch-all shadowing (3 endpoints) · HIGH confidence

**Files:** `backend/routes/data_providers.py`, `backend/routes/trinity.py`, `backend/routes/anomaly.py`

**Root cause:** a 1-segment catch-all `@router.get("/{ticker}")` is declared BEFORE literal 1-segment routes, so FastAPI matches e.g. `/api/data/status` to `{ticker="status"}` and the literal route is unreachable.

- [ ] **Step 1 — verify the bug** for each file by listing decorator order:
  `grep -nE '@router\.(get|post)\("' backend/routes/data_providers.py` (and trinity.py, anomaly.py). Confirm `/{ticker}` appears before the literals (`/status`,`/health` in data_providers; `/align` in trinity; `/ensemble*` in anomaly).
- [ ] **Step 2 — reorder:** move each literal route's function block to ABOVE the `@router.get("/{ticker}")` block. (Cut the whole `@router.get("/status") ... def get_data_status(): ...` block and paste it before the `/{ticker}` route. Pure move, no logic change.)
- [ ] **Step 3 — verify import + a smoke test** still pass:
  `cd backend && .venv/bin/python3 -c "import routes.data_providers, routes.trinity, routes.anomaly; print('ok')"`
  `.venv/bin/python3 -m pytest tests/ -k "data_provider or trinity or anomaly" -q --tb=line -p no:cacheprovider --ignore=tests/chaos --ignore=tests/e2e 2>&1 | tail -5`
- [ ] **Step 4 — commit + gate** (pathspec, the 3 files):
  ```bash
  git commit -m "fix(round-10-routes): move literal routes before /{ticker} catch-all (status/health/align/ensemble reachable)" -- backend/routes/data_providers.py backend/routes/trinity.py backend/routes/anomaly.py
  git pull --rebase --autostash origin main && git push origin main && git fetch origin && git log origin/main --oneline -1 | grep "literal routes before"
  ```
**Done when:** imports succeed, no new failures, commit on origin. (If there is no test for these endpoints, that's fine — the fix is structurally correct; do not invent tests.)

---

## TASK 3 — `/api/performance/stats` double-prefix 404 · HIGH confidence

**Files:** `backend/routes/admin.py`, `backend/routes/llm.py` · Test `backend/tests/routes/test_admin_auth_extra.py`

**Root cause:** these two routers bake absolute `/api/...` into their decorators AND `server.py` mounts them with `prefix="/api"` → live path becomes `/api/api/...`. (The OTHER routers use relative paths and are correct — do NOT touch them or `server.py`.)

- [ ] **Step 1 — confirm:** `grep -nE '@router\.(get|post)\("/api/' backend/routes/admin.py backend/routes/llm.py` — every decorator that starts with `/api/` is wrong.
- [ ] **Step 2 — make decorators relative** in `admin.py` and `llm.py` only: change each `@router.get("/api/X")` → `@router.get("/X")`. (server.py's `prefix="/api"` then yields the correct `/api/X`.)
- [ ] **Step 3 — verify:** `cd backend && .venv/bin/python3 -c "import routes.admin, routes.llm; print('ok')"` then run any admin/perf test: `.venv/bin/python3 -m pytest tests/routes/test_admin_auth_extra.py -q --tb=line -p no:cacheprovider 2>&1 | tail -5`.
- [ ] **Step 4 — commit + gate** (pathspec: admin.py, llm.py). Subject: `fix(round-10-routes): admin/llm decorators relative (kill /api/api double-prefix)`.
**Done when:** imports ok, the path is `/api/performance/stats` (single), commit on origin.

---

## TASK 4 — `llm.py` 3 dead endpoints (500s) · MEDIUM

**Files:** `backend/routes/llm.py` (and `backend/server.py` ONLY if you implement handlers there — but server.py is heavily shared; prefer the route-local option).

**Root cause:** `routes/llm.py` lazily imports `llm_analyze_trade_handler`, `llm_generate_briefing_handler`, `get_llm_providers` from `server` — none exist → every call 500s. There is a real service at `backend/services/llm.py` (`LLMService`, `get_llm_service`, `analyze_trade_with_llm`).

- [ ] **Step 1 — read** `routes/llm.py` and `services/llm.py`. Decide: rewire the 3 routes to call the real `services/llm.py` functions, OR (if the service can't satisfy them) return a clean `503 {"detail": "LLM not configured"}` instead of crashing. **Do not invent business logic.**
- [ ] **Step 2 — implement** the chosen option in `routes/llm.py` only.
- [ ] **Step 3 — verify import + (if a test exists) run it.** At minimum `cd backend && .venv/bin/python3 -c "import routes.llm; print('ok')"`.
- [ ] **Step 4 — commit + gate** (pathspec: routes/llm.py). Subject: `fix(round-10-routes): wire llm endpoints to services.llm (no more import-500s)`.
**Done when:** the 3 endpoints no longer reference undefined names; import ok; commit on origin.

---

## TASK 5 — `test_fallback_responses` (4) + `test_api` shape (4) · MEDIUM, investigate

**Failing tests:**
- `tests/routes/test_fallback_responses.py::TestFallbackResponses::{test_implied_pdf_external_error_returns_200, test_movers_error_returns_200_with_empty_results, test_history_error_returns_200_with_empty_snapshots, test_degraded_response_has_required_fields}`
- `tests/test_api.py::{test_advanced_spy, test_hedge_impulse_spy, test_pressure_cloud_spy, test_charm_integral_spy}` (assert keys `implied_pdf` / `curve` / `stability_zones` / `total_charm_to_close` present in the response).

- [ ] **Step 1 — for ONE test at a time**, run with `--tb=short` and read the assertion + the route it hits. Determine whether the **endpoint** omits the key/contract (source bug → fix the route to include it / degrade to 200 with the documented shape) or the **test** encodes a stale contract (then it's a stale-test; leave it and note for Nav — do NOT delete/skip it).
- [ ] **Step 2 — fix the route** in `backend/routes/*.py` to honor the degraded-response contract the test asserts (return HTTP 200 with the required keys even on upstream error). Keep changes minimal and route-local.
- [ ] **Step 3 — run the cluster green:** `.venv/bin/python3 -m pytest tests/routes/test_fallback_responses.py tests/test_api.py -q --tb=line -p no:cacheprovider 2>&1 | tail -8`.
- [ ] **Step 4 — commit + gate** (pathspec: only the route files you changed). Subject: `fix(round-10-routes): degraded-response contract (fallback + api shape tests)`.
**Done when:** the named tests pass OR you've documented (1-line each) which are stale-test contracts needing Nav's decision.

---

## TASK 6 — `test_microstructure_math::TestNodeLifecycle` (6) · MEDIUM, investigate

**Failing tests:** the 6 `TestNodeLifecycle` tests in `tests/services/test_microstructure_math.py` (spot_near_node→active, tap→tapped, full_lifecycle, tracker creates/tracks, detects taps, expired removed).

- [ ] **Step 1 — run with `--tb=short`**, read the test class fixture + the node-lifecycle source it imports (grep the import). All 6 fail together → likely one shared bug (a state-transition threshold, a missing transition, or a renamed method/attribute).
- [ ] **Step 2 — fix the source** to satisfy the transition contract the tests encode. (This is mechanical state-machine logic, not business judgment — safe to fix.)
- [ ] **Step 3 — green:** `.venv/bin/python3 -m pytest tests/services/test_microstructure_math.py -q --tb=line -p no:cacheprovider 2>&1 | tail -6`.
- [ ] **Step 4 — commit + gate** (pathspec). Subject: `fix(round-10): node lifecycle transitions (microstructure)`.
**Done when:** the 6 pass (or a precise note on which remain and why).

---

## TASK 7 — `test_causal_inference` (4) · LOW priority, only if time

**Failing tests:** `tests/services/test_causal_inference.py::{TestBackdoorCriterion::test_minimal_adjustment_set, TestDoCalculus::test_interventional_mean, TestCausalEffectEstimator::test_auto_selects_backdoor, TestCausalEffectEstimator::test_iv_method}`.

- [ ] **Step 1 — `--tb=short`**, read test + source. This is numerical/graph math — if the fix requires changing the *intended* statistical method (not just a bug), SKIP and note it. If it's a clear bug (wrong variable, off-by-one in adjustment set, sign), fix it.
- [ ] **Step 2 — green or skip-with-note.** Commit pathspec if fixed. Subject: `fix(round-10): causal_inference <specific bug>`.

---

## EXPLICITLY OUT OF SCOPE — do NOT attempt (leave for Nav/architect)

- **`tests/services/risk/test_gate.py` (9 failures).** The tests expect looser limits (e.g. a 1.6%-of-equity position approved) than the gate enforces (`RiskConfig.max_position_pct = 0.01` = 1%). Changing a live trading risk-control to pass a test is a **risk-policy decision for Nav**, not an agent fix. Skip entirely.
- **ML leakage retrain** (trainer scaler/feature-selection fit pre-split; fabricated `acc/(1-acc)` "Sharpe"). Judgment-heavy ML work — separate track.
- **`tests/services/test_greeks_api.py::...latency...` and `tests/perf/test_p99_latency.py`** — perf/latency, likely machine-dependent/flaky. Skip unless trivially obvious.

---

## FINAL — report honestly at the end of your run

Run the full baseline one more time and paste the real summary line:
```bash
cd backend && .venv/bin/python3 -m pytest -q --tb=no -p no:cacheprovider --ignore=tests/chaos --ignore=tests/e2e 2>&1 | tail -3
```
Then write a short status to `docs/ROUND10_DEEPSEEK_STATUS_2026-05-30.md` (pathspec-commit it): per task — DONE (with the `N passed` evidence) / PARTIAL / SKIPPED (+ one-line reason). Confirm the final failure count vs the 39 you started with. **Do not round up. Do not claim a task done without the pytest line proving it.**

Context for you (verified by the architect, 2026-05-30): the suite collects 2636 tests; commits `81e64c0`→`88f274c` already fixed collection + ~21 failures; full findings in `docs/ROUND10_ARCHITECT_AUDIT_2026-05-30.md`.
