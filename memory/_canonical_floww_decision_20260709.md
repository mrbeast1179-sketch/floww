# Canonical Floww Decision — 2026-07-09

## Decision: `/Users/nav/Documents/GitHub/floww` is CANONICAL

## Comparison

| Property | `/Users/nav/Documents/GitHub/floww` (WINNER) | `/Users/nav/GitHub/floww` (LOSER) |
|---|---|---|
| Origin URL | `https://github.com/JattMoosewala5911/floww.git` | `git@github.com:JattMoosewala5911/floww.git` |
| Last commit | `f42c9ed` — feat(paper-trading): wire execution engine into routes + server | `f42c9ed` — same |
| Commit count | 263 | 263 |
| Branch | main | main |
| Tracked status | Clean | Clean |
| Untracked files | 0 | 1 (`backend/tests/services/test_microstructure_property.py`, 340 lines) |

## Rationale

Per protocol: both repos have identical commit counts (263) and identical last commits (f42c9ed). The tiebreaker rule states: "If both match origin and commit counts are equal → the one at /Users/nav/Documents/GitHub/floww wins by precedent (all memory + dispatch plans reference it)."

## Loser handling

The loser has ONE untracked file not in the canonical:
- `backend/tests/services/test_microstructure_property.py` (340 lines, property-based microstructure tests using hypothesis)

**Action taken**: Copied this file to the canonical repo before archiving the loser.

**Archive path**: `~/.archive/floww_dup_20260709/`

## Reversibility

To restore the duplicate: `mv ~/.archive/floww_dup_20260709/ ~/GitHub/floww`

## Verification

- Canonical origin: https://github.com/JattMoosewala5911/floww.git
- Canonical commit count: 263
- Canonical last commit: f42c9ed
- Decision is unambiguous and reversible
