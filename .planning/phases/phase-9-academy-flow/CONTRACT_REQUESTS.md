# Contract Requests — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

**Purpose:** Cross-lane dependencies between Agent 2 (frontend), Agent 3 (backend/proposals), Agent 4 (research/eval), and existing code.

**How to use:** Each request is a CONTRACT with an owner lane. The Receiving Agent must satisfy the contract as specified before the Requesting Agent wires live data. Agents use these as integration boundaries — not as directives to edit files in other lanes.

---

## CR-01 — B1 snapshot cadence: Mongo↔DuckDB thread

| Field | Value |
|---|---|
| **ID** | CR-01 |
| **Type** | Backend lane (Agent 3) |
| **Status** | OPEN |
| **Priority** | HIGH — blocks W2.3, W2.4, W3.2-close, W4.1-W4.3, W7.2-close |
| **Depends on** | HANDOFF_B1 section (Mongo snapshots available) |
| **Summary** | Persist Level 2 tick snapshots to file-backed DuckDB on a recurring cadence thread so Phase 9 can answer "what happened over the last N days" instead of "what just happened." |

### Trigger

Agent 3 marks this contract request as SATISFIED when the cadence thread is live on the backend and persists snapshots to a file-backed DuckDB (not Mongo, not in-memory) at a cadence Agent 3 declares in the contract.

### What Agent 3 must deliver

1. **Cadence declaration:** A declared `POLL_CADENCE` (seconds) in Agent 3's proposal. Defaults: 15s if unstated.

2. **Snapshot payload shape:** A DuckDB table or schema that Agent 2's fixtures can target. Minimum columns:
   - `timestamp` (ISO8601)
   - `ticker` (string)
   - `strike` (float or NaN for equity snapshots)
   - `option_type` (C/P string or NaN)
   - `expiry` (ISO8601 expiry or NaN)
   - `side` (BID/MID/ASK string — never BUY/SELL)
   - `last` (float or null)
   - `bid` (float or null)
   - `ask` (float or null)
   - `volume` (int)
   - `open_interest` (int or null)
   - `iv` (float or null)
   - `mark_price` (float or null)
   - `premium` (float or null)
   - `size` (int, computed)
   - `notional` (float, computed)
   - `meta` (JSON string, versioned — for future columns without schema changes)

3. **Query contract:** The table must support:
   - `SELECT * WHERE ticker = ? AND timestamp >= ? ORDER BY timestamp DESC LIMIT ?`
   - `SELECT * WHERE expiry = ? ORDER BY timestamp DESC LIMIT ?`
   - `SELECT * WHERE side = ? ORDER BY timestamp DESC LIMIT ?`
   - Time-windowed queries for NetPremium trends, strike distribution, Vol/OI 14d

4. **Agent 2 fixture target:** A documented DuckDB query path that Agent 2's `W4_HISTORY_FIXTURES` target in `FlowseekerLibrary Tests > 0. Test runner > W4_HISTORY_FIXTURES`.

5. **Mongo promotion gate:** Agent 3's proposal must state whether the cadence thread is a NEW Mongo collection or writes to existing `tick_snapshots` collection. Agent 2 needs the `TICK-SNAPSHOT-BACKEND` gate in `FlowseekerLibrary Tests > 0. Test runner > `to know when the fixture pipeline is complete.

6. **No mock data:** Strictly prohibited. The cadence thread must query the SAME public API that the existing `/` Route on `public/` views uses, OR a third-party data source with equal-or-better reliability. If a third-party source is used, Agent 3 must document it in the proposal and Agent 4 must evaluate it in `Source manifest`.

### Acceptance criteria

- [ ] Cadence thread starts automatically on backend restart (no manual trigger)
- [ ] Snapshots persist to file-backed DuckDB surviving backend restart
- [ ] DuckDB path is documented in Agent 3's proposal
- [ ] Agent 2 can query the DuckDB with the documented contract and get real historical rows
- [ ] `tick_snapshots` OR Agent 3 declares alternative collection name for Mongo promotion
- [ ] No mock data in the cadence thread
- [ ] DuckDB fixture query path is documented for Agent 2 fixtures

