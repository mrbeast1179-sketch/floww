# Risk Register — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

## How to read

| Field | Meaning |
|---|---|
| **ID** | Short identifier |
| **Category** | data / product / integration / process / security / compliance |
| **Severity** | P0 = blocks core delivery / P1 = degrades quality / P2 = manageable risk / P3 = future concern |
| **Lane** | Which agent owns the risk (A1=Architect, A2=Frontend, A3=Backend, A4=Research) |
| **Status** | OPEN / MONITORING / MITIGATED / DEFERRED WINDOW |
| **Expiry** | When the monitoring window closes (e.g., `until B1 merged`, `until W1 shipped`) |

---

## Data risks

### RD-01 — Snapshot chains, NOT print tape (P0, A1/A3, OPEN)

**Description:** Tidehunter Pro's new data foundation (Public API + snapshot chains) does NOT provide a true print tape. No OPRA feed. No signed prints. No true multi-exchange sweep visibility.

**Impact:** All flow surfaces built on this data inherit the same fundamental limitation. Any claim of sweep visibility, signed direction, or true venue attribution is a bug.

**Mitigation:**
- Non-negotiable data reality statement enforced in CONTRACTS.md and Front-End Data Spec
- Every surface that infers side from last-vs-bid/ask is labeled with its inference method
- No sweep classification anywhere unless true venue data exists (W6 sweep filter chip is labeled "sweep proxy")
- VPIN-from-snapshots is prohibited

**Status:** OPEN (structural reality, not a bug to fix — a constraint to design around)

---

### RD-02 — Dark pool prints have no side/direction (P0, A1/A3/A4, OPEN)

**Description:** Dark pool prints have no side and no direction. Any copy claiming dark pool "buying" or "selling" is a bug. Anything claiming confirmed buyer/seller identity is a bug.

**Impact:** If any Tidehunter Pro surface claims dark pool directional activity without true venue data, it is generating fake positives — exactly the problem this Phase 9 is trying to solve.

**Mitigation:**
- Dark pool methodology in `eval/` references the QUARTER-COW opacity model
- All dark pool surfaces in Phase 9 are labeled with opacity level
- W7.4 dark pool overlay is spec-only until CR-03 FINRA ETL lands
- Agent 4 runs citation audit for dark pool claims (no directional language permitted)

**Status:** OPEN

---

### RD-03 — SIDE inferred from last-vs-bid/ask (P1, A1/A3, OPEN)

**Description:** Side (buy/sell) is inferred from whether the last price crossed the bid or ask. This is an inference, not a signed print. In fast markets or with wide spreads, inference is unreliable.

**Impact:** Any flow surface that treats inferred side as ground truth will produce false classifications. This is the core reason Tidehunter Pro has "fake positives" — side inference on snapshot data is noisy.

**Mitigation:**
- All side labels in Phase 9 surfaces are labeled with inference method
- Side is a derived field, not a raw field
- Scanner/Alert logic treats side as a signal, not a fact
- Agent 4 writes methodology doc for side inference and its failure modes

**Status:** OPEN (structural reality)

---

### RD-04 — Sweep classification is a proxy (P1, A1/A3, OPEN)

**Description:** Sweep classification (large orders split across venues) requires true multi-exchange sweep visibility. Without OPRA feed or true venue data, sweep classification is a proxy — usually: large size relative to OI + unusual time + multiple legs.

**Impact:** The "sweep" label on any trade is a proxy classification, not a confirmed sweep. Calling proxy sweeps "sweeps" without qualification is a fake positive.

**Mitigation:**
- W6 sweep-only filter chip is labeled "sweep proxy"
- Sweep classification methods documented in contracts
- No sweep claim without qualification of proxy status

**Status:** OPEN

---

### RD-05 — Public API data availability/freshness (P1, A1/A3, OPEN)

**Description:** The Public.com API provides the new data foundation. Its availability, freshness, and data completeness are outside Tidehunter Pro's control. If the API is down, rate-limited, or returns stale data, Phase 9 surfaces degrade.

**Impact:** All new institutional-grade surfaces depend on this data source. If it degrades, the product degrades.

