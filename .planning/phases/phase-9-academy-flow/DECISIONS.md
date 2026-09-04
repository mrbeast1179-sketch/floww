# Decisions — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

## D1 — Pulse stays per-ticker; market breadth lives in Scanner

**Status:** LOCKED (from PLAN.md)

Pulse is per-ticker on Public API chains. Only rows with real bid/ask → real SIDE/PRICE. Market breadth lives in Scanner. `mkScanRow` has no bid/ask/mid — forcing scan rows into the tape would silently degrade the reference's core columns.

**Rationale:** The Public API `/api/public/chain/{ticker}` returns per-contract bid/ask/last/vol/OI/IV/greeks. That's enough for a real per-ticker Pulse. Scanner needs market-wide aggregation that only a backend `/scan` endpoint can provide. Mixing them corrupts both.

**Agent 2 implication:** Keep `mapPublicChainToRows` + `aggregatePulse` in PulseTape. ScannerTable gets its rows from a separate source (backend `/scan` or the 18-ticker `SCAN_UNIVERSE` fallback).

## D2 — Reference SIGNAL spec stands

**Status:** LOCKED (from PLAN.md, Phase 7)

ASK → BULLISH, including put-ASK with HEDGE? tag.

**Rationale:** This is the BladeMap reference contract. Put-ASK is often protective buying, not directional bullishness. The tape keeps BULLISH; the HEDGE? tag annotates the ambiguity. Changing this would break the reference contract and all existing fixture tests.

**Agent 4 implication:** Score spec sign matrix must respect D2. Put-ASK → BULLISH with HEDGE? tag, never BEARISH.

## D3 — Calibration is desk-controlled; every new signal ships with its evaluator

**Status:** LOCKED (from PLAN.md)

The desk owns thresholds. Every new signal ships WITH its evaluator from day one.

**Rationale:** Steal [3] — no signal without Performance_Evaluation. This prevents the "ship a signal, figure out if it works later" anti-pattern. The alert engine (`backend/services/alert_engine.py`) already has `eval_alert_rules` + `AlertManager` — evaluators are the pattern.

**Agent 2 implication:** Every new UI signal (sweep, block, unusual) must have a corresponding evaluator fixture in Agent 4's lane.

**Agent 3 implication:** Alert rule changes go through evaluators, not direct threshold edits.

## D4 — Per-tag 30-minute outcome tracking

**Status:** LOCKED (from PLAN.md)

Adopt per-tag 30-min outcome tracking in the outcomes module.

**Rationale:** Steal [1]. `backend/services/flow_outcomes.py` exists — this is partially real. The outcomes module needs per-tag hit-rate tracking with read-only calibration (no automatic threshold changes).

**Agent 3 implication:** B7 is the backend task. Agent 4 writes the evaluator fixtures.

## D5 — Dark pool ships as FINRA context panel only

**Status:** LOCKED (from PLAN.md)

Never a live tape on free data. Real-time TRF prints = paid gate. Dark pool prints have no side and no direction.

**Rationale:** Zhu 2014 (conditional) + Comerton-Forde-Putnins 2015 + BJZZ 2021 (scope-limited) all confirm: dark prints are unsigned execution footprints. FINRA ATS weekly + Reg SHO daily are the only free sources. TRF websocket = paid (Massive pattern).

**Agent 2 implication:** Dark pool UI must show: time, ticker, price, size, notional, sector, level, date. NO side, NO direction, NO buy/sell language.

**Agent 3 implication:** B3 builds FINRA ATS weekly + Reg SHO daily ETL. Top-N levels overlay = price-level clustering by notional, no direction.

## D6 — Greeks computed in-house

**Status:** LOCKED (from PLAN.md)

Never depend on vendor greeks.

**Rationale:** Tradier sandbox = delayed chains WITHOUT greeks. Real-time + hourly Greeks need a funded brokerage account. `backend/services/bs_calculator.py` exists for in-house BS calculation. `backend/services/greeks.py` likely has the aggregator.

**Agent 3 implication:** Greeks stay in-house. Tradier is a chain source only, not a greek source.

## D7 — One chain interface: yfinance → Tradier → Databento

**Status:** LOCKED (from PLAN.md)

Tradier verified: sandbox = delayed chains WITHOUT greeks; realtime + hourly Greeks need a funded brokerage account. In-house Greeks matter on every tier.

**Rationale:** Single adapter pattern. yfinance for free baseline, Tradier for delayed chains (no greeks), Databento for paid OPRA backfill → live OPRA.

**Agent 3 implication:** B1 cadence job should target one chain source (likely yfinance or Tradier sandbox) and be designed to swap sources later.

