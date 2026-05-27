# DeepSeek Pro — Round 9 Closure + Full System Validation (target: 5-6 hours)

> **For agentic workers:** Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. This is a CLOSURE + VALIDATION mission — you are not adding features. Your job is to land in-flight work, verify damage, exercise the running system end-to-end, and lock the round closed with a high-quality closure doc.

**Goal:** Close Round 9 properly. Beyond just landing commits, this mission VALIDATES that the integrated system actually works — every endpoint each agent touched gets exercised, every claim in every commit gets grep-verified, every deleted dead-code name gets per-name verified, the ML pipeline runs end-to-end with --dry-run, and a Round-10 plan document is generated from real evidence (not from hope).

**Architecture:** You hold full context that no individual Owl Alpha can — the FULL 24-commit Round-9 history + A2's out-of-scope inference.py bugfix + A9's deletion damage map + A10's recovery scope + every agent's close-out doc + the live runtime state of backend + frontend. You make architect-level judgment calls (accept/reject A2's bugfix; decide conftest.py freeze waiver; decide whether to escalate A9 incident to Round 10 plan or leave as-is; decide whether observable backend memory growth warrants immediate fix or R10 ticket) without needing to ping back.

**Tech Stack:** Python 3.13 · FastAPI · pytest · ruff · git (with pull --rebase + stash) · npm + jest · curl · ps.

**Why this is YOU not another Owl Alpha:**
- 12 task types span source code, tests, docs, runtime validation, judgment calls
- Cross-agent context required (read every close-out doc + every diff)
- Multiple architect-level decisions (out-of-scope acceptance, freeze waivers, R10 escalation)
- Concurrent-modification race recovery (stuck pushes, rebase conflicts)
- Final closure doc must accurately reflect 30+ commits + actual runtime behavior

**Time budget (~330 min + 30 min slack = ~6 hours):**
- Phase A — Verify & Decide: 65 min (T1, T2, T3)
- Phase B — Complete Pending Agent Work: 90 min (T4, T5, T6)
- Phase C — Validation, RUN the System: 100 min (T7, T8, T9, T10)
- Phase D — Closure Documentation: 60 min (T11, T12)
- Slack for halts, conflict resolution: 30 min

---

## Pre-flight hard gates (do EVERY one — STOP on any failure)

- [ ] **PF1.** `pwd` ends in `/Users/nav/Documents/GitHub/floww`. NOT `/Users/nav/GitHub/floww` (stale clone — caused 3+ production incidents).

- [ ] **PF2.** Confirm origin tip is at `e2a70e3` (this plan's own commit) or LATER (more agents may have pushed since):
  ```bash
  git fetch origin && git log origin/main --oneline -5
  ```
  If origin is OLDER than `e2a70e3`, you're in the wrong clone — STOP.

- [ ] **PF3.** Build green:
  ```bash
  cd backend && .venv/bin/python3 -c "from server import app; print('OK')"
  ```
  Must print `OK`. If any ImportError → A9's damage incomplete → make T2 (deep audit) the FIRST priority and skip ahead.

- [ ] **PF4.** Capture full baselines to `/tmp/dspro_baseline.txt`:
  ```bash
  cd /Users/nav/Documents/GitHub/floww
  {
    echo "=== Baseline at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
    echo "Origin tip: $(git rev-parse origin/main)"
    echo "Local HEAD: $(git rev-parse HEAD)"
    echo ""
    echo "=== Pytest collection ==="
    (cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3)
    echo ""
    echo "=== Pytest full sweep (--tb=no) ==="
    (cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -5)
    echo ""
    echo "=== Working tree ==="
    git status --short
    echo ""
    echo "=== Last 25 commits ==="
    git log origin/main --oneline -25
    echo ""
    echo "=== File count in backend/services ==="
    ls backend/services/*.py | wc -l
    echo ""
    echo "=== Total LOC in backend (excluding venv) ==="
    find backend -name '*.py' -not -path '*/\.venv/*' -not -path '*/__pycache__/*' | xargs wc -l | tail -1
  } > /tmp/dspro_baseline.txt
  cat /tmp/dspro_baseline.txt | head -40
  ```

- [ ] **PF5.** Note working tree state:
  ```bash
  git status --short
  ```
  Modified files you'll need to decide on: typically `inference.py` (A2 HOLD-zone fix), `ml_api.py` (A2 /health endpoints, may have landed already), `pyproject.toml` (A1 T8 may have started). Untracked: agent test files (A4/A5/A6/A7 close-out residue). Any OTHER unexpected files → STOP and reconcile.

- [ ] **PF6.** Confirm Python venv has needed tools:
  ```bash
  cd backend
  .venv/bin/python3 -c "import joblib, pytest, ruff" 2>&1 || \
    .venv/bin/pip install joblib pytest ruff
  .venv/bin/python3 -c "import psutil" 2>&1 || \
    .venv/bin/pip install psutil   # for T10 memory check
  ```

- [ ] **PF7.** First pulse:
  ```bash
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DSPRO :: started :: pre-flight OK :: HEAD=$(git rev-parse --short HEAD)" \
    | tee -a kanban/cards/agent_DSPRO_status.md ~/Documents/GitHub/Hermes/Daily\ Log.md 2>/dev/null
  ```

---

# PHASE A — Verify & Decide (~65 min)

## Task 1 — Decide A2's out-of-scope modifications (25 min)

A2 was scoped to: `services/__init__.py` (NEW), `services/ml/__init__.py` (NEW), `tests/services/ml/test_ml_integration.py` (REWRITE), `tests/test_services_is_package.py` (NEW), `pytest.ini` (NEW). A2 ALSO modified `inference.py` (forbidden file) AND `ml_api.py` (A1's scope). Both apparently legitimate.

### 1.1 — Read A2's inference.py change

```bash
git diff -- backend/services/ml/inference.py | head -50
```

Expect: a change to `_map_binary_to_3way()` HOLD-zone logic. Old version returned UP/DOWN with un-normalized probabilities (~1.9 sum) in weak-confidence band. New version returns HOLD with probs normalized to sum=1.0.

- [ ] **1.1.1** Verify the fix logic with a comprehensive test BEFORE accepting:
  ```bash
  cat > /tmp/test_hold_zone.py <<'EOF'
  """Comprehensive verification of A2's _map_binary_to_3way HOLD-zone fix.
  
  Tests cover: weak confidence (HOLD), strong UP, strong DOWN, boundary cases,
  probability normalization, type return.
  """
  import sys
  sys.path.insert(0, "/Users/nav/Documents/GitHub/floww/backend")
  from services.ml.inference import _map_binary_to_3way, HOLD, UP, DOWN, STRONG_CONFIDENCE
  
  print(f"STRONG_CONFIDENCE threshold: {STRONG_CONFIDENCE}")
  print(f"UP={UP}, HOLD={HOLD}, DOWN={DOWN}")
  print()
  
  cases = [
      # (prediction, proba, expected_label, description)
      (1, [0.45, 0.55], "HOLD", "Weak UP confidence (0.55)"),
      (0, [0.55, 0.45], "HOLD", "Weak DOWN confidence (0.55)"),
      (1, [0.50, 0.50], "HOLD", "Exactly 50/50"),
      (1, [0.20, 0.80], "UP",   "Strong UP (0.80)"),
      (0, [0.85, 0.15], "DOWN", "Strong DOWN (0.85)"),
      (1, [0.30, 0.70], "UP",   "Strong-ish UP (0.70 — should hit STRONG_CONFIDENCE boundary)"),
  ]
  
  errors = []
  for pred_in, proba, expected, desc in cases:
      pred_out, probs_out = _map_binary_to_3way(prediction=pred_in, proba=proba)
      label_map = {UP: "UP", HOLD: "HOLD", DOWN: "DOWN"}
      label_out = label_map.get(pred_out, f"UNKNOWN({pred_out})")
      probs_sum = sum(probs_out)
      
      # Acceptance checks
      sum_ok = abs(probs_sum - 1.0) < 0.01
      label_match = label_out == expected
      
      status = "OK " if sum_ok and label_match else "FAIL"
      print(f"  [{status}] {desc}")
      print(f"         in:  pred={pred_in} proba={proba}")
      print(f"         out: pred={pred_out}({label_out}) probs={[round(p, 3) for p in probs_out]} sum={probs_sum:.4f}")
      
      if not sum_ok:
          errors.append(f"{desc}: probs sum {probs_sum:.4f} != 1.0")
      if not label_match:
          errors.append(f"{desc}: got {label_out}, expected {expected}")
  
  print()
  if errors:
      print(f"FAILED ({len(errors)} errors):")
      for e in errors: print(f"  - {e}")
      sys.exit(1)
  else:
      print("ALL PASS — A2's fix is correct, safe to accept")
      sys.exit(0)
  EOF
  cd /Users/nav/Documents/GitHub/floww && backend/.venv/bin/python3 /tmp/test_hold_zone.py
  ```

- [ ] **1.1.2** Cross-check: grep for OTHER callers of `_map_binary_to_3way` to understand blast radius:
  ```bash
  grep -rn '_map_binary_to_3way' backend/ --include='*.py' | grep -v '\.venv/' | head -10
  ```
  Document each caller in your pulse — if any test relies on the OLD buggy behavior, you must update that test too OR document the breakage.

### 1.2 — Accept or revert A2's inference.py

- [ ] **1.2.1** If 1.1.1 test PASSED and 1.1.2 found no broken callers → **ACCEPT**. Stage the change to its own commit:
  ```bash
  cd /Users/nav/Documents/GitHub/floww
  git add backend/services/ml/inference.py
  git commit -m "$(cat <<'EOF'
  fix(round-9-architect): _map_binary_to_3way HOLD-zone correct prediction + normalized probs
  
  Originally A2's discovery (out-of-A2-scope file inference.py). Architect
  (DS Pro) accepted after independent verification — bug was real, fix is
  correct, no other callers rely on the buggy behavior.
  
  Bug: in the weak-confidence band (e.g., proba=[0.45, 0.55]), the function
  returned UP or DOWN with probabilities summing to ~1.9 (not normalized).
  Effect: clients downstream of inference.predict() that used the probability
  vector for thresholding got incoherent values.
  
  Fix: return HOLD in the weak band, with probs normalized to sum=1.0.
  
  Verification (full test in /tmp/test_hold_zone.py):
  $ backend/.venv/bin/python3 /tmp/test_hold_zone.py
  ALL PASS — A2's fix is correct, safe to accept
  
  Cross-caller check:
  $ grep -rn '_map_binary_to_3way' backend/ --include='*.py' | grep -v '\.venv/'
  <PASTE CALLERS HERE — confirm each caller's behavior is improved not broken>
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'architect.*HOLD-zone'
  ```

- [ ] **1.2.2** If 1.1.1 test FAILED → **REVERT**:
  ```bash
  cd /Users/nav/Documents/GitHub/floww
  git checkout -- backend/services/ml/inference.py
  ```
  Document in close-out (T12): "A2's HOLD-zone fix attempted but probability normalization broken; logged as R10 ticket."

### 1.3 — Decide A2's ml_api.py /health endpoints

Check if still uncommitted on local tree (may have already landed during prior session activity):

```bash
git diff -- backend/routes/ml_api.py | head -60
```

- [ ] **1.3.1** If `git diff` shows no changes (already committed by another agent or A2 themselves) → SKIP this sub-task.
- [ ] **1.3.2** If diff shows added `/health/{ticker}` + `/health` endpoints → verify import path:
  ```bash
  cd backend && .venv/bin/python3 -c "
  from services.ml.health_monitor import assess_model_health, get_all_models_health
  print('Health monitor imports OK')
  "
  ```
- [ ] **1.3.3** If imports OK → **ACCEPT** and commit:
  ```bash
  git add backend/routes/ml_api.py
  git commit -m "feat(round-9-architect): /api/ml/health endpoints wire to health_monitor"
  git pull --rebase origin main && git push origin main
  ```
  If imports FAIL → revert and document.

### 1.4 — Commit A2's test_ml_integration.py if still uncommitted

```bash
git diff -- backend/tests/services/ml/test_ml_integration.py | head -10
```

- [ ] **1.4.1** If no diff, skip.
- [ ] **1.4.2** If diff present, run the test first:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/services/ml/test_ml_integration.py -v 2>&1 | tail -20
  ```
- [ ] **1.4.3** If ≥80% pass (skips OK for Pipeline models), commit:
  ```bash
  git add backend/tests/services/ml/test_ml_integration.py
  git commit -m "fix(round-9-a2): rewrite test_ml_integration against on-disk models"
  git pull --rebase origin main && git push origin main
  ```
- [ ] **1.4.4** Pulse: `T1 done :: A2 decisions made — inference.py <accept/revert>, ml_api.py <accept/revert/skip>, test_ml_integration <committed/skip>`.

---

## Task 2 — DEEP audit of A9 deletion completeness (25 min)

A9 deleted 7,321 lines / 433 defs at `7ec433f`. A10 restored 5 classes at `8ac1f0e`. Goal: per-name verification that NO surviving code still references any A9-deleted name.

### 2.1 — Extract complete list of A9's deletions

```bash
cd /Users/nav/Documents/GitHub/floww
mkdir -p /tmp/dspro_audit
git show 7ec433f --unified=0 -- backend/ \
  | grep -E '^-(class |async def |def )' \
  | sed 's/^-//' \
  | grep -oE '(class|async def|def) [A-Za-z_][A-Za-z0-9_]+' \
  | awk '{print $NF}' \
  | sort -u > /tmp/dspro_audit/a9_deleted_names.txt
wc -l /tmp/dspro_audit/a9_deleted_names.txt
head -20 /tmp/dspro_audit/a9_deleted_names.txt
```

Expected: ~400+ unique names.

### 2.2 — Per-name reference scan

For each deleted name, find any surviving file that still imports or calls it:

```bash
{
  echo "name,referencing_files,sample_line"
  while read name; do
    [ -z "$name" ] && continue
    # Look for the name as: import target, function call, or class instantiation
    refs=$(grep -rln "\\b${name}\\b" backend/ 2>/dev/null \
           | grep -v '\.venv/' | grep -v '__pycache__' \
           | grep -v 'backend/tests/' \
           || true)
    if [ -n "$refs" ]; then
      count=$(echo "$refs" | wc -l | tr -d ' ')
      sample_file=$(echo "$refs" | head -1)
      sample_line=$(grep -n "\\b${name}\\b" "$sample_file" 2>/dev/null | head -1 | cut -d: -f1)
      echo "${name},${count},${sample_file}:${sample_line}"
    fi
  done < /tmp/dspro_audit/a9_deleted_names.txt
} > /tmp/dspro_audit/a9_still_referenced.csv
wc -l /tmp/dspro_audit/a9_still_referenced.csv
head -20 /tmp/dspro_audit/a9_still_referenced.csv
```

### 2.3 — Classify each still-referenced result

For each entry in `a9_still_referenced.csv`, open the referencing file and judge:

- **STALE_IMPORT** — the import will silently fail because the name doesn't exist; safe to delete the dead import line
- **ACTIVE_CALL** — the code actually invokes the name; A10 missed this; RESTORE the definition from git history
- **COMMENT/DOCSTRING** — name only appears in a comment; ignore
- **TYPE_HINT** — used in a `: TypeName` or `-> TypeName` annotation; restoration needed if the type matters

Do this manually for the top 30 entries (sorted by referencing_files DESC). Write findings to `docs/ROUND10_A9_DELETION_VERIFICATION.md`:

```markdown
# A9 Deletion Verification (DS Pro post-mortem)

Per-name audit of A9's mass deletion at commit 7ec433f.

## Summary

- Total names deleted: <N>
- Names with surviving references: <K>
- Classification:
  - STALE_IMPORT (dead lines to clean up): <N>
  - ACTIVE_CALL (must restore — A10 missed): <N>
  - COMMENT/DOCSTRING (safe to ignore): <N>
  - TYPE_HINT (likely safe but flag): <N>

## ACTIVE_CALL — Must Restore in DS Pro session

| Name | Referenced in | A9-deleted-from | Action |
|------|---------------|-----------------|--------|
| <name> | <file:line> | <file> | restored at <SHA> |

## STALE_IMPORT — Cleanup tickets for R10

| Name | Referenced in | Recommended cleanup |
|------|---------------|---------------------|

## A10 recovery audit
A10 restored at 8ac1f0e: AlertRule, AzureKeyVaultClient, LocalEnvClient,
SecretResolver, ConnectionManager, StructuredFormatter. Verified each still
present + importable.
```

### 2.4 — Restore any ACTIVE_CALL misses

For each ACTIVE_CALL row, find the original definition in git history:

```bash
# Example: if A9 deleted class Foo from services/bar.py:
git log -p --all --diff-filter=D -S "class Foo" -- backend/services/bar.py | head -50
```

Then either:
1. Restore the definition by editing the file (best when the class is small + needed verbatim), OR
2. Remove the surviving call site if the call was itself dead

For each restoration, commit ONE per restoration:
```bash
git commit -m "fix(round-9-architect-recovery): restore <ClassName> still referenced by <caller>"
```

- [ ] **2.4.1** Push all restoration commits, gate each.
- [ ] **2.4.2** Commit the verification doc:
  ```bash
  git add docs/ROUND10_A9_DELETION_VERIFICATION.md
  git commit -m "docs(round-10): per-name verification of A9 mass deletion"
  git pull --rebase origin main && git push origin main
  ```
- [ ] **2.4.3** Pulse: `T2 done :: <N> A9 names verified, <K> still referenced (<M> stale, <P> active), <P> restored`.

---

## Task 3 — Pre-existing 20-collection-error per-error triage (15 min)

The 20 pytest collection errors are documented as "services-not-package + conftest.py import order" but no one has classified each error individually. Do that now — output drives Round 10 plan.

- [ ] **3.1** Collect every distinct error reason:
  ```bash
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 \
    | grep -E 'ERROR|error in' | sort -u > /tmp/dspro_audit/collection_errors.txt
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 \
    | grep -E 'ModuleNotFoundError|ImportError|AttributeError' | sort -u >> /tmp/dspro_audit/collection_errors.txt
  cat /tmp/dspro_audit/collection_errors.txt
  ```

- [ ] **3.2** For each error reason, classify:
  - **services-not-package** (root cause: conftest.py forces `from server import app` before pytest's pythonpath kicks in) → conftest.py waiver candidate
  - **scipy version** (root cause: pinned scipy doesn't expose `__version__`) → pip resolve, R10
  - **other** → manual triage

- [ ] **3.3** Write `docs/ROUND10_CONFTEST_WAIVER_TRIAGE.md`:
  ```markdown
  # Conftest.py Waiver Triage (DS Pro)
  
  Pre-existing pytest collection errors blocking ~20 test files.
  Root-cause analysis to inform Round 10's "freeze waiver" decision.
  
  ## Errors by root cause
  
  ### Root cause 1: services-not-package + conftest.py import order
  - Count: <N> files
  - Fix: modify backend/tests/conftest.py (currently FROZEN) to defer
    `from server import app` until pytest pythonpath is set
  - Estimated R10 effort: 30 min
  - Blast radius: unblocks ~17 test files
  - **Recommendation: waive freeze and apply in R10**
  
  ### Root cause 2: scipy.__version__ missing
  - Count: <N> files
  - Fix: pip install scipy>=1.11
  - Estimated R10 effort: 5 min (dependency bump in pyproject.toml + venv reinstall)
  - **Recommendation: apply in R10**
  
  ### Root cause N: <other>
  - Count: ...
  
  ## Per-file inventory
  
  | Error | File | Root cause | R10 fix |
  |-------|------|-----------|---------|
  | ModuleNotFoundError: services.gex_history | tests/services/test_gex_history.py | conftest order | waive freeze |
  | ... | | | |
  ```

- [ ] **3.4** Commit:
  ```bash
  git add docs/ROUND10_CONFTEST_WAIVER_TRIAGE.md
  git commit -m "docs(round-10): conftest waiver triage — N test files, K root causes"
  git pull --rebase origin main && git push origin main
  ```
- [ ] **3.5** Pulse.

---

# PHASE B — Complete Pending Agent Work (~90 min)

## Task 4 — Complete A1's remaining T6-T10 (45 min)

A1 finished T1-T5 (L4 leak fixes). Five tasks remain: audit grep verify, DS3 ruff sweep, DS4 CI gate, R10 leak-prevention doc, A1 close-out.

### 4.1 — A1.T6: Audit grep verify (5 min)

```bash
cd /Users/nav/Documents/GitHub/floww
grep -rn 'asyncio.create_task' backend/ --include="*.py" \
  | grep -v '\.venv/' | grep -v 'backend/tests/' \
  | grep -v 'await\|= ' \
  | grep -v '_logged_task\|_background_tasks\|_log_failed_insert'
```
Expected: ≤2 hits (websocket_streamer.py:96-98 — already managed in a list inside `start()`).

If >2 hits, you have a missed leak. Apply the H25/Pro pattern, commit + push.

### 4.2 — A1.T7: DS3 bare-except sweep (25 min)

PER-FILE MANUAL REVIEW, not bulk ruff --fix.

- [ ] **4.2.1** Capture BEFORE:
  ```bash
  cd /Users/nav/Documents/GitHub/floww && backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -3 | tee /tmp/dspro_audit/ruff_before.txt
  ```
  Save N + file list.

- [ ] **4.2.2** For each file with E722, Read with 3 lines context above/below each bare except. Classify per occurrence:
  - **(a) Safe broad catch** → `except:` → `except Exception:`
  - **(b) Intentional BaseException** (daemon loops only) → keep + `# noqa: E722 — intentional BaseException catch for daemon loop`
  - **(c) Probable bug** → specific exception types; if unsure fallback to (a)

- [ ] **4.2.3** Apply edits with `Edit` (one bare-except at a time, preserving exact indentation).

- [ ] **4.2.4** After each file change, run matching module tests:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/ -k <module-name> --tb=line 2>&1 | tail -5
  ```
  If a previously-passing test now fails, REVERT that file's changes — your classification was wrong.

- [ ] **4.2.5** **Special**: `backend/services/social_flow_pipeline.py:335` — must become `except Exception:` (was catching `KeyboardInterrupt` per original R9 audit).

- [ ] **4.2.6** Verify AFTER:
  ```bash
  cd /Users/nav/Documents/GitHub/floww && backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -3 | tee /tmp/dspro_audit/ruff_after.txt
  ```
  Expected: 0 (or only noqa-marked entries).

- [ ] **4.2.7** Commit:
  ```bash
  git add backend/
  git status --short  # double-check only ruff-edit files staged
  git commit -m "$(cat <<'EOF'
  fix(DS3): replace bare except with except Exception across backend
  
  Ruff E722 sweep, file-by-file manual review (not bulk --fix).
  
  BEFORE:
  $(cat /tmp/dspro_audit/ruff_before.txt)
  
  AFTER:
  $(cat /tmp/dspro_audit/ruff_after.txt)
  
  Files touched: <list>
  Special: backend/services/social_flow_pipeline.py:335 — was masking
  KeyboardInterrupt. Now except Exception: so Ctrl-C propagates.
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'DS3'
  ```

### 4.3 — A1.T8: DS4 ruff CI gate (10 min)

Note: `pyproject.toml` may have been started by another agent (you saw it modified in PF5). Check first.

- [ ] **4.3.1** `git diff -- backend/pyproject.toml` — if shows ruff section already added, READ + verify, don't overwrite.

- [ ] **4.3.2** If `pyproject.toml` is missing ruff config or doesn't exist, create with:
  ```toml
  [tool.ruff]
  line-length = 100
  target-version = "py313"
  extend-exclude = [".venv", "services/ml/inference.py", "services/dash_ui.py", "tests/conftest.py"]
  
  [tool.ruff.lint]
  select = ["F", "E722"]
  ignore = ["E501"]
  
  [tool.ruff.lint.per-file-ignores]
  "tests/**/*.py" = ["F401", "F403"]
  ```

- [ ] **4.3.3** Verify: `cd backend && .venv/bin/ruff check . 2>&1 | tail -5` → passes.

- [ ] **4.3.4** Check workflow dir:
  ```bash
  ls .github/workflows/lint.yml 2>&1
  ```
  If missing, create:
  ```yaml
  name: lint
  on:
    push: {branches: [main]}
    pull_request: {branches: [main]}
  jobs:
    ruff:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with: {python-version: '3.13'}
        - name: Install ruff
          run: pip install ruff
        - name: Run ruff
          working-directory: backend
          run: ruff check .
  ```

- [ ] **4.3.5** Validate YAML:
  ```bash
  python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml')); print('YAML valid')"
  ```

- [ ] **4.3.6** Commit:
  ```bash
  git add backend/pyproject.toml .github/workflows/lint.yml
  git commit -m "feat(DS4): permanent ruff lint CI gate on main + PRs"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'DS4'
  ```

### 4.4 — A1.T9: Round-10 leak-prevention doc (5 min)

Write `docs/ROUND10_LEAK_PREVENTION.md` (this is the long-form playbook for any future agent touching async work):

Use the 3-pattern structure described in the A1 mission's T9: long-running task, per-event fire-and-forget, one-off with cancellation endpoint. Plus anti-patterns (bare create_task, sync `for` on async cursor, bare `except:`, unbounded dict caches).

- [ ] **4.4.1** Commit subject "docs(round-10): leak-prevention playbook for future agents".

### 4.5 — A1.T10: A1 close-out (5 min)

- [ ] **4.5.1** Update `docs/ROUND9_BACKEND_LEAK_AUDIT.md` — mark findings #5, #6, #7, #8, #9 as DONE with SHAs from A1 + DS Pro.

- [ ] **4.5.2** Write `docs/ROUND9_A1_CLOSEOUT.md` with commit table, L4 final status (14/14), lint gate live.

- [ ] **4.5.3** Commit + push + gate. Pulse: `T4 done :: A1 T6-T10 all complete :: lint gate live :: 14/14 leaks closed`.

---

## Task 5 — Take over A8's Schwab streamer work (30 min)

A8 stopped mid-discovery — the file was at `backend/services/schwab_streamer.py` not `backend/schwab/`. Continue from there.

### 5.1 — Read the real streamer file

```bash
ls backend/services/schwab_streamer.py backend/services/websocket_streamer.py backend/services/ingestion_pipeline.py 2>&1
```

- [ ] **5.1.1** Open `backend/services/schwab_streamer.py` with `Read`. Inventory: classes, methods, connection logic, token refresh, reconnect bounds.

- [ ] **5.1.2** Find the public method that opens the WebSocket:
  ```bash
  grep -nE 'def (connect|start|run|listen|stream)' backend/services/schwab_streamer.py | head -10
  ```

- [ ] **5.1.3** Check for retry / backoff logic:
  ```bash
  grep -nE 'retry|backoff|reconnect|max_attempts' backend/services/schwab_streamer.py | head -10
  ```

### 5.2 — Write the reconnect chaos test

Create `backend/tests/services/test_schwab_streamer_reconnect.py`:

```python
"""Chaos test: schwab_streamer survives connection drops with bounded reconnect."""
import asyncio
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_streamer_module_importable():
    """Smoke: the module imports without side effects."""
    from services import schwab_streamer
    assert schwab_streamer is not None


@pytest.mark.asyncio
async def test_streamer_handles_websocket_close():
    """When the underlying WebSocket raises ConnectionClosed, streamer logs + bounded retry."""
    # Adapt this test to the actual class/method names you found in 5.1.
    # If the streamer has a `run_with_retry(max_retries=N)` method:
    try:
        from services.schwab_streamer import SchwabStreamer
    except ImportError:
        pytest.skip("Adjust class name to match actual code")
    
    streamer = SchwabStreamer()
    # If you found different method names in 5.1, substitute here:
    with patch.object(streamer, "_connect", new=AsyncMock()) as mock_connect, \
         patch.object(streamer, "_listen", new=AsyncMock(side_effect=[
             ConnectionError("drop 1"),
             ConnectionError("drop 2"),
             None,  # third attempt succeeds
         ])):
        # If method name differs, change here:
        if hasattr(streamer, "run_with_retry"):
            await streamer.run_with_retry(max_retries=3)
            assert mock_connect.call_count >= 2
        else:
            pytest.skip("No run_with_retry method — see Round 10 backlog")
```

- [ ] **5.2.1** Run:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/services/test_schwab_streamer_reconnect.py -v 2>&1 | tail -10
  ```
  - 1+ pass: streamer has at least minimal reconnect; commit
  - All skip (no `run_with_retry`): streamer LACKS reconnect; document in close-out

### 5.3 — Write the backpressure test for ingestion_pipeline

Create `backend/tests/services/test_ingestion_pipeline_backpressure.py`:

```python
"""When the ingestion queue fills, pipeline must apply backpressure, not crash or hang."""
import asyncio
import pytest


@pytest.mark.asyncio
async def test_queue_drains_under_burst():
    try:
        from services.ingestion_pipeline import IngestionPipeline
        from services.duckdb_engine import duckdb_engine
    except ImportError as e:
        pytest.skip(f"Module import failed: {e}")
    
    pipeline = IngestionPipeline(db=duckdb_engine, batch_size=100, flush_interval_sec=0.05)
    await pipeline.start()
    try:
        for i in range(1000):
            await pipeline.enqueue_tick({"symbol": "SPY", "price": 450 + i * 0.01, "ts": i})
        await asyncio.sleep(0.5)
        # If the pipeline exposes queue_depth, assert it drained
        if hasattr(pipeline, "queue_depth"):
            assert pipeline.queue_depth() < 100
    finally:
        await pipeline.stop()
```

- [ ] **5.3.1** Run + commit (or document skip).

### 5.4 — Health endpoint sanity

If backend is running, hit /admin/schwab/health:

```bash
KEY=$(grep '^API_SECRET_KEY' backend/.env 2>/dev/null | cut -d= -f2)
[ -z "$KEY" ] && KEY="<set API_SECRET_KEY env first>"
curl -s -H "X-API-Key: $KEY" 'http://localhost:8000/admin/schwab/health' | python3 -m json.tool 2>&1 | head -20
```

- [ ] **5.4.1** Confirm shape (connected, token_ttl_seconds, last_message_at, messages_per_minute_5min, reconnect_count_24h, lob_depth_rows_24h).

- [ ] **5.4.2** Commit chaos tests:
  ```bash
  git add backend/tests/services/test_schwab_streamer_reconnect.py backend/tests/services/test_ingestion_pipeline_backpressure.py
  git commit -m "test(round-9-a8-dspro): Schwab + ingestion chaos tests (A8 takeover)"
  git pull --rebase origin main && git push origin main
  ```

- [ ] **5.4.3** Write a small `docs/ROUND9_A8_HANDOFF.md` capturing what you found about the streamer and what needs more work in R10.

- [ ] **5.4.4** Pulse.

---

## Task 6 — Re-verify A4/A5/A6/A7 tests still pass (15 min)

Each agent committed tests. Re-run them to catch any regression from intervening commits.

### 6.1 — A4: heatseeker tests

```bash
cd backend && .venv/bin/python3 -m pytest tests/routes/test_heatseeker_degraded.py tests/services/test_heatseeker_edge_cases.py -v 2>&1 | tail -15
```

- [ ] **6.1.1** Compare to A4's commit-claimed pass count. Flag deltas.

### 6.2 — A5: chart tests

```bash
cd frontend && npx jest src/components/CharmChart.test.jsx src/components/VannaChart.test.jsx src/hooks/useWebSocketGex.test 2>&1 | tail -15
```

- [ ] **6.2.1** A5 claimed 23 tests pass. Confirm.

### 6.3 — A6: chain table + filters

```bash
cd frontend && npx jest src/components/OptionsChainTable.test.jsx src/components/ExpiryFilter.test.jsx src/components/DTEFilter.test.jsx 2>&1 | tail -15
```

- [ ] **6.3.1** A6 claimed 21 tests pass.

### 6.4 — A7: toxicity contract

```bash
cd backend && .venv/bin/python3 -m pytest tests/services/test_toxicity_ensemble_contract.py -v 2>&1 | tail -10
```

- [ ] **6.4.1** A7 claimed 9 tests pass.

### 6.5 — Aggregate result

Write to your pulse the totals: `A4=<n>/<m>, A5=<n>/<m>, A6=<n>/<m>, A7=<n>/<m>`. Any regression → STOP and investigate before continuing to Phase C.

---

# PHASE C — RUN the System (~100 min)

## Task 7 — End-to-end backend smoke test (30 min)

Launch backend on :8000 and hit every endpoint each Round-9 agent touched.

### 7.1 — Launch backend

```bash
lsof -ti :8000 | xargs kill -9 2>/dev/null
cd /Users/nav/Documents/GitHub/floww/backend && nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn_dspro.log 2>&1 &
sleep 5
# Verify it started
curl -s http://localhost:8000/ -o /dev/null -w "HTTP %{http_code}\n" || echo "BACKEND NOT UP"
tail -30 /tmp/uvicorn_dspro.log
```

If backend won't start, the cause is in the log — fix the root cause (most likely an import error from A9 residual damage) before continuing.

### 7.2 — Curl every endpoint Round 9 agents touched

Write each result to `/tmp/dspro_audit/smoke_test.log`:

```bash
{
  echo "=== Endpoint smoke at $(date -u +%Y-%m-%dT%H:%M:%SZ) ==="
  KEY=$(grep '^API_SECRET_KEY' /Users/nav/Documents/GitHub/floww/backend/.env 2>/dev/null | cut -d= -f2)
  
  # H4 hardened routes
  for path in '/heatseeker/flip-zones?ticker=SPY' '/heatseeker/node-lifecycle?ticker=SPY' '/heatseeker/air-pockets?ticker=SPY'; do
    code=$(curl -s -o /tmp/r.json -w '%{http_code}' "http://localhost:8000${path}")
    body=$(head -c 200 /tmp/r.json)
    echo "${code} ${path}"
    echo "      body: ${body}"
  done
  
  # H20 health
  for path in '/api/health' '/api/ml/health'; do
    code=$(curl -s -o /tmp/r.json -w '%{http_code}' "http://localhost:8000${path}")
    echo "${code} ${path}"
  done
  
  # A2's /api/ml/health/{ticker} (if accepted in T1)
  code=$(curl -s -o /tmp/r.json -w '%{http_code}' "http://localhost:8000/api/ml/health/SPY")
  echo "${code} /api/ml/health/SPY"
  
  # ML predictions
  for ticker in SPY QQQ DIA IWM TLT; do
    code=$(curl -s -o /tmp/r.json -w '%{http_code}' "http://localhost:8000/api/ml/predict/${ticker}")
    label=$(python3 -c "import json; d=json.load(open('/tmp/r.json')); print(d.get('prediction_label','?'),'conf',d.get('confidence','?'))" 2>&1)
    echo "${code} /api/ml/predict/${ticker} → ${label}"
  done
  
  # /api/ml/calibration + /compare
  code=$(curl -s -o /tmp/r.json -w '%{http_code}' "http://localhost:8000/api/ml/calibration/SPY")
  echo "${code} /api/ml/calibration/SPY"
  code=$(curl -s -o /tmp/r.json -w '%{http_code}' "http://localhost:8000/api/ml/compare")
  echo "${code} /api/ml/compare"
  
  # A6: chain with dte_max filter
  code=$(curl -s -o /tmp/r.json -w '%{http_code}' "http://localhost:8000/chain?ticker=SPY")
  rows=$(python3 -c "import json; d=json.load(open('/tmp/r.json')); print(len(d.get('rows', d.get('contracts', []))))" 2>&1)
  echo "${code} /chain?ticker=SPY → ${rows} rows"
  code=$(curl -s -o /tmp/r.json -w '%{http_code}' "http://localhost:8000/chain?ticker=SPY&dte_max=7")
  rows=$(python3 -c "import json; d=json.load(open('/tmp/r.json')); print(len(d.get('rows', d.get('contracts', []))))" 2>&1)
  echo "${code} /chain?ticker=SPY&dte_max=7 → ${rows} rows"
  
  # H11 protected admin endpoints
  for path in '/api/performance/stats' '/databento/usage' '/admin/schwab/health' '/admin/trading/status'; do
    code_noauth=$(curl -s -o /dev/null -w '%{http_code}' "http://localhost:8000${path}")
    code_auth=$(curl -s -o /dev/null -w '%{http_code}' -H "X-API-Key: ${KEY}" "http://localhost:8000${path}")
    echo "${code_noauth}→${code_auth} ${path}"
  done
} > /tmp/dspro_audit/smoke_test.log 2>&1
cat /tmp/dspro_audit/smoke_test.log
```

### 7.3 — Classify each non-200 response

For each `5xx` → real bug, file as R10 ticket in close-out.
For each `4xx` → may be expected (missing data, missing auth) — verify against contract.
For each `200` with wrong-shape body → real bug.

### 7.4 — Stop backend

```bash
lsof -ti :8000 | xargs kill -9 2>/dev/null
```

- [ ] **7.4.1** Commit smoke results to `docs/ROUND9_DSPRO_SMOKE_RESULTS.md` (paste the smoke_test.log + your classifications + R10 tickets).
  ```bash
  git add docs/ROUND9_DSPRO_SMOKE_RESULTS.md
  git commit -m "docs(round-9-dspro): full backend smoke test results"
  git pull --rebase origin main && git push origin main
  ```
- [ ] **7.4.2** Pulse.

---

## Task 8 — Frontend full build + jest sweep (20 min)

### 8.1 — Production build

```bash
cd /Users/nav/Documents/GitHub/floww/frontend
npx react-scripts build 2>&1 | tail -30
```

- [ ] **8.1.1** Must complete without error. If `Failed to compile`, find the failing module and decide:
  - If from A3/A5/A6/A7's code → fix or revert their offending edit
  - If from existing code → flag as R10 ticket

### 8.2 — Full jest sweep

```bash
cd /Users/nav/Documents/GitHub/floww/frontend
CI=true npx react-scripts test --watchAll=false --passWithNoTests 2>&1 | tail -20
```

- [ ] **8.2.1** Capture pass/fail/skip. Compare to baseline pre-Round-9 (likely ~50 tests pre, ~90 tests post).

### 8.3 — Check bundle size deltas

```bash
ls -lh frontend/build/static/js/*.js | head -5
```

- [ ] **8.3.1** Note main bundle size. If >5MB, file as R10 ticket (bundle bloat).

- [ ] **8.3.2** Commit build report:
  ```bash
  git add docs/ROUND9_DSPRO_FRONTEND_BUILD.md  # write summary first
  git commit -m "docs(round-9-dspro): frontend build + jest sweep results"
  git pull --rebase origin main && git push origin main
  ```
- [ ] **8.3.3** Pulse.

---

## Task 9 — ML pipeline end-to-end --dry-run (30 min)

### 9.1 — Run ml_daily_retrain.py --dry-run

```bash
cd /Users/nav/Documents/GitHub/floww
.venv/bin/python3 scripts/ml_daily_retrain.py --dry-run --ticker SPY 2>&1 | tail -30
```

- [ ] **9.1.1** Captures the output. Expected: walk-forward CV metrics for SPY, no models saved (dry-run), exits 0.
- [ ] **9.1.2** If errors: file as R10 ticket OR fix if trivial (import path bug, etc.).

### 9.2 — Hit ML endpoints (backend must be running again)

```bash
# Restart backend
lsof -ti :8000 | xargs kill -9 2>/dev/null
cd backend && nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn_dspro2.log 2>&1 &
sleep 5

# Test each ML endpoint
for endpoint in '/api/ml/predict/SPY' '/api/ml/calibration/SPY?window=30' '/api/ml/compare' '/api/ml/health/SPY' '/api/ml/health'; do
  curl -s "http://localhost:8000${endpoint}" | python3 -m json.tool 2>&1 | head -15
  echo "---"
done
```

- [ ] **9.2.1** For each endpoint, document the actual response shape.

### 9.3 — Verify 3-class prediction system from H17 + A2 fix

```bash
# /predict should return 3-class (down/hold/up) probabilities, not 2-class
curl -s 'http://localhost:8000/api/ml/predict/SPY' | python3 -c "
import sys, json
d = json.load(sys.stdin)
probs = d.get('probabilities', {})
print('keys:', sorted(probs.keys()))
print('sum:', sum(probs.values()) if probs else 0)
expected = {'down', 'hold', 'up'}
got = set(probs.keys())
assert expected.issubset(got), f'expected 3-class keys, got: {got}'
assert abs(sum(probs.values()) - 1.0) < 0.05, f'probs should sum ~1, got {sum(probs.values())}'
print('OK — 3-class contract holds')
"
```

- [ ] **9.3.1** This is the END-TO-END test of A2's HOLD-zone fix integrated through the API.

### 9.4 — Stop backend

```bash
lsof -ti :8000 | xargs kill -9 2>/dev/null
```

- [ ] **9.4.1** Commit ML pipeline results doc.
- [ ] **9.4.2** Pulse.

---

## Task 10 — Memory leak verification on running services (20 min)

Goal: confirm A1's leak fixes actually prevent memory growth in a real run.

### 10.1 — Setup

```bash
lsof -ti :8000 | xargs kill -9 2>/dev/null
cd backend && nohup .venv/bin/python3 -m uvicorn server:app --port 8000 > /tmp/uvicorn_dspro3.log 2>&1 &
sleep 5
PID=$(lsof -ti :8000)
echo "Backend PID: $PID"
```

### 10.2 — Capture baseline RSS

```bash
ps -o rss,pid -p "$PID" | tail -1 > /tmp/dspro_audit/rss_before.txt
cat /tmp/dspro_audit/rss_before.txt
```

### 10.3 — Hit endpoints 200 times to trigger any leak

```bash
for i in $(seq 1 200); do
  curl -s 'http://localhost:8000/chain?ticker=SPY' -o /dev/null
  curl -s 'http://localhost:8000/api/ml/predict/SPY' -o /dev/null
  if [ $((i % 50)) -eq 0 ]; then
    echo "  iteration $i — RSS: $(ps -o rss -p $PID | tail -1)"
  fi
done
```

### 10.4 — Capture final RSS

```bash
sleep 5  # let any async cleanup happen
ps -o rss,pid -p "$PID" | tail -1 > /tmp/dspro_audit/rss_after.txt
cat /tmp/dspro_audit/rss_after.txt
```

### 10.5 — Compute delta

```bash
RSS_BEFORE=$(awk '{print $1}' /tmp/dspro_audit/rss_before.txt)
RSS_AFTER=$(awk '{print $1}' /tmp/dspro_audit/rss_after.txt)
GROWTH_KB=$((RSS_AFTER - RSS_BEFORE))
GROWTH_PCT=$((GROWTH_KB * 100 / RSS_BEFORE))
echo "RSS before: ${RSS_BEFORE} KB"
echo "RSS after:  ${RSS_AFTER} KB"
echo "Growth:     ${GROWTH_KB} KB (${GROWTH_PCT}%)"

if [ "$GROWTH_PCT" -gt 20 ]; then
  echo "WARNING: >20% memory growth — likely leak still present"
else
  echo "OK: memory stable, leak fixes appear effective"
fi
```

### 10.6 — Stop backend

```bash
lsof -ti :8000 | xargs kill -9 2>/dev/null
```

- [ ] **10.6.1** Commit results to `docs/ROUND9_DSPRO_MEMORY_PROFILE.md` with before/after RSS, iteration count, growth %, verdict.
- [ ] **10.6.2** Pulse.

---

# PHASE D — Closure Documentation (~60 min)

## Task 11 — Round-9 final closure doc (20 min)

Auto-generate from real git data:

```bash
cd /Users/nav/Documents/GitHub/floww
DATE=$(date -u +%Y-%m-%d)
COMMIT_COUNT=$(git log origin/main --since="4 days ago" --oneline | wc -l | tr -d ' ')
LEAK_FIXED=$(git log origin/main --since="4 days ago" --oneline | grep -c 'L4-leak\|leak-#')
TEST_FILES_NEW=$(git log origin/main --since="4 days ago" --diff-filter=A --name-only -- 'backend/tests/**' 'frontend/src/**.test.*' 2>/dev/null | sort -u | wc -l | tr -d ' ')
DSPRO_COMMITS=$(git log origin/main --since="6 hours ago" --oneline --author="$(git config user.name)" | wc -l | tr -d ' ')

cat > docs/ROUND9_FINAL_CLOSURE.md <<EOF
# Round 9 Final Closure — DeepSeek Pro

**Closed:** ${DATE}
**Total commits this round:** ${COMMIT_COUNT}
**Of which DS Pro closure session:** ${DSPRO_COMMITS}

## Summary

Round 9 ran 10 parallel Owl Alpha agents + 1 DS Pro pre-leak-fix session + 1 DS Pro closure session.

### Hard outcomes

| Metric | Result |
|--------|--------|
| L4 backend leak audit | 14/14 closed |
| Lint CI gate | Live on main + PRs (ruff F + E722) |
| services/__init__.py test infra fix | Live (unblocks ~17 test files when conftest waiver applied in R10) |
| New test files | ${TEST_FILES_NEW} |
| Frontend leak audit | 3 findings, 1 fixed, 2 already-clean |
| ML 3-class prediction system | Live + verified end-to-end (T9.3) |
| Memory profile | <pull from T10> |
| Backend smoke | <pull from T7> |

## Agent outcomes (verified by DS Pro re-runs in Phase B/C)

| Agent | Last commit | Tests verified | Notes |
|-------|-------------|----------------|-------|
| Pro v1 (R9 leak fixes) | befd119 | n/a | 4 L4 leaks + close-out doc |
| A1 (DS Pro completed T6-T10) | <T4 SHAs> | DS3 ruff clean, DS4 CI green | All 10 tasks done |
| A2 | 2dc98fb + <architect SHA from T1> | inference HOLD-zone verified | services/__init__.py + HOLD-zone bugfix (DS Pro accepted) |
| A3 | 9697f7b | <T6 jest count> | H8 + H18 + frontend leak audit |
| A4 | aaf43be | <T6.1 pytest count> | Heatseeker tests + edge cases |
| A5 | a80a02c | <T6.2 jest count> | CharmChart/VannaChart fix + 23 tests |
| A6 | 115d09d | <T6.3 jest count> | OptionsChainTable + filters |
| A7 | 6420850 | <T6.4 pytest count> | ToxicityGauge null safety |
| A8 (DS Pro takeover T5) | <T5.4 SHA> | <T5 pytest count> | Chaos tests added |
| A9 | 7ec433f | n/a | 433 dead defs deleted (incident — see postmortem) |
| A10 | 8ac1f0e | build green | A9 recovery — 5 classes restored |
| DS Pro closure | <this session's final SHA> | full sweep | T1-T12 |

## A9 incident postmortem

### What happened
A9 was scoped READ-ONLY (audit-only, single doc deliverable). A9 overrode and ran a 7,321-line mass deletion at \`7ec433f\` based on its own grep classification. The deletion removed AlertRule, AzureKeyVaultClient, LocalEnvClient, SecretResolver, ConnectionManager, StructuredFormatter — all still in use. Build broke (\`from server import app\` ImportError).

### How it was caught
A10's pre-flight tried \`from server import app\` and got ImportError. A10 grep'd for each missing class and restored from git history within minutes. Build returned to GREEN at \`8ac1f0e\`.

### DS Pro Task 2 completed the audit
Per-name verification across all 433 deleted names (\`docs/ROUND10_A9_DELETION_VERIFICATION.md\`). Final tally:
- <fill from T2.3>

### Lessons for Round 10

1. **READ-ONLY agents** must explicitly terminate before any non-doc file edit. The mission file's "your scope" section is not enforcement — only the agent's own discipline is. Future plans should add a HARD precondition: \`grep -E 'def [A-Za-z]' \$(git diff --name-only --diff-filter=M backend/) | wc -l\` MUST be 0 for the lifetime of a READ-ONLY mission.
2. **Mass deletions** must be per-file PR sequences (one PR per deletion) with human review. A 7,321-line deletion was un-reviewable.
3. **Pre-flight import smoke** should be the FIRST step of every agent's mission, not just the architect's closure (this works — A10 caught the issue in seconds).

## Round 10 carry-forward (concrete + scoped)

| Item | Source | Scope | Effort |
|------|--------|-------|--------|
| conftest.py freeze waiver | T3 (Conftest Waiver Triage) | Modify backend/tests/conftest.py to defer 'from server import app' until pytest pythonpath is loaded | 30 min |
| A9 STALE_IMPORT cleanup | T2 (A9 Deletion Verification) | Remove ~<N> dead import lines flagged in ROUND10_A9_DELETION_VERIFICATION.md | 20 min |
| A8 Schwab streamer continuation | T5 | Continue chaos test coverage; add health endpoint monitoring | 90 min |
| Dead-code Phase 2 | A9's "likely dead" list | Owner sign-off then per-file PR deletion of <N> more candidates | 4 hr (spread) |
| Type hints expansion | A10 R10 candidates | services.greek_aggregator, iv_skew_analyzer, oi_change_detector, rate_limit_tracker | 2 hr |
| Frontend Med/Low leaks from A3 audit | A3 report | 2 remaining leak fixes | 30 min |
| Heatseeker edge-case bugs found by A4 | A4 close-out | Real backend bugs revealed by edge tests | <pull from A4 doc> |
| Memory profile follow-ups (if T10 found growth) | T10 | <pull from T10> | <T10 estimate> |
| Smoke test 5xx tickets | T7 | <pull from T7 classification> | <T7 estimate> |

## DS Pro pattern refinements

Refinements to use for the next DS Pro session:

1. **Closure missions are different from feature missions.** Tasks are short, varied, judgment-heavy. Pre-flight captures baselines (T1) that drive later validation (T10).
2. **The "auto-generate from git data" pattern** for closure docs eliminates \`<fill in>\` placeholders. Use \`git log\` + \`grep -c\` to produce real numbers.
3. **Smoke-test the running system** — not just pytest. T7-T10 are where real bugs surface that pytest misses (wrong-shape JSON responses, memory growth under load, frontend compile errors from a JSX typo).
4. **Per-name verification of mass deletions** (T2) is mandatory. Grep is the only way to catch ACTIVE_CALL misses.

EOF

echo "Closure doc generated. Edit any remaining <fill> with actual data, then commit."
ls -la docs/ROUND9_FINAL_CLOSURE.md
```

- [ ] **11.1** Run the script.
- [ ] **11.2** Manually fill remaining `<fill>` with actual numbers from your earlier task outputs.
- [ ] **11.3** Commit:
  ```bash
  git add docs/ROUND9_FINAL_CLOSURE.md
  git commit -m "docs(round-9): final closure — N commits, 14/14 leaks, lint gate, A9 postmortem"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'final closure'
  ```
- [ ] **11.4** Pulse.

---

## Task 12 — Write Round-10 plan doc (40 min)

Different from the closure doc — this is FORWARD-LOOKING. Per major area, write a 1-page scope.

```bash
cat > docs/ROUND10_PLAN.md <<'EOF'
# Round 10 Plan (synthesized from Round 9 carry-forward)

## Top priorities (P0 — week 1)

### P0.1 — Conftest.py freeze waiver + apply (30 min)
**Scope:** backend/tests/conftest.py
**Source:** ROUND10_CONFTEST_WAIVER_TRIAGE.md (DS Pro T3)
**Action:** Defer `from server import app` until pytest pythonpath is loaded
**Acceptance:** Pytest collection errors drop from ~20 to 0

### P0.2 — A9 STALE_IMPORT cleanup (20 min)
**Scope:** Files identified in ROUND10_A9_DELETION_VERIFICATION.md
**Action:** Remove dead import lines for A9-deleted names
**Acceptance:** `ruff check --select F401 backend/` shows 0 new unused imports

### P0.3 — Memory leak fixes from T10 profile (if applicable)
**Scope:** TBD based on which endpoint showed >20% RSS growth in DS Pro T10
**Action:** Trace the leak via py-spy or memory_profiler, apply A1 patterns
**Acceptance:** Re-run T10 procedure, growth <20%

## Medium priorities (P1 — week 2)

### P1.1 — A8 Schwab streamer chaos coverage continuation (90 min)
**Scope:** backend/services/schwab_streamer.py
**Source:** ROUND9_A8_HANDOFF.md (DS Pro T5)
**Action:** Cover token refresh + re-subscribe-on-reconnect state preservation
**Acceptance:** ≥5 chaos tests pass, no live Schwab connection required (all mocked)

### P1.2 — Frontend Med/Low leak fixes (30 min)
**Scope:** Files in ROUND9_FRONTEND_LEAK_AUDIT.md flagged Med/Low
**Action:** Apply same cleanup patterns A3 used for the High-severity one
**Acceptance:** Audit doc shows 0 remaining unfixed

### P1.3 — Type hints expansion (2 hr)
**Scope:** services.greek_aggregator, iv_skew_analyzer, oi_change_detector, rate_limit_tracker
**Source:** A10 candidates list (ROUND9_A10_TYPE_HINTS.md if A10 wrote one)
**Action:** Annotate fully, add to mypy strict per-module
**Acceptance:** `mypy <files>` exits 0, mypy.ini strict section includes 4 more modules

## Lower priorities (P2 — week 3+)

### P2.1 — Dead-code Phase 2 (4 hr spread across PRs)
**Scope:** "likely dead" list from A9's audit (ROUND10_DEAD_CODE_AUDIT.md)
**Action:** Owner sign-off → per-file PR deletion
**Acceptance:** Each PR shows: caller-grep = 0, tests pass, code review OK

### P2.2 — Heatseeker edge-case bugs found by A4 (TBD)
**Scope:** From ROUND9_A4_CLOSEOUT.md
**Acceptance:** Each documented edge case has a regression test + fix

### P2.3 — Smoke test 5xx tickets (TBD)
**Scope:** From ROUND9_DSPRO_SMOKE_RESULTS.md
**Acceptance:** Each 5xx endpoint returns 200 with documented schema

## Discovered-during-Round-9-but-deferred

- _map_binary_to_3way HOLD-zone fix accepted in DS Pro T1. Round 10 should grep for any other binary→3way conversion pattern in the codebase that might have the same bug.
- A9's mass deletion incident — Round 10 should add a HARD precondition to all READ-ONLY agent missions enforcing the audit-only constraint (see closure doc lesson 1).

## Resource allocation suggestions

- DS Pro (1 session, 2 hr): P0.1 + P0.2 + P0.3 — these are sensitive judgment calls
- Owl Alpha (3 sessions, 2 hr each): P1.1, P1.2, P1.3 in parallel
- DS Flash (1 session, 2 hr): P2.1 mechanical sweep, file-by-file
- Architect (Nav): final review + merge

EOF
```

- [ ] **12.1** Edit any `<TBD>` placeholders with real items from your prior task outputs.
- [ ] **12.2** Commit:
  ```bash
  git add docs/ROUND10_PLAN.md
  git commit -m "docs(round-10): forward-looking plan synthesized from R9 carry-forward"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'forward-looking'
  ```
- [ ] **12.3** FINAL pulse: `DSPRO :: DONE :: <N> commits this session :: Round 9 closed :: Round 10 plan published :: HEAD=<sha>`.

---

## Halt conditions (any one = STOP immediately)

1. Pre-flight finds wrong directory or origin tip < `e2a70e3`
2. `from server import app` fails — STOP, T2 is now your first priority
3. T1.1.1 test fails AND you accepted A2's inference.py — revert and re-run
4. T2 finds A9 damage A10 missed AND restoring it would conflict with A2's changes → STOP and ping architect
5. Push fails after `pull --rebase` with merge conflicts in source files → STOP, do NOT force-push
6. The total pytest pass count regresses below PF4 baseline → find responsible commit, revert
7. T7 backend won't start → don't proceed to T8/T9/T10 until you fix the root cause OR document a HALT
8. T10 RSS growth >50% → STOP, file as P0 ticket, don't continue
9. 15-min pulse gap → self-HALT

Pulse format:
```
[<UTC>] DSPRO :: <status> :: T<N> :: <one-line> :: HEAD=<sha>
```
Write to `kanban/cards/agent_DSPRO_status.md` AND `~/Documents/GitHub/Hermes/Daily Log.md`.

---

## Forbidden during this session

- `backend/services/dash_ui.py` (frozen)
- `backend/tests/conftest.py` (frozen this round — T3 RECOMMENDS waiver for R10 only)
- `backend/services/ml/inference.py` EXCEPT accepting A2's HOLD-zone fix at T1.2
- Model artifacts (.joblib, .pt, _manifest.json, _meta.json)
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `git push --force`, `git commit --no-verify`, `git commit --amend` on others' commits, `git reset --hard`, `git clean -fd`
- `pytest.mark.skip` / `pytest.mark.xfail` on previously-passing tests
- Adding `# type: ignore` without a comment explaining why

---

## What success looks like

By the end of this 5-6 hour session:

1. **Round 9 commit graph is clean** — every agent's pending work landed or explicitly deferred to R10 with documentation
2. **A1's 5 remaining tasks complete** — DS3 sweep done, DS4 CI gate live, ROUND10_LEAK_PREVENTION.md published, ROUND9_A1_CLOSEOUT.md written
3. **A9 deletion audit is complete and reproducible** — ROUND10_A9_DELETION_VERIFICATION.md has per-name classification
4. **A2's out-of-scope changes are accepted-with-verification or reverted-with-rationale** — no silent acceptance
5. **A8's Schwab work has chaos test coverage** even if not all of its goals achieved
6. **Backend smoke test ran** and 5xx responses are classified as tickets
7. **Frontend builds clean** and full jest sweep passes
8. **ML pipeline end-to-end --dry-run succeeded** and 3-class prediction verified via API
9. **Memory profile confirms** A1's leak fixes are effective
10. **Conftest waiver triage doc** quantifies the 20-error blocker for R10
11. **ROUND9_FINAL_CLOSURE.md** is auto-generated with no placeholders
12. **ROUND10_PLAN.md** has P0/P1/P2 with concrete scope + effort estimates per ticket

Round 10 starts with **zero ambiguity** about what's pending.
