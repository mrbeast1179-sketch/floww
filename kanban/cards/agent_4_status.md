`agent_4_status.md` — Solstice/Triad frontend wiring Agent 4.

State: Phase 3/5 frontend wiring ACTIVE. Public API endpoints ready in backend.

Current HEAD on main: c5e3b18 (feat(frontend): Phase 5.1 wire Solstice chain table to Public API)
Commit chain prior to this phase's commit:
  56c0c69 docs(gsd): update AGENT_CONTRACT.md kanban status line
  08c3c11 docs(gsd): Phase 3 closure, Phase 4 active, kanban refresh, contract sync
  ecfabb6 test(public-api): verify failed broker recovery
  94c3c89 feat(public-api): Phase 3 integration — PublicBroker wired as primary data source

Phase 5.1 Solstice chain table Public API wiring — DONE:
- `frontend/src/components/OptionsChainTable.jsx` — rewired to fetch from
  /api/public/chain/{ticker} via fetchPublicChain() first, falling back to
  /api/chain?ticker={ticker} (merged path: Public API → cvserver → yfinance).
- Uses existing `fetchPublicChain` helper from frontend/src/lib/publicApi.js.
- `chainRespToRows()` maps public chain {contracts, n_contracts, spot, expiries,
  data_source, ticker} → table {rows, count, expiries, spot, ticker, data_source}.
- AbortController cancels in-flight fetches on ticker/param change (Phase 5.1.3).
- Shows error only if BOTH public + merged paths fail (Phase 5.1.4).
- All 13 columns preserved (Type, Strike, Exp, DTE, IV, Δ, Γ, OI, Vol, GEX, Vanna,
  Charm, Moneyness). CSV export preserved. Virtual scrolling preserved.
- `frontend/src/components/OptionsChainTable.test.jsx` — 10 tests, all passing:
  renders, fetches from public API first, falls back to merged on public API fail,
  null greeks safe, moneyness_pct safe (null/+/−).

Test results:
- Frontend OptionsChainTable tests: 10/10 passing
- Full backend test suite: 4606 passed, 64 skipped, 1 xfailed (no regressions)

Wiring complete. Next: Agent 4 picks up 5.2 Triad multi-ticker confluence + 5.3 Tidehunter Pro
when Phase 5.1 is committed and verified.