## D8 — Quiet accumulation gate: volume > 2 sigma AND price-range compression < 1 sigma

**Status:** LOCKED (from PLAN.md)

Display-first only. Requires baseline plumbing. If baseline missing, show unavailable. No alert-gating until approved.

**Rationale:** Steal [1]. Coiled-price requirement. `backend/services/flow_quiet_accumulation.py` or similar would be the home — not yet created.

**Agent 3 implication:** B6 designs the gate. Needs baseline plumbing (B1 cadence or file-backed DuckDB). Display-first = show the gate state in UI, don't gate alerts on it yet.

**Agent 4 implication:** B6 evaluator fixtures needed. Gate economics analysis in alert-gate-economics.md.

## D9 — SIDE, sweep, VPIN-like labels must be marked inferred/proxy

**Status:** LOCKED (from HANDOFF.md)

SIDE = last-vs-mid inference. Sweep = heuristic (short-dated/size/voi proxy) until P2 OPRA. VPIN-from-snapshots = prohibited.

**Rationale:** We have snapshot chains, not a print tape. No OPRA feed. No signed prints. No multi-exchange sweep visibility. Anything claiming confirmed buyer/seller identity is a bug.

**Agent 2 implication:** Every SIDE label must show inferred. Every sweep label must show proxy where applicable. No VPIN from snapshots.

**Agent 4 implication:** Refuted-claims audit must scan for: "confirmed buy", "confirmed seller", "dark pool buying", "dark pool selling", "VPIN", "guaranteed", "will move", "institutional buying detected", "true sweep".

## D10 — No paid key is on the critical path

**Status:** LOCKED (from PLAN.md)

P1 Databento OPRA backfill → P2 live OPRA (true SIDE/sweep) → P3 TRF websocket → P4 Tradier realtime+Greeks. No paid key is on the critical path.

**Rationale:** The free tier must ship. Paid upgrades are gated, priced before built.

**Agent 3 implication:** All B-tasks must work on free data. Paid gates are separate.

## D11 — DECIDED NOW: W6 filter depth moves BEFORE W2 context columns

**Status:** NEW (Architect decision, 2026-09-03)

**Problem:** The original plan has W6 (filter depth) after W2 (context columns) and W3 (workflow). But filter depth is the product for most users, and it's frontend-only — it needs only W1's tape. Waiting until W6 means users see an unfiltered tape for 3 waves.

**Decision:** Reorder to W1 → W6 (filters) → W2 (context cols) → W3 (workflow) → W4 (history) → W5 (score) → W7 (methodology). Filters after W1 because they operate on the same tape data. Context columns (earnings, sector, ΔOI) need backend data (B1/B2) so they stay later.

**Rationale:** Filters are subtractive and operate on data already in hand (bid/ask, volume, OI, DTE, strike, premium). Context columns need external data (earnings calendar, sector map, OI history) that depends on backend cadence. The filter-first reorder gives users something useful sooner.

**Agent 2 implication:** W6 filters ship before W2 context columns. Filter fixtures needed first.

**Agent 3 implication:** B1/B2 still on critical path for W2/W4. B3 (dark pool) still late.

## D12 — DECIDED NOW: composite_flow_score.py is the backend score system; frontend pulseScore10 is a separate display transformation

**Status:** NEW (Architect decision, 2026-09-03)

**Problem:** The backend has `composite_flow_score.py` computing a 0..100 composite score (illiquidity 30% + toxicity 25% + dislocation 25% + direction 20%) with bands HIGH/MED/WATCH/LOW. The frontend has `pulseScore10` (conviction 20-99 → 0-10) and `rowConviction` (pattern + size + stat + urgency → 20-99). These are two different score systems that must not be conflated.

**Decision:** 
- Backend composite score (0..100, 4 bands) = institutional conviction metric. Displayed as LEAD chip in summary bar. NOT used for Pulse tape row scoring.
- Frontend pulseScore10 (0-10) = tape row conviction display. Derived from `rowConviction` (pattern 8-24 + size 0-30 + stat 0-26 + urgency 2-14 = 20-99).
- W5 signed score spec = NEW display-only score (-100..+100, sign matrix SIDE×C/P×hedge). This is a third system, distinct from both.
- No alert-gating on the signed score in Phase 9. Alert gating stays on SCORE≥92 / WHALE≥$25M / SIGMA≥6σ / 0DTE volOI≥2 for now.

**Rationale:** Conflating three score systems would create invisible bugs. Each has a different purpose: backend composite = institutional conviction, frontend pulseScore10 = tape display, W5 signed score = directional signal for investigation. Agent 4 must document all three and their boundaries.

**Agent 4 implication:** Score spec must define all three systems, their relationships, and their boundaries. The signed score spec must NOT leak into alert gating.

