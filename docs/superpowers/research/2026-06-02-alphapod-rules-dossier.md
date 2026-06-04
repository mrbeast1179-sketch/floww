# AlphaPod Flow-Alert Rules Dossier (reverse-engineered)

> Source of truth for **Plan 02 — Alert Engine**. Reverse-engineered read-only from the scraped mirror `~/GitHub/hub-alphapodtrading`. OBSERVED = quoted/derived from real data or the JS bundle; INFERRED = stated as such.

## Ground truth
The flow-alert ground truth is the live `/alerts` capture: **73 unique alerts** = `api-data/alerts-p1.json` (50) + `alerts-p2.json` (23), pagination `total=73, page_size=50` (mirror: `alerts-live-p1-fresh.json`). The other ~2,148 `api-data/*.json` are per-ticker deep-dive/chart/digest artifacts (they feed Ticker Analysis / Daily Report, **not** the alert engine). The daily digest (`alpha-flow*.json` → `top_10`, `unusual_flow.items`) is a **separate ticker-level rollup** with its own fields (`conviction_tier`, `composite_score`, `structure_label`, `top_contracts[]`) — do not conflate with the per-contract alert engine.

**ARCHITECTURAL FINDING (OBSERVED):** rule classification AND confidence scoring are 100% server-side. The SPA bundle only sorts/filters/colors pre-computed fields. The rubric is recoverable because every alert carries `confidence_factors[]` — plain-English strings naming each threshold bucket and point adjustment.

## A. Alert schema (47 fields, all present on 73/73)
`alert_id`(uuid) · `ticker` · `option_type`(put/call) · `strike`(float) · `expiration`(date) · `dte`(int) · `premium`(float, total $ of the leg) · `size`(int contracts) · `side`(buy=ask/sell=bid) · `alert_rule`(str — the rule) · `has_sweep`(bool) · `has_floor`(bool) · `volume`(int) · `open_interest`(int) · `vol_oi_ratio`(float) · `spot_price`(float) · `market_cap`(float — drives FloorTrade cap class) · `sector`(str/null — sector WR bonus) · `tier`(int: **0=index/SPY-special, 1=highest, 2=standard**) · `iv`(float/null) · `delta`,`gamma`(**always null**) · `is_spread`(bool) · `spread_type`(str/null e.g. "DIAGONAL PUT SPREAD","MULTI-LEG") · `spread_net_premium` · `spread_gross_buy`/`spread_gross_sell` · `avg_fill_price`(float — drives Asc/Desc) · `spread_partner_{strike,side,size,expiration,option_type,alert_id}` · `spread_primary_leg`(bool/null) · `created_at`(ISO ET) · `sentiment`(NEUTRAL/BULLISH/BEARISH) · `exec_type`(SINGLE/SWEEP/FLOOR — mutually exclusive) · `confidence`(LOW/MED/HIGH) · `confidence_score`(int 0–100) · `confidence_factors`(str[] — the rubric) · `direction`(ambiguous/bullish/bearish) · `pct_otm`(float; call=`(strike−spot)/spot*100`, put=`(spot−strike)/spot*100`; negative=ITM) · `iv_rank`,`oi_change`,`classified_pct`,`stickiness`(**always null**).

## B. Rule catalog (13 observed + 4 bundle-only)
Glossary (OBSERVED, verbatim from bundle):
- **Virgin Strike**: first-ever activity on this strike — brand-new positioning.
- **RepeatedHits**: same contract hit multiple times — accumulation.
- **RepeatedHitsAscendingFill**: repeated hits, rising fills — aggressive accumulation.
- **RepeatedHitsDescendingFill**: repeated hits, falling fills — distribution/averaging-down.
- **Golden Sweeps**: large multi-exchange sweep — urgent institutional buying.
- **OTM Conviction**: OTM options with high conviction.
- **LowHistoricVolumeFloor**: floor trade on a contract with unusually low historical volume.
- **FloorTradeLargeCap/MidCap/SmallCap**: cap-bucketed institutional floor block.
- **SweepsFollowedByFloor**: sweep then floor on same contract — double confirmation.
- **Small Cap Sweep**: sweep on a small-cap name.

