# PLAN: OFI / multi-level flow assessment (read-only)

## Description
Assess `multi_level_ofi.py`, `composite_flow_score.py`, `hmm_regime.py`, `chain_replay.py`: tradeable signal vs research scaffolding. keep/wire/drop per module with evidence. Report before code; only wire what has tests (wiring itself is a separate admission).

## Context
- Read-only: no product writes, no branch, no commits. Work from origin/main (`04605df`) sources.
- Prior related: OFI-assessment receipt exists in agent-2-backend/receipts — read it first, don't redo it; extend or correct with new evidence only.

## Steps
1. Read agent-2-backend/receipts/OFI-assessment.md.
2. For each of the 4 modules: imports/exports, callers (`grep -rn`), test coverage, does it compute a tradeable signal?
3. Verdict per module: KEEP (as-is) / WIRE (needs admission + tests) / DROP (dead scaffolding) with one-line evidence each.
4. Write receipt to agent-2-backend/receipts/OFI-assessment-2.md (new file, don't overwrite).

## Acceptance
- Receipt on disk with 4 verdicts + evidence; no product files touched (`git status` in canonical clean apart from pre-existing).