## D13 — DECIDED NOW: Agent 2 decomposes FlowseekerProBlademap.jsx BEFORE adding new features

**Status:** NEW (Architect decision, 2026-09-03)

**Problem:** The current `FlowseekerProBlademap.jsx` is 1954 lines, monolithic, containing Pulse + Scanner + all helpers + `SCAN_UNIVERSE` (18 tickers) + `DEFAULT_RULES` + alert noise cap + FR filter stubs. Adding W1-W7 features on top of this monolith will create an unmaintainable 3000+ line file.

**Decision:** Agent 2's first task is decomposition, not feature addition. Extract:
- `PulseTape.jsx` — Pulse tape display (mapPublicChainToRows, aggregatePulse, pulseScore10, pulseSignal, pulseHedge, pulseBadges)
- `OverviewBar.jsx` — overview bar (Net Premium, P/C, FIR, session label)
- `ScannerTable.jsx` — scanner rows (from backend /scan or SCAN_UNIVERSE fallback)
- `ScannerFilters.jsx` — W6 filters
- `Tracker.jsx` — W3 tracker
- `ChartModal.jsx` — W3 chart modal v1
- `TabConfig.js` — W4 per-tab config substrate
- `Highlighting.jsx` — W3 highlighting
- `FilterState.js` — W6 filter state
- `types.js` — local types
- `fixtures/` — synthetic fixture data

The monolith `FlowseekerProBlademap.jsx` becomes a shell that composes these sub-components. Existing tests must still pass after decomposition.

**Rationale:** Decomposition first = testable units later. A 1954-line monolith cannot be reliably extended by 4 agents. Each sub-component gets its own test file. Agent 2 must commit the decomposition before W1 feature work.

**Agent 2 implication:** Decomposition is W0.5 (between W0 spikes and W1 tracer). No new features until decomposition is done and tests pass.

## D14 — DECIDED NOW: Agent 3 PROPOSAL_ONLY is the default; BACKEND_LANE_OWNER=1 required for any backend edit

**Status:** NEW (Architect decision, 2026-09-03)

**Problem:** The repo has multiple agents working concurrently. Backend edits by Agent 3 could conflict with other agents' work on `backend/` files.

**Decision:** Agent 3 is PROPOSAL_ONLY by default. Writes proposals, OpenAPI specs, fixtures, ETL designs, migration plans. Does NOT apply backend edits unless the operator explicitly sets BACKEND_LANE_OWNER=1.

**Rationale:** This matches the HANDOFF.md constraint ("frontend/src/App.js and all of backend/ are owned by other lanes — propose, don't touch"). The operator can override per-agent if they want Agent 3 to own a backend lane.

**Agent 3 implication:** All B-tasks are written as proposals with exact file:line references, proposed patches, OpenAPI specs, and fixtures. No backend code is edited unless BACKEND_LANE_OWNER=1.

## D15 — DECIDED NOW: Agent 4's refuted-claims audit is a GATING item for Phase 9 merge

**Status:** NEW (Architect decision, 2026-09-03)

**Problem:** The HANDOFF.md explicitly lists refuted claims that must not appear in code or copy: P&P 7-90 band, Ni GX formula + sign rule, ΓIB-as-Barbon, flip-as-academic, crash probabilities, two phantom papers, -$200mm folklore, VPIN-from-snapshots. If any of these appear in the codebase or UI copy, that's a bug.

**Decision:** Agent 4's refuted-claims audit is a GATING item. Phase 9 merge cannot proceed until:
1. Agent 4 has scanned the codebase + UI copy for refuted claim terms.
2. All hits are either removed or labeled as heuristic/refuted.
3. The audit report is attached to the merge request.

**Rationale:** The HANDOFF.md says "If repo docs/UI strings are readable, use rg to search for offending terms." This is not optional — it's a gating item. False claims in a retail trading terminal erode trust and can cause real financial harm.

**Agent 4 implication:** Must run rg searches for refuted terms and report file:line violations. Must not edit copy itself (that's Agent 2's lane) — reports violations for Agent 2 to fix.

## D16 — DECIDED NOW: W4 CSV export must include honest missing-value handling

**Status:** NEW (Architect decision, 2026-09-03)

**Problem:** CSV export is a data export feature. If it exports fabricated values for missing fields, that's a data integrity bug.

**Decision:** CSV export must:
- Include current filters, timestamp, visible columns in header.
- Export honest missing values (empty cell, "N/A", "unknown", "baseline-building", etc.) — never fabricated values.
- Round-trip: importing the CSV back should reproduce the same row set (modulo sort).

**Rationale:** CSV export is how users take data out of the system. Fabricated values in CSV = fabricated data in their spreadsheets. This is a trust issue.

