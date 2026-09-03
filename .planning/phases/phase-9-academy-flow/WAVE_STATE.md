# Wave State — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

## Wave order (reordered from PLAN.md)

**Decision D11:** W6 (filter depth) moves BEFORE W2 (context columns). Filters are frontend-only, operate on data already in hand, and are the product for most users. Context columns need backend data (B1/B2) so they stay later.

**Final order:**
```
W0 → W1 → W6 → W2 → W3 → W4 → W5 → W7
```

### W0 — Spikes (cheap, de-risk)

**Goal:** Resolve unknowns before product code.

**Tasks:**
- OPTION instrument_type on public bars — go/no-go (fallback: snapshot-derived contract history)
- OpenTerminalUI [2] heat-score/sentiment read — go/no-go
- yfinance earnings/sector field check — go/no-go

**Dependencies:** None.

**Frontend-only?** Yes (go/no-go records, no product code).

**Test evidence:** Go/no-go records in agent2-frontend.md.

**Deliverables:** Spike report with go/no-go per item.

---

### W1 — Tracer: Tape Depth (frontend-only)

**Goal:** Add spread-position bar + Fill cols + Overview bar to Pulse tape.

**Tasks:**
- W1.1 Spread-position bar: `(last - bid) / (ask - bid)`, clamped [0,1], NO_QUOTE state when bid/ask missing
- W1.2 Fill column: premium fill amount per row
- W1.3 Overview bar v1: Net Premium, P/C ratio, FIR (|callPrem - putPrem| / (callPrem + putPrem)), session label (|FIR| >= 0.3 → Bullish/Bearish, else Neutral), RVOL honest-empty "needs baseline"

**Dependencies:** None (operates on existing Pulse row data: bid/ask/last/vol/OI/IV/premium).

**Frontend-only?** Yes.

**Fixture-first?** Yes — fixtures prove spread bar formula, overview bar values, RVOL honest-empty.

**Test evidence:**
- Spread bar: 20 sampled rows, bar position == (last-bid)/(ask-bid) ±1%
- Overview bar: values reproduce from same payload ±1%
- RVOL: shows "building n/20" pre-cadence (not a number, not 0, not 1.0)

**Deliverables:**
- `PulseTape.jsx` with spread bar + fill cols
- `OverviewBar.jsx` with net premium / P/C / FIR / session label / RVOL state
- W1 tests in `PulseTape.test.jsx`

**Agent 2 tasks:** Extract PulseTape from monolith, implement W1.1-W1.3, write fixtures + tests.

**Agent 3 tasks:** None (frontend-only).

**Agent 4 tasks:** Write overview bar evaluator fixtures (expected netPremium, pcRatio, fir, sessionLean for known payloads).

---

### W6 — Filter Depth (frontend-only, needs only W1)

**Goal:** Full filter system for Pulse + Scanner.

**Tasks:**
- W6.1 Equity-type triple toggle: Stocks / ETFs / Indices (static map)
- W6.2 Sweeps-only chip (labeled as sweep proxy)
- W6.3 Side chips: Bid / Mid / Ask
- W6.4 OTM / ITM / 0DTE toggles
- W6.5 OPEX-week-only toggle
- W6.6 Strike-range filter (min/max inputs)
- W6.7 OI-growth slider (fixture-first, needs B1 for real values)
- W6.8 Contract sentiment slider (bid/ask mix)
- W6.9 Chain sentiment slider
- W6.10 |score| mode (absolute value score filter)
- W6.11 Row icons: sweep waves + multi-leg Layers badge
- W6.12 Filter state object (C16) + per-tab persistence
- W6.13 Before/after row counts in debug mode
- W6.14 Empty-state widen actions

**Dependencies:** W1 (tape data).

**Frontend-only?** Yes (all filters computable from row data already in hand).

**Fixture-first?** Yes — all filters proven on synthetic fixtures.

**Test evidence:**
- Equity-type toggle: ETF-off removes all ETF rows on fixture
- Sweeps-only: keeps classified sweeps, removes others
- Side chips: each chip removes opposite side rows
- OTM/ITM/0DTE: each toggle moves row counts monotonically
- Strike range: min/max filters rows correctly
- OI-growth: fixture-first (no real values until B1)
- Sentiment sliders: each moves row counts monotonically
- |score| mode: filters rows with |score| < threshold
- Row icons: sweep + multi-leg fixtures badge correctly
- Filter state: serializes/deserializes correctly
- Before/after counts: debug mode shows counts
- Empty-state widen: each action measurably widens row count

