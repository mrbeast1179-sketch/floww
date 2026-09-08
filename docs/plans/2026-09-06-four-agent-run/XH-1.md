# XH-1 — UI quote/side/sweep/block copy honesty (Agent 3 frontend)

## Why

RECOVERY-QUEUE.md agent-3 backlog item 2. Floww surfaces quote, side, sweep, and
block data across multiple frontend surfaces (Flowseeker Pro, Heatseeker, trade journal,
scanner). Some of that data is real (provider quotes, actual trade prints where available),
some is a derived proxy (quote-based side inference, modeled sweep estimates, chain-derived
block approximations). The frontend must not misrepresent proxy data as ground truth.

This is a discovery + audit task: read every surface that renders quote/side/sweep/block
information, characterize what each renders as, identify gaps where proxy data is presented
without a label, and deliver a concrete admission list for Agent 1. No product edits until
admitted.

## Admission criteria (read before admitting)

- [ ] `FLOWSEEKER-1A` receipt (ALERT-SURFACING-1A-receipt.md) is reviewed — this task
      does not duplicate the badge-wiring work already done there.
- [ ] Agent 1 has confirmed this is the next agent-3 frontend task and named the exact
      surfaces to audit (not the whole frontend).
- [ ] Boot artifact written to run-state before any work.

## Scope (what this task covers)

### Quote rendering surfaces
- Every component that displays a price, bid/ask, last, mark, or implied value.
- How unknown/missing quotes are shown (NO_QUOTE, stale, N/A, blank — must be explicit,
  not silently zero or last-known).
- Whether quote age / source is surfaced.

### Side inference
- Where side (buy/sell) is displayed: is it a real trade print, or a quote-derived proxy?
- If derived: is the proxy label present (e.g. "quote-side", "modeled")?
- Chain-derived side (call/put OI rotation, volume imbalance) — is it labeled as a proxy?

### Sweep estimates
- Any "sweep" or "block" rendering — is it an actual detected sweep from a data provider,
  or a heuristic/chaining estimate?
- If heuristic: label, confidence, and uncertainty must be honest.

### Block / large-print representation
- Does the UI claim a block print where none is confirmed?
- Are block "estimates" from chain data labeled as modeled?

## Exclusions

- No backend changes — this is frontend-only audit + receipt.
- No new UI components — this task identifies problems; fixes come as separate admitted
  units.
- No App.js edits unless Agent 1/Nav records a standing waiver (App.js is frozen without
  explicit waiver per RECOVERY-QUEUE.md).
- No live provider calls — read existing code paths, fixtures, and rendered behavior from
  code + tests, not live market data.
- No re-litigation of F5/F6/F11/F19 honesty fixes already landed in PR40 — focus on
  quote/side/sweep/block specifically, not the general honesty checklist.

## Deliverable (before any code)

A receipt file (XH-1-discovery.md) containing:

1. **Surface inventory**: list of every frontend component/path that renders quote, side,
   sweep, or block data, with exact file:line references.
2. **Classification table**: for each surface, what data source feeds it (real quote /
   quote-proxy / model / chain-derived / unknown), whether the proxy nature is labeled in
   the UI, and what happens on missing data.
3. **Honesty gaps**: specific surfaces where proxy data is presented without a label, or
   where missing data is silently filled.
4. **Proposed fixes**: for each gap, a one-line description of what the fix should do
   (add label, change fallback, suppress misrepresentation). Each fix is a separate
   admitted unit — this task does not implement them.
5. **Blocker list**: any surface that needs a product decision (e.g. "this sweep estimate
   is intentionally coarse — do we label it or remove it?") flagged for Nav/Agent-1.

## Test discipline

- Read-only until admitted — no test changes in this discovery phase.
- After admission and implementation: every change must have a test (existing or new) that
  would fail before the fix and pass after. No skipping, no xfailing passing tests.
- Full-suite green before commit.

## Handoff to Agent 4

After the discovery receipt is complete and any admitted fixes are implemented + tested,
send the exact changed-file list and candidate head to Agent 4 for review, save the receipt
to the lane receipt directory, and obtain the next task from Agent 1.

## Estimated effort

Discovery: 45–60 minutes. Per-gap fix (if admitted): 20–40 minutes each depending on
surface complexity. This task card is the discovery + admission; implementation units are
separate.

## Code pointers

Start from `FLOWSEEKER-1A` receipt (evidence/ALERT-SURFACING-1A-receipt.md) for the
badge-wiring surfaces already touched. This task looks at the broader quote/side/sweep/block
surface, not just the badges. Read frontend/src/components/flowseeker/ and
frontend/src/components/heatseeker/ for the primary surfaces; App.js is read-only unless
waived.
