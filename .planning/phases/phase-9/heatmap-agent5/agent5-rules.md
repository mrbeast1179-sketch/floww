AGENT5_RULES.md
# Phase 9 · Heatseeker Agent 5 — rules of the lane

## Scope
- You are improving heatmaps and their help layer for this platform's Heatseeker surface.
- "Heatseeker" here includes the frontend pieces already named with that prefix and the
  small/big map experience as the user encounters them.
- You may improve UI, layout, labels, states, help, and small shared conventions.
- You may not silently change backend contracts, new-backend-routes, or frozen files.

## Improvement discipline
- Start from visible pain, not from the idea of a bigger change.
- Before touching a file, read the file.
- Prefer the smallest change that resolves the visible complaint.
- If a change is more than a focused edit, say so in the commit message or a note in
  this lane's dir.

## Help system rules
- Help must be optional and reachable; it must not be the gate to the map.
- Help must be navigable and returnable; a user must not get lost in it.
- Help text must be accurate to the current product, not aspirational lore.
- If something is uncertain, say what is certain and what is not.

## Tests
- If the change has testable logic, add a test.
- If the change is purely presentational and the existing stack already covers the
  surface, do not invent tests just to have tests; at minimum do not break existing ones.
- Never mark a previously passing test skipped/xfailed without architect approval.

## Collaboration
- Do not commit onto another agent's branch.
- If you need a backend shape that does not exist, write a Roadmap GIP or note it for
  Agent 3; do not invent the endpoint yourself.
- If you are unsure whether a file is frozen or owned by another lane, stop and ask
  before editing.

## Finishing
- End the session with a short reconciliation note in this lane's dir.
- Push this lane's branch if it has landed commits; never force-push.
- Agent 1 owns the final word on merge readiness for this lane.