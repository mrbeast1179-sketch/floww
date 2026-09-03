# Lane Map — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

## Rule

Four agents work this repo concurrently. `frontend/src/App.js` and all of `backend/` are owned by other lanes unless explicitly overridden. Agent 3 is PROPOSAL_ONLY by default.

## Lane assignments

### Agent 1 — Architect / Orchestrator / Gatekeeper
**Owns:**
- `.planning/phases/phase-9-academy-flow/WAVE_STATE.md`
- `.planning/phases/phase-9-academy-flow/DECISIONS.md`
- `.planning/phases/phase-9-academy-flow/CONTRACTS.md`
- `.planning/phases/phase-9-academy-flow/GATE_PLAN.md`
- `.planning/phases/phase-9-academy-flow/RISK_REGISTER.md`
- `.planning/phases/phase-9-academy-flow/CONTRACT_REQUESTS.md`
- `.planning/phases/phase-9-academy-flow/INTEGRATION_CHECKLIST.md`
- `.planning/phases/phase-9-academy-flow/reports/agent1-architect.md`

**Forbidden:** product code, `frontend/src/App.js`, `backend/`, any lane's deliverables.

**Deliverables:** lane map, pathmap, decisions, contracts, wave state, gate plan, risk register, contract request triage, integration checklist, architect report.

**Commit prefix:** `phase9(arch):`

### Agent 2 — Frontend Flowseeker / Pulse / Scanner / Tracker / Filters
**Owns:**
- `frontend/src/components/flowseeker/**` (new components, hooks, fixtures, tests)
- `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` (owned by this lane per current repo state — only file in flowseeker dir)
- `frontend/src/components/flowseeker/FlowseekerProBlademap.css`
- `frontend/src/components/flowseeker/scanLogic.js` + `scanLogic.test.js` (if it exists as a separate module)
- `frontend/src/config/api.js` (read-only; does not edit unless contract requires)
- `frontend/__tests__/**` flowseeker-specific tests
- `.planning/phases/phase-9-academy-flow/reports/agent2-frontend.md`
- `.planning/phases/phase-9-academy-flow/reports/agent2-pathmap.md`

**Discovered paths (2026-09-03):**
- `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` (1954 lines — the only flowseeker component currently in the repo; contains Pulse tape, Scanner fallback, mapPublicChainToRows, aggregatePulse, pulseScore10, pulseSignal, pulseHedge, pulseBadges, DEFAULT_RULES with SCORE 92 / WHALE $25M / SIGMA 6σ / follow 3d, ALERT_NOISE_CAP_H=4, FR filter stubs)
- `frontend/src/components/flowseeker/FlowseekerProBlademap.css` (scoped .fsb-* classes)
- `frontend/src/components/flowseeker/FlowseekerProBlademap.test.jsx`
- `frontend/src/components/flowseeker/BlademapActiveMount.test.jsx`
- `frontend/src/config/api.js` (exports BACKEND_URL + API; read-only for Agent 2 unless contract)
- `frontend/src/components/Wtipanel.jsx`, `RussellPanel.jsx`, `PublicPanel.jsx` (existing but NOT flowseeker lane — owned by other lanes)

**Forbidden:** `frontend/src/App.js`, global routing shell, `backend/`, other product features, alert threshold defaults (owned by Alert Engine lane — Agent 2 only reads/uses, does not change), outcome threshold defaults.

**Deliverables:** flowseeker components, hooks, fixtures, tests, pathmap, frontend report.

**Commit prefix:** `phase9(flow-fe):`

### Agent 3 — Backend / Data / ETL / Dark Pool Context
**Default mode:** PROPOSAL_ONLY.

**Owns (PROPOSAL_ONLY):**
- `.planning/proposals/backend/**`
- `.planning/proposals/openapi/**`
- `fixtures/backend/**`
- `.planning/phases/phase-9-academy-flow/reports/agent3-backend.md`

**Owns (if BACKEND_LANE_OWNER=1):**
- `backend/services/**` (Phase 9 additions only)
- `backend/routes/flowseeker.py` or new route file (if needed)
- `backend/scheduler.py` or equivalent (cadence job)
- `backend/tests/**`
- `backend/models/**` (if needed)

**Forbidden:** `frontend/src/App.js`, frontend UI, paid-key critical paths, CBOE scraping, repo clones.

