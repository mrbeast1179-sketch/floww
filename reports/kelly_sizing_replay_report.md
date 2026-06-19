# Kelly Sizing Replay Report

Linear-scaling replay sourced from `0.0200`-of-equity baseline (the current paper_trading.py default). Each record's realised `total_pnl` is uniformly scaled by `policy_pct / baseline_pct`.

**Caveat**: this replay is a *first-order* approximation. The source JSON provides aggregates only — it lacks trade-by-trade sequencing, so compounding dynamics from a Kelly-sized equity curve are NOT modelled. Use this section as a sizing-policy comparison, not a walk-forward simulation.

## Per-Policy Aggregate

| Policy | % of equity | Total P&L | Mean Final Equity | Win count | Sharpe-proxy | MDD proxy |
|---|---:|---:|---:|---:|---:|---:|
| naive 2% (baseline) | 0.0200 | $-235.63 | $9,988.78 | 9/21 | -0.0174 | $2,619.30 |
| naive 1% (signal_translator default) | 0.0100 | $-117.83 | $9,994.39 | 9/21 | -0.0174 | $1,309.65 |
| quarter-Kelly @ p=0.55, b=1.65 | 0.0693 | $-816.75 | $9,961.11 | 9/21 | -0.0174 | $9,078.25 |
| half-Kelly @ p=0.55, b=1.65 | 0.1386 | $-1,633.45 | $9,922.22 | 9/21 | -0.0174 | $18,156.51 |
| empirical quarter-Kelly (per-record) | 0.0000 | $+35,551.57 | $11,692.93 | 9/21 | +0.5336 | $11,933.59 |
| empirical half-Kelly (per-record) | 0.0000 | $+71,103.17 | $13,385.87 | 9/21 | +0.5336 | $23,867.16 |

## Kelly No-Trade Filter

The empirical Kelly filter skipped **11 of 21** records (records where empirical win-rate < breakeven `1/(avg_rr+1)`). For those records, replayed P&L is **$0.00** under empirical half/quarter-Kelly — those strategies would NOT have been traded at all under Kelly-aware discipline. The raw naive-2% loss for those strategies was **$-5,414.81** — capital the empirical Kelly filter prevented from being risked.

Filtered records:

| Symbol | Strategy | Win-rate | Avg R:R | Naive P&L |
|---|---|---:|---:|---:|
| GS | DVT_Pullback_Cloud | 0.1111 | +1.6456 | $-1,154.81 |
| MS | DVT_Pullback_Cloud | 0.2000 | +1.6339 | $-470.48 |
| MS | DVT_Momentum | 0.2500 | +1.7332 | $-544.13 |
| XLI | DVT_Pullback_Cloud | 0.3333 | +1.5758 | $-83.23 |
| BAC | DVT_Pullback_Cloud | 0.3333 | +1.6063 | $-89.81 |
| JPM | DVT_Momentum | 0.0000 | +1.6456 | $-947.32 |
| LRCX | DVT_Momentum | 0.3333 | +1.6929 | $-101.55 |
| INTC | DVT_Momentum | 0.0000 | +1.7357 | $-773.41 |
| TGT | DVT_Momentum | 0.2000 | +1.7647 | $-415.15 |
| QQQ | DVT_Pullback_Cloud | 0.2500 | +1.6667 | $-255.58 |
| IWM | DVT_Pullback_Cloud | 0.0000 | +1.6034 | $-579.34 |

## Capital Risked Proxy

Total dollar exposure across all 21 records under each policy (sum of trades × $10000 equity × policy fraction).

| Policy | Dollars risked |
|---|---:|
| naive 2% (baseline) | $21,800.00 |
| naive 1% (signal_translator default) | $10,900.00 |
| quarter-Kelly @ p=0.55, b=1.65 | $75,537.00 |
| half-Kelly @ p=0.55, b=1.65 | $151,074.00 |
| empirical quarter-Kelly (per-record) | $0.00 |
| empirical half-Kelly (per-record) | $0.00 |

## Per-Record Replay (empirical half-Kelly)

All 21 records with empirical full-Kelly computed from THIS record's win-rate and avg-rr. Records with `empirical_filtered=true` would NOT have been traded at all under Kelly-aware discipline (replayed P&L = $0).

| Symbol | Strategy | WR | R:R | Naive P&L | Emp. f* | Emp. half | Emp. quarter |
|---|---|---:|---:|---:|---:|---:|---:|
| AMAT | DVT_Momentum | 0.667 | 1.755 | $+1,464.49 | 0.4768 | $+17,454.94 | $+8,727.47 |
| SCHD | DVT_Cross_Support | 1.000 | 1.543 | $+952.79 | 1.0000 | $+23,819.75 | $+11,909.88 |
| CVS | DVT_Momentum | 0.667 | 1.680 | $+922.13 | 0.4683 | $+10,795.85 | $+5,397.92 |
| CVS | DVT_Pullback_Cloud | 0.667 | 1.687 | $+483.29 | 0.4690 | $+5,666.97 | $+2,833.48 |
| MU | DVT_Momentum | 0.667 | 1.649 | $+472.48 | 0.4645 | $+5,486.26 | $+2,743.13 |
| KLAC | DVT_Pullback_Cloud | 0.667 | 1.634 | $+469.58 | 0.4627 | $+5,431.86 | $+2,715.93 |
| TXN | DVT_Momentum | 0.500 | 1.763 | $+451.40 | 0.2163 | $+2,441.39 | $+1,220.69 |
| JPM | DVT_Pullback_Cloud | 0.400 | 1.679 | $+48.75 | 0.0426 | $+51.88 | $+25.94 |
| KLAC | DVT_Momentum | 0.375 | 1.717 | $+6.14 | 0.0110 | $+1.68 | $+0.84 |
| XLI | DVT_Pullback_Cloud | 0.333 | 1.576 | $-83.23 | 0.0000 | $+0.00 | $+0.00 |
| BAC | DVT_Pullback_Cloud | 0.333 | 1.606 | $-89.81 | 0.0000 | $+0.00 | $+0.00 |
| GS | DVT_Momentum | 0.375 | 1.764 | $-91.87 | 0.0206 | $-47.41 | $-23.71 |
| LRCX | DVT_Momentum | 0.333 | 1.693 | $-101.55 | 0.0000 | $+0.00 | $+0.00 |
| QQQ | DVT_Pullback_Cloud | 0.250 | 1.667 | $-255.58 | 0.0000 | $+0.00 | $+0.00 |
| TGT | DVT_Momentum | 0.200 | 1.765 | $-415.15 | 0.0000 | $+0.00 | $+0.00 |

*(Showing top 15 of 21 records sorted by naive P&L descending.)*
