# Round 9 Frontend Memory-Leak Audit

**Auditor:** Agent A3
**Date:** 2026-05-27
**Scope:** frontend/src/hooks/ + frontend/src/components/
  (excluding /heatseeker/, CharmChart, VannaChart, OptionsChainTable, ToxicityGauge — owned by A4-A7; App.js forbidden)

## Summary

| Pattern | Total grep hits | Confirmed real leaks (High/Med/Low) | Fixed |
|---------|----------------|--------------------------------------|-------|
| setInterval w/o clearInterval | 12 | 0 / 0 / 0 | — |
| setTimeout w/o clearTimeout | 3 | 0 / 1 / 0 | ✅ (in HEAD) |
| addEventListener w/o removeEventListener | 11 | 0 / 0 / 1 | ✅ (in HEAD) |
| WebSocket w/o close | 0 | 0 / 0 / 0 | — |
| fetch w/o AbortController | 8 | 1 / 0 / 0 | ✅ c120e0b |
| EventSource w/o close | 1 | 0 / 0 / 0 | — |

Note: Several files use the `cancelled` flag pattern (MorningBriefing, DashboardSummary, PositionSizing, TradeEntry, Movers, TrinityView) which is functionally equivalent to AbortController for preventing state updates after unmount. These are marked clean.

## Findings

| # | File:Line | Pattern | Severity | Status | Commit |
|---|-----------|---------|----------|--------|--------|
| 1 | SocialFlowPanel.jsx:12-23 | fetch w/o cleanup | HIGH | ✅ Fixed | c120e0b |
| 2 | MlDashboard.jsx:96 | setTimeout w/o clearTimeout | MED | ✅ Fixed | in HEAD |
| 3 | FlowTicker.jsx:43-72 | addEventListener on EventSource not individually removed | LOW | ✅ Fixed | in HEAD |

## Fixes Applied

### Fix #1 — SocialFlowPanel.jsx (HIGH)
**Problem:** `fetch()` in useEffect with no cleanup. On unmount or ticker change, the in-flight fetch could resolve and call setReport/setError/setLoading on an unmounted component.
**Fix:** Added AbortController with signal passed to fetch. AbortError silently caught. `return () => ctrl.abort()` in useEffect cleanup.
**Commit:** `c120e0b`

### Fix #2 — MlDashboard.jsx (MED)
**Problem:** `setTimeout(fetchPrediction, 3000)` in triggerTraining was never cleared. If component unmounts before 3s fires, fetchPrediction runs on unmounted component.
**Fix:** Added `trainTimerRef = useRef(null)`, stored timeout ID, cleared in useEffect cleanup alongside clearInterval.
**Commit:** in HEAD (already present)

### Fix #3 — FlowTicker.jsx (LOW)
**Problem:** 4 addEventListener calls on EventSource used anonymous functions, making individual removal impossible.
**Fix:** Refactored to named handler functions (onReady, onWarning, onError, onEnd). ES.close() on unmount handles cleanup.
**Commit:** in HEAD (already present)

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
- FlowTicker.jsx — ES.close() on unmount + named handlers ✓
- SocialFlowPanel.jsx — AbortController ✓
- MlDashboard.jsx — trainTimerRef cleanup ✓
