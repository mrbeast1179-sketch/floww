# Pathmap — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

## Flowseeker frontend (Agent 2 lane)

### Current monolithic component
- `frontend/src/components/flowseeker/FlowseekerProBlademap.jsx` — 1954 lines. Single component containing Pulse tape + Scanner fallback + all helpers. This is the file Agent 2 must decompose.

### Existing flowseeker files
- `frontend/src/components/flowseeker/FlowseekerProBlademap.css` — scoped .fsb-* classes
- `frontend/src/components/flowseeker/FlowseekerProBlademap.test.jsx` — existing Jest test
- `frontend/src/components/flowseeker/BlademapActiveMount.test.jsx` — existing Jest test

### Config
- `frontend/src/config/api.js` — exports BACKEND_URL + API (read-only for Agent 2 unless contract requires edit)

### Wtipanel / RussellPanel / PublicPanel
- `frontend/src/components/Wtipanel.jsx` — WTI HAR-IV panel (owned by other lane)
- `frontend/src/components/RussellPanel.jsx` — Russell pairs panel (owned by other lane)
- `frontend/src/components/PublicPanel.jsx` — Public.com brokerage panel (owned by other lane)

### Agent 2 target structure (proposed, to be created)
```
frontend/src/components/flowseeker/
  FlowseekerProBlademap.jsx        # shell that composes sub-surfaces (decomposed from current monolith)
  FlowseekerProBlademap.css         # scoped styles (existing, extend)
  PulseTape.jsx                    # W1 — spread bar + fill cols + overview bar
  PulseTape.test.jsx               # W1 tests
  scanLogic.js                     # existing formatter single source (if separate) or kept in Blademap
  scanLogic.test.js                # existing formatter tests
  OverviewBar.jsx                  # W1 — net premium / P/C / FIR / session label
  ScannerTable.jsx                 # W4 — market-wide scanner rows
  ScannerFilters.jsx               # W6 — equity-type, sweeps, side, OTM/ITM/0DTE, OPEX, strike-range, OI-growth, sentiment, |score|
  Tracker.jsx                      # W3 — bookmark + live P/L + statuses
  Tracker.test.jsx                 # W3 tests
  ChartModal.jsx                   # W3 — contract history + Net Premium v1
  ChartModal.test.jsx              # W3 tests
  TabConfig.js                      # W4 — per-tab config substrate (single object)
  TabConfig.test.js                 # W4 tests
  Highlighting.jsx                 # W3 — Size>OI / Vol>OI row icons
  Highlighting.test.jsx            # W3 tests
  FilterState.js                    # W6 — filter state object + serialization
  FilterState.test.js               # W6 tests
  types.js                         # local TypeScript-style JSDoc types for contracts
  fixtures/                        # synthetic fixture data for tests
    pulseRows.json
    scannerRows.json
    alerts.json
    trackerItems.json
    darkPoolLevels.json
    finraContext.json
    regShoContext.json
    missingFieldStates.json
    highlightingCases.json
    scoreBoundaryCases.json
    filterSubtractivenessCases.json
```

## Backend (Agent 3 lane — PROPOSAL_ONLY unless BACKEND_LANE_OWNER=1)

### Existing backend structure
- `backend/alert_engine.py` — Alert dataclass, GEXSnapshot, combine_signals, eval_magnitude, confidence, eval_alert_rules, alert_evaluator, AlertManager
- `backend/routes/` — 30+ route files (admin.py, alerts.py, flowseeker.py, heatseeker.py, chain.py, greeks.py, gex_analysis.py, data_providers.py, etc.)
- `backend/services/` — not yet enumerated (TBD)
- `backend/scheduler.py` — not found by name (TBD)
- `backend/models/` — not yet enumerated (TBD)

### Backend files to discover (Agent 1 will enumerate, Agent 3 owns proposals)
- `backend/services/` contents
- `backend/models/` contents
- `backend/scheduler.py` or equivalent cadence file
- `backend/tests/` structure
- Existing /scan or /flowseeker chain endpoint (likely in routes/flowseeker.py or routes/heatseeker.py)