### What Agent 2 can do before CR-01 is satisfied

- Ship W4.1-W4.3 against fixtures derived from `W4_AFTER_FIXTURE.json` + synthetic snapshots
- Document the gap in `FlowseekerLibrary Tests > 0. Test runner > W4 fix needed if MongoDB`
- Recall the Mongo promotion gate `TICK-SNAPSHOT-BACKEND` in `FlowseekerLibrary Tests > 0. Test runner > `

### What Agent 4 does

- Evaluate the cadence data source in `Source manifest` (CR-01 references it)
- Write historical view evaluator fixtures in `W4 evaluator fixtures`
- Verify that DuckDB queries reproduce expected history on demand

---

## CR-02 — B2: Finnhub earnings cache + sector/industry map

| Field | Value |
|---|---|
| **ID** | CR-02 |
| **Type** | Backend lane (Agent 3) |
| **Status** | OPEN |
| **Priority** | HIGH — blocks W2.1 (earnings proximity), W2.2 (sector/industry) |
| **Depends on** | HANDOFF_B2 section (Finnhub /earnings & /profile2 available) |
| **Summary** | Populate a backend earnings calendar + sector/industry map from Finnhub so Pulse/Scanner rows can show earnings proximity and sector filters without frontend fetching. |

### Trigger

Agent 3 marks this contract request as SATISFIED when the backend exposes:
- An earnings calendar that can be queried by ticker (with dates and what was announced)
- A sector/industry map for all tickers in the SCAN_UNIVERSE (or the 18-ticker fallback)

### What Agent 3 must deliver

1. **Earnings calendar shape:**
   ```json
   {
     "earnings": {
       "AAPL": [
         { "date": "2026-01-28", "quarter": "Q4 2025", "surprise": "beats/misses/in-line", "implied_move_pct": 4.2 }
       ]
     },
     "cache_ts": "2026-01-25T00:00:00Z",
     "next_refresh": "2026-01-26T00:00:00Z"
   }
   ```

2. **Sector/industry map shape:**
   ```json
   {
     "sector_map": {
       "AAPL": { "sector": "Technology", "industry": "Consumer Electronics" },
       "XLU": { "sector": "Utilities", "industry": "Utilities" }
     }
   }
   ```

3. **Frontend API contract:** Endpoints (or a single endpoint) Agent 2 can call to get:
   - Earnings for a list of tickers → returns earnings calendar for those tickers
   - Sector/industry for a list of tickers → returns sector/industry map subset

4. **Cache policy:** Earnings + sector data is read-heavy, write-light. Agent 3 must declare cache TTL and refresh cadence in the proposal. Agent 4 will evaluate in `Source manifest` whether Finnhub calls violate >1/min if called inline.

5. **No-go fallback:** If Finnhub /calendar/earnings or /profile2 is not viable, Agent 3 must declare the GO/NO-GO in the proposal. Agent 2 can still ship W2.1/W2.2 against fixtures if the backend data doesn't land.

### Acceptance criteria

- [ ] Earnings calendar returns real Finnhub data for 5+ tickers sampled
- [ ] Sector/industry map returns real Finnhub profile2 data for 5+ tickers sampled
- [ ] Frontend endpoints documented for Agent 2 to call
- [ ] Cache TTL declared in proposal
- [ ] GO/NO-GO declared if Finnhub endpoints are not viable

### What Agent 2 can do before CR-02 is satisfied

- Ship W2.1 (earnings proximity column + filter) against fixtures only
- Ship W2.2 (sector/industry filter) against fixtures only
- Document the gap in `FlowseekerLibrary Tests > 0. Test runner > W2 fix needed if Finnhub is cancelled`
- Recall the Finnhub-go/no-go gate `FINNHUB-CACHE-GO/NO-GO` in `FlowseekerLibrary Tests > 0. Test runner > `

### What Agent 4 does

- Write context column evaluator fixtures for earnings proximity + sector/industry
- Run citation audit for earnings/sector claims (source attribution, Finnhub data agreement)
- Evaluate Finnhub /calendar/earnings rate limits in `Source manifest`

---

## CR-03 — B3: FINRA Reg SHO / Dark Pool ETL + trade attribution

