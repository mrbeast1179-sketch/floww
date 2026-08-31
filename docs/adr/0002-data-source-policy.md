# ADR-0002 — Data source policy & priority chain

**Status:** Accepted
**Date:** 2026-08-31
**Context:** Phase 3 (Public API Data Layer) made `public_api` the primary data source for option chains, replacing the pre-Phase-3 `yfinance`-only path. The priority chain now reads: Public API (public.com brokerage) → cvserver/CVForge → yfinance + Databento OI overlay. This ADR records the decision, the rationale, and the consequences.

---

## Decision

The `fetch_spot_and_chains_merged` function in `backend/server.py` uses the following priority chain for fetching option chain data:

1. **Public API** (`PUBLIC_API_KEY` set) — full greeks, real-time chain data from public.com brokerage. Timeout: 30s. On failure (timeout/exception), falls through to cvserver.
2. **cvserver/CVForge** (`CVSERVER_API_KEY` set) — 32 expiries, 171 strikes, all greeks included. Timeout: 30s. For index symbols (`^SPX`, `I:SPX`), uses a screen API fast-path to avoid timeout. On failure, falls through to yfinance.
3. **yfinance** — spot + IV from option chains. Always available (no key required). For paid-tier tickers (SPY, QQQ, IWM, DIA, TLT, SPX), overlays Databento OI on top.
4. **Databento** — real-time/EOD Open Interest via OPRA.PILLAR statistics. Used as OI supplement for paid-tier tickers when yfinance OI is sparse (overnight/throttled). On failure, falls back to yfinance OI only.

The `data_source` field in the response records which path actually produced the data: `public_api`, `cvserver`, `databento+yfinance`, `yfinance`, or `error`.

For index symbols (`^SPX`, `I:SPX`) where Public API isn't available, the cvserver screen API fast-path is used to fetch contracts, then falls through to full GEX computation in `_build_heatmap_impl` rather than returning early.

Free-tier tickers (not in `PAID_TICKERS`) short-circuit to yfinance-only data with no Databento overlay.

## Consequences

### Positive
- Primary data source is now real-time brokerage data with full greeks (Public API), significantly higher quality than yfinance-only.
- cvserver provides a high-capacity fallback with 32 expiries × 171 strikes.
- Databento OI overlay improves Open Interest accuracy for paid-tier tickers during yfinance sparse windows.
- `data_source` field allows the frontend and tests to know which source produced the data (used by heatmap tests to assert expected source).

### Negative
- Public API requires `PUBLIC_API_KEY` in `.env` (currently set). Without it, the system falls through to cvserver → yfinance.
- cvserver requires `CVSERVER_API_KEY` in `.env`. Without it, the system falls through to yfinance + Databento.
- For index symbols, the cvserver screen API fast-path returns contracts only — the full GEX computation happens in `_build_heatmap_impl` after the fast-path, so the payload is always complete (grid, strikes, nodes, patterns).
- Public API chain endpoints hit rate limits; the 30s timeout and fallback chain protect against hanging requests.

## Alternatives considered

- **yfinance-only (pre-Phase-3):** Simpler, no keys required, but lower-quality data (no real-time greeks, sparse OI in some windows). Superseded.
- **cvserver-only:** Higher capacity than Public API but requires a key and has a different data format. Used as fallback, not primary.
- **Databento-only:** Real-time OI but no IV/spot data. Used as supplement, not primary.

## References

- `backend/server.py:fetch_spot_and_chains_merged` — the priority chain implementation
- `backend/services/public_api_adapter.py` — Public API adapter
- `backend/services/cvserver_client.py` — cvserver/CVForge client
- `backend/databento_provider.py` — Databento OI provider
- `backend/.env` — `PUBLIC_API_KEY`, `CVSERVER_API_KEY` (both set)
- `.planning/ROADMAP.md` Phase 3 — Public API Data Layer (CLOSED 2026-08-31)
- `backend/tests/test_heatseeker_v2.py` — tests assert `data_source in (...)` with the full taxonomy
