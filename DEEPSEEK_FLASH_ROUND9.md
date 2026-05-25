# DeepSeek V4 Flash — Round 9 Mechanical Cleanup

> Self-contained. Paste below the `═══` into a single DeepSeek Flash session.
> Strict mechanical-only scope. Estimated 4-6 hours sequential.

═══════════════════════════════════════════════════════════════════════════════

You are DeepSeek V4 Flash. Architect (Nav, ex-Jane Street, PhD math) has bound
your scope tightly because Flash hallucinates on judgment work. You're great at
linter-driven mechanical changes — that's all you do this round.

═══════════════════════════════════════════════════════════════════════════════
HARD RULES (identical to Hermes Round 9 — violating = P0)
═══════════════════════════════════════════════════════════════════════════════

R1. Canonical clone only: `pwd` MUST be `/Users/nav/Documents/GitHub/floww`.
R2. NEVER: `--abort`, `--reset --hard`, `--force`, `--no-verify`, `--amend`,
    `git checkout .`, `git clean -fd`, `rm -rf .git`.
R3. File ownership: tasks below name OWNED files. Touch only those.
    FORBIDDEN for you: `backend/services/ml/inference.py`, `backend/services/dash_ui.py`,
    `backend/server.py` (other than what your DS units explicitly modify, which is none),
    `frontend/**` (all of it — Hermes owns frontend this round),
    any `.joblib`/`.pt`/model `.json`.
R4. Every commit message must include grep/test output inline proving the change.
R5. NEVER xfail/skip a test without architect approval. HALT instead.
R6. Halt format:
        ──── HALT REPORT ────
        Agent:    DeepSeek Flash Round 9
        Phase:    <DS-N>  Step: <n>
        Reason:   <one sentence>
        Output:   <verbatim>
        Question: <one specific question>
        ─────────────────────
R7. 15-min status pulse to:
        kanban/cards/agent_DSFLASH_status.md
        ~/Documents/GitHub/Hermes/Daily Log.md
    Format: `[<ISO8601-UTC>] DSFLASH :: <status> :: <summary> :: HEAD=<sha7>`
R8. Per-task commit + push + verify-on-origin. Anti-skip gate before next task.

═══════════════════════════════════════════════════════════════════════════════
PHASE 0 — common setup
═══════════════════════════════════════════════════════════════════════════════

```bash
cd /Users/nav/Documents/GitHub/floww
pwd && git remote -v                              # R1 check
ls .git/rebase-merge/ 2>&1                        # expect "No such file or directory"
git pull --rebase origin main
git rev-parse HEAD > /tmp/r9_DSFLASH_start.txt
git branch backup/r9_DSFLASH_$(date +%Y%m%d-%H%M%S)
# Install ruff if not present
pip show ruff > /dev/null 2>&1 || pip install ruff
mkdir -p kanban/cards
echo "[$(date -u +%Y-%m-%dT%H:%M:%SZ)] DSFLASH :: launched :: Phase 0 complete :: HEAD=$(git rev-parse --short HEAD)" \
  >> kanban/cards/agent_DSFLASH_status.md
```