| Field | Value |
|---|---|
| **ID** | CR-03 |
| **Type** | Backend lane (Agent 3) |
| **Status** | WISH — not required for Phase 9 core delivery |
| **Priority** | LOW-MEDIUM — enables W7.4 dark pool overlay, requires filings/auth |
| **Depends on** | HANDOFF_B3 section (MNS/ATS Reg SHO, FINRA TRACE, SEC IFR, FINRA Daily Trading Activity) |
| **Summary** | Ingest Reg SHO threshold securities list (MNS/ATS) + FINRA TRACE short sale data + SEC IFR + FINRA Daily Trading Activity, attribute to tickers in SCAN_UNIVERSE, persist to Mongo, and expose dark pool levels data for the W7.4 overlay. |

### Trigger

Agent 3 marks this contract request as SATISFIED when:
- Reg SHO MNS data is ingested for tickers in SCAN_UNIVERSE
- Dark pool trade attribution is persisted to Mongo
- Dark pool levels top-N data is exposed for W7.4 overlay

### What Agent 3 must deliver

1. **Reg SHO MNS ingestion:**
   - Daily refresh of threshold securities list
   - Persist to Mongo with ticker, date, threshold flag, shares
   - Be transparent about lag/delays in Reg SHO reporting

2. **Dark pool attribution:**
   - Map FINRA TRACE + SEC IFR trades to tickers in SCAN_UNIVERSE
   - Persist to Mongo with trade timestamp, size, dark pool flag, exchange/venue (if disclosed)
   - CRITICAL: Dark pool prints have NO side, NO direction. Agent 3 must NOT add fabricated direction.

3. **W7.4 data contract:**
   - A backend endpoint that returns top-N dark pool levels by notional for a given ticker or date range
   - Data shape compatible with the W7.4 dark pool overlay spec in `W7 work items` (dashed lines + notional labels)

4. **Authentication:** FINRA TRACE requires FINRA membership or paid subscription. Agent 3's proposal must declare whether FINRA access is available. If not, the overlay ships spec-only (W7.4 stays in WISH state).

### Acceptance criteria

- [ ] Reg SHO MNS data ingested for SCAN_UNIVERSE tickers (daily refresh or declared cadence)
- [ ] Dark pool trades attributed to tickers in Mongo
- [ ] Dark pool levels top-N endpoint exists (even if empty until FINRA auth lands)
- [ ] Authentication path declared in proposal
- [ ] NO fabricated dark pool direction (this is a bug if present)

### What Agent 2 can do before CR-03 is satisfied

- Ship W7.4 spec-only (overlay component stubs that render "dark pool data unavailable" state)
- Document the gap in `FlowseekerLibrary Tests > 0. Test runner > W7 fix needed if FINRA auth is delayed`

### What Agent 4 does

- Write dark pool methodology spec in `eval/` referencing the QUARTER-COW opacity model
- Run citation audit for dark pool claims (no directional language permitted)
- Write copy audit for dark pool UI (no "buying"/"selling" in dark pool context)

---

## CR-04 — B5: Min volume alignment in public bars pipeline

| Field | Value |
|---|---|
| **ID** | CR-04 |
| **Type** | Backend lane (Agent 3) |
| **Status** | OPEN |
| **Priority** | LOW — observability / data integrity; not a user-facing feature |
| **Depends on** | HANDOFF_B5 section (min volume check) |
| **Summary** | Align the minimum volume check in the public bars pipeline with the existing frontend `MIN_VOLUME = 1` gate. The frontend's "building n over 20" bar tells users the scan cadence hasn't yet accumulated enough prints to break the MIN_VOLUME floor. Backend data should respect the same threshold so stale bars don't show as fully-populated. |

### Trigger

Agent 3 marks this contract request as SATISFIED when:
- The `MIN_VOLUME` check in the backend data pipeline is visible/auditable
- The backend's minimum-volume threshold matches or exceeds the frontend's `MIN_VOLUME = 1`
- Agent 2 can verify that the frontend "building n over 20" state aligns with backend data freshness

### What Agent 3 must deliver

1. **MID_VOLUME threshold declaration:** A declared `MIN_VOLUME` value in the backend pipeline (or equivalent). Default: 1 (matching frontend).

