# Round 9 Follow-up — Hermes Agent Launcher

Five Hermes Owl Alpha agent prompts. Each prompt is a self-contained file you copy-paste into a fresh Owl Alpha session.

## TL;DR — which to launch when

| Phase | Agents | Why parallel-safe |
|-------|--------|-------------------|
| **Phase 1 — launch all 4 at the same time** | H26, H27, H28, H30 | Each touches a disjoint set of files (see ownership table below) |
| **Phase 2 — launch after H26's commits land on origin** | H29 | H29's ruff sweep modifies the same files H26 just patched; race-prone if parallel |

Estimated wall-clock with parallel Phase 1: **~90 min for all 5 agents** (the slowest single agent is H28's audit at ~90 min; H29 starts when H26 done at ~75 min).

---

## File ownership (verify before launching)

```
H26 → backend/server.py (lines ~2188)
       backend/routes/replay.py
       backend/services/paper_trader.py
       backend/routes/ml_predict_api.py
       (+ test files in backend/tests/)

H27 → backend/services/__init__.py (new file)
       backend/services/ml/__init__.py (new file, if needed)
       backend/tests/test_services_is_package.py (new file)

H28 → docs/ROUND9_FRONTEND_LEAK_AUDIT.md (new file)
       3 frontend files (TBD by H28 based on what audit finds)

H29 → backend/**/*.py (manual ruff E722 per file, sequenced AFTER H26)
       backend/pyproject.toml
       .github/workflows/lint.yml

H30 → backend/tests/services/ml/test_ml_integration.py (was untracked, will be committed)
```

No two agents in Phase 1 touch the same file. H29 in Phase 2 origin-gates on H26 in its own pre-flight.

---

## Launch instructions per agent

### Agent H26 — L4 Medium-Severity Leak Fixes
- **File**: `round9_followup/HERMES_H26_L4_MEDIUM_LEAKS.md`
- **Expected duration**: ~75 min
- **Deliverables**: 5 commits on origin/main (4 leak fixes + close-out doc)
- **Paste into Owl Alpha**: read the file with `cat round9_followup/HERMES_H26_L4_MEDIUM_LEAKS.md` and paste the entire content

### Agent H27 — Unblock 20 Test Files via `services/__init__.py`
- **File**: `round9_followup/HERMES_H27_PACKAGE_INIT_UNBLOCK.md`
- **Expected duration**: ~30 min (HIGHEST LEVERAGE — single file fix unlocks ~150-300 tests)
- **Deliverables**: 1-2 commits (`services/__init__.py` + regression test, optionally `services/ml/__init__.py`)
- **Paste into Owl Alpha**: same pattern

### Agent H28 — Frontend Memory-Leak Audit + Top-3 Fixes
- **File**: `round9_followup/HERMES_H28_FRONTEND_LEAK_AUDIT.md`
- **Expected duration**: ~90 min (45 audit + 45 fix)
- **Deliverables**: 5 commits (audit report + 3 fixes + close-out marking)
- **Paste into Owl Alpha**: same pattern

### Agent H29 — DS3 Bare-Except Sweep + DS4 Lint CI Gate (Phase 2)
- **File**: `round9_followup/HERMES_H29_LINT_GATE_AFTER_H26.md`
- **Expected duration**: ~45 min
- **PRECONDITION**: H26's commits MUST be on origin first. The prompt's pre-flight hard-gates on this.
- **Deliverables**: 2 commits (DS3 sweep + DS4 CI gate)
- **Launch only after**: `git log origin/main --oneline | grep -c 'L4-leak-#[56789]'` returns ≥3

### Agent H30 — Rewrite ML Integration Tests
- **File**: `round9_followup/HERMES_H30_ML_INTEGRATION_TEST_FIX.md`
- **Expected duration**: ~45 min
- **Deliverables**: 1 commit — the rewritten test file (currently `??` untracked in working tree)
- **Paste into Owl Alpha**: same pattern

---

## Architect monitoring

Every 15 min, you'll see new lines appear in:
- `kanban/cards/agent_H26_status.md`
- `kanban/cards/agent_H27_status.md`
- `kanban/cards/agent_H28_status.md`
- `kanban/cards/agent_H29_status.md`
- `kanban/cards/agent_H30_status.md`

Quick check command:
```bash
ls -t kanban/cards/agent_H{26,27,28,29,30}_status.md 2>/dev/null | xargs tail -1
```

To see new commits as they land:
```bash
git fetch origin && git log origin/main --oneline --since="2 hours ago"
```

---

## Total session impact (if all 5 agents succeed)

| | Count | Effect |
|---|-------|--------|
| New commits on origin | ~14 | 5 (H26) + 2 (H27) + 5 (H28) + 2 (H29) + 1 (H30) — close-outs included |
| L4 backend leaks fixed | +5 | All 9 remaining Med/Low items closed (combined with Pro's 5 = 14/14 backend leak audit COMPLETE) |
| Test files unblocked | ~20 | `services/__init__.py` unlocks the full `tests/services/` directory |
| Frontend leaks fixed | +3 | Top-severity findings from new L2+L3 audit |
| CI gates added | +1 | Permanent ruff gate prevents F401/E722 regressions |
| Untracked working-tree files | 1 → 0 | `test_ml_integration.py` finally committed |
| Audit reports written | +1 | `docs/ROUND9_FRONTEND_LEAK_AUDIT.md` |

---

## Forbidden across ALL 5 agents (architect-locked this round)

- `backend/services/ml/inference.py` (frozen)
- `backend/services/dash_ui.py` (Round 7 frozen)
- `backend/tests/conftest.py` (Round 9 verified-not-broken)
- `frontend/src/App.js` (heavy WIP)
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- Any `.joblib`, `.pt`, or model `.json` artifact
- Destructive git operations (force, hard reset, --no-verify, --amend others)
- `pytest.mark.xfail` / `pytest.mark.skip` on a previously-passing test
