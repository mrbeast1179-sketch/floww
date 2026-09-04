# Gate Plan — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

## Purpose

This is the gatekeeper document for Phase 9. Every gate defined here is a control point that must pass before the associated deliverable ships. Agent 1 owns this document. Agent 4's evaluations feed into these gates. Agent 2's test evidence feeds into these gates. Agent 3's proposals feed into these gates.

## Gate types

| Type | Symbol | Who evaluates | Who approves | What it gates |
|---|---|---|---|---|
| **Data gate** | D | Agent 3 (proposal) + Agent 4 (eval) | Agent 1 | Backend data availability, freshness, schema |
| **Product gate** | P | Agent 2 (tests) + Agent 4 (eval) | Agent 1 | Frontend feature readiness, test evidence, UI quality |
| **Evaluation gate** | E | Agent 4 (eval) | Agent 1 | Methodology quality, false positive rate, backtest results |
| **Research gate** | R | Agent 4 (research) | Agent 1 | Literature ground truth, citation accuracy, methodology validity |
| **Agent gate** | A | Agent 1 (orchestration) | Agent 1 | Cross-agent integration, lane discipline, contract satisfaction |

---

## Phase 9 gate list

### G0 — Spike gates (W0)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G0.1 | OPTION instrument_type on public bars | D | Agent 3 checks if public bars include instrument_type. If yes: GO. If no: NO-GO (fallback: snapshot-derived contract history). | OPEN — Agent 3 to check |
| G0.2 | OpenTerminalUI heat-score/sentiment | D | Agent 3 checks if OpenTerminalUI provides heat score / sentiment. If yes: GO. If no: NO-GO. | OPEN — Agent 3 to check |
| G0.3 | yfinance earnings/sector fields | D | Agent 3 checks what Finnhub /calendar/earnings + /profile2 return. | OPEN — Agent 3 to check |

**Decision:** Agent 1 defers these to Agent 3's spike check. Agent 1 records GO/NO-GO in DECISIONS.md after Agent 3 reports.

---

### G1 — Tracer gates (W1)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G1.1 | Spread-position bar implementation | P | Agent 2 ships PulseTape with spread bar. Tests pass (20 rows, ±1%). | OPEN — Agent 2 to ship |
| G1.2 | Fill column implementation | P | Agent 2 ships fill column. Tests pass. | OPEN — Agent 2 to ship |
| G1.3 | Overview bar v1 (net premium, P/C, FIR, session, RVOL honest-empty) | P | Agent 2 ships OverviewBar. Tests pass on fixtures. RVOL shows honest-empty state. | OPEN — Agent 2 to ship |

**Decision:** Agent 2 ships W1. Agent 4 evaluates overview bar values against expected fixtures. Agent 1 approves when tests pass + eval passes.

---