2. **Data freshness visibility:** A way for Agent 2's frontend to know whether backend data has accumulated enough prints to break the MIN_VOLUME floor. This could be a field on the snapshot response, a separate freshness endpoint, or a documented convention.

3. **Honest-empty data:** Backend snapshots with volume below MIN_VOLUME should NOT be served as fully-populated trades. They should either:
   - Be excluded from the response entirely
   - Or include a `freshness` or `accumulation` field that the frontend can use to show "building n over 20" honestly

### Acceptance criteria

- [ ] MIN_VOLUME threshold declared in backend pipeline
- [ ] Backend data respects the same threshold as frontend (or documented divergence)
- [ ] Frontend can determine data freshness from backend response
- [ ] Stale/under-accumulated data does not show as fully-populated

### What Agent 2 can do before CR-04 is satisfied

- Keep the existing frontend MIN_VOLUME = 1 gate working
- Ship W1-W7 features against current data without waiting for backend alignment
- Document any divergence in `FlowseekerLibrary Tests > 0. Test runner > `

### What Agent 4 does

- Verify the MIN_VOLUME alignment between frontend + backend in the integration checklist
- No deep eval needed — this is an observability/data integrity contract

---

## CR-05 — B6: Quiet accumulation spike alert (proposal only)

| Field | Value |
|---|---|
| **ID** | CR-05 |
| **Type** | Backend lane (Agent 3) — PROPOSAL ONLY |
| **Status** | OPEN — proposal, no code commitment |
| **Priority** | LOW — proposal only; not a Phase 9 core deliverable |
| **Depends on** | HANDOFF_B6 section (quiet accumulation spike alert) |
| **Summary** | Agent 3 PROPOSES an alert type for quiet accumulation spikes (≥300% trade count increase vs trailing 30-day daily average) based on the Handoff spec. Agent 4 evaluates the proposed methodology. Agent 2 implements the UI ONLY if the alert is approved by the gate plan. |

### Trigger

Agent 3 submits a proposal. Agent 4 writes an evaluation. Agent 1 triages via the gate plan.

### What Agent 3 must deliver

1. **Proposal shape:**
   - Alert name + criteria (trade count increase threshold, trailing window, lookback)
   - Data requirements (snapshot cadence, volume thresholds, ticker universe)
   - Expected false positive rate (stated honestly, with methodology)
   - Pros/cons from Agent 3's perspective

2. **Honesty requirements:**
   - Alert quality must be honest about signal strength
   - Not "hot 4D TE heavy premium fake volume sweep alert" — substance over marketing
   - If quiet accumulation is hard to distinguish from routine large-block trades, Agent 3 must say so

### What Agent 4 must deliver

- An evaluation of the proposed quiet accumulation alert in `Alert gate economics`
- False positive estimate, signal strength assessment, alert fatigue risk
- Recommendation: ship / refine / reject

### What Agent 1 (me) must do

- Include CR-05 in the gate plan (EVALUATE, not SHIP, initially)
- Decide whether quiet accumulation alert is worth building in Phase 9 or deferred

### What Agent 2 can do before CR-05 is approved

- Nothing. The alert UI ships only if the gate plan approves.

### Acceptance criteria

- [ ] Agent 3 proposal submitted
- [ ] Agent 4 evaluation submitted
- [ ] Agent 1 gate decision recorded in GATE_PLAN.md
- [ ] If approved: Agent 3 implements, Agent 2 builds UI
- [ ] If rejected/refined: spec recorded in RISK_REGISTER.md

---

## CR-06 — B7: Outcome tracking backend (partial code exists)

| Field | Value |
|---|---|
| **ID** | CR-06 |
| **Type** | Backend lane (Agent 3) — partial code exists |
| **Status** | PARTIAL — `backend/services/flow_calibration.py` + `backend/services/flow_outcomes.py` exist |
| **Priority** | LOW — partial implementation exists; Agent 3 may enhance or leave as-is |
| **Depends on** | HANDOFF_B7 section (Mongo persistence + calibration service) |
| **Summary** | Outcome tracking backend for W3.2 Tracker. Existing code: `backend/services/flow_calibration.py` + `backend/services/flow_outcomes.py`. Agent 3 may enhance, leave as-is, or replace — Agent 1 does not require any specific backend implementation for Phase 9 core delivery. Agent 2's tracker ships localStorage-first regardless. |

