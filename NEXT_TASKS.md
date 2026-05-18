# NEXT_TASKS.md — Hermes work queue

> **Read order on every session start:**
> 1. `CLAUDE_REVIEW_PROMPT.md` (architectural contract — read §0 and current phase)
> 2. `REVIEW_LOG.md` (last 5 entries)
> 3. This file (queue)
>
> **Loop:** pick the first non-blocked task → run it → write proof in `REVIEW_LOG.md` → check it off → append ≥ 3 new tasks here before stopping.
> **If a task is impossible:** add a row to `BLOCKERS.md` with the symptom and curl/traceback, move on.
> **Forbidden:** vague tasks ("improve ML"). Every task has an exact `Run:` command and `Proof:` command.

---

## Active phase: 1 — Real data acquisition (in progress)

### Prerequisites (all verified ✅)
- ml_synthetic.py: DELETED
- test_ml_advanced.py: DELETED
- 12 models quarantined in models/_quarantine/
- InsufficientRealDataError + DegenerateModelError: DEFINED in backend/services/ml/__init__.py
- Quarantine guard on joblib.load: ACTIVE in 3 files
- truth_audit.sh: EXECUTABLE, wired into CI
- check_phase_claim.sh: EXECUTABLE, commit-msg hook active
- REVIEW_LOG.md: baseline written

### Phase 1 data status
- backfill_databento.py: EXISTS, dry-run tested
- ingest_research_csvs.py: EXISTS, all 7 sources ingested (45K+ docs in MongoDB)
- backfill_yfinance.py: NOT YET CREATED ← current task

---

## On-deck (execute in order)

- [ ] **phase1-3**: yfinance backfill of underlying bars
  - **Run:** create `scripts/backfill_yfinance.py`. Fetches decades of daily OHLCV for SPY,QQQ,IWM,DIA,VIX,VIX9D,DXY,TLT. Writes to MongoDB `underlying_bars` collection. Idempotent: upsert on (ticker, date).
  - **Proof:** mongo `underlying_bars` count ≥ 10000

- [ ] **phase1-4**: enable real Databento backfill (BLOCKED — needs Nav approval)
  - **Run:** with Nav's explicit OK in-session, `python scripts/backfill_databento.py --tickers SPY,QQQ --start 2024-01-01 --end 2024-12-31`
  - **Proof:** mongo `databento_eod_chains` count ≥ 250

- [ ] **phase2-1**: write `backend/services/ml/quality.py` with all degeneracy gates
  - **Run:** implement per `CLAUDE_REVIEW_PROMPT.md` §Phase 2. Gates: class balance, feature variance, prediction distribution std, no future leakage, holdout untouched. Add `backend/tests/services/ml/test_quality.py` with positive + negative tests.
  - **Proof:** `pytest backend/tests/services/ml/test_quality.py -v` passes

- [ ] **phase3-1**: canonical Black-Scholes tests
  - **Run:** port Hull 10e examples into `backend/tests/test_bs_greeks_canonical.py`. Rel-err < 1e-6.
  - **Proof:** `pytest backend/tests/test_bs_greeks_canonical.py -v` passes

- [ ] **phase2-2**: implement calc_vex, calc_dex, calc_vega_total
  - **Run:** add to `backend/advanced_analytics.py`. Unit tests against FlashAlpha sample_chain.csv and BS reference vectors.
  - **Proof:** `grep -rn "def calc_vex\|def calc_dex\|def calc_vega_total" backend/advanced_analytics.py` returns results

- [ ] **phase4-1**: feature engineering on real data
  - **Run:** create `backend/services/ml/features.py`. ~50 features from real Mongo collections. No-leakage guarantee. Lands in `ml_features` collection.
  - **Proof:** `ml_features` collection populated for SPY across 2024, manifest shows variance > 1e-6 on every feature

- [ ] **phase5-1**: retrain SPY direction model on real GEX data
  - **Run:** retrain on `gex_enhanced_snapshots` + `gex_llm_patterns_outcomes` (243 days, labeled). Walk-forward CV. Must beat 3 baselines.
  - **Proof:** model saved to `models/` (not `_quarantine/`), training log shows precision/recall/F1

---

## Blocked

- **phase1-4** (real Databento backfill): Needs Nav approval — costs real money from $125 credit

---

## Done (archived)

### Phase 0 — Truth audit & synthetic-data demolition (completed 2026-05-17)
- [x] **phase0-1**: truth_audit.sh created, executable, wired into CI
- [x] **phase0-2**: ml_synthetic.py + test_ml_advanced.py deleted, InsufficientRealDataError added
- [x] **phase0-3**: 12 models quarantined in models/_quarantine/
- [x] **phase0-4**: quarantine guard on joblib.load in 3 files
- [x] **phase0-5**: truth_audit wired into CI
- [x] **phase0-6**: commit-msg hook for Phase claim honesty
- [x] **phase0-7**: REVIEW_LOG.md baseline written

### Phase 1 — Data acquisition (partial)
- [x] **phase1-1**: scripts/backfill_databento.py created, dry-run tested
- [x] **phase1-2**: scripts/ingest_research_csvs.py created, all 7 sources ingested (45K+ docs)