### G2 — Filter gates (W6)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G2.1 | Equity-type triple toggle | P | Agent 2 ships ETF/Stock/Index toggle. Tests pass (ETF-off removes ETF rows). | OPEN — Agent 2 to ship |
| G2.2 | Sweeps-only chip (labeled proxy) | P | Agent 2 ships sweeps-only chip. Tests pass. Chip labeled "sweep proxy". | OPEN — Agent 2 to ship |
| G2.3 | Side chips (Bid/Mid/Ask) | P | Agent 2 ships side chips. Tests pass (each chip removes opposite side). | OPEN — Agent 2 to ship |
| G2.4 | OTM / ITM / 0DTE toggles | P | Agent 2 ships OTM/ITM/0DTE toggles. Tests pass (each toggle moves row counts monotonically). | OPEN — Agent 2 to ship |
| G2.5 | OPEX-week-only toggle | P | Agent 2 ships OPEX toggle. Tests pass. | OPEN — Agent 2 to ship |
| G2.6 | Strike-range filter | P | Agent 2 ships strike range. Tests pass (min/max filter rows). | OPEN — Agent 2 to ship |
| G2.7 | OI-growth slider (fixture-first, needs B1) | P | Agent 2 ships OI-growth slider against fixtures. Real values gated on B1. | OPEN — Agent 2 to ship fixtures |
| G2.8 | Contract sentiment slider | P | Agent 2 ships contract sentiment. Tests pass (moves row counts). | OPEN — Agent 2 to ship |
| G2.9 | Chain sentiment slider | P | Agent 2 ships chain sentiment. Tests pass. | OPEN — Agent 2 to ship |
| G2.10 | \|score\| mode | P | Agent 2 ships absolute value score filter. Tests pass. | OPEN — Agent 2 to ship |
| G2.11 | Row icons (sweep waves + multi-leg badge) | P | Agent 2 ships sweep/multi-leg icons. Tests pass (fixtures badge correctly). | OPEN — Agent 2 to ship |
| G2.12 | Filter state object (C16) + persistence | P | Agent 2 ships FilterState. Tests pass (serializes/deserializes). | OPEN — Agent 2 to ship |
| G2.13 | Before/after row counts in debug mode | P | Agent 2 ships debug counts. Tests pass. | OPEN — Agent 2 to ship |
| G2.14 | Empty-state widen actions | P | Agent 2 ships empty-state widen. Tests pass (each action widens row count). | OPEN — Agent 2 to ship |