**Deliverables:**
- `ScannerFilters.jsx` — all filter controls
- `FilterState.js` — filter state object + serialization
- `FilterState.test.js` — filter tests
- W6 tests

**Agent 2 tasks:** Implement W6.1-W6.14, write fixtures + tests.

**Agent 3 tasks:** None (frontend-only, OI-growth is fixture-first).

**Agent 4 tasks:** Write filter subtractiveness evaluator fixtures, filter economics analysis.

---

### W2 — Context Columns (needs backend data)

**Goal:** Add earnings proximity, sector/industry, ΔOI, strategy badge to Pulse/Scanner.

**Tasks:**
- W2.1 Earnings proximity column + filter (Finnhub /calendar/earnings cache, B2)
- W2.2 Sector/industry filter (Finnhub profile2 + static map, B2)
- W2.3 ΔOI column (Mongo snapshot OI history until file-backed DuckDB, needs B1)
- W2.4 Strategy badge on Pulse (spread legs flagged, not directional, needs B1 for OI data)

**Dependencies:**
- W2.1 → B2 (earnings cache)
- W2.2 → B2 (sector map, profile2)
- W2.3 → B1 (Mongo snapshot cadence for OI history)
- W2.4 → B1 (OI data for strategy detection)

**Frontend-only?** No — needs backend data (B1, B2).

**Fixture-first?** Yes — all context columns ship against fixtures first, wire live when backend lands.

**Test evidence:**
- Earnings: 5 sampled tickers match Finnhub calendar, cached (no per-poll fetch)
- Sector: 5 sampled tickers match Finnhub profile2 + static map
- ΔOI: matches next-day exchange truth on 5 sampled contracts
- Strategy badge: synthetic vertical/straddle fixtures badge correctly; legs never WHALE alone

**Deliverables:**
- Earnings proximity column + filter component
- Sector/industry filter component
- ΔOI column component
- Strategy badge component
- W2 tests

**Agent 2 tasks:** Implement W2.1-W2.4 against fixtures, write tests.

**Agent 3 tasks:** B2 (earnings cache + sector map), B1 (cadence for OI history).

**Agent 4 tasks:** Write context column evaluator fixtures, citation audit for earnings/sector claims.

---

### W3 — Workflow Surfaces (needs W1 tape + W2 context)

**Goal:** Chart modal v1, Tracker v1, highlighting, tab substrate.

**Tasks:**
- W3.1 Chart modal v1: Contract history + Net Premium views only (5 views is scope creep; remaining 3 are W5)
- W3.2 Tracker v1: bookmark from row, localStorage-first persistence, live P/L using quote marks (mid → last → stale), statuses (STILL IN, PENDING, PARTIAL N%, EXITED, EXPIRED, UNKNOWN), close detection is proxy based on OI drift/volume (labeled as proxy)
- W3.3 Flow Highlighting: Size>OI → yellow, Vol>OI → purple, per-tab persisted, OI=0 edge case documented
- W3.4 One per-tab config substrate: single serialized object per tab (tabs + columns + highlighting + filters), schemaVersion, safe migration, max 10 tabs on Live Feed, max 5 tabs on Scanner

**Dependencies:**
- W3.1 → None (works on existing tape data)
- W3.2 → None for live P/L (uses current quotes); close detection needs B1 (OI drift)
- W3.3 → None (works on existing row data)
- W3.4 → None (localStorage-first)

**Frontend-only?** Mostly yes. Close detection needs B1 for real OI drift data.

**Fixture-first?** Yes — tracker P/L, highlighting, tab config all proven on fixtures first.

**Test evidence:**
- Chart modal: opens from any Pulse row; NetPremium default view; figures match tape
- Tracker: P/L within a tick of mark; staged close detected on fixture drift
- Highlighting: 100% fire on synthetic fixtures including OI=0 edge (documented, not "fixed")
- Tab config: prefs survive reload; 10-tab render perf unchanged; CSV round-trips