### Trigger

Agent 3's proposal (or existing code inspection). Agent 1 records the current state in RISK_REGISTER.md.

### What Agent 3 must deliver (if enhancing)

- Mongo persistence for tracker outcomes (if localStorage-only is insufficient)
- Calibration service that can consume outcome data
- Open Endpoint `/duckdb/status` (file-backed DuckDB status)

### What Agent 2 must do regardless

- Ship W3.2 Tracker localStorage-first with 6 statuses
- Document Mongo promotion gate `TRACKER-MONGO-PROMOTION` in `FlowseekerLibrary Tests > 0. Test runner > `
- If MongoDB is cancelled: Tracker ships localStorage-only with a documented limitation

### Acceptance criteria

- [ ] Agent 3's proposal recorded (or existing code inspected)
- [ ] Agent 2's tracker ships localStorage-first regardless of backend state
- [ ] Mongo promotion gate recorded in RISK_REGISTER.md

---

## CR-07 — B8: Citation hygiene (backend docstrings)

| Field | Value |
|---|---|
| **ID** | CR-07 |
| **Type** | Backend lane (Agent 3) — DOCUMENTATION ONLY |
| **Status** | OPEN |
| **Priority** | LOW — no user-facing impact; institutional hygiene |
| **Depends on** | HANDOFF_B8 section (citation hygiene) |
| **Summary** | Backend services need docstrings documenting data provenance: source, method, freshness, lag, known biases. NOT for rendering in frontend — used by agents + engineers inspecting backend code. |

### Trigger

Agent 3's proposal or existing code inspection. Agent 1 records the state in RISK_REGISTER.md.

### What Agent 3 must deliver (if implementing)

- Docstrings on backend services that document:
  - Data source (e.g. "Finnhub /profile2", "public API snapshot chain", "yfinance")
  - Method (e.g. "HAR-IV model", "ADF cointegration test, tuple-fixed")
  - Freshness (e.g. "daily cache refresh", "15s cadence")
  - Lag (e.g. "Reg SHO MNS list is T+1", "Finnhub earnings calendar may lag exchange")
  - Known biases (e.g. "dark pool prints have no side", "snapshot chains have no sweep visibility")

### What Agent 4 must do

- Evaluate citation hygiene state in `eval/` reports
- Flag services missing provenance documentation

### Acceptance criteria

- [ ] Agent 3's proposal recorded (or existing code inspected)
- [ ] Missing provenance entries flagged in RISK_REGISTER.md

---

## CR-08 — B9: Open/short interest borrow inputs (proposal only)

| Field | Value |
|---|---|
| **ID** | CR-08 |
| **Type** | Backend lane (Agent 3) — PROPOSAL ONLY |
| **Status** | OPEN — proposal, no code commitment |
| **Priority** | LOW — proposal only; not a Phase 9 core deliverable |
| **Depends on** | HANDOFF_B9 section (O/S borrow inputs) |
| **Summary** | Agent 3 PROPOSES integration of open/short interest borrow rate inputs into flow scoring. Agent 4 evaluates. Agent 1 triages via gate plan. NOT a Phase 9 core deliverable. |

### What Agent 3 must deliver

- A proposal documenting how borrow rate inputs would affect flow scoring
- Data source for borrow rates (if any)
- Expected impact on score magnitude/sign

### What Agent 4 must deliver

- Evaluation of borrow rate inputs (signal strength, data availability, false positive risk)

### What Agent 1 must do

- Include CR-08 in gate plan (EVALUATE, not SHIP)

---

## CR-09 — Pulse decomposition: agent2 pathmap products + test runner

| Field | Value |
|---|---|
| **ID** | CR-09 |
| **Type** | Frontend lane (Agent 2) — already in flight on main |
| **Status** | SHIPPED — `agent2-pathmap.md` + `agent2-frontend.md` are committed on main |
| **Priority** | DONE — reference only for Agent 1's contracts |
| **Summary** | Agent 2 already decomposed the monolith into Pathmap products (PulseTape, PulseColumns, OverviewBar, etc.) and shipped W1-W7. Agent 1 references these for contract cross-checks. |

