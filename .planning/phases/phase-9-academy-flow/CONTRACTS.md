# Contracts — Phase 9 Academy Flow Build

**Created:** 2026-09-03 · **Agent:** 1 (Architect) · **Branch:** phase9/agent1-architect

**Purpose:** Precise JSON/TypeScript-style schemas for every data structure in Phase 9. Agent 2 implements against these. Agent 3 proposes backend endpoints that produce these. Agent 4 writes evaluators with these.

**Rule:** Every field marked `inferred` or `proxy` must be labeled as such in UI copy. Every field marked `unavailable` must have an honest empty state, never a fabricated value.

---


## R1 Honest-Empty — AI Context Pillar (2026-09-04, ruling R1)

**Law:** The Public.com "AI context" pillar is DEAD. Key Moments and Earnings Hub do not exist in the Individual API surface (`backend/services/public_api.py` zero hits for trading/marketdata/historicdata only). Any contract touching AI catalysts, Key Moments, Earnings Hub, or the 1.2x score booster resolves to **honest-empty**, never placeholder, never fabricated text.

**Schema (apply to every pulse/scanner/alert/aiCatalyst/scoreBooster field):**
```ts
type AIContextAvailability = { available: false; reason: "no_api_surface" };
type AICatalyst = null; // value is null when available===false
// Pulse/Scanner row extension:
aiCatalyst: AICatalyst | { available: false; reason: "no_api_surface" };
scoreBooster: 1.0; // fixed — 1.2x booster is void under R1; never multiply
```

**Honest-empty states:** `{ available:false, reason:"no_api_surface" }` → UI renders "AI context unavailable — no API surface" (not spinner, not blank). No booster math. Backtest/outcomes must exclude booster until API surface changes. Grep 2026-09-04: zero literal `Key Moment`/`1.2x`/`booster` hits in docs — this is preventive hardening.

---

## C1 — Pulse Row

The per-ticker live tape row. Source: Public API `/api/public/chain/{ticker}` + aggregation.

```typescript
interface PulseRow {
  // Identity
  ticker: string;                    // REQUIRED — underlying symbol, e.g. "SPY"
  type: "CALL" | "PUT";              // REQUIRED — from chain contract type
  strike: number;                    // REQUIRED — strike price
  expiration: string;                // REQUIRED — ISO date, e.g. "2026-09-18"
  timestamp: number;                 // REQUIRED — row timestamp (ms since epoch)

  // Quote data (from chain snapshot)
  bid: number;                       // REQUIRED — may be 0 on fallback paths → NO_QUOTE state
  ask: number;                       // REQUIRED — may be 0 on fallback paths → NO_QUOTE state
  last: number;                      // REQUIRED — may be 0 on fallback paths → NO_QUOTE state
  mid: number;                       // DERIVED — (bid+ask)/2 if both > 0, else estPrice() fallback
  spot: number | null;               // OPTIONAL — underlying price, null if unavailable

  // Flow metrics
  volume: number;                    // REQUIRED — contract volume (calls+puts)
  oi: number;                        // REQUIRED — open interest
  vol_oi_ratio: number;              // DERIVED — oi > 0 ? volume/oi : volume/100
  iv: number;                        // REQUIRED — implied volatility (0-100 scale)
  premium: number;                   // DERIVED — round(volume * mid * 100), in $

  // Classification (heuristic)
  classification: "regular" | "sweep" | "unusual" | "block";
  // sweep = dte <= 2 + premium >= $5M
  // block = premium >= $50M
  // unusual = everything else with vol_oi_ratio >= 0.4
  // Classifications are PROXIES until P2 OPRA. Must be labeled as such in UI.

  // SIDE (inferred)
  side: "BID" | "ASK";               // DERIVED — last >= midQ → ASK, else BID; voi >= 1.5 → ASK fallback
  // SIDE is INFERRED from last-vs-mid. Must be labeled "inferred" in UI.
  // No confirmed buyer/seller identity. Ever.

  // Derived tape columns
  otm: number | null;                // DERIVED — |strike - spot| / spot * 100, null if spot missing
  dte: number;                       // DERIVED — bizDTE(expiration)
  signal: "BULLISH" | "BEARISH";     // DERIVED — ASK → BULLISH, BID → BEARISH (D2)
  hedge: boolean;                    // DERIVED — put-ASK → true (D2)
  score: number;                     // DERIVED — pulseScore10(conv), 0-10 display
  conviction: number;                // DERIVED — rowConviction(), 20-99 internal
  badges: ("SILVER" | "GOLDEN" | "WHALE")[];  // DERIVED — premium thresholds

  // Aggregation (90s window)
  _aggPrem: number;                  // INTERNAL — summed premium in window
  _aggSize: number;                  // INTERNAL — summed volume in window
  _aggN: number;                     // INTERNAL — print count in window
  _aggTs: number;                    // INTERNAL — latest timestamp in window

  // Honest empty states
  noQuote: boolean;                  // true when bid=0 or ask=0 or last=0 → NO_QUOTE state
  stale: boolean;                    // true when row data is older than acceptable threshold
}
```

**Required fields:** ticker, type, strike, expiration, timestamp, volume, oi, vol_oi_ratio, iv, premium, classification, side, signal, badges, score, conviction

**Nullable fields:** spot, otm, mid (may be estimated)

**Honest empty states:**
- `noQuote: true` → row renders NO_QUOTE state (spread bar says "no quote", never guesses)
- `stale: true` → row renders STALE state (timestamp older than threshold)
- `spot: null` → otm renders as "—" (not 0)

**Units:** strike, bid, ask, last, mid, spot in $; volume in contracts; oi in contracts; iv in % (0-100); premium in $; timestamp in ms

**Timestamps:** expiration as ISO date; timestamp as ms since epoch; all relative times computed server-side or client-side from timestamp

**Stale threshold:** 90 seconds for Pulse tape (aggregatePulse window). Rows older than 90s are pruned.

**Source:** snapshot (Public API chain) + derived (computed fields)

**Inferred/proxy:** side (inferred), classification (proxy), signal (derived from inferred side), hedge (derived from inferred side)

---

## C2 — Overview Bar Payload

The summary bar for a per-ticker Pulse view. Source: aggregated Pulse rows for one ticker.

```typescript
interface OverviewBarPayload {
  ticker: string;                    // REQUIRED
  sessionState: "LIVE" | "CLOSED" | "PREMARKET";  // REQUIRED — market state
  netPremium: number;                // DERIVED — sum of all row premiums, $
  callPremium: number;               // DERIVED — sum of CALL row premiums, $
  putPremium: number;                // DERIVED — sum of PUT row premiums, $
  pcRatio: number;                   // DERIVED — callPremium / putPremium, may be Infinity if putPremium=0
  fir: number;                       // DERIVED — |callPrem - putPrem| / (callPrem + putPrem), 0..1
  sessionLean: "Bullish" | "Bearish" | "Neutral";  // DERIVED — |FIR| >= 0.3 → Bullish/Bearish, else Neutral
  totalVolume: number;               // DERIVED — sum of all row volumes
  totalOI: number;                   // DERIVED — sum of all row OIs
  uniqueContracts: number;           // DERIVED — count of unique strike/expiration pairs
  rvol: number | null;               // OPTIONAL — session RVOL, null until baseline exists → "needs baseline"
  rvolState: "available" | "baseline-building" | "unavailable";
  // rvolState = "baseline-building" shows "building n/20" until 20d baseline exists
  // rvolState = "unavailable" when RVOL cannot be computed at all
  asOf: string;                      // REQUIRED — ISO timestamp of last aggregation
  rowCount: number;                  // REQUIRED — number of rows in the aggregation
  frozen: boolean;                   // REQUIRED — true when feed is paused/stale
}
```

