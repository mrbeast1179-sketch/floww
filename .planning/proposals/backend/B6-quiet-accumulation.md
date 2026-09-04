# Backend Proposal B6 — Quiet Accumulation Alert (Display-First Evaluation)

**Proposed by:** Agent 3 (Backend/Data lane) · **Status:** PROPOSAL — evaluation-first, no code commitment
**Depends on:** HANDOFF B6, PLAN.md D8, FULL_PLAN.md B6, CONTRACTS.md CR-05
**Blocks:** None — evaluation only; no alert ships without Agent 4 eval + Agent 1 gate decision

## Problem

The Academy's quiet-accumulation gate (PLAN.md D8, FULL_PLAN.md D8) is: contract vol z-score >2
AND price-range compression <1σ (coiled-price requirement) over the bar window. This is
display-first — it NEVER blocks alerts in v1. Agent 3 proposes the backend plumbing for it so
Agent 4 can evaluate it with fixtures.

## Proposal

1. **Baseline plumbing:** a function in `flow_alerts.py` (or new module) that computes, per
   contract, the vol z-score and price-range compression z-score over a trailing window.
2. **Needs B1 cadence:** baseline requires historical snapshots → depends on B1. Until B1 lands,
   this is fixture-only.
3. **Display-first:** the gate fires on coiled-price fixtures (Agent 4's eval). It does NOT gate
   alerts in v1. It's a display label ("coiled") on qualifying contracts.
4. **Agent 4 evaluates:** false positive rate, signal strength, fatigue risk (see alert-gate-economics.md).
5. **Agent 1 triages:** via alert gate economics. If approved, Agent 3 implements; Agent 2 displays.

## Risks

- Needs B1 cadence for real baselines. Without B1, this is fixture-only forever.
- Quiet accumulation is hard to distinguish from routine large-block trades. Honest about that.
- Display-first means no user impact until evaluated + approved + implemented + displayed.

## Acceptance criteria (when evaluated + approved + implemented)

- [ ] Agent 3 proposal submitted (this doc)
- [ ] Agent 4 evaluation submitted (alert-gate-economics.md update)
- [ ] Agent 1 gate decision recorded (GATE_PLAN.md)
- [ ] If approved: Agent 3 implements, Agent 2 displays "coiled" label
- [ ] If rejected: spec recorded in RISK_REGISTER.md

## Gate decision requested

Agent 1: EVALUATE, not SHIP. Agent 4 evaluates first. If Agent 4 recommends shipping, Agent 1
decides. This is a proposal, not a commitment.

**Proposer's recommendation:** Evaluate. The coiled-price concept is academically grounded
(volume + compression = accumulation signal). But it needs evaluation before any code commitment.