### What Agent 1's contracts must respect

- `agent2-pathmap.md` is the authoritative frontend decomposition reference
- `agent2-frontend.md` contains the test runner + 13 test files
- Any contract that references frontend modules must use the `agent2-pathmap.md` module names

### What Agent 3 must not do

- Agent 3 must NOT edit `frontend/src/components/flowseeker/*.jsx`
- Agent 3 must NOT edit `frontend/src/App.js`
- Agent 3 must NOT assume frontend module names that contradict `agent2-pathmap.md`

---

## CR-10 — Score spec: signed flow score contract (-100..+100)

| Field | Value |
|---|---|
| **ID** | CR-10 |
| **Type** | Cross-lane (Agent 2 + Agent 4) |
| **Status** | OPEN — needs Agent 4 evaluation + Agent 2 display implementation |
| **Priority** | MEDIUM — display-only, not alert-gating |
| **Depends on** | CONTRACTS.md C1-C17 (Full signed score spectrum, sign matrix, magnitude weights, boundary cases) |
| **Summary** | The signed Flow Score (`-100..+100`) is a DISPLAY-ONLY indicator — it is NOT used for alert gating (that's the composite score's job via Engine Handoff Gate C18). Agent 4 writes the spec + evaluator fixtures. Agent 2 implements the score display UI. |

### Trigger

Agent 4 writes the score spec in `eval/signed-score-spec.md` (or equivalent). Agent 2 implements display UI. Agent 1 records in GATE_PLAN.md.

### What Agent 4 must deliver

- `eval/signed-score-spec.md` — the signed score spec document (signs, magnitude, boundary cases)
- Evaluator fixtures for score boundary cases (tested against W5.1-W5.2)
- Citation audit for score methodology claims

### What Agent 2 must deliver

- Score display component (if spec is complete)
- Unit tests for score display (boundary cases: -100, 0, +100, no-quote, zero OI, missing IV, put-ASK hedge, 0DTE volOI>=2)

### Acceptance criteria

- [ ] Agent 4 score spec written
- [ ] Agent 4 evaluator fixtures written
- [ ] Agent 2 score display UI implemented (if spec is complete)
- [ ] Score does NOT gate alerts (Engine Handoff Gate C18 enforces this)
- [ ] Score is DISPLAY-ONLY, marked as such in UI

---

## CR-11 — Sub-agent scaffold: tools + tests + ignore + env docs

| Field | Value |
|---|---|
| **ID** | CR-11 |
| **Type** | Cross-lane (Agent 1) — already in deliverables |
| **Status** | PARTIAL — `AGENT_RUNBOOK.md` exists |
| **Priority** | DONE — reference only |
| **Summary** | Agent 1's sub-agent scaffolding doc. Agent 2's `agent2-pathmap.md` documents the test runner. Agent 3's proposal documents backend setup. Agent 4's research documents eval setup. Agent 1 records the consolidated sub-agent environment in `AGENT_RUNBOOK.md`. |

### What Agent 1 must deliver

- `AGENT_RUNBOOK.md` with sub-agent commands, test commands, ports, env setup, git workflow, Mermaid support

---

## CR-12 — AGENT_RUNBOOK.md: sub-agent environment doc

| Field | Value |
|---|---|
| **ID** | CR-12 |
| **Type** | Agent 1 (Architect) deliverable |
| **Status** | OPEN — needs to be written |
| **Priority** | MEDIUM — supports all sub-agents running Phase 9 |
| **Summary** | Document the sub-agent run environment: git commands, test commands, ports, env vars, Hermes config, Mermaid support, how to run agents. |

### What Agent 1 must deliver

- `AGENT_RUNBOOK.md` with:
  - Git commands for creating/checking out phase9 branches
  - Test commands for each agent's test suite
  - Port layout (8000 backend, 3000 proxy, any new ports)
  - Environment variables needed (Public.com key, Finnhub key, etc.)
  - Hermes config for each agent (model, memory, skills)
  - Mermaid support (if used)
  - How to run agents (Hermes CLI, subagent dispatch)

