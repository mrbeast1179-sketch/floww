# Heatseeker — heatmap architecture notes (Phase 9 · Agent 5)

Architect-owned reading for any agent improving the Heatseeker map surfaces.
Lane owns frontend maps/help and roadmap GIPs; this doc is the boundary note so
improvements are deliberate, not scattered.

## What Heatseeker is on this repo, right now
- Backend: `backend/services/heatseeker.py` + `backend/services/heatseeker_snapshots.py`
  (and supporting GEX helpers under `backend/services/gex_*.py`). Those are the existing
  GEX/VEX/heatmap computation homes — not to be rewritten by this lane without a GIP.
- Frontend heatmap pieces live under `frontend/src/components/heatseeker/` — this lane
  reads them, improves the map surfaces and the help layer, and writes tests where logic
  is touched.
- Zenith is the tab that presents the legacy GEX grid as a UI surface; "Solstice" and
  "Heatseeker" naming is used across roadmap docs for the heatmap-family surfaces.

## Guiding shape for "better" maps
- A heatmap should read like a chart first, a data table second.
  - Spot-anchored strike order is easier to read than an arbitrary numeric walk.
  - Each axis should say what it is: expiry axis, strike axis, value axis conventions.
  - The map should make the "where is spot relative to this strike" relationship obvious.
- Controls should be discoverable and reversible.
  - Zoom/pan/expand should have a clear on/off and a clear return path.
  - Locating a strike or expiry should not require guessing the control grammar.
- Empty/loading/stale/error states must be honest.
  - The map does not pretend to know a future tick.
  - Loading is loading. Stale is stale. Error is error. Empty is empty.

## Help layer intent
- Help is reachable and navigable, not a wall of text.
- Help explains:
  - what the map is showing now
  - how to read sign/magnitude on the cells
  - what is uncertain in snapshot-based data
  - where to go next in the surface
- Help should not invent features the product does not have, and should not copy external
  marketing language verbatim unless it is verified accurate for this implementation.

## Surface contract (what agents should reuse)
- When adding or changing map panels, reuse existing frontend idioms for labels, numerics,
  loading/empty/error shapes, and test placement rather than inventing a new pattern for
  each panel.
- If a new map piece needs a shared helper (coordinate formatting, legend units, value
  color conventions, strike/expiry labels), add one small shared helper and use it — do
  not duplicate the same decision across panels.

## Review gates for this lane
- Each commit that touches a map surface should carry a short rationale.
- Each user-facing help change should be accurate to the current implementation.
- No merge to main without Agent 1 reviewing this lane's commits against the Roadmap GIP.

## Out of scope without a GIP
- New backend routes or new computation homes.
- New paid-tier dependencies.
- Refactoring the existing GEX/VEX computation homes just for style.
- Touching architect-frozen files.
