## Destination

Floww has enough settled provider, entitlement, semantic, retention, rollout, and
acceptance decisions to file independent contract-grade issues for a shadow-tested
proprietary market-data plane without changing existing signal meaning.

## Decisions so far

- Floww remains paper/simulation only; this data transition does not authorize live execution.
- Public API remains the comparator and rollback source during shadow operation.
- Provider adapters terminate at normalized contracts with field-level provenance; consumers do not depend on vendor payloads.
- Quote-derived side and aggregate proxies remain labeled separately from exchange-reported trades.
- Frozen ML/model artifacts and the dual GEX scale convention do not change in this program.

## Existing Floww signals that already carry institutional edge

These are the existing proprietary-signal candidates already in the codebase
(2026-09-08). Each is independent of any new vendor — they already live on public
data + internal analytics. They are the "institutional edge" layer as it exists
today; a proprietary market-data plane would RAISE their data quality, not
redefine them.

### 1. Multi-Level Order Flow Imbalance (MLOFI) — `backend/services/multi_level_ofi.py`

**What it is.** Per Xu/Gould/Howison (2019, arXiv:1907.06230), a limit-order-book
OFI vector across N levels plus an aggregated OFI scalar and a buy/sell/neutral
label. Two implementations:

- `MultiLevelOFI` — real LOB snapshots `{level: {bid: (px, sz), ask: (px, sz)}}`.
  Computes the paper's per-level net-flow delta. Pure Python, no torch/numba/scipy.
- `StructuralOFI` — chain-based proxy when LOB data is absent: uses call_oi + put_oi
  delta per strike across two consecutive options-chain snapshots, weighted by
  call-vs-put dominance. NOT the paper's MLOFI directly; a correlated proxy for
  the Flowseeker feed until a real LOB feed lands.

**Institutional edge today.** The chain-based structural OFI already reads
institutional positioning from options open-interest rotation — call OI growth at
strikes weighted toward call dominance = buy-side institution flow; put OI growth
= sell-side. That is real orderflow signal from public data (Finnhub/Yfinance
chains) that most retail traders never compute.

**What proprietary data improves.** A real LOB feed (level 2/3, tick-by-tick)
would let `MultiLevelOFI` replace `StructuralOFI` as the primary path. The formula
does not change — only the input surface upgrades from chain-derive to actual book.
The chain proxy stays as a fallback / coverage extension for symbols where the
proprietary feed has no book snapshot.

**Tests:** `backend/tests/test_multi_level_ofi.py` — 9 tests, all passing.
Locks warming state, buy-pressure detection, sell-pressure bulletproof single-side
scenario, history buffer clamp, structural OFI call growth / put inversion, and
waking-flip-after-second-fetch. Do not touch these tests without a real regression.

### 2. Composite Flow Score — `backend/services/composite_flow_score.py`

**What it is.** Headline 0..100 conviction synthesis of five orthogonal sub-scores:

| Sub-score | Weight | Source | Signal |
|-----------|--------|--------|---------|
| Illiquidity | 0.25 | Amihud + Kyle's λ | Shallow markets / adverse-cost risk |
| Toxicity | 0.20 | VPIN | Informed-fraction in order flow |
| Dislocation | 0.25 | HMM regime × OFI disagreement | Mispricing when regime and flow diverge |
| Direction | 0.20 | |OFI aggregate| capped at 1000 shares | Book dominance direction |
| Sentiment | 0.10 | Social-flow polarity | Conviction magnitude from retail/social signal |

Four-band label: HIGH (≥80) / MED (60–79) / WATCH (40–59) / LOW (<40).
Strict ANY-warming: if any sub-service is warming, `composite = 0` and label = LOW.

**Institutional edge today.** This is the "institutional conviction" headline that
competes with institutional flow desks' internal scoring. It combines microstructure
liquidity, informed-flow toxicity, regime context, orderflow direction, and
sentiment into a single tradable-conviction number. A proprietary feed would give
it real-time LOB inputs instead of chain-derived OFI, and would let VPIN use actual
trade/quote tick streams instead of aggregate approximations.

**Tests:** `backend/tests/test_composite_flow_score.py` — exists, passing.