**Mitigation:**
- CR-04 (B5 min volume alignment) ensures backend respects data freshness
- Frontend "building n over 20" honest-empty state communicates data accumulation status
- Agent 3's proposal must document API availability assumptions
- Agent 4 evaluates data source in Source manifest

**Status:** MONITORING

---

### RD-06 — Finnhub rate limits for earnings/sector data (P2, A1/A3, OPEN)

**Description:** Agent 2 proposes calling Finnhub /calendar/earnings + /profile2 inline. Finnhub free tier has rate limits. If called inline at scan cadence, this could violate >1/min.

**Impact:** If Finnhub calls are blocked, earnings proximity + sector filters don't work. W2.1/W2.2 degrade to fixtures-only.

**Mitigation:**
- CR-02 (B2 earnings cache) proposes a backend cache with TTL
- Agent 3's proposal must address rate limits
- Agent 2 can ship W2.1/W2.2 against fixtures even if backend cache doesn't land
- If Finnhub is fully unavailable: W2.1/W2.2 ship fixture-only with documented limitation

**Status:** MONITORING

---

### RD-07 — yfinance reliability for WTI (P2, A1/A3, MONITORING)

**Description:** Existing backend `wti_vol.py` uses yfinance for WTI CL=F + ^OVX. yfinance is a free/unreliable data source. WTI HAR-IV forecast depends on it.

**Impact:** If yfinance is down or returns bad data, WTICrude v1/v2 surfaces degrade. Existing system already handles this with try/except.

**Mitigation:**
- Existing backend has try/except around yfinance calls
- No change needed for Phase 9 (WTI is existing surface, not new)
- Agent 1 notes this as a known limitation, not a Phase 9 risk

**Status:** MITIGATED (existing try/except)

---

### RD-08 — Mongo snapshot availability for B1 (P2, A1/A3, OPEN)

**Description:** B1 snapshot cadence requires Mongo snapshot data to exist. If the Mongo collection is empty, freshly created, or missing the expected schema, B1 can't build the DuckDB cadence.

**Impact:** B1 cadence thread can't start until Mongo has snapshot data. If Mongo is empty, Phase 9 history-backed views (W4.1-W4.3) stay fixture-first longer.

**Mitigation:**
- CR-01 (B1 cadence) requires Agent 3 to verify Mongo snapshot availability
- If Mongo is empty: Agent 3's proposal must state this and propose a path to populate it
- Agent 2 ships W4.1-W4.3 against fixtures until B1 is live
- Mongo promotion gate `TICK-SNAPSHOT-BACKEND` in test runner handles this

**Status:** OPEN (depends on Mongo state, which Agent 3 must verify)

---

## Product risks

### RP-01 — Fake positives from score/algorithm misuse (P0, A1/A2/A4, OPEN)

**Description:** The existing Tidehunter Pro surfaces have "a lot of fake positives." The user explicitly wants Blademap AI-quality flow surfaces with "a couple of alert but good ones on all stocks." If Phase 9 ships surfaces that produce the same fake positives, the Phase 9 goal is not met.

**Impact:** Phase 9 fails its primary objective if it doesn't reduce fake positives.

**Mitigation:**
- Alert gate economics in `eval/` defines alert quality thresholds
- Composite flow score (Engine Handoff) gates alerts, not raw trade volume
- Scanner gates (≥250K premium, ≥200 size ratio, TTM squeeze, OR score≥60) filter noise
- Front-End Data Spec enforces sparse single-ticker scanning
- W6 filters give users tools to reduce noise
- Agent 4 evaluates every alert type for false positive rate before it ships
- No marketing language ("hot", "massive", "insane") in scanner/alert surfaces

**Status:** OPEN (the core problem Phase 9 is solving)

---

### RP-02 — Alert fatigue from low-quality alerts (P1, A1/A2/A4, OPEN)

**Description:** If Phase 9 ships too many low-quality alerts, users will ignore them. Alert fatigue is the enemy of institutional-grade flow surfaces.

**Impact:** Users lose trust in Tidehunter Pro alerts. Phase 9's "couple of alert but good ones" goal is undermined.