**Agent 2 implication:** CSV export tests must verify honest missing-value handling. No fabricated values in CSV output.

## D17 — DECIDED NOW: Agent 2's W3 Tracker close-detection is a PROXY, labeled as such

**Status:** NEW (Architect decision, 2026-09-03)

**Problem:** The PLAN.md says "close detection is a proxy based on OI drift/volume; label it as proxy." This is correct — we have snapshot chains, not a print tape. We cannot detect actual trade closes.

**Decision:** Tracker close-detection:
- Uses OI drift + volume as proxy signals.
- Labels as "proxy" in UI.
- Staged: live P/L first (mark = mid → last → stale), OI-drift close detection gated on B1 cadence.
- Statuses: STILL IN, PENDING, PARTIAL N%, EXITED, EXPIRED, UNKNOWN.
- UNKNOWN is an honest state, not a bug.

**Rationale:** We cannot detect actual closes without a print tape. OI drift is a proxy. Labeling it as proxy is honest. UNKNOWN is an honest state for when the proxy can't decide.

**Agent 2 implication:** Tracker UI must show "proxy" label on close detection. UNKNOWN must be a valid status, not an error.

## D18 — DECIDED NOW: Agent 4's score spec must include boundary cases and degraded states

**Status:** NEW (Architect decision, 2026-09-03)

**Problem:** Score specs that don't define boundary cases and degraded states get implemented incorrectly.

**Decision:** Agent 4's signed score spec must include:
- Boundary cases: score -100, 0, +100.
- Degraded states: no-quote, zero OI, missing IV, put-ASK hedge case, 0DTE volOI≥2 case.
- Missing data handling: if SIDE missing → score unavailable; if OI missing → cap magnitude and mark degraded; if IV missing → omit IV component, mark degraded.
- Prohibited: VPIN, crash probability, false sweep certainty, confirmed buyer/seller.

**Rationale:** A score spec without boundary cases gets implemented with invisible bugs at the edges. The spec must be complete enough that Agent 2 can implement it without asking questions.

**Agent 4 implication:** Score spec must be complete, not hand-wavy. Boundary cases are required, not optional.

## D19 — R1 FALLOUT (2026-09-04, Architect ruling, highest priority)

**Status:** LOCKED — supersedes any prior AI-catalyst booster language.

**Context:** Public.com Individual API surface was verified 2026-09-04 to expose only `trading/marketdata/historicdata` (see `backend/services/public_api.py` — zero hits for `Key Moments`, `Earnings Hub`, `AI context`). The "AI context" pillar (Key Moments feed, Earnings Hub stream, 1.2x score booster) does not exist in the authenticated surface and therefore cannot be wired. This is ruling **R1**.

**Decision:** Every schema, promise, or UI copy touching AI catalysts, Key Moments, Earnings Hub, or the 1.2x booster now resolves to an **honest-empty** typed null with a reason code, never a placeholder, never fabricated text:

```ts
type AIContextAvailability = { available: false; reason: "no_api_surface" };
type AICatalyst = null; // when available===false, value is null + reason
```

Affected contracts (grep 2026-09-04: zero literal `Key Moment`/`1.2x`/`booster` hits in phase-9 docs — hardening is preventive, not clean-up): `CONTRACTS.md` pulse/scanner/alert `aiCatalyst`/`scoreBooster` fields now `T | null` with `available/reason`; `WAVE_STATE.md` notes that any W3/W5 booster step is honest-empty until the API surface changes. Frontend renders "AI context unavailable — no API surface" copy, not an empty spinner.

**Rationale:** Fabricated catalyst text would be a worse bug than a missing feature. Honest-empty is load-bearing — it keeps the gate honest and prevents hallucinated catalysts from entering outcomes or backtests.

**Owner:** Architect (Agent 1). Frontend (Agent 2) renders the empty state; Backend (Agent 3) must not invent a synthetic catalyst endpoint; Research (Agent 4) audits copy for booster claims.

## D20 — KEY PROTECTION LAW (2026-09-04, Architect law, standing)

**Status:** LAW — cited in `RISK_REGISTER.md` and `GATE_PLAN.md`; violations fail the gate.

> "Chain data flows ONLY through fetch_chain_from_public_api (60s TTL) or CacheRouter (300s). No new per-ticker Public pollers. No cadence shortening. Frontend never calls Public directly. Violations fail the gate."

See `backend/services/public_api_adapter.py` (60s chain TTL + coalescing + stale-serve) and `backend/services/public_api.py` (Triad at 60s). Rate incident 2026-09-04 (Triad 7×~6 calls/30s → 80+/min) is the evidence that this law is not optional.

