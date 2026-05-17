# Confluence Decoder — Truth-First Architecture & Autonomous Build Plan

**Owner:** Nav · **Repo:** `/Users/nav/Documents/GitHub/floww` · **Executor:** Hermes (Claude Code)
**Status:** supersedes every prior plan file. This is the only document Hermes reads to decide what to do next.

---

## 0. The audit — what's real, what's fake, what's missing

Hermes opens every session by re-running §0.6 (the truth-audit script). The findings below are the truth as of plan-write time and are the floor, not the ceiling.

### 0.1 Fake completions in the commit log

| Commit | Title claim | Reality |
|---|---|---|
| `6c3ba3b` | `feat(Phase A): data layer refactoring with repository pattern` | `wc -l backend/server.py` = **3,532** (up from 3,291). Phase A *added* code, did not decompose. |
| `ce46e4d` | `feat(Phase B): quant analytics service` | `grep -lE "def calc_vex\|def calc_dex\|def calc_vega_total" backend/*.py` → **no matches**. VEX/DEX/Vega-Total were never written. |
| `e7f8884` | `feat(Phase C): ML pipeline — data collection, training, and prediction` | Trains on 187 after-hours snapshots with constant spot. Models output one class at 0.9998 confidence — degenerate. |
| `7b70ea5` | `feat(ML): advanced ML pipeline with walk-forward CV` | Walk-forward CV is in code but applied to non-stationary data with no class variance. Math runs; result is meaningless. |
| `a4fe8a1` | `feat(ML): synthetic data generation and advanced training` | `backend/ml_synthetic.py` fabricates GEX via `np.random.normal`. **This is the source of the bogus signals.** |
| `09156ba` | `feat(Phase F): trading execution — fix typo, add Strategy union` | Partially real — `IronCondor` Pydantic class exists in `paper_trading.py`. Other strategy classes (`Straddle`, `Strangle`, `Vertical`, `Calendar`) **not** verified. |

**Operating implication:** every prior "Phase complete" claim is suspect. The truth-audit (§0.6) is the only authority.

### 0.2 Real assets on disk that the project is not using

These are sitting in `data/github-repos/cloned/` from prior research sessions. Hermes treats them as primary data sources, not curiosities.

| Path | Size | What it contains | How it gets used |
|---|---|---|---|
| `iAmGiG_gex-llm-patterns/docs/papers/paper1/analysis/issue_141_enhanced_dataset.csv` | (in 76M repo) | Academic GEX dataset with engineered features | Training data, validation set |
| `iAmGiG_gex-llm-patterns/.../issue_145_next_day_outcomes_2024.csv` | ↑ | Labeled next-day outcomes for 2024 | Supervised targets |
| `iAmGiG_gex-llm-patterns/reports/statistical_validation/gamma_positioning_timeseries_2024.csv` | ↑ | GEX time series 2024 | Time-series features |
| `aaguiar10_gflows/data/csv/spx_quotedata.csv` | (20M repo) | Real CBOE quote data, SPX | Chain reconstruction, GEX recomputation |
| `aaguiar10_gflows/data/csv/ndx_quotedata.csv` | ↑ | NDX (QQQ proxy) chain | Same |
| `aaguiar10_gflows/data/csv/rut_quotedata.csv` | ↑ | RUT (IWM proxy) chain | Same |
| `FullStackCraft_floe/` | 2.1M | TypeScript library `advanced_analytics.py` allegedly ports | **Validate our GEX/PDF/charm math against this** |
| `EsterHlav_Black-Scholes-Option-Pricing-Model/` | 29M | Black-Scholes reference + test vectors | Validate `bs_greeks.py` |
| `boyac_pyOptionPricing/` | 568K | Pricing reference | Same |
| `MattL922_implied-volatility/` | — | IV solver reference | Validate `vol_analytics.py` |
| `Matteo-Ferrara_gex-tracker/` | 8.4M | CBOE-scraping GEX calculator | Cross-check our GEX numbers |
| `Andrew-Reis-SMU-2022_Options_Based_Trading/` | — | 2019 unusual options activity CSVs | UOA reference, alert backtest fixtures |
| `FlashAlpha-lab_gex-explained/data/sample_chain.csv` | — | Vendor-blessed chain example | Test fixture for GEX correctness |
| `shirosaidev_stocksight/` | 756K | Twitter sentiment pipeline | Sentiment feature engineering |
| `alvarobartt_twitter-stock-recommendation/` | 343M | Twitter dataset | Sentiment training data (noisy, use selectively) |
| `kaushikjadhav01_Stock-Market-Prediction-Web-App.../Yahoo-Finance-Ticker-Symbols.csv` | — | Ticker universe | Universe expansion later |

### 0.3 External data sources we have keys/credits for

| Source | Status | Use |
|---|---|---|
| **Databento** | Key in `backend/.env`; client at `backend/databento_provider.py`; $125 of credits | **Historical EOD options chains 2022→present**. Currently used only for daily OI. Backfill is the largest unrealized data asset. |
| Polygon.io | Key in env | Historical options aggregates, minute bars for SPY/QQQ |
| FlashAlpha | Key in env | 81 endpoints including historical EOD options, OI, quotes |
| Alpha Vantage | Key in env | Technical indicators, 500/day |
| Finnhub | Key in env | Real-time quotes, news, 60/min |
| yfinance | No key needed | Decades of OHLCV underlying, unlimited |
| Alpaca | Key in env | Paper trading; **never** historical |

