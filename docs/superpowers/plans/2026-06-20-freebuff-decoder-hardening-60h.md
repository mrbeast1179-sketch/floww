# freebuff — Confluence Decoder Hardening (60-Hour Work Prompt) Implementation Plan

> **For agentic workers (freebuff):** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking. You run in your own clone with shell/git/pytest — use them, with evidence.

**Goal:** Over ~60 hours, harden the Confluence Decoder (floww) backend by fixing *verified* correctness/silent-failure/security bugs under strict TDD — WITHOUT touching the model-locked GEX feature path, frozen files, or any live-execution code.

**Architecture:** FastAPI backend (`backend/`, port 8000) + React PWA (`frontend/`, port 3000) + Mongo (Motor) + DuckDB + frozen GBM models. You work one lane at a time, failing-test-first, pathspec commits, rebase-before-push, verify-on-origin after every commit.

**Tech Stack:** Python 3.12 (`backend/.venv/bin/python3`), pytest (asyncio auto), ruff (E,E722,F,W,I; ignore E501), React 18 / CRA / craco / jest, git.

---

## Global Constraints (copied verbatim from CLAUDE.md + architect audit — every task implicitly includes these)

**PRIME DIRECTIVE — read before anything:** Your last session you flagged the GEX `0.01` factor as a "100× bug" (review item #1) and started changing `0.01 → 0.0001`. **That was WRONG and you correctly self-reverted.** `gamma·OI·100·S²·0.01` IS the canonical SqueezeMetrics/SpotGamma Dollar-GEX convention (1% move). The existing test of record `backend/tests/services/ml/test_gex_inference_extra.py:184` asserts it. **Do not re-open this. Do not change any GEX numeric constant.**

1. **DUAL GEX SCALE IS INTENTIONAL — DO NOT "FIX" OR "UNIFY".** Two scales coexist by design:
   - `services/gex_aggregator.py` → **S²** (dollar-GEX, `spot²`) — DISPLAY only.
   - `services/gex_history.py` → **S¹** (`spot¹`) — ML features feeding **frozen** GBM models.
   - Relationship `display_net_gex == spot * feature_net_gex` is pinned by `tests/services/test_gex_aggregator_oracle.py`. Model-locked constants in `gex_history.py`: `_RISK_FREE = 0.045`, `_IV_FALLBACK = 0.20`.
   - **Unifying these = a retrain migration (re-backfill + retrain all production GBMs). OUT OF SCOPE. Touching it requires explicit architect (Nav) approval.**
   - This kills the `dollar_gex()` cross-17-file refactor your thinker proposed. See "REJECTED TASKS" below.

2. **FROZEN FILES — do not edit without explicit Nav approval (STOP and ask):**
   `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py`, all model artifacts (`*.joblib`, `*.pt`, `*_manifest.json`, `*_meta.json` under `backend/models/`), `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`, `frontend/src/App.js` (surgical-only, approval required).

3. **PAPER-ONLY. NEVER wire AI to live order execution.** The owner trades at a loss and is stressed; help via paper/sim only. The only reachable order path today is Alpaca **paper** (`ALPACA_BASE_URL = "https://paper-api.alpaca.markets"`). Any task that could make a live broker order reachable STOPS and asks Nav first.

4. **TDD is non-negotiable.** A test you write MUST fail before your fix and pass after. NEVER add `@pytest.mark.skip`/`xfail`/`it.skip()` to a previously-passing test. If your change makes a passing test fail, your change is WRONG — revert and find root cause.

5. **No fabrication.** No invented SHAs, no "tests pass" without the pasted output, no claiming a push landed without `git log origin/main`. Round 7's fabricated completion log is the negative-example floor. (Prior fabrications on this project: a fake `viridisColor()` claim, fabricated ML Sharpe > 10. Don't.)