**Deliverables:**
- `ChartModal.jsx` — contract history + Net Premium v1
- `Tracker.jsx` — bookmark + live P/L + statuses
- `Highlighting.jsx` — Size>OI / Vol>OI row icons
- `TabConfig.js` — per-tab config substrate
- `Tracker.test.jsx`, `ChartModal.test.jsx`, `Highlighting.test.jsx`, `TabConfig.test.js`

**Agent 2 tasks:** Implement W3.1-W3.4, write fixtures + tests.

**Agent 3 tasks:** B1 (cadence for OI drift close detection), Mongo promotion gate for tracker (later).

**Agent 4 tasks:** Write tracker evaluator fixtures, close-detection proxy audit, tab config migration tests.

---

### W4 — History-Backed Views (needs B1 cadence)

**Goal:** Net Premium trend, Strike Distribution, Vol/OI 14d, feed tabs, ticker !exclude, cap/sort, CSV export.

**Tasks:**
- W4.1 NetPremium trend: 5d/7d/14d/30d windows, trend chart
- W4.2 Strike distribution: histogram by strike, call/put volume, OI, max pain
- W4.3 Vol/OI 14d footer table: 14 days of volume/OI/vol_oi_ratio
- W4.4 Feed tabs: up to 10 tabs, ticker-scope search with !TICKER exclusion
- W4.5 Results cap: 50/100/250/500
- W4.6 Sort: Time / Premium / Size (non-Time sorts apply $25K premium floor)
- W4.7 CSV export: includes current filters, timestamp, visible columns, honest missing values

**Dependencies:** B1 (snapshot cadence for history data). Frontend ships against fixtures first, wires live when cadence lands.

**Frontend-only?** No — needs B1 for real history data. Fixture-first regardless.

**Test evidence:**
- NetPremium trend: reproduce from snapshots on demand
- Strike distribution: reproduce from snapshots on demand
- Vol/OI 14d: reproduce from snapshots on demand
- Feed tabs: 10-tab render perf unchanged
- Ticker !exclude: excludes specified ticker from results
- Cap/sort: each cap/sort moves row counts correctly
- CSV: includes filters, timestamp, columns, honest missing values; round-trips

**Deliverables:**
- `ScannerTable.jsx` — market-wide scanner rows with cap/sort
- `NetPremiumTrend.jsx` — trend chart
- `StrikeDistribution.jsx` — histogram
- `VolOIHistory.jsx` — 14d footer table
- `CSVExport.js` — CSV export utility
- W4 tests

**Agent 2 tasks:** Implement W4.1-W4.7 against fixtures, write tests.

**Agent 3 tasks:** B1 (snapshot cadence) is critical path. Without B1, W4 stays fixture-first.

**Agent 4 tasks:** Write history view evaluator fixtures, CSV honest-missing audit.

---

### W5 — Signed Score Spec + Backtest Harness (display-only)

**Goal:** Signed Flow Score spec (-100..+100) DISPLAY-ONLY + backtest harness on Databento credits.

**Tasks:**
- W5.1 Signed score spec: -100..+100, sign matrix SIDE×C/P×hedge, magnitude from spread/volOI/premium/IV weights, DISPLAY-ONLY (not alert-gating)
- W5.2 Score boundary cases: -100, 0, +100, no-quote, zero OI, missing IV, put-ASK hedge, 0DTE volOI≥2
- W5.3 Backtest harness: Databento credits (P1 funding), Sharpe-gated reports per ADR-0001
- W5.4 Remaining 3 modal views: (scope creep — only if time permits)

**Dependencies:**
- W5.1-W5.2 → None (spec + unit tests)
- W5.3 → P1 funding (Databento credits) — gated, not free

**Frontend-only?** No — score spec is a contract between frontend + backend. Backtest harness needs Databento credits (paid).

**Fixture-first?** Yes — score boundary cases proven on fixtures.

**Test evidence:**
- Score components unit-tested (sign matrix, magnitude weights)
- Boundary cases: -100, 0, +100 all produce correct scores
- No-quote → score unavailable
- Zero OI → magnitude capped, degraded
- Missing IV → IV component omitted, degraded
- Put-ASK hedge → BULLISH with HEDGE? tag
- 0DTE volOI≥2 → score computed correctly
- Backtest reports: Sharpe-gated per ADR-0001 (if P1 funded)

