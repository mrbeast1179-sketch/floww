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
| Options chain / OI / Greeks (heatmap) | **Public API** (brokerage) | Tidehunter Pro (paid tier) |
| Spot price + IV | Public API spot endpoint | yfinance (5s cache) |
| Design-time data inspection | cvserver MCP tools | — |
| Runtime page data | `window.cvApi` via local proxy | — |
| Schwab | **NOT USED** — mock feed only for tests | — |

**Schwab is out.** Do not plan anything around it. Do not wire agents to it. The `schwab_streamer.py` module exists but has no live key — mock only.

- **Public API key: EXISTS** — `d84ic5pr01qutij93me0d84ic5pr01qutij93meg`. The `/Users/nav/backend/services/public_api.py` already has a full `PublicBroker` implementation. The connection between the standalone `/Users/nav/backend/` layer and floww backend is the open question (see `.planning/DATA_SOURCES.md`). Do NOT add any real API key to the repo. The `.env` files are gitignored.

**Zenith is a UI tab, not a data service.** API calls do NOT route to Zenith. Zenith (legacy Skylit GEX grid) is display-only; data comes from Solstice/Triad/Tidehunter Pro.

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
- Next phase being added: Phase 3 — Public API Data Layer
- Kanban: 23 cards all done, 0 in progress
- Backend: ~4546 tests passing, working tree clean, 1 commit ahead of origin/main (deep sweep report just pushed)
- Frontend: 277 passed, 18 pre-existing failures (CSS module + missing module scopes — not new)
