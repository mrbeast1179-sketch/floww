# Conftest.py Waiver Triage (DS Pro)

Pre-existing pytest collection errors blocking ~22 test files.
Root-cause analysis to inform Round 10's "freeze waiver" decision.

## Errors by root cause

### Root cause 1: services-not-package + conftest.py import order
- Count: ~20 files
- Symptom: `ModuleNotFoundError: No module named 'services.xxx'; 'services' is not a package`
- Root cause: `backend/tests/conftest.py` does `from server import app` at import time, before pytest's pythonpath mechanism adds `backend/` to sys.path. This causes `services` to be resolved as a non-package.
- Fix: Modify conftest.py to defer `from server import app` until pytest pythonpath is loaded (e.g., move into a fixture or use conftest import hook)
- Estimated R10 effort: 30 min
- Blast radius: unblocks ~17-20 test files
- **Recommendation: waive freeze and apply in R10**

### Root cause 2: scipy.__version__ missing
- Count: 1 file (`test_train_spy_v2.py`)
- Symptom: `AttributeError: module 'scipy' has no attribute '__version__'`
- Root cause: Pinned scipy version in venv doesn't expose `__version__` attribute
- Fix: `pip install scipy>=1.11` or update pyproject.toml dependency
- Estimated R10 effort: 5 min
- **Recommendation: apply in R10**

## Per-file inventory

| File | Root Cause | R10 Fix |
|------|-----------|---------|
| tests/services/test_gex_history.py | conftest order | waive freeze |
| tests/services/test_greek_aggregator.py | conftest order | waive freeze |
| tests/services/test_iv_skew_analyzer.py | conftest order | waive freeze |
| tests/services/test_live_trading_switch.py | conftest order | waive freeze |
| tests/services/test_ml_ensemble.py | conftest order | waive freeze |
| tests/services/test_oi_change_detector.py | conftest order | waive freeze |
| tests/services/test_paper_broker.py | conftest order | waive freeze |
| tests/services/test_paper_trader.py | conftest order | waive freeze |
| tests/services/test_position_sizing.py | conftest order | waive freeze |
| tests/services/test_replay_engine.py | conftest order | waive freeze |
| tests/services/test_request_deduplicator.py | conftest order | waive freeze |
| tests/services/test_retail_flow_graph.py | conftest order | waive freeze |
| tests/services/test_retail_flow_score.py | conftest order | waive freeze |
| tests/services/test_retail_flow_signal.py | conftest order | waive freeze |
| tests/services/test_scheduler.py | conftest order | waive freeze |
| tests/services/test_semantic_search.py | conftest order | waive freeze |
| tests/services/test_semantic_search_retail_flow.py | conftest order | waive freeze |
| tests/services/test_trading_signals.py | conftest order | waive freeze |
| tests/services/test_yfinance_fetcher.py | conftest order | waive freeze |
| tests/services/test_yoptions_fetcher.py | conftest order | waive freeze |
| tests/test_pipeline_integration.py | conftest order | waive freeze |
| tests/test_train_spy_v2.py | scipy version | pip bump |
| tests/services/test_toxicity_ensemble_contract.py | conftest order | waive freeze |
