# AGENT CONTRACT — Meridian / Confluence Decoder (floww)

> Source of truth for every agent spawned in this repo. Read this FIRST. If anything here conflicts with what your spawn prompt says, this file wins.

---

## 1. Canonical paths (BURN THESE IN)

- **THE ONLY floww clone:** `/Users/nav/Documents/GitHub/floww`
- If `pwd` doesn't end in `Documents/GitHub/floww` → **STOP and re-cd.**
- **NEVER** use `/Users/nav/floww` — it points at a suspended GitHub account; nothing pushed there reaches Nav.
- **NEVER** use `/Users/nav/GitHub/floww` — old stale clone, deleted 2026-05-29. Do not re-clone there.

---

## 2. Lane separation (NON-NEGOTIABLE — shared clone, multiple agents)

- **Only edit files in your assigned lane.** Never touch another agent's in-flight WIP.
- **Pathspec commits ONLY:** `git add <your-exact-files>` then commit. **Never** `git add -A` / `git add .` — that sweeps up other agents' work.
- **Before you start:** run `git status --short` and note what's already modified. If you see files outside your lane, STOP and ask.
- **Check for other agents' status files** in `kanban/cards/agent_*_status.md` before touching anything.

---

## 3. Forbidden files (architect-frozen — touch = ask Nav first)

- `backend/services/ml/inference.py` — frozen except surgical bug fixes you must justify in commit body
- `backend/services/dash_ui.py` — frozen
- `backend/tests/conftest.py` — R10 P0.1 WAIVES the freeze (per CLAUDE.md current state)
- Model artifacts: `.joblib`, `.pt`, `*_manifest.json`, `*_meta.json` under `backend/models/`
- `frontend/.env`, `frontend/package.json`, `frontend/craco.config.js`
- `frontend/src/App.js` — heavy concurrent WIP, surgical edits only with explicit approval

If a task requires touching a forbidden file, **STOP and ask Nav first.**

---

## 4. Forbidden git operations

- `git push --force` / `--force-with-lease`
- `git commit --no-verify`
- `git commit --amend` on a commit not authored by yourself this session
- `git rebase --abort` (use `--continue` after fixing conflicts; if stuck, HALT)
- `git reset --hard`, `git checkout .`, `git restore .`, `git clean -fd`
- `git rebase -i` (interactive)

If you need to undo work, **ASK first.**

---

## 5. Commit message style (mandatory)

Use a HEREDOC and include **inline real evidence** (grep/pytest/curl output) in the body:

```bash
git commit -m "$(cat <<'EOF'
feat(public-api): integrate chain endpoint with Tidehunter Pro fallback

Brief explanation of what + why.

Verification:
$ curl -s 'http://localhost:8000/api/chain/SPY' | python3 -c "..."
OK
$ cd backend && .venv/bin/python3 -m pytest tests/services/test_public_chain.py -v 2>&1 | tail -5
5 passed

Co-Authored-By: Agent N ( Hermes )
EOF
)"
```

Subject: `<type>(<scope>): <one-line>`. Types: `feat`, `fix`, `docs`, `test`, `refactor`, `chore`. Scope = the area you're touching.

**Anti-skip gate (every push):** After pushing, verify:
```bash
git fetch origin && git log origin/main --oneline -1 | grep "<your subject>"
```
If the grep finds nothing, the push silently failed — STOP.

---

## 6. Anti-fabrication (the most important rule)

**Every claim must carry real command output.** Do not say a test passes, a route works, or a commit landed without pasting the actual `pytest` tail / `curl` response / `git log origin/main` line. Unverifiable claims are treated as failures.

Round 7's fabricated completion log is the negative-example floor — never repeat it.

---

## 7. Test discipline (non-negotiable)

- **NEVER** add `@pytest.mark.skip` / `@pytest.mark.xfail` / `it.skip()` to a previously-passing test.
- If your change makes a passing test fail, **your change is WRONG** — revert and find root cause.
- A test you write yourself **MUST fail before your fix and pass after.**
- Backend venv: always `backend/.venv/bin/python3` (Python 3.13). Never system Python.
- Backend tests: `cd backend && .venv/bin/python3 -m pytest -q`
- Frontend tests: `cd frontend && npx craco test --watchAll=false`

---

## 8. Data source routing (see `.planning/DATA_SOURCES.md` for full detail)

| Need | Primary | Fallback |
|---|---|---|
| Options chain / OI / Greeks (heatmap) | **Public API** (PublicBroker) | cvserver → yfinance → Databento |
| Spot price + IV | Public API (PublicBroker.get_quotes) | yfinance (5s cache) |
| Bars / OHLCV | Public API (PublicBroker.get_bars) | yfinance |
| Design-time data inspection | cvserver MCP tools | — |
| Runtime page data | `window.cvApi` via local proxy | — |
| Schwab | **NOT USED** — mock feed only for tests | — |

**Schwab is out.** Do not plan anything around it. Do not wire agents to it. The `schwab_streamer.py` module exists but has no live key — mock only.

