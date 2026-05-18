# REVIEW_LOG.md

## 2026-05-17T23:59:00Z — Phase 0 baseline

### Code metrics
- server.py: 3,533 lines (target: < 3,200 — Phase A refactor still needed)
- route count: 84 handlers in server.py (target: 0 — all extracted to backend/routes/)
- App.js: 730 lines
- backend/ Python files: 28 (excluding __pycache__, .venv)
- frontend/src/ files: 7

### Data state
- ml_synthetic.py: DELETED
- test_ml_advanced.py: DELETED
- models quarantined: 12 (all .joblib files moved to models/_quarantine/)
- models live: 0
- InsufficientRealDataError: DEFINED in backend/services/ml/__init__.py
- DegenerateModelError: DEFINED in backend/services/ml/__init__.py
- Quarantine guard: ACTIVE in server.py, ml_price_prediction.py, ml_training.py

### Audit infrastructure
- qc/audit/truth_audit.sh: EXISTS and EXECUTABLE
- qc/audit/check_phase_claim.sh: EXISTS and EXECUTABLE
- .githooks/commit-msg: ACTIVE (core.hooksPath = .githooks)
- CI truth_audit step: WIRED into .github/workflows/ci.yml

### Truth audit status (at time of this log)
- server.py < 3200 lines: ❌ (3,533 — Phase A incomplete)
- calc_vex exists: ❌ (Phase B incomplete)
- calc_dex exists: ❌ (Phase B incomplete)
- calc_vega_total exists: ❌ (Phase B incomplete)
- ml_synthetic.py absent: ✅
- synthetic imports absent: ✅
- .env git-ignored: ✅
- truth_audit.sh executable: ✅

### What's next
Phase 1: Real data acquisition. Three tracks:
  1. Databento historical EOD chains ($125 credit)
  2. yfinance OHLCV (free, decades)
  3. Ingest research CSVs already on disk