Per-rule stats from the 73 (n · premium range · key discriminator):
- **RepeatedHits** n=26 · $54.6K–3.45M · same contract repeated, no fill trend.
- **RepeatedHitsAscendingFill** n=16 · $60K–3.62M · `avg_fill_price` rising; mostly SWEEP. base WR 61.2% (highest).
- **RepeatedHitsDescendingFill** n=7 · $88K–2.07M · `avg_fill_price` falling.
- **LowHistoricVolumeFloor** n=6 · $350K–5.38M · `exec_type=FLOOR`, long-dated, large premium.
- **Golden Sweeps** n=5 · $264K–463K · **call+buy+SWEEP=100%, always BULLISH, tier 2**; premium floor ≈ $264K. Ex: `DOCU 65C buy, $463,365, size 3646, vol/OI 38.4, SWEEP → HIGH(76)`.
- **FloorTradeLargeCap** n=3 · mcap 12.9–24.4B · FLOOR.
- **FloorTradeMidCap** n=1 · mcap 2.9B · FLOOR.
- **OtmEarningsFloor** n=1 · mcap 649B · FLOOR + OTM near earnings; base WR 71.8%.
- **OTM Conviction** n=2 · call+buy, SINGLE, `pct_otm ≳ 16%` (obs 16.8 & 23.4).
- **SPY_call_buy_TIER_2 / SPY_put_buy_TIER_2 / SPY_put_sell_TIER_2 / SPY_call_buy_HIGH_CONVICTION** · all tier=0, SPY, ATM (`pct_otm≈−3…0`), $1.0–1.6M, SINGLE. HIGH_CONVICTION base WR 55% vs TIER_2 50%.

## C. Confidence scoring (the core deliverable)
Additive: start at rule **base win-rate**, apply bucket adjustments, **cap at 69 if `is_spread`** (all 41 spreads carry "Capped at MED: alert is part of a multi-leg structure"; max non-spread = 89), then bucket:
> **LOW ≤54 · MED 55–69 · HIGH ≥70** (OBSERVED, clean).

- **Rule base WR (OBSERVED):** AscendingFill 61.2 · Golden Sweeps 57.4 · RepeatedHits 53.4 · DescendingFill 52.0 · FloorMidCap 50.0 · LowHistVolFloor 47.7 · FloorLargeCap 47.6 · OTM Conviction & OtmEarningsFloor 71.8 · SPY_*_TIER_2 50.0 · SPY HIGH_CONVICTION 55.0.
- **DTE buckets:** ~3 momentum · 10–11 good (57.6) · 16 moderate (57.5) · 24 extended · 30–45 longer (~51) · 60–108 long · 136–227 "very long — avoid".
- **Premium buckets:** $55–88K light · $102–491K moderate (~48) · $506–937K significant block (52.7) · $1.0–3.6M institutional (59.3, best) · $5.4M+ very large (hedging risk). Approx gates: ≥$100K, ≥$500K, ≥$1M, ≳$5M.
- **Vol/OI buckets:** 0–0.9 below OI (~55) · 1.0–2.3 moderate · 3.2–4.8 sweet spot · 5.5–8.1 elevated · 10.3–42.5 very high (~56) · ≥~50 extreme/gamma (45).
- **Execution:** buy/ask "directional" (56.6) · sell/bid "may be hedge" (48.2) · SWEEP (58.5 vs 52.1) · FLOOR "neutral" (51.2).
- **Size vs OI:** size>OI "dominant new position" · 53–90% "strong new money" · 22–43% "moderate".
- **Directional ± points (OBSERVED explicit):** Bullish sweep **+3** · Bearish $500K+ **+2** · Bearish no-sweep **+1** · Put-sale (put+bid) **−3** · Call-sale (call+bid) **−3** · Ambiguous **−3**.
- **Sector ± (OBSERVED):** Energy +2 · Consumer Defensive +1 · Technology +1 · Financial Services +1 · Industrials +1 · Healthcare −1.
- **Tier:** 1 highest · 2 standard (52.3) · 0 index (string mislabels as "Tier 4", 61.4).