6. **Multi-agent lane discipline** (Hermes/OWL-Alpha and DS-Pro may be in the same repo): commit with **pathspec** (`git add <exact files>`, never `git add -A`); `git pull --rebase origin main` before every push; stay in YOUR lane (the files in YOUR current task only).

7. **Forbidden git ops:** `push --force`/`--force-with-lease`, `commit --no-verify`, `commit --amend` on others' commits, `rebase --abort`, `reset --hard`, `checkout .`, `restore .`, `clean -fd`, `rebase -i`. To undo, ASK.

8. **Canonical clone only:** `/Users/nav/Documents/GitHub/floww`. If `pwd` doesn't end in `Documents/GitHub/floww`, STOP and re-cd.

9. **Commit style (mandatory):** HEREDOC subject `<type>(<scope>): <one-line>` + body with inline grep/pytest/curl evidence.

10. **Anti-skip gate after EVERY commit:** `git pull --rebase origin main && git push origin main` → `git fetch origin && git log origin/main --oneline -1 | grep <subject substring>`. Empty grep = push silently failed = STOP and investigate.

---

## Calibration: what you got RIGHT, WRONG, and MISSED last session

**RIGHT (keep doing):** self-reverting the GEX "fix" after web research; surveying all 17 GEX sites before acting; spawning a design thinker.

