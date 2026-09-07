# Loop improvements — hardened rules from the E4-32 pass (2026-09-07)

These are binding on future build/review passes. Each rule exists because this
session caught a real error that an earlier pass made or nearly made.

## 1. Three-dot diffs, never two-dot, for review payload

`git diff base..head` (two-dot) counts main-side-only changes as branch deletions.
E4-32 nearly reported "PR32 deletes PR29/30 work" — false. The review payload is
ALWAYS `git diff $(git merge-base base head)..head --name-status`. Then classify:

- `BOTH_SIDES` check: for each payload file, `git log merge-base..base -- <file>`.
  Empty everywhere = textually clean merge, no silent textual conflict.
- Files in two-dot but not three-dot are main-side-only: they SURVIVE the merge.
  Say so explicitly instead of alarming.

## 2. CI gates before verdict, on the merge commit

CI runs on the merge commit (`55cae55` pattern), not the branch head. Read
`gh pr checks` FIRST; a failed required check is `[CI]` blocking, full stop —
no amount of green local testing overrides it. When a job fails, pull
`--log-failed` and separate test failures from gate failures (E4-32:
backend-tests passed 11/11 pytest but failed its lint gate — one root cause, not two).

## 3. Blame-attribution for lint findings

For every lint error, `git blame` the flagged line at head AND run the same
command at base. E4-32: `main` clean + `head` 5 errors = branch-attributable,
airtight. If base is also dirty, the finding is pre-existing — still blocking
for merge-cleanliness, but the prescription (and the author to notify) differs.

## 4. No receipt on disk = no review happened

A prior pass claimed "PR32 reviewed, APPROVED" with no receipt file and a stale
head (`2b594ed` vs `c17fc61`). Rule: a review claim is backed by
`proof/receipts/<ID>.md` pinning the exact head, or it does not exist. Prompts
must state the missing-receipt fact so workers never inherit floating claims.

## 5. Scope-vs-title check on every PR

Read the PR body + file list together. If the title sells one unit (T1 scroller)
but the payload ships more (Discord backend), that is a `[SCOPE]` finding:
approve only what a linked issue authorizes. Prescribe split-vs-authorize;
never silently approve the wider delta. Check `closingIssuesReferences` — empty
means no O/X contract, which alone bars approval.

## 6. Exact-head reproduction protocol (reviewer-run, read-only)

Detached worktree at the pinned head → install with lockfile → focused contract
tests → touched-area suites → full suite. Never on the builder branch, never
mutating. Record install exit, suite/test counts observed (E4-32: 61/469 vs the
PR body's unchecked "468" — disk beats prose). Remove the temp worktree after.

## 7. Frozen-file waiver is a line item, not a vibe

`App.js` (and the CLAUDE.md frozen list) touched → the receipt carries a waiver
line: surgical description + "waiver pending/recorded". Sized the diff (E4-32:
28 lines, 3 duplications → 1 helper) so Nav's waiver call takes seconds.

## 8. Review never mutates GitHub from the architect lane

Verdict comments, labels, and merges are loop-runner/Nav actions. A receipt
PRESCRIBES the exact loop action (`gsd:rework`, outcome sync, resumption line)
so the handoff is one command, but the reviewer stops at the receipt.
