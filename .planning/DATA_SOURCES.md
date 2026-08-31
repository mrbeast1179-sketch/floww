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
| 1 | **Public API** (brokerage) | Default — always try first |
| 2 | **Tidehunter Pro** | Public API rate-limited, down, or insufficient coverage |

**Rule:** Solstice heatmap always attempts Public API first. If Public API returns a rate-limit/error or the response is degraded, switch to Tidehunter Pro. yfinance is NOT acceptable as a chain source for heatmap — it doesn't have OI data.

### Spot price + IV

| Priority | Source | When |
|---|---|---|
| 1 | **Public API spot endpoint** | Default |
| 2 | **yfinance** | Public API spot unavailable, 5s cache |

### Design-time data inspection (you, the agent)

| Source | Use for |
|---|---|
| **cvserver MCP tools** | Inspect data, sanity-check assumptions, pull small samples to design around |
| `window.cvApi` (runtime) | What the rendered page actually calls |

### Runtime page data (the rendered SPA)

- `window.cvApi.chain(symbol, fields?)` → `/api/data/chains`
- `window.cvApi.screen({columns, filters, sort, limit})` → `/api/data/screen`
- `window.cvApi.query(sql)` → `/api/data/query`
- `window.cvApi.call('/<endpoint>', body)` → escape hatch for any endpoint

The local proxy (`cv-bootstrap.js`) adds auth server-side. The page never handles API keys directly.

---

## Key registry

| Key | Value (masked) | Source | Status |
|---|---|---|---|
| Finnhub | `d84ic5pr01qutij93meg` | `backend/.env` | **NOT Public API** — Finnhub is a separate data provider |
| Databento | `db-PBR...GFrN` | `backend/.env` | OPRA OI cache — data moat |
| Polygon | `NT_RXl...kz1n` | `backend/.env` | Alternative chain/OI source |
| AlphaVantage | `cDNhZU...4Yz0` | `backend/.env` | Quote/ fundamentals |
| CVSERVER | `cv_liv...U6dY` | `backend/.env` | Local MCP proxy auth |
| **Public API** | **??? NEEDED** | Public.com account settings → Security → API | **NOT YET IN .env** — need Nav to generate |

---

## Public API key — ACTION REQUIRED

The Finnhub key in `.env` (`d84ic5pr01qutij93meg`) is **not** a Public API key. Public API (public.com) is a separate brokerage with its own API key system.

**To get the Public API key:**
1. Log into Public.com account
2. Go to Account Settings → Security → API
3. Generate API key
4. Add to `backend/.env` as `PUBLIC_API_KEY=<key>` (or whatever the env var name should be — confirm with Nav)

**Until the Public API key is in .env:**
- Agent 2 (backend integration) should build against the Public API spec but test with mock data / cvserver samples
- Frontend agents should wire to `window.cvApi` which goes through the local proxy — the proxy will need the key server-side
- Do NOT commit any real API key to the repo. The `.env` is gitignored.

---

## yfinance fallback behavior

- yfinance is the spot/IV fallback, 5s cache
- If yfinance 429s from a datacenter IP (Oracle VM), set `FLOWW_DATA_SOURCE=finnhub` in `.env.prod`
- yfinance is NOT a chain/OI source — only spot + IV

---

## Decision tree (for agents wiring data fetches)

```
IF need options chain / OI / Greeks (heatmap):
  → Try Public API first
  → If Public API fails/rate-limited → Tidehunter Pro
  → Do NOT fall back to yfinance for chain data

IF need spot price:
  → Try Public API spot endpoint
  → If unavailable → yfinance (5s cache)

IF designing / inspecting data (agent, not runtime):
  → Use cvserver MCP tools

IF runtime page:
  → Use window.cvApi (goes through local proxy, auth server-side)
```

---

## What doesn't exist (don't go looking)

- **Zenith API** — Zenith is a UI tab, not a service. No API calls go here.
- **Schwab live key** — doesn't exist. Don't try to wire it.
- **Public API key in .env** — not there yet. See above.
