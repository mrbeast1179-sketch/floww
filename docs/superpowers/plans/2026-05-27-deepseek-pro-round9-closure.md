# DeepSeek Pro — Round 9 Closure Mission (target: 2 hours)

> **For agentic workers:** Use superpowers:executing-plans. Steps use checkbox (`- [ ]`) syntax. This is a CLOSURE plan — you are not adding features. Your job is to land the in-flight work, verify damage, and lock the round closed.

**Goal:** Land the 10-Owl-Alpha session cleanly: commit A2 & A4's pending work, complete A1's last 5 tasks (DS3 ruff sweep + DS4 CI gate + Round-10 docs), verify A9's mass deletion didn't leave hidden damage A10 missed, push everything safely, write the Round-9 final closure doc.

**Architecture:** You hold context that no individual Owl Alpha can: the FULL 23-commit Round-9 history + A2's out-of-scope inference.py bugfix + A4's in-progress destructuring + A9's deletion damage map + A10's recovery scope. You make architect-level judgment calls (accept/reject A2's bugfix; decide which conftest.py exception to grant; decide on stuck-push conflict resolution) without needing to ping back.

**Tech Stack:** Python 3.13 · FastAPI · pytest · ruff · git (with pull --rebase + stash).

**Why this is YOU not another Owl Alpha:**
- Cross-agent context required (you read every other agent's close-out doc)
- Multiple architect-level judgment calls (out-of-scope acceptance, freeze waivers)
- Concurrent-modification race recovery (stuck pushes from A5, A10)
- Final closure doc must accurately reflect 30+ commits across 11 agents

---

## Pre-flight hard gates (do EVERY one — STOP on any failure)

- [ ] **PF1.** `pwd` ends in `/Users/nav/Documents/GitHub/floww`. Not `/Users/nav/GitHub/floww` (stale clone).
- [ ] **PF2.** Confirm origin is at `8ac1f0e` or later (A10's restoration commit):
  ```bash
  git fetch origin && git log origin/main --oneline -3
  ```
  Expected first line: `8ac1f0e fix(round-10): restore deleted classes + fix import breakages from A9 dead-code audit`. If older, the recovery wasn't pushed — STOP and HALT.
- [ ] **PF3.** Confirm build is GREEN:
  ```bash
  cd backend && .venv/bin/python3 -c "from server import app; print('OK')"
  ```
  Must print `OK`. If any ImportError, A9's damage is INCOMPLETE — go to Task 2 first.
- [ ] **PF4.** Capture baseline pytest:
  ```bash
  cd backend && .venv/bin/python3 -m pytest --collect-only -q 2>&1 | tail -3
  ```
  Save the "N tests collected, M errors" line. Expected: 2106+ collected, 20-23 errors (all pre-existing services-not-package).
- [ ] **PF5.** Note working tree state:
  ```bash
  git status --short
  ```
  Expected modified: `backend/routes/ml_api.py` (A2 added /health endpoints), `backend/services/ml/inference.py` (A2 real bugfix to HOLD zone), `backend/tests/services/ml/test_ml_integration.py` (A2 rewrite). Expected untracked: `backend/tests/services/test_heatseeker_edge_cases.py` (A4), `docs/ROUND9_A4_CLOSEOUT.md` (A4). Any OTHER unexpected files → STOP and reconcile first.

---

## Task 1 — Decide on A2's out-of-scope modifications (25 min)

A2 was scoped to `services/__init__.py`, `test_ml_integration.py`, `pytest.ini`, `test_services_is_package.py`. A2 ALSO modified `inference.py` (forbidden file) AND `ml_api.py` (A1's scope). Both modifications appear LEGITIMATE — but you must verify and decide.

### 1.1 — Read A2's inference.py change

```bash
git diff -- backend/services/ml/inference.py | head -50
```

The change fixes `_map_binary_to_3way()` — when confidence is weak (e.g., 0.45/0.55), it was returning UP/DOWN with non-normalized probabilities summing to ~1.9. The fix returns HOLD with probs normalized to sum=1. This is a real bug.

- [ ] **1.1** Verify the fix logic by writing a test BEFORE accepting the change:
  ```bash
  cat > /tmp/test_map_binary_hold.py <<'EOF'
  """Verify A2's inference.py HOLD-zone fix."""
  import sys
  sys.path.insert(0, "/Users/nav/Documents/GitHub/floww/backend")
  from services.ml.inference import _map_binary_to_3way, HOLD, STRONG_CONFIDENCE

  # Weak confidence: 55% up, 45% down → should be HOLD
  pred, probs = _map_binary_to_3way(prediction=1, proba=[0.45, 0.55])
  assert pred == HOLD, f"Expected HOLD, got {pred}"
  assert abs(sum(probs) - 1.0) < 0.01, f"Probs should sum to 1, got {sum(probs)}: {probs}"
  print(f"OK: pred={pred} probs={probs} sum={sum(probs):.4f}")

  # Strong UP
  pred, probs = _map_binary_to_3way(prediction=1, proba=[0.2, 0.8])
  print(f"Strong UP: pred={pred} probs={probs}")

  # Strong DOWN
  pred, probs = _map_binary_to_3way(prediction=0, proba=[0.85, 0.15])
  print(f"Strong DOWN: pred={pred} probs={probs}")
  EOF
  cd /Users/nav/Documents/GitHub/floww && backend/.venv/bin/python3 /tmp/test_map_binary_hold.py
  ```
  Expected: HOLD on weak confidence, probs sum to 1.

- [ ] **1.2** If the test passes → **ACCEPT** the inference.py change (architect override of the forbidden-file rule, because the fix is correct + tested). Move it to a commit with this exact subject:
  ```
  fix(round-9-architect): _map_binary_to_3way HOLD zone — correct prediction + normalized probs
  ```
  Commit body must INLINE the test output as proof.

- [ ] **1.3** If the test fails → **REVERT** A2's change to inference.py:
  ```bash
  git checkout -- backend/services/ml/inference.py
  ```
  And document in the closure doc that the bug remains for Round 10.

### 1.4 — Decide on A2's ml_api.py /health endpoints

```bash
git diff -- backend/routes/ml_api.py | head -60
```

A2 added `GET /api/ml/health/{ticker}` and `GET /api/ml/health` that wire to `services.ml.health_monitor` (which was created in an earlier round). Out of A2's scope (A1 owns ml_api.py file) but A1 isn't touching these endpoints and they're net-positive.

- [ ] **1.4** Verify the endpoints actually wire to the existing health_monitor:
  ```bash
  cd backend && .venv/bin/python3 -c "from services.ml.health_monitor import assess_model_health, get_all_models_health; print('imports OK')"
  ```
  If imports OK → **ACCEPT**. Stage and commit with subject:
  ```
  feat(round-9-architect): /api/ml/health endpoints wire to health_monitor
  ```
  If imports fail → REVERT this part of A2's diff:
  ```bash
  git checkout -- backend/routes/ml_api.py
  ```

### 1.5 — Commit A2's test_ml_integration.py rewrite

The rewrite was within A2's scope. Verify it doesn't break:
```bash
cd backend && .venv/bin/python3 -m pytest tests/services/ml/test_ml_integration.py -v 2>&1 | tail -15
```
- [ ] **1.5** If most pass (some skipped on Pipeline OK) → commit:
  ```
  fix(round-9-a2): rewrite test_ml_integration.py against on-disk models
  ```
- [ ] **1.6** If ≥3 fail with real reasons → **STOP and document** as Round 10 ticket; do NOT skip/xfail.

### 1.7 — Push the architect-decision commits + verify gates

```bash
git pull --rebase origin main
git push origin main
git fetch origin && git log origin/main --oneline -5
```

Each commit subject from 1.2 + 1.4 + 1.5 must appear on origin.

---

## Task 2 — Audit A9's deletion completeness (25 min)

A9 deleted 7,321 lines / 433 defs at `7ec433f`. A10 restored 5 classes at `8ac1f0e`. There may be MORE deletions that A10 missed but no test currently exercises.

### 2.1 — Find any other broken import in source

- [ ] **2.1** Grep for imports of names A9 may have deleted from across backend:
  ```bash
  # First, list every class/function A9 deleted
  cd /Users/nav/Documents/GitHub/floww
  git show 7ec433f --stat | tail -100 > /tmp/a9_files.txt
  git show 7ec433f --name-only | tail -100 > /tmp/a9_filenames.txt
  
  # For each deleted file, see what classes/functions were removed
  git show 7ec433f --unified=0 -- backend/ \
    | grep -E '^-(class |async def |def )' \
    | sed 's/^-//' \
    | grep -oE '(class|def) [A-Za-z_][A-Za-z0-9_]+' \
    | awk '{print $2}' \
    | sort -u > /tmp/a9_deleted_names.txt
  wc -l /tmp/a9_deleted_names.txt
  ```

- [ ] **2.2** For each deleted name, check if anything in current HEAD still imports/calls it:
  ```bash
  while read name; do
    [ -z "$name" ] && continue
    hits=$(grep -rln "\\b${name}\\b" backend/ 2>/dev/null \
           | grep -v '\.venv/' | grep -v '__pycache__' \
           | xargs grep -l "import\|from\|${name}(" 2>/dev/null | wc -l)
    if [ "$hits" -gt 0 ]; then
      echo "STILL_REFERENCED: $name ($hits files)"
    fi
  done < /tmp/a9_deleted_names.txt | head -30
  ```

- [ ] **2.3** For each `STILL_REFERENCED` result, open the referencing file and check whether the reference is:
  - **Dead/stale import** → safe (the import will silently fail; fix by removing the import line)
  - **Active call** → A10 missed this; restore from git history
  - **Comment/docstring** → ignore

- [ ] **2.4** For active calls A10 missed, restore from git history:
  ```bash
  # Find what file A9 deleted the class from
  git log -p --all --diff-filter=D -S "class MissingName" -- backend/ | head -50
  # Then either restore the class definition OR remove the call
  ```
  Per restoration, commit with subject:
  ```
  fix(round-9-architect-recovery): restore <ClassName> missed by A10
  ```

- [ ] **2.5** Pulse to `kanban/cards/agent_DSPRO_status.md`: `T2 done :: <N> A9 deletions still referenced, <M> restored`.

---

## Task 3 — Commit A4's pending files (10 min)

A4 produced `backend/tests/services/test_heatseeker_edge_cases.py` and `docs/ROUND9_A4_CLOSEOUT.md` but didn't commit before its session ended. Both are within A4's scope, both are net-positive.

- [ ] **3.1** Verify the test file runs:
  ```bash
  cd backend && .venv/bin/python3 -m pytest tests/services/test_heatseeker_edge_cases.py -v 2>&1 | tail -10
  ```

- [ ] **3.2** If passes (or skips with documented reason), commit both:
  ```bash
  git add backend/tests/services/test_heatseeker_edge_cases.py docs/ROUND9_A4_CLOSEOUT.md
  git commit -m "$(cat <<'EOF'
  test(round-9-a4-closeout): heatseeker edge cases + A4 closeout doc
  
  A4 left these uncommitted at session end. Both within A4's file ownership
  (services/heatseeker*.py + docs). Edge case tests:
  - calc_flip_zones with empty chain
  - calc_flip_zones with zero spot
  - calc_node_lifecycle with no history
  
  Verification:
  \$ cd backend && .venv/bin/python3 -m pytest tests/services/test_heatseeker_edge_cases.py -v 2>&1 | tail -1
  <PASTE ACTUAL PASS COUNT>
  EOF
  )"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'a4-closeout'
  ```

---

## Task 4 — Complete A1's remaining 5 tasks (45 min)

A1 finished T1-T5 (the 4 L4 leak fixes). T6-T10 remain. Execute them now.

### 4.1 — T6: Audit grep verify (5 min)

```bash
cd /Users/nav/Documents/GitHub/floww
grep -rn 'asyncio.create_task' backend/ --include="*.py" \
  | grep -v '\.venv/' | grep -v 'backend/tests/' \
  | grep -v 'await\|= ' \
  | grep -v '_logged_task\|_background_tasks\|_log_failed_insert'
```
Expected: ≤2 hits (`websocket_streamer.py:96-98` — already managed in a list inside `start()`).

If >2 hits, find the missed leak, apply the H25/Pro pattern, commit + push.

### 4.2 — T7: DS3 bare-except sweep (30 min)

Per-file MANUAL review (not bulk ruff --fix).

- [ ] **4.2.1** Install ruff: `backend/.venv/bin/ruff --version` (or `pip install ruff`).
- [ ] **4.2.2** Capture BEFORE:
  ```bash
  cd /Users/nav/Documents/GitHub/floww && backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -3
  ```
  Save N + file list.

- [ ] **4.2.3** For each file with E722, open with Read tool. For each bare `except:`:
  - 3 lines context above + below
  - Classify:
    - **(a) Safe** → `except:` → `except Exception:`
    - **(b) Intentional BaseException** (daemon loops only) → keep + `# noqa: E722 — intentional BaseException catch`
    - **(c) Probable bug** → specific exception types; if unsure fallback to (a)
  - Apply with Edit
  - After each file: run matching pytest module to confirm no regression

- [ ] **4.2.4** **Special**: `backend/services/social_flow_pipeline.py:335` — confirm it's now `except Exception:` (NOT bare). The original Round 9 plan flagged it for catching `KeyboardInterrupt` accidentally.

- [ ] **4.2.5** Re-check:
  ```bash
  cd /Users/nav/Documents/GitHub/floww && backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -3
  ```
  Expected: 0 (or only noqa-marked).

- [ ] **4.2.6** Commit with BEFORE/AFTER inline:
  ```
  fix(DS3): replace bare except with except Exception across backend
  ```

### 4.3 — T8: DS4 ruff config + CI gate (10 min)

- [ ] **4.3.1** `ls backend/pyproject.toml` — if exists, READ first (don't overwrite).
- [ ] **4.3.2** Create or extend `backend/pyproject.toml`:
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
- [ ] **4.3.4** Create `.github/workflows/lint.yml`:
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
- [ ] **4.3.5** Validate YAML: `python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml'))"`.
- [ ] **4.3.6** Commit + push + gate (subject contains `DS4`).

### 4.4 — T9: Round-10 leak-prevention doc (10 min)

Write `docs/ROUND10_LEAK_PREVENTION.md` with the 3 patterns synthesized from H25 + Pro + A1's work:

- **Pattern 1 — Long-running background task** (use `_background_tasks` + `_logged_task` from `server.py`)
- **Pattern 2 — Per-event fire-and-forget DB write** (use `_log_failed_insert` wrapper, do NOT register in `_background_tasks` — would explode under load)
- **Pattern 3 — One-off task with cancellation endpoint** (store ref on module/app state, cancel + await in matching `/stop` route)
- **Anti-patterns** (bare `create_task`, sync `for` on async cursor, bare `except:`, unbounded dict caches with no eviction)
- **Audit history table** (R9 L1: 14 found, 14 closed)

Commit with subject `docs(round-10): leak-prevention pattern reference`.

---

## Task 5 — Final pytest sweep + comparison (10 min)

- [ ] **5.1** Full run:
  ```bash
  cd backend && .venv/bin/python3 -m pytest -q --tb=no 2>&1 | tail -5
  ```
  Capture pass/fail/skip/error counts.

- [ ] **5.2** Compare to PF4 baseline. The delta should be:
  - +A2's new tests (3 in `test_services_is_package`)
  - +A4's new tests (`test_heatseeker_edge_cases` + `test_heatseeker_degraded`)
  - +DS Pro's chaos tests if A8 finished
  - 0 regressions

- [ ] **5.3** If regressions appear, find the responsible commit (likely A2's ml_api.py /health if you accepted them OR A9 residual damage), fix or revert.

---

## Task 6 — Write Round 9 final closure doc (15 min)

Auto-generate from real git data so there are no placeholders:

```bash
cd /Users/nav/Documents/GitHub/floww
DATE=$(date -u +%Y-%m-%d)

# Capture metrics
COMMIT_COUNT=$(git log origin/main --since="3 days ago" --oneline | wc -l)
LEAK_FIXED=$(git log origin/main --since="3 days ago" --oneline | grep -c 'L4-leak\|leak-#')
LINT_GATE=$(git log origin/main --since="3 days ago" --oneline | grep -c 'DS4\|lint gate')
TEST_DELTA_NEW=$(git log origin/main --since="3 days ago" --diff-filter=A --name-only -- 'backend/tests/**' | grep -c '_test\.py\|test_')

cat > docs/ROUND9_FINAL_CLOSURE.md <<EOF
# Round 9 Final Closure — DeepSeek Pro v2

**Closed:** ${DATE}

## Summary

- **Total commits:** ${COMMIT_COUNT} on origin/main in the past 72h
- **L4 leak fixes:** ${LEAK_FIXED} (audit closed 14/14)
- **Lint CI gate:** ${LINT_GATE} added (ruff F + E722)
- **New test files:** ${TEST_DELTA_NEW}

## Agent outcomes (each agent's last verified state)

| Agent | Last commit | Status | Notes |
|-------|-------------|--------|-------|
| Pro (R9 v1) | befd119 | DONE | 4 leak fixes + close-out |
| A1 | <fill from git log> | DONE (via DS Pro T4) | 5 leak fixes + DS3 + DS4 + R10 leak doc |
| A2 | 2dc98fb + architect commit | DONE | services/__init__.py + test rewrite + (DS Pro accepted) inference.py HOLD-zone fix + /health endpoints |
| A3 | 9697f7b | DONE | H8 + H18 + frontend leak audit (3 findings, 1 fixed) |
| A4 | 45f3e49 + DS Pro T3 commit | DONE | H4 regression test + heatseeker edge cases + close-out |
| A5 | 8aa8995 | DONE | CharmChart/VannaChart fix + tests |
| A6 | 115d09d | DONE | OptionsChainTable + ExpiryFilter + DTEFilter + backend dte_max |
| A7 | 6420850 | DONE | ToxicityGauge null safety + contract docs |
| A8 | <fill> | <fill> | Schwab streamer hardening — check status |
| A9 | 7ec433f | DONE-but-incident | 433 dead defs deleted; broke 4 classes |
| A10 | 8ac1f0e | DONE-recovery | Restored 4 broken classes; build green |
| DS Pro (R9 v2 closure) | <this session's final SHA> | DONE | Closure: A1 T6-T10 + A4 commits + A2 decisions + A9 audit + final doc |

## A9 incident postmortem

A9's prompt was READ-ONLY (audit-only, single doc deliverable). A9 overrode and ran a 7,321-line mass deletion. A10 surgically restored 4 broken classes. DS Pro Task 2 verified no additional damage remained.

**Lesson for Round 10:** READ-ONLY agents must terminate their session before any non-doc file edit. Mass deletions must be per-file PR sequences with human review.

## Round 10 carry-forward

- conftest.py import-order issue blocks 20 test files — needs architect freeze waiver
- A8's Schwab work may be incomplete — DS Pro to verify or queue for Round 10
- Type hints: 4 utility modules done (A10's plan); 4 more candidates queued
- Dead code: 433 deleted; the "likely dead" list from A9 audit needs owner sign-off before R10 deletion

## Files generated this round

- round9_followup_v2/_PREAMBLE.md + AGENT_A1.md..A10.md + _LAUNCHER.md (12 files, 3801 lines)
- docs/ROUND9_FRONTEND_LEAK_AUDIT.md
- docs/ROUND9_A{3,4,6,7}_CLOSEOUT.md
- docs/ROUND9_A7_TOXICITY_CONTRACT.md
- docs/ROUND10_DEAD_CODE_AUDIT.md (A9)
- docs/ROUND10_LEAK_PREVENTION.md (A1/DS Pro)
- docs/ROUND9_FINAL_CLOSURE.md (this doc)
EOF

# Fill any <fill> placeholders manually after inspecting git log
echo "Doc generated. Edit any remaining <fill> with the actual SHAs from:"
echo "git log origin/main --since='3 days ago' --oneline"
```

- [ ] **6.1** Run the script.
- [ ] **6.2** Edit any `<fill>` placeholders using the suggested git log.
- [ ] **6.3** Commit:
  ```bash
  git add docs/ROUND9_FINAL_CLOSURE.md
  git commit -m "docs(round-9): final closure — <N> commits, 14/14 leaks, lint gate, A9 postmortem"
  git pull --rebase origin main && git push origin main
  git fetch origin && git log origin/main --oneline -1 | grep 'final closure'
  ```

---

## Halt conditions (any one = STOP immediately)

1. Pre-flight finds origin not at 8ac1f0e+ (recovery not pushed) → STOP
2. `from server import app` fails → A10's recovery is incomplete; you MUST fix before any other task
3. Task 1.2 test fails AND you accepted A2's inference.py — revert and re-run
4. Task 2 finds A9 damage A10 missed AND restoring it would conflict with A2's changes → STOP and ping architect
5. Push fails after `pull --rebase` with merge conflicts in source files → STOP, do NOT force-push
6. The total pytest fail count regresses below baseline → find the responsible commit and revert
7. 15-min pulse gap → self-HALT

Pulse format:
```
[<UTC>] DSPRO :: in-progress :: T<N> :: <one-line> :: HEAD=<sha>
```
Write to `kanban/cards/agent_DSPRO_status.md` AND `~/Documents/GitHub/Hermes/Daily Log.md`.

---

## What success looks like

- Origin/main has ALL Round 9 work landed, no agent's work left uncommitted
- A2's HOLD-zone bug fix accepted (or explicitly deferred to R10 with documentation)
- A9's deletion damage fully audited and verified contained
- A1's 5 remaining tasks complete (T6 grep verify, T7 ruff sweep, T8 CI gate, T9 R10 leak doc, T10 close-out)
- Pytest sweep shows 0 regressions vs PF4 baseline (pre-existing collection errors are documented in close-out, not "fixed by hiding")
- `docs/ROUND9_FINAL_CLOSURE.md` accurately reflects all 30+ commits across 11 agents
- Round 10 carry-forward list is concrete and prioritized
