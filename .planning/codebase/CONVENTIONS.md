# Coding Conventions

**Analysis Date:** 2026-08-24

## Naming Patterns

**Files:**
- Backend Python: `snake_case.py` (e.g., `backend/services/duckdb_engine.py`, `backend/routes/alerts.py`)
- Backend tests mirror source layout: `backend/tests/services/test_<module>.py`, `backend/tests/routes/test_<endpoint>.py`
- Frontend tests: `frontend/src/__tests__/*.test.js(x)` (Jest/CRA convention)
- React components: PascalCase (`frontend/src/components/`)

**Functions / Variables:**
- Python: `snake_case` functions and variables; `PascalCase` classes
- Module-level private/cache members use `_` prefix (see `_alert_engine` in `backend/routes/alerts.py`)
- Async functions: no special prefix (`async def get_alert_engine()`)

## Code Style

**Linting:** ruff — rules `E`, `E722`, `F`, `W`, `I`; **E501 ignored** (line length not enforced).
- Run: `cd backend && .venv/bin/ruff check .`
- Auto-fix safe issues: `.venv/bin/ruff check --fix .`
- Enforced in CI: `.github/workflows/lint.yml`

**Type hints:** use them on new/edited service and route code (FastAPI signatures are typed); legacy modules vary — match surrounding code, don't mass-annotate.

**Python runtime:** always `backend/.venv/bin/python3` (never system Python).

**Test discipline (from `CLAUDE.md`):**
- NEVER add `@pytest.mark.skip`, `@pytest.mark.xfail`, or `it.skip()` to a previously-passing test without architect approval.
- If your change breaks a passing test, your change is wrong — revert and find root cause.

## Commit Message Format (mandatory per `CLAUDE.md`)

Subject: `<type>(<scope>): <one-line subject>`
- Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`
- Scopes follow round naming: `round-9-h26`, `round-10-P0.1`, `round-10-architect`, etc.

Body must include **inline verification evidence** (real grep/test/curl output) via HEREDOC:

```bash
git commit -m "$(cat <<'EOF'
fix(round-10-P0.2): restore fetch_spot_and_chains (A9 deletion miss)

Brief explanation of what + why.

Verification:
$ cd backend && .venv/bin/python3 -m pytest tests/services/test_....py -v 2>&1 | tail -1
2 passed
EOF
)"
```

Never invent SHAs; verify with `git log origin/main`.

## Forbidden Files (architect-frozen)

Touching any of these requires stopping and asking Nav first:
- `backend/services/ml/inference.py` — frozen except surgical bug fixes justified in commit body
- `backend/services/dash_ui.py` — Round 7 frozen
- `backend/tests/conftest.py` — R9 frozen; R10 P0.1 waives freeze only with architect approval
- Model artifacts under `backend/models/`: `*.joblib`, `*.pt`, `*_manifest.json`, `*_meta.json`
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `frontend/src/App.js` — concurrent WIP; surgical edits only with explicit approval

## Forbidden Git Operations

- `git push --force` / `--force-with-lease`
- `git commit --no-verify`
- `git commit --amend` on commits not authored this session
- `git rebase --abort` (use `--continue`; if stuck, HALT)
- `git reset --hard`, `git checkout .`, `git restore .`, `git clean -fd`
- `git rebase -i` (interactive)

To undo work: ASK first.

---

*Conventions audit: 2026-08-24*