**Deliverables:**
- `types.js` — score types + sign matrix
- Score tests
- Backtest harness (if P1 funded)

**Agent 2 tasks:** Implement score display in UI (if spec is complete).

**Agent 3 tasks:** Score computation endpoint (if needed for live data).

**Agent 4 tasks:** Write signed score spec (C1-C17 in CONTRACTS.md are the contract; Agent 4 writes the spec document + evaluator fixtures + backtest design).

---

### W7 — Methodology Surfaces (needs W3 Tracker + modal; turns docs into UI)

**Goal:** Starter tab presets, in-modal investigation checklist, funnel empty-states, dark-pool levels overlay, right-click actions.

**Tasks:**
- W7.1 Starter tab presets: "Broad $100K Stocks" + "High-Conviction Sweeps $250K |score|>60"
- W7.2 In-modal investigation checklist: 6 steps checkable, hypothesis verdict recorded (confirmed/skipped + reason), localStorage-first
- W7.3 Funnel empty-states: "0 rows — widen shortage" with one-click widen actions (drop score gate / widen DTE / include ETFs)
- W7.4 Dark-pool levels overlay on heatseeker: Top-N horizontal dashed lines + notional labels from B3 FINRA data (needs B3 first — specced here, built after)
- W7.5 Right-click row actions: filter matching trades, exclude ticker (!TICKER), track trade (needs W3 Tracker)
- W7.6 Pulse sort by Premium/Size with $25K-premium floor quirk on non-Time sorts

**Dependencies:**
- W7.1 → W3 (tab config substrate)
- W7.2 → W3 (tracker + chart modal)
- W7.3 → W6 (filters)
- W7.4 → B3 (FINRA ETL for dark pool data) — specced here, built after B3 lands
- W7.5 → W3 (tracker)

**Frontend-only?** Mostly yes. Dark-pool overlay needs B3 for data.

**Test evidence:**
- Starter presets: fresh profile opens with both tabs, gates verified by mount test
- Investigation checklist: 6 steps checkable; verdict + reason persisted per print
- Funnel empty-states: each widen action measurably widens row count on fixtures
- Dark-pool overlay: lines match FINRA ETL top-N notionals ±1% (post-B3)
- Right-click actions: actions mutate filters correctly
- Sort floor: non-Time sorts enforce $25K floor

**Deliverables:**
- `TabPresets.js` — starter tab presets
- `InvestigationChecklist.jsx` — in-modal checklist
- `FunnelEmptyState.jsx` — funnel guidance
- `DarkPoolOverlay.jsx` — dark pool levels overlay (post-B3)
- `RightClickActions.jsx` — right-click menu
- W7 tests

**Agent 2 tasks:** Implement W7.1-W7.3, W7.5-W7.6. W7.4 is post-B3 (specced here, built after).

**Agent 3 tasks:** B3 (dark pool ETL) for W7.4 data.

**Agent 4 tasks:** Write investigation checklist evaluator fixtures, dark pool methodology spec, copy audit for dark pool UI.

---

## Merge order

1. W0 spikes → go/no-go records
2. W1 tracer → tape depth (frontend-only)
3. W6 filters → filter depth (frontend-only, reordered before W2)
4. W2 context columns → earnings/sector/ΔOI/strategy (needs B1/B2)
5. W3 workflow → chart modal + tracker + highlighting + tab substrate
6. W4 history → trend + distribution + Vol/OI + tabs + CSV (needs B1)
7. W5 score → signed score spec + backtest (display-only)
8. W7 methodology → presets + checklist + funnel + dark pool overlay (post-B3) + right-click

## What can start immediately

- W0 spikes (go/no-go only)
- W1 tracer (frontend-only, operates on existing Pulse data)
- W6 filters (frontend-only, operates on existing row data)
- W3.1 chart modal v1 (contract history + Net Premium from existing data)
- W3.3 highlighting (operates on existing row data)
- W3.4 tab config substrate (localStorage-first)
- W5.1-W5.2 score spec + boundary cases (spec + unit tests only)

## What is fixture-first