## D. Sort modes (bundle, OBSERVED)
Default `actionability`. `Hv={HIGH:3,MED:2,LOW:1}`.
- actionability → `conviction_score` desc
- confidence → tier desc, then score desc
- premium → `total_premium` desc
- ticker → `localeCompare` A→Z
UI premium bands: `premium>=1e6` "Meaningful", `>=5e5` "Medium". `customMinPremium` default `250000`. Filters: direction, `conviction_tier==='HIGH'`, watched, sector, theme. Rule-name normalizer `Oh(e)=e.replace(/[\s_-]+/g,'').toLowerCase()`.

## E. Repeated-hits semantics
Group key = same contract `(ticker, option_type, strike, expiration)` within a session. Multiple prints → Repeated-Hits family. `avg_fill_price` trend across prints: rising → AscendingFill, falling → DescendingFill, else RepeatedHits. Hit count not its own field (implicit; the digest layer surfaces `total_contracts_added`/`oi_change`). Re-impl must track per-(contract, session) print sequences and compare consecutive fills.

## F. Threshold constants in bundle
`premium>=1e6`, `premium>=5e5` (UI gates); `customMinPremium=250000`; tier map `{HIGH:3,MED:2,LOW:1}`. Rule thresholds themselves are server-side — reconstructed in §C from `confidence_factors`.

## G. Re-implementation notes (floww feed: ticker,type,side,strike,expiry,premium,oi,size,volume)
Derive per print: `vol_oi_ratio=volume/oi`; `pct_otm` (formulas in §A); `dte`; `exec_type∈{SINGLE,SWEEP,FLOOR}` (need a sweep detector = same contract across exchanges in a tight window; a floor/block detector).

Rules to encode:
1. **RepeatedHits family** — group by (ticker,type,strike,expiry); ≥N repeats fire; sub-classify by consecutive `avg_fill_price` trend.
2. **Golden Sweeps** — call & buy & SWEEP & premium ≳ $250K (obs floor $264K) → BULLISH, tier 2.
3. **OTM Conviction** — pct_otm ≳ 16% & buy (calls), large premium/volume, no sweep/floor.
4. **LowHistoricVolumeFloor** — FLOOR & volume high vs the contract's historical baseline; long-dated, large premium.
5. **FloorTrade{Large|Mid|Small}Cap** — FLOOR bucketed by underlying market_cap (Large ≳ $10–13B; Mid ≈ $2–10B; Small below — exact cuts server-side).
6. **OtmEarningsFloor** — FLOOR & OTM & within earnings window.
7. **SweepsFollowedByFloor** — SWEEP then FLOOR on same contract.
8. **Virgin Strike** — first-ever activity (`oi_prior==0`, no prior prints).
9. **SPY/index TIER rules** — tier=0; emit `SPY_{type}_{side}_TIER_2` for ATM SPY blocks ≥ ~$1M; promote to `SPY_call_buy_HIGH_CONVICTION` above the higher bar.
10. **Small Cap Sweep** — SWEEP on small-cap underlying.

Then run the §C scorer on every fired alert: base WR + adjustments, cap 69 if spread, bucket. Set `direction`/`sentiment` from type+side+sweep. Persist `confidence_factors[]` strings for UI tooltip parity.

**Gotchas:** greeks/iv_rank/oi_change/stickiness null in feed — don't depend on them. `tier`(0/1/2) ≠ the `_TIER_2` token in SPY rule names. Digest `top_10` is a separate rollup pipeline. Scoring is additive & server-side; thresholds above are reconstructed from `confidence_factors`, not code constants.

**Key files:** `api-data/alerts-p1.json` + `alerts-p2.json` (ground-truth alerts → regression fixtures); `api-data/alpha-flow.json` (digest shape); `assets/index-CFbq_e3t.js` (sort logic, tier map `Hv`, glossary, premium gates).
