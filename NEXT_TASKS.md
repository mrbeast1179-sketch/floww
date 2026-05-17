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

## Active phase: 0 — Truth audit & synthetic-data demolition

- [ ] **phase0-1**: write the truth-audit script
  - **Run:** create `qc/audit/truth_audit.sh` verbatim from `CLAUDE_REVIEW_PROMPT.md` §0.6; `chmod +x qc/audit/truth_audit.sh`
  - **Proof:** `bash qc/audit/truth_audit.sh; echo "exit=$?"` runs end-to-end and prints each check's ✅/❌
  - **On failure:** none — pure file write

- [ ] **phase0-2**: delete the synthetic-data generator and rewire callers
  - **Run:**
    ```bash
    grep -rEn "from ml_synthetic|import ml_synthetic|generate_synthetic_snapshots" backend/ --include='*.py' \
      | grep -v __pycache__ > /tmp/synthetic_callers.txt
    cat /tmp/synthetic_callers.txt   # review before editing
    # For each caller: replace the call with: raise InsufficientRealDataError("synthetic data is banned — collect more real data via scripts/backfill_*")
    # Add InsufficientRealDataError to backend/services/ml/errors.py (create the module if absent).
    git rm backend/ml_synthetic.py
    ```
  - **Proof:**
    ```bash
    test ! -f backend/ml_synthetic.py \
      && ! grep -rE "ml_synthetic|generate_synthetic_snapshots" backend/ --include='*.py' | grep -v __pycache__
    ```
  - **On failure:** if a caller is in a hot path that breaks production, comment out the call site behind a feature flag and add a `phase0-2-followup` task; do not silently restore synthetic data.

- [ ] **phase0-3**: quarantine the Session-7 degenerate models
  - **Run:**
    ```bash
    mkdir -p models/_quarantine
    for f in models/SPY_direction.pkl models/QQQ_direction.pkl; do
      [ -f "$f" ] && git mv "$f" models/_quarantine/ || true
    done
    cat > models/_quarantine/README.md <<'EOF'
    Quarantined models — DO NOT LOAD.
    Trained on 187 after-hours snapshots with constant spot. Output one class at 0.9998 confidence on all inputs.
    Reference: REVIEW_LOG.md and CLAUDE_REVIEW_PROMPT.md §0.1.
    EOF
    ```
  - **Proof:** `test -f models/_quarantine/README.md && grep -q 'DO NOT LOAD' models/_quarantine/README.md`
  - **On failure:** none

- [ ] **phase0-4**: add load-guard so inference refuses quarantined artifacts
  - **Run:** in the model-loading path (currently `joblib.load` calls in `ml_price_prediction.py` and `ml_advanced.py`), wrap with `assert "_quarantine" not in str(path), f"refused to load quarantined model: {path}"`
  - **Proof:**
    ```bash
    python -c "
    from pathlib import Path
    bad = Path('models/_quarantine/SPY_direction.pkl')
    bad.parent.mkdir(parents=True, exist_ok=True); bad.write_text('x')
    import ml_price_prediction as m
    try:
        m.load_model(str(bad)); print('FAIL: loaded quarantined')
    except AssertionError as e:
        print('OK:', e)
    "
    ```

- [ ] **phase0-5**: wire truth-audit into CI as a required check
  - **Run:** add a job `truth-audit` to `.github/workflows/ci.yml`:
    ```yaml
    truth-audit:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - run: bash qc/audit/truth_audit.sh
    ```
    Then mark the job required in branch protection.
  - **Proof:** open a throwaway PR; the `truth-audit` job appears and runs.

- [ ] **phase0-6**: add a commit-message hook that bans fake `feat(Phase X)` titles
  - **Run:** in `.pre-commit-config.yaml`, add a custom local hook:
    ```yaml
    - repo: local
      hooks:
        - id: phase-claim-honesty
          name: Phase claims must flip a truth-audit check
          language: system
          stages: [commit-msg]
          entry: bash qc/audit/check_phase_claim.sh
    ```
    `qc/audit/check_phase_claim.sh` reads the commit message; if the title starts with `feat(Phase ` it runs `bash qc/audit/truth_audit.sh` and refuses unless at least one check that was ❌ in `HEAD` is ✅ in the working tree.
  - **Proof:** attempt a no-op commit with title `feat(Phase A): pretend to refactor` — the hook rejects it.

