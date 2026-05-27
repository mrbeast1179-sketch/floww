# Hermes Owl Alpha — Agent H29 · DS3 Bare-Except Sweep + DS4 Lint CI Gate (~45 min)

You are Agent H29. You complete two pending sub-units from Round 9:
- **DS3**: Replace every bare `except:` in backend with `except Exception:` (ruff rule E722). DeepSeek Flash started this and was blocked by syntax errors that have since been fixed by the architect.
- **DS4**: Add a permanent ruff lint gate to CI so DS1/DS3-style regressions never silently land again.

**SEQUENCING — IMPORTANT:** This agent MUST run AFTER Agent H26 completes (H26 modifies `backend/server.py`, `backend/routes/replay.py`, `backend/services/paper_trader.py`, `backend/routes/ml_predict_api.py` — the same files your ruff sweep will touch). If H26's commits are not on origin yet, your pre-flight will catch it.

---

## Hard constraints

- **Canonical clone**: `/Users/nav/Documents/GitHub/floww`. **Not** the stale one.
- **Forbidden files**: same as other H-agents — see your H26 prompt for the full list. Special: ruff's `--fix` should NOT touch `backend/services/ml/inference.py`, `backend/services/dash_ui.py`, `backend/tests/conftest.py`. You will use a per-file exclude list.
- **No `--force`, `--no-verify`, `--amend` of others' commits, `--hard`, `clean -fd`.**
- **NEVER** mark a test xfail/skip. If a test fails after ruff's fix, the fix was wrong — revert your specific edit, leave the bare-except alone, and HALT for architect.
- **Each ruff `--fix` MUST be reviewed before commit**, not blind-committed. Ruff has been known to misjudge intent in tricky cases (e.g., catching `BaseException` because someone genuinely wanted to catch keyboard interrupt — your job is to verify case-by-case, not bulk-trust).
- **Origin gate after every commit.**
- **15-min pulse** to `kanban/cards/agent_H29_status.md`.

---

## Pre-flight (HARD GATE on H26)

- [ ] **PF1.** `pwd` ends in `/Users/nav/Documents/GitHub/floww`.