### 3. HMM Regime Detector — `backend/services/hmm_regime.py`

**What it is.** Pure-Python 3-state Gaussian Hidden Markov Model (no torch/numba).
Two features per observation: log(call_vol+1)/(put_vol+1) clipped to [-3,3], and
total_vol/(total_oi+1) clipped to [0,5]. Three regimes dynamically relabeled by
per-state mean of feature[0]: TRENDING_BULL (highest call dominance), RANGING
(middle), TRENDING_BEAR (lowest / put dominance). Baum-Welch EM, forward-backward
smoothing, log-space numerics.

**Institutional edge today.** Regime detection from options-volume asymmetry is a
real institutional signal — it tells you whether the market is in a call-dominated
trend, a put-dominated trend, or noise. Institutions use regime filters to decide
whether their book-bias signals are tradable.

**What proprietary data improves.** Real-time tick data would let the HMM run on
actual trade/quote ticks instead of chain snapshots, tightening regime transitions
and giving higher-confidence state assignments faster.

**Tests:** `backend/tests/test_hmm_regime.py` — 10 tests, all passing. Locks
warming, buffer clamp, fit invalidation, posterior sum-to-one, smoothed path,
mean shift after fit, distinct-label separation, bull/bear concentration, and
confidence thresholds.

### 4. Chain Replay — `backend/services/chain_replay.py`

**What it is.** Rolling-buffer history of Composite Flow Score + sub-scores per
symbol. Push-on-composite-fetch, 240-snapshot deque (~2hrs at 30s polling), FIFO
cap at 64 symbols. Read-tail, read-window, read_payload, summarise_iterable.

**Institutional edge today.** This is the replay/scrub capability that lets a desk
review how conviction evolved through a session — the institutional "what happened"
tool. Pure Python, no ML.

### 5. Flow Toxicity / VPIN — `backend/services/vpin_engine.py` + related

**What it is.** Volume-synchronized probability of informed trading. VPIN is the
classic microstructure informed-flow metric. In Floww it feeds the toxicity sub-score
of the composite.

**Institutional edge today.** VPIN is exactly the kind of signal institutional
flow desks watch — it separates informed vs uninformed flow. Combined with the
composite's illiquidity and dislocation, it gives a real microstructure-informed
conviction picture from public data.

### 6. Kyle's Lambda / Amihud — `backend/services/kyle_lambda.py` + `amihud_illiquidity.py`

**What they are.** Kyle's λ measures price impact per unit volume (informed trader
pressure). Amihud measures price impact per dollar volume (liquidity measure).
Both feed the illiquidity sub-score.

**Institutional edge today.** These are institutional microstructure measures.
Institutions use them to size through liquid vs illiquid books. Floww already
computes them from public quote volume data.

## What "institutional edge" means here

Institutional edge, in the Floww context, is the ability to read orderflow,
microstructure, regime, and conviction from data that most retail traders don't
process — and to do it at quality that competes with institutional flow desks.

Today that edge comes from:

1. **Options-chain orderflow signal** (`StructuralOFI`): reading institutional
   positioning from OI rotation at strikes — retail doesn't compute this.
2. **Microstructure conviction synthesis** (`CompositeFlowScore`): combining VPIN,
   Kyle, Amihud, HMM regime, OFI, and sentiment into one 0..100 number.
3. **Regime-filtered tradability** (`hmm_regime`): only trusting directional signals
   when regime agrees — institutional discipline.
4. **Replay/scrub** (`chain_replay`): post-session review of conviction evolution.
5. **Toxicity + illiquidity** (VPIN, Kyle, Amihud): informed-flow and liquidity
   quality measures from public data.

None of this requires a proprietary feed. The proprietary feed is an upgrade path,
not a prerequisite.

## What a proprietary market-data plane would add

Per the PROPRIETARY-DATA-DISCOVERY-MAP, the open questions are:

- D-1: Which vendor/feed/account, which entitlements (real-time, delayed, historical,
  OPRA, equities, index-options, Greeks, OI, redistribution)?
- D-2: Authoritative event/correction semantics (timestamps, sequences, venues,
  condition codes, cancels, crossed/locked quotes, missing fields)?