- All W1-W7 frontend features ship against synthetic fixtures first
- W4 history views ship against fixtures until B1 cadence lands
- W2 context columns ship against fixtures until B1/B2 land
- W7.4 dark pool overlay ships spec-only until B3 lands

## What requires B1 snapshot cadence

- W2.3 ΔOI column (real OI history)
- W2.4 strategy badge (real OI data)
- W3.2 tracker close detection (OI drift proxy)
- W4.1-W4.3 history-backed views (NetPrem trend, strike distribution, Vol/OI 14d)
- W7.2 tracker close detection stages (OI drift)

## What requires B2 earnings cache

- W2.1 earnings proximity column + filter

## What requires B3 FINRA/Reg SHO ETL

- W7.4 dark pool levels overlay

## What is frontend-only

- W1 tracer (spread bar + fill + overview bar)
- W6 filters (all filter controls + state)
- W3.1 chart modal v1 (contract history + Net Premium from existing data)
- W3.3 highlighting (Size>OI / Vol>OI)
- W3.4 tab config substrate (localStorage)
- W5.1-W5.2 score spec + boundary cases (spec + unit tests)
- W7.1 starter presets
- W7.2 investigation checklist
- W7.3 funnel empty-states
- W7.5 right-click actions
- W7.6 sort floor quirk

## What is proposal-only

- B1 snapshot cadence (backend)
- B2 earnings cache (backend)
- B3 FINRA/Reg SHO ETL (backend)
- B5 align min volume (backend)
- B6 quiet accumulation gate (backend)
- B7 outcome tracking (backend)
- B8 citation hygiene (backend docstrings)
- B9 O/S borrow inputs (backend)

## Test evidence required per wave

| Wave | Test evidence |
|---|---|
| W0 | Go/no-go records in agent2-frontend.md |
| W1 | Spread bar ±1% on 20 rows; overview bar ±1% on fixtures; RVOL honest-empty |
| W6 | All filters move row counts monotonically; filter state round-trips; empty-state widen actions work; row icons badge correctly |
| W2 | 5 tickers match Finnhub calendar/profile; ΔOI matches exchange truth on 5 contracts; strategy badge fixtures correct |
| W3 | Chart modal opens from row; tracker P/L within tick; highlighting 100% on fixtures; tab config survives reload |
| W4 | History views reproduce from snapshots; CSV round-trips; 10-tab perf unchanged |
| W5 | Score boundary cases unit-tested; sign matrix correct; no alert-gating on score |
| W7 | Presets mount correctly; checklist persists verdicts; funnel widen actions work; right-click actions mutate filters |

## Open questions for Agent 1 triage

1. **Decomposition strategy:** Agent 2 must decompose the 1954-line `FlowseekerProBlademap.jsx` monolith. Should decomposition be W0.5 (before W1) or part of W1? **Decision: W0.5 — decomposition must happen before any feature work.**

2. **SCAN_UNIVERSE fallback:** The frontend has a hardcoded 18-ticker `SCAN_UNIVERSE` for scanner fallback. Should Agent 3 build a backend `/scan` endpoint, or should Agent 2 work with the 18-ticker fallback? **Decision: Agent 3 B1 includes a `/scan` endpoint proposal. Agent 2 works with the 18-ticker fallback until B1 lands.**

3. **Tab config persistence:** Should tab config persist to localStorage only, or should Agent 3 build a Mongo promotion path? **Decision: localStorage-first for Phase 9. Mongo promotion is a gate for later.**

4. **Chart modal v1 scope:** The plan says "Contract history + Net Premium ONLY — 5 views is scope creep." Should Agent 2 wait for W5 to build the remaining 3 views, or build them now if time permits? **Decision: Wait for W5. W3 ships 2 views only.**

5. **Tracker close detection:** The plan says close detection is a proxy based on OI drift/volume. Should Agent 2 implement it now (labeled as proxy) or wait for B1? **Decision: Implement live P/L now (mid → last → stale). Close detection ships as proxy-labeled, gated on B1 for real OI drift data.**

6. **Filter depth reorder:** W6 moves before W2. Does this create any dependency issues? **Decision: No. Filters operate on existing row data. W2 context columns need backend data. Filter-first is correct.**
