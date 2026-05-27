# Round 9 Follow-up v2 — 10-Agent Hermes Owl Alpha Launcher

10 fresh Hermes Owl Alpha sessions. Each agent has 2-3 hours of dense, TDD-style work with disjoint file ownership. Total wall-clock with 10 parallel: ~3 hours for the longest agent (A8). Total committed work: ~50-60 new commits on origin.

This SUPERSEDES the prior 5-agent v1 plan (`round9_followup/`). Files in v1 remain for reference but should NOT be launched alongside v2 (double-pressure on the same files).

---

## Phase plan

| Phase | Agents launched | Why parallel-safe |
|-------|------------------|-------------------|
| **Phase 1 — launch all 10 NOW in parallel** | A1, A2, A3, A4, A5, A6, A7, A8, A9, A10 | Disjoint file ownership matrix (see below). A9 is read-only audit. |
| **Phase 2 — none** | — | Single-phase launch; the entire batch runs simultaneously |

Each agent enforces its own pre-flight + 15-min pulse cadence + origin-state gate. If any agent stalls, the others continue.

---

## File ownership matrix (zero overlap)

| Agent | Files writable |
|-------|----------------|
| **A1** | `backend/server.py`, `backend/routes/replay.py`, `backend/services/paper_trader.py`, `backend/routes/ml_predict_api.py`, `backend/pyproject.toml`, `.github/workflows/lint.yml`, plus DS3 ruff sweep across backend (manual per-file) |
| **A2** | `backend/services/__init__.py` (NEW), `backend/services/ml/__init__.py` (NEW), `backend/tests/services/ml/test_ml_integration.py` (REWRITE), `backend/tests/test_services_is_package.py` (NEW), `backend/pytest.ini` (NEW) |
| **A3** | `frontend/src/hooks/*` EXCEPT useGreeks, useWebSocketGex (A5). `frontend/src/components/*` EXCEPT `heatseeker/`, CharmChart, VannaChart, OptionsChainTable, ToxicityGauge (A4-A7). NOT App.js. |
| **A4** | `backend/services/heatseeker*.py`, `frontend/src/components/heatseeker/*` |
| **A5** | `frontend/src/components/CharmChart.jsx`, `VannaChart.jsx`, `frontend/src/hooks/useGreeks.js`, `useWebSocketGex.jsx` |
| **A6** | `frontend/src/components/OptionsChainTable.jsx`, `ExpiryFilter.jsx` (NEW), `DTEFilter.jsx` (NEW), `backend/routes/market_data.py` (chain endpoint additions only) |
| **A7** | `frontend/src/components/ToxicityGauge.jsx`, `backend/services/ml_ensemble.py` (toxicity sections only) |
| **A8** | `backend/schwab/*`, `backend/services/websocket_streamer.py`, `backend/services/ingestion_pipeline.py` |
| **A9** | **READ-ONLY everywhere.** Writes ONLY `docs/ROUND10_DEAD_CODE_AUDIT.md` + scripts/audit_dead_code.py + scripts/count_callers.py |
| **A10** | `backend/services/option_chain.py`, `bs_greeks.py`, `spy_helpers.py`, `backend/error_tracking.py`, `backend/mypy.ini` |

**Universally forbidden** for ALL agents:
- `backend/services/ml/inference.py`
- `backend/services/dash_ui.py`
- `backend/tests/conftest.py`
- Any model artifact (.joblib, .pt, _manifest.json, _meta.json)
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `frontend/src/App.js` (except A3 surgical, with extra care)

---

## Time budget per agent

| Agent | Target duration | Total tasks | Expected commits |
|-------|------------------|-------------|------------------|
| A1 | 3 hr | 10 | 7-8 |
| A2 | 2.5 hr | 10 | 3-4 |
| A3 | 3 hr | 10 | 7 |
| A4 | 2.5 hr | 10 | 6-7 |
| A5 | 2.5 hr | 10 | 5-6 |
| A6 | 2.5 hr | 10 | 5-6 |
| A7 | 2.5 hr | 10 | 5 |
| A8 | 3 hr | 10 | 6-8 |
| A9 | 2.5 hr | 9 | 1-2 |
| A10 | 2.5 hr | 10 | 2-3 |

Total expected commits: **~50-60 commits** on origin/main in ~3 hours wall-clock.

---

## Launch instructions

Open 10 fresh Hermes Owl Alpha sessions. Paste these one prompt per session:

| Session | Prompt file (read with `cat` and paste full content) |
|---------|------------------------------------------------------|
| 1 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A1.md` |
| 2 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A2.md` |
| 3 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A3.md` |
| 4 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A4.md` |
| 5 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A5.md` |
| 6 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A6.md` |
| 7 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A7.md` |
| 8 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A8.md` |
| 9 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A9.md` |
| 10 | `cat round9_followup_v2/_PREAMBLE.md && cat round9_followup_v2/AGENT_A10.md` |

If you cannot run `cat` on the agent side, the FULL content of each file appears inline in the architect's response message — copy from there.

---

## Architect monitoring

Run every 15 min to see all agent activity at once:
```bash
cd /Users/nav/Documents/GitHub/floww && git fetch origin && \
  echo "=== last 10 commits ===" && git log origin/main --oneline -10 && \
  echo "=== latest pulse per agent ===" && \
  for id in A1 A2 A3 A4 A5 A6 A7 A8 A9 A10; do
    [ -f "kanban/cards/agent_${id}_status.md" ] && tail -1 "kanban/cards/agent_${id}_status.md" || echo "$id :: no status yet"
  done
```

---

## Expected outcome (if all 10 succeed)

- L4 backend leak audit: **14/14 fixed** (5 Pro + 5 A1 + 4 already-done)
- Lint CI gate: **live** on main branch
- `services/__init__.py` test infra: **fixed**, +200+ tests unlocked
- `test_ml_integration.py`: **committed**
- Frontend leak audit: **complete + top-5 fixed**
- Heatseeker panel test coverage: **extended, H4 contract regression-locked**
- Charm/Vanna charts: **render correctly with d8af12c contract**
- OptionsChainTable: **vanna/charm/dte columns added, expiry+DTE filters**
- ToxicityGauge: **null-safe, threshold-colored, contract documented**
- Schwab streamer: **chaos-tested, health contract documented**
- Round 10 dead-code audit: **complete with reproducible scripts**
- 4 utility modules: **fully type-annotated, mypy strict gate**

Round 9 closes. Round 10 backlog is concrete + prioritized.

---

## Halt-condition pattern (all agents)

Any agent self-HALTs if:
1. Pre-flight finds wrong directory or missing prerequisite commits
2. A failing-test step doesn't actually fail (test is wrong)
3. A pass step doesn't pass after fix (fix is wrong)
4. Wider test sweep regresses
5. Origin gate returns empty (push silently failed)
6. Out-of-scope file edit required → STOP and ping architect via `kanban/cards/architect_inbox.md`
7. 15-min pulse gap

Halt format:
```
[<UTC>] <ID> :: HALT :: T<N> :: <reason> :: HEAD=<sha>
```

Architect responds within 15 min by appending to the same status file.