- D-3: Licensing, retention, display boundaries?
- D-4: Shadow acceptance and rollback thresholds (coverage, freshness, gap, duplicate,
  correction, parity, latency, cost)?
- D-5: Replay retention and recovery objectives?
- D-6: User-visible provenance and degraded-state behavior?

Until D-1 is resolved, the following is the architectural direction NOT a
commitment to build:

### Shadow-tested proprietary plane — architectural direction

1. **Provider adapter layer**: new `backend/services/proprietary_book.py` (or similar)
   that terminates at the same normalized LOB snapshot contract that `MultiLevelOFI`
   already consumes: `{level: {bid: (px, sz), ask: (px, sz)}}`. Consumers do NOT
   change — only the input source. Public-api comparator stays as fallback.

2. **Field-level provenance**: every LOB snapshot carries `{source: "proprietary"|"public",
   age_ms, coverage, delayed_real_time, correction_state, fallback_chain}`. The
   composite and OFI output carry provenance so the UI can show "this signal is from
   proprietary book data, age 23ms" or "degraded: using chain proxy, public data".

3. **Shadow operation**: proprietary source runs in parallel with public source,
   logged but not preferred. Acceptance thresholds (D-4) must hold before any
   consumer prefers the proprietary source. Rollback = flip preference back to public.

4. **VPIN upgrade path**: if the proprietary feed carries trade/quote tick streams,
   `vpin_engine.py` could use real ticks instead of aggregate approximations. Same
   VPIN formula, better input.

5. **HMM upgrade path**: if the proprietary feed carries real-time ticks, the HMM
   could run on actual trade/quote ticks rather than chain snapshots. Same Baum-Welch
   EM, tighter transitions.

6. **No new alpha**: this program does NOT introduce new signals, thresholds, causal
   claims, or ML retraining merely because richer data is available. Existing signal
   meaning is preserved (per the map's decisions). The proprietary plane raises data
   quality, not signal count.

## Files that must not change

- `backend/services/multi_level_ofi.py` — formula is locked by tests. New provider
  feeds INTO the existing `MultiLevelOFI.push_snapshot` contract. Do not change the
  OFI formula without re-proving all 9 tests.
- `backend/services/composite_flow_score.py` — weights and synthesis locked by tests.
  New data feeds the existing sub-score inputs. Do not change weights without re-proving.
- `backend/services/hmm_regime.py` — Baum-Welch EM, 3-state structure, feature
  contract locked by tests. New data feeds the existing `push_observation` contract.
- `backend/tests/test_multi_level_ofi.py` — 9 tests, must keep passing.
- `backend/tests/test_hmm_regime.py` — 10 tests, must keep passing.
- `backend/tests/test_composite_flow_score.py` — must keep passing.
- `backend/tests/test_chain_replay.py` — must keep passing.
- Frozen ML/model artifacts (Round-9 freeze rule).
- Dual GEX scale convention.

## Out of scope for this program

- Automated live-order execution (Floww is paper/simulation only).
- New alpha, thresholds, causal claims, or ML retraining from richer data.
- Direct-exchange/Kafka/Flink/ClickHouse infrastructure before D-1 proves need + entitlement.
- Replacing the Tidehunter UI before B0 redesign artifacts and Nav visual sign-off.
- Folding `swarmSPX` into Floww.

## Current status

- What exists: MLOFI (LOB + chain proxy), Composite Flow Score (5-sub-score synthesis),
  HMM regime (3-state Baum-Welch), Chain Replay, VPIN, Kyle, Amihud — all from public
  data, all tested, all passing. This is the institutional edge as it exists today.
- What does NOT exist: any proprietary market-data provider adapter, any shadow
  operation, any D-1 resolution, any entitlement confirmation.
- What is pending: D-1 (vendor/entitlement) must resolve before any code is written.
  This file is the institutional-edge reference doc, not a build plan.

## Queue issues

- D-1 vendor/entitlement — Nav-gated (needs real account/contract).
- D-4 shadow acceptance thresholds — Nav-gated.
- D-6 provenance/UI behavior — Nav-gated.
