# floww/DVT Swarm Coordination Pack — 2026-06-20

> **Owner:** Claude Code (main session). **Workers:** freebuff (DeepSeek-Pro) + 3 Hermes (OWL-Alpha). Nav launches them; this pack assigns lanes + guardrails so they stop colliding.
> **Why this exists:** this session every agent (a) committed with `git commit --no-verify`, (b) "verified" by `grep bundle.js` without ever rendering the UI, (c) edited the frozen `App.js` concurrently, and one is editing the **model-locked GEX dual-scale path**. This pack stops all four failure modes.

---

## SHARED GUARDRAILS — apply to ALL workers (read first, every round)

1. **NEVER `git commit --no-verify`.** It is a CLAUDE.md *forbidden* op. The pre-commit hook currently errors only because **`ruff` is not installed in `backend/.venv`** — the FIRST worker to hit it must fix the gate, not bypass it:
   ```bash
   backend/.venv/bin/pip install ruff
   backend/.venv/bin/ruff check backend/scripts/memory_mesh.py   # then fix any real findings
   ```
   After that the hook runs clean and `--no-verify` is never needed again.
2. **Pathspec commits only.** `git add <exact files you changed>` — NEVER `git add -A` / `git add .`. The tree has 20+ files dirty from other agents right now; `add -A` would commit their half-done work.
3. **Lane separation (anti-clobber).** Only the files in YOUR lane below. `frontend/src/App.js` is **architect-frozen** — only **ONE** worker (Hermes-FE-1) may edit it per round; everyone else proposes a diff in their report for the owner to apply.
4. **Render-verify before claiming done.** `curl bundle.js | grep Component` proves it's *bundled*, NOT that it *renders*. The PWA needs an auth token the headless browser doesn't have. To verify UI: ask Nav to look at the PWA, OR `cd frontend && npx eslint src/<file>` + a production `npm run build` (must exit 0). No "verified ✓" without pasted evidence.
5. **GEX dual-scale is model-locked — keep the oracle green.** After ANY edit under `backend/services/gex_*`, `bs_greeks.py`, `advanced_analytics.py`, `app/backend/spy_data.py`, or `domain/greek_scalers.py`:
   ```bash
   backend/.venv/bin/python3 -m pytest tests/services/test_gex_aggregator_oracle.py -q   # MUST stay 12 passed
   ```
   Do **NOT** numerically unify the S² (display) and S¹ (feature) scales — that retrains every frozen GBM. New scaler helpers must be **additive** (used by display only), proven by the oracle staying green.
6. **No fabrication.** Real SHAs only (`git log origin/main --oneline | grep <subject>`). No invented metrics (the Sharpe-3.66 / 100%-win-rate numbers are fabricated — never propagate).
7. **Anti-skip gate after every commit:** `git pull --rebase origin main && git push origin main` → `git fetch origin && git log origin/main --oneline -1 | grep <subject>`. Empty grep = push failed = STOP.

---

## LANE 1 — freebuff (DeepSeek-Pro): backend quant / GEX hardening

**Execute:** `docs/superpowers/plans/2026-06-20-freebuff-decoder-hardening-60h.md` (already authored — TDD, failing-test-first).
**In-bounds:** `backend/services/numba_greeks.py`, `liquidity_metrics.py`, `order_router.py`, `server.py` (MONGO_URL/CORS/replay-dup), `backend/domain/*` (vpin, almgren_chriss, greek_scalers), `backend/tests/**`.
**OUT OF BOUNDS / STOP-AND-ASK:**
- The `dollar_gex()`/`greek_scalers` work you've started is **only acceptable if the golden oracle stays 12-passed and the S¹ feature path (`gex_history.py`, `services/ml/gex_inference.py`, `ml_realtime_features.py`) is byte-for-byte unchanged.** If your scaler refactor touches those, REVERT and report — it's the retrain trap.
- Do NOT edit frozen files (`services/ml/inference.py`, `dash_ui.py`, `conftest.py`, model artifacts) without Nav approval.
**First action this round:** install ruff (Guardrail 1) so the whole team's commit gate works.

## LANE 2 — Hermes-DVT: DVT learning content

**In-bounds:** DVT engine/strategy code in floww, and DVT *learning* content **only inside** `/Applications/Claude everything/dashboard.html` (the canonical Mission Control — extend the existing `DVT_CURRICULUM`/`DVT_QUIZ`).
**OUT OF BOUNDS:** Do **NOT** create new/standalone `*.html` dashboards or parallel DVT docs (this already happened — a stray `dvt_dashboard.html` was archived). All DVT learning extends the in-file curriculum. Paper-only; never wire live execution.

## LANE 3 — Hermes-FE-1: floww frontend (Heatseeker/Skylit visual — owns App.js this round)

**In-bounds:** `frontend/src/App.js` (you are the SOLE App.js editor this round), `frontend/src/components/DomHeatmap.jsx`, `MultiTickerHeatmap.jsx`, `VolumeProfileGrid.jsx`, `TrinityView.jsx`, `frontend/src/App.css`.
**Tasks:**
1. Remove the dead `import GridHeatmap from "./components/GridHeatmap"` at `App.js:8` (no longer used after DomHeatmap replaced it). `npx eslint src/App.js` must be clean.
2. **Render-verify the redesign with Nav** (Guardrail 4) — the DOM heatmap, Multi, Profile, and Trinity views were never visually confirmed. Get a screenshot/confirmation before marking done.
**OUT OF BOUNDS:** backend, `App.css` structural rewrites that Hermes-FE-2 needs.

## LANE 4 — Hermes-BE / floww backend (non-GEX)

**In-bounds:** backend routes/services NOT in freebuff's GEX lane — e.g. alerts, social_flow, retail_flow, morning_briefing, agent_hub. Coordinate with freebuff to avoid `server.py` collisions (one edits the router block at a time).
**OUT OF BOUNDS:** the GEX/greeks files (freebuff's lane), frozen files, frontend.

---

## OWNER (me) — verified this round
- Golden GEX oracle: **12 passed** on the live dirty tree → dual-scale invariant intact despite concurrent GEX edits.
- Hermes Heatseeker redesign: commits `b0c51ef`→`566e17c` real + pushed (local==origin); App.css braces balanced; 4 components on disk.
- Outstanding for owner: confirm new `domain/` modules (vpin/almgren/greek_scalers) pass their tests; reinforce this pack to the Hermes handoff doc.
