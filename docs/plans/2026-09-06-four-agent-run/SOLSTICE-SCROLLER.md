# SCROLL-1 — ticker/scroller recovery contract draft

Status: discovery ready; implementation follows the RH-1 reproduction and exact file admission. User explicitly added this problem on September 7.

## Why

The latest Hermes report says the ticker bar caps DOM buttons at 500 and search suggestions at 200 while arrows traverse about 5000 symbols. Those changes remain dirty in App.js and SkylitTickerBar.jsx. A static cap can reduce rendering work while leaving the selected ticker outside the visible list. The user calls the broken surface Solstice; verify the mounted surface before patching Skylit again.

## Outcomes

- O-1: identify the actual mounted Solstice/Skylit component, ticker response contract, total unique symbol count, rendered count and selection source of truth.
- O-2: every intended ticker is reachable through search and keyboard navigation; movement past 499/500 and last/first wraps correctly without a stale closure.
- O-3: selected ticker is revealed/focused in the actual scrollable surface, including an item outside the initial rendered window. Pointer/touch scrolling and keyboard selection agree.
- O-4: search covers the complete source collection even when suggestions are capped; query filtering occurs before result limiting, duplicates normalize consistently and active requests cannot overwrite newer results.
- O-5: DOM work stays bounded using a measured appropriate approach (moving window, paging or virtualization); total count and visible count are honestly represented. Do not require a new library by default.
- O-6: preserve ticker selection/Heatmap propagation, responsive behavior, accessibility and service-worker update behavior; prove with fixtures and browser evidence tied to the served revision.

## Exclusions

- X-1: no ticker-universe API redesign, 11,220-symbol experiment resurrection or paid data call.
- X-2: no unrelated App.js refactor, dependency/package/craco edit or service restart.
- X-3: no deletion of the user's dirty caps; preserve a snapshot and integrate only reviewed behavior.
- X-4: a bundle grep or user reload request alone does not satisfy the outcomes.

## Code pointers

Current dirty source:
- frontend/src/App.js (search cap; frozen surgical scope requires a recorded waiver).
- frontend/src/components/heatseeker/SkylitTickerBar.jsx (button cap/count/search).

Read consumers SkylitDashboard.jsx/SkylitControlBar.jsx, actual Solstice component and App.css before deciding the lease. The initial task is read-only; coordinator expands only the concrete files needed for the reproduced issue.

## Testing notes

Fixtures: empty, loading, error, 80, 500, 501 and 5000 unique tickers; mixed-case duplicates; a selected item beyond 500; a query matching only the last item; a match after position200; rapid ticker switches; unmount/remount. Assert source count, reachable result, selected item visibility and no invalid index. Test filtering-before-slicing, keyboard focus in inputs, last/first wrap and abort/stale-response behavior.

Record a browser performance trace or React render evidence for the 5000-item fixture before/after on the same host; choose an acceptance budget from the measured baseline. No invented universal latency target. Unit tests cover state logic; browser proof covers actual scroll behavior.

## Manual walkthrough

1. Open the identified surface on an isolated fixture build with served revision recorded.
2. Scroll with mouse/trackpad/touch; select and search for an item beyond the initial500.
3. Use arrows through the 499/500 boundary and wrap last/first; confirm highlighted item, visible item and loaded ticker agree.
4. Search for the last symbol, resize to narrow layout, reload and repeat.
5. Record console errors and remaining limitations. A live PWA reload remains separate from fixture proof.
