# Phase 9 — Academy Flow Build (Skylit Flowseeker parity, Public-API-first)

**Status:** PLANNED 2026-09-03 · **Parent:** ROADMAP.md (new; Phase 8 owned by another agent)
**Sources:** 6 Skylit Academy Flowseeker articles (user-pasted 2026-09-03),
`/tmp/wf_academy/gap_matrix.md` (HAVE/CAN/NEED + rethink + architecture decision),
`/tmp/wf_academy/repo_flow.md` (4 verified flow repos), `/tmp/wf_academy/repo_data.md`
(GEX libs, dark pool, providers), `/tmp/wf_academy/ui_spec.md` (BladeMap visual spec).

**Goal:** every Academy capability that Public API + existing services can support,
built tracer-first with measurable acceptance. Nothing that needs a paid key or a
true print tape ships as anything but an honest degraded state.

## Locked decisions (from verification, not opinion)
- D1 Pulse stays PER-TICKER on Public API chains (only rows with real bid/ask → real
  SIDE/PRICE). Market breadth lives in Scanner. mkScanRow has no bid/ask/mid —
  forcing scan rows into the tape would silently degrade the reference's core columns.
- D2 Reference SIGNAL spec stands (ASK→BULLISH incl. put-ASK + HEDGE? tag, Phase 7).
- D3 Calibration stays open (desk's dials) but every new signal ships WITH its
  evaluator from day one (steal [3]: no signal without Performance_Evaluation).
- D4 Adopt per-tag 30-min outcome tracking (steal [1]) in the outcomes module.
- D5 Dark pool ships as FINRA context panel only (weekly ATS + daily Reg SHO, keyless
  ETL). Never a live tape on free data. Real-time TRF prints = paid gate.
- D6 Greeks computed in-house (steal 1a/1b formulas); never depend on vendor greeks.
- D7 One chain interface yfinance→Tradier→Databento (steal 1c/1d adapter pattern).
- D8 Alert rule upgrade (steal [1]): volume >2σ AND price-range compression <1σ
  (coiled-price requirement) evaluated as an additional gate, display-first.

## Waves (tracer-first; commit per wave; Jest evidence each)
- **W0 Spikes (cheap, de-risk):** OPTION instrument_type on public bars (fallback:
  snapshot-derived contract history); OpenTerminalUI [2] heat-score/sentiment read;
  yfinance earnings/sector field check. Output: go/no-go per item, no product code.
- **W1 Tracer — tape depth, frontend-only:** Spread-position bar + Fill cols on Pulse
  (bid/ask/last already in rows) + Overview bar v1 (Net Premium, P/C, FIR as defined
  below, session label; RVOL ships as honest "needs baseline" state). Metric: bar
  values ±1% vs manual calc on same payload; spread bar matches (last-bid)/(ask-bid).
- **W2 Context cols:** finnhub /calendar/earnings method + cache → earnings-proximity
  col+filter; sector/industry filter (finnhub profile cache); ΔOI col (DuckDB OI
  history); strategy badge ported to Pulse mapper (backend detect_spreads logic).
  Metric: ΔOI matches next-day exchange truth on 5 sampled contracts.
- **W3 Workflow:** chart modal v1 (Contract history + Net Premium ONLY — 5 views is
  scope creep; remaining 3 are W5); Tracker v1 (bookmark + live P/L via quotes +
  STILL-IN/PARTIAL/EXITED via OI drift; localStorage-first, Mongo promotion = gate);
  Flow Highlighting (Size>OI yellow / Vol>OI purple, per-tab persisted, synthetic
  fixtures prove 100% fire rate); ONE per-tab config substrate (tabs + columns +
  highlighting + filters — single object, not three features). Metric: tracker P/L
  within a tick of mark; highlighting 100% on fixtures.
- **W4 History-backed:** Net Premium trend + Strike Distribution + Vol/OI 14d footer
  (needs W4-backend cadence; frontend ships against fixtures first, wires live when
  cadence lands). Feed tabs (10) + ticker-scope search (!exclude) + results cap/sort
  + CSV export. Metric: trend values reproduce from snapshots on demand.
- **W5 Score + depth:** signed Flow Score spec (-100..+100: sign matrix SIDE×C/P×hedge;
  magnitude from spread/volOI/premium/IV weights) DISPLAY-ONLY + backtest harness on
  Databento credits; remaining 3 modal views; scanner depth filters (OI growth,
  sentiment sliders, OPEX). Metric: score components unit-tested; backtest reports
  Sharpe-gated per ADR-0001. Alert-gating on the score is explicitly OUT (later phase).

## Definitions (no vibes)
- FIR = |callPrem − putPrem| / (callPrem + putPrem), 0..1, per session window.
- RVOL = session premium-to-time vs 20d same-time baseline (DuckDB rollups; until
  cadence exists the bar shows "baseline building n/20").
- Quiet-accumulation gate [1]: contract vol z-score >2 AND (contract range z <1 AND
  underlying range z <1) over the bar window.

## Backend-lane proposals (NOT this lane; file:line)
- B1 Snapshot cadence job in scheduler.py (fixed-interval precedent) for chains;
  raise/segment Mongo 50-cap or roll to DuckDB for intraday baselines.
- B2 finnhub earnings-calendar cache endpoint (free tier, aggressive cache).
- B3 FINRA ATS weekly + Reg SHO daily ETL → venue-share + short-pressure panel.
- B4 flow_alerts: quiet-accumulation gate (display-first), per-tag outcome tracking.
- B5 Align force_refresh min_volume 1000 vs market_scan 2500 (found Phase 7).

## Paid gates (later, priced before built)
P1 Databento OPRA backfill → P2 live OPRA (true SIDE/sweep) → P3 TRF websocket
(Massive pattern) → P4 Tradier realtime+Greeks. No paid key is on the critical path.

## Verification loop (every wave)
1. New signal ⇒ new evaluator (steal [3]); fixtures prove fire rates.
2. Full frontend suite green; backend suites untouched-and-green.
3. Metrics in the table above, not adjectives. 4. Heredoc commit, own files only.

## NOT in scope
Mobile card layouts, Discord share/image export (after P1), Atlas overlay (Heatseeker
cross-check already same-terminal), options-strategy modal legs beyond badge,
any CBOE scraping (prohibited), any repo clones (patterns only, Nav's rule).
