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

## Cohort 3 — IWM under audit (held, not yet moved)

`IWM_direction_v1.0.joblib` has Sharpe 5.81 — suspicious but not auto-quarantined.
Awaiting rolling-OOS re-evaluation per `reports/multiticker_model_audit.md` §5.
If OOS Sharpe < 1.0, IWM joins cohort 2.