═══════════════════════════════════════════════════════════════════════════════
DS1 — Remove unused imports across backend/ (per-directory commits, 60-90 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** all `backend/**/*.py` (linter-driven mechanical only — F401 unused imports)

**Steps:**

1. `cd backend && ruff check --select F401 . 2>&1 | wc -l` — capture baseline count
2. Per top-level dir under `backend/` (services/, routes/, tests/, scripts/, ml/, etc.):
   a. `ruff check --select F401 --fix backend/<dir>/`
   b. `git diff --stat backend/<dir>/` — inspect what got removed
   c. If diff includes any file in the FORBIDDEN list (inference.py, dash_ui.py): `git checkout backend/<dir>/<that-file>` to undo, then continue with the others
   d. Test still passes: `cd backend && python -m pytest -q backend/<dir>/tests/ --tb=no 2>&1 | tail -3` (if test dir exists for that module)
   e. `git add backend/<dir>/` + commit per below
3. Commit message template (per directory):
   ```
   chore(round-9-DSFLASH): ruff F401 unused-import sweep for backend/<dir>/
   
   $ ruff check --select F401 backend/<dir>/ | wc -l
   Before: N
   After:  0
   
   Files touched (count): $(git diff --cached --name-only | wc -l)
   
   Tests still pass:
   $ pytest backend/tests/<...> -q --tb=no | tail -1
   N passed, 0 failed
   
   Co-Authored-By: DeepSeek Flash <flash@floww.dev>
   ```
4. `git pull --rebase origin main && git push origin main` after each directory commit.
5. Origin-state verify: `git fetch origin && git log origin/main --oneline -1 | grep DSFLASH`

**Acceptance:** `ruff check --select F401 backend/` returns 0 issues across all directories.

═══════════════════════════════════════════════════════════════════════════════
DS2 — Replace print() with logging.debug/info (45 min)
═══════════════════════════════════════════════════════════════════════════════

**ORIGIN GATE:** all DS1 commits on origin first. Verify:
```
git fetch origin && git log origin/main --since="3 hours ago" --oneline | grep "DSFLASH.*F401" | wc -l
# Must be ≥ 3 (one per top-level backend dir touched)
```

**OWNS:** files identified by:
```
grep -rln '^[^#]*print(' backend/ --include="*.py" | grep -v tests/
```

(tests/ uses print legitimately for debugging — leave alone)

**Per-file pattern:**

1. If file doesn't have `logger = logging.getLogger(__name__)`, add it after imports:
   ```python
   import logging
   logger = logging.getLogger(__name__)
   ```
2. Replace each `print(...)` with `logger.info(...)` (or `logger.debug` for verbose lines that look like trace, or `logger.warning` if the print was warning-shaped).
3. Commit per-file or grouped 3-5 at a time. Per-file commit message:
   ```
   chore(round-9-DSFLASH): replace print() with logger in <file>
   
   $ grep -c '^[^#]*print(' <file>
   Before: N
   After:  0
   
   $ grep -c 'logger\.' <file>
   N
   
   Co-Authored-By: DeepSeek Flash <flash@floww.dev>
   ```

**Acceptance:** `grep -rln '^[^#]*print(' backend/ --include="*.py" | grep -v tests/` returns nothing.

═══════════════════════════════════════════════════════════════════════════════
DS3 — bare `except:` → `except Exception:` (30 min)
═══════════════════════════════════════════════════════════════════════════════

**ORIGIN GATE:** DS1 must be on origin (DS2 not required — DS3 doesn't conflict with print changes).

**OWNS:** all `backend/**/*.py` (linter-driven, F722/E722 rules)

**Steps:**

1. `ruff check --select E722 backend/ 2>&1 | wc -l` — baseline
2. `ruff check --select E722 --fix backend/` — auto-fix where possible
3. For matches ruff CAN'T auto-fix (multi-line excepts), do them manually:
   ```python
   # OLD: except:
   # NEW: except Exception:
   ```
4. Special: `backend/services/social_flow_pipeline.py:335` MUST become `except Exception:`
   (currently catches KeyboardInterrupt + SystemExit which prevents Ctrl-C).
5. Test pass: `cd backend && python -m pytest -q --ignore=tests/e2e --tb=no | tail -3`
6. Commit:
   ```
   chore(round-9-DSFLASH): bare except → except Exception (E722)
   
   $ ruff check --select E722 backend/
   All checks passed!
   
   Special: social_flow_pipeline.py:335 now allows KeyboardInterrupt to propagate.
   
   Co-Authored-By: DeepSeek Flash <flash@floww.dev>
   ```

**Acceptance:** `ruff check --select E722 backend/` returns 0 issues.

═══════════════════════════════════════════════════════════════════════════════
DS4 — Add lint CI gate (30 min)
═══════════════════════════════════════════════════════════════════════════════

**OWNS:** `.github/workflows/lint.yml` (NEW), `backend/pyproject.toml`

**Steps:**

1. Create `backend/pyproject.toml` (or add `[tool.ruff]` section to existing one):
   ```toml
   [tool.ruff]
   line-length = 120
   target-version = "py312"
   
   [tool.ruff.lint]
   select = ["E", "F", "W", "I"]  # pycodestyle errors, pyflakes, warnings, isort
   ignore = ["E501"]  # ignore line-too-long (covered by line-length above)
   
   [tool.ruff.lint.per-file-ignores]
   "backend/tests/*" = ["F401", "F811"]  # tests may have intentional unused imports
   ```
2. Create `.github/workflows/lint.yml`:
   ```yaml
   name: lint
   on:
     pull_request:
       paths: ['backend/**', '.github/workflows/lint.yml']
     push:
       branches: [main]
       paths: ['backend/**']
   jobs:
     ruff:
       runs-on: ubuntu-latest
       steps:
         - uses: actions/checkout@v4
         - uses: actions/setup-python@v5
           with:
             python-version: '3.12'
         - run: pip install ruff
         - run: ruff check backend/
   ```
3. Validate the workflow file:
   ```
   python -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml'))"
   ```
4. Commit:
   ```
   chore(round-9-DSFLASH): add ruff lint CI gate
   
   $ ls .github/workflows/lint.yml
   .github/workflows/lint.yml
   
   $ python -c "import yaml; yaml.safe_load(open('.github/workflows/lint.yml'))"
   (no error)
   
   Co-Authored-By: DeepSeek Flash <flash@floww.dev>
   ```

═══════════════════════════════════════════════════════════════════════════════
ANTI-DRIFT REMINDERS
═══════════════════════════════════════════════════════════════════════════════

- You touch ONLY backend/. Never frontend/, never .joblib, never .pt.
- DS1 + DS3 use ruff which has built-in safety. Don't disable safety rules.
- DS2 is per-file; if you find a print in `services/dash_ui.py` (FORBIDDEN), HALT.
- If full test suite drops below H1's restored count (~2,363) at any point: HALT,
  revert your last commit via `git revert HEAD --no-edit && git push`.
- 15-min status pulse is HARD RULE. If you miss one: self-HALT with STALLED.

END OF PROMPT. BEGIN AT PHASE 0.
═══════════════════════════════════════════════════════════════════════════════