**Required fields:** ticker, sessionState, netPremium, callPremium, putPremium, pcRatio, fir, sessionLean, totalVolume, totalOI, uniqueContracts, asOf, rowCount, frozen

**Nullable fields:** rvol (null until baseline exists)

**Honest empty states:**
- `rvolState: "baseline-building"` → overview shows "RVOL: building n/20" (not a number)
- `rvolState: "unavailable"` → overview shows "RVOL: unavailable" (not 0, not 1.0)
- `frozen: true` → overview renders FROZEN state (paused feed)
- `rowCount: 0` → overview renders EMPTY state

**Units:** netPremium, callPremium, putPremium in $; pcRatio unitless; fir unitless 0..1; totalVolume/totalOI in contracts; rvol unitless (ratio)

**Timestamps:** asOf as ISO timestamp

**Stale threshold:** overview matches last aggregation timestamp; if timestamp > 90s old, overview is stale

**Source:** derived (aggregated from Pulse rows)

**Inferred/proxy:** sessionLean is derived from fir (which is derived from premiums). All premiums are derived from snapshot data. No confirmed direction.

---

## C3 — Scanner Contract Row

Market-wide scanner row. Source: backend `/scan` endpoint (or SCAN_UNIVERSE fallback).

```typescript
interface ScannerRow {
  ticker: string;                    // REQUIRED
  type: "CALL" | "PUT";              // REQUIRED
  strike: number;                    // REQUIRED
  expiration: string;                // REQUIRED
  timestamp: number;                 // REQUIRED
  bid: number;                       // REQUIRED — may be 0 → NO_QUOTE
  ask: number;                       // REQUIRED — may be 0 → NO_QUOTE
  last: number;                      // REQUIRED — may be 0 → NO_QUOTE
  mid: number;                       // DERIVED
  spot: number | null;               // OPTIONAL
  volume: number;                    // REQUIRED
  oi: number;                        // REQUIRED
  vol_oi_ratio: number;              // DERIVED
  iv: number;                        // REQUIRED
  premium: number;                   // DERIVED
  side: "BID" | "ASK";               // DERIVED — inferred (same as PulseRow.side)
  otm: number | null;                // DERIVED
  dte: number;                       // DERIVED
  signal: "BULLISH" | "BEARISH";     // DERIVED
  hedge: boolean;                    // DERIVED
  score: number;                     // DERIVED — display score
  conviction: number;                // DERIVED — internal conviction
  badges: string[];                  // DERIVED — SILVER/GOLDEN/WHALE

  // Scanner-specific
  sweepPct: number;                  // DERIVED — sweep classification %, proxy
  sweepLabel: "sweep" | "proxy" | "none";  // DERIVED — "proxy" until P2 OPRA
  multiLeg: boolean;                 // DERIVED — true if legs detected (strategy badge)
  strategyLabel: string | null;      // OPTIONAL — "vertical", "straddle", etc. or null
  // strategyLabel is display-only; never infer missing legs

  // OI change (needs B1 cadence for real values)
  oiChange: number | null;           // DERIVED — oi delta since previous snapshot, null if no history
  oiChangePct: number | null;        // DERIVED — oiChange / previousOI * 100, null if no history

  // Earnings proximity (needs B2 earnings cache)
  earnings: {
    date: string | null;             // ISO date or null
    hour: number | null;             // 0-23 or null
    proximity: "none" | "before" | "after" | "during";  // DERIVED
    raw: "available" | "unavailable";  // source status
  };

  // Sector (needs B2 sector map)
  sector: string | null;             // e.g. "Technology", "Energy", null if unknown
  industry: string | null;           // e.g. "Electronic Technology", null if unknown
  equityType: "stock" | "etf" | "index";  // DERIVED from static map

  // Filterable fields
  noQuote: boolean;                  // true when bid=0 or ask=0 or last=0
  stale: boolean;                    // true when data is stale
}
```

**Required fields:** ticker, type, strike, expiration, timestamp, volume, oi, vol_oi_ratio, iv, premium, side, signal, badges, score, conviction, sweepLabel, multiLeg, equityType, noQuote, stale

**Nullable fields:** spot, otm, mid, oiChange, oiChangePct, earnings.date, earnings.hour, sector, industry, strategyLabel

**Honest empty states:**
- `noQuote: true` → NO_QUOTE state
- `oiChange: null` → "—" (not 0, not "no change")
- `earnings.date: null` → "earnings: unknown" (not "no earnings")
- `sector: null` → "sector: unknown" (not "no sector")
- `sweepLabel: "proxy"` → labeled as proxy in UI

**Units:** same as PulseRow

**Source:** snapshot (chain) + derived + external (earnings, sector) + backend (OI change)

**Inferred/proxy:** side (inferred), sweepLabel (proxy), strategyLabel (heuristic if incomplete)

---

## C4 — Alert Payload

Alert fired by the alert engine. Source: `backend/alert_engine.py` + scan logic.

```typescript
interface Alert {
  id: string;                        // REQUIRED — unique alert id
  type: string;                      // REQUIRED — alert type, e.g. "SCORE", "WHALE", "SIGMA", "0DTE", "OICONF"
  priority: "HIGH" | "MEDIUM" | "LOW";  // REQUIRED — from alert_evaluator
  ticker: string;                    // REQUIRED
  contract: string;                  // REQUIRED — "SPY 2026-09-18C450" style
  message: string;                   // REQUIRED — human-readable alert message
  data: AlertData;                   // REQUIRED — structured alert data
  timestamp: string;                 // REQUIRED — ISO timestamp
  ttl: number | null;                // OPTIONAL — time-to-live in seconds, null = no TTL
  firstSeen: string;                 // REQUIRED — first time this alert fired
  lastSeen: string;                  // REQUIRED — last time this alert fired
  count: number;                     // REQUIRED — times fired in current window
  dedupKey: string;                  // REQUIRED — dedup hash
  noiseCapHit: boolean;              // REQUIRED — true if alert was suppressed by noise cap
  rule: AlertRule;                   // REQUIRED — the rule that fired
}

interface AlertData {
  score: number | null;              // alert score, null if not score-based
  premium: number | null;            // alert premium, null if not premium-based
  sigma: number | null;              // sigma value, null if not sigma-based
  volume: number | null;             // volume, null if not volume-based
  vol_oi_ratio: number | null;       // vol/oi ratio, null if not applicable
  dte: number | null;                // dte, null if not applicable
  side: "BID" | "ASK" | null;        // inferred side, null if not applicable
  signal: "BULLISH" | "BEARISH" | null;  // derived signal
  hedge: boolean | null;             // put-ASK hedge flag
  classification: string | null;     // sweep/unusual/block/etc.
  bid: number | null;
  ask: number | null;
  last: number | null;
  strike: number | null;
  expiration: string | null;
  oi: number | null;
  spot: number | null;
}

interface AlertRule {
  name: string;                      // REQUIRED — rule name, e.g. "SCORE>=92"
  threshold: number | null;          // the threshold value
  operator: ">=" | ">" | "<" | "<=" | "==";  // comparison operator
  parameters: Record<string, any>;  // rule-specific parameters
}
```