- [ ] **PF2.** Confirm H26 closure on origin (you depend on H26's file ownership):
  ```
  git fetch origin
  git log origin/main --oneline -15 | grep -E 'L4-leak-#5|L4-leak-#6|L4-leak-#7|L4-leak-#8'
  ```
  Expected: at least 3 of those 4 commits visible. **If fewer than 3 → STOP. H26 is not done. Wait or HALT.**

- [ ] **PF3.** Confirm working tree clean except for the known untracked test:
  ```
  git status --short
  ```
  Expected: only `?? backend/tests/services/ml/test_ml_integration.py`.

- [ ] **PF4.** Confirm ruff is installed in the project venv:
  ```
  backend/.venv/bin/ruff --version
  ```
  If "command not found": `backend/.venv/bin/pip install ruff` (this is allowed — ruff is a dev dependency).

- [ ] **PF5.** Capture BEFORE count of bare excepts:
  ```
  backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -3
  ```
  Save the number — paste in commit message later.

- [ ] **PF6.** Pulse:
  ```
  echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] H29 :: started :: pre-flight OK, ruff version <X>, bare-except count <N> :: HEAD=$(git rev-parse --short HEAD)" \
    >> kanban/cards/agent_H29_status.md
  ```

---

## Task 1: DS3 — Bare except sweep (20 min)

### T1.1 — Enumerate every site (do NOT bulk-fix yet)

```bash
backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | head -50
```

Save the file list. For EACH file with E722 hits, you will do steps T1.2–T1.5.

### T1.2 — Per-file review (manual eyeball, NOT bulk --fix)

For each file:
1. Open it with the Read tool. Read 3 lines above each bare `except:` and 3 below.
2. For each occurrence, decide:
   - **(a) Safe**: it's clearly intended to be a broad catch-all of normal exceptions (e.g., wrapping an optional DB lookup). Convert `except:` → `except Exception:`.
   - **(b) Needs `BaseException`**: the surrounding comments or code suggest the author specifically wanted to catch `KeyboardInterrupt` or `SystemExit` (rare; usually only in long-running daemon loops). KEEP the bare except but add a comment `# noqa: E722 — intentional catch of BaseException for daemon loop` so ruff stops flagging it.
   - **(c) BUG**: it's clearly catching too much because of laziness, and probably hiding errors. Convert to a specific exception type (e.g., `except (KeyError, ValueError):`). If you can't determine the right type without deeper code understanding, fall back to (a).

3. Pay extra attention to `backend/services/social_flow_pipeline.py:335` — the original Round 9 plan called this out specifically as a bare except that was catching `KeyboardInterrupt`. Verify the current state.

### T1.3 — Apply changes file-by-file

Use `Edit` (not bulk ruff --fix) so you can review each change. The edits are tiny:
- `except:` → `except Exception:`  (case (a))
- `except:  # noqa: E722 — intentional BaseException catch for daemon loop`  (case (b))
- `except (SomeType, OtherType):`  (case (c))

### T1.4 — Verify after each file

```bash
backend/.venv/bin/python3 -m pytest backend/tests/ -k <module-name> --tb=line 2>&1 | tail -5
```
Run the relevant module's tests after EACH file change. If a test that was passing now fails, you broke something — revert that one edit.

### T1.5 — Final ruff sweep

After all files reviewed:
```bash
backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -3
```
Expected: 0 errors (or only the files where you added `# noqa: E722` comments — those are intentional and should pass).

### T1.6 — Commit (single commit covers all files)

```bash
git add backend/
git status --short  # double-check only ruff-fix files staged
git commit -m "$(cat <<'EOF'
fix(DS3): replace bare except with except Exception across backend

Ruff E722 sweep. Each occurrence was reviewed individually rather than
bulk --fix, because some daemon loops genuinely want to catch
BaseException (KeyboardInterrupt). Those were preserved with a
`# noqa: E722` comment explaining intent.

BEFORE:
  $ backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -1
  Found <N> errors.

AFTER:
  $ backend/.venv/bin/ruff check --select E722 backend/ 2>&1 | tail -1
  All checks passed!

Files touched (review-by-review):
<paste list of files you edited>

Special: backend/services/social_flow_pipeline.py:335 — <how you handled it>.

Verification: relevant pytest module sweeps still green (no regressions).
EOF
)"
git push origin main
git fetch origin && git log origin/main --oneline -1 | grep 'DS3'
```

**If grep fails, STOP.**

### T1.7 — Pulse

---

## Task 2: DS4 — Permanent ruff CI gate (15 min)

### T2.1 — Create `backend/pyproject.toml` (if missing) or extend (if exists)

- [ ] First check:
  ```
  ls backend/pyproject.toml 2>&1
  ```

- [ ] If MISSING, create with:
  ```toml
  [tool.ruff]
  line-length = 100
  target-version = "py313"
  
  # Files ruff should never touch (frozen / architect-managed)
  extend-exclude = [
      ".venv",
      "services/ml/inference.py",
      "services/dash_ui.py",
      "tests/conftest.py",
  ]
  
  [tool.ruff.lint]
  # Initial rule set — start strict, expand later.
  # F = pyflakes (unused imports / undefined names)
  # E722 = bare except
  # E501 = line too long (excluded — too noisy on existing code; revisit Round 10)
  select = ["F", "E722"]
  ignore = ["E501"]
  
  [tool.ruff.lint.per-file-ignores]
  # Tests can have wildcard imports + bare excepts in fixtures
  "tests/**/*.py" = ["F401", "F403"]
  ```

- [ ] If EXISTS, READ it first. Add or modify the `[tool.ruff]` section to match the above without overwriting unrelated sections (e.g., poetry config). If there's already a ruff section that conflicts, prefer the existing config — your job is to GATE what's there, not redesign it.

### T2.2 — Verify the config works

```bash
cd backend && .venv/bin/ruff check . 2>&1 | tail -5
```
Expected: passes cleanly (since T1 fixed all E722, and DS1 already fixed all F401). If errors appear, fix them or adjust the exclude list.

### T2.3 — Create `.github/workflows/lint.yml`

- [ ] Check if it already exists:
  ```
  ls .github/workflows/lint.yml 2>&1
  ```

- [ ] If MISSING, create with:
  ```yaml
  name: lint
  
  on:
    push:
      branches: [main]
    pull_request:
      branches: [main]
  
  jobs:
    ruff:
      runs-on: ubuntu-latest
      steps:
        - uses: actions/checkout@v4
        - uses: actions/setup-python@v5
          with:
            python-version: '3.13'
        - name: Install ruff
          run: pip install ruff
        - name: Run ruff
          working-directory: backend
          run: ruff check .
  ```

- [ ] If EXISTS, leave it alone and just ensure it includes a ruff job. If it doesn't, ADD a ruff job to the existing file (don't replace).

### T2.4 — Validate YAML syntax

```bash
python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml')); print('YAML valid')"
```
Expected: `YAML valid`.

### T2.5 — Commit

```bash
git add backend/pyproject.toml .github/workflows/lint.yml
git status --short
git commit -m "$(cat <<'EOF'
feat(DS4): permanent ruff lint CI gate

Locks in DS1 (F401 unused imports) + DS3 (E722 bare except) so they
can't silently regress on a future PR.

Files:
- backend/pyproject.toml: ruff config with select=["F","E722"],
  per-file ignores for tests, exclude list for architect-frozen files
- .github/workflows/lint.yml: runs `ruff check backend/` on push + PR

Verification:
  $ cd backend && .venv/bin/ruff check .
  All checks passed!

  $ python3 -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml'))"
  (no error)
EOF
)"
git push origin main
git fetch origin && git log origin/main --oneline -1 | grep 'DS4'
```

### T2.6 — Pulse — `DONE :: lint gate live`.

---

## Halt conditions

1. Pre-flight finds H26 not yet complete on origin → STOP and wait.
2. Bulk ruff `--fix` was used (it MUST be manual per-file).
3. Any test that was passing before your DS3 edit now fails — revert that edit, re-run, document.
4. `social_flow_pipeline.py:335` review reveals the bare except is hiding a real bug — STOP and ping architect rather than papering over.
5. CI YAML is invalid.
6. Origin gate fails.
7. 15-min pulse gap.

---

## What success looks like

- 2 commits on origin (DS3 sweep + DS4 gate)
- `ruff check backend/` exits 0
- `.github/workflows/lint.yml` is a valid GitHub Actions workflow that will run on next PR
- Future agents can't add a bare except or unused import without CI failing