- [ ] **phase0-7**: log the new baseline measurements
  - **Run:**
    ```bash
    {
      echo "## $(date -u +%FT%TZ) — Phase 0 baseline"
      echo "- server.py lines: $(wc -l < backend/server.py)"
      echo "- route count: $(grep -cE '^@(api|app)\.' backend/server.py)"
      echo "- App.js lines: $(wc -l < frontend/src/App.js)"
      echo "- mongo collections + counts: see qc/audit/mongo_inventory.txt"
      echo "- truth audit: $(bash qc/audit/truth_audit.sh; echo exit=$?)"
    } >> REVIEW_LOG.md
    ```
  - **Proof:** `tail -10 REVIEW_LOG.md | grep -q "Phase 0 baseline"`

---

## On-deck (seeded for after Phase 0 closes — Hermes re-orders as needed)

- [ ] **phase1-1**: scaffold `scripts/backfill_databento.py`
  - **Run:** create the script per `CLAUDE_REVIEW_PROMPT.md` §Phase 1 Track 1.A. First implementation handles `--dry-run` only and prints projected cost from Databento `metadata.get_cost`. No live API calls yet.
  - **Proof:** `python scripts/backfill_databento.py --ticker SPY --start 2024-12-01 --end 2024-12-31 --dry-run` prints a non-zero projected cost in USD without spending credit.

- [ ] **phase1-2**: write `scripts/ingest_research_csvs.py`
  - **Run:** create the ingestion script per §Phase 1 Track 1.C. It reads the five named CSV paths, parses to records, lands in `gex_llm_patterns_outcomes`, `gex_llm_patterns_timeseries`, `cboe_quotes_spx`, `cboe_quotes_ndx`, `cboe_quotes_rut`, `flashalpha_sample_chain` collections, writes per-file manifest at `qc/data/<basename>_manifest.json`.
  - **Proof:**
    ```bash
    python scripts/ingest_research_csvs.py --all
    python - <<'PY'
    import json, glob
    for p in glob.glob("qc/data/*_manifest.json"):
        m = json.load(open(p))
        assert m["row_count"] > 0, p
        print(p, m["row_count"])
    PY
    ```

- [ ] **phase1-3**: yfinance backfill of underlying bars
  - **Run:** `python scripts/backfill_yfinance.py --tickers SPY,QQQ,IWM,DIA,VIX,VIX9D,DXY,TLT --interval 1d --start 2015-01-01`
  - **Proof:** mongo `underlying_bars` count ≥ 10000

- [ ] **phase1-4**: enable real backfill (lift `--dry-run` only after Nav approves cost)
  - **Run:** with Nav's explicit OK in-session, `python scripts/backfill_databento.py --ticker SPY --start 2024-01-01 --end 2024-12-31`
  - **Proof:** mongo `databento_eod_chains` count by `ticker == SPY` ≥ 250

- [ ] **phase2-1**: write `backend/services/ml/quality.py` with all degeneracy gates
  - **Run:** implement per `CLAUDE_REVIEW_PROMPT.md` §Phase 2. Add `backend/tests/services/ml/test_quality.py` with positive + negative tests for each gate.
  - **Proof:** `pytest backend/tests/services/ml/test_quality.py -v` passes

- [ ] **phase3-1**: canonical Black-Scholes tests against `EsterHlav_Black-Scholes-Option-Pricing-Model`
  - **Run:** port four Hull-textbook examples + one zero-vol degenerate case into `backend/tests/test_bs_greeks_canonical.py`. Compare to our `bs_greeks` with rel-err < 1e-6.
  - **Proof:** `pytest backend/tests/test_bs_greeks_canonical.py -v` passes

---

## Blocked

(empty — when adding, link the BLOCKERS.md row)

---

## Done (archived)

(empty)
