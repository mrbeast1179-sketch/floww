# Multi-Ticker Model Methodology Audit — v1.0 cohort

**Verdict (TL;DR):** SHIP-gate broken; **SPY and TLT must be quarantined**, QQQ/IWM/DIA require an out-of-sample re-evaluation before any paper-trade promotion to live.

| Ticker | n | features | Acc | F1 | Sharpe | Reported verdict | **Audit verdict** | Reason |
|---|---:|---:|---:|---:|---:|---|---|---|
| SPY | 167 | 45 (GEX-heavy) | 0.900 | 0.880 | **31.5** | SHIP | **QUARANTINE** | 3.7 samples per feature; in-sample fit confirmed by `reports/backtest_2024.md` (`"Headline metrics are therefore IN-SAMPLE"`) |
| QQQ | 2,799 | 32 (no GEX) | 0.531 | 0.573 | 2.87 | SHIP | KEEP — needs OOS | Sharpe and accuracy plausible; not yet validated on truly held-out 2025+ data |
| IWM | 2,799 | 32 (no GEX) | 0.550 | 0.484 | 5.81 | SHIP | INVESTIGATE | Sharpe high enough to be suspicious; recall 0.47 vs precision 0.66 suggests imbalanced threshold; needs OOS |
| DIA | 2,799 | 32 (no GEX) | 0.531 | 0.550 | 2.14 | SHIP | KEEP — needs OOS | Plausible; same OOS gap as QQQ |
| TLT | 2,799 | 32 (no GEX) | 0.519 | 0.481 | **0.00** | SHIP | **QUARANTINE** | Sharpe = 0 means literally no edge over baseline; should never have shipped |

---

## 1. The two distinct cohorts on disk

There are two model families currently in `models/`, trained with different methodologies:

**Cohort A — GEX-feature SPY model** (`models/SPY_direction_v1.0.joblib`):
- 167 labeled samples (the `gex_llm_patterns_outcomes` collection — the academic CSV from `iAmGiG_gex-llm-patterns`).
- 45 features including `net_gex`, `gex_concentration`, `net_gex_zscore_60d`, `net_gex_roc_*`, `dist_to_flip`, etc.
- LightGBM, walk-forward CV (6 folds reported).
- Sharpe 31.5 — *deeply* implausible for daily direction prediction.

**Cohort B — Price/vol-only models** (QQQ/IWM/DIA/TLT v1.0):
- 2,799 samples each (from yfinance daily OHLCV, 2015-03-31 → 2026-05-15).
- 32 features: returns multi-horizon, SMAs, ATR, realized vol, RSI, MACD, Bollinger Bands. **No GEX features.**
- LightGBM, walk-forward CV (8 folds reported).
- Sharpes 0.00 / 2.14 / 2.87 / 5.81 — three plausible, one zero-edge.

The difference comes from data availability: GEX features only exist where someone (the iAmGiG academic dataset) labeled them, which currently bounds the labeled set to 167 rows. The price/vol cohort uses yfinance, which goes back a decade.

## 2. The structural bug: `beats_baselines` is unconditionally `true`

Every `reports/training_*.json` artifact has:

```json
"baselines": {},
"beats_baselines": true
```

An empty `baselines` dict means no baseline was actually computed and compared. Yet `beats_baselines` is reported `true`. This means the SHIP gate is broken — it admits anything, including TLT's Sharpe-0 model.

**Required fix in the training pipeline** (`scripts/train_spy_model.py` or its multi-ticker successor):

1. Compute baselines explicitly per fold:
   - `baseline_majority`: predict the train-fold majority class always
   - `baseline_persistence`: predict the same sign as the prior bar's realized return
   - `baseline_linear`: penalized logistic regression on the same features
2. Compute each baseline's Sharpe on the test fold under the same simulated strategy.
3. `beats_baselines = candidate_sharpe > max(baseline_sharpes)`. If any baseline is missing, default `beats_baselines = False`, not True.

Until this is fixed, **no model should be promoted to active**.

## 3. The SPY-specific finding

`reports/backtest_2024.md` already contains the smoking gun:

> "CAVEAT: the shipped artifact was trained on 167 rows (per `SPY_meta_v1.0.json`); the 2024 evaluation set has 167 rows that overlap with that training window. **Headline metrics are therefore IN-SAMPLE on the deployed pickle.**"

The monthly table shows precision/recall/F1/accuracy all at exactly 1.000 across every month — the textbook signature of in-sample evaluation on a memorized training set.

The 45-feature design also fails the basic rule-of-thumb: with 167 samples you cannot reliably fit 45 parameters. **SPY v1.0 must be quarantined.** The path forward is one of:

- (a) Reduce features to ≤ 15 (e.g. drop redundant rolling-vol variants, drop multiple-horizon return columns that correlate with each other), retrain on the same 167 rows, accept the smaller model.
- (b) Expand the labeled dataset using the recent Databento backfill — compute GEX/VEX/DEX from the SPY 252-day chain data already on disk + Mongo, label by next-day return, get ~200+ additional rows.
- (c) Both, then retrain v2.0 with proper train/test/holdout splits (60/20/20 time-ordered) and a real baseline-beat gate.

## 4. The TLT-specific finding

TLT's Sharpe is **literally 0.00**. Accuracy 51.9% with class-balance 51.1% means the model is one percentage point above random guessing. The model has no edge yet was promoted to SHIP because the broken baseline-gate accepted it. Quarantine.

## 5. The IWM-specific finding

IWM's Sharpe 5.81 is unusually high for daily-direction prediction of a noisy small-cap index. Two diagnostic checks before trusting it:

- Recompute IWM's Sharpe on the **most recent 250 trading days only** (rolling OOS). If it collapses, the headline Sharpe is fold-aggregation noise.
- Inspect the precision/recall asymmetry: precision 0.66 vs recall 0.47 means the model is conservatively biased — it predicts "up" rarely but is correct often. That can be real, or it can be an artifact of the threshold choice. Re-evaluate at threshold 0.50.

## 6. The QQQ and DIA findings

Both have plausible OOS-looking metrics (53% accuracy, Sharpe 2-3) on a 2,799-row dataset spanning 11+ years. The walk-forward CV with 8 folds is methodologically sound *if* the splits respect time order and don't leak target into features.

Diagnostic to run before live promotion (not now — paper-trade dry-run is fine):

- Compute the per-fold Sharpe distribution. If the overall Sharpe of ~2.5 is composed of one fold at 8 and seven folds near 0, the model is unstable; if it's broadly ~2-3 across folds, it's real.
- Verify the labeling code: is `target_directional_move` for day `t` computed from `close(t+1) - close(t)`, with `close(t+1)` strictly absent from the feature row? Confirm in `backend/services/ml/targets.py`.

## 7. Implications for paper-trade dry-run (already wired on main)

`backend/paper_trading.py:410 daily_paper_trade_dry_run(ticker="SPY")` is registered as a cron at 09:35 ET weekdays. Per `LIVE_TRADING_ENABLED` defaulting off, no real orders are placed — only logged to `orders_dry_run`. That's safe.

The risk surface is when someone flips `LIVE_TRADING_ENABLED=1`. **Do not flip it for SPY until SPY v2.0 lands and survives a true OOS test.** Do not flip it for any ticker until the broken baseline-gate is fixed.

A defensible interim: promote QQQ or DIA to live first (the two most plausible models), but with the absolute smallest possible capital ($100-$500 of the $5K account), and only after a 30-day live dry-run with logged predictions + realized outcomes shows the same Sharpe holds up.

## 8. Recommended actions

In priority order:

1. **Quarantine SPY v1.0 and TLT v1.0** — `git mv models/SPY_direction_v1.0.joblib models/_quarantine/`, ditto scaler, meta. The `joblib.load` guard already in place at 4 sites will refuse to load them. (Recommend doing this in a follow-up PR rather than this one — it has downstream impact on the daily cron, which Nav should approve.)
2. **Fix the SHIP-gate bug** in the training pipeline so `beats_baselines` is computed against real baselines and defaults False on missing data.
3. **Re-evaluate QQQ/IWM/DIA on rolling-OOS** (last 250 trading days only); record per-fold Sharpe spread.
4. **Retrain SPY v2.0** using the Databento-backfilled 252-day 2024 dataset (the data is already on disk) — compute GEX features from chains, label by realized 1-day return, build a 400+ row dataset with proper 60/20/20 time-ordered splits.
5. **Add an audit-test step** to the truth-audit script: any model in `models/` whose meta JSON has `sharpe > 5` or `"baselines": {}` is flagged red.

## 9. Methodology principles re-stated

(These are not new but bear repeating after this audit.)

- **In-sample = useless.** Train on `[t_start, t_train_end]`, test on `[t_train_end + embargo, t_test_end]`. Never the same span.
- **Baseline-beat is the floor.** A model that doesn't beat majority + persistence + penalized-linear on the test fold is not shipping. Period.
- **Sharpe > 5 daily** = suspect by default. Cap the SHIP threshold at Sharpe 3 unless there's an explicit defensible reason.
- **Empty baselines dict** = unverified model. SHIP gate must default False on missing baselines.
- **Class balance reporting** — every training run should report majority-class accuracy alongside model accuracy. A 51%-positive-rate dataset where the model gets 52% accuracy is essentially baseline.

---

*Audited: 2026-05-18 UTC. Audit produced by methodology review of `models/*_meta_v1.0.json` + `reports/training_*.json` + `reports/backtest_2024.md`. No code changes in this PR — actions above are recommendations for follow-up PRs.*