**WRONG (do not repeat):**
- Calling `0.01` a bug (it's the convention).
- Proposing to "fix" `app/backend/spy_data.py:113` (`spot*0.01`) and `services/heatseeker.py:927` (`gamma*oi*100` only) to "unify" scales. **These may be intentional** (heatseeker:927 cancels in a ratio; spy_data is a separate app surface). Unverified "consistency" edits to GEX scaling are exactly the dual-scale trap. → REJECTED unless Nav approves.
- Several "Critical" review items were speculative (you admitted in #7 you "hadn't yet read" the files claiming SABR/Hawkes/VPIN are missing). **Audit existence before claiming absence.**

**MISSED (the architect audit found these — they ARE real, adversarially verified against source):**
- `backend/services/numba_greeks.py:163` — `bs_delta_vec` hardcodes `r=0.0`; every sibling Greek uses the real `r`. Internally inconsistent delta.
- `backend/services/liquidity_metrics.py:36` — `KyleLambda.update()` guard `if len(self._returns) > 0:` is unreachable; `/api/liquidity/{ticker}/kyle` silently always returns `lambda=0`.
- `frontend/src/config/api.js:12` + `frontend/src/App.js:332` — `FlowAlertsPage` egresses the bearer token + ticker queries to external `https://api.alphapodtrading.com` when logged in, then swallows the failure in `catch{ /*noop*/ }`. Stale AlphaPod integration; should be removed.
- `backend/server.py:2810` and `:2997` — `replay_router` registered twice.
- `backend/services/order_router.py` — docstring says "Paper-trade order client" but it POSTs `BUY_TO_OPEN`/`SELL_TO_OPEN` to the **live** `https://api.schwabapi.com/trader/v1/.../orders`. Currently orphaned (instantiated only in tests), so latent — but a lying docstring is a paper-safety landmine.

> NOTE: the architect's audit workflow was cut short by a session usage limit; ~22 verification agents did not finish. Treat the Tier-1 list as the verified core, not the complete bug set. Phase 5 re-runs discovery.

---

## REJECTED TASKS (do NOT do these — they will break production or violate freezes)

- ❌ Change `0.01 → 0.0001` (or any GEX magnitude constant) anywhere. Not a bug.
- ❌ The cross-17-file `dollar_gex()/dollar_vex()` refactor that touches `gex_aggregator.py`, `gex_history.py`, `services/ml/gex_inference.py`, `ml_realtime_features.py`, `scripts/train_spy_ml.py`. These are the **model-locked S¹ feature path** — a pure-looking refactor still risks the golden oracle + retrains. Architect-approval-only.
- ❌ "Unify" `spy_data.py:113` / `heatseeker.py:927` GEX scales.
- ❌ Build NEW SABR / SVI / Hawkes / VPIN / Almgren-Chriss / 1D-CNN subsystems from scratch in this window (scope creep). You may AUDIT whether they already exist and write a findings doc (Phase 5), nothing more.
- ❌ Edit any frozen file (§2) without Nav approval.
- ❌ Any change that makes a live broker order reachable.

---

## File Structure (what this plan touches)

- `backend/services/numba_greeks.py` — fix delta `r`; **Test:** `backend/tests/services/test_numba_greeks_delta_r.py` (new)
- `backend/services/liquidity_metrics.py` — fix KyleLambda streaming guard; **Test:** `backend/tests/services/test_kyle_lambda_streaming.py` (new)
- `backend/server.py` — remove duplicate `replay_router` include; `MONGO_URL` env default; CORS tighten; exception-type leak; **Test:** `backend/tests/test_server_wiring.py` (new)
- `backend/services/order_router.py` — correct docstring + hard env-gate the live path; **Test:** `backend/tests/services/test_order_router_gate.py` (new)
- `frontend/src/config/api.js` — remove external AlphaPod fallback (App.js change is approval-gated)
- `backend/bs_greeks.py` (top-level only) — characterization tests (NOT numeric edits); **Test:** `backend/tests/test_bs_greeks_characterization.py` (new)
- `docs/superpowers/research/2026-06-20-decoder-subsystem-existence-audit.md` (new, Phase 5)

---

## Phase 0 — Setup & Calibration (≈2h, read-only, no code)

### Task 0: Establish baseline and internalize the guardrails

**Files:** none (read-only)

- [ ] **Step 1: Confirm location & freshness**
  Run: `cd /Users/nav/Documents/GitHub/floww && pwd && git fetch origin && git status --short && git log origin/main --oneline -3`
  Expected: path ends `Documents/GitHub/floww`; note any uncommitted drift before starting.

- [ ] **Step 2: Capture the test baseline (paste the real numbers)**
  Run: `cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -5`
  Record pass/fail counts. This is your regression floor — you must never lower it.

- [ ] **Step 3: Prove the GEX convention is NOT a bug (so you never re-open it)**
  Run: `cd backend && .venv/bin/python3 -m pytest tests/services/ml/test_gex_inference_extra.py -q 2>&1 | tail -3` and `.venv/bin/python3 -m pytest tests/services/test_gex_aggregator_oracle.py -q 2>&1 | tail -3`
  Expected: PASS. These pin `0.01` and `display = spot * feature`. If they pass, the convention is correct — stop thinking about it.

- [ ] **Step 4: Read the freezes** — open CLAUDE.md "Forbidden files" + "Dual GEX scale" sections. Do not edit anything listed there in this plan.

---

## Phase 1 — Verified backend correctness bugs (≈14h)

### Task 1: Fix `bs_delta_vec` risk-free-rate inconsistency

**Files:**
- Modify: `backend/services/numba_greeks.py:163`
- Test: `backend/tests/services/test_numba_greeks_delta_r.py` (create)

**Interfaces:**
- Consumes: `_d1d2(S, K, T, sigma, r, q)` (line 68), `bs_delta_vec(S, K, T, sigma, r=0.05, q=0.0)` (line 137).
- Produces: delta values consistent with `r` used by gamma/vanna/charm.

- [ ] **Step 0 (verify-before-fix — MANDATORY):** confirm delta is NOT a locked model feature.
  Run: `cd backend && grep -rn "delta" services/ml/ scripts/ | grep -iE "feature|FEATURES|columns" | head`
  If `delta` appears in any frozen model's feature list → STOP, this becomes a characterization-only task, escalate to Nav. If absent (expected), proceed.

- [ ] **Step 1: Write the failing test** (FD oracle: delta from numba path must match a finite-difference of price w.r.t. S, computed with the SAME r):
```python
# backend/tests/services/test_numba_greeks_delta_r.py
import numpy as np
from services.numba_greeks import bs_delta_vec, bs_call_price_vec

def test_delta_uses_real_r_matches_fd():
    S, K, T, sig, r, q = 580.0, np.array([580.0]), np.array([0.25]), np.array([0.18]), 0.045, 0.0
    h = 1e-3
    p_up = bs_call_price_vec(S + h, K, T, sig, r, q)[0]
    p_dn = bs_call_price_vec(S - h, K, T, sig, r, q)[0]
    fd_delta = (p_up - p_dn) / (2 * h)
    analytic = bs_delta_vec(S, K, T, sig, r, q)[0]
    assert abs(analytic - fd_delta) < 1e-3, f"delta {analytic} != FD {fd_delta} (r ignored?)"
```

- [ ] **Step 2: Run test to verify it FAILS**
  Run: `cd backend && .venv/bin/python3 -m pytest tests/services/test_numba_greeks_delta_r.py -v`
  Expected: FAIL (analytic delta uses r=0, FD uses r=0.045 → mismatch).

- [ ] **Step 3: Minimal fix** — at `numba_greeks.py:163` change `_d1d2(S, K[i], T[i], sigma[i], 0.0, q)` to `_d1d2(S, K[i], T[i], sigma[i], r, q)`. Add `r` to the `bs_delta_vec` docstring Args (match gamma's docstring style).

- [ ] **Step 4: Run test to verify it PASSES**, then the neighbours don't regress:
  Run: `cd backend && .venv/bin/python3 -m pytest tests/services/test_numba_greeks_delta_r.py tests/services/test_reference_parity.py tests/services/test_greek_aggregator.py -q 2>&1 | tail -5`
  Expected: all PASS.

- [ ] **Step 5: Commit** (pathspec only):
```bash
git add backend/services/numba_greeks.py backend/tests/services/test_numba_greeks_delta_r.py
git commit -m "$(cat <<'EOF'
fix(greeks): bs_delta_vec was ignoring r (hardcoded 0.0) — use real risk-free rate

bs_delta_vec passed 0.0 as r to _d1d2 while gamma/vega/vanna/charm/vomma/zomma/theta
all pass the real r. delta's d1 used drift (0 - q); curvature/vol Greeks used (0.045 - q).
Now consistent. FD oracle test added (was unguarded — fd_oracle only covered top-level bs_greeks).

Verification:
$ .venv/bin/python3 -m pytest tests/services/test_numba_greeks_delta_r.py -q 2>&1 | tail -1
1 passed
$ .venv/bin/python3 -m pytest tests/services/test_reference_parity.py tests/services/test_greek_aggregator.py -q 2>&1 | tail -1
<paste real line>
EOF
)"
```
  Then the anti-skip gate (§10).

### Task 2: Fix `KyleLambda` streaming update (always-zero lambda)

**Files:**
- Modify: `backend/services/liquidity_metrics.py:34-42`
- Test: `backend/tests/services/test_kyle_lambda_streaming.py` (create)

**Interfaces:**
- Consumes: `KyleLambda.update(price, volume, sign)`, `KyleLambda.compute()`. Called by `routes/liquidity.py:80` (POST `/api/liquidity/{ticker}/kyle`).
- Produces: non-zero lambda after ≥4 streaming updates with non-trivial price moves.

- [ ] **Step 1: Write the failing test:**
```python
# backend/tests/services/test_kyle_lambda_streaming.py
from services.liquidity_metrics import KyleLambda

def test_streaming_update_accumulates_and_lambda_nonzero():
    k = KyleLambda(window=50)
    prices = [100, 101, 99, 102, 98, 103, 97]
    for i, p in enumerate(prices):
        k.update(price=float(p), volume=1000.0, sign=1 if i % 2 == 0 else -1)
    assert k.compute() != 0.0, "streaming Kyle lambda stuck at 0 — guard unreachable"
```

- [ ] **Step 2: Run → FAIL** (`compute()` returns 0.0 because `_returns` never grows).
  Run: `cd backend && .venv/bin/python3 -m pytest tests/services/test_kyle_lambda_streaming.py -v`

- [ ] **Step 3: Minimal fix** — at `liquidity_metrics.py:36` change the guard from `if len(self._returns) > 0:` to `if hasattr(self, "_last_price") and self._last_price is not None:` (initialize `self._last_price = None` in `__init__` if not present). The body that appends the return/signed-volume now runs from the 2nd update onward.

- [ ] **Step 4: Run → PASS** + batch path unchanged:
  Run: `cd backend && .venv/bin/python3 -m pytest tests/services/test_kyle_lambda_streaming.py tests/services/test_microstructure_math.py -q 2>&1 | tail -3`

- [ ] **Step 5: Commit** (pathspec `liquidity_metrics.py` + the new test) with curl evidence:
```bash
# (optional live proof if backend running)
# curl -s -XPOST localhost:8000/api/liquidity/SPY/kyle -d '{"price":101,"volume":1000,"sign":1}' ...
```
  Then anti-skip gate.

### Task 3: Remove duplicate `replay_router` registration

**Files:** Modify `backend/server.py` (remove the second include at `:2997`, keep `:2810`); Test `backend/tests/test_server_wiring.py` (create).

- [ ] **Step 1: Failing test** — assert each router object is included at most once:
```python
# backend/tests/test_server_wiring.py
def test_no_duplicate_router_registration():
    import server
    seen = {}
    for r in server.app.router.routes:
        key = getattr(r, "path", None)
        if key:
            seen[key] = seen.get(key, 0) + 1
    dupes = {p: n for p, n in seen.items() if n > 1 and p.startswith("/api/replay")}
    assert not dupes, f"duplicate routes: {dupes}"
```

- [ ] **Step 2: Run → FAIL** (replay paths counted twice).
- [ ] **Step 3: Fix** — delete the second `# ============ Replay Route ============` block (the `import` + `app.include_router(replay_router ...)` at `server.py:2996-2997`). Keep the first at `:2810`.
- [ ] **Step 4: Run → PASS** + `pytest tests/test_api.py -q` no regression.
- [ ] **Step 5: Commit** + anti-skip gate.

---

## Phase 2 — Security / paper-safety (≈12h, escalation-gated where noted)

### Task 4: Quarantine the live-Schwab `order_router.py` (paper-safety landmine)

**Files:** Modify `backend/services/order_router.py` (docstring + env gate only); Test `backend/tests/services/test_order_router_gate.py` (create).

- [ ] **Step 1: Failing test** — submitting an order without the explicit opt-in env var must be refused before any network call:
```python
# backend/tests/services/test_order_router_gate.py
import pytest
from services.order_router import OrderRouter

@pytest.mark.asyncio
async def test_live_orders_disabled_by_default(monkeypatch):
    monkeypatch.delenv("FLOWW_ENABLE_LIVE_SCHWAB", raising=False)
    r = OrderRouter("acct-123")
    res = await r.submit_order({"ticker": "SPY", "side": "buy", "qty": 1, "order_type": "limit"})
    assert res["status"] in ("rejected", "error")
    assert "live" in str(res.get("reason", "")).lower() or "disabled" in str(res.get("reason", "")).lower()
```

- [ ] **Step 2: Run → FAIL** (today it tries to refresh a token / POST live).
- [ ] **Step 3: Fix** — (a) correct the module docstring: it targets the **LIVE** Schwab Trader API, not paper. (b) At the top of `submit_order`, add:
```python
import os
if os.getenv("FLOWW_ENABLE_LIVE_SCHWAB") != "1":
    return {"status": "rejected", "reason": "live Schwab orders disabled (paper-only). Set FLOWW_ENABLE_LIVE_SCHWAB=1 to enable."}
```
  Do NOT remove the file (tests depend on it). Do NOT add a route that calls it.

- [ ] **Step 4: Run → PASS** + existing `tests/services/test_order_router.py` (update any test that assumed an unguarded submit to set the env var explicitly — these are YOUR tests, allowed).
- [ ] **Step 5: ESCALATE before committing anything that changes execution semantics** — post a one-paragraph note to Nav: "order_router live-Schwab path now gated behind `FLOWW_ENABLE_LIVE_SCHWAB`; confirm you want it kept (gated) vs deleted." Commit only after acknowledgement.

### Task 5: `MONGO_URL` startup-crash + env hardening

**Files:** Modify `backend/server.py` (the `MONGO_URL = os.environ["MONGO_URL"]` line); Test `backend/tests/test_server_wiring.py` (extend).

- [ ] **Step 1: Failing test** — importing config helper without `MONGO_URL` set should fall back, not `KeyError`. (Wrap the lookup in a small `get_mongo_url()` helper so it's testable.)
- [ ] **Step 2: Run → FAIL.**
- [ ] **Step 3: Fix** — `MONGO_URL = os.getenv("MONGO_URL", "mongodb://localhost:27017")` + a startup log line if the default is used.
- [ ] **Step 4: Run → PASS** + `pytest tests/test_api.py -q`.
- [ ] **Step 5: Commit + anti-skip gate.**

### Task 6: CORS + exception-type leak (config review, not behavior break)

**Files:** Modify `backend/server.py` CORS middleware + global exception handler.

- [ ] **Step 1:** Read current CORS config. If `allow_origins=["*"]` AND credentials are allowed, that's invalid+unsafe. Failing test: assert configured origins come from an env allowlist (default `http://localhost:3000`).
- [ ] **Step 2–4:** Replace `*` with `os.getenv("CORS_ORIGINS","http://localhost:3000").split(",")`; in the global handler, stop returning `type(exc).__name__` to the client (log it server-side only). Run `pytest tests/test_api.py` — **must not** break the PWA's own origin. If unsure whether the PWA uses a non-localhost origin, STOP and ask Nav (don't lock yourself out).
- [ ] **Step 5: Commit + anti-skip gate.**

---

## Phase 3 — Frontend AlphaPod egress (≈6h, App.js is approval-gated)

### Task 7: Remove external `api.alphapodtrading.com` data egress

**Files:** Modify `frontend/src/config/api.js`; `frontend/src/App.js:332` (FROZEN — approval required).

- [ ] **Step 1: Document the defect** for Nav with exact lines: `config/api.js:12` external fallback + `App.js:332` `const base = token ? ALPHAPOD_API : API` → logged-in users send `Authorization: Bearer <local dev token>` + ticker to a third-party domain, then `catch{ /*noop*/ }` hides the failure (alerts silently empty when logged in).
- [ ] **Step 2: Safe (non-frozen) part now** — in `config/api.js`, change the fallback so it can never point off-box by default: `export const ALPHAPOD_API = process.env.REACT_APP_API_URL || BACKEND_URL + "/api";` (or delete `ALPHAPOD_API` if Nav approves the App.js edit too).
- [ ] **Step 3: ESCALATE the App.js one-liner** — propose the surgical patch `const base = API;` (drop the external branch) and the `catch` → `catch(e){ console.warn('alerts fetch failed', e); }`. Apply ONLY after Nav approves (App.js is frozen). Frontend jest is ~35/37 red pre-existing (CSS mapper) — do not "fix" that; verify your change compiles via `cd frontend && npx eslint src/config/api.js`.
- [ ] **Step 4: Commit** (pathspec; config/api.js separately from any approved App.js change) + anti-skip gate.

---

## Phase 4 — Greeks characterization safety net (≈8h, NO numeric edits)

### Task 8: Pin current Greek values with Hull-table + FD characterization tests

**Files:** Create `backend/tests/test_bs_greeks_characterization.py`. Do NOT modify `bs_greeks.py` numerics.

- [ ] **Step 1:** Write tests asserting top-level `bs_greeks` gamma/vega/vanna/charm/vomma/zomma against published Hull-table values (tolerance 1e-3) AND a finite-difference oracle. These LOCK current behavior so any future refactor (yours or another agent's) that drifts a Greek fails loudly. (Addresses the real gap behind your review #5/#20: `_mask_zero` silently returns 0.0 — add one test that a guard-clause input `T<=0` returns 0.0 but a genuinely-bad input is distinguishable.)
- [ ] **Step 2: Run → all PASS on current code** (characterization, so they pass immediately; if any FAILS you've found a real Greek bug — STOP, report to Nav, do not "fix" silently).
- [ ] **Step 3: Commit** the test file + anti-skip gate.

---

## Phase 5 — Honest subsystem existence audit (≈10h, read-only, produces a doc)

### Task 9: Verify which "advertised" subsystems actually exist before anyone builds or trims

**Files:** Create `docs/superpowers/research/2026-06-20-decoder-subsystem-existence-audit.md`.

- [ ] **Step 1:** For each claimed subsystem (SABR/SVI, Hawkes, VPIN, Almgren-Chriss, Kyle λ, 1D-CNN anomaly), grep the repo and record file:line where it exists OR "ABSENT".
  Run e.g.: `cd backend && grep -rilE "sabr|svi|hawkes|vpin|almgren|kyle|autoencoder|conv1d|1dcnn" --include='*.py' | sort -u`
- [ ] **Step 2:** For each "exists", note whether it's wired to a route + tested. For each "absent", note where the README/docs over-claim it.
- [ ] **Step 3:** Write the doc as a table (subsystem | status | file:line | wired? | tested? | doc-claim location). **Do not build anything.** End with a prioritized recommendation for Nav (ship vs trim docs). Commit the doc + anti-skip gate.

---

## Phase 6 — Remaining-bug re-discovery (≈8h)

### Task 10: Re-run the cut-short audit dimensions

**Files:** none (analysis) → individual fix tasks become new mini-tasks following the Task-1 template.

- [ ] **Step 1:** The architect's audit lost ~22 verification agents to a usage limit. Re-review these dimensions for silent failures / `except: pass` / endpoints returning `{"error":...}` with HTTP 200: `routes/admin.py`, `routes/ml_api.py`, `routes/predictive.py`, `routes/gemini.py`, `routes/alerts.py`, `services/correlation_engine.py`, `services/paper_trader.py`, `services/social_flow_pipeline.py`, `services/health_monitor.py`.
- [ ] **Step 2:** For each real, reproducible bug: write a failing test → minimal fix → passing test → commit → anti-skip gate (the Task-1 loop). For each suspected-but-unconfirmed: log it in a findings doc, DON'T fix on speculation.
- [ ] **Step 3:** Keep `pytest -q --tb=no` at or above the Phase-0 baseline at all times.

---

## Self-Review (architect ran this against the audit)

- **Coverage:** every Tier-1 verified bug (delta-r, Kyle, replay-dup, order_router, AlphaPod egress, MONGO_URL) has a task. ✓
- **Placeholders:** none — each code step shows the code/command. ✓
- **Frozen-file safety:** App.js + numerics are approval-gated, not edited blind. ✓
- **The trap:** the GEX/dual-scale refactor is explicitly REJECTED, with the green oracle test as proof it's not a bug. ✓
- **Type consistency:** `bs_delta_vec(S,K,T,sigma,r,q)`, `KyleLambda.update(price,volume,sign)/compute()`, `OrderRouter.submit_order(intent)` names match source. ✓

## Execution Handoff

Plan saved to `docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md`. freebuff should execute **Phase 0 → 6 in order**, one task at a time, failing-test-first, committing per task with the anti-skip gate. STOP-and-ask gates: Task 4 (execution semantics), Task 6 (CORS origin), Task 7 (App.js frozen edit), and any GEX/model-feature/frozen-file temptation.
