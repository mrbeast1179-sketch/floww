# Data Sources — Meridian / Confluence Decoder

> Single source of truth for which API feeds what. Agents: read this before wiring any endpoint.

---

## Status: 2026-08-30

- Schwab: **DELIBERATELY OUT.** Not using it, not building around it. Mock feed only for tests.
- Zenith: **UI tab only**, not a data service. API calls do not route to Zenith.
- Public API: **PRIMARY for everything.** Building all data flow around it.
- Tidehunter Pro: **fallback** for heatmap when Public API is limited.

---

## Data source priority matrix

### Options chain / OI / Greeks (heatmap — Solstice tab)

| Priority | Source | When |
|---|---|---|
| 1 | **Public API** (`/Users/nav/backend/services/public_api.py` → `PublicBroker`) | Default — always try first. Key: `d84ic5pr01qutij93me0d84ic5pr01qutij93meg` |
| 2 | **Tidehunter Pro** | Public API rate-limited, down, or insufficient coverage |

**Rule:** Solstice heatmap always attempts Public API first. If Public API returns a rate-limit/error or the response is degraded, switch to Tidehunter Pro. yfinance is NOT acceptable as a chain source for heatmap — it doesn't have OI data.

### Spot price + IV

| Priority | Source | When |
|---|---|---|
| 1 | **Public API** (`PublicBroker.get_quotes()`) | Default |
| 2 | **yfinance** | Public API spot unavailable, 5s cache |

### Design-time data inspection (you, the agent)

| Source | Use for |
|---|---|
| **cvserver MCP tools** | Inspect data, sanity-check assumptions, pull small samples to design around. floww backend already has `cvserver_client.py`. |
| `window.cvApi` (runtime) | What the rendered page actually calls via local proxy |

### Runtime page data (the rendered SPA)

- `window.cvApi.chain(symbol, fields?)` → `/api/data/chains`
- `window.cvApi.screen({columns, filters, sort, limit})` → `/api/data/screen`
- `window.cvApi.query(sql)` → `/api/data/query`
- `window.cvApi.call('/<endpoint>', body)` → escape hatch for any endpoint

The local proxy (`cv-bootstrap.js`) adds auth server-side. The page never handles API keys directly.

---

## Key registry

| Key | Value | Source | Status |
|---|---|---|---|
| **Public API** | `d84ic5pr01qutij93me0d84ic5pr01qutij93meg` | User-provided (paste 2026-08-30) | **ACTIVE KEY** — this is the Public.com brokerage API key to use for everything. The `/Users/nav/backend/` service layer already has `PublicBroker` in `public_api.py`. |
| Public API (env.example) | `PkdDGcMzqMie0f6I823q6nHtmkGJyRsu` | `/Users/nav/backend/.env.example` | **STALE?** — existing env.example key. The user-provided key `d84ic...` supersedes this. Confirm which to use. |
| CVSERVER | `cv_liv...U6dY` | `backend/.env` (floww) | Local MCP proxy auth — existing floww capability |
| Databento | `db-PBR...GFrN` | `backend/.env` (floww) | OPRA OI cache — data moat |
| Polygon | `NT_RXl...kz1n` | `backend/.env` (floww) | Alternative chain/OI source |
| AlphaVantage | `cDNhZU...4Yz0` | `backend/.env` (floww) | Quote/fundamentals |
| Finnhub | `d84ic5pr01qutij93meg` | `backend/.env` (floww) | **NOTE:** same value as Public API key — may be a copy/paste or the same key used for both. Verify. |

---

## Public API — EXISTING IMPLEMENTATION (`/Users/nav/backend/services/public_api.py`)

**Full `PublicBroker` class already built and tested.** The `/Users/nav/backend/` service layer is a standalone Python backend with:

**Auth:** `PUBLIC_API_KEY` env var → JWT access token (55 min default validity, max 1440)
**Endpoints implemented:**
- `get_accounts()` — list all accounts
- `get_trading_account()` — active trading account
- `get_portfolio(account_id)` — cash, positions, P&L, options buying power
- `get_quotes([symbols], account_id)` — live quotes
- `get_option_chain(symbol, expiration, account_id)` — raw chain
- `get_option_chain_parsed(symbol, expiration, account_id)` — `{"calls": [...], "puts": [...]}` with `OptionContract` objects (strike, expiration, OI, IV, delta, gamma, theta, vega, bid, ask)
- `get_option_greeks(osi_symbols, account_id)` — max 250 symbols per call
- `get_bars(symbol, period, ...)` — OHLCV, multiple aggregations (1m to 1y)
- `place_order(...)` — equity/options/crypto/bond, market/limit/stop/stop-limit

**Test coverage:** `/Users/nav/backend/tests/services/test_public_api.py` (547 lines) — all network calls mocked, covers error paths (no key, API returning None, bulk quote mixed success/failure).

**Gaps to fill for Phase 3:**
1. Confirm which key is active (`d84ic...` vs `PkdDG...`)
2. Wire PublicBroker into floww backend (currently floww uses cvserver_client.py for chain data)
3. Add `/api/public/chain/{ticker}` endpoint to floww backend that uses PublicBroker under the hood
4. Add rate-limit handling → Tidehunter Pro fallback
5. Frontend wiring: Solstice/Triad/Tidehunter Pro tabs call the new floww backend endpoints

**Connection model (to decide in Phase 3.1):**
- Option A: Copy/import `PublicBroker` into floww backend's services/ and add endpoints
- Option B: The `/Users/nav/backend/` layer IS a separate service that floww talks to via HTTP
- Option C: Floww backend adds PublicBroker as a new data provider alongside cvserver_client

---

## yfinance fallback behavior

- yfinance is the spot/IV fallback, 5s cache
- If yfinance 429s from a datacenter IP (Oracle VM), set `FLOWW_DATA_SOURCE=finnhub` in `.env.prod`
- yfinance is NOT a chain/OI source — only spot + IV

---

## Decision tree (for agents wiring data fetches)

```
IF need options chain / OI / Greeks (heatmap):
  → Try Public API (PublicBroker.get_option_chain_parsed / get_option_greeks)
  → If Public API fails/rate-limited → Tidehunter Pro
  → Do NOT fall back to yfinance for chain data

IF need spot price:
  → Try Public API (PublicBroker.get_quotes)
  → If unavailable → yfinance (5s cache)

IF designing / inspecting data (agent, not runtime):
  → Use cvserver MCP tools (existing floww backend capability)

IF runtime page:
  → Use window.cvApi (goes through local proxy, auth server-side)
  → OR call floww backend endpoints that use PublicBroker under the hood
```

---

## What doesn't exist (don't go looking)

- **Zenith API** — Zenith is a UI tab, not a service. No API calls go here.
- **Schwab live key** — doesn't exist. Don't try to wire it.
- **Tidehunter Pro key** — not yet in any .env. Only needed if Public API is actually limited.
