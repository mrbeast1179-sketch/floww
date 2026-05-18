# ADR-0001 — Model promotion policy

**Status:** Accepted
**Date:** 2026-05-18
**Context:** After the multi-ticker model audit ([`reports/multiticker_model_audit.md`](../../reports/multiticker_model_audit.md)) identified three compounding bugs that let bad models ship (auto-pass baseline gate, no Sharpe sanity cap, missing-baselines defaulted to auto-accept), we need an explicit policy for what gets promoted to `models/` (the active directory) vs `models/_quarantine/` (the dead-letter directory).

---

## Decision

A trained model is **promoted to `models/`** only when **all four** of the following hold for the best fold-aggregated result:

### 1. Baseline-beat (hard gate)

`model.sharpe` must strictly exceed each of:
- **majority** — train-fold majority class predicted always
- **persistence** — predict the same sign as the last realized return
- **logistic** — penalized logistic regression on the same features

Implementation: [`backend/services/ml/gate.evaluate_ship_verdict`](../../backend/services/ml/gate.py). Missing any baseline = fail-closed (`+inf` default), never auto-pass.

### 2. Sharpe sanity cap (hard gate)

`model.sharpe <= MAX_PLAUSIBLE_DAILY_SHARPE` (default **10**).

**Rationale:** Daily direction prediction on liquid ETFs almost never sustains Sharpe above ~3 out-of-sample over multi-year windows. Anything above 10 with our sample sizes is overwhelmingly an in-sample artifact, label leakage, or a metric error.

History:
- **SPY v1.0** shipped at Sharpe 31.5 / accuracy 0.90 / F1 0.88 on 167 samples × 45 features (3.7 samples per feature). [`reports/backtest_2024.md`](../../reports/backtest_2024.md) confirmed in-sample evaluation. Quarantined.

### 3. Audit-flag absence (soft gate, advisory)

[`qc/audit/truth_audit.sh`](../../qc/audit/truth_audit.sh) Rule 9 flags any live model with:
- `sharpe > 5` (suspicious for daily direction), OR
- `"baselines": {}` in its meta JSON (unverified)

Threshold of 5 is intentionally tighter than the hard-cap of 10 from gate (2). A `sharpe > 5` flag is an **investigation trigger** — quarantine pending rolling-OOS validation.

History:
- **IWM v1.0** at Sharpe 5.81 / accuracy 0.55 quarantined on `safety/quarantine-iwm-v1` pending rolling-OOS verification. Threshold 5 can be raised to 7 *with an ADR* if IWM's edge survives rolling-OOS over the most recent 250 days.

### 4. No empty `baselines` dict (hard gate)

Every promoted model's training report (`reports/training_<ticker>_<ts>.json`) must have `baselines` populated with the three baseline metrics. An empty `baselines: {}` indicates the baseline-beat gate didn't actually evaluate — fail-closed.

History:
- **TLT v1.0** shipped at Sharpe 0.00 with `baselines: {}` (the auto-pass bug). Quarantined.

---

## Consequences

**Positive.**
- Models that have not been verified against baselines cannot ship.
- Models with implausible-by-construction Sharpe values are auto-rejected.
- The promotion gate is testable: [`backend/tests/services/ml/test_gate.py`](../../backend/tests/services/ml/test_gate.py) pins each rejection path with 20 unit tests.
- The truth audit script (when running) can detect post-hoc that a bad model is live, even if the gate were ever bypassed.

**Negative.**
- The threshold of 5 in Rule 9 is conservative — it will quarantine models that may have real edge. Cost of false positive: a real model spends time in quarantine until rolling-OOS validates it.
- A model with genuine Sharpe > 10 (rare but possible — e.g. very high-frequency or special-regime strategies) needs an explicit per-deployment override via the `max_sharpe` parameter and a defending ADR.

**Reversal path.** If a quarantined model is later validated:

1. Run rolling-OOS over the most recent 250 trading days; record per-fold Sharpe spread.
2. If OOS Sharpe ≥ 3 and the per-fold distribution is reasonably tight (no fold >>2× the median), write a per-model defense ADR (`docs/adr/00NN-<ticker>-<version>-promotion.md`) documenting the spread and the regime.
3. `git mv models/_quarantine/<ticker>_* models/`.
4. The audit's Rule 9 will still flag `sharpe > 5` unless the threshold is also raised. The ADR justifies raising it.

---

## Implementation references

| Component | Path |
|---|---|
| Gate module (4 rejection paths, testable) | [`backend/services/ml/gate.py`](../../backend/services/ml/gate.py) |
| Gate unit tests (20 tests) | [`backend/tests/services/ml/test_gate.py`](../../backend/tests/services/ml/test_gate.py) |
| Training pipeline (uses gate helpers) | [`scripts/train_spy_model.py`](../../scripts/train_spy_model.py) |
| Audit script (Rule 9 enforces) | [`qc/audit/truth_audit.sh`](../../qc/audit/truth_audit.sh) |
| Quarantine directory | [`models/_quarantine/`](../../models/_quarantine/) |
| Quarantine README (cohort history) | [`models/_quarantine/README.md`](../../models/_quarantine/README.md) |
| Original audit motivation | [`reports/multiticker_model_audit.md`](../../reports/multiticker_model_audit.md) |

---

## What this ADR does NOT cover

- **Promotion to live trading.** The promotion gate above governs `_quarantine/` → `models/` (paper-trade-eligible). Promotion of a model from paper to **live** (`LIVE_TRADING_ENABLED=1` flip in `backend/paper_trading.py`) is a separate decision that requires demonstrated forward-OOS performance over a meaningful capital-exposure window. To be specified in ADR-0002.
- **Multi-task targets.** Currently the gate only evaluates `target_directional_move`. Other targets (`target_return_pct`, `target_range_expansion`, etc.) follow the same gate by convention but are not pinned by code. To be specified in ADR-0003.
- **Ensemble models.** A stacked ensemble's Sharpe is computed from its predictions, not its members'. Same gate applies.