### 0.4 Cache and Mongo state

- `cache/<TICKER>.json` — 228 bytes each, just `{ticker, spot, expiries, total_contracts, warmed_at}`. **Not training data.** Delete or repurpose.
- MongoDB has 8 collections with 2 indexes total. Snapshot data is what Session 7's ML trained on — 187 after-hours rows.

### 0.5 What Hermes can and cannot drive

| Tool | Hermes uses it? | Notes |
|---|---|---|
| Bash | ✅ | Primary executor |
| Python via venv | ✅ | `pip`, `pytest`, ad-hoc scripts |
| Mongo via `motor`/`pymongo` | ✅ | Programmatic; no DataGrip UI access |
| HTTP via `httpx`/`aiohttp` | ✅ | Databento, FlashAlpha, Polygon, etc. |
| `git`, `gh` | ✅ | Branches, PRs, CI logs |
| **PyCharm / WebStorm / DataGrip / IntelliJ** | ❌ | These are Nav's IDEs. There is no MCP that lets Hermes click in them. Anything described in prior plans as "Hermes uses DataGrip" was wrong. |
| Browser, GUI | ❌ | |

This plan therefore drops the JetBrains-driver pretense. Where the IDE adds value (visual coverage gutter, refactor preview, schema explorer), that's noted as a **Nav action** during PR review — never a Hermes step.

### 0.6 The truth-audit script (Hermes runs at the start of every session)