**Backend files discovered (read-only, 2026-09-03):**
- `backend/alert_engine.py` — Alert dataclass, GEXSnapshot, combine_signals, eval_magnitude, confidence, eval_alert_rules, alert_evaluator (rule-based: HIGH if 2+ high-confidence signals, else MEDIUM, else LOW), AlertManager (add/deduplicate_by_hash/manifest/flush). Uses GEX regime, wall breaches, gamma squeeze, momentum extremes, GEX magnitude shifts, pin risk, volume spikes. No options-flow/contract-scan alert logic visible here.
- `backend/routes/` — 30+ route files (admin.py, alerts.py, flowseeker.py, heatseeker.py, chain.py, greeks.py, gex_analysis.py, data_providers.py, etc.). No dedicated "options flow scanner" route file visible by name — likely `flowseeker.py` or `heatseeker.py` carries the chain/scan logic.
- `backend/services/` — not directly visible; need to discover.
- `backend/scheduler.py` — not found by name; cadence job location TBD in pathmap.

**Deliverables (PROPOSAL_ONLY):** proposal packets, OpenAPI specs, fixtures, ETL designs, migration plans, backend report.

**Commit prefix:** `phase9(backend-prop):` (PROPOSAL_ONLY) or `phase9(backend):` (OWNER).

### Agent 4 — Research / Papers / GitHub / Score / Evaluation
**Owns:**
- `.planning/research/phase-9/**`
- `.planning/eval/phase-9/**`
- `.planning/phases/phase-9-academy-flow/reports/agent4-research.md`

**Forbidden:** product code, backend code, `frontend/src/App.js`, alert defaults, threshold defaults, deployment config.

**Deliverables:** source manifest, claim→rule map, refuted-claims audit, missing literature, GitHub pattern research, score spec, alert gate economics, dark pool methodology, evaluator fixtures, copy checklist, research report.

**Commit prefix:** `phase9(research):`

## Dependency graph

```
Agent 1 (arch) ──own──> contracts, wave state, decisions
     │
     ├──> Agent 2 (frontend) consumes CONTRACTS.md + WAVE_STATE.md
     │     └──> Agent 2 writes fixtures + components + tests
     │
     ├──> Agent 3 (backend, PROPOSAL_ONLY) consumes CONTRACTS.md + WAVE_STATE.md
     │     └──> Agent 3 writes proposals + OpenAPI + fixtures
     │
     └──> Agent 4 (research) consumes PLAN.md + HANDOFF.md + REQUIREMENTS.md
           └──> Agent 4 writes score spec + evaluators + citation audit + dark pool methodology
```

**Merge order:**
1. Agent 1 planning/contracts (base)
2. Agent 4 research/evaluators (honesty + score constraints)
3. Agent 3 fixtures/OpenAPI/proposals
4. Agent 2 frontend (consumes stable contracts/fixtures)

## Conflict rules

- Never two agents on one file.
- If ownership is ambiguous, the agent creates a proposal under `.planning/proposals/` and continues with unblocked work.
- Agent 2 may NOT edit `frontend/src/App.js` — if a new component needs mounting, file a contract request.
- Agent 3 may NOT edit `backend/` unless BACKEND_LANE_OWNER=1.
- Agent 4 may NOT edit product code — writes evaluator reports + proposal requests only.
- Agent 1 triages CONTRACT_REQUESTS.md; does not edit product code itself.

## Test responsibilities

| Lane | Tests |
|---|---|
| Agent 1 | Captures baseline test status; does not fix unrelated failures |
| Agent 2 | Jest tests for every new surface + formatter + filter + state; flowseeker-specific first, then full suite |
| Agent 3 | Proposed pytest cases (PROPOSAL_ONLY); actual tests only if BACKEND_LANE_OWNER=1 |
| Agent 4 | Evaluator fixtures with expected outputs; score boundary cases; copy audit (grep, not edit) |

## Existing front-end state (context for Agent 2)

The current `FlowseekerProBlademap.jsx` is a single monolithic component (1954 lines) containing:
- Pulse tape with `mapPublicChainToRows` + `aggregatePulse` (90s window, 50-row cap)
- Scanner fallback with `SCAN_UNIVERSE` (18 tickers) — market-wide scan is supposed to come from backend `/scan` endpoint
- `DEFAULT_RULES` = SCORE 92 / WHALE $25M / SIGMA 6σ / follow 3d / oiconf + zerodte on
- `ALERT_NOISE_CAP_H = 4`
- `pulseScore10`, `pulseSignal` (ASK→BULLISH), `pulseHedge` (put-ASK→HEDGE? tag), `pulseBadges` (SILVER $899K / GOLDEN $950K / WHALE $1M)
- `Wtipanel`, `RussellPanel` imports (existing, owned by other lanes)
- FR filter stubs present but not fully wired (equity-type, sweeps-only, side chips — referenced in CSS/UI but not all functional)

**Key gap Agent 2 must address:** the component is monolithic; Phase 9 wants modular flowseeker surfaces (Pulse, Scanner, Tracker, Chart modal, filters) broken out. Agent 2 owns the decomposition.