**Required fields:** id, type, priority, ticker, contract, message, data, timestamp, firstSeen, lastSeen, count, dedupKey, noiseCapHit, rule

**Nullable fields:** ttl, and most AlertData fields (null when not applicable to the rule type)

**Honest empty states:**
- `noiseCapHit: true` → alert was fired but suppressed by noise cap (4/hour). UI shows "alert fired, not displayed (noise cap)".
- `data.score: null` → this is not a score-based alert (e.g., it's a WHALE alert)
- `priority: "LOW"` → low-priority alert, may be excluded from tape by noise cap

**Units:** score unitless 0-100; premium in $; sigma unitless; volume in contracts; vol_oi_ratio unitless; dte in days; timestamp ISO

**Source:** derived (from scan rows + alert engine rules)

**Inferred/proxy:** side (inferred), signal (derived from inferred side), hedge (derived)

---

## C5 — Tracker Item

A bookmarked trade in the Tracker. Source: localStorage-first, promoted to Mongo later.

```typescript
interface TrackerItem {
  id: string;                        // REQUIRED — unique tracker id
  ticker: string;                    // REQUIRED
  contract: string;                  // REQUIRED — "SPY 2026-09-18C450" style
  type: "CALL" | "PUT";              // REQUIRED
  strike: number;                    // REQUIRED
  expiration: string;                // REQUIRED
  side: "BID" | "ASK";               // REQUIRED — the side the user acted on
  action: "BUY" | "SELL";            // REQUIRED — user's action
  quantity: number;                  // REQUIRED — contracts/shares
  avgPrice: number;                  // REQUIRED — average entry price
  markPrice: number | null;          // OPTIONAL — current mark (mid → last → stale)
  markSource: "mid" | "last" | "stale" | null;  // DERIVED — where mark came from
  marketValue: number | null;        // DERIVED — quantity * markPrice, null if no mark
  unrealizedPnl: number | null;      // DERIVED — (markPrice - avgPrice) * quantity * 100 (options)
  unrealizedPnlPct: number | null;   // DERIVED — unrealizedPnl / (avgPrice * quantity * 100) * 100
  status: TrackerStatus;             // REQUIRED
  closeProxy: CloseProxy | null;     // OPTIONAL — OI drift close proxy, null until B1 lands
  enteredAt: string;                 // REQUIRED — ISO timestamp of entry
  updatedAt: string;                 // REQUIRED — ISO timestamp of last update
  notes: string | null;              // OPTIONAL — user notes
  verdict: InvestigationVerdict | null;  // OPTIONAL — from in-modal checklist
  frozen: boolean;                   // REQUIRED — true when mark data is stale
}

type TrackerStatus = "STILL IN" | "PENDING" | "PARTIAL" | "EXITED" | "EXPIRED" | "UNKNOWN";

interface CloseProxy {
  detected: boolean;                 // true if OI drift suggests close
  method: "oi_drift" | "volume_surge" | "expiry";  // proxy method
  confidence: number;                // 0-1 proxy confidence
  note: string;                      // "Closing detected via OI drift proxy" etc.
  // Close detection is a PROXY. Must be labeled as such in UI.
  // Cannot detect actual trade closes without print tape.
}

interface InvestigationVerdict {
  confirmed: boolean;                // true if user confirmed hypothesis
  skipped: boolean;                  // true if user skipped
  reason: string | null;             // user's reason
  steps: InvestigationStep[];        // which steps were checked
}

interface InvestigationStep {
  id: string;                        // step id, e.g. "netprem-5d"
  label: string;                     // human label, e.g. "Net Premium 5-7D"
  checked: boolean;                  // true if user checked this step
  read: string | null;               // what the user read, e.g. "+$2.3M net prem"
}
```

**Required fields:** id, ticker, contract, type, strike, expiration, side, action, quantity, avgPrice, status, enteredAt, updatedAt, frozen

**Nullable fields:** markPrice, markSource, marketValue, unrealizedPnl, unrealizedPnlPct, closeProxy, notes, verdict

**Honest empty states:**
- `status: "UNKNOWN"` → honest state when proxy can't decide (not an error)
- `markPrice: null` → "no mark" state (not $0 P/L)
- `frozen: true` → tracker renders FROZEN state (mark data stale)
- `closeProxy: null` → close detection unavailable (no B1 cadence yet)

**Units:** strike, avgPrice, markPrice in $; quantity in contracts; marketValue in $; unrealizedPnl in $; unrealizedPnlPct in %

**Timestamps:** enteredAt, updatedAt as ISO timestamps

**Source:** user input (entry) + snapshot data (mark) + derived (P/L)

**Inferred/proxy:** markSource (mid → last → stale fallback), closeProxy (OI drift proxy)

---

## C6 — Tab Configuration Object

Per-tab config substrate. One serialized object per tab. Source: localStorage, promoted to Mongo later.

```typescript
interface TabConfig {
  schemaVersion: number;             // REQUIRED — current schema version, for migration
  tabId: string;                     // REQUIRED — unique tab id
  name: string;                      // REQUIRED — user-visible tab name
  surface: "pulse" | "scanner";      // REQUIRED — which surface this tab is for
  ticker: string | null;             // OPTIONAL — per-ticker scope for pulse tabs, null for scanner tabs
  filters: FilterState;              // REQUIRED — filter state (see C16)
  columns: ColumnState;              // REQUIRED — column visibility + order
  highlighting: HighlightState;      // REQUIRED — highlighting rules (see C17)
  sort: SortState;                   // REQUIRED — sort configuration
  cap: number;                       // REQUIRED — results cap (50/100/250/500)
  createdAt: string;                 // REQUIRED — ISO timestamp
  updatedAt: string;                 // REQUIRED — ISO timestamp
}

interface ColumnState {
  visible: string[];                 // REQUIRED — ordered list of visible column ids
  order: string[];                   // REQUIRED — column order (may differ from visible)
}

interface HighlightState {
  sizeGTOI: boolean;                 // true → yellow highlight for size > OI
  volGTOI: boolean;                  // true → purple highlight for vol > OI
  // If OI=0 and numerator>0, treat as true (documented edge, not a bug)
  // If both zero, false
}

interface SortState {
  field: "time" | "premium" | "size" | "score" | "dte" | "strike";  // REQUIRED
  direction: "asc" | "desc";         // REQUIRED
  // Non-Time sorts apply $25K premium floor (see C16)
}

interface FilterState {
  equityType: ("stock" | "etf" | "index")[];  // REQUIRED — equity-type triple toggle
  sweepsOnly: boolean;               // REQUIRED — sweeps-only chip
  side: ("bid" | "mid" | "ask")[];  // REQUIRED — side chips
  otm: boolean;                      // REQUIRED — OTM toggle
  itm: boolean;                      // REQUIRED — ITM toggle
  dte0: boolean;                     // REQUIRED — 0DTE toggle
  opexOnly: boolean;                 // REQUIRED — OPEX-week-only toggle
  strikeMin: number | null;          // OPTIONAL — min strike
  strikeMax: number | null;          // OPTIONAL — max strike
  oiGrowthMin: number | null;        // OPTIONAL — min OI growth % (needs B1 for real values)
  contractSentimentMin: number | null;  // OPTIONAL — min contract sentiment (bid/ask mix)
  chainSentimentMin: number | null;  // OPTIONAL — min chain sentiment
  scoreAbsMin: number | null;        // OPTIONAL — |score| > X mode
  premiumMin: number | null;         // OPTIONAL — min premium (for non-Time sorts)
}

interface SortState {
  field: "time" | "premium" | "size" | "score" | "dte" | "strike";
  direction: "asc" | "desc";
}
```

**Required fields:** schemaVersion, tabId, name, surface, filters, columns, highlighting, sort, cap, createdAt, updatedAt

**Nullable fields:** ticker (null for scanner tabs), and all optional filter fields

**Honest empty states:**
- `ticker: null` + `surface: "pulse"` → tab is a scanner tab (market-wide)
- `filters.equityType: []` → all equity types included (default)
- `filters.sweepsOnly: false` → all rows included (default)

**Units:** cap in rows; strikes in $; premium in $; sentiment 0-1; oiGrowth in %

**Source:** user input (localStorage) + derived (defaults)

**Migration:** schemaVersion enables safe migration. Missing fields get defaults. Unknown fields are preserved but ignored.

---

## C7 — Chart Modal Series Payload

Chart modal data. Source: backend chain history (or Mongo snapshots) + Net Premium computation.

```typescript
interface ChartModalPayload {
  ticker: string;                    // REQUIRED
  contract: string;                  // REQUIRED — "SPY 2026-09-18C450" style
  type: "CALL" | "PUT";              // REQUIRED
  strike: number;                    // REQUIRED
  expiration: string;                // REQUIRED
  view: "contract-history" | "net-premium";  // REQUIRED — which view is active
  asOf: string;                      // REQUIRED — ISO timestamp

  // Contract history view
  contractHistory: ContractHistoryPoint[] | null;
  // null if no history available → honest empty state

  // Net Premium view
  netPremium: NetPremiumPoint[] | null;
  // null if no data available → honest empty state

  // Shared
  seriesTitle: string;               // REQUIRED — human title for the chart
  spot: number | null;               // OPTIONAL — underlying price for reference line
  spotLabel: string | null;          // OPTIONAL — "SPY $590.12" style label

  // Honest states
  loading: boolean;                  // REQUIRED — true while fetching
  stale: boolean;                    // REQUIRED — true when data is stale
  error: string | null;              // OPTIONAL — error message if fetch failed
  noData: boolean;                   // REQUIRED — true when no data available (not an error)
}

interface ContractHistoryPoint {
  timestamp: number;                 // REQUIRED — ms since epoch
  bid: number;                       // REQUIRED
  ask: number;                       // REQUIRED
  last: number;                      // REQUIRED
  iv: number;                        // REQUIRED
  volume: number;                    // REQUIRED
  oi: number;                        // REQUIRED
  vega: number | null;               // OPTIONAL — in-house greek, null if unavailable
  delta: number | null;              // OPTIONAL — in-house greek, null if unavailable
  gamma: number | null;              // OPTIONAL — in-house greek, null if unavailable
}

interface NetPremiumPoint {
  timestamp: number;                 // REQUIRED
  callPremium: number;               // DERIVED — sum of CALL premiums in window
  putPremium: number;                // DERIVED — sum of PUT premiums in window
  netPremium: number;                // DERIVED — callPremium - putPremium
  fir: number;                       // DERIVED — |callPrem - putPrem| / (callPrem + putPrem)
  sessionLean: "Bullish" | "Bearish" | "Neutral";  // DERIVED
}
```

**Required fields:** ticker, contract, type, strike, expiration, view, asOf, seriesTitle, loading, stale, error, noData

**Nullable fields:** spot, spotLabel, contractHistory, netPremium, vega, delta, gamma

**Honest empty states:**
- `loading: true` → chart shows loading state
- `noData: true` → chart shows "no data available" state (not empty chart)
- `error: "some message"` → chart shows error state with message
- `stale: true` → chart shows stale data warning
- `contractHistory: null` → "no contract history available" state
- `netPremium: null` → "no net premium data available" state

**Units:** timestamp ms; bid/ask/last/iv in $; volume/oi in contracts; vega/delta/gamma unitless greeks

**Source:** snapshot (chain history) + derived (Net Premium computation) + in-house (greeks)

**Inferred/proxy:** All greeks are in-house computed (D6). No vendor greeks.

---

## C8 — Net Premium Payload

Net Premium trend data. Source: aggregated chain snapshots over time windows.

```typescript
interface NetPremiumPayload {
  ticker: string;                    // REQUIRED
  window: "5d" | "7d" | "14d" | "30d";  // REQUIRED — time window
  asOf: string;                      // REQUIRED — ISO timestamp
  points: NetPremiumPoint[];         // REQUIRED — time series points
  summary: NetPremiumSummary;        // REQUIRED — summary stats
  loading: boolean;                  // REQUIRED
  stale: boolean;                    // REQUIRED
  noData: boolean;                   // REQUIRED
  error: string | null;              // OPTIONAL

  // Honest states
  baselineAvailable: boolean;        // REQUIRED — true if enough history for trend
}

interface NetPremiumPoint {
  timestamp: number;                 // REQUIRED
  callPremium: number;               // DERIVED
  putPremium: number;                // DERIVED
  netPremium: number;                // DERIVED
  fir: number;                       // DERIVED
  sessionLean: "Bullish" | "Bearish" | "Neutral";  // DERIVED
  volume: number;                    // DERIVED — total volume in window
}

interface NetPremiumSummary {
  totalCallPrem: number;             // DERIVED
  totalPutPrem: number;              // DERIVED
  totalNetPrem: number;              // DERIVED
  avgFIR: number;                    // DERIVED
  dominantLean: "Bullish" | "Bearish" | "Neutral";  // DERIVED — lean with most net premium
  peakNetPrem: number;               // DERIVED — max netPremium in series
  peakTime: number | null;           // DERIVED — timestamp of peak, null if no points
}
```

**Required fields:** ticker, window, asOf, points, summary, loading, stale, noData, baselineAvailable

**Nullable fields:** error

**Honest empty states:**
- `noData: true` → "no net premium data available" (not zeros)
- `baselineAvailable: false` → trend chart shows "insufficient history" warning
- `loading: true` → loading state

**Units:** premiums in $; fir unitless 0..1

**Source:** derived (aggregated snapshots)

**Inferred/proxy:** sessionLean derived from fir (derived from premiums). No confirmed direction.

---

## C9 — Strike Distribution Payload

Strike distribution histogram. Source: aggregated chain snapshots.

```typescript
interface StrikeDistributionPayload {
  ticker: string;                    // REQUIRED
  expiration: string | null;         // REQUIRED for single expiry, null for all
  asOf: string;                      // REQUIRED
  strikes: StrikeBin[];              // REQUIRED — histogram bins
  loading: boolean;                  // REQUIRED
  stale: boolean;                    // REQUIRED
  noData: boolean;                   // REQUIRED
  error: string | null;              // OPTIONAL

  // Summary
  totalVolume: number;               // DERIVED — total volume across all strikes
  totalOI: number;                   // DERIVED — total OI across all strikes
  atmStrike: number | null;          // DERIVED — strike closest to spot
  callWall: number | null;           // DERIVED — strike with max call OI
  putWall: number | null;            // DERIVED — strike with max put OI
  maxPain: number | null;            // DERIVED — max pain strike (largest OI difference)
  spot: number | null;               // OPTIONAL — underlying price for reference
}

interface StrikeBin {
  strike: number;                    // REQUIRED
  callVolume: number;                // DERIVED — call volume at strike
  putVolume: number;                 // DERIVED — put volume at strike
  callOI: number;                    // DERIVED — call OI at strike
  putOI: number;                     // DERIVED — put OI at strike
  totalVolume: number;               // DERIVED — callVolume + putVolume
  totalOI: number;                   // DERIVED — callOI + putOI
  callPrem: number;                  // DERIVED — estimated call premium at strike
  putPrem: number;                   // DERIVED — estimated put premium at strike
  netPrem: number;                   // DERIVED — callPrem - putPrem
}
```

**Required fields:** ticker, asOf, strikes, loading, stale, noData

**Nullable fields:** expiration, callWall, putWall, maxPain, atmStrike, spot, error

**Honest empty states:**
- `noData: true` → "no strike distribution data available"
- `loading: true` → loading state
- `stale: true` → stale data warning

**Units:** strike in $; volumes in contracts; OIs in contracts; premiums in $

**Source:** derived (aggregated snapshots)

**Inferred/proxy:** maxPain is a derived computation (largest OI difference). Not a prediction.

---

## C10 — Vol/OI History Payload

Vol/OI 14d footer table. Source: aggregated chain snapshots over 14 days.

```typescript
interface VolOIHistoryPayload {
  ticker: string;                    // REQUIRED
  contract: string;                  // REQUIRED — "SPY 2026-09-18C450" style
  type: "CALL" | "PUT";              // REQUIRED
  strike: number;                    // REQUIRED
  expiration: string;                // REQUIRED
  asOf: string;                      // REQUIRED
  days: VolOI day[];                 // REQUIRED — 14 days of data
  loading: boolean;                  // REQUIRED
  stale: boolean;                    // REQUIRED
  noData: boolean;                   // REQUIRED
  error: string | null;              // OPTIONAL

  summary: VolOISummary;             // REQUIRED — summary stats
}

interface VolOIDay {
  date: string;                      // REQUIRED — ISO date
  volume: number;                    // DERIVED — contract volume
  oi: number;                        // DERIVED — open interest
  vol_oi_ratio: number;              // DERIVED
  change: number | null;             // DERIVED — volume delta from previous day, null for first day
  oiChange: number | null;           // DERIVED — OI delta from previous day, null for first day
}

interface VolOISummary {
  avgVolume: number;                 // DERIVED — 14d average volume
  avgOI: number;                     // DERIVED — 14d average OI
  avgVolOIRatio: number;             // DERIVED — 14d average vol/oi
  totalVolume: number;               // DERIVED — 14d total volume
  totalOI: number;                   // DERIVED — 14d total OI
  maxVol: number;                    // DERIVED — max daily volume
  maxVolDate: string | null;         // DERIVED — date of max volume, null if no days
  maxOIRatio: number;                // DERIVED — max vol/oi ratio
  maxOIRatioDate: string | null;     // DERIVED — date of max ratio, null if no days
  trend: "increasing" | "decreasing" | "flat";  // DERIVED — volume trend over 14d
}
```

**Required fields:** ticker, contract, type, strike, expiration, asOf, days, summary, loading, stale, noData

**Nullable fields:** error, change (first day), oiChange (first day), maxVolDate, maxOIRatioDate

**Honest empty states:**
- `noData: true` → "no vol/OI history available" (needs B1 cadence)
- `days: []` → empty table (not zeros)
- `loading: true` → loading state
- `stale: true` → stale data warning

**Units:** date as ISO; volume in contracts; oi in contracts; vol_oi_ratio unitless; change/oiChange in contracts

**Source:** derived (aggregated snapshots)

**Inferred/proxy:** trend is a simple linear regression on 14d volume. Not a prediction.

---

## C11 — Dark Pool Level Payload

Dark pool Top-N levels. Source: FINRA ATS weekly + Reg SHO daily ETL (B3). NO side, NO direction.

```typescript
interface DarkPoolLevelsPayload {
  ticker: string | null;             // REQUIRED — null for market-wide view
  asOf: string;                      // REQUIRED — ISO timestamp of last ETL run
  etlLastRun: string;                // REQUIRED — ISO timestamp of last ETL execution
  etlSource: "finra_ats" | "reg_sho" | "both";  // REQUIRED — data source
  levels: DarkPoolLevel[];           // REQUIRED — Top-N clustered levels
  loading: boolean;                  // REQUIRED
  stale: boolean;                    // REQUIRED — true if etlLastRun is old
  noData: boolean;                   // REQUIRED — true when no dark pool data available
  paidGate: boolean;                 // REQUIRED — true when real-time TRF would be needed
  error: string | null;              // OPTIONAL

  summary: DarkPoolSummary;
}

interface DarkPoolLevel {
  clusterId: string;                 // REQUIRED — unique cluster id
  clusterPrice: number;              // DERIVED — clustered price level
  totalNotional: number;             // DERIVED — total notional in cluster ($)
  printCount: number;                // DERIVED — number of prints in cluster
  latestDate: string;                // REQUIRED — ISO date of most recent print in cluster
  ageDays: number;                   // DERIVED — days since latest print
  tickers: string[];                 // OPTIONAL — tickers in cluster (cross-symbol clustering)
  sector: string | null;             // OPTIONAL — sector if clustered by sector
  minPrice: number;                  // DERIVED — min print price in cluster
  maxPrice: number;                  // DERIVED — max print price in cluster
  priceRange: number;                // DERIVED — maxPrice - minPrice

  // NO side. NO direction. NO buy/sell. NO bullish/bearish.
  // Only: time, ticker, price, size, notional, sector, level, date.
}

interface DarkPoolSummary {
  totalNotional: number;             // DERIVED — total notional across all levels
  totalPrints: number;               // DERIVED — total print count
  uniqueLevels: number;              // DERIVED — number of clusters
  topLevelNotional: number;          // DERIVED — notional of largest cluster
  topLevelPrice: number | null;      // DERIVED — price of largest cluster, null if no levels
  oldestPrintDate: string | null;    // DERIVED — date of oldest print, null if no prints
  newestPrintDate: string | null;    // DERIVED — date of newest print, null if no prints
  sectors: string[];                 // DERIVED — unique sectors in data
}

interface DarkPoolLevelFilter {
  topN: 1 | 2 | 3 | 5;              // REQUIRED — Top N levels
  lookback: 30 | 45 | 90 | 180;     // REQUIRED — lookback days
  minNotional: number;               // REQUIRED — min notional filter ($)
  clusterTolerance: number;          // REQUIRED — price clustering tolerance ($ or %)
  sector: string | null;             // OPTIONAL — sector filter
}
```

**Required fields:** asOf, etlLastRun, etlSource, levels, loading, stale, noData, paidGate, summary

**Nullable fields:** ticker, error

**Honest empty states:**
- `noData: true` → "no free dark pool data available" (FINRA ATS/Reg SHO not available or no prints)
- `paidGate: true` → "real-time TRF prints require paid subscription" note
- `stale: true` → "dark pool data last updated X days ago" warning
- `loading: true` → loading state

**UI copy rules (D5):**
- ALLOWED: "large size transacted at this price", "off-exchange print", "level may act as reference", "no side is known"
- PROHIBITED: "dark pool buying", "dark pool selling", "institutions are long here", "bullish dark print", "bearish dark print", "confirmed buyer", "confirmed seller"

**Units:** clusterPrice in $; totalNotional in $; printCount in prints; ageDays in days; minPrice/maxPrice/priceRange in $

**Timestamps:** asOf, etlLastRun, latestDate as ISO timestamps/dates

**Source:** external (FINRA ATS weekly, Reg SHO daily) + derived (clustering)

**Inferred/proxy:** clusterPrice is a derived clustering (NOT a prediction). totalNotional is derived from print data. NO direction inferred.

---

## C12 — FINRA ATS Context Payload

FINRA ATS weekly venue share context. Source: FINRA ATS weekly ETL (B3).

```typescript
interface FINRAATSContextPayload {
  asOf: string;                      // REQUIRED — ISO date of data
  etlLastRun: string;                // REQUIRED — ISO timestamp of last ETL run
  stale: boolean;                    // REQUIRED — true if data is old
  loading: boolean;                  // REQUIRED
  noData: boolean;                   // REQUIRED — true when no FINRA ATS data
  error: string | null;              // OPTIONAL

  // Per-ticker venue share
  tickers: FINRAATSTicker[];         // REQUIRED

  // Market-wide summary
  summary: FINRAATSSummary;
}

interface FINRAATSTicker {
  ticker: string;                    // REQUIRED
  totalATSVolume: number;            // DERIVED — total ATS volume (shares)
  totalExchangeVolume: number;       // DERIVED — total exchange volume (shares)
  atsSharePct: number;               // DERIVED — ATS volume / (ATS + exchange) * 100
  topVenues: ATSVenue[];             // DERIVED — top ATS venues by volume
  weekEnding: string;                // REQUIRED — ISO date of week ending
  rank: number | null;               // DERIVED — rank by ATS share among all tickers, null if not ranked
}

interface ATSVenue {
  venue: string;                     // REQUIRED — ATS venue name
  volume: number;                    // DERIVED — volume at this venue
  sharePct: number;                  // DERIVED — venue volume / total ATS volume * 100
}

interface FINRAATSSummary {
  totalTickers: number;              // DERIVED — number of tickers with ATS data
  totalATSVolume: number;            // DERIVED — total ATS volume across all tickers
  avgATSSharePct: number;            // DERIVED — average ATS share across tickers
  topTicker: string | null;          // DERIVED — ticker with highest ATS share
  topTickerShare: number | null;     // DERIVED — top ticker's ATS share
  weekEnding: string;                // REQUIRED — week ending date
}
```

**Required fields:** asOf, etlLastRun, stale, loading, noData, tickers, summary

**Nullable fields:** error, topVenues (may be empty array), rank (null if not ranked)

**Honest empty states:**
- `noData: true` → "no FINRA ATS data available" (not zeros)
- `loading: true` → loading state
- `stale: true` → "FINRA ATS data as of X (Y days old)" warning

**UI copy rules:**
- ATS data is WEEKLY, not real-time. Must show weekEnding.
- ATS volume is context, not directional. No "ATS buying" or "ATS selling".
- "ATS share" = percentage of volume that went through ATS venues. Higher = more off-exchange activity.

**Units:** volume in shares; atsSharePct in %; weekEnding as ISO date

**Timestamps:** asOf, etlLastRun as ISO; weekEnding as ISO date

**Source:** external (FINRA ATS weekly) + derived (venue share computation)

**Inferred/proxy:** atsSharePct is derived from ATS + exchange volume data. Not a prediction.

---

## C13 — Reg SHO Short Pressure Payload

Reg SHO daily short pressure context. Source: Reg SHO daily ETL (B3).

```typescript
interface RegSHOContextPayload {
  asOf: string;                      // REQUIRED — ISO date of data
  etlLastRun: string;                // REQUIRED — ISO timestamp of last ETL execution
  stale: boolean;                    // REQUIRED
  loading: boolean;                  // REQUIRED
  noData: boolean;                   // REQUIRED
  error: string | null;              // OPTIONAL

  tickers: RegSHOTicker[];           // REQUIRED
  summary: RegSHOSummary;
}

interface RegSHOTicker {
  ticker: string;                    // REQUIRED
  shortVolume: number;               // DERIVED — short volume (shares), if available
  totalVolume: number;               // DERIVED — total volume (shares)
  shortPct: number | null;           // DERIVED — shortVolume / totalVolume * 100, null if data unavailable
  shortInterest: number | null;      // DERIVED — short interest (shares), if available from Reg SHO
  shortInterestPctOfFloat: number | null;  // DERIVED — shortInterest / float * 100, null if unavailable
  float: number | null;              // DERIVED — available float, null if unavailable
  closePrice: number | null;         // DERIVED — close price on data date, null if unavailable
  date: string;                      // REQUIRED — ISO date of data
  dataStatus: "available" | "estimated" | "unavailable";  // REQUIRED — data quality status
}

interface RegSHOSummary {
  totalTickers: number;              // DERIVED
  avgShortPct: number | null;        // DERIVED — average short % across tickers
  maxShortPct: number | null;        // DERIVED — highest short % ticker
  maxShortTicker: string | null;     // DERIVED — ticker with highest short %
  date: string;                      // REQUIRED — data date
}
```

**Required fields:** asOf, etlLastRun, stale, loading, noData, tickers, summary

**Nullable fields:** error, shortVolume, shortInterest, shortInterestPctOfFloat, float, closePrice, shortPct

**Honest empty states:**
- `noData: true` → "no Reg SHO data available"
- `shortPct: null` → "short %: unavailable" (not 0)
- `dataStatus: "unavailable"` → "short data not available for this ticker"
- `dataStatus: "estimated"` → "short data is estimated, not confirmed"

**UI copy rules:**
- Reg SHO data is DAILY, not real-time. Must show date.
- Short volume ≠ short interest. Short volume = shares traded short today. Short interest = shares short from previous settlement.
- Short pressure is CONTEXT, not directional. No "short squeeze imminent" or "short covering imminent".
- "shortPct" = short volume / total volume. Higher = more short activity today.

**Units:** shortVolume/totalVolume/float/shortInterest in shares; shortPct/shortInterestPctOfFloat in %; closePrice in $

**Timestamps:** asOf, etlLastRun as ISO; date as ISO date

**Source:** external (Reg SHO daily) + derived (short % computation)

**Inferred/proxy:** shortPct is derived from short volume / total volume. Not a prediction. shortInterest may be estimated if not directly available.

---

## C14 — Earnings Proximity Payload

Earnings proximity data. Source: Finnhub `/calendar/earnings` cache (B2).

```typescript
interface EarningsProximityPayload {
  ticker: string;                    // REQUIRED
  asOf: string;                      // REQUIRED — ISO timestamp of cache
  cacheLastUpdated: string;          // REQUIRED — ISO timestamp of last cache update
  stale: boolean;                    // REQUIRED — true if cache is old
  loading: boolean;                  // REQUIRED
  noData: boolean;                   // REQUIRED — true when no earnings data
  error: string | null;              // OPTIONAL

  earnings: EarningsInfo | null;     // REQUIRED — earnings info or null
  proximity: "none" | "before" | "after" | "during";  // DERIVED
  daysToEarnings: number | null;     // DERIVED — days until next earnings, null if no earnings
  daysSinceEarnings: number | null;  // DERIVED — days since last earnings, null if no earnings
}

interface EarningsInfo {
  nextDate: string | null;           // ISO date of next earnings, null if no upcoming
  nextHour: number | null;           // 0-23, earnings hour, null if unavailable
  lastDate: string | null;           // ISO date of last earnings, null if no history
  lastHour: number | null;           // 0-23, last earnings hour, null if unavailable
  quarter: string | null;            // e.g. "Q2 2026", null if unavailable
  status: "confirmed" | "tentative" | "unknown";  // earnings status
  source: "finnhub" | "unavailable";  // data source
}
```

**Required fields:** ticker, asOf, cacheLastUpdated, stale, loading, noData, earnings, proximity

**Nullable fields:** daysToEarnings, daysSinceEarnings, and most EarningsInfo fields

**Honest empty states:**
- `noData: true` → "no earnings data available" (Finnhub free tier may not have all tickers)
- `earnings: null` → "earnings: unknown" (not "no earnings")
- `nextDate: null` → "next earnings: unknown" (not "no upcoming earnings")
- `daysToEarnings: null` → "days to earnings: unknown"
- `stale: true` → "earnings data as of X" warning

**UI copy rules:**
- Finnhub free tier = 1 month historical + new updates. Multi-quarter surprise trends are NOT available.
- Earnings proximity = how close the current date is to the next earnings date.
- "before" = current date is before next earnings. "after" = current date is after last earnings. "during" = current date is within 24h of earnings.

**Units:** daysToEarnings/daysSinceEarnings in days; nextHour in 0-23

**Timestamps:** asOf, cacheLastUpdated as ISO; nextDate/lastDate as ISO dates

**Source:** external (Finnhub /calendar/earnings) + derived (proximity computation)

**Inferred/proxy:** proximity is derived from current date vs earnings date. Not a prediction.

---

## C15 — Sector/Industry Payload

Sector and industry data. Source: Finnhub `/stock/profile2` + static sector map.

```typescript
interface SectorIndustryPayload {
  ticker: string;                    // REQUIRED
  asOf: string;                      // REQUIRED — ISO timestamp of cache
  cacheLastUpdated: string;          // REQUIRED
  stale: boolean;                    // REQUIRED
  loading: boolean;                  // REQUIRED
  noData: boolean;                   // REQUIRED
  error: string | null;              // OPTIONAL

  profile: SectorIndustryProfile | null;
  sector: string | null;             // DERIVED — mapped from finnhubIndustry
  industry: string | null;           // DERIVED — from profile2
  equityType: "stock" | "etf" | "index";  // DERIVED — from static map
}

interface SectorIndustryProfile {
  name: string | null;               // company name, null if unavailable
  finnhubIndustry: string | null;    // Finnhub industry, null if unavailable
  exchange: string | null;           // exchange, null if unavailable
  logo: string | null;               // company logo URL, null if unavailable
  // Note: GICS sector is NOT directly available from profile2.
  // Must map finnhubIndustry → sector via static map.
}

// Static sector map (Agent 2 builds this)
// finnhubIndustry → sector mapping
// Example:
//   "Technology" → "Technology"
//   "Electronic Technology" → "Technology"
//   "Financial" → "Financial"
//   "Healthcare" → "Healthcare"
//   "Consumer" → "Consumer"
//   "Energy" → "Energy"
//   "Industrial" → "Industrials"
//   "Utilities" → "Utilities"
//   "Basic Materials" → "Materials"
//   "Real Estate" → "Real Estate"
//   "Services" → "Industrials"
//   "Conglomerates" → "Industrials"
//   "Transportation" → "Industrials"
//   Unknown/unmapped → "Other"
```

**Required fields:** ticker, asOf, cacheLastUpdated, stale, loading, noData, profile, sector, industry, equityType

**Nullable fields:** profile (null if no profile data), sector (null if unmapped), industry (null if unavailable), and all SectorIndustryProfile fields

**Honest empty states:**
- `noData: true` → "no sector/industry data available"
- `sector: null` → "sector: unknown" (not "no sector")
- `industry: null` → "industry: unknown"
- `equityType: "stock"` → default for unmapped tickers

**UI copy rules:**
- Sector comes from static finnhubIndustry→sector map, not from GICS directly.
- Industry comes from Finnhub profile2 finnhubIndustry field.
- Equity type comes from static map (SPY/QQQ/IWM/DIA/TLT = ETF; SPX/VIX = index; else stock).

**Source:** external (Finnhub profile2) + static (sector map, equity type map) + derived (sector, equityType)

**Inferred/proxy:** sector is a mapping, not a direct field. equityType is a static classification.

---

## C16 — Filter State Object

Filter state for Pulse/Scanner tabs. Source: user input (localStorage tab config).

```typescript
interface FilterState {
  // Equity type
  equityType: ("stock" | "etf" | "index")[];  // REQUIRED — which types to include
  // Default: all three. Empty = no rows.

  // Sweep filter
  sweepsOnly: boolean;               // REQUIRED — if true, only sweep-classified rows
  // Default: false. Sweep classification is a PROXY until P2 OPRA.

  // Side chips
  side: ("bid" | "mid" | "ask")[];  // REQUIRED — which sides to show
  // Default: all three.

  // Moneyness
  otm: boolean;                      // REQUIRED — include OTM contracts
  itm: boolean;                      // REQUIRED — include ITM contracts
  dte0: boolean;                     // REQUIRED — include 0DTE contracts
  // Default: all true. If all false, no rows.

  // OPEX
  opexOnly: boolean;                 // REQUIRED — if true, only OPEX-week expirations
  // Default: false.

  // Strike range
  strikeMin: number | null;          // OPTIONAL — min strike (inclusive)
  strikeMax: number | null;          // OPTIONAL — max strike (inclusive)
  // Default: null (no range).

  // OI growth (needs B1 cadence for real values)
  oiGrowthMin: number | null;         // OPTIONAL — min OI growth % (14d)
  // Default: null (no filter). null until B1 lands → filter disabled.

  // Sentiment (bid/ask mix)
  contractSentimentMin: number | null;  // OPTIONAL — min contract sentiment (0-1)
  // contractSentiment = 1 if all volume on ask side, 0 if all on bid
  chainSentimentMin: number | null;  // OPTIONAL — min chain sentiment (0-1)
  // chainSentiment = aggregated sentiment across all contracts in chain
  // Default: null (no filter).

  // Score
  scoreAbsMin: number | null;        // OPTIONAL — min |score| for display
  // Default: null (no filter). |score| mode.

  // Premium
  premiumMin: number | null;         // OPTIONAL — min premium for display
  // Default: null. Used for non-Time sort floor (see C17).

  // Debug/test
  debugRowCount: boolean;            // OPTIONAL — if true, show before/after row counts
  // Default: false. For test mode only.
}
```

**Required fields:** equityType, sweepsOnly, side, otm, itm, dte0, opexOnly

**Nullable fields:** strikeMin, strikeMax, oiGrowthMin, contractSentimentMin, chainSentimentMin, scoreAbsMin, premiumMin

**Honest empty states:**
- `equityType: []` → no rows (all types excluded)
- `side: []` → no rows (all sides excluded)
- `otm: false, itm: false, dte0: false` → no rows (no moneyness included)
- `oiGrowthMin: null` → OI growth filter disabled (needs B1)

**Filter subtractiveness rule:**
- Filters are subtractive. Each filter removes rows that don't match.
- No filter ADDS rows.
- `sweepsOnly: true` removes non-sweep rows. It does NOT scale bars upward.
- Empty filter state = all rows included (subject to other filters).

**Before/after row counts:**
- When `debugRowCount: true`, UI shows: "X rows before filters, Y rows after" for each filter.
- Used for test mode and performance profiling.

**Empty-state widen actions (W7 M3):**
- "Lower premium min" → sets premiumMin to null or lower value
- "Enable ETFs" → adds "etf" to equityType
- "Clear sweep-only" → sets sweepsOnly to false
- "Lower score threshold" → sets scoreAbsMin to null or lower value
- "Clear DTE band" → enables otm, itm, dte0

**Units:** strikeMin/strikeMax in $; oiGrowthMin in %; contractSentimentMin/chainSentimentMin unitless 0-1; scoreAbsMin unitless 0-100; premiumMin in $

**Source:** user input (localStorage) + derived (defaults)

**Inferred/proxy:** sweepsOnly operates on sweep classification (proxy). contractSentiment/chainSentiment are derived from bid/ask mix (snapshot data).

---

## C17 — Highlight Rule Object

Highlighting rules for Pulse/Scanner rows. Source: user input (localStorage tab config).

```typescript
interface HighlightState {
  sizeGTOI: boolean;                 // TRUE → yellow highlight when volume > OI
  volGTOI: boolean;                  // TRUE → purple highlight when vol/oi_ratio >= 1.5
  // Edge cases:
  // - OI=0 and volume>0: treat as true (documented, not a bug)
  // - both zero: false (no data to compare)
  // - vol/oi_ratio exactly 1.0: false for volGTOI (needs >= 1.5)
}

interface HighlightRule {
  id: string;                        // REQUIRED — "size-gtoi" or "vol-gtoi"
  enabled: boolean;                  // REQUIRED
  color: string;                      // REQUIRED — CSS color
  label: string;                     // REQUIRED — human label, e.g. "Size > OI"
  condition: string;                 // REQUIRED — human-readable condition, e.g. "volume > open interest"
  note: string | null;               // OPTIONAL — edge case note, e.g. "OI=0 treated as true"
}

interface HighlightStateExtended {
  rules: HighlightRule[];            // REQUIRED — all available rules
  active: string[];                  // REQUIRED — ids of active rules
  perTab: boolean;                   // REQUIRED — true if highlights are per-tab
  persisted: boolean;                // REQUIRED — true if highlights persist across reloads
}
```

**Required fields:** sizeGTOI, volGTOI

**Honest empty states:**
- `sizeGTOI: false, volGTOI: false` → no highlights (not an error)
- `sizeGTOI: true` with all OI=0 rows → all rows highlighted yellow (documented edge case)

**Edge case documentation:**
- OI=0 and volume>0: sizeGTOI = true (volume > 0 = volume > OI when OI=0). This is intentional and documented, not a bug.
- Both zero: sizeGTOI = false (no data to compare).

**Units:** unitless booleans

**Source:** user input (localStorage) + derived (defaults)

**Inferred/proxy:** Highlights are based on snapshot data (volume, OI). Not confirmed institutional activity.

---

## C18 — Empty/Loading/Stale/Error/Frozen/No-Quote/No-Baseline States

Standard surface states. Every new surface must ship all of these.

```typescript
type SurfaceState = "loading" | "empty" | "stale" | "error" | "frozen" | "no-quote" | "no-baseline" | "paid-gate" | "no-data" | "unknown";

interface SurfaceStateConfig {
  state: SurfaceState;
  label: string;                     // REQUIRED — user-visible label
  description: string;               // REQUIRED — user-visible description
  icon: string | null;               // OPTIONAL — icon name
  action?: string;                   // OPTIONAL — one-click action label
  actionHandler?: string;            // OPTIONAL — action handler name
  // Action examples:
  // - "loading" → "Retry"
  // - "empty" → "Widen filters" / "Show all rows"
  // - "stale" → "Refresh"
  // - "error" → "Retry" / "Report issue"
  // - "frozen" → "Resume feed"
  // - "no-quote" → "Try different ticker"
  // - "no-baseline" → "Baseline building n/20"
  // - "paid-gate" → "Upgrade to access"
  // - "no-data" → "No data available for this request"
  // - "unknown" → "Data status unknown"
}

// State definitions
const STATE_DEFS: Record<SurfaceState, SurfaceStateConfig> = {
  loading: {
    label: "Loading",
    description: "Fetching data…",
    icon: "spinner",
    action: "Retry",
    actionHandler: "retry",
  },
  empty: {
    label: "No data",
    description: "No rows match your current filters.",
    icon: "empty",
    action: "Widen filters",
    actionHandler: "widenFilters",
  },
  stale: {
    label: "Stale data",
    description: "Data hasn't been updated in a while.",
    icon: "stale",
    action: "Refresh",
    actionHandler: "refresh",
  },
  error: {
    label: "Error",
    description: "Something went wrong loading this data.",
    icon: "error",
    action: "Retry",
    actionHandler: "retry",
  },
  frozen: {
    label: "Feed paused",
    description: "Market data feed is paused or disconnected.",
    icon: "frozen",
    action: "Resume feed",
    actionHandler: "resumeFeed",
  },
  "no-quote": {
    label: "No quote available",
    description: "Bid/ask/last data is not available for this contract.",
    icon: "no-quote",
    action: "Try different ticker",
    actionHandler: "changeTicker",
  },
  "no-baseline": {
    label: "Baseline building",
    description: "Historical baseline is being built. RVOL will be available once complete.",
    icon: "baseline",
    action: null,
    actionHandler: null,
  },
  "paid-gate": {
    label: "Paid feature",
    description: "This data requires a paid subscription.",
    icon: "paid",
    action: "Learn more",
    actionHandler: "learnMore",
  },
  "no-data": {
    label: "No data available",
    description: "No data is available for this request.",
    icon: "no-data",
    action: null,
    actionHandler: null,
  },
  unknown: {
    label: "Status unknown",
    description: "Unable to determine data status.",
    icon: "unknown",
    action: "Refresh",
    actionHandler: "refresh",
  },
};
```

**Rule:** Every new surface in Phase 9 must ship ALL of these states. Agent 2's tests must verify each state renders correctly on fixtures.

**State precedence (highest to lowest):**
1. error — error takes precedence over everything
2. loading — loading takes precedence over data states
3. frozen — frozen takes precedence over data
4. stale — stale data warning
5. no-quote — no quote available
6. no-baseline — baseline building
7. paid-gate — paid feature gate
8. no-data — no data available
9. unknown — status unknown
10. empty — no rows match (lowest precedence, only when no higher state applies)

**Honest empty state rules:**
- "empty" = no rows match filters (not "no data available")
- "no-data" = the request returned no data at all (not "no rows")
- "no-quote" = bid/ask/last is 0 or missing (not "no data")
- "no-baseline" = RVOL baseline not yet built (not "RVOL unavailable")
- "paid-gate" = feature requires paid subscription (not "feature unavailable")
- "frozen" = feed is paused/disconnected (not "error")
- "stale" = data is old but still displaying (not "error")
- "error" = fetch failed or returned error (not "no data")
- "loading" = fetch in progress (not "empty")
- "unknown" = cannot determine status (not "error")