---

## CR-13 — GMP-style integration checkpoint

| Field | Value |
|---|---|
| **ID** | CR-13 |
| **Type** | Agent 1 (Architect) deliverable |
| **Status** | OPEN — needs to be written |
| **Priority** | MEDIUM — integration verification |
| **Summary** | A GMP-style integration checkpoint document that lists all integration points between agents and how to verify each one works. |

### What Agent 1 must deliver

- `INTEGRATION_CHECKLIST.md` with:
  - All integration points (Agent 2 ↔ Agent 3, Agent 2 ↔ Agent 4, Agent 3 ↔ Agent 4)
  - Verification method for each (curl, frontend test, backend test, eval fixture)
  - Expected state when integration is healthy

---

## CR-14 — RISK_REGISTER.md

| Field | Value |
|---|---|
| **ID** | CR-14 |
| **Type** | Agent 1 (Architect) deliverable |
| **Status** | OPEN — needs to be written |
| **Priority** | HIGH — risk management across all agents |
| **Summary** | Comprehensive risk register covering Phase 9 delivery risks, data risks, integration risks, process risks. |

### What Agent 1 must deliver

- `RISK_REGISTER.md` with:
  - All identified risks (high/medium/low)
  - Mitigation for each risk
  - Owner lane for each risk
  - Status (open/monitoring/mitigated)

---

## CR-15 — GATE_PLAN.md

| Field | Value |
|---|---|
| **ID** | CR-15 |
| **Type** | Agent 1 (Architect) deliverable |
| **Status** | OPEN — needs to be written |
| **Priority** | HIGH — gate authority for all Phase 9 decisions |
| **Summary** | Gate plan that defines how gates are evaluated, who evaluates them, and what the criteria are. |

### What Agent 1 must deliver

- `GATE_PLAN.md` with:
  - All gate types (data gates, product gates, evaluation gates, research gate, agent gates)
  - Gate evaluation criteria
  - Gate authority (who evaluates, who approves)
  - Gate state for each gate (open/passing/failed/deferred)

---

## CR-16 — reports/agent1-architect.md

| Field | Value |
|---|---|
| **ID** | CR-16 |
| **Type** | Agent 1 (Architect) deliverable |
| **Status** | OPEN — needs to be written |
| **Priority** | HIGH — summary report of Agent 1's work |
| **Summary** | Comprehensive report documenting Agent 1's Phase 9 Architect work: what was produced, what was discovered, what is pending, what is blocked. |

### What Agent 1 must deliver

- `reports/agent1-architect.md` with:
  - Executive summary
  - What was produced (all deliverables)
  - What was discovered (repo state, code that already exists, gaps)
  - What is pending (what still needs to be done)
  - What is blocked (if anything)
  - Recommendations for next steps

---

## Summary: what's still needed

| ID | File | Owner | Status |
|---|---|---|---|
| CR-12 | AGENT_RUNBOOK.md | Agent 1 | OPEN |
| CR-13 | INTEGRATION_CHECKLIST.md | Agent 1 | OPEN |
| CR-14 | RISK_REGISTER.md | Agent 1 | OPEN |
| CR-15 | GATE_PLAN.md | Agent 1 | OPEN |
| CR-16 | reports/agent1-architect.md | Agent 1 | OPEN |
| CR-10 | eval/signed-score-spec.md | Agent 4 | OPEN |
| CR-01 | B1 cadence thread | Agent 3 | OPEN |
| CR-02 | B2 earnings cache | Agent 3 | OPEN |
| CR-03 | B3 FINRA ETL | Agent 3 | WISH |
| CR-05 | B6 quiet accumulation alert | Agent 3 | PROPOSAL ONLY |
| CR-06 | B7 outcome tracking | Agent 3 | PARTIAL (code exists) |
| CR-07 | B8 citation hygiene | Agent 3 | OPEN (docstrings) |
| CR-08 | B9 borrow inputs | Agent 3 | PROPOSAL ONLY |
| CR-09 | Agent 2 pathmap + tests | Agent 2 | SHIPPED on main |
