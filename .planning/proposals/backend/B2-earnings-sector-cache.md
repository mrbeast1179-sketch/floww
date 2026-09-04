# Backend Proposal B2 — Finnhub Earnings + Sector Cache

**Proposed by:** Agent 3 (Backend/Data lane) · **Status:** PROPOSAL — needs Agent 1 gate decision + BACKEND_LANE_OWNER=1
**Depends on:** HANDOFF B2, PLAN.md W2, FULL_PLAN.md B2, CONTRACTS.md CR-02, PLAN.md C10
**Blocks:** W2.1 (earnings proximity col + filter), W2.2 (sector/industry filter)

## Problem

W2.1 (earnings proximity) and W2.2 (sector/industry) need Finnhub data. Calling Finnhub
`/calendar/earnings` + `/stock/profile2` inline at scan cadence risks >1/min on free tier (C7:
earnings is free but limited to 1 month historical + new updates). Frontend fetching per-poll is
not viable; a backend cache with TTL is required.

## Proposal

Add a backend earnings + sector cache service that:

1. **Populates from Finnhub** on a declared refresh cadence (default: hourly for sector map,
   daily for earnings calendar — earnings doesn't change intra-day).
2. **Caches in-memory** (or file-backed, same DuckDB as B1 if B1 lands) with declared TTLs:
   - Sector map: 24h TTL (industries rarely change)
   - Earnings calendar: 1h TTL for upcoming earnings; 24h for historical
3. **Exposes frontend endpoints** (matches CR-02):
   - `GET /api/context/earnings?tickers=AAPL,TSLA,MSFT` → returns earnings calendar for those tickers
   - `GET /api/context/sector?tickers=AAPL,TSLA,MSFT` → returns sector/industry map subset
4. **Static map fallback** (C10): Finnhub profile2 returns `finnhubIndustry` (free, verified).
   GICS sector needs a static `finnhubIndustry→sector` map (or yfinance `.info` fallback).
   W2 builds the map, not a new vendor.
5. **Cache stamped** with `cache_ts` + `next_refresh` so frontend can show data age honestly.
6. **GO/NO-GO declared:** if Finnhub endpoints are not viable (rate-limited, auth required),
   Agent 3 declares GO/NO-GO in proposal. Agent 2 ships W2.1/W2.2 against fixtures regardless.

## Rate safety

- Earnings: 1 month historical only (C7). No multi-quarter surprise trends (dropped from W2).
- Sector: profile2 is free, explicitly the Company Profile endpoint. One call per ticker on refresh.
- Refresh cadence tuned to stay under Finnhub free tier limits. If limits are hit, cache TTL extends.

## Data shape (matches CR-02)

```json
{
  "earnings": {
    "AAPL": [
      {"date": "2026-01-28", "quarter": "Q4 2025", "implied_move_pct": 4.2}
    ]
  },
  "cache_ts": "2026-09-03T12:00:00Z",
  "next_refresh": "2026-09-03T13:00:00Z"
}
```

```json
{
  "sector_map": {
    "AAPL": {"sector": "Technology", "industry": "Consumer Electronics"},
    "XLU": {"sector": "Utilities", "industry": "Utilities"}
  }
}
```

## Risks

- Finnhub free tier limits: mitigated by aggressive caching + hourly/daily refresh.
- Earnings limited to 1 month historical (C7): proximity gating works; multi-quarter surprise
  trends are NOT available — dropped from W2 scope.
- Sector map incomplete: static map covers common industries; yfinance fallback for edge cases.

## Acceptance criteria (when implemented)

- [ ] Earnings endpoint returns real Finnhub data for 5+ tickers sampled
- [ ] Sector endpoint returns real Finnhub profile2 + static map for 5+ tickers sampled
- [ ] Cache TTL declared and honored
- [ ] cache_ts + next_refresh stamped on responses
- [ ] GO/NO-GO declared if Finnhub not viable
- [ ] No per-poll Finnhub fetch from frontend

## Gate decision requested

Agent 1: grant BACKEND_LANE_OWNER=1 for B2. Unblocks W2.1 + W2.2.

**Proposer's recommendation:** Ship B2. Earnings proximity + sector filter are high-value,
low-risk W2 features. Finnhub free tier supports it with caching.
