# Round 9 Frontend Memory-Leak Audit

**Auditor:** Agent A3
**Date:** 2026-05-27
**Scope:** frontend/src/hooks/ + frontend/src/components/
  (excluding /heatseeker/, CharmChart, VannaChart, OptionsChainTable, ToxicityGauge — owned by A4-A7; App.js forbidden)

## Summary

| Pattern | Total grep hits | Confirmed real leaks (High/Med/Low) |
|---------|----------------|--------------------------------------|
| setInterval w/o clearInterval | 12 | 0 / 0 / 0 |
| setTimeout w/o clearTimeout | 3 | 0 / 1 / 0 |
| addEventListener w/o removeEventListener | 11 | 0 / 0 / 1 |
| WebSocket w/o close | 0 | 0 / 0 / 0 |
| fetch w/o AbortController | 8 | 1 / 0 / 0 |
| EventSource w/o close | 1 | 0 / 0 / 0 |

Note: Several files use the `cancelled` flag pattern (MorningBriefing, DashboardSummary, PositionSizing, TradeEntry, Movers, TrinityView) which is functionally equivalent to AbortController for preventing state updates after unmount. These are marked clean.

## Findings

| # | File:Line | Pattern | Severity | Recommended fix |
|---|-----------|---------|----------|-----------------|
| 1 | SocialFlowPanel.jsx:12-23 | fetch w/o cleanup | HIGH | Add AbortController or cancelled flag |
| 2 | MlDashboard.jsx:96 | setTimeout w/o clearTimeout | MED | Clear timeout in useEffect cleanup or use ref |
| 3 | FlowTicker.jsx:43-72 | addEventListener on EventSource not individually removed | LOW | ES.close() on unmount handles cleanup; low risk |

## Top 3 (this session — agent A3 fixes)

1. **SocialFlowPanel.jsx:12-23** — fetch() in useEffect with no cleanup. On unmount or ticker change, the in-flight fetch can resolve and call setReport/setError/setLoading on an unmounted component. Classic React memory leak + state-on-unmounted warning.
2. **MlDashboard.jsx:96** — setTimeout(fetchPrediction, 3000) in triggerTraining is never cleared. If component unmounts before the 3s fires, fetchPrediction runs on unmounted component.
3. **FlowTicker.jsx:43-72** — 4 addEventListener calls on EventSource without corresponding removeEventListener. While ES.close() on unmount handles this implicitly, best practice is to remove individual listeners.

## Round 10 candidates (Med/Low from other files)

- ThemeContext.js:50-58 — fetch POST without AbortController (fire-and-forget, no state update, very low risk)
- use-toast.js:29 — setTimeout for toast removal (global singleton, not a component leak)

## Files verified clean (with cleanup)

- AlertsPanel.jsx — clearInterval + cancelled flag ✓
- DashboardSummary.jsx — clearInterval + cancelled flag ✓
- Movers.jsx — clearInterval + mounted flag ✓
- TrinityView.jsx — clearInterval + mounted flag ✓
- RateLimitDashboard.jsx — clearInterval ✓
- PositionSizing.jsx — cancelled flag ✓
- TradeEntry.jsx — cancelled flag ✓
- MorningBriefing.jsx — cancelled flag ✓
- PWAInstallBanner.js — removeEventListener ✓
- ShortcutsModal.jsx — removeEventListener ✓
- FlowCarousel.js — removeEventListener ✓
- useHeatseeker.js — AbortController ✓
- useMarketData.js — AbortController ✓
- useMLPredictions.js — AbortController ✓
- FlowTicker.jsx — ES.close() on unmount ✓
