MISSION.md
# Phase 9 · Heatseeker Agent 5 — Heatmap Discovery Partner
Lane: phase9/heatmap-agent5
Owner: Agent 5
Architect: Agent 1 (this branch hop)

State at handoff: 2026-09-03/04. Branch off an up-to-date main, never rewrite public history.

## Why this lane exists
Nav asked for one agent to own the Heatseeker map experience end to end: the small map
and the big map, their controls, their drawer/new-tab flows, their help layer, and the
surface-level Vega/grid contract the frontend relies on. Not a tutorial clone. A working
improvement system, reviewable per commit, with tests where the lane touches logic.

## What "better" means here
- Heatmap reads as a chart, not a spreadsheet: spot-anchored strikes, axis context,
  clear zoom/expand/locate affordances, no peeking at implementation detail.
- Help layer: an openable, navigable, optionally advanced view that explains the map,
  the nodes, the signs, and how to read a snapshot — without blocking the primary task.
- Surface contract: frontend uses one source of truth for coordinates/labels/legend units;
  new panels conform to the same conventions as existing pieces (DualGEXBadge, FlipZones,
  AirPockets, StackedNodes, TugOfWar, BeachBall — these already exist).
- No regressions: existing heatseeker tests still pass, existing backend shapes untouched
  unless this lane explicitly proposes a change through the roadmap GIPs.

## What "good" means here
- Every user-facing change ships with its rationale in the commit message or a short
  note in MISSION_HEAT.md, so another agent (or Nav) can tell what was improved and why.
- State is explicit: interactive states (idle/loading/error/empty/advanced) render
  honestly; the map does not pretend to know a future tick.
- Agentic pieces stay bounded: if we build an assistant, it does not drift into new
  backend routes unless the Roadmap says so, and it never touches the architect-frozen
  surfaces without sign-off.

## Lane boundaries
- Owned: `.planning/phases/phase-9/heatmap-agent5/**`, frontend heatseeker maps/help
  surfaces, frontend-only config for those surfaces, tests for the new/changed surfaces.
- Read-only reference: backend heatseeker services, existing GEX/VEX surface helpers.
- Forbidden without sign-off: `frontend/src/App.js`, any architect-frozen backend path,
  product-code merges into another agent's branch, force-push of any kind.
- Cross-lane proposals only: add a ROADMAP GIP, do not silently change a backend contract.

## Review cadence
- Agent 1 spot-checks this lane's commits against the roadmap before any merge to main.
- End of session: a short reconciliation note lands in this lane's dir summarizing what
  shipped, what is still open, and what would need a GIP or agent re-dispatch.

Handoff rule: if you pause and resume, record where you stopped inside this lane dir and
do not assume the branch did not move.