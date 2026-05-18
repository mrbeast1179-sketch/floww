# Quarantined Models — DO NOT LOAD

The `joblib.load` guard at 4 call sites refuses to load any path containing
`_quarantine`. These models are kept under git for forensic value only.

---

## Cohort 1 — Synthetic-data models (2026-05-17)

Trained on `np.random.normal`-generated GEX snapshots via the now-deleted
`backend/ml_synthetic.py`. Output single class at ~0.9998 confidence on
every input. Worthless.

- `best_model_*.joblib`, `price_model_*.joblib`, matching `scaler_*` and meta

**Reference:** CLAUDE_REVIEW_PROMPT.md §0.1, REVIEW_LOG.md baseline entry.

---

## Cohort 2 — v1.0 over-fit / no-edge models (2026-05-18)

Quarantined after `reports/multiticker_model_audit.md` flagged structural
issues. See that report for the full audit.

| File | Reason |
|---|---|
| `SPY_direction_v1.0.joblib` / `SPY_scaler_v1.0.joblib` / `SPY_meta_v1.0.json` | In-sample overfit: 167 samples, 45 features (3.7 samples per feature), claimed Sharpe 31.5 / accuracy 0.90. `reports/backtest_2024.md` already documented the in-sample evaluation. |
| `TLT_direction_v1.0.joblib` / `TLT_scaler_v1.0.joblib` / `TLT_meta_v1.0.json` | Sharpe 0.00 — literally no edge over baseline. Shipped due to the broken `beats_baselines` gate (every `reports/training_*.json` had `"baselines": {}` yet `"beats_baselines": true`). |
| `IWM_direction_v1.0.joblib` / `IWM_scaler_v1.0.joblib` / `IWM_meta_v1.0.json` | Sharpe 5.81 > qc/audit/truth_audit.sh Rule 9 threshold of 5. 2,799 samples / 32 features (no GEX), reasonable sample-per-feature ratio, but Sharpe 5.81 for a daily-direction model is at the upper edge of plausibility (literature typical OOS for ETF direction prediction: 0.5–3). Precision 0.66 / recall 0.47 asymmetry also suggests threshold-tuning artifact rather than genuine edge. |

**Operational impact:** `backend/paper_trading.py:daily_paper_trade_dry_run`
already handles `FileNotFoundError` from `_load_active_model` by returning
`{"action": "skip", "reason": "model_missing: ..."}`. The daily cron logs
a warning and exits cleanly. No downstream breakage.

**To restore:** Retrain on real data with a fixed baseline-beat gate (see
`reports/multiticker_model_audit.md` §2). Required gates before promotion:
- `compute_baselines()` returns non-empty dict (majority + persistence + linear)
- `beats_baselines = candidate_sharpe > max(baseline_sharpes)` computed, not hardcoded
- Sharpe ≤ 3 for daily direction prediction unless explicit justification

---

## Audit principles (from multiticker_model_audit.md §9)
- **In-sample = useless.** Train/test must never overlap.
- **Baseline-beat is the floor.** Must beat majority + persistence + logistic.
- **Sharpe > 5 daily** = suspect by default.
- **Empty baselines dict** = unverified model. SHIP gate defaults False.
- **Class balance reporting** required for every training run.

**Reference:** CLAUDE_REVIEW_PROMPT.md §0.1, REVIEW_LOG.md, reports/multiticker_model_audit.md