**Mitigation:**
- Alert gate economics defines alert quality thresholds (false positive ceiling, confidence floor, cost estimate)
- Alert count ceiling (no high-volume low-quality alerts)
- Alert quality hierarchy: Institutional > Conviction > Standard (consistent quality signal)
- Agent 4 evaluates every alert type before it ships
- Front-End Data Spec requires every alert type to have a documented methodology + expected quality

**Status:** OPEN

---

### RP-03 — 3520+ file changes from merge conflict (P1, A1, OPEN)

**Description:** Agent 2 already shipped W1-W7 on main with 3520+ new/modified files. If Agent 1 or Agent 3 tries to edit files that Agent 2 touched, merge conflicts are likely. The main branch now contains Agent 2's code.

**Impact:** Concurrent work on main could cause conflicts. The 4-branch strategy exists to avoid this.

**Mitigation:**
- 4-branch isolation strategy (Agent 1 on phase9/agent1-architect, Agent 2 on phase9/agent2-frontend-flow, etc.)
- Each agent's lane ownership enforced in LANE_MAP.md
- Agent 1 does NOT write product code — its deliverables are planning files only
- Agent 3 is PROPOSAL_ONLY by default — no backend edits unless BACKEND_LANE_OWNER=1
- Agent 4 writes to `.planning/research/` and `.planning/eval/` — no product code
- CR-09 documents that Agent 2's pathmap + tests are already committed on main

**Status:** OPEN (process risk, mitigated by branch strategy)

---

### RP-04 — Monolith decomposition risk (P1, A2, DEFERRED)

**Description:** Agent 2 already decomposed the 1954-line `FlowseekerProBlademap.jsx` monolith and shipped W1-W7 on main. If Agent 2 needs to further decompose or refactor, the risk is that the decomposition introduces bugs in existing surfaces.

**Impact:** Existing Tidehunter Pro surfaces (Smart Order Flow, Dealer Positioning, WTI, Stat-Arb Pairs, Scanner) could break during decomposition.

**Mitigation:**
- Agent 2's `agent2-frontend.md` has the test runner + 13 test files
- Agent 2's `agent2-pathmap.md` documents the decomposition
- All new features ship against fixtures first
- Existing surfaces are not in scope for Phase 9 (they are the baseline to improve upon, not replace)

**Status:** MITIGATED (Agent 2 already handled decomposition; tests in place)

---

### RP-05 — Scope creep: 5 modal views, 3520 files, Blademap parity (P2, A1, OPEN)

**Description:** The Phase 9 scope is large: 5 chart modal views, full scanner, tracker, filters, history views, dark pool overlay, signed score, alert gating, evaluation suite, 3520+ files. "Blademap parity" is aspirational.

**Impact:** If Phase 9 tries to deliver everything, delivery quality suffers. The user wants "a couple of alert but good ones on all stocks" — not every possible feature.