- **Public API key: EXISTS and CONFIRMED** — `d84ic5pr01qutij93me0d84ic5pr01qutij93meg`. The standalone `/Users/nav/backend/services/public_api.py` has a full `PublicBroker` class (1050 lines) with chain, quotes, portfolio, orders, greeks, bars — tested by a 547-line mocked test suite. The connection model is: **copy PublicBroker into floww backend** (two separate repos, no import path between them). The key goes in `backend/.env` (gitignored) + documented in `backend/.env.example`. See `.planning/PHASE3_PUBLIC_API_PLAN.md` for the full deep-dive + agent fleet + routing decision tree.

- **Connection model decided:** `/Users/nav/backend/` is a standalone service layer (NOT a server, NOT a git repo). It has NOTHING wired into floww. The PublicBroker must be COPIED into `/Users/nav/Documents/GitHub/floww/backend/services/public_api.py` and wired as the primary data source. The fallback chain is: Public API → cvserver (existing `cvserver_client.py`) → yfinance + Databento (existing).

- **Zenith is a UI tab, not a data service.** API calls do NOT route to Zenith. Zenith (legacy Skylit GEX grid) is display-only; data comes from Solstice/Triad/Tidehunter Pro.

---

## 13. GSD Active Phase — Phase 3: Public API Data Layer

**Status:** ACTIVE (2026-08-30). See ROADMAP.md §3 for ticket list.

**Agent fleet (all spawn from this repo):**

| Agent | Lane | Repo | Mission |
|---|---|---|---|
| **Agent 1** (you) | Planning + coordination + git | `floww` | Write plan, push contract/docs, spawn fleet, monitor |
| **Agent 2** | Backend integration | `floww` | Copy PublicBroker → add PUBLIC_API_KEY → modify fetch_spot_and_chains_merged → new routes → tests |
| **Agent 3** | cvserver alignment | `floww` | Verify fallback path compatibility, update INTEGRATIONS.md |
| **Agent 4** | Frontend wiring | `floww` | Solstice/Triad: use Public API endpoints. Zenith unchanged. |
| **Agent 5** | GSD execution | `floww` | Phase plans, kanban cards, tracking |

**Lane boundaries (CRITICAL — prevents cross-agent collisions):**
- Agent 2: `backend/services/` (new files only), `backend/routes/` (new files), `backend/.env` + `.env.example` (non-committed), `backend/tests/services/` (new test files). Does NOT touch `backend/server.py` logic except adding the new router include line.
- Agent 3: `.planning/codebase/INTEGRATIONS.md`, `backend/.env.example` (docs only). Does NOT modify cvserver_client.py logic.
- Agent 4: `frontend/src/components/heatseeker/`, `frontend/src/lib/hooks/` (data fetch hooks). Does NOT touch `frontend/src/App.js` (frozen).
- Agent 5: `.planning/phases/`, `kanban/cards/`. Does NOT touch backend/frontend code.

**Launch sequence:**
1. Agent 1 pushes Phase 3 plan + contract updates (this commit)
2. Agent 1 spawns Agent 2 + Agent 3 simultaneously
3. Agent 2 + Agent 3 sync on the PublicBroker data shape vs cvserver data shape (fallback contract)
4. Agent 2 ships routes + tests → Agent 1 approves
5. Agent 4 spawns once Agent 2's routes are committed
6. Agent 5 tracks all phases end-to-end

---

## 9. Paper only — ALWAYS

Never wire any AI/automation to live order execution. Analytics, paper, and simulation only. This is an operating contract rule, not a suggestion.

---

## 10. Self-HALT rule

If you go **15 minutes without progress**, stop and write your status to `kanban/cards/agent_<n>_status.md` using the append-only format. Do not silently drift.

---

## 11. Status reporting

Each agent writes append-only status lines to `kanban/cards/agent_<n>_status.md`:

```
[2026-08-30T12:00:00Z] AgentN :: in-progress :: <what you're doing> :: HEAD=<git sha>
[2026-08-30T12:15:00Z] AgentN :: DONE :: <what shipped> :: HEAD=<git sha>
```

Format: `[timestamp] AgentId :: status :: note :: HEAD=sha`

---

## 12. GSD integration state (as of this contract)

- GSD scaffolded at `.planning/` (ROADMAP.md, PROJECT.md, STATE.md, REQUIREMENTS.md, config.json, 7 codebase maps)
- Current phase: Phase 1 — Oracle Go-Live (pending VM provisioning)
- **NEXT phase: Phase 4 — Tidehunter Pro Integration (ACTIVE, documented)** — see ROADMAP.md §4. Not building today — documented as the Phase 3 live-testing fallback. Phase 3 is CLOSED.

Kanban: 23 cards all done, 0 in progress (Phase 3 kanban refresh complete at ecfabb6+)
- Phase 2 — Round 10 P0 Closure: COMPLETE (P0.1-0.3 done)
- Kanban: 23 cards all done, 0 in progress
- Backend: ~4546 tests passing, working tree clean, 1 commit ahead of origin/main (deep sweep report just pushed)
- Frontend: 277 passed, 18 pre-existing failures (CSS module + missing module scopes — not new)
