WAYPOINTS.md
# Phase 9 · Heatseeker Agent 5 — waypoints

These are the checkpoints for this lane in the current session. They are checkpoints,
not promises that every path must visit in order.

1. Establish base truth
   - Confirm the live Small map and Big map paths on disk and in the branch.
   - Confirm the existing help/idle/loading/empty shapes if any.
   - Confirm test posture for the pieces this lane touches.
   - Commit a short recon note.

2. Improve first impression without touching what already works
   - Pick the highest-signal annoyances (axes, spot context, zoom wording, empty states,
     locate behavior, label legibility) and fix the visible ones first.
   - Do not refactor everything to fix one annoyance; prefer narrowing the change.

3. Add a navigable help layer
   - Make help openable from the map context (button, key, or both).
   - Make help navigable (sections, return path, search if cheap).
   - Keep help honest: explain what the map shows now and what it cannot know.

4. Stabilize the surface contract for new heatmap/UIX pieces
   - Pick one shared shape for coordinate/legend/value conventions and use it.
   - Reuse existing component idioms instead of introducing a new one for every panel.

5. Ship with tests where it counts
   - Logic that can be verified without a browser: verify it.
   - UI that is purely presentational: prefer a small, honest test or a clear note.

6. Reconciliation
   - Write the ending note: what shipped, what did not, what needs a GIP/agent next.