**Decision:** Agent 2 ships W6 filters. Agent 4 evaluates filter subtractiveness (filters reduce noise, don't just move it around). Agent 1 approves when all tests pass + eval passes.

---

### G3 — Context column gates (W2)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G3.1 | Earnings proximity column + filter (needs B2) | P+D | Agent 2 ships earnings column against fixtures. Agent 3 ships B2 earnings cache. Live data matches Finnhub for 5 tickers. | OPEN — Agent 2 fixtures, Agent 3 proposal |
| G3.2 | Sector/industry filter (needs B2) | P+D | Agent 2 ships sector filter against fixtures. Agent 3 ships B2 sector map. Live data matches Finnhub profile2 + static map for 5 tickers. | OPEN — Agent 2 fixtures, Agent 3 proposal |
| G3.3 | ΔOI column (needs B1) | P+D | Agent 2 ships ΔOI column against fixtures. Agent 3 ships B1 cadence. Live ΔOI matches exchange truth on 5 contracts. | OPEN — Agent 2 fixtures, Agent 3 proposal (B1) |
| G3.4 | Strategy badge (needs B1, non-directional) | P+D | Agent 2 ships strategy badge against fixtures. Agent 3 ships B1 cadence. Badge identifies spreads/straddles without claiming direction. | OPEN — Agent 2 fixtures, Agent 3 proposal (B1) |

**Decision:** Agent 2 ships W2 context columns against fixtures first. Agent 3 ships B1/B2 backend. Agent 4 evaluates context column accuracy. Agent 1 approves when fixtures pass + backend lands + eval passes.

---

### G4 — Workflow surface gates (W3)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G4.1 | Chart modal v1 (contract history + Net Premium only) | P | Agent 2 ships ChartModal with 2 views. Tests pass (opens from row, values match tape). | OPEN — Agent 2 to ship |
| G4.2 | Tracker v1 (bookmark + live P/L + 6 statuses) | P | Agent 2 ships Tracker. Tests pass (P/L within tick of mark). Close detection is proxy-labeled. | OPEN — Agent 2 to ship |
| G4.3 | Flow highlighting (Size>OI yellow, Vol>OI purple) | P | Agent 2 ships highlighting. Tests pass (100% fire on synthetic fixtures, OI=0 edge documented). | OPEN — Agent 2 to ship |
| G4.4 | One per-tab config substrate | P | Agent 2 ships TabConfig. Tests pass (survives reload, 10-tab perf unchanged, CSV round-trips). | OPEN — Agent 2 to ship |

**Decision:** Agent 2 ships W3 workflow surfaces. Agent 4 evaluates tracker + chart modal. Agent 1 approves when tests pass + eval passes.

---

### G5 — History-backed view gates (W4)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G5.1 | NetPremium trend (5d/7d/14d/30d) | P+D | Agent 2 ships against fixtures. Agent 3 ships B1 cadence. Live trend reproduces from snapshots. | OPEN — Agent 2 fixtures, Agent 3 proposal (B1) |
| G5.2 | Strike distribution (histogram) | P+D | Agent 2 ships against fixtures. Agent 3 ships B1 cadence. Live distribution reproduces from snapshots. | OPEN — Agent 2 fixtures, Agent 3 proposal (B1) |
| G5.3 | Vol/OI 14d footer table | P+D | Agent 2 ships against fixtures. Agent 3 ships B1 cadence. Live table reproduces from snapshots. | OPEN — Agent 2 fixtures, Agent 3 proposal (B1) |
| G5.4 | Feed tabs (up to 10 tabs, !exclude) | P | Agent 2 ships feed tabs. Tests pass (10-tab perf unchanged, !exclude works). | OPEN — Agent 2 to ship |
| G5.5 | Results cap (50/100/250/500) | P | Agent 2 ships results cap. Tests pass. | OPEN — Agent 2 to ship |
| G5.6 | Sort (Time/Premium/Size, $25K floor on non-Time) | P | Agent 2 ships sort. Tests pass ($25K floor enforced). | OPEN — Agent 2 to ship |
| G5.7 | CSV export (filters, timestamp, columns, honest missing) | P | Agent 2 ships CSV export. Tests pass (round-trips, honest missing values). | OPEN — Agent 2 to ship |

**Decision:** Agent 2 ships W4 against fixtures until B1 lands. Agent 3 ships B1 cadence (critical path). Agent 4 evaluates history view accuracy. Agent 1 approves when fixtures pass + B1 lands + eval passes.

---

### G6 — Signed score spec + backtest gates (W5)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G6.1 | Signed score spec (-100..+100, DISPLAY-ONLY) | E+R | Agent 4 writes spec. Agent 2 implements display. Sign matrix + magnitude weights + boundary cases documented. NOT alert-gating. | OPEN — Agent 4 to write spec |
| G6.2 | Score boundary case tests | P | Agent 2 ships score tests. -100, 0, +100, no-quote, zero OI, missing IV, put-ASK hedge, 0DTE volOI>=2 all pass. | OPEN — Agent 2 to ship |
| G6.3 | Backtest harness (Databento credits, P1 funding gate) | E | Agent 4 writes backtest design. P1 funding required for Databento credits. Sharpe-gated reports per ADR-0001. | OPEN — AWAITING P1 FUNDING |
| G6.4 | Remaining 3 modal views (scope creep) | P | Only if time permits. Agent 2 may ship if W1-W7 are complete. | DEFERRED — not required |

**Decision:** Agent 4 writes score spec + evaluator fixtures. Agent 2 implements score display (if spec is complete). Backtest harness is DEFERRED until P1 funding lands. Agent 1 approves score display when spec + tests pass. Backtest is a separate gate.

---

### G7 — Methodology surface gates (W7)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G7.1 | Starter tab presets (Broad $100K + High-Conviction Sweeps) | P | Agent 2 ships TabPresets. Tests pass (fresh profile opens with both tabs). | OPEN — Agent 2 to ship |
| G7.2 | In-modal investigation checklist (6 steps + verdict) | P | Agent 2 ships checklist. Tests pass (6 steps checkable, verdict persisted). | OPEN — Agent 2 to ship |
| G7.3 | Funnel empty-states (0 rows — widen shortage) | P | Agent 2 ships funnel empty-states. Tests pass (each widen action widens row count). | OPEN — Agent 2 to ship |
| G7.4 | Dark-pool levels overlay (post-B3, WISH) | P+D | Agent 2 ships overlay spec-only until B3 lands. If B3 never lands: stays spec-only. | DEFERRED — needs B3 + FINRA auth |
| G7.5 | Right-click row actions (filter, exclude, track) | P | Agent 2 ships right-click menu. Tests pass (actions mutate filters). | OPEN — Agent 2 to ship |
| G7.6 | Pulse sort floor quirk ($25K on non-Time sorts) | P | Agent 2 ships sort floor. Tests pass. | OPEN — Agent 2 to ship |

**Decision:** Agent 2 ships W7.1-W7.3, W7.5-W7.6. W7.4 is DEFERRED until B3 + FINRA auth. Agent 4 evaluates methodology surfaces. Agent 1 approves when tests pass + eval passes.

---

### G8 — Backend proposal gates (B1-B9)

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G8.1 | B1 snapshot cadence (Mongo↔DuckDB, file-backed) | D | Agent 3 ships proposal + implementation. Cadence thread starts on restart. DuckDB persists snapshots. Query contract matches CR-01. | OPEN — Agent 3 to propose + ship |
| G8.2 | B2 earnings cache + sector map | D | Agent 3 ships proposal + implementation. Finnhub cache with TTL. Frontend endpoints match CR-02. | OPEN — Agent 3 to propose + ship |
| G8.3 | B3 FINRA Reg SHO / Dark Pool ETL | D | Agent 3 ships proposal. FINRA auth path declared. Reg SHO MNS ingested. Dark pool trades attributed (NO fabricated direction). W7.4 overlay data contract matched. | OPEN — Agent 3 to propose (may be WISH if no FINRA auth) |
| G8.4 | B5 min volume alignment | D | Agent 3 ships proposal. MIN_VOLUME threshold declared. Backend data respects same threshold as frontend. | OPEN — Agent 3 to propose |
| G8.5 | B6 quiet accumulation alert (proposal only) | E | Agent 3 ships proposal. Agent 4 evaluates. Agent 1 triages via gate plan. | OPEN — proposal only, no code commitment |
| G8.6 | B7 outcome tracking (partial code exists) | D | Agent 3 inspects existing code + ships proposal if enhancing. Agent 2 ships tracker localStorage-first regardless. | OPEN — partial code exists, proposal optional |
| G8.7 | B8 citation hygiene (docstrings) | R | Agent 3 ships docstrings on backend services. Data provenance documented. | OPEN — documentation only |
| G8.8 | B9 O/S borrow inputs (proposal only) | E | Agent 3 ships proposal. Agent 4 evaluates. Agent 1 triages via gate plan. | OPEN — proposal only, no code commitment |

**Decision:** Agent 3 submits proposals for B1-B9. Agent 4 evaluates B6 and B9 (alert-type proposals). Agent 1 approves B1-B5, B7, B8 as feasibility gates (proposal → implementation if viable). Agent 1 evaluates B6 and B9 via alert gate economics.

---

### G9 — Evaluation gates

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G9.1 | Alert gate economics (all alert types) | E | Agent 4 writes alert gate economics doc. Each alert type has: false positive ceiling, confidence floor, cost estimate, fatigue risk. | OPEN — Agent 4 to write |
| G9.2 | Composite flow score evaluation | E | Agent 4 evaluates composite score methodology. Backtest results (if P1 funded). Score quality validated. | OPEN — Agent 4 to evaluate |
| G9.3 | Dark pool methodology evaluation | E | Agent 4 writes dark pool methodology doc. QUARTER-COW opacity model. Dark pool claims evaluated for directional language. | OPEN — Agent 4 to write |
| G9.4 | Scanner alert mechanism evaluation | E | Agent 4 evaluates scanner alert mechanism (webhook vs push, per-scan vs per-ticker). | OPEN — Agent 4 to evaluate |
| G9.5 | Filter economics analysis | E | Agent 4 evaluates filter subtractiveness. Filters reduce noise, not just move it. | OPEN — Agent 4 to write |
| G9.6 | Citation audit (all surfaces) | E | Agent 4 runs citation audit. No fabricated claims. Source attribution correct. Rating/score methodology honest. | OPEN — Agent 4 to run |
| G9.7 | Backtest evaluation (P1 funding gate) | E | Agent 4 runs backtest harness. Sharpe-gated reports per ADR-0001. Score quality validated against historical data. | DEFERRED — P1 funding gate |

**Decision:** Agent 4 writes all evaluation docs. Agent 1 approves when evaluations pass gate criteria. Backtest is DEFERRED until P1 funding.

---

### G10 — Research gates

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G10.1 | Source manifest | R | Agent 4 writes source manifest. All data sources documented with: source, access method, rate limits, freshness, lag, known biases. | OPEN — Agent 4 to write |
| G10.2 | Missing literature report | R | Agent 4 writes missing literature report. Topics where research is thin. Recommendations for future research. | OPEN — Agent 4 to write |
| G10.3 | Refuted claims audit | R | Agent 4 writes refuted claims audit. Claims that were made in earlier phases that are now known to be false or misleading. | OPEN — Agent 4 to write |
| G10.4 | Claim-rule map | R | Agent 4 writes claim-rule map. Each claim in Tidehunter Pro surfaces mapped to its evidence level (KNOWN / LIKELY / HEURISTIC / PROHIBITED). | OPEN — Agent 4 to write |

**Decision:** Agent 4 writes all research docs. Agent 1 approves when research passes gate criteria.

---

### G11 — Agent integration gates

| ID | Name | Type | Criteria | Status |
|---|---|---|---|---|
| G11.1 | Lane discipline | A | All agents stay within their lanes. No agent edits files outside its ownership. LANE_MAP.md enforced. | OPEN — Agent 1 to enforce |
| G11.2 | Contract satisfaction | A | All CR-01 through CR-16 contract requests satisfied per their criteria. | OPEN — Agent 1 to track |
| G11.3 | Sub-agent environment | A | AGENT_RUNBOOK.md written. All agents have run commands, test commands, ports, env vars, skills. | OPEN — Agent 1 to write |
| G11.4 | Integration verification | A | INTEGRATION_CHECKLIST.md written. All integration points verified. | OPEN — Agent 1 to write |

**Decision:** Agent 1 enforces lane discipline + contract satisfaction + sub-agent environment + integration verification. These are Agent 1's core responsibilities.

---

## Gate decision authority

| Gate type | Who evaluates | Who approves | Who can override |
|---|---|---|---|
| D (Data) | Agent 3 + Agent 4 | Agent 1 | Agent 1 (gatekeeper) |
| P (Product) | Agent 2 + Agent 4 | Agent 1 | Agent 1 (gatekeeper) |
| E (Evaluation) | Agent 4 | Agent 1 | Agent 1 (gatekeeper) |
| R (Research) | Agent 4 | Agent 1 | Agent 1 (gatekeeper) |
| A (Agent) | Agent 1 | Agent 1 | N/A (Agent 1 is the authority) |

**Rule:** Agent 1 is the gatekeeper for all gates. Agent 1 can approve, defer, reject, or request re-evaluation. Agent 1's decision is final for Phase 9.

---

## Gate state tracking

Agent 1 updates gate state in this document when:
- A gate is evaluated (status: OPEN → PASSING / FAILING / DEFERRED)
- A gate criterion is satisfied (status: OPEN → PASSING)
- A gate fails (status: OPEN → FAILING, with reason)
- A gate is deferred (status: OPEN → DEFERRED, with reason)
- A gate is resolved (status: PASSING/FAILING/DEFERRED → CLOSED)

**Gate state legend:**
- **OPEN:** Gate not yet evaluated. Criteria not yet satisfied.
- **PASSING:** Gate criteria satisfied. Gate is passing.
- **FAILING:** Gate criteria not satisfied. Gate is failing. Reason recorded.
- **DEFERRED:** Gate deferred to later milestone or external dependency. Reason recorded.
- **CLOSED:** Gate resolved. No longer active.

---

## Gate decision log

Agent 1 records all gate decisions here with date, decision, and rationale.

| Date | Gate | Decision | Rationale |
|---|---|---|---|
| 2026-09-03 | G0.1-G0.3 | DEFERRED to Agent 3 spike | Agent 3 to check OPTION instrument_type, OpenTerminalUI, yfinance fields |
| 2026-09-03 | W6 reorder (W6 before W2) | APPROVED | Filters are frontend-only, operate on existing data. Context columns need backend data. Filter-first is correct. |
| 2026-09-03 | W3 modal scope (2 views, not 5) | APPROVED | 2 views (contract history + Net Premium) is Phase 9 scope. Remaining 3 are W5 if time permits. |
| 2026-09-03 | W7.4 dark pool overlay | DEFERRED | Requires B3 FINRA ETL + FINRA auth. Specced here, built after B3 lands. Stays WISH if no FINRA auth. |
| 2026-09-03 | B6 quiet accumulation alert | DEFERRED to evaluation | Agent 3 proposes, Agent 4 evaluates, Agent 1 triages via alert gate economics. Not a code commitment. |
| 2026-09-03 | B9 O/S borrow inputs | DEFERRED to evaluation | Agent 3 proposes, Agent 4 evaluates, Agent 1 triages via gate plan. Not a code commitment. |
| 2026-09-03 | Backtest harness (P1 funding) | DEFERRED | Databento credits require P1 funding. Sharpe-gated reports per ADR-0001. Awaiting funding. |
| 2026-09-03 | Agent 3 lane owner | NOT GRANTED YET | Agent 3 is PROPOSAL_ONLY by default. Agent 1 will grant BACKEND_LANE_OWNER=1 for specific contracts when ready. |

---

## Gate plan maintenance

Agent 1 updates this gate plan when:
- A new gate is identified
- A gate state changes
- A gate decision is made
- A new Phase 9 deliverable introduces new gates

Agent 4 updates this gate plan when:
- An evaluation identifies a new gate
- An evaluation changes a gate's criteria or status

Agent 2 updates this gate plan when:
- A product feature ships that changes the gate state

Agent 3 updates this gate plan when:
- A backend proposal ships that changes the gate state

---

## Gate plan summary

| Gate type | Count | Gates |
|---|---|---|
| D (Data) | 7 | G0.1, G0.2, G0.3, G3.1, G3.2, G3.3, G3.4, G5.1, G5.2, G5.3, G8.1, G8.2, G8.3, G8.4, G8.6 |
| P (Product) | 33 | G1.1, G1.2, G1.3, G2.1-G2.14, G3.1, G3.2, G3.3, G3.4, G4.1, G4.2, G4.3, G4.4, G5.4, G5.5, G5.6, G5.7, G6.2, G7.1, G7.2, G7.3, G7.4, G7.5, G7.6 |
| E (Evaluation) | 7 | G6.1, G6.3, G8.5, G8.8, G9.1, G9.2, G9.3, G9.4, G9.5, G9.6, G9.7 |
| R (Research) | 4 | G6.1, G8.7, G10.1, G10.2, G10.3, G10.4 |
| A (Agent) | 4 | G11.1, G11.2, G11.3, G11.4 |

**Total gates:** 55 (some gates span multiple types)

**Open gates:** 55 (none yet evaluated — Phase 9 just started)

**Deferred gates:** G6.3 (backtest, P1 funding), G7.4 (dark pool overlay, B3+FINRA), G0.1-G0.3 (spike, Agent 3 to check), B6 (alert proposal, eval-first), B9 (proposal, eval-first)

**Gate plan status:** Gate A PASSED 2026-09-04T01:00Z (be97bd2); Gate B PENDING (Agent 2 cold, critical path); Gate C PENDING (awaits Gate B). Liveness protocol: re-verify hourly, timestamp state changes, triage RFCs same-day. Proof: commits on phase9/agent1-architect within the hour.

---

## MERGE GATES (2026-09-04, Agent 1 gatekeeping — three merges, exact commands)

**Law to enforce at every gate (RISK_REGISTER R25 / DECISIONS D20):**

> "Chain data flows ONLY through fetch_chain_from_public_api (60s TTL) or CacheRouter (300s). No new per-ticker Public pollers. No cadence shortening. Frontend never calls Public directly. Violations fail the gate."

### Gate A — Agent 3 rebase/push — PASSED 2026-09-04T01:00Z (be97bd2, 0 ahead, R3 retired)

**Status: PASSED 2026-09-04T01:00Z — tidehunter 0 ahead of origin/main, be97bd2 verified (zero conflicts, zero overlap with d222dee). Any lane still 'awaiting Gate A' is stale — proceed.**

**Original precondition (for record):** Working tree clean, upstream fetched, rebase-not-merge, never force-push.

```
# from tidehunter worktree (verify worktree path first)
git fetch origin
git rebase origin/main   # not merge; resolve, do not force-push
git log --oneline origin/main..HEAD   # expect 4 SHIP commits — now 0 (landed to be97bd2)
git diff --name-only origin/main..HEAD   # expect backend-only — now 0 (landed)
# tests per lane:
cd backend && .venv/bin/python3 -m pytest -q   # backend green (or targeted suite per proposal)
cd frontend && npx craco test --watchAll=false  # frontend still green (untouched, but verify no regression)
# honest-copy audit (blocks merge):
grep -R -i "dark pool.*buy\|dark pool.*sell\|VPIN\|OPRA.*print" frontend/ backend/ --include="*.jsx" --include="*.js" --include="*.py" | grep -v "honest-empty\|proxy\|prohibited" # expect 0
grep -R "Key Moment\|Earnings Hub\|1.2x.*booster" .planning/ --include="*.md" | grep -v "honest-empty\|no_api_surface" # expect 0
```

Owner: Agent 3 proposes, Agent 1 signs off. Never `git push --force`.

### Gate B — Agent 2 compose (W8 mount + wire, d222dee + W8) — PENDING (owner cold, see ROADMAP Gate Board)

**Acceptance (W8 exit-gate metrics, exact commands + thresholds):**

- All 39 modules mounted in `FlowseekerProBlademap.jsx` shell, no `frontend/src/App.js` diff.
- Full frontend suite: `cd frontend && npx craco test --watchAll=false` → 0 failures, 40 suites / 291 baseline preserved + new wave tests.
- 6-states checklist per surface (loading/empty/stale/error/frozen/no-quote) — fixtures prove each state, checklist attached to W8 report.
- Honest-copy audit: zero dark-pool side / OPRA print / VPIN claims (greps below must be 0).
- R1 honest-empty: `aiCatalyst/scoreBooster` = {available:false, reason:"no_api_surface"} where applicable, scoreBooster fixed 1.0.


```
git diff --name-only origin/main..HEAD | grep -q "frontend/src/App.js" && echo "FAIL: App.js diff" || echo "OK"
# verify 39 modules still present:
find frontend/src/components/flowseeker -type f | wc -l   # expect >=39
cd frontend && npx craco test --watchAll=false   # full suite green
# 6-states + honest-copy audits:
grep -R "Key Moment\|Earnings Hub" frontend/ --include="*.jsx" | grep -v "honest-empty\|no_api_surface" # expect 0
# per GATE_PLAN 6-gate loop: states-per-surface checklist attached to report
```

Gate is `WAVE_STATE.md: W8 Exit Gate` + Agent 1 sign-off. No App.js diff.

### Gate C — Final integration sign-off (both lanes + Agent 4 eval) — PENDING (awaits Gate B)

**Commands:**

```
# rebase both onto main in dependency order (Agent 3 first, then Agent 2 W8 on top), or merge via PR with Agent 1 approval
cd backend && .venv/bin/python3 -m pytest -q
cd frontend && npx craco test --watchAll=false
# backend untouched check if Agent 3 already merged:
git diff --name-only origin/main..HEAD -- backend/ | wc -l   # inform, not block
# final grep sweeps (1-pager evidence in report):
grep -R -i "possibly delisted" backend/services/*.py | head # expect only yfinance noise, not product claims
```

Honest-copy audit blocks Gate C: any dark-pool side, OPRA print-tape, or VPIN-from-snapshots claim fails.

