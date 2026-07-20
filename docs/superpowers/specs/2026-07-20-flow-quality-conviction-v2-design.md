# Conviction v2 — quality-over-quantity layer for the institutional alert engine

_2026-07-20 · design for `backend/services/flow_quality.py` + integration into
`flow_alerts.eval_institutional`. Grounded in: FlowAlgo/UnusualWhales product
research, TradeAlgo UOA filtering methodology, Cremers-Weinbaum (JFQA 2010),
Benjamini-Hochberg (1995). Nav directive: "quality over quantity, PhD-grade."_

## Problem

The v1 engine (210f0d0) fires on single-print evidence. Product research says
the majority of raw UOA flags are noise: ~35% of options volume is multi-leg
(spread legs masquerade as directional whales), 30-40% of flagged activity is
hedging/non-directional. Without trade prints we cannot see sweeps or at-ask
aggression — but four print-less quality levers exist.

## Design (four pure functions + factor rewiring)

### 1. Spread-leg detection — `detect_spreads(rows)`
The #1 noise killer. Within ONE scan snapshot, flag likely strategy legs:
- **Vertical**: same under+exp+type, different strikes, both vol ≥ 1000,
  volume ratio in [0.7, 1.43] (matching sizes ≈ paired legs).
- **Straddle/strangle**: same under+exp, opposite types, strikes within 5% of
  each other, matching volume by the same ratio test.
Marks `spread_leg=True` on both legs. Alerts on spread legs: side becomes
`STRATEGY`, bias `None`, tier capped at BRONZE. A desk never sells a vertical
leg as a directional whale.

### 2. Cremers-Weinbaum IV spread — `cw_iv_spread(rows)`
Per ticker: volume-weighted mean of (call IV − put IV) across strike-matched
call/put pairs of the same expiry. Positive spread = call demand richening =
bullish informed pressure (JFQA 2010: predicts returns at weekly horizon).
This is the print-less substitute for at-ask aggression. Feature stored per
alert (`cw_spread`); a tier factor when it CONFIRMS the alert's bias
(cw ≥ +0.015 for BULLISH, ≤ −0.015 for BEARISH).

### 3. Cluster confirmation — `cluster_biases(rows, min_n=3)`
≥3 distinct qualifying contracts (score ≥ 70), same ticker, same bias, in one
snapshot = laddered accumulation (strikes/expiries), the classic
institutional footprint. Tier factor `cluster`.

### 4. FDR-controlled σ alerts — `bh_fdr(pvals, q=0.10)`
SIGMA currently fires at raw σ ≥ 4 across ~300 tickers/day — a
multiple-testing machine. Convert each ticker's σ to a one-sided normal
p-value and keep only Benjamini-Hochberg survivors at q=0.10 (with σ ≥ 3
floor). Fewer, defensible σ alerts.

### Conviction stack ("prime bracket")
New factor `prime`: premium ≥ $250k AND vol/OI ≥ 5 — the empirically
measured 55-62% directional bracket from product research. Factors now:
{oiconf, sigma(FDR-surviving), score90, whale, informed_band,
regime_confluent, cw_confirm, cluster, prime} → GOLD ≥ 3, SILVER 2, BRONZE 1,
spread-leg capped BRONZE.

### Measurement — `GET /api/flowseeker/alerts/quality`
Per rule × tier: n, hit-rate (move_pct sign matches bias, |move| ≥ 0.5%),
avg move. Reads the persisted feed — the calibration loop that makes tiers
empirical instead of aspirational. No new data required.

## Non-goals (this iteration)
True sweep/block/split classification and at-ask aggression (need OPRA-grade
prints), dark-pool correlation (no feed), IV-percentile context (needs IV
history depth — natural follow-up once flow_scan_daily carries IV), earnings
calendar alignment (steal-list #13's lane).

## Testing
TDD: `backend/tests/services/test_flow_quality.py` — spread pairing (vertical,
straddle, non-matching sizes, sub-floor volumes), CW spread (sign, weighting,
no-pairs), clusters, BH-FDR (all-null, one-strong, boundary), prime bracket,
tier capping via eval_institutional integration, quality endpoint math.