Hermes creates `qc/audit/truth_audit.sh` (Phase 0, task #1) and reads it on every session start. It asserts the *current* state against the *claimed* state:

```bash
#!/usr/bin/env bash
# qc/audit/truth_audit.sh — falsify recent "Phase X complete" commits
set -u
fail=0
say() { echo "AUDIT: $1"; }

# A) server.py must trend down
n=$(wc -l < backend/server.py)
say "server.py = $n lines"
[ "$n" -lt 3200 ] || { say "  ❌ Phase-A refactor unfinished (target < 3200)"; fail=1; }

# B) VEX/DEX/Vega-Total must exist if Phase B is claimed complete
for fn in calc_vex calc_dex calc_vega_total; do
  if grep -qE "def $fn" backend/*.py 2>/dev/null; then
    say "  ✅ $fn defined"
  else
    say "  ❌ $fn missing — Phase B not complete"; fail=1
  fi
done

# C) Synthetic data must not exist
if [ -f backend/ml_synthetic.py ]; then
  say "  ❌ backend/ml_synthetic.py present — synthetic data must be deleted"; fail=1
fi
if grep -rE "from ml_synthetic|import ml_synthetic|generate_synthetic_snapshots" backend/ 2>/dev/null | grep -v "__pycache__" >/dev/null; then
  say "  ❌ synthetic data is still imported somewhere"; fail=1
fi

# D) Strategy union must cover the named strategies
for cls in IronCondor Straddle Strangle Vertical Calendar SingleLeg; do
  if grep -qE "class $cls\b" backend/*.py 2>/dev/null; then
    say "  ✅ $cls Pydantic class exists"
  else
    say "  ❌ $cls missing — Phase F incomplete"; fail=1
  fi
done

# E) Data freshness — refuse to call any ML "trained" with < 1000 real samples
if [ -f models/SPY_direction.pkl ]; then
  n_real=$(python3 -c "import os, json; p='qc/data/SPY_training_manifest.json'; print(json.load(open(p))['n_rows']) if os.path.exists(p) else print(0)" 2>/dev/null)
  say "  SPY training corpus = ${n_real:-0} rows"
  [ "${n_real:-0}" -ge 1000 ] || { say "  ❌ model trained on < 1000 rows — degenerate"; fail=1; }
fi

exit $fail
```

This script's job is to **make lying expensive**. CI runs it on every PR. A session that opens with `fail=1` becomes a remediation session, not a feature session.

---

## 1. Operating laws (non-negotiable, code-enforced)

1. **No synthetic data.** Ever. Models train only on real market data. Test fixtures can be hand-crafted, but they live in `backend/tests/fixtures/` and are never imported by production code.
2. **No model ships without a data manifest.** Every model artifact is paired with `qc/data/<model>_manifest.json` listing: source files, row count, date range, target balance, feature variance.
3. **Degenerate-model gate.** Training pipeline asserts: target classes balanced within 30/70 in train, feature variance > 1e-6 on every feature, OOS predicted-probability distribution std > 0.05 (catches "always predicts the same thing"). Any violation → raises `DegenerateModelError` and refuses to save.
4. **Baseline-first.** No "model X works" claim without comparing against three baselines on the same OOS slice: (a) majority-class, (b) persistence (predict same as last bar), (c) penalized logistic on the same features. The model must beat all three on Sharpe-of-simulated-strategy.
5. **Out-of-sample is sacred.** Time-ordered split, never random. The last 20% of data by date is locked away as a holdout that nobody (including Hermes) reads until promotion.
6. **Truth-audit on every session.** §0.6 must pass green before any feature work. A red audit becomes the session's only task.
7. **No "Phase X complete" without the audit.** Commit titles `feat(Phase X): ...` are reserved for commits that flip a §0.6 check from ❌ to ✅. Anything else uses `feat(<scope>): ...` without the phase tag.
8. **Self-resumption.** Every session ends by writing 3+ specific next tasks to `NEXT_TASKS.md`. No vague entries. No "improve ML" — instead "run `python scripts/backfill_databento.py --ticker SPY --start 2022-01-01 --end 2022-12-31` and verify ≥ 200 days land in `databento_eod_chains` collection."
9. **Reality over story.** Numbers in reports come from script output, not from prose. PR descriptions paste the verification command and its output verbatim.
10. **Hermes uses CLI; Nav uses JetBrains.** Tool boundaries respected.

---

## 2. Hermes's actual toolbox

Everything Hermes needs lives in these primitives. The plan never asks Hermes to do something its toolbox can't.

| Capability | Tool / Library |
|---|---|
| File edits | `Read`, `Write`, `Edit` |
| Shell | `Bash` (pip, pytest, git, gh, curl, jq, find) |
| Python ad-hoc | `python -c "..."` with the project venv |
| Mongo | `motor` (async) and `pymongo` from Python scripts |
| HTTP | `httpx`/`aiohttp` to vendor APIs |
| Data | `pandas`, `pyarrow` (read CSVs in `data/github-repos/cloned/...`) |
| ML | `scikit-learn`, `xgboost`, `lightgbm`, `optuna`, `mlflow`, `shap` |
| Stats | `scipy`, `statsmodels` |
| CI | GitHub Actions via `.github/workflows/` |
| Tracking | Markdown files: `REVIEW_LOG.md`, `NEXT_TASKS.md`, `BACKLOG.md`, `docs/adr/` |

What Nav adds during PR review (the JetBrains pass):

| Action | Tool |
|---|---|
| Visual coverage gutter | PyCharm (`pytest --cov` + Run with Coverage) |
| Refactor preview before merge | PyCharm Refactor → Move/Extract |
| Mongo schema visualization + explain plans | DataGrip Console |
| React DevTools profiler | WebStorm + Chrome |
| Inspect Code (deep static analysis) | PyCharm / WebStorm Code → Inspect Code |

---

## 3. The bounded contexts (target architecture)

Same shape as a hedge-fund research/exec stack:

```
                          ┌──────────────────────────┐
                          │       Frontend           │
                          │ (heatmap, flow, alerts,  │
                          │  portfolio, ML insights) │
                          └────────────┬─────────────┘
                                       │ REST + WS
                          ┌────────────▼─────────────┐
                          │ FastAPI composition root │
                          │     server.py (small)    │
                          └────────────┬─────────────┘
                                       │
       ┌─────────────────┬─────────────┼─────────────┬──────────────┐
       ▼                 ▼             ▼             ▼              ▼
┌────────────┐  ┌────────────────┐ ┌─────────┐ ┌───────────┐ ┌────────────┐
│ Data layer │  │ Quant analytics│ │ Signals │ │ ML / RL   │ │ Execution  │
│ providers, │  │ Greeks, GEX,   │ │ alerts, │ │ pipeline  │ │ paper/live │
│ cache,     │  │ VEX, DEX, IV,  │ │ rules + │ │ + registry│ │ risk gate, │
│ DB, idx,   │  │ regime, PDF    │ │ ML enr. │ │ + drift   │ │ idempotent │
│ backfill   │  │ scenario mtx   │ │         │ │ monitor   │ │ recon loop │
└─────┬──────┘  └────────┬───────┘ └────┬────┘ └─────┬─────┘ └─────┬──────┘
      │                  │              │             │             │
      └──────────────────┴──────────────┴─────────────┴─────────────┘
                                  │
                ┌─────────────────▼──────────────────┐
                │  Mongo + Redis + filesystem        │
                │  (snapshots, chains, features,     │
                │   labels, predictions, models,     │
                │   orders, portfolio, audit)        │
                └────────────────────────────────────┘
```

Quality attributes:

| Attribute | Target | Enforcement |
|---|---|---|
| Truth | Audit ✅ on every PR | `qc/audit/truth_audit.sh` in CI |
| Determinism | Same input ⇒ same output | seed=0 everywhere; test asserts |
| Reproducibility | `pip install -r requirements.txt && pytest` matches CI | Pinned versions; hash-verified deps where feasible |
| Real data | No synthetic generators in `backend/` | CI grep guard |
| Non-degenerate models | Class balance, variance, prob-distribution checks | `DegenerateModelError` at train time |
| Out-of-sample | Locked holdout slice | Code refuses to peek at holdout outside promotion |
| Numerical correctness | Greeks/GEX agree with `floe`, `pyOptionPricing`, Hull to rel-err < 1e-6 | Fixture-based unit tests |
| Idempotency | Same `TradeIntent` ⇒ same `client_order_id` ⇒ one fill | Integration test |
| Coverage | Backend ≥ 80%; trading code ≥ 95% | `pytest --cov-fail-under` |

---

# Phase plan — reordered around reality

The old A–J plan assumed prior phases delivered. They didn't. The new plan does the audit, fixes the lie, lands real data, then builds.

Every phase has the same skeleton: **claim under audit** (what Hermes pretends is done) · **truth** (what the audit shows) · **work** (commands and code) · **proof** (the verification that flips the audit green) · **exit**.

---

## Phase 0 — Truth audit & synthetic-data demolition

**Claim:** Phases A, B, C, F complete.
**Truth:** §0.1. Three of four phases are not actually done; ML trained on fake data.

**Work units.**

1. Create `qc/audit/truth_audit.sh` from §0.6. Make it executable. Wire it into CI as a required check.
2. **Delete** `backend/ml_synthetic.py`. Find all imports and remove their callers. Replace any code that called `generate_synthetic_snapshots` with a clear `raise InsufficientRealDataError("collect more data — synthetic data is banned")`.
3. **Quarantine** Session 7's degenerate model. Move `models/SPY_direction.pkl` and `models/QQQ_direction.pkl` (if they exist) to `models/_quarantine/` with a `README.md` explaining why. Add a CI guard that refuses to load anything in `_quarantine/` at inference time.
4. **Re-baseline metrics.** Run `cloc backend frontend/src`, `radon cc backend -a`, `grep -c "^@(api|app)\." backend/server.py`. Write the numbers into `REVIEW_LOG.md` as the new floor.
5. **Honest commit hygiene.** Add a commit-message hook that rejects `feat(Phase X)` unless `truth_audit.sh` flipped a check from ❌ to ✅ in this commit. Implementation: hook diffs the audit output before/after.

**Proof.**
```bash
test ! -f backend/ml_synthetic.py
! grep -rE "from ml_synthetic|import ml_synthetic|generate_synthetic_snapshots" backend/ --include="*.py" | grep -v __pycache__
bash qc/audit/truth_audit.sh   # exits 0 OR exits with the truthful remaining red items
```

**Exit:** synthetic generator deleted, quarantine in place, audit script is the project's authority. Hermes's first action in every subsequent session is `bash qc/audit/truth_audit.sh`.

---

## Phase 1 — Real data acquisition (the only way Phase C can ever work)

**Target.** Years of real options chains and underlying bars for SPY/QQQ — and supplementary tickers — landed in Mongo and queryable, with manifests that prove provenance.

**Strategy.** Three parallel data tracks; each is independent so one stalling doesn't block the others.

### Track 1.A — Databento historical EOD chains (highest-quality, has credits)

Databento has the deepest options history. We have ~$125 of credit. Used right, that backfills years of EOD chains for SPY+QQQ.

1. Build `scripts/backfill_databento.py`:
   - Args: `--ticker SPY --start 2022-01-01 --end 2025-12-31 --schema opra-pillar.options.eod`
   - Streams DBN files to `data/databento/<ticker>/<year>/<month>.dbn.zst`
   - Parses to Mongo collection `databento_eod_chains` with index `(ticker, day desc)`
   - Cost-meter: queries Databento's `usage` endpoint before each request; halts if projected cost would exceed `DATABENTO_BUDGET_USD` (env var, default $100).
2. Run for SPY for 2022, 2023, 2024, 2025 — confirm row count in `qc/data/<ticker>_databento_manifest.json`.
3. Repeat for QQQ.
4. Document the schema in `docs/data-model/databento_eod.md`.

### Track 1.B — Yahoo Finance OHLCV underlying (free, deep, instant)

`yfinance` gives decades of bar data with no API key.

1. `scripts/backfill_yfinance.py --tickers SPY,QQQ,IWM,DIA,VIX,VIX9D,DXY,TLT --interval 1d --start 2015-01-01`
2. Also pull minute bars for the last 60 days (`--interval 1m --period 60d`) — yfinance limit.
3. Land in collection `underlying_bars` with `(ticker, ts desc)` index.

### Track 1.C — Ingest the cloned research-repo CSVs

These files are already on disk. Wasting them is the single biggest project sin.

1. `scripts/ingest_research_csvs.py` reads:
   - `data/github-repos/cloned/iAmGiG_gex-llm-patterns/.../issue_141_enhanced_dataset.csv`
   - `data/github-repos/cloned/iAmGiG_gex-llm-patterns/.../issue_145_next_day_outcomes_2024.csv`
   - `data/github-repos/cloned/iAmGiG_gex-llm-patterns/.../gamma_positioning_timeseries_2024.csv`
   - `data/github-repos/cloned/aaguiar10_gflows/data/csv/{spx,ndx,rut}_quotedata.csv`
   - `data/github-repos/cloned/FlashAlpha-lab_gex-explained/data/sample_chain.csv`
2. Lands each into its own collection with a `_source` field documenting provenance.
3. Manifest per file: `qc/data/<basename>_manifest.json` with row count, date range, columns, sha256.

### Cross-cutting

4. **One ingestion contract.** All three tracks land rows that pass `validate_ingested_row(row, kind)` — checks types, finite numerics, monotonic timestamps, no nulls in required fields.
5. **Data freshness dashboard.** `/api/admin/data/freshness` returns per-collection: `last_row_ts`, `row_count`, `oldest_row_ts`, `source`. Powers the audit.

**Proof.**
```bash
python scripts/backfill_databento.py --ticker SPY --start 2024-01-01 --end 2024-12-31
python scripts/backfill_yfinance.py --tickers SPY,QQQ --interval 1d --start 2020-01-01
python scripts/ingest_research_csvs.py --all

python - <<'PY'
import asyncio, os
from motor.motor_asyncio import AsyncIOMotorClient
async def main():
    db = AsyncIOMotorClient(os.environ["MONGO_URL"])[os.environ["DB_NAME"]]
    for col, threshold in [("databento_eod_chains", 250),
                           ("underlying_bars", 5000),
                           ("gex_llm_patterns_outcomes", 200)]:
        n = await db[col].count_documents({})
        assert n >= threshold, f"{col}: {n} < {threshold}"
        print(f"  ✅ {col}: {n}")
asyncio.run(main())
PY
```

**Exit:** ≥ 250 days of SPY EOD chains, ≥ 5000 SPY underlying bars, ≥ 200 labeled outcomes from the research CSVs. Manifests written. Truth-audit gains a section that checks these thresholds.

---

## Phase 2 — Data-quality gates as code

**Target.** The pipeline refuses to produce a degenerate model. Detection is in Python, not policy.

**Work units.**

1. New module `backend/services/ml/quality.py`:
   ```python
   def assert_class_balance(y, min_ratio=0.20): ...
   def assert_feature_variance(X, min_var=1e-6): ...
   def assert_temporal_ordering(ts): ...
   def assert_no_future_leakage(X, ts, lookahead_cols): ...
   def assert_holdout_untouched(holdout_idx, train_idx, val_idx): ...
   def assert_prediction_distribution(p, min_std=0.05): ...
   class DegenerateModelError(Exception): pass
   ```
2. The training entrypoint calls **every** gate before model.fit and after model.predict. Failures raise `DegenerateModelError` with a precise message ("feature `regime_changed` has variance 0; collected during 2026-05-17 16:00–24:00 ET; all rows after-hours").
3. Unit tests for each gate, including positive and negative cases.
4. The gates also surface as a `/api/admin/ml/data-quality?ticker=SPY` endpoint that returns a structured "go / no-go" verdict before any human-triggered retrain.

**Proof.**
```bash
pytest backend/tests/services/ml/test_quality.py -v
# All gates have positive + negative tests; all pass.
```

**Exit:** every entry into `train_*` calls the gates; degenerate models cannot be saved.

---

## Phase 3 — Math correctness vs. references on disk

**Target.** `bs_greeks.py`, `advanced_analytics.py`, `vol_analytics.py` produce numerical outputs that agree with the cloned reference libraries (`FullStackCraft_floe`, `boyac_pyOptionPricing`, `EsterHlav_Black-Scholes...`, `MattL922_implied-volatility`) and with hand-computed Hull-textbook examples.

**Work units.**

1. `backend/tests/test_bs_greeks_canonical.py` — Hull 10e examples: ATM 30-day call, OTM put, deep-ITM, zero-vol edge case. Rel-err < 1e-6.
2. `backend/tests/test_gex_reference.py` — feed `FlashAlpha-lab_gex-explained/data/sample_chain.csv` through `calc_gex` and assert known totals.
3. `backend/tests/test_floe_parity.py` — port one or two `floe` TypeScript test cases to Python and assert our Python implementations match.
4. `backend/tests/test_pdf_breeden_litzenberger.py` — synthetic risk-neutral PDF (lognormal) should be recovered to within 1% by `calc_implied_pdf` when fed corresponding call prices.
5. Add VEX, DEX, Vega-Total (the missing Phase B work). Each gets reference tests.

**Proof.**
```bash
pytest backend/tests/test_bs_greeks_canonical.py backend/tests/test_gex_reference.py \
       backend/tests/test_floe_parity.py backend/tests/test_pdf_breeden_litzenberger.py -v
grep -lE "def calc_vex|def calc_dex|def calc_vega_total" backend/*.py   # non-empty
bash qc/audit/truth_audit.sh    # Phase B section now green
```

**Exit:** numerical agreement to documented tolerance with all three reference libraries; Phase B audit flips green.

---

## Phase 4 — Feature engineering on real data

**Target.** `compute_features(ticker, as_of)` returns a row of ~50 features computed from real Mongo collections, with zero future leakage.

**Work units.**

1. Module `backend/services/ml/features.py`.
2. Feature families (the same taxonomy as before, but now powered by Phase 1 data):
   - **Underlying:** returns over 1m/5m/15m/1h/1d/5d horizons; realized vol (Parkinson, Garman-Klass) over 5d/20d/60d; overnight gap; opening range; ATR.
   - **GEX / VEX / DEX:** magnitude, z-score over 60d, rate of change, distance-to-flip in σ, wall density ATM±1%, Herfindahl gamma concentration.
   - **IV:** ATM IV, 25Δ RR, 25Δ butterfly, term-structure slope, IV rank, IV percentile.
   - **Flow:** sweep frequency, block premium, bull/bear premium ratio (5m / 30m / 1d).
   - **Macro:** VIX level, VIX9D/VIX ratio, DXY return, 10Y change.
   - **Sentiment:** rolling sentiment from `social_flow_pipeline` aggregated to 5m bars (when available).
   - **Calendar:** dow, dom, days-to-OPEX, days-to-FOMC, earnings-season flag.
3. **No-leakage guarantee.** Every feature at time `t` depends only on rows with `ts <= t`. Unit test asserts this by deliberately corrupting future rows and confirming features at `t` don't change.
4. `FEATURE_VERSION = "v1.0"`. Stored alongside every feature row. Model artifacts pin their feature version; mismatched versions refuse inference.
5. Lands in collection `ml_features` with index `(ticker, version, ts desc)`.

**Proof.**
```bash
python -m backend.services.ml.features --ticker SPY --start 2024-01-01 --end 2024-12-31
# Writes ~50 feature rows per market day × 252 days into ml_features.
# Manifest qc/data/SPY_features_v1.0_manifest.json shows row count, variance per column, null rates.

pytest backend/tests/services/ml/test_features_no_leakage.py -v   # passes
```

**Exit:** ml_features collection populated for SPY+QQQ across the available real-data window; manifest shows variance > 1e-6 on every feature; no-leakage test green.

---

## Phase 5 — Targets, baselines, and the real model bake-off

**Target.** Multi-task targets computed honestly; three baselines beat each model that gets promoted.

**Work units.**

1. **Targets** (multi-task, all stored alongside features):
   - `ret_1h`, `ret_eod`, `range_1h`
   - `dir_1h ∈ {-1,0,+1}` with threshold τ = 0.25 × rolling-ATR
   - `regime_change_1h` boolean
2. **Walk-forward CV** (`WalkForwardSplit(n_splits=8, train_size_months=12, test_size_months=2, embargo_hours=2)`).
3. **Baselines** (these are gates, not afterthoughts):
   - `baseline_majority` — always predicts the train-set majority class
   - `baseline_persistence` — predicts the same as the last bar's realized direction
   - `baseline_linear` — penalized logistic regression on the same features
4. **Models** (four families, same harness):
   - Logistic regression (the baseline above doubles as the simplest model)
   - XGBoost
   - LightGBM
   - 1D-CNN (PyTorch) — optional, gated by GPU
5. **Optuna search**, 50 trials each, inner CV inside each fold.
6. **Calibration** via `CalibratedClassifierCV(method='isotonic')` on a held-out fold slice.
7. **SHAP** for tree models, `IntegratedGradients` for the CNN. Feature importance per fold + average.
8. **Reports** under `qc/ml-runs/<run_id>/`:
   - `report.md` opening with a one-line verdict: `SHIP / REJECT / ITERATE`.
   - Per-model: ML metrics (accuracy, F1, AUC, Brier, calibration error) + trading metrics (hit rate, profit factor, Sharpe, Sortino, Calmar, max-DD).
   - **The model is rejected if it doesn't beat all three baselines on Sharpe.**
   - Calibration plot, SHAP summary plot, prediction distribution plot.
9. The training entrypoint refuses to save a model that doesn't beat baselines or that fails any §2 gate.

**Proof.**
```bash
python -m backend.services.ml.pipeline --ticker SPY --run-id qc-001
# Produces qc/ml-runs/qc-001/report.md
head -3 qc/ml-runs/qc-001/report.md   # must contain SHIP / REJECT / ITERATE verdict line
```

**Exit:** at least one model passes all gates on at least one ticker, with trading metrics that beat the three baselines on the held-out slice. If nothing passes, the verdict is `REJECT` and Hermes goes back to Phase 4 (feature engineering) — **this is a feature, not a failure**.

---

## Phase 6 — Model registry, inference, drift

**Target.** Active model identifiable by ID; promotion gated; drift monitored.

**Work units.**

1. MLflow tracking, local file backend at `mlruns/`. Each Optuna trial logs params, metrics, artifacts.
2. Mongo collection `ml_models` rows: `model_id`, `ticker`, `feature_version`, `training_window`, `metrics_summary`, `artifact_path`, `created_at`, `status` ∈ {`shadow`, `active`, `retired`}.
3. Endpoint `POST /api/admin/ml/promote/{model_id}` flips `shadow → active` only if:
   - `metrics_summary.beats_baselines == true`
   - `metrics_summary.holdout_sharpe > prior_active.holdout_sharpe`
   - `metrics_summary.calibration_error < 0.05`
4. Inference endpoint `POST /api/ml/predict/{ticker}` loads the active model, runs `compute_features` over the latest window, returns `{prediction, calibrated_probability, model_id, feature_version, request_id, ts}`. Latency p95 < 100 ms (XGBoost/LightGBM) — profile and assert.
5. PSI drift monitor. Hourly cron computes PSI per feature over rolling 24h vs the training-window distribution; logs alarms when PSI > 0.25.
6. Every prediction logged to `ml_predictions` with feature snapshot + (later, after horizon) realized outcome. Powers online evaluation.

**Proof.**
```bash
curl -fs -X POST localhost:8000/api/admin/ml/promote/<id> | jq .status     # "active"
curl -fs -X POST localhost:8000/api/ml/predict/SPY | jq .
# Returns prediction with model_id, feature_version, calibrated_probability
```

**Exit:** an active SPY model with provenance, monitored for drift, returning calibrated probabilities at latency budget.

---

## Phase 7 — server.py decomposition (the real one)

**Target.** `server.py` ≤ 200 lines, every handler in `backend/routes/<context>.py`.

**Why now.** Earlier phases produced real tests (math, features, ML). With those passing, decomposition is safe.

**Work units.**

1. Build the route inventory: `grep -nE "^@(api|app)\." backend/server.py > qc/audit/routes_before.txt`.
2. For each of the 74 handlers, decide its target module: `market_data`, `analytics`, `alerts`, `ml`, `trading`, `portfolio`, `briefings`, `auth`, `admin`.
3. Move one router per PR. Each PR: extract, register in `server.py`, run full pytest, run integration smoke (`curl /health`, `curl /api/admin/data/freshness`), commit.
4. Extract shared deps (`get_db`, `get_redis`, `get_current_user`, `rate_limit`) into `backend/deps.py`.
5. Final `server.py` is composition root: app, middleware, routers include, lifespan.

**Proof.**
```bash
wc -l backend/server.py    # ≤ 200
pytest -ra                  # all green
diff <(grep -nE "^@(api|app)\." backend/server.py | wc -l) <(echo 0) && echo "no handlers left in server.py"
```

**Exit:** truth-audit Phase A check flips green; tests still pass.

---

## Phase 8 — Alerts & signals (rule DSL + ML enrichment + history)

Same shape as the prior plan's Phase E, but now ML-enriched predicates resolve to a *calibrated* model. Each alert ties to a backtest report (Phase 9) with a quality score.

**Work units.**

1. YAML alert DSL at `backend/alerts/definitions/*.yaml` (predicate, priority, cooldown, description).
2. Predicate evaluator supports rule-only and ML-enriched predicates (`ml.dir_1h_proba > 0.65`).
3. `alerts_history` collection — every fire stored with predicate value, model prediction (if used), realized outcome at horizon.
4. Migrate the 7 hardcoded alerts in `alert_engine.py` to YAML; delete the Python methods.

**Exit:** new alert = YAML file + Phase 9 backtest run. No code change.

---

## Phase 9 — Backtester (gates alerts & ML for "live use")

**Target.** Event-driven, no-lookahead backtester with realistic slippage/commission, used to grade every alert and ML model before it goes live.

**Work units.**

1. `backend/services/backtest/engine.py` — event-driven; fills at next-bar open; slippage 0.05%, commission $0.65/contract default.
2. `Signal.evaluate(snapshot_history, bar_history, position) -> Action` interface — same shape for rule alerts and ML predictions.
3. Three preset evaluations: 70/30 IS-OOS, walk-forward (same splits as Phase 5), Monte Carlo bootstrap (1000 paths).
4. Reports under `qc/backtests/<id>/`.

**Exit:** every alert in `alerts/definitions/` has a backtest report with Sharpe, hit rate, max-DD. Alerts with Sharpe < 0 are auto-downgraded.

---

## Phase 10 — Trading execution (idempotency, risk gate, reconciliation)

**Work units.** (Same as prior plan's Phase F, now after the data/ML foundation is real.)

1. `TradeIntent` Pydantic; `client_order_id` = deterministic hash(intent + session_salt).
2. `check_risk(intent, portfolio, account)` runs before every submit: max position, max daily loss, concurrent-position limit, premium-as-fraction-of-equity, expiry hygiene, regime-aware sizing.
3. Paper-vs-live URL guard: constructor asserts `"paper" in BASE_URL` unless `LIVE_TRADING_ENABLED=1`.
4. 30-second reconciliation loop diffs Alpaca `list_orders` against local `orders` collection.
5. `Strategy` Pydantic discriminated union covers `IronCondor`, `Straddle`, `Strangle`, `Vertical`, `Calendar`, `SingleLeg`. Phase F's typo (`iron_condible`) gone, *and* the union is complete (truth-audit covers this).

**Exit:** integration tests prove same-intent → one fill; risk-cap rejections work; live URL refused without explicit flag.

---

## Phase 11 — Portfolio & P&L (Decimal math, tax-lot, event log)

Same as prior plan. Tax-lot FIFO/LIFO/HIFO; multi-leg aggregation; event-sourced position state; EOD mark cron at 16:15 ET.

---

## Phase 12 — Frontend architecture

`TanStack Query` + `Zustand`. `App.js` ≤ 100 lines. Page-per-route. Hooks for every data feed. Tests for every component (≥ 60% coverage at exit). React Testing Library + Playwright happy-path E2E. `react-hooks/exhaustive-deps: error`.

---

## Phase 13 — Observability & SLOs

`structlog` JSON logs with request IDs; Prometheus metrics; OpenTelemetry traces; Sentry-style error tracker via existing `error_tracking.py`; Grafana dashboards; runbooks; SLOs in `docs/SLO.md`.

---

## Phase 14 — Quality processes

ADRs under `docs/adr/`. PR template requires verification output and risk assessment. Conventional commits enforced via commitlint. Trunk-based; main always deployable. Coverage ratchet to 85% backend / 75% frontend.

---

## 4. Self-resumption — how Hermes never runs out of work

**`NEXT_TASKS.md`** is the resumption file. It lives at the repo root. Every Hermes session:

1. Opens by reading `NEXT_TASKS.md` and `REVIEW_LOG.md` (last 5 entries).
2. Picks the first non-blocked task and works it.
3. When done (or blocked), writes the next 3 tasks to `NEXT_TASKS.md`.

Task format is strict — example:

```markdown
- [ ] **task-id**: <imperative summary>
  - **Phase:** <0..14>
  - **Estimate:** <minutes>
  - **Run:** `<exact bash command>`
  - **Proof:** `<exact bash command whose output proves it worked, with expected text>`
  - **On failure:** <fallback or escalation>
```

Vague tasks ("improve ML") are forbidden. Tasks must be runnable cold by a fresh session.

If a task is impossible (data missing, key revoked, API down): Hermes appends to `BLOCKERS.md` with the specific reason and the exact symptom (curl output, traceback), and moves to the next non-blocking task.

---

## 5. Anti-stall protocol

Hermes commonly stops because of:

1. **Ambiguity.** Solution: every task in `NEXT_TASKS.md` has exact commands.
2. **A single failing tool call.** Solution: on the first failure, try the documented fallback. On a second failure, log to `BLOCKERS.md` and move on. Never spin.
3. **End of stated scope.** Solution: a session never ends without writing ≥ 3 new entries to `NEXT_TASKS.md`. If genuinely no next tasks exist within the current phase, the next task is "promote next phase: re-read `CLAUDE_REVIEW_PROMPT.md` §<next-phase>, write 3 seed tasks."
4. **Lost context.** Solution: `REVIEW_LOG.md` is append-only with one line per action. `NEXT_TASKS.md` is the queue. A fresh session reads both and is oriented in under a minute.
5. **Fake completion.** Solution: §0.6 truth-audit gates every PR. Lies can't merge.

---

## 6. The week-one runway (what `NEXT_TASKS.md` looks like at hand-off)

Seeded by Hermes immediately after reading this plan, before doing anything else:

```markdown
- [ ] **phase0-1**: create truth-audit script
  - **Run:** write `qc/audit/truth_audit.sh` from CLAUDE_REVIEW_PROMPT.md §0.6, chmod +x
  - **Proof:** `bash qc/audit/truth_audit.sh; echo "exit=$?"` runs and prints its checks
- [ ] **phase0-2**: delete synthetic data and its callers
  - **Run:** `git rm backend/ml_synthetic.py`; grep for `generate_synthetic_snapshots` / `import ml_synthetic` and replace each caller with `raise InsufficientRealDataError(...)`
  - **Proof:** `test ! -f backend/ml_synthetic.py && ! grep -rE "ml_synthetic" backend/ --include='*.py' | grep -v __pycache__`
- [ ] **phase0-3**: quarantine the degenerate Session-7 model
  - **Run:** `mkdir -p models/_quarantine && git mv models/SPY_direction.pkl models/_quarantine/ 2>/dev/null; git mv models/QQQ_direction.pkl models/_quarantine/ 2>/dev/null; echo 'Quarantined: trained on flat after-hours data, predicts one class at 0.9998 confidence.' > models/_quarantine/README.md`
  - **Proof:** `test -f models/_quarantine/README.md`
- [ ] **phase0-4**: wire truth-audit into CI
  - **Run:** add a job to `.github/workflows/ci.yml` that runs `bash qc/audit/truth_audit.sh`
  - **Proof:** open a PR; the new CI job is required and runs the audit
- [ ] **phase1-1**: scaffold `scripts/backfill_databento.py`
  - **Run:** create the script per §Phase 1 Track 1.A; dry-run with `--ticker SPY --start 2024-12-01 --end 2024-12-31`
  - **Proof:** dry-run prints projected request count + cost; no API calls made
- [ ] **phase1-2**: ingest research-CSVs
  - **Run:** `python scripts/ingest_research_csvs.py --all`
  - **Proof:** Mongo collection `gex_llm_patterns_outcomes` count ≥ 200; manifest at `qc/data/issue_145_next_day_outcomes_2024_manifest.json` exists with non-empty `row_count`
- [ ] **phase1-3**: yfinance backfill
  - **Run:** `python scripts/backfill_yfinance.py --tickers SPY,QQQ,IWM,DIA,VIX --interval 1d --start 2015-01-01`
  - **Proof:** Mongo `underlying_bars` count ≥ 10000
```

Hermes seeds this file as its first action. The file is the loop's fuel.

---

## 7. What this plan is NOT

- **Not a feature list.** Features go in `BACKLOG.md`. This plan is about getting to a state where features can be built safely.
- **Not a story.** Numbers come from script output, not prose. Each phase passes or fails by its proof commands.
- **Not aspirational about Hermes tooling.** Hermes drives CLI + Python + files. Nav drives JetBrains for visual passes.
- **Not security theater.** Account is private; standard env-file hygiene only. No key rotation.
- **Not infrastructure-first.** Azure deploy is post-Phase-14.

---

## 8. The five questions for Nav that gate Phase 5

(Same as prior plan, kept here because they still apply.)

1. **Universe.** SPY+QQQ only for ML, or include IWM/DIA/sector ETFs? (Default: SPY+QQQ.)
2. **Horizon priority.** 1h primary or EOD primary? (Default: 1h primary, EOD secondary.)
3. **Risk cap.** Hard 2% per trade, regime can only reduce? Or dynamic widening allowed? (Default: hard cap.)
4. **GPU.** Available for CNN? (Default: skip CNN until available.)
5. **Data window.** From 2020-01-01 onward? (Default: yes — pre-2020 regime is different enough to hurt.)

Hermes asks these via `AskUserQuestion` at the start of Phase 5 and writes the answers to `docs/adr/0001-ml-scope.md`.

---

*This plan is the contract. Every PR proves a piece of it true. The truth-audit script is the umpire. Lying is expensive, fixing is cheap, building on truth is the only thing that compounds.*
