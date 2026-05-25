# Round 9 Prioritized Backlog

Generated 2026-05-25 by DeepSeek V4 Pro Bulletproof session.
Source: docs/ROUND9_BACKEND_DIAGNOSTIC.md + DeepSeek working knowledge of codebase.

## Priority 1 — Backend route registration (highest urgency)

All 5 /api/* endpoints return 404 from uvicorn. Fix before any frontend work.

- Fix /api/databento route registration in backend/main.py
- Fix /api/heatseeker route registration
- Fix /api/live route registration
- Fix /api/ml route registration
- Fix /api/preferences route registration

## Priority 2 — Frontend file ownership remainder

Files in Hermes ownership that DeepSeek can't touch:

- frontend/src/App.js — toggle composition (DAY+CHARM, DTE, Expiries)
- frontend/src/components/heatseeker/*.jsx — content (imports clean per audit)
- frontend/src/components/PortfolioPanel.jsx — dummy scenarios/hedge buttons
- Skylit ticker dropdown — UX decision needed
- Dashboard tab embed style — dark theme match

## Priority 3 — Test coverage gaps

Components without test files (Phase 2 of Bulletproof session added 6 test files):

- AlertsPanel.jsx
- AlertOverlay.jsx
- FlowTicker.jsx
- HistoryPanel.jsx
- OptionsChainTable.jsx
- MultiTimeframeGEXPanel.jsx
- UOAPanel.jsx
- ToxicityGauge.jsx
- BarHeatmap.jsx
- CharmChart.jsx
- GridHeatmap.jsx
- TrinityView.jsx
- VannaChart.jsx

## Priority 4 — Frontend antipattern cleanup

From ROUND8_FRONTEND_AUDIT.md:
- Missing key props in .map() calls (~70 potential instances)
- console.log/warn/error left in production code (9 instances)

## Estimated session time per priority

- P1: 30-60 min (fix backend route registration)
- P2: requires Hermes (UX/design judgment)
- P3: 20-30 min (mechanical test scaffolding)
- P4: 15-30 min (mechanical cleanup)

## Files Modified in Bulletproof Session

- PaperTrade.jsx, SidebarPanels.jsx, AdvancedAnalyticsPanel.jsx (null-safety)
- PaperTrade.test.jsx, SidebarPanels.test.jsx, AdvancedAnalyticsPanel.test.jsx
- MorningBriefing.test.jsx, PositionSizing.test.jsx, DashboardSummary.test.jsx
- docs/ROUND9_BACKEND_DIAGNOSTIC.md
