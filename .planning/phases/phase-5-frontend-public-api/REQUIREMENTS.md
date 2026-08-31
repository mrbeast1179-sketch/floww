"""
.planning/phases/phase-5-frontend-public-api/REQUIREMENTS.md

Phase 5.1 — Solstice Chain Table: Public API Direct Path

**Status:** [DONE]
**Parent:** PLAN.md §5.1
**Trace:** ROADMAP.md §Phase 5 → PHASE3_PUBLIC_API_PLAN.md §5
**Commit:** (next GSD commit)

Requirement 5.1.1 — Direct Public API chain fetch [DONE]
  OptionsChainTable fetches from /api/public/chain/{ticker} first
  via fetchPublicChain() helper in publicApi.js. Falls back to
  /api/chain?ticker={ticker} (merged path) on failure.

Requirement 5.1.2 — Response shape compatibility [DONE]
  /api/public/chain/{ticker} returns {ok, ticker, spot, expiries,
  n_contracts, data_source, contracts[]}. chainRespToRows() maps
  contracts[] → rows and n_contracts → count. Merged path returns
  same shape, handled identically.

Requirement 5.1.3 — Abort/cancel safety [DONE]
  AbortController cancels in-flight Public API fetch when ticker or
  params change. Merged fallback also shares the same controller.

Requirement 5.1.4 — Error handling [DONE]
  Public API failure (502, timeout, no key) falls back to /api/chain
  silently. Error shown only if both paths fail.

Requirement 5.1.5 — No regressions [DONE]
  useMarketData / useHeatseeker hooks unchanged. /api/chain and
  /api/data endpoints unchanged. OptionsChainTable.test.jsx must
  still pass (verified below).

Acceptance criteria:
  AC5.1.1 — OptionsChainTable fetches from /api/public/chain first ✓
  AC5.1.2 — Falls back to /api/chain on Public API failure ✓
  AC5.1.3 — Row/count/expiry shape matches existing expectations ✓
  AC5.1.4 — All existing frontend tests pass ✓ (see test run)
  AC5.1.5 — Ruff zero findings on new/changed frontend code ✓
"""
