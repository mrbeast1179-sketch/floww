# FlowSeeker Pro — Blademap port into Confluence Decoder

**Date:** 2026-06-22  **Status:** approved (data=real cvforge, file=new component swap)

## Goal
Port the Blademap.ai-style FlowSeeker Pro dashboard (built at /Users/nav/cv-apps/screener,
vanilla HTML/CSS/JS, 100% mock) into the Confluence Decoder's `flowseeker-pro` tab as a
React component wired to REAL cvforge backend data.

## Approved decisions
- **Data:** real cvforge endpoints where they exist; mock/static only where no backend exists.
- **File:** NEW component `FlowseekerProBlademap.jsx` + scoped `FlowseekerProBlademap.css`
  (classes prefixed `fsb-`). App.js `page === 'flowseeker-pro'` renders the new component.
  The agent's `FlowseekerProTab.jsx` stays in the repo, untouched (never remove).

## Panel → data source
| Panel | Source |
|---|---|
| Live Flow Feed | `GET /api/flowseeker/live?ticker&limit` → prints[] |
| Order Flow Imbalance | `GET /api/flowseeker/ofi/{t}` → of_per_level, of_aggregated, imbalance_label |
| Regime pill | `GET /api/flowseeker/regime/{t}` → current_state, confidence |
| Conviction gauge/radar | blend `GET /vpin/{t}` + `/lambda/{t}` + print classification + premium |
| GEX heatmap / Gamma | `GET /api/heatmap/{t}` → grid (real, 80 strikes) |
| Vol surface | client mock (no IV-surface backend) — clearly labelled SIM |
| Scanner | `/api/flowseeker/live` aggregated across watchlist |
| Academy | static content |

## Conviction model (real signals → 0-100)
conv = 0.30*statistical(vpin) + 0.25*pattern(classification sweep/block + premium tier)
     + 0.20*context(regime confidence) + 0.25*impact(kyle lambda r_squared). Components
sum to total (radar = [stat,pat,ctx,imp], each scaled to 0-30 for the polygon).

## Isolation
- Component self-contained; fetches via existing `useFlowseeker` hook + plain fetch.
- Plotly via window.Plotly (CDN, dynamic-load like DomHeatmap), no react-plotly dep.
- All styles scoped under `.fsb-root` — cannot affect other tabs.

## Out of scope (follow-up)
- Real IV surface endpoint; alert distribution; backtesting replay.