**Mitigation:**
- Phase 9 scope is defined in WAVE_STATE.md — not everything ships in Phase 9
- W3.1 ships 2 modal views (contract history + Net Premium) — remaining 3 are W5 if time permits
- W7.4 dark pool overlay is WISH (requires FINRA auth)
- B6 quiet accumulation alert is PROPOSAL ONLY
- B9 O/S borrow inputs is PROPOSAL ONLY
- Alert quality > alert quantity (user's stated preference)
- Agent 1's gate plan controls what ships and what is deferred

**Status:** OPEN (scope management is Agent 1's job)

---

### RP-06 — Composite flow score complexity (P2, A1/A2/A4, OPEN)

**Description:** The composite flow score (Engine Handoff, E1-E22) is complex. It combines side signals, option metrics, dark pool signals, statistical signals, and market regime signals into a score from -100 to +100. If the score is too complex, it becomes a black box that users don't understand.

**Impact:** A black-box score that users don't trust is worse than no score at all. It could also produce fake positives if the score components are misaligned.

**Mitigation:**
- Agent 4 writes the composite score methodology doc
- Score components are unit-tested (sign matrix, magnitude weights, boundary cases)
- Score is DISPLAY-ONLY (not alert-gating) — alerts use composite score via Engine Handoff Gate C18
- Score components are inspectable (each component produces a value that can be shown)
- Agent 4 runs backtest evaluation (P2 funding gate) to validate score quality

**Status:** OPEN

---

### RP-07 — Tracker close detection proxy limitation (P2, A2, OPEN)

**Description:** Tracker close detection is a proxy based on OI drift/volume (labeled as proxy). It's not a confirmed close. If the proxy is wrong, tracker P/L is wrong.

**Impact:** Tracker P/L accuracy degrades if close detection proxy is noisy. Users may see incorrect P/L on tracked positions.

**Mitigation:**
- Close detection is labeled as proxy in UI
- Live P/L uses mid → last → stale mark price (accurate to mark)
- Agent 2 documents the proxy limitation
- Agent 4 evaluates close detection proxy in eval fixtures
- B1 snapshot cadence (if it lands) provides better OI drift data for close detection

**Status:** MONITORING

---

## Integration risks

### RI-01 — Frontend-backend contract drift (P1, A1/A2/A3, OPEN)

**Description:** Agent 2's frontend expects certain data shapes from the backend. Agent 3's backend proposals may change those shapes. If contracts drift, frontend breaks.

**Impact:** Frontend-backend integration breaks. Phase 9 surfaces don't work.

**Mitigation:**
- CONTRACTS.md defines precise JSON/TypeScript-style schemas for every data shape
- Each contract is a cross-lane agreement (CR-01 through CR-10)
- Agent 2 ships against fixtures first — fixtures encode the contract
- Agent 3's proposals must satisfy the contract before Agent 2 wires live
- Agent 1's contract requests define the integration boundaries

**Status:** OPEN (managed by contract system)

---

### RI-02 — Agent 2 fixtures vs. live data mismatch (P2, A1/A2/A3, OPEN)

**Description:** Agent 2 ships W1-W7 against fixtures first. If the fixtures don't match what the live backend returns, surfaces break when wired live.

**Impact:** Phase 9 surfaces work in tests but break in production.

**Mitigation:**
- Agent 4's evaluator fixtures validate that live data matches expected contract
- Agent 3's proposals must document the exact data shape
- Agent 2's fixtures are the contract — if live data diverges, fixtures are updated
- Mongo promotion gate `TICK-SNAPSHOT-BACKEND` controls when W4 wires live

**Status:** MONITORING

---

### RI-03 — Branch isolation failure (P1, A1, OPEN)

**Description:** The 4-branch strategy isolates agents. If an agent edits files outside its lane, it creates conflicts for other agents. Agent 1 already wrote LANE_MAP.md to enforce this.

**Impact:** Merge conflicts, broken code, wasted work.

**Mitigation:**
- LANE_MAP.md defines ownership + forbidden files per agent
- Agent 1 enforces lane discipline (no product code, no App.js, no backend)
- Agent 3 is PROPOSAL_ONLY by default
- Agent 4 writes to `.planning/` only
- Agent 2's lane is frontend flowseeker only
- CR-09 documents Agent 2's pathmap so other agents know what files are in Agent 2's lane

**Status:** OPEN (enforced by Agent 1)

---

### RI-04 — MAIN_DOCUMENTATION.md staleness (P2, A1, MONITORING)

**Description:** Agent 4's research doc says "MAIN_DOCUMENTATION.md is the primary doc for running Hermes agents on floww" but Agent 1's repo inspection found `AGENT_RUNBOOK.md` instead. If documentation is stale, agents waste time reading wrong docs.

**Impact:** Agents read wrong documentation, waste time, or miss critical setup steps.

**Mitigation:**
- Agent 1's CR-12 (AGENT_RUNBOOK.md) documents the sub-agent environment
- Agent 1's CR-11 (sub-agent scaffold) covers tools + tests + ignore + env docs
- Agent 1 notes the discrepancy in RISK_REGISTER.md
- Agent 4's research doc is updated to reference AGENT_RUNBOOK.md instead of MAIN_DOCUMENTATION.md (if Agent 4 is still active)

**Status:** MONITORING (documentation staleness is a known issue)

---

## Process risks

### RP-01 — 3520+ file merge conflict risk (see RP-03 above, already covered)

---

### RP-02 — Agent 1 scope: planning only, no product code (P2, A1, OPEN)

**Description:** Agent 1's role is Architect/Orchestrator/Gatekeeper. It does NOT write product code. If Agent 1 needs to write code to validate a decision or test a contract, it must do so in planning files only (e.g., eval fixtures, contract specs, decision records).

**Impact:** Agent 1 cannot directly test product code. It must rely on Agent 2's tests and Agent 4's evaluations.

**Mitigation:**
- Agent 1's deliverables are planning files (LANE_MAP.md, PATHMAP.md, DECISIONS.md, CONTRACTS.md, WAVE_STATE.md, GATE_PLAN.md, RISK_REGISTER.md, CONTRACT_REQUESTS.md, INTEGRATION_CHECKLIST.md, reports/agent1-architect.md)
- Agent 1 can write eval fixtures + methodology docs in `.planning/research/` and `.planning/eval/`
- Agent 1 does NOT write product code in `frontend/` or `backend/`

**Status:** OPEN (by design — Agent 1 is a planning agent)

---

### RP-03 — Agent 3 PROPOSAL_ONLY default (P2, A1, OPEN)

**Description:** Agent 3 (backend) is PROPOSAL_ONLY by default unless Agent 1 explicitly marks it as the backend lane owner. This means Agent 3 writes proposals, not code, unless Agent 1 grants permission.

**Impact:** Backend changes for Phase 9 (B1-B9) may not land if Agent 3 stays in proposal mode. Phase 9 surfaces that depend on backend data (W2.1-W2.4, W4.1-W4.3, W7.4) stay fixture-first.

**Mitigation:**
- Agent 1's GATE_PLAN.md defines when Agent 3 moves from PROPOSAL_ONLY to lane owner
- Agent 1 can grant BACKEND_LANE_OWNER=1 for specific contracts
- Agent 3's proposals are evaluated by Agent 4 before any code commitment
- Agent 2 ships against fixtures until backend data is live

**Status:** OPEN (Agent 1 controls this via gate plan)

---

### RP-04 — Evaluation-first requirement (P2, A1/A4, OPEN)

**Description:** Phase 9 requires evaluation-first: every new feature, alert type, or methodology change must be evaluated before it ships. Agent 4 is responsible for evaluation.

**Impact:** If Agent 4 is slow or unavailable, Phase 9 delivery slows. Features wait for evaluation.

**Mitigation:**
- Agent 4's research doc defines the evaluation process
- Agent 1's GATE_PLAN.md defines evaluation gates
- Agent 2 ships against fixtures first — evaluation can happen in parallel with frontend work
- If Agent 4 is unavailable: Agent 1 can evaluate simple features (frontend-only) directly

**Status:** OPEN

---

## Security risks

### RS-01 — Public.com API key exposure (P1, A1/A3, OPEN)

**Description:** The Public.com API key is stored in environment variables. If the key is exposed in code, logs, or frontend bundle, it could be compromised.

**Impact:** Unauthorized trading or data access via the Public.com API.

**Mitigation:**
- Backend key is env-backed (never in code)
- Frontend only calls backend, not Public.com directly
- Agent 3's proposals must not embed API keys in code
- Agent 1's INTEGRATION_CHECKLIST.md includes a security check for key exposure

**Status:** MONITORING

---

### RS-02 — Frontend data exposure (P2, A1/A2, OPEN)

**Description:** Frontend surfaces display trade data, portfolio positions, and flow information. If sensitive data is exposed to unauthorized users, it's a security issue.

**Impact:** Data leakage, privacy violation.

**Mitigation:**
- Existing backend auth (JWT, ownership scoping) protects backend endpoints
- Frontend auth gating (if any) is Agent 2's responsibility
- Agent 1's INTEGRATION_CHECKLIST.md includes a security check for auth gating

**Status:** MONITORING

---

## Compliance risks

### RC-01 — Dark pool directional claims (P0, A1/A4, OPEN — see RD-02)

**Description:** Any claim of dark pool "buying" or "selling" without true venue data is a compliance risk. Regulators and sophisticated users will flag this as misleading.

**Impact:** Regulatory scrutiny, user trust loss, potential legal exposure.

**Mitigation:**
- Non-negotiable data reality: dark pool prints have no side/direction
- Dark pool surfaces labeled with opacity level
- Agent 4's citation audit flags any directional dark pool language
- W7.4 dark pool overlay is spec-only until CR-03 lands

**Status:** OPEN

---

### RC-02 — Sweep classification claims (P1, A1/A4, OPEN — see RD-04)

**Description:** Sweep classification without true multi-exchange visibility is a proxy. Calling proxy sweeps "sweeps" without qualification is misleading.

**Impact:** User trust loss, potential regulatory scrutiny if sweeps are used for trading decisions.

**Mitigation:**
- Sweep classification labeled as proxy
- No sweep claim without qualification
- Agent 4's methodology doc defines sweep proxy limitations

**Status:** OPEN

---

### RC-03 — Side inference claims (P1, A1/A4, OPEN — see RD-03)

**Description:** Side inferred from last-vs-bid/ask is an inference, not a signed print. Treating inferred side as ground truth is misleading.

**Impact:** User trust loss if side inference is wrong.

**Mitigation:**
- Side labels qualified with inference method
- Side is a derived field, not a raw field
- Agent 4's methodology doc defines side inference limitations

**Status:** OPEN

---

## Risk summary

| Severity | Count | Risks |
|---|---|---|
| P0 | 3 | RD-01 (snapshot chains), RD-02 (dark pool no direction), RP-01 (fake positives) |
| P1 | 8 | RD-03 (side inference), RD-04 (sweep proxy), RD-05 (API freshness), RP-02 (alert fatigue), RP-03 (merge conflicts), RI-01 (contract drift), RI-03 (branch isolation), RC-02 (sweep claims) |
| P2 | 10 | RD-06 (Finnhub rates), RD-07 (yfinance), RD-08 (Mongo), RP-05 (scope creep), RP-06 (score complexity), RP-07 (tracker proxy), RI-02 (fixture mismatch), RI-04 (doc staleness), RP-02 (A1 scope), RP-03 (A3 proposal-only), RS-01 (API key), RS-02 (data exposure), RC-03 (side claims) |

**P0 risks (3):** All are structural data reality constraints, not bugs to fix. They define the boundaries within which Phase 9 must operate.

**P1 risks (8):** All are manageable with mitigation. Agent 1's gate plan + Agent 4's evaluations are the primary mitigation.

**P2 risks (10):** All are future concerns or manageable with existing mitigation.

---

## Risk status summary

| Status | Count | Risks |
|---|---|---|
| OPEN | 18 | RD-01, RD-02, RD-03, RD-04, RD-05, RD-08, RP-01, RP-02, RP-03, RP-05, RP-06, RP-07, RI-01, RI-03, RP-02 (A1), RP-03 (A3), RS-01, RC-01, RC-02, RC-03 |
| MONITORING | 5 | RD-05, RD-06, RD-07, RI-02, RI-04, RS-01, RS-02 |
| MITIGATED | 2 | RD-07 (existing try/except), RP-04 (Agent 2 decomposition + tests) |
| DEFERRED WINDOW | 0 | — |

**OPEN risks (18):** These are the risks Agent 1 is tracking. Most are structural (data reality) or process (branch isolation, proposal-only default). Agent 1's gate plan + Agent 4's evaluations are the primary mitigation.

**MONITORING risks (5):** These are risks that are being watched but not actively mitigated beyond existing measures.

**MITIGATED risks (2):** These are risks that have been mitigated by existing code/process.

---

## Risk register maintenance

Agent 1 updates this risk register when:
- A new risk is identified
- A risk status changes (OPEN → MONITORING → MITIGATED → DEFERRED WINDOW)
- A risk is resolved (removed from register)
- A new Phase 9 deliverable introduces new risks

Agent 4 updates this risk register when:
- An evaluation identifies a new risk
- An evaluation changes a risk's severity or status

Agent 2 updates this risk register when:
- A frontend integration issue introduces a new risk
- A frontend feature ships that changes the risk profile

Agent 3 updates this risk register when:
- A backend proposal introduces a new risk
- A backend change ships that changes the risk profile
