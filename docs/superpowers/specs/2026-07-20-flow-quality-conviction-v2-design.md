# Conviction v2 — quality-over-quantity layer for the institutional alert engine

## Status

Two parallel axes — the Conviction v2 quality layer (v2.0→v2.5.1) and the backend
hardening wave (a6fffe8→f41351e) that ships independently. Listed in two named
tables so a skim reader does not infer supersession across axes.

### Conviction v2 quality layer

| Wave | Landed | Note |
|------|--------|------|
| v2.0 — four-lever engine + prime bracket + tier system + measurement endpoint | `9db3ba4` | initial design |
| v2.1 — cluster wiring | `546fc52` | |
| v2.2 — quality-trend sparkline math (7/14/30 windows, Wilson lower bound) | `546fc52` | |
| v2.3 — Wilson 95% confidence interval helpers (statistical-honesty layer) | `546fc52` | |
| v2.4 — bestRuleForTier (decision-rule ranking with `BEST_RULE_MIN_N=3` floor) | `546fc52` | **closed 2026-07-21** |
| v2.4.1 — "single-hit fringe vs thin high-rate rival" coverage pin | (this commit) | **closed 2026-07-21** |
| v2.5 — daily sparkline for per-tier trending | `f20c416` | |
| v2.5.1 — null-aware coercion helper cleanup | `f89a010` | |

### Backend hardening wave (parallel axis)

| Wave | Landed | Note |
|------|--------|------|
| v2.2 desk-pass — fresh-interest / campaign / IV gates | `a6fffe8` | |
| v2.2-wire — desk_pass() integrated into `_run_institutional_alerts` | `642d225` | |
| v2.2-wire-failopen — 3 wire-up pin tests | `f41351e` | |

Source of truth for v2.4 bestRuleForTier remains the code in
`frontend/src/components/flowseeker/convictionUi.js` and tests in
`convictionUi.test.js` as captured in `546fc52`. This is a docs-only commit
(no functional change). Close-out happens in a separately-named doc commit; this
spec just records status.

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


---

## Addendum: v2.4 bestRuleForTier (close-out detail)

**Landed**: `546fc52 feat(flowseeker): Conviction v2.1 cluster wiring + v2.2/v2.3/v2.4 close-out`
**Formal close-out**: 2026-07-21 (`docs(flowseeker): close out Conviction v2.4 bestRuleForTier`)
**Tested at close-out**: `frontend/src/components/flowseeker/convictionUi.test.js` — `describe("bestRuleForTier (v2.4 extension)")` block, full convictionUi suite (`CI yarn test convictionUi`) **60/60 green**.

### What it does

`bestRuleForTier(tier, byRuleAndTier)` ranks all qualifying candidate rules for a given tier
and returns the single highest-signal rule. Ranking is **sample-size-weighted hit count**
rather than raw hit rate, so `n=10, hits=8` (80% on 10 obs) ranks below `n=30, hits=24`
(80% on 30 obs) — the larger sample carries less noise. Tie-break: `n_measured DESC, hit_rate DESC`.

The `BEST_RULE_MIN_N = 3` floor enforces that no tier renders a "best rule" chip unless that rule
has been measured ≥ 3 times against its tier. Below the floor the function returns `null` and
the chip is hidden.

### Files

- `frontend/src/components/flowseeker/convictionUi.js` — `bestRuleForTier()` export + `BEST_RULE_MIN_N = 3` constant
- `frontend/src/components/flowseeker/convictionUi.test.js` — `describe("bestRuleForTier (v2.4 extension)")` covering null/guard, ranking, tier-keyed filtering, and `BEST_RULE_MIN_N` floor enforcement

### Layered-on work

v2.4 is in the middle of the Conviction stack — does not supersede itself, but subsequent
waves built ON TOP of it:

- v2.5 daily sparkline (`f20c416`) — per-tier fade-signal via `dailySeriesForTier` + Wilson CIs
- v2.5.1 cleanup (`f89a010`) — `_toNum` null-aware coercion helper
- v2.2 desk-pass (`a6fffe8`) + v2.2-wire (`642d225`) + v2.2-wire-failopen (`f41351e`) — backend hardening; v2.4 frontend layer sits on top of the resulting feed

### v2.4.1 Coverage-pin test

Closed 2026-07-21 (this commit). The "single-hit fringe candidate loses to thin
high-rate rival" test pins the floor edge case the prior v2.4 close-out left uncovered:

- **Fringe** sits exactly at `BEST_RULE_MIN_N = 3` with `hits = 1` — the WEAKEST
  possible qualifying entry. Without this pin, a future regression mis-ranking
  the weighted-hits key could silently flip a result at the floor boundary.
- **Rival** has `hits = 10`, `n_measured = 10` — "thin + high-rate" (100% record
  at small n). Wins decisively on weighted-hits ranking (10 > 1).
- **Test contract**: fringe qualifies (`n_measured > 0` holds), floor holds
  (`n_measured >= 3`), and a higher-weighted-hits rival wins. `hit_rate` is
  recomputed and reads ~1.0 (10/10).

This test does NOT strictly pin the ranking metric — under a hypothetical
`hit_rate`-DESC re-ranking the rival still wins because its 100% rate beats the
fringe's ~33%. The ranking-metric regression coverage is provided implicitly by
the 7 existing tests in the `describe("bestRuleForTier (v2.4 extension)")` block.

### Calibration notes

`BEST_RULE_MIN_N = 3` was chosen empirically. At `n=2`, a single hit/miss swings the rate
50pp with zero statistical confidence; at `n=3` the rate has meaningful variance and the
chip surfaces only stable signals. Raising the floor to `n=5` would tighten signal quality
at the cost of hiding legitimate early-cycle best-rules.