### Agent 3 target proposal structure
```
.planning/proposals/backend/
  b1-snapshot-cadence.md          # cadence job design + patch
  b2-earnings-cache.md             # Finnhub /calendar/earnings cache
  b3-dark-pool-etl.md              # FINRA ATS + Reg SHO + Top-N levels
  b5-align-min-volume.md           # force_refresh vs market_scan min_volume alignment
  b6-quiet-accumulation.md         # display-first gate design
  b7-outcome-tracking.md           # per-tag 30-min outcome tracking
  b8-citation-hygiene.md           # gex_paper_accurate.py docstring fixes
  b9-os-borrow-inputs.md           # stock-volume share + short-fee feed design
  openapi/
    overview-bar-openapi.yaml
    pulse-extras-openapi.yaml
    scanner-extras-openapi.yaml
    dark-pool-levels-openapi.yaml
    finra-ats-openapi.yaml
    reg-sho-openapi.yaml
    quiet-accumulation-openapi.yaml
    outcomes-openapi.yaml
    earnings-openapi.yaml
    sector-openapi.yaml
fixtures/backend/
  cadence-fixture.json
  earnings-fixture.json
  finra-fixture.json
  regsho-fixture.json
  dark-pool-topn-fixture.json
  quiet-accumulation-fixture.json
  outcome-fixture.json
```

## Research (Agent 4 lane)

### Target structure
```
.planning/research/phase-9/
  source-manifest.md              # confirmed + missing papers, data sources
  claim-rule-map.md               # citation -> product rule mapping
  refuted-claims-audit.md         # scan for false claims in repo/docs/copy
  missing-literature.md           # 0DTE + 2023+ intraday momentum targets
  github-patterns.md              # public repo pattern research (no code copying)
.planning/eval/phase-9/
  signed-score-spec.md            # -100..+100 score spec, sign matrix, magnitude weights
  alert-gate-economics.md         # SCORE 92 / $25M / 6σ / 4hr economics analysis
  dark-pool-methodology.md        # honest dark pool filtering design
  copy-checklist.md               # honest copy rules per surface
  fixtures/
    pulseRows.json
    overviewBarPayloads.json
    scannerRows.json
    alerts.json
    trackerItems.json
    darkPoolLevels.json
    finraContext.json
    regShoContext.json
    missingFieldStates.json
    highlightingCases.json
    scoreBoundaryCases.json
    filterSubtractivenessCases.json
```

## Phase 9 planning dir (Agent 1 owns all)
```
.planning/phases/phase-9-academy-flow/
  HANDOFF.md                      # existing — source of truth
  PLAN.md                        # existing — wave plan W0-W7
  REQUIREMENTS.md                # existing — R9.0-R9.25
  FULL_PLAN.md                   # existing
  LANE_MAP.md                    # created now
  PATHMAP.md                     # created now
  DECISIONS.md                   # to create
  CONTRACTS.md                   # to create
  WAVE_STATE.md                  # to create
  GATE_PLAN.md                   # to create
  RISK_REGISTER.md               # to create
  CONTRACT_REQUESTS.md           # to create
  INTEGRATION_CHECKLIST.md       # to create
  reports/
    agent1-architect.md          # to create
    agent2-frontend.md           # Agent 2 writes
    agent2-pathmap.md            # Agent 2 writes
    agent3-backend.md            # Agent 3 writes
    agent3-pathmap.md            # Agent 3 writes
    agent4-research.md           # Agent 4 writes
```

## Key notes for Agent 1 triage

1. The existing `FlowseekerProBlademap.jsx` is a 1954-line monolith — Agent 2 must decompose it. This is the #1 frontend risk.
2. `DEFAULT_RULES` already has SCORE 92 / WHALE $25M / SIGMA 6σ — Agent 4 must evaluate whether these thresholds are right for a whole-market universe.
3. `ALERT_NOISE_CAP_H = 4` — Agent 4 must evaluate whether 4/hour is right throttle shape.
4. `SCAN_UNIVERSE` is hardcoded to 18 tickers — the plan assumes a backend `/scan` endpoint for market-wide. Agent 3 must either build it or Agent 2 must work with the 18-ticker fallback.
5. The 15s poll cadence + Mongo 50/ticker cap + in-memory DuckDB are real constraints — Agent 3 B1 is critical path for W4 history features.
6. No dedicated "options flow scanner" route file visible by name — Agent 3 must discover where chain/scan logic lives.
