# FlowSeeker Pro Scanner — User Research Synthesis (2026-07-10)

**Method:** Expert evaluation for a single-user product (Nav). Multi-lens research pass
(JTBD / heuristics / competitive / perf / signal) run as a workflow; one lens completed
before the session limit killed the fleet, its 8 findings hand-verified against the code.
Live-UI audit of the running app surfaced one additional confirmed perf bug.
Competitive baseline: Unusual Whales, FlowAlgo, Cheddar Flow, BlackBoxStocks, InsiderFinance.

**Persona anchor:** intermittent checker (12-hr Dow shifts + clinicals) · free/cvforge data
only (no prints, no live quotes, 429-prone upstream) · desktop, dark, dense-data tolerant,
needs jargon decoded.

---

## Themes

1. **"While I was away" is the core unserved job.** The scanner is built for a user
   watching live; Nav is away for 12-hour stretches. Everything that happened between
   check-ins must be reconstructable in 90 seconds.
2. **Confirmation beats more signals.** With no tape, the scanner's vol/OI-family signals
   are guesses; day-over-day OI change and multi-day persistence are the only free
   confirmations available — and the backend already collects most of the raw material.
3. **Context makes numbers readable.** Raw IV, raw sigma, raw score need self-accumulated
   history (IV rank, streaks) and event flags (earnings) to be interpretable by a
   non-professional.
4. **The scanner must not compete with itself for the browser's connection budget.**
   (Confirmed live: heavy chart polls starved /scan into a blank table.)

## Shipped in this pass (commits on main)

| # | Item | Finding |
|---|------|---------|
| 1 | 🎯 UNIV chip — alerts + notifications scoped to My Universe (default ON) | F3 |
| 2 | ☾ "While you were away" banner — gap length, per-rule alert counts, top-3 new contracts (clickable); tape now keeps today + yesterday with a `prev` day-tag | F1 |
| 3 | ⤓ CSV export of the filtered view + ⧉ Copy (TSV) of the alert tape — for the DVT journal | F7 |
| 4 | Tab-gated heavy polls: chain feed (15s) + vpin/lambda/ofi/heatmap (6s!) no longer fire while on the Scanner tab; regime pill kept | live-audit |

All scanLogic additions (`evalAlerts allow`, `awaySummary`, `scanRowsToCSV`) are Jest-tested (51 tests).

## Backlog (needs backend work — "next")

- **ΔOI column (F2, impact 5):** persist per-contract `{ticker, contract_key, date, oi}` in
  `_record_scan_baseline` (top-300/day); join yesterday's OI into /scan like
  regimes/baselines; "FRESH → CONFIRMED" tooltip when OI holds next day. The one real
  "was it opening flow?" check a print-less feed can do.
- **Volume/PCR history + streaks (F5, impact 4):** `GET /scan/history/{ticker}` reading
  `flow_scan_daily` (call/put/total vol per day already stored, currently collapsed to
  avg/std one step before the UI); rollup-chip sparkline + "3d unusual" streak tag.
- **Earnings-proximity flag (F4, impact 4):** daily-cached yfinance/AlphaVantage earnings
  dates → `E-2d` badge; pre-earnings vol explosions are the biggest false-positive source
  for vol/OI signals.
- **IV rank (F6, impact 3):** persist daily atm_iv (already computed in /regime path);
  percentile tint on the IV column once ≥10 days accumulate.
- **Ticker drill-down panel (F8, impact 3):** slide-in on rollup-chip click; reuse the
  built-but-unused `/alerts/{symbol}` endpoint (confidence factors double as plain-English
  explanations). Gate behind panel-open + chain cache for 429 safety.

## Rejected / out of scope

- Sweep/block detection, bid-ask side inference: needs trade prints — feed can't do it.
- Live IV surface: same.
- O/S ratio (Roll-Schultz-Subrahmanyam): needs per-ticker stock volume per scan row;
  revisit if a cheap stock-volume source lands in the scan payload.